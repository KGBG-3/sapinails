-- Run once in the Supabase SQL editor on top of the 2026-10-22 schema.
-- Safe to run again. The same statements are part of supabase/schema.sql.
-- To undo: supabase/rollback/2026-11-15_booking_no_promo.sql
--
-- 2026-11-15 · the booking form lets a client ask not to get invitations to book again
--   1. appointments.no_promo keeps what she asked in the form.
--   2. request_booking() takes the answer (p_no_promo). The old six-argument version is dropped in the
--      same transaction: two versions side by side would make every booking call ambiguous.
--   3. The mark moves to her club card (data.noPromo, the time in ms, the same mark the admin screen sets)
--      when the booking is saved, or later when the booking gets its card.
--   4. A save of a card that does not mention the mark keeps it. The admin screen removes it with noPromo: 0.
-- Everything runs in one transaction and checks itself at the end: if a check fails, nothing is changed.

begin;

alter table public.appointments add column if not exists no_promo boolean not null default false;  -- asked in the booking form not to get invitations

drop function if exists public.request_booking(text, timestamptz, text, text, text, text[]);

create or replace function public.request_booking(
  p_service text, p_start timestamptz, p_name text, p_phone text,
  p_note text default '', p_addons text[] default '{}', p_no_promo boolean default false)
returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare
  tz constant text := 'Asia/Jerusalem';
  st jsonb;
  svc public.services%rowtype;
  v_name text := left(regexp_replace(btrim(coalesce(p_name, '')), '\s+', ' ', 'g'), 60);
  v_phone text := public.norm_phone(p_phone);
  v_note text := left(btrim(coalesce(p_note, '')), 300);
  v_no_promo boolean := coalesce(p_no_promo, false);
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

  -- no_promo reaches her card in the appointments_card trigger
  insert into public.appointments (starts_at, ends_at, service_id, service_name, minutes, price,
                                   name, phone, note, addons, client_id, status, source, is_new, no_promo)
  values (p_start, v_end, svc.id, svc.name, svc.minutes, svc.price,
          v_name, v_phone, v_note, v_addons, v_client, v_status, 'online', not v_known, v_no_promo)
  returning id into v_id;

  return jsonb_build_object('ok', true, 'id', v_id, 'status', v_status, 'isNew', not v_known,
                            'start', p_start, 'end', v_end, 'service', svc.name,
                            'minutes', svc.minutes, 'price', svc.price);
exception when exclusion_violation then
  return jsonb_build_object('ok', false, 'error', 'taken');
end;
$$;

revoke execute on function public.request_booking(text, timestamptz, text, text, text, text[], boolean) from public;
grant execute on function public.request_booking(text, timestamptz, text, text, text, text[], boolean) to anon, authenticated;

-- runs when a booking is saved, or becomes confirmed (online, approval, or added by Sapir):
-- opens the club card when it is missing, and carries "no invitations" from the booking form to the card
create or replace function public.appointments_card() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  got_card boolean := false;
  t bigint;
begin
  if new.status = 'confirmed' and new.client_id is null then
    if tg_op = 'INSERT' then
      new.client_id := public.card_for(new.name, new.phone);
      got_card := true;
    elsif old.status is distinct from 'confirmed' then
      new.client_id := public.card_for(new.name, new.phone);
      got_card := true;
    end if;
  end if;
  -- once per booking: when it is saved, or when it gets its card. A later change of the booking
  -- does not bring back a mark that Sapir removed.
  if new.no_promo and new.client_id is not null and (tg_op = 'INSERT' or got_card) then
    t := floor(extract(epoch from clock_timestamp()) * 1000)::bigint;
    update public.clients c
       set data = c.data || jsonb_build_object('noPromo', t, 'updatedAt', t)
     where c.id = new.client_id
       and not (case when jsonb_typeof(c.data -> 'noPromo') = 'number'
                     then (c.data ->> 'noPromo')::numeric > 0 else false end);
  end if;
  return new;
end $$;
drop trigger if exists appointments_card on public.appointments;
create trigger appointments_card before insert or update of status on public.appointments
  for each row execute function public.appointments_card();

-- The admin screen saves a whole card at a time. A screen that was opened before the mark was set, or one
-- that still runs an older version, would save the card without it. Such a save keeps the mark.
-- Removing the mark is a save that says so: noPromo: 0.
create or replace function public.clients_keep_no_promo() returns trigger
language plpgsql set search_path = '' as $$
begin
  if not (new.data ? 'noPromo') and jsonb_typeof(old.data -> 'noPromo') = 'number' then
    if (old.data ->> 'noPromo')::numeric > 0 then
      new.data := new.data || jsonb_build_object('noPromo', old.data -> 'noPromo');
    end if;
  end if;
  return new;
end $$;
drop trigger if exists clients_keep_no_promo on public.clients;
create trigger clients_keep_no_promo before update on public.clients
  for each row execute function public.clients_keep_no_promo();

revoke execute on function public.appointments_card(), public.clients_keep_no_promo() from public, anon, authenticated;

-- the checks: an error here undoes everything above
do $$
declare
  n int;
begin
  select count(*) into n from pg_proc p join pg_namespace s on s.oid = p.pronamespace
   where s.nspname = 'public' and p.proname = 'request_booking';
  if n <> 1 then raise exception 'request_booking: % versions, expected exactly 1', n; end if;
  if not has_function_privilege('anon', 'public.request_booking(text, timestamptz, text, text, text, text[], boolean)', 'execute') then
    raise exception 'request_booking: visitors (anon) cannot run it';
  end if;
  if has_function_privilege('anon', 'public.appointments_card()', 'execute')
     or has_function_privilege('anon', 'public.clients_keep_no_promo()', 'execute') then
    raise exception 'an inner function is open to visitors';
  end if;
end $$;

commit;

-- the API re-reads the list of functions (Supabase also does this by itself after a change)
notify pgrst, 'reload schema';

-- what is in place now (one row; every value should be true, and booking_versions 1)
select
  (select count(*) from pg_proc p join pg_namespace s on s.oid = p.pronamespace
    where s.nspname = 'public' and p.proname = 'request_booking') as booking_versions,
  has_function_privilege('anon', 'public.request_booking(text, timestamptz, text, text, text, text[], boolean)', 'execute') as visitors_can_book,
  exists (select 1 from information_schema.columns
           where table_schema = 'public' and table_name = 'appointments' and column_name = 'no_promo') as column_added,
  exists (select 1 from pg_trigger where tgname = 'clients_keep_no_promo' and not tgisinternal) as mark_kept_on_save,
  exists (select 1 from pg_trigger where tgname = 'appointments_card' and not tgisinternal) as card_trigger,
  exists (select 1 from pg_trigger where tgname = 'appointments_notify' and not tgisinternal) as phone_alert_trigger;
