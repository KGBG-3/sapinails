-- A dry run of the saves that Sapir's admin screen makes, on the real database, for the Supabase SQL editor.
-- It runs as the role the admin screen uses (authenticated, signed in as the owner), on the card that was
-- changed last, and ends with an error ON PURPOSE: the error message is the report, and the error undoes
-- everything the run did. The card and the booking are left exactly as they were.
-- Read the first line of the message: "verdict": "ALL OK" or "PROBLEM".
--
--   1. the owner sees the cards                                    (the access rules let her in)
--   2. a plain save of a card                                      -> saved
--   3. the mark "no invitations" is set the way the screen does it -> on the card
--   4. a save from a screen that does not know the mark            -> the mark stays
--   5. the mark is removed the way the screen does it (noPromo: 0) -> gone
--   6. the next plain save                                         -> the card has no such field
--   7. a booking is saved without a change                         -> saved (the card trigger runs)
do $$
declare
  uid uuid; cid text; aid uuid;
  d jsonb; c jsonb; n int; seen int;
  t bigint := floor(extract(epoch from clock_timestamp()) * 1000)::bigint;
  good boolean := true;
  rep jsonb := '{}'::jsonb;
begin
  select user_id into uid from public.admins order by created_at limit 1;
  select id into cid from public.clients order by updated_at desc limit 1;
  select id into aid from public.appointments order by created_at desc limit 1;
  if uid is null or cid is null then raise exception 'DRY RUN, nothing was saved: no owner or no card to try on'; end if;

  perform set_config('request.jwt.claim.sub', uid::text, true);
  perform set_config('request.jwt.claim.role', 'authenticated', true);
  perform set_config('request.jwt.claims', jsonb_build_object('sub', uid, 'role', 'authenticated')::text, true);
  set local role authenticated;

  select count(*) into seen from public.clients;
  rep := rep || jsonb_build_object('1_owner_sees_cards', seen);
  good := good and seen > 0;

  select data - 'noPromo' into d from public.clients where id = cid;
  if d is null then raise exception 'DRY RUN, nothing was saved: the owner cannot read the card (%)', rep; end if;

  insert into public.clients (id, data) values (cid, d || jsonb_build_object('notes', 'dry run'))
    on conflict (id) do update set data = excluded.data;
  get diagnostics n = row_count;
  select data into c from public.clients where id = cid;
  rep := rep || jsonb_build_object('2_plain_save', n = 1 and c ->> 'notes' = 'dry run');
  good := good and n = 1 and c ->> 'notes' = 'dry run';

  insert into public.clients (id, data) values (cid, d || jsonb_build_object('noPromo', t))
    on conflict (id) do update set data = excluded.data;
  select data into c from public.clients where id = cid;
  rep := rep || jsonb_build_object('3_mark_set', (c ->> 'noPromo')::numeric = t);
  good := good and (c ->> 'noPromo')::numeric = t;

  insert into public.clients (id, data) values (cid, d || jsonb_build_object('notes', 'saved by an old screen'))
    on conflict (id) do update set data = excluded.data;
  select data into c from public.clients where id = cid;
  rep := rep || jsonb_build_object('4_old_screen_save', jsonb_build_object('mark_kept', coalesce((c ->> 'noPromo')::numeric = t, false), 'rest_saved', c ->> 'notes' = 'saved by an old screen'));
  good := good and coalesce((c ->> 'noPromo')::numeric = t, false) and c ->> 'notes' = 'saved by an old screen';

  insert into public.clients (id, data) values (cid, d || jsonb_build_object('noPromo', 0))
    on conflict (id) do update set data = excluded.data;
  select data into c from public.clients where id = cid;
  rep := rep || jsonb_build_object('5_mark_removed', (c ->> 'noPromo')::numeric = 0);
  good := good and (c ->> 'noPromo')::numeric = 0;

  insert into public.clients (id, data) values (cid, d)
    on conflict (id) do update set data = excluded.data;
  select data into c from public.clients where id = cid;
  rep := rep || jsonb_build_object('6_next_save_has_no_field', not (c ? 'noPromo'));
  good := good and not (c ? 'noPromo');

  if aid is not null then
    update public.appointments set status = status where id = aid;
    get diagnostics n = row_count;
    rep := rep || jsonb_build_object('7_booking_saved', n = 1);
    good := good and n = 1;
  else
    rep := rep || jsonb_build_object('7_booking_saved', 'no booking to try on');
  end if;

  raise exception 'DRY RUN, nothing was saved. "verdict": "%" %', case when good then 'ALL OK' else 'PROBLEM' end, jsonb_pretty(rep);
end $$;
