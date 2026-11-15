-- Undo of supabase/migrations/2026-11-15_booking_no_promo.sql. Run in the Supabase SQL editor only if needed.
-- Brings back request_booking() and the card trigger as they were on 2026-10-22, and removes the rule that
-- keeps the "no invitations" mark on a card. The column appointments.no_promo stays (what clients asked is
-- not thrown away), and marks that are already on cards stay too.
-- The booking page keeps working after this: when the server does not know the new field, the page saves the
-- booking without it and writes the request in the note to Sapir.

begin;

drop function if exists public.request_booking(text, timestamptz, text, text, text, text[], boolean);

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

revoke execute on function public.request_booking(text, timestamptz, text, text, text, text[]) from public;
grant execute on function public.request_booking(text, timestamptz, text, text, text, text[]) to anon, authenticated;

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

drop trigger if exists clients_keep_no_promo on public.clients;
drop function if exists public.clients_keep_no_promo();

do $$
declare
  n int;
begin
  select count(*) into n from pg_proc p join pg_namespace s on s.oid = p.pronamespace
   where s.nspname = 'public' and p.proname = 'request_booking';
  if n <> 1 then raise exception 'request_booking: % versions, expected exactly 1', n; end if;
  if not has_function_privilege('anon', 'public.request_booking(text, timestamptz, text, text, text, text[])', 'execute') then
    raise exception 'request_booking: visitors (anon) cannot run it';
  end if;
end $$;

commit;

notify pgrst, 'reload schema';
