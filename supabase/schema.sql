-- sapinails.il · database (Supabase / Postgres)
-- Appointments + club punch cards for Sapir's studio.
-- Admins are the users listed in public.admins (Sapir's login). To add one:
--   insert into public.admins (user_id) select id from auth.users where email = '...';
-- Visitors (role anon) can only call public_info(), public_busy() and request_booking().

begin;

-- ---------- helpers ----------
create or replace function public.norm_phone(p text) returns text
language sql immutable parallel safe set search_path = '' as $$
  select case
           when d ~ '^972' then '0' || substr(d, 4)
           when d ~ '^5[0-9]{8}$' then '0' || d
           else d
         end
  from (select case when x ~ '^00' then substr(x, 3) else x end as d
        from (select regexp_replace(coalesce(p, ''), '[^0-9]', '', 'g') as x) a) b
$$;

create or replace function public.hhmm_to_min(t text) returns int
language sql immutable parallel safe set search_path = '' as $$
  select case when t ~ '^[0-9]{1,2}:[0-9]{2}$'
              then split_part(t, ':', 1)::int * 60 + split_part(t, ':', 2)::int end
$$;

create or replace function public.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- ---------- tables ----------
create table if not exists public.admins (
  user_id uuid primary key references auth.users (id) on delete cascade,
  created_at timestamptz not null default now()
);

create table if not exists public.settings (
  id text primary key default 'main' check (id = 'main'),
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.services (
  id text primary key,
  name text not null check (char_length(name) between 1 and 60),
  minutes int not null check (minutes between 5 and 480),
  price numeric(8, 2),
  counts boolean not null default true,      -- marks a punch on the club card when done
  sort int not null default 0,
  active boolean not null default true,
  updated_at timestamptz not null default now()
);

-- one row per club card; data keeps the shape the card app uses
-- {name, phone, g, notes, punches, rewards, visits, createdAt, lastVisit, updatedAt, log[]}
create table if not exists public.clients (
  id text primary key,
  data jsonb not null,
  phone_norm text generated always as (public.norm_phone(data ->> 'phone')) stored,
  updated_at timestamptz not null default now()
);
create index if not exists clients_phone_norm on public.clients (phone_norm);

create table if not exists public.appointments (
  id uuid primary key default gen_random_uuid(),
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  service_id text references public.services (id) on delete set null,
  service_name text not null default '',
  minutes int not null,
  price numeric(8, 2),
  name text not null default '',
  phone text not null default '',
  phone_norm text generated always as (public.norm_phone(phone)) stored,
  note text not null default '',
  addons text[] not null default '{}',
  client_id text references public.clients (id) on delete set null,
  status text not null default 'pending'
    check (status in ('pending', 'confirmed', 'done', 'noshow', 'cancelled')),
  source text not null default 'online' check (source in ('online', 'admin')),
  is_new boolean not null default false,
  punched boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint appointments_range check (ends_at > starts_at),
  constraint appointments_no_overlap exclude using gist (tstzrange(starts_at, ends_at, '[)') with &&)
    where (status in ('pending', 'confirmed'))
);
create index if not exists appointments_starts_at on public.appointments (starts_at);
create index if not exists appointments_phone_norm on public.appointments (phone_norm);

create table if not exists public.blocks (
  id uuid primary key default gen_random_uuid(),
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  all_day boolean not null default false,
  reason text not null default '',
  created_at timestamptz not null default now(),
  constraint blocks_range check (ends_at > starts_at)
);
create index if not exists blocks_starts_at on public.blocks (starts_at);

drop trigger if exists settings_touch on public.settings;
create trigger settings_touch before update on public.settings for each row execute function public.touch_updated_at();
drop trigger if exists services_touch on public.services;
create trigger services_touch before update on public.services for each row execute function public.touch_updated_at();
drop trigger if exists clients_touch on public.clients;
create trigger clients_touch before update on public.clients for each row execute function public.touch_updated_at();
drop trigger if exists appointments_touch on public.appointments;
create trigger appointments_touch before update on public.appointments for each row execute function public.touch_updated_at();

-- ---------- access ----------
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.admins a where a.user_id = auth.uid());
$$;

alter table public.admins enable row level security;
alter table public.settings enable row level security;
alter table public.services enable row level security;
alter table public.clients enable row level security;
alter table public.appointments enable row level security;
alter table public.blocks enable row level security;

drop policy if exists admins_self on public.admins;
create policy admins_self on public.admins for select to authenticated using (user_id = auth.uid());

drop policy if exists settings_admin on public.settings;
create policy settings_admin on public.settings for all to authenticated using (public.is_admin()) with check (public.is_admin());
drop policy if exists services_admin on public.services;
create policy services_admin on public.services for all to authenticated using (public.is_admin()) with check (public.is_admin());
drop policy if exists clients_admin on public.clients;
create policy clients_admin on public.clients for all to authenticated using (public.is_admin()) with check (public.is_admin());
drop policy if exists appointments_admin on public.appointments;
create policy appointments_admin on public.appointments for all to authenticated using (public.is_admin()) with check (public.is_admin());
drop policy if exists blocks_admin on public.blocks;
create policy blocks_admin on public.blocks for all to authenticated using (public.is_admin()) with check (public.is_admin());

revoke all on public.admins, public.settings, public.services, public.clients, public.appointments, public.blocks from anon;
grant usage on schema public to anon, authenticated;
grant select on public.admins to authenticated;
grant select, insert, update, delete on public.settings, public.services, public.clients, public.appointments, public.blocks to authenticated;

-- ---------- public functions (the booking page) ----------
create or replace function public.public_info() returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'settings', coalesce((
      select jsonb_build_object(
        'studioName', s.data -> 'studioName', 'ownerName', s.data -> 'ownerName',
        'ownerPhone', s.data -> 'ownerPhone', 'address', s.data -> 'address', 'intro', s.data -> 'intro',
        'slotMinutes', s.data -> 'slotMinutes', 'bufferMinutes', s.data -> 'bufferMinutes',
        'minNoticeMinutes', s.data -> 'minNoticeMinutes', 'maxDaysAhead', s.data -> 'maxDaysAhead',
        'hours', s.data -> 'hours', 'cardSize', s.data -> 'cardSize', 'addons', s.data -> 'addons')
      from public.settings s where s.id = 'main'), '{}'::jsonb),
    'services', coalesce((
      select jsonb_agg(jsonb_build_object('id', v.id, 'name', v.name, 'minutes', v.minutes, 'price', v.price)
                       order by v.sort, v.name)
      from public.services v where v.active), '[]'::jsonb),
    'now', now());
$$;

create or replace function public.public_busy(p_from timestamptz, p_to timestamptz)
returns table (s timestamptz, e timestamptz)
language sql stable security definer set search_path = '' as $$
  select a.starts_at, a.ends_at from public.appointments a
   where a.status in ('pending', 'confirmed') and a.starts_at < p_to and a.ends_at > p_from
     and p_to > p_from and p_to - p_from <= interval '120 days'
  union all
  select b.starts_at, b.ends_at from public.blocks b
   where b.starts_at < p_to and b.ends_at > p_from
     and p_to > p_from and p_to - p_from <= interval '120 days';
$$;

create or replace function public.request_booking(
  p_service text, p_start timestamptz, p_name text, p_phone text,
  p_note text default '', p_addons text[] default '{}')
returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare
  tz constant text := 'Asia/Jerusalem';
  st jsonb;
  svc public.services%rowtype;
  v_name text := left(regexp_replace(btrim(coalesce(p_name, '')), '\s+', ' ', 'g'), 60);
  v_phone text := public.norm_phone(p_phone);
  v_note text := left(btrim(coalesce(p_note, '')), 300);
  v_addons text[];
  step int; buf int; notice int; ahead int;
  local_ts timestamp; start_min int; wd int;
  w jsonb; ws int; we int; fits boolean := false;
  v_end timestamptz;
  v_client text; v_known boolean; v_status text; v_id uuid;
begin
  select data into st from public.settings where id = 'main';
  if st is null then return jsonb_build_object('ok', false, 'error', 'closed'); end if;
  select * into svc from public.services where id = p_service and active;
  if not found then return jsonb_build_object('ok', false, 'error', 'service'); end if;
  if char_length(v_name) < 2 then return jsonb_build_object('ok', false, 'error', 'name'); end if;
  if v_phone !~ '^0[0-9]{8,9}$' and v_phone !~ '^[1-9][0-9]{9,14}$' then
    return jsonb_build_object('ok', false, 'error', 'phone');
  end if;
  select coalesce(array_agg(distinct left(btrim(x), 40)), '{}') into v_addons
    from unnest(coalesce(p_addons, '{}')) x where btrim(x) <> '';
  v_addons := v_addons[1:6];

  step := greatest(5, coalesce((st ->> 'slotMinutes')::int, 30));
  buf := greatest(0, coalesce((st ->> 'bufferMinutes')::int, 0));
  notice := greatest(0, coalesce((st ->> 'minNoticeMinutes')::int, 0));
  ahead := greatest(1, coalesce((st ->> 'maxDaysAhead')::int, 30));

  local_ts := p_start at time zone tz;
  start_min := extract(hour from local_ts)::int * 60 + extract(minute from local_ts)::int;
  wd := extract(dow from local_ts)::int;
  if extract(second from local_ts) <> 0 then return jsonb_build_object('ok', false, 'error', 'time'); end if;
  if p_start < now() + make_interval(mins => notice) then return jsonb_build_object('ok', false, 'error', 'notice'); end if;
  if local_ts::date > (now() at time zone tz)::date + ahead then return jsonb_build_object('ok', false, 'error', 'ahead'); end if;

  for w in select * from jsonb_array_elements(coalesce(st -> 'hours' -> (wd::text), '[]'::jsonb)) loop
    ws := public.hhmm_to_min(w ->> 'from');
    we := public.hhmm_to_min(w ->> 'to');
    if ws is not null and we is not null and start_min >= ws and start_min + svc.minutes <= we
       and (start_min - ws) % step = 0 then
      fits := true;
      exit;
    end if;
  end loop;
  if not fits then return jsonb_build_object('ok', false, 'error', 'time'); end if;

  v_end := p_start + make_interval(mins => svc.minutes);

  perform pg_advisory_xact_lock(hashtext('sapinails.booking'));

  if exists (select 1 from public.appointments a
              where a.status in ('pending', 'confirmed')
                and a.starts_at < v_end + make_interval(mins => buf)
                and a.ends_at + make_interval(mins => buf) > p_start)
     or exists (select 1 from public.blocks b
              where b.starts_at < v_end + make_interval(mins => buf)
                and b.ends_at + make_interval(mins => buf) > p_start) then
    return jsonb_build_object('ok', false, 'error', 'taken');
  end if;

  if (select count(*) from public.appointments a
       where a.phone_norm = v_phone and a.status in ('pending', 'confirmed') and a.starts_at > now()) >= 2 then
    return jsonb_build_object('ok', false, 'error', 'limit');
  end if;
  if (select count(*) from public.appointments a
       where a.source = 'online' and a.created_at > now() - interval '1 hour') >= 20 then
    return jsonb_build_object('ok', false, 'error', 'busy');
  end if;

  select c.id into v_client from public.clients c where c.phone_norm = v_phone order by c.updated_at desc limit 1;
  v_known := v_client is not null
          or exists (select 1 from public.appointments a where a.phone_norm = v_phone and a.status in ('confirmed', 'done'));
  v_status := case when v_known and coalesce(st ->> 'approval', 'new') = 'new' then 'confirmed' else 'pending' end;

  insert into public.appointments (starts_at, ends_at, service_id, service_name, minutes, price,
                                   name, phone, note, addons, client_id, status, source, is_new)
  values (p_start, v_end, svc.id, svc.name, svc.minutes, svc.price,
          v_name, v_phone, v_note, v_addons, v_client, v_status, 'online', not v_known)
  returning id into v_id;

  return jsonb_build_object('ok', true, 'id', v_id, 'status', v_status, 'isNew', not v_known,
                            'start', p_start, 'end', v_end, 'service', svc.name,
                            'minutes', svc.minutes, 'price', svc.price);
exception when exclusion_violation then
  return jsonb_build_object('ok', false, 'error', 'taken');
end;
$$;

revoke execute on function public.public_info(), public.public_busy(timestamptz, timestamptz),
  public.request_booking(text, timestamptz, text, text, text, text[]), public.is_admin() from public;
grant execute on function public.public_info(), public.public_busy(timestamptz, timestamptz),
  public.request_booking(text, timestamptz, text, text, text, text[]) to anon, authenticated;
grant execute on function public.is_admin() to authenticated;

-- merge a few settings keys in one statement (admin only, through the row rules above)
create or replace function public.merge_settings(p_patch jsonb) returns jsonb
language sql volatile security invoker set search_path = '' as $$
  update public.settings set data = data || p_patch where id = 'main' returning data;
$$;
revoke execute on function public.merge_settings(jsonb) from public;
grant execute on function public.merge_settings(jsonb) to authenticated;

-- live updates for the admin screen
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    begin
      alter publication supabase_realtime add table public.appointments, public.clients, public.settings, public.services, public.blocks;
    exception when duplicate_object then null;
    end;
  end if;
end $$;

-- =====================================================================
-- Added 2026-10-22 (also in supabase/migrations/2026-10-22_cards_reminders_push.sql)
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

commit;
