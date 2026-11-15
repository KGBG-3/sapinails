-- A dry run of the booking flow on the real database, for the Supabase SQL editor.
-- It ends with an error ON PURPOSE: the error message is the report, and the error undoes everything the
-- run did. No booking, no card and no phone alert are left behind, and nobody is notified.
-- Read the first line of the message: "verdict": "ALL OK" or "PROBLEM".
--
-- What it walks through, with an invented client and the real opening hours:
--   1. a new client books with "no invitations" ticked        -> the booking keeps no_promo
--   2. the booking is approved                                 -> her card is opened with the mark
--   3. the card is saved by a screen that does not know marks  -> the mark stays
--   4. the mark is removed the way the admin screen does it    -> it is gone
--   5. she books again the way the page did before 2026-11-15  -> saved, the card stays unmarked
--   6. she books again with the box ticked                     -> the card is marked again
--   7. every online booking queued one phone alert
do $$
declare
  nm constant text := 'בדיקה אוטומטית';
  ph constant text := '050-000-0017';
  st jsonb; svc public.services%rowtype; step int; ahead int;
  ts timestamptz; r jsonb; a public.appointments%rowtype; c jsonb;
  phase int := 1; tries int := 0; id2 uuid; v_card text;
  q0 bigint; q1 bigint;
  good boolean := true;
  rep jsonb := '{}'::jsonb;
begin
  if exists (select 1 from public.clients where phone_norm = public.norm_phone(ph))
     or exists (select 1 from public.appointments where phone_norm = public.norm_phone(ph)) then
    raise exception 'DRY RUN, nothing was saved: the test phone number is in use, pick another one';
  end if;
  select data into st from public.settings where id = 'main';
  select * into svc from public.services where active order by minutes, id limit 1;
  if st is null or svc.id is null then raise exception 'DRY RUN, nothing was saved: no settings or no open treatment'; end if;
  step := greatest(5, coalesce((st ->> 'slotMinutes')::int, 30));
  ahead := greatest(1, coalesce((st ->> 'maxDaysAhead')::int, 30));
  begin select count(*) into q0 from net.http_request_queue; exception when others then q0 := null; end;

  for ts in
    select (d.day + make_interval(mins => g.m)) at time zone 'Asia/Jerusalem'
      from generate_series(1, ahead) n
      cross join lateral (select (now() at time zone 'Asia/Jerusalem')::date + n as day) d
      cross join lateral jsonb_array_elements(coalesce(st -> 'hours' -> (extract(dow from d.day)::int::text), '[]'::jsonb)) w
      cross join lateral generate_series(public.hhmm_to_min(w ->> 'from'), public.hhmm_to_min(w ->> 'to') - svc.minutes, step) g(m)
     order by 1
  loop
    tries := tries + 1;
    if phase = 2 then
      r := public.request_booking(p_service := svc.id, p_start := ts, p_name := nm, p_phone := ph, p_note := 'dry run', p_addons := '{}');
    else
      r := public.request_booking(p_service := svc.id, p_start := ts, p_name := nm, p_phone := ph, p_note := 'dry run', p_addons := '{}', p_no_promo := true);
    end if;
    if not (r ->> 'ok')::boolean then
      continue when r ->> 'error' in ('taken', 'time', 'notice', 'ahead');
      rep := rep || jsonb_build_object('stopped_at_step', phase, 'answer', r);
      good := false;
      exit;
    end if;
    select * into a from public.appointments where id = (r ->> 'id')::uuid;

    if phase = 1 then
      rep := rep || jsonb_build_object('1_new_client_ticked', jsonb_build_object('status', a.status, 'no_promo', a.no_promo, 'has_card', a.client_id is not null));
      good := good and a.no_promo and a.source = 'online';
      update public.appointments set status = 'confirmed' where id = a.id;
      select * into a from public.appointments where id = a.id;
      v_card := a.client_id;
      select data into c from public.clients where id = v_card;
      rep := rep || jsonb_build_object('2_approved', jsonb_build_object('card_opened', v_card is not null,
        'card_marked', coalesce((c ->> 'noPromo')::numeric > 0, false), 'name_on_card', c ->> 'name', 'punches', c -> 'punches'));
      good := good and v_card is not null and coalesce((c ->> 'noPromo')::numeric > 0, false);
      update public.clients set data = (data - 'noPromo') || '{"notes":"saved by an old screen"}' where id = v_card;
      select data into c from public.clients where id = v_card;
      rep := rep || jsonb_build_object('3_old_screen_save', jsonb_build_object('mark_kept', coalesce((c ->> 'noPromo')::numeric > 0, false), 'rest_saved', c ->> 'notes' = 'saved by an old screen'));
      good := good and coalesce((c ->> 'noPromo')::numeric > 0, false) and c ->> 'notes' = 'saved by an old screen';
      update public.clients set data = data || '{"noPromo":0}' where id = v_card;
      select data into c from public.clients where id = v_card;
      rep := rep || jsonb_build_object('4_mark_removed', (c ->> 'noPromo')::numeric = 0);
      good := good and (c ->> 'noPromo')::numeric = 0;
    elsif phase = 2 then
      id2 := a.id;
      select data into c from public.clients where id = v_card;
      rep := rep || jsonb_build_object('5_page_as_before', jsonb_build_object('status', a.status, 'no_promo', a.no_promo, 'same_card', a.client_id = v_card,
        'card_marked', coalesce((c ->> 'noPromo')::numeric > 0, false)));
      good := good and not a.no_promo and a.client_id = v_card and not coalesce((c ->> 'noPromo')::numeric > 0, false);
      update public.appointments set status = 'cancelled' where id = id2;
    else
      select data into c from public.clients where id = v_card;
      rep := rep || jsonb_build_object('6_ticked_again', jsonb_build_object('status', a.status, 'no_promo', a.no_promo, 'card_marked', coalesce((c ->> 'noPromo')::numeric > 0, false)));
      good := good and a.no_promo and coalesce((c ->> 'noPromo')::numeric > 0, false);
      exit;
    end if;
    phase := phase + 1;
  end loop;

  good := good and phase = 3 and rep ? '6_ticked_again';
  begin select count(*) into q1 from net.http_request_queue; exception when others then q1 := null; end;
  rep := rep || jsonb_build_object('7_phone_alerts_queued', case when q0 is null or q1 is null then 'could not read the queue' else (q1 - q0)::text || ' (expected 3)' end,
                                   'hours_tried', tries, 'treatment', svc.name);
  if q0 is not null and q1 is not null then good := good and q1 - q0 = 3; end if;
  raise exception 'DRY RUN, nothing was saved. "verdict": "%" %', case when good then 'ALL OK' else 'PROBLEM' end, jsonb_pretty(rep);
end $$;
