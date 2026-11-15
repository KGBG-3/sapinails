// Rehearses the database files on a throwaway Postgres that runs inside Node (PGlite). Nothing here
// touches the real database.
//   node tools/tests/check_db.mjs
// What it does:
//   1. builds the database as it was before the last migration (supabase/schema.sql from git, or the
//      file given in BEFORE=...), adds the migration, and walks through the booking and card flows;
//   2. runs the undo file, checks that booking works as before, and runs the migration again;
//   3. builds a fresh database from today's supabase/schema.sql and checks it is the same as (1).
import { PGlite } from '@electric-sql/pglite';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const MIG = 'supabase/migrations/2026-11-15_booking_no_promo.sql';
const UNDO = 'supabase/rollback/2026-11-15_booking_no_promo.sql';
const BEFORE_REF = process.env.BEFORE_REF || '48a2d70';   // the commit whose schema.sql matches the database before the migration
const read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');
const before = process.env.BEFORE ? fs.readFileSync(process.env.BEFORE, 'utf8')
  : execFileSync('git', ['-C', ROOT, 'show', `${BEFORE_REF}:supabase/schema.sql`], { encoding: 'utf8' });

// what Supabase gives and plain Postgres does not: the API roles, auth.uid(), pg_net, and the rule that
// new tables and functions in public are open to the API roles unless a file closes them
const STUBS = `
create role anon nologin; create role authenticated nologin; create role service_role nologin;
create schema auth;
create table auth.users (id uuid primary key default gen_random_uuid(), email text);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated;
create schema extensions; create schema net;
create table net.calls (id bigserial primary key, url text, body jsonb);
create function net.http_post(url text, body jsonb default '{}', params jsonb default '{}', headers jsonb default '{}', timeout_milliseconds int default 5000)
returns bigint language plpgsql security definer as $$ declare i bigint; begin insert into net.calls (url, body) values (url, body) returning id into i; return i; end $$;
grant usage on schema net to anon, authenticated;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;
`;
const SEED = `
insert into auth.users (id, email) values ('00000000-0000-0000-0000-0000000000aa', 'owner@example.test');
insert into public.admins (user_id) values ('00000000-0000-0000-0000-0000000000aa');
insert into public.settings (id, data) values ('main', '{"studioName":"סטודיו","slotMinutes":30,"bufferMinutes":0,"minNoticeMinutes":120,"maxDaysAhead":30,
  "hours":{"0":[{"from":"08:00","to":"21:00"}],"1":[{"from":"08:00","to":"21:00"}],"2":[{"from":"08:00","to":"21:00"}],"3":[{"from":"08:00","to":"21:00"}],
           "4":[{"from":"08:00","to":"21:00"}],"5":[{"from":"08:00","to":"21:00"}],"6":[{"from":"08:00","to":"21:00"}]}}');
insert into public.services (id, name, minutes, price, sort) values ('gel', 'לק ג׳ל', 60, 130, 1);
create function public.t_slot(d int, hm text) returns timestamptz language sql stable as
  $$ select (((now() at time zone 'Asia/Jerusalem')::date + d) + hm::time) at time zone 'Asia/Jerusalem' $$;
`;

let fails = 0, passes = 0;
const ok = (cond, label, extra) => { if (cond) { passes++; console.log('  ok   ' + label); } else { fails++; console.log('  FAIL ' + label + (extra !== undefined ? ' -> ' + JSON.stringify(extra) : '')); } };
const one = async (db, sql, params) => (await db.query(sql, params)).rows[0];
const all = async (db, sql, params) => (await db.query(sql, params)).rows;

// a call the way a visitor's browser makes it: role anon, named arguments
async function book(db, args) {
  const names = Object.keys(args);
  const sql = `select public.request_booking(${names.map((n, i) => `${n} := $${i + 1}`).join(', ')}) as r`;
  await db.exec('set role anon');
  try { return (await db.query(sql, names.map(n => args[n]))).rows[0].r; }
  catch (e) { return { thrown: e.message }; }
  finally { await db.exec('reset role'); }
}
// statements the way Sapir's admin screen makes them: role authenticated, signed in as the owner
async function asAdmin(db, sql, params) {
  await db.exec(`set role authenticated; select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000000aa', false)`);
  try { return await db.query(sql, params); }
  finally { await db.exec(`reset role; select set_config('request.jwt.claim.sub', '', false)`); }
}
const slot = async (db, d, hm) => (await one(db, 'select public.t_slot($1, $2) as t', [d, hm])).t;
const card = async (db, id) => { const r = await one(db, 'select data from public.clients where id = $1', [id]); return r ? r.data : null; };
const appt = async (db, id) => one(db, 'select * from public.appointments where id = $1', [id]);
const marked = d => !!d && typeof d.noPromo === 'number' && d.noPromo > 0;
// the database keeps the fields of a card in its own order, so cards are compared with sorted keys
const canon = v => (Array.isArray(v) ? v.map(canon) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canon(v[k])])) : v);
const without = (d, ...keys) => { const o = { ...d }; keys.forEach(k => delete o[k]); return JSON.stringify(canon(o)); };

async function newDb(schema) {
  const db = new PGlite();
  await db.exec(STUBS);
  await db.exec(schema);
  await db.exec(SEED);
  return db;
}
async function snapshot(db) {
  const fns = await all(db, `select p.oid::regprocedure::text as sig, pg_get_functiondef(p.oid) as def,
      (select coalesce(array_agg(a.grantee::regrole::text || ':' || a.privilege_type order by 1), '{}') from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a) as acl
    from pg_proc p join pg_namespace s on s.oid = p.pronamespace where s.nspname = 'public' and p.proname <> 't_slot' order by 1`);
  const trg = await all(db, `select tgrelid::regclass::text || '.' || tgname as name, pg_get_triggerdef(oid) as def from pg_trigger
    where not tgisinternal and tgrelid::regclass::text like 'appointments%' or (not tgisinternal and tgrelid in ('public.clients'::regclass, 'public.settings'::regclass, 'public.services'::regclass)) order by 1`);
  const cols = await all(db, `select table_name || '.' || column_name as name, data_type, is_nullable, coalesce(column_default, '') as def
    from information_schema.columns where table_schema = 'public' order by 1`);
  return { fns, trg, cols };
}

async function flows(db, label) {
  console.log(`\n${label}`);
  const calls0 = +(await one(db, 'select count(*) as n from net.calls')).n;
  let online = 0;

  // the page as it is today: six fields, no p_no_promo
  let r = await book(db, { p_service: 'gel', p_start: await slot(db, 2, '09:00'), p_name: 'רותי ישנה', p_phone: '050-100-0001', p_note: '', p_addons: [] });
  ok(r.ok === true && r.status === 'pending' && r.isNew === true, 'old page (six fields): a new client is saved as pending', r); online++;
  let a = await appt(db, r.id);
  ok(a.no_promo === false && a.client_id === null, 'old page: no_promo is false and no card yet', [a.no_promo, a.client_id]);

  // new client, box ticked
  r = await book(db, { p_service: 'gel', p_start: await slot(db, 2, '10:00'), p_name: 'נועה חדשה', p_phone: '050-100-0002', p_note: 'שלום', p_addons: ['פרנץ׳'], p_no_promo: true });
  ok(r.ok === true && r.status === 'pending', 'box ticked, new client: saved as pending', r); online++;
  const idNew = r.id;
  a = await appt(db, idNew);
  ok(a.no_promo === true && a.client_id === null, 'box ticked: no_promo is true on the booking, no card before approval', [a.no_promo, a.client_id]);
  ok(+(await one(db, `select count(*) as n from public.clients where phone_norm = '0501000002'`)).n === 0, 'box ticked: no card was opened for a pending request');
  // Sapir approves from the admin screen
  await asAdmin(db, `update public.appointments set status = 'confirmed' where id = $1`, [idNew]);
  a = await appt(db, idNew);
  let c = await card(db, a.client_id);
  ok(!!a.client_id && marked(c), 'approval: the card is opened with the mark', c && c.noPromo);
  ok(c && c.name === 'נועה חדשה' && c.punches === 0 && Array.isArray(c.log) && c.log.length === 1 && c.updatedAt === c.noPromo, 'approval: the new card is whole (name, 0 punches, join line)', c);
  const idCardNew = a.client_id, markNew = c.noPromo;

  // existing card, box ticked
  const base = { name: 'דנה ותיקה', phone: '052-200-0003', g: 'f', notes: 'אוהבת ורוד', punches: 3, rewards: 1, visits: 9, createdAt: 1700000000000, lastVisit: 1750000000000, updatedAt: 1750000000000, log: [{ t: 1700000000000, a: 'join', p: 0 }] };
  await asAdmin(db, `insert into public.clients (id, data) values ('c-dana', $1)`, [JSON.stringify(base)]);
  r = await book(db, { p_service: 'gel', p_start: await slot(db, 2, '11:00'), p_name: 'דנה ותיקה', p_phone: '0522000003', p_note: '', p_addons: [], p_no_promo: true });
  ok(r.ok === true && r.status === 'confirmed' && r.isNew === false, 'box ticked, known client: confirmed at once', r); online++;
  a = await appt(db, r.id); c = await card(db, 'c-dana');
  ok(a.client_id === 'c-dana' && a.no_promo === true && marked(c), 'known client: her card is marked', c && c.noPromo);
  ok(without(c, 'noPromo', 'updatedAt') === without(base, 'updatedAt'), 'known client: nothing else on the card changed', c);
  const markDana = c.noPromo, idDana1 = r.id;

  // again with the box ticked: the first date stays
  r = await book(db, { p_service: 'gel', p_start: await slot(db, 3, '11:00'), p_name: 'דנה ותיקה', p_phone: '0522000003', p_no_promo: true });
  ok(r.ok === true, 'second booking with the box ticked', r); online++;
  c = await card(db, 'c-dana');
  ok(c.noPromo === markDana, 'an existing mark keeps its date', [c.noPromo, markDana]);
  const idDana2 = r.id;

  // without the box: the mark stays
  await db.query(`update public.appointments set status = 'done' where id = $1`, [idDana1]);
  r = await book(db, { p_service: 'gel', p_start: await slot(db, 4, '11:00'), p_name: 'דנה ותיקה', p_phone: '0522000003', p_no_promo: false });
  ok(r.ok === true, 'third booking, box not ticked', r); online++;
  c = await card(db, 'c-dana');
  ok(c.noPromo === markDana, 'a booking without the box does not remove the mark');
  r = await book(db, { p_service: 'gel', p_start: await slot(db, 5, '11:00'), p_name: 'דנה ותיקה', p_phone: '0522000003', p_no_promo: true });
  ok(r.ok === false && r.error === 'limit', 'the limit of two open bookings still holds', r);

  // known from an older booking but without a card: the card is opened inside the booking
  await db.query(`insert into public.appointments (starts_at, ends_at, service_id, service_name, minutes, name, phone, status, source)
                  values (now() - interval '30 days', now() - interval '30 days' + interval '1 hour', 'gel', 'לק ג׳ל', 60, 'מיכל', '0533000004', 'done', 'admin')`);
  r = await book(db, { p_service: 'gel', p_start: await slot(db, 2, '13:00'), p_name: 'מיכל', p_phone: '053-300-0004', p_no_promo: true });
  ok(r.ok === true && r.status === 'confirmed', 'known from an older booking, no card: confirmed at once', r); online++;
  a = await appt(db, r.id); c = await card(db, a.client_id);
  ok(!!a.client_id && marked(c) && c.name === 'מיכל', 'the card that is opened inside the booking carries the mark', c);

  // p_no_promo: null behaves like "not ticked"
  r = await book(db, { p_service: 'gel', p_start: await slot(db, 2, '14:00'), p_name: 'שירה', p_phone: '0544000005', p_no_promo: null });
  ok(r.ok === true, 'p_no_promo null is accepted', r); online++;
  ok((await appt(db, r.id)).no_promo === false, 'p_no_promo null is saved as false');

  // a taken hour: no booking and nothing on the card
  await asAdmin(db, `insert into public.clients (id, data) values ('c-tal', $1)`, [JSON.stringify({ ...base, name: 'טל', phone: '0555000006' })]);
  r = await book(db, { p_service: 'gel', p_start: await slot(db, 2, '10:00'), p_name: 'טל', p_phone: '0555000006', p_no_promo: true });
  ok(r.ok === false && r.error === 'taken', 'a taken hour is refused', r);
  ok(!marked(await card(db, 'c-tal')), 'a refused booking leaves the card unmarked');
  r = await book(db, { p_service: 'nope', p_start: await slot(db, 2, '15:00'), p_name: 'טל', p_phone: '0555000006', p_no_promo: true });
  ok(r.ok === false && r.error === 'service', 'an unknown treatment is refused', r);

  // the admin screen removes the mark (noPromo: 0); later changes of an old booking do not bring it back
  await asAdmin(db, `insert into public.clients (id, data) values ('c-dana', $1) on conflict (id) do update set data = excluded.data`, [JSON.stringify({ ...c0(await card(db, 'c-dana')), noPromo: 0 })]);
  c = await card(db, 'c-dana');
  ok(c.noPromo === 0 && !marked(c), 'the admin screen can remove the mark (noPromo: 0)', c.noPromo);
  await asAdmin(db, `update public.appointments set status = 'done', punched = true where id = $1`, [idDana2]);
  await asAdmin(db, `update public.appointments set status = 'confirmed', punched = false where id = $1`, [idDana2]);
  await asAdmin(db, `update public.appointments set status = 'cancelled' where id = $1`, [idDana2]);
  ok(!marked(await card(db, 'c-dana')), 'done, reopened, cancelled: a removed mark stays removed');
  // a save without the field after the removal keeps it removed
  await asAdmin(db, `insert into public.clients (id, data) values ('c-dana', $1) on conflict (id) do update set data = excluded.data`, [JSON.stringify(c0(await card(db, 'c-dana'), 'noPromo'))]);
  c = await card(db, 'c-dana');
  ok(!marked(c) && !('noPromo' in c), 'after removal, a normal save leaves the card without the field', c.noPromo);

  // a save that does not know the mark (older screen, or read before the mark was set) keeps it
  c = await card(db, idCardNew);
  const stale = { ...c0(c, 'noPromo'), punches: 1, visits: 1, notes: 'נשמר ממסך ישן', updatedAt: c.updatedAt + 5 };
  await asAdmin(db, `insert into public.clients (id, data) values ($1, $2) on conflict (id) do update set data = excluded.data`, [idCardNew, JSON.stringify(stale)]);
  c = await card(db, idCardNew);
  ok(c.noPromo === markNew && c.punches === 1 && c.notes === 'נשמר ממסך ישן', 'a save without the field keeps the mark and takes the rest', c);
  await asAdmin(db, `update public.clients set data = $2 where id = $1`, [idCardNew, JSON.stringify({ ...stale, punches: 2 })]);
  c = await card(db, idCardNew);
  ok(c.noPromo === markNew && c.punches === 2, 'the same with a plain update');
  // a save that carries the mark, or a newer one, is taken as is
  await asAdmin(db, `update public.clients set data = $2 where id = $1`, [idCardNew, JSON.stringify({ ...stale, noPromo: markNew + 1000 })]);
  ok((await card(db, idCardNew)).noPromo === markNew + 1000, 'a save that carries a mark is taken as is');
  // odd old values never block a save
  for (const [odd, name] of [['"abc"', 'text'], ['null', 'null'], ['-5', 'negative'], ['true', 'true'], ['{"a":1}', 'object']]) {
    await db.query(`update public.clients set data = jsonb_set(data, '{noPromo}', $1::jsonb) where id = 'c-tal'`, [odd]);
    let err = null;
    try { await asAdmin(db, `update public.clients set data = data - 'noPromo' || '{"notes":"x"}' where id = 'c-tal'`); } catch (e) { err = e.message; }
    c = await card(db, 'c-tal');
    ok(err === null && !('noPromo' in c), `an odd old value (${name}) does not block a save and is not kept`, err || c.noPromo);
  }

  // the phone alert: one call for every online booking, none for the rest
  const calls = await all(db, 'select body from net.calls where id > $1 order by id', [calls0]);
  ok(calls.length === online && calls.every(x => x.body.op === 'booking' && x.body.id), `one phone alert per online booking (${online})`, calls.length);

  // what visitors and signed-in strangers can reach
  const tryAs = async (role, sql) => { await db.exec(`set role ${role}`); try { await db.query(sql); return 'allowed'; } catch (e) { return /permission denied/.test(e.message) ? 'denied' : e.message; } finally { await db.exec('reset role'); } };
  ok(await tryAs('anon', 'select 1 from public.appointments limit 1') === 'denied', 'visitors cannot read bookings');
  ok(await tryAs('anon', 'select 1 from public.clients limit 1') === 'denied', 'visitors cannot read cards');
  ok(await tryAs('anon', `select public.card_for('x y', '0501112222')`) === 'denied', 'visitors cannot open a card directly');
  ok(await tryAs('anon', `update public.clients set data = data`) === 'denied', 'visitors cannot change cards');
  await db.exec('set role authenticated');
  const seen = +(await one(db, 'select count(*) as n from public.clients')).n;
  await db.exec('reset role');
  ok(seen === 0, 'a signed-in user who is not the owner sees no cards', seen);
  const versions = await all(db, `select p.oid::regprocedure::text as sig from pg_proc p join pg_namespace s on s.oid = p.pronamespace where s.nspname = 'public' and p.proname = 'request_booking'`);
  ok(versions.length === 1 && /boolean\)$/.test(versions[0].sig), 'exactly one request_booking, the new one', versions);
}
const c0 = (d, ...drop) => { const o = { ...d }; drop.forEach(k => delete o[k]); return o; };

const mig = read(MIG), undo = read(UNDO);

// ---------- 1. yesterday's database + the migration ----------
console.log('yesterday\'s database');
const A = await newDb(before);
let r = await book(A, { p_service: 'gel', p_start: await slot(A, 1, '09:00'), p_name: 'לפני השינוי', p_phone: '0509990000', p_note: '', p_addons: [] });
ok(r.ok === true, 'before the migration: a booking is saved', r);
r = await book(A, { p_service: 'gel', p_start: await slot(A, 1, '10:00'), p_name: 'לפני השינוי', p_phone: '0509990001', p_no_promo: true });
ok(!!r.thrown && /does not exist/.test(r.thrown), 'before the migration: the new field is unknown (the page falls back on this)', r);
// a mark that the admin screen set before the migration
await asAdmin(A, `insert into public.clients (id, data) values ('c-old', '{"name":"מסומנת מהבוקר","phone":"0508880000","g":"f","notes":"","punches":2,"rewards":0,"visits":2,"createdAt":1,"lastVisit":null,"updatedAt":2,"log":[],"noPromo":1763190000000}')`);

const last = await A.exec(mig);
const summary = last[last.length - 1].rows[0];
ok(summary && +summary.booking_versions === 1 && ['visitors_can_book', 'column_added', 'mark_kept_on_save', 'card_trigger', 'phone_alert_trigger'].every(k => summary[k] === true), 'the migration ran and its closing row is all true', summary);
ok(+(await one(A, `select count(*) as n from public.appointments where no_promo`)).n === 0, 'existing bookings got no_promo = false');
ok((await card(A, 'c-old')).noPromo === 1763190000000, 'a mark from before the migration is untouched');
await A.exec(mig);
ok(true, 'the migration can be run a second time');
await flows(A, 'after the migration');
const snapA = await snapshot(A);

// ---------- 2. undo, then forward again ----------
console.log('\nundo');
await A.exec(undo);
r = await book(A, { p_service: 'gel', p_start: await slot(A, 6, '09:00'), p_name: 'אחרי ביטול', p_phone: '0507770000', p_note: '', p_addons: [] });
ok(r.ok === true, 'after the undo: the old page still books', r);
r = await book(A, { p_service: 'gel', p_start: await slot(A, 6, '10:00'), p_name: 'אחרי ביטול', p_phone: '0507770001', p_no_promo: true });
ok(!!r.thrown && /does not exist/.test(r.thrown), 'after the undo: the new field is unknown again', r);
ok((await card(A, 'c-old')).noPromo === 1763190000000, 'after the undo: marks on cards are still there');
ok((await all(A, `select 1 from pg_trigger where tgname = 'clients_keep_no_promo'`)).length === 0, 'after the undo: the keep-the-mark rule is gone');
await A.exec(undo);
ok(true, 'the undo can be run a second time');
await A.exec(mig);
r = await book(A, { p_service: 'gel', p_start: await slot(A, 6, '11:00'), p_name: 'שוב קדימה', p_phone: '0507770002', p_no_promo: true });
ok(r.ok === true, 'forward again: the new field works', r);
const snapA2 = await snapshot(A);
ok(JSON.stringify(snapA2) === JSON.stringify(snapA), 'undo + migration ends in the same database as the migration alone');

// ---------- 3. a fresh install from today's schema.sql ----------
console.log('\nfresh install from supabase/schema.sql');
const B = await newDb(read('supabase/schema.sql'));
const snapB = await snapshot(B);
for (const part of ['fns', 'trg', 'cols']) {
  const a = snapA[part], b = snapB[part];
  const diff = [];
  const names = new Set([...a.map(x => x.sig || x.name), ...b.map(x => x.sig || x.name)]);
  for (const n of names) {
    const x = a.find(y => (y.sig || y.name) === n), y = b.find(z => (z.sig || z.name) === n);
    if (JSON.stringify(x) !== JSON.stringify(y)) diff.push(n);
  }
  ok(diff.length === 0, `schema.sql and (old schema + migration) agree on ${part === 'fns' ? 'functions and who may run them' : part === 'trg' ? 'triggers' : 'columns'} (${a.length})`, diff);
}
await B.exec(read('supabase/schema.sql'));
ok(JSON.stringify(await snapshot(B)) === JSON.stringify(snapB), 'schema.sql can be run again on an existing database');
await flows(B, 'fresh install: the same flows');

console.log(`\n${fails ? 'FAILED: ' + fails : 'ALL PASSED'} (${passes} checks)`);
process.exit(fails ? 1 : 0);
