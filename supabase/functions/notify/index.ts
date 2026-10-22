// Supabase Edge Function "notify": phone alerts (Web Push) for Sapir's studio.
//
// Who calls it:
//   the database, when a client books online       {op: 'booking', id}
//   the database, every hour (pg_cron)              {op: 'hourly'}
//   the admin screen                                {op: 'key'} and {op: 'test', endpoint}
//
// Deploy with "Verify JWT" turned off. No login is needed because every request is limited here:
//   booking  only a fresh online booking that was not announced yet, so each booking alerts once
//   hourly   only at the evening-list hour (Israel time), once a day
//   test     only to a phone that is already registered, at most once every 20 seconds
//   key      returns the public half of the web push key pair
// The key pair is created on first use and kept in public.server_kv, which only the server can read.
// Nothing needs to be pasted into the dashboard: the database keys come from the environment.

const ZONE = 'Asia/Jerusalem';
const SITE = 'https://kgbg-3.github.io/sapinails/';
const ADMIN = SITE + 'admin/';
const CORS: Record<string, string> = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

// ---------- bytes ----------
const te = new TextEncoder();
const enc = (s: string): Uint8Array => te.encode(s);
export function b64u(bytes: Uint8Array): string {
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
export function unb64u(s: string): Uint8Array {
  const t = s.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(t + '==='.slice((t.length + 3) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}
function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}
async function hmac(key: Uint8Array, data: Uint8Array): Promise<Uint8Array> {
  const k = await crypto.subtle.importKey('raw', key, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return new Uint8Array(await crypto.subtle.sign('HMAC', k, data));
}

// ---------- web push (RFC 8291 payload encryption, RFC 8292 VAPID) ----------
export async function encryptPayload(
  p256dh: string, authSecret: string, plaintext: Uint8Array,
  salt: Uint8Array = crypto.getRandomValues(new Uint8Array(16)),
): Promise<Uint8Array> {
  const uaPublic = unb64u(p256dh);
  const auth = unb64u(authSecret);
  const local = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']) as CryptoKeyPair;
  const asPublic = new Uint8Array(await crypto.subtle.exportKey('raw', local.publicKey));
  const uaKey = await crypto.subtle.importKey('raw', uaPublic, { name: 'ECDH', namedCurve: 'P-256' }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: 'ECDH', public: uaKey }, local.privateKey, 256));
  const prkKey = await hmac(auth, shared);
  const ikm = (await hmac(prkKey, concat(enc('WebPush: info\0'), uaPublic, asPublic, new Uint8Array([1])))).slice(0, 32);
  const prk = await hmac(salt, ikm);
  const cek = (await hmac(prk, concat(enc('Content-Encoding: aes128gcm\0'), new Uint8Array([1])))).slice(0, 16);
  const nonce = (await hmac(prk, concat(enc('Content-Encoding: nonce\0'), new Uint8Array([1])))).slice(0, 12);
  const key = await crypto.subtle.importKey('raw', cek, 'AES-GCM', false, ['encrypt']);
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, key, concat(plaintext, new Uint8Array([2]))));
  const header = new Uint8Array(21);
  header.set(salt, 0);
  new DataView(header.buffer).setUint32(16, 4096);
  header[20] = asPublic.length;
  return concat(header, asPublic, sealed);
}

type Vapid = { jwk: JsonWebKey; pub: string };
export async function vapidAuth(endpoint: string, v: Vapid, now = Date.now()): Promise<string> {
  const aud = new URL(endpoint).origin;
  const head = b64u(enc(JSON.stringify({ typ: 'JWT', alg: 'ES256' })));
  const claims = b64u(enc(JSON.stringify({ aud, exp: Math.floor(now / 1000) + 12 * 3600, sub: SITE })));
  const key = await crypto.subtle.importKey('jwk', v.jwk, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
  const sig = new Uint8Array(await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, key, enc(`${head}.${claims}`)));
  return `vapid t=${head}.${claims}.${b64u(sig)}, k=${v.pub}`;
}
export async function newVapid(): Promise<Vapid> {
  const kp = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']) as CryptoKeyPair;
  return {
    jwk: await crypto.subtle.exportKey('jwk', kp.privateKey),
    pub: b64u(new Uint8Array(await crypto.subtle.exportKey('raw', kp.publicKey))),
  };
}

// ---------- database (REST with the server key) ----------
// deno-lint-ignore no-explicit-any
const env = (k: string): string => ((globalThis as any).Deno?.env.get(k) ?? (globalThis as any).process?.env?.[k] ?? '') as string;
function serverKey(): string {
  try {
    const all = JSON.parse(env('SUPABASE_SECRET_KEYS') || '{}');
    const v = all.default || Object.values(all)[0];
    if (typeof v === 'string' && v) return v;
  } catch (_) { /* projects without the new keys */ }
  return env('SUPABASE_SERVICE_ROLE_KEY');
}
// deno-lint-ignore no-explicit-any
async function rest(path: string, opt: { method?: string; body?: unknown; prefer?: string } = {}): Promise<any> {
  const key = serverKey();
  const headers: Record<string, string> = { apikey: key, 'Content-Type': 'application/json' };
  if (!key.startsWith('sb_')) headers.Authorization = `Bearer ${key}`;
  if (opt.prefer) headers.Prefer = opt.prefer;
  const r = await fetch(`${env('SUPABASE_URL')}/rest/v1/${path}`, {
    method: opt.method || 'GET', headers, body: opt.body === undefined ? undefined : JSON.stringify(opt.body),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`db ${r.status} ${path.split('?')[0]}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : null;
}
async function kvGet(k: string) {
  const rows = await rest(`server_kv?select=v&k=eq.${encodeURIComponent(k)}`);
  return rows.length ? rows[0].v : null;
}
async function kvPut(k: string, v: unknown) {
  await rest('server_kv?on_conflict=k', { method: 'POST', body: { k, v, updated_at: new Date().toISOString() }, prefer: 'resolution=merge-duplicates,return=minimal' });
}
async function kvAdd(k: string, v: unknown): Promise<boolean> {
  const rows = await rest('server_kv?on_conflict=k', { method: 'POST', body: { k, v }, prefer: 'resolution=ignore-duplicates,return=representation' });
  return rows.length > 0;
}
async function vapidKeys(): Promise<Vapid> {
  const have = await kvGet('vapid');
  if (have && have.jwk && have.pub) return have;
  const v = await newVapid();
  if (await kvAdd('vapid', v)) return v;
  return await kvGet('vapid'); // a parallel request created them first
}
async function settings() {
  const rows = await rest('settings?select=data&id=eq.main');
  return (rows[0] && rows[0].data) || {};
}
// deno-lint-ignore no-explicit-any
export function prefs(st: any) {
  const n = (st && st.notify) || {};
  const h = Number(n.eveningHour);
  return { booking: n.booking !== false, eveningHour: n.eveningHour === undefined || n.eveningHour === null || !Number.isFinite(h) ? 20 : h };
}

// ---------- Israel time ----------
const fmt = new Intl.DateTimeFormat('en-CA', {
  timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', weekday: 'short',
});
export function il(ms: number) {
  const o: Record<string, string> = {};
  for (const p of fmt.formatToParts(new Date(ms))) o[p.type] = p.value;
  return {
    y: +o.year, m: +o.month, d: +o.day, h: (+o.hour) % 24, mi: +o.minute,
    key: `${o.year}-${o.month}-${o.day}`, wd: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(o.weekday),
  };
}
const offsetAt = (ms: number) => { const p = il(ms); return Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi) - Math.floor(ms / 60000) * 60000; };
export function zoned(key: string, min: number): number {
  const [y, m, d] = key.split('-').map(Number);
  const g = Date.UTC(y, m - 1, d, 0, min);
  let t = g - offsetAt(g);
  t = g - offsetAt(t);
  return t;
}
export const addDays = (key: string, n: number) => {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
};
const pad = (n: number) => String(n).padStart(2, '0');
const hm = (ms: number) => { const p = il(ms); return `${pad(p.h)}:${pad(p.mi)}`; };
const WD = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'];
export function whenText(ms: number, now = Date.now()): string {
  const p = il(ms), today = il(now).key;
  const day = p.key === today ? 'היום' : p.key === addDays(today, 1) ? 'מחר' : `יום ${WD[p.wd]} ${p.d}.${p.m}`;
  return `${day} בשעה ${hm(ms)}`;
}
const firstName = (n: string) => String(n || '').trim().split(/\s+/)[0] || '';

// ---------- sending ----------
type Sub = { endpoint: string; p256dh: string; auth: string; fails: number };
async function broadcast(payload: Record<string, string>, only?: string) {
  const v = await vapidKeys();
  let subs: Sub[] = await rest('push_subs?select=endpoint,p256dh,auth,fails');
  if (only) subs = subs.filter((s) => s.endpoint === only);
  const body = enc(JSON.stringify(payload));
  const results = await Promise.all(subs.map(async (s) => {
    try {
      const r = await fetch(s.endpoint, {
        method: 'POST',
        headers: {
          Authorization: await vapidAuth(s.endpoint, v),
          'Content-Encoding': 'aes128gcm', 'Content-Type': 'application/octet-stream', TTL: '86400', Urgency: 'high',
        },
        body: await encryptPayload(s.p256dh, s.auth, body),
      });
      const detail = r.ok ? '' : (await r.text()).slice(0, 200);
      return { s, status: r.status, detail };
    } catch (e) {
      return { s, status: 0, detail: String(e) };
    }
  }));
  for (const { s, status, detail } of results) {
    const q = `push_subs?endpoint=eq.${encodeURIComponent(s.endpoint)}`;
    if (status === 404 || status === 410) await rest(q, { method: 'DELETE' }); // the phone turned alerts off
    else if (status >= 200 && status < 300) await rest(q, { method: 'PATCH', body: { last_ok_at: new Date().toISOString(), fails: 0 } });
    else { console.error('push failed', status, detail); await rest(q, { method: 'PATCH', body: { fails: (s.fails || 0) + 1 } }); }
  }
  return { ok: true, sent: results.filter((x) => x.status >= 200 && x.status < 300).length, of: results.length };
}

async function onBooking(id: string) {
  if (!/^[0-9a-f-]{36}$/i.test(id)) return { ok: false, error: 'id' };
  const since = new Date(Date.now() - 30 * 60e3).toISOString();
  // marks the booking as announced in the same step, so a repeated call sends nothing
  const rows = await rest(
    `appointments?id=eq.${id}&source=eq.online&notified_at=is.null&created_at=gt.${since}&select=id,name,service_name,starts_at,status`,
    { method: 'PATCH', body: { notified_at: new Date().toISOString() }, prefer: 'return=representation' },
  );
  if (!rows.length) return { ok: true, skipped: 'not-new' };
  if (!prefs(await settings()).booking) return { ok: true, skipped: 'off' };
  const a = rows[0], pending = a.status === 'pending';
  return broadcast({
    title: pending ? 'בקשה לתור חדש 💅' : 'נקבע תור חדש 💅',
    body: `${a.name} · ${a.service_name}\n${whenText(Date.parse(a.starts_at))}${pending ? ' · מחכה לאישור שלך' : ''}`,
    tag: 'appt-' + a.id,
    url: ADMIN + '#appt=' + a.id,
  });
}

async function onHourly() {
  const pref = prefs(await settings());
  if (pref.eveningHour < 0) return { ok: true, skipped: 'off' };
  const now = il(Date.now());
  if (now.h !== pref.eveningHour) return { ok: true, skipped: 'hour' };
  if (!(await kvAdd('evening:' + now.key, true))) return { ok: true, skipped: 'sent' };
  await rest(`server_kv?k=gte.evening:&k=lt.evening:${addDays(now.key, -7)}`, { method: 'DELETE' });
  const tk = addDays(now.key, 1);
  const from = new Date(zoned(tk, 0)).toISOString(), to = new Date(zoned(addDays(tk, 1), 0)).toISOString();
  const list = await rest(`appointments?select=name,starts_at,status&status=in.(confirmed,pending)&starts_at=gte.${from}&starts_at=lt.${to}&order=starts_at`);
  if (!list.length) return { ok: true, skipped: 'empty' };
  // deno-lint-ignore no-explicit-any
  const lines = list.map((a: any) => `${hm(Date.parse(a.starts_at))} ${firstName(a.name)}${a.status === 'pending' ? ' (מחכה לאישור)' : ''}`);
  return broadcast({
    title: `מחר ${list.length === 1 ? 'תור אחד' : list.length + ' תורים'} 💅`,
    body: lines.join(' · ') + '\nלחיצה כאן לשליחת תזכורות בוואטסאפ',
    tag: 'evening',
    url: ADMIN + '#remind',
  });
}

async function onTest(endpoint: string) {
  if (!endpoint) return { ok: false, error: 'endpoint' };
  const rows = await rest(`push_subs?select=endpoint&endpoint=eq.${encodeURIComponent(endpoint)}`);
  if (!rows.length) return { ok: false, error: 'unknown' };
  const last = Number(await kvGet('test_last')) || 0;
  if (Date.now() - last < 20000) return { ok: false, error: 'wait' };
  await kvPut('test_last', Date.now());
  return broadcast({ title: 'ההתראות פועלות ✓', body: 'כך תופיע כאן כל בקשה לתור חדש מהאתר.', tag: 'test', url: ADMIN }, endpoint);
}

// deno-lint-ignore no-explicit-any
export async function handle(input: any) {
  switch (input && input.op) {
    case 'key': return { ok: true, publicKey: (await vapidKeys()).pub };
    case 'booking': return await onBooking(String(input.id || ''));
    case 'hourly': return await onHourly();
    case 'test': return await onTest(String(input.endpoint || ''));
    default: return { ok: false, error: 'op' };
  }
}

// deno-lint-ignore no-explicit-any
const D = (globalThis as any).Deno;
if (D && typeof D.serve === 'function') {
  D.serve(async (req: Request) => {
    if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
    let input = {};
    try { input = await req.json(); } catch (_) { /* no body */ }
    try {
      return Response.json(await handle(input), { headers: CORS });
    } catch (e) {
      console.error(e);
      return Response.json({ ok: false, error: 'server' }, { status: 500, headers: CORS });
    }
  });
}
