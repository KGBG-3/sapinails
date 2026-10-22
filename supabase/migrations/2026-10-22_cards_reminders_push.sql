-- Run once in the Supabase SQL editor on top of the 2026-10-21 schema.
-- Safe to run again. The same statements are part of supabase/schema.sql.

begin;

-- =====================================================================
-- 2026-10-22 · club card on confirmation, reminders, phone alerts
-- =====================================================================

-- ---------- a club card for every confirmed booking ----------
-- Finds the card by phone (or by exact name when there is no phone) and opens a new one when missing.
create or replace function public.card_for(p_name text, p_phone text) returns text
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_name text := left(regexp_replace(btrim(coalesce(p_name, '')), '\s+', ' ', 'g'), 40);
  v_phone text := public.norm_phone(p_phone);
  v_id text;
  t bigint := floor(extract(epoch from clock_timestamp()) * 1000)::bigint;
begin
  if char_length(v_name) < 2 and v_phone = '' then return null; end if;
  perform pg_advisory_xact_lock(hashtext('sapinails.card:' || case when v_phone <> '' then v_phone else v_name end));
  if v_phone <> '' then
    select c.id into v_id from public.clients c where c.phone_norm = v_phone order by c.updated_at desc limit 1;
  else
    select c.id into v_id from public.clients c where c.data ->> 'name' = v_name order by c.updated_at desc limit 1;
  end if;
  if v_id is null then
    v_id := substr(md5(random()::text || clock_timestamp()::text), 1, 20);
    insert into public.clients (id, data) values (v_id, jsonb_build_object(
      'name', case when v_name <> '' then v_name else 'ללא שם' end,
      'phone', btrim(coalesce(p_phone, '')), 'g', 'f', 'notes', '',
      'punches', 0, 'rewards', 0, 'visits', 0, 'createdAt', t, 'lastVisit', null, 'updatedAt', t,
      'log', jsonb_build_array(jsonb_build_object('t', t, 'a', 'join', 'p', 0))));
  end if;
  return v_id;
end $$;

-- runs when a booking is saved as confirmed or becomes confirmed (online, approval, or added by Sapir)
create or replace function public.appointments_card() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.status = 'confirmed' and new.client_id is null then
    if tg_op = 'INSERT' then
      new.client_id := public.card_for(new.name, new.phone);
    elsif old.status is distinct from 'confirmed' then
      new.client_id := public.card_for(new.name, new.phone);
    end if;
  end if;
  return new;
end $$;
drop trigger if exists appointments_card on public.appointments;
create trigger appointments_card before insert or update of status on public.appointments
  for each row execute function public.appointments_card();

-- ---------- reminders & notifications ----------
alter table public.appointments add column if not exists reminded_at timestamptz;  -- Sapir sent the day-before message
alter table public.appointments add column if not exists notified_at timestamptz;  -- Sapir's phone got the new-booking alert

-- the phones that get alerts (Web Push subscriptions), managed from the admin screen
create table if not exists public.push_subs (
  endpoint text primary key,
  p256dh text not null,
  auth text not null,
  label text not null default '',
  created_at timestamptz not null default now(),
  last_ok_at timestamptz,
  fails int not null default 0
);
alter table public.push_subs enable row level security;
drop policy if exists push_subs_admin on public.push_subs;
create policy push_subs_admin on public.push_subs for all to authenticated using (public.is_admin()) with check (public.is_admin());
revoke all on public.push_subs from anon;
grant select, insert, update, delete on public.push_subs to authenticated;

-- values only the server function reads (its web-push key pair, last evening list). No policies: no API access.
create table if not exists public.server_kv (
  k text primary key,
  v jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.server_kv enable row level security;
revoke all on public.server_kv from anon, authenticated;

-- the notify function works with the server key
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant usage on schema public to service_role;
    grant select, insert, update, delete on public.appointments, public.settings, public.push_subs, public.server_kv to service_role;
  end if;
end $$;

-- the Edge Function that sends the alerts (deployed with JWT verification off; it checks every request itself)
create or replace function public.notify_url() returns text
language sql immutable set search_path = '' as $$
  select 'https://gjmeuimtupsordxqepcz.supabase.co/functions/v1/notify'
$$;

-- a new online booking pings the function; a failure here never blocks the booking
create or replace function public.appointments_notify() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  begin
    perform net.http_post(
      url := public.notify_url(),
      body := jsonb_build_object('op', 'booking', 'id', new.id),
      headers := '{"Content-Type": "application/json"}'::jsonb,
      timeout_milliseconds := 8000);
  exception when others then
    null;
  end;
  return null;
end $$;
drop trigger if exists appointments_notify on public.appointments;
create trigger appointments_notify after insert on public.appointments
  for each row when (new.source = 'online') execute function public.appointments_notify();

revoke execute on function public.card_for(text, text), public.appointments_card(), public.appointments_notify(), public.notify_url()
  from public, anon, authenticated;

-- extensions for the web call and the hourly check (Supabase); skipped where they are not installed
do $$
begin
  create extension if not exists pg_net with schema extensions;
exception when others then
  raise notice 'pg_net not enabled: %', sqlerrm;
end $$;
do $$
begin
  create extension if not exists pg_cron with schema pg_catalog;
  grant usage on schema cron to postgres;
  grant all privileges on all tables in schema cron to postgres;
  -- every hour; the function itself decides when it is time for the evening list (Israel time)
  perform cron.schedule('sapinails-hourly', '0 * * * *',
    $job$ select net.http_post(url := public.notify_url(), body := '{"op":"hourly"}'::jsonb, timeout_milliseconds := 8000) $job$);
exception when others then
  raise notice 'pg_cron not enabled: %', sqlerrm;
end $$;

-- one-time: confirmed bookings that have no card yet get one now
update public.appointments a set client_id = public.card_for(a.name, a.phone)
 where a.status = 'confirmed' and a.client_id is null;

commit;
