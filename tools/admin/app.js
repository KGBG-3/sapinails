
/* =====================================================================
   Below: the new parts of the admin screen.
   Backend (Supabase), login, appointments, opening hours and settings.
   ===================================================================== */
const CFG = window.SAPI || {};
const sb = window.supabase.createClient(CFG.url, CFG.key, {
  auth: { persistSession: true, autoRefreshToken: true, storageKey: 'sapinails-admin' },
});
S.view = 'agenda';
S.full = {};

/* ---------- time, always in Israel ---------- */
const ZONE = CFG.zone || 'Asia/Jerusalem';
const T = (() => {
  const pad = n => String(n).padStart(2, '0');
  const fmt = new Intl.DateTimeFormat('en-CA', { timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const parts = ms => { const o = {}; for (const p of fmt.formatToParts(new Date(ms))) o[p.type] = p.value; return { y: +o.year, m: +o.month, d: +o.day, h: (+o.hour) % 24, mi: +o.minute }; };
  const offsetAt = ms => { const p = parts(ms); return Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi) - Math.floor(ms / 60000) * 60000; };
  const zoned = (key, min) => { const [y, m, d] = key.split('-').map(Number); const g = Date.UTC(y, m - 1, d, 0, min); let t = g - offsetAt(g); t = g - offsetAt(t); return t; };
  const key = ms => { const p = parts(ms); return `${p.y}-${pad(p.m)}-${pad(p.d)}`; };
  const add = (k, n) => { const [y, m, d] = k.split('-').map(Number); const dt = new Date(Date.UTC(y, m - 1, d + n)); return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`; };
  const wd = k => { const [y, m, d] = k.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)).getUTCDay(); };
  const min = t => { const m = /^(\d{1,2}):(\d{2})$/.exec(t || ''); return m ? +m[1] * 60 + +m[2] : null; };
  const mod = ms => { const p = parts(ms); return p.h * 60 + p.mi; };
  const hm = ms => { const p = parts(ms); return `${pad(p.h)}:${pad(p.mi)}`; };
  const hhmm = m => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const long = ms => new Intl.DateTimeFormat('he-IL', { timeZone: ZONE, weekday: 'long', day: 'numeric', month: 'long' }).format(new Date(ms));
  const short = ms => new Intl.DateTimeFormat('he-IL', { timeZone: ZONE, day: 'numeric', month: 'numeric' }).format(new Date(ms));
  const keyLong = k => long(zoned(k, 720));
  const month = k => new Intl.DateTimeFormat('he-IL', { timeZone: 'UTC', month: 'long', year: 'numeric' }).format(new Date(k + 'T12:00:00Z'));
  return { parts, zoned, key, add, wd, min, mod, hm, hhmm, long, short, keyLong, month, today: () => key(Date.now()) };
})();
const WD_SHORT = ['א׳', 'ב׳', 'ג׳', 'ד׳', 'ה׳', 'ו׳', 'ש׳'];
const WD_LONG = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'];
function fmtDur(m) {
  m = Math.round(m || 0);
  if (m < 60) return `${m} דק׳`;
  const h = Math.floor(m / 60), r = m % 60;
  const hs = h === 1 ? 'שעה' : h === 2 ? 'שעתיים' : `${h} שעות`;
  return r === 0 ? hs : r === 30 ? `${hs} וחצי` : `${hs} ו־${r} דק׳`;
}
const fmtPrice = p => (p == null || p === '' ? '' : `${Number(p).toLocaleString('he-IL')}₪`);
const iso = ms => new Date(ms).toISOString();
function relAgo(ms) {
  const d = Date.now() - ms;
  if (d < 90e3) return 'עכשיו';
  if (d < 3600e3) return `לפני ${Math.round(d / 60e3)} דק׳`;
  if (d < 2 * 3600e3) return 'לפני שעה';
  if (d < 24 * 3600e3) return `לפני ${Math.round(d / 3600e3)} שעות`;
  return rel(ms);
}

/* ---------- dates under the nails ---------- */
function punchDates(c, N) {
  const dates = [];
  for (const e of c.log || []) {
    const p = Math.min(num(e.p), N);
    if (e.a === 'punch') { if (p >= 1) dates[p - 1] = e.t; dates.length = Math.min(dates.length, p); }
    else if (e.a === 'redeem' || e.a === 'join') { dates.length = 0; }
    else if (e.a === 'adjust') { dates.length = Math.min(dates.length, p); }
  }
  return dates;
}
const nailDate = ms => (ms ? T.short(ms) : '');

/* ---------- database adapter for the card screen ---------- */
function dbErr(error) {
  const e = new Error((error && error.message) || 'db error');
  const code = error && error.code, status = error && error.status;
  e.code = code === '42501' || status === 401 || status === 403 ? 'not_granted'
    : code === '23P01' ? 'overlap'
    : /fetch|network|Failed|timeout/i.test((error && error.message) || '') ? 'unavailable' : 'failed';
  e.raw = error;
  return e;
}
const newId = () => { const a = 'abcdefghijklmnopqrstuvwxyz0123456789', r = crypto.getRandomValues(new Uint8Array(20)); let s = ''; for (const x of r) s += a[x % 36]; return s; };
const listeners = { clients: new Set(), settings: new Set() };
const notify = kind => listeners[kind].forEach(fn => fn());
async function fetchClients() {
  const { data, error } = await sb.from('clients').select('id,data');
  if (error) throw dbErr(error);
  return data;
}
async function fetchSettings() {
  const { data, error } = await sb.from('settings').select('data').eq('id', 'main').maybeSingle();
  if (error) throw dbErr(error);
  return data ? data.data : null;
}
async function mergeSettings(patch) {
  const { data, error } = await sb.rpc('merge_settings', { p_patch: patch });
  if (error) throw dbErr(error);
  if (data == null) throw Object.assign(new Error('not granted'), { code: 'not_granted' });
  S.full = data;
  notify('settings');
  return data;
}
function docRef(path) {
  const [col, id] = path.split('/');
  return {
    id,
    async set(body) {
      if (col === 'clients') {
        const { error } = await sb.from('clients').upsert({ id, data: body });
        if (error) throw dbErr(error);
        notify('clients');
      } else if (path === 'meta/settings') {
        await mergeSettings(body);
      } else throw new Error('unsupported ' + path);
    },
    async delete() {
      const { error } = await sb.from('clients').delete().eq('id', id);
      if (error) throw dbErr(error);
      notify('clients');
    },
    onSnapshot(cb, onErr) {
      const fn = () => fetchSettings().then(d => cb({ exists: !!d, data: () => d })).catch(e => onErr && onErr(e));
      listeners.settings.add(fn); fn();
      return () => listeners.settings.delete(fn);
    },
  };
}
const DB = {
  doc: docRef,
  collection: () => ({
    doc: () => docRef('clients/' + newId()),
    onSnapshot(cb, onErr) {
      const fn = () => fetchClients().then(rows => cb({ docs: rows.map(r => ({ id: r.id, exists: true, data: () => r.data })), size: rows.length, empty: !rows.length })).catch(e => onErr && onErr(e));
      listeners.clients.add(fn); fn();
      return () => listeners.clients.delete(fn);
    },
  }),
};

/* ---------- appointments state ---------- */
const A = { list: [], blocks: [], services: [], loaded: false, error: false, day: null, seenPending: null, hoursDraft: null, hoursDirty: false };
const ST_LABEL = { pending: 'ממתין לאישור', confirmed: 'מאושר', done: 'בוצע', noshow: 'לא הגיעה', cancelled: 'בוטל' };
const apptById = id => A.list.find(a => a.id === id) || null;
const svcById = id => A.services.find(s => s.id === id) || null;
const normP = p => { let d = String(p || '').replace(/\D/g, ''); if (d.startsWith('00')) d = d.slice(2); if (d.startsWith('972')) d = '0' + d.slice(3); if (/^5\d{8}$/.test(d)) d = '0' + d; return d; };
function clientForAppt(a) {
  if (!a) return null;
  if (a.client_id && S.clients.has(a.client_id)) return S.clients.get(a.client_id);
  const p = normP(a.phone);
  if (!p) return null;
  return [...S.clients.values()].find(c => normP(c.phone) === p) || null;
}
function nextApptFor(c) {
  const p = normP(c.phone), now = Date.now();
  return A.list.filter(a => (a.status === 'pending' || a.status === 'confirmed') && a.e > now && (a.client_id === c.id || (p && normP(a.phone) === p))).sort((x, y) => x.s - y.s)[0] || null;
}
function siteBase() {
  let base = String((S.settings && S.settings.siteUrl) || '').replace(/[#?].*$/, '').replace(/\/+$/, '');
  if (!base || /claude\.ai\//i.test(base)) return '';
  if (!/^https?:\/\//i.test(base)) base = 'https://' + base;
  return base;
}
const bookLink = () => (siteBase() ? siteBase() + '/book/' : '');

async function refreshBooking() {
  const today = T.today();
  const from = iso(T.zoned(T.add(today, -60), 0)), to = iso(T.zoned(T.add(today, 200), 0));
  const [a, b, s] = await Promise.all([
    sb.from('appointments').select('*').gte('starts_at', from).lt('starts_at', to).order('starts_at'),
    sb.from('blocks').select('*').gte('ends_at', from).order('starts_at'),
    sb.from('services').select('*').order('sort').order('name'),
  ]);
  const err = a.error || b.error || s.error;
  if (err) { A.error = true; render(); throw dbErr(err); }
  A.list = a.data.map(r => ({ ...r, s: Date.parse(r.starts_at), e: Date.parse(r.ends_at) }));
  A.blocks = b.data.map(r => ({ ...r, s: Date.parse(r.starts_at), e: Date.parse(r.ends_at) }));
  A.services = s.data;
  A.loaded = true; A.error = false;
  const pend = A.list.filter(x => x.status === 'pending');
  if (A.seenPending) {
    const fresh = pend.filter(x => !A.seenPending.has(x.id));
    if (fresh.length === 1) toast(`בקשה חדשה מ${firstName(fresh[0].name)}`, [{ label: 'פתיחה', fn: () => openSheet({ type: 'appt', id: fresh[0].id }) }]);
    else if (fresh.length > 1) toast(`${fresh.length} בקשות חדשות לתורים`);
  }
  A.seenPending = new Set(pend.map(x => x.id));
  render();
}
let refreshTimer = null;
const refreshSoon = () => { clearTimeout(refreshTimer); refreshTimer = setTimeout(() => refreshBooking().catch(() => {}), 250); };

/* ---------- availability (same rules as the booking page) ---------- */
function dayWindows(key) {
  const hours = (S.full && S.full.hours) || {};
  return (hours[String(T.wd(key))] || []).map(w => [T.min(w.from), T.min(w.to)]).filter(([a, b]) => a != null && b != null && b > a);
}
function busyFor(ignoreId) {
  return [
    ...A.list.filter(a => (a.status === 'pending' || a.status === 'confirmed') && a.id !== ignoreId).map(a => [a.s, a.e]),
    ...A.blocks.map(b => [b.s, b.e]),
  ];
}
function freeStarts(key, minutes, ignoreId) {
  const st = S.full || {};
  const step = Math.max(5, +st.slotMinutes || 30), buf = (+st.bufferMinutes || 0) * 60000;
  const busy = busyFor(ignoreId), now = Date.now(), out = [];
  for (const [ws, we] of dayWindows(key)) {
    for (let t = ws; t + minutes <= we; t += step) {
      const s = T.zoned(key, t), e = s + minutes * 60000;
      if (s < now) continue;
      if (busy.every(([bs, be]) => e + buf <= bs || s >= be + buf)) out.push(s);
    }
  }
  return out;
}

/* ---------- views ---------- */
const TAB_ICONS = {
  agenda: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>',
  cards: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5.5" width="18" height="13" rx="3"/><path d="M7.5 15.5c0-2.4 1-4.6 2-5.5 1 .9 2 3.1 2 5.5M13.5 15.5c0-2.4 1-4.6 2-5.5 1 .9 2 3.1 2 5.5"/></svg>',
  hours: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
  more: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></svg>',
};
function render() {
  const authed = !!S.authed;
  $('#vLogin').hidden = authed;
  $('#tabbar').hidden = !authed;
  ['agenda', 'cards', 'hours', 'more'].forEach(v => { $('#v' + v[0].toUpperCase() + v.slice(1)).hidden = !authed || S.view !== v; });
  if (authed) {
    if (S.view === 'cards') renderCards();
    else if (S.view === 'agenda') renderAgenda();
    else if (S.view === 'hours') renderHours();
    else if (S.view === 'more') renderMore();
    document.querySelectorAll('.tab').forEach(t => t.setAttribute('aria-current', t.dataset.v === S.view ? 'page' : 'false'));
    const pend = A.list.filter(a => a.status === 'pending' && a.e > Date.now()).length;
    const badge = $('#pendBadge');
    badge.hidden = !pend; badge.textContent = pend;
  }
  updateSheets();
  const fab = $('#addBtn');
  const sheetOpen = S.stack.length > 0;
  let fabAct = null;
  if (authed && !sheetOpen && S.canWrite) {
    if (S.view === 'cards' && S.status === 'ready' && S.clients.size > 0) fabAct = ['add', 'לקוחה חדשה'];
    else if (S.view === 'agenda' && A.loaded) fabAct = ['appt-new', 'תור חדש'];
  }
  fab.hidden = !fabAct;
  if (fabAct && fab.dataset.act !== fabAct[0]) { fab.dataset.act = fabAct[0]; fab.innerHTML = `${IC.plus}<span>${fabAct[1]}</span>`; }
  root.classList.toggle('locked', sheetOpen);
}
function setView(v) {
  S.view = v;
  try { localStorage.setItem('sapinails.view', v); } catch (_) {}
  render();
  window.scrollTo(0, 0);
}
function paint(el, html) { if (el._last !== html) { el.innerHTML = html; el._last = html; } }

/* ---------- agenda ---------- */
function renderAgenda() {
  const v = $('#vAgenda');
  if (A.error && !A.loaded) { paint(v, `<div class="err-box">היומן לא נטען. בדיקת החיבור לאינטרנט ואז <button type="button" class="text-btn" data-act="reload">ניסיון נוסף</button></div>`); return; }
  if (!A.loaded) { paint(v, '<div class="skel-list" aria-hidden="true"><div class="skel"></div><div class="skel"></div><div class="skel"></div></div>'); return; }
  const today = T.today(), now = Date.now();
  if (!A.day) A.day = today;
  const key = A.day;
  const pend = A.list.filter(a => a.status === 'pending' && a.e > now).sort((x, y) => x.s - y.s);
  const toClose = A.list.filter(a => a.status === 'confirmed' && a.e <= now && a.e > now - 21 * DAY).sort((x, y) => x.s - y.s);
  const dayItems = A.list.filter(a => T.key(a.s) === key && a.status !== 'cancelled').sort((x, y) => x.s - y.s);
  const active = dayItems.filter(a => a.status !== 'noshow');
  const mins = active.reduce((t, a) => t + (a.minutes || 0), 0), money = active.reduce((t, a) => t + (Number(a.price) || 0), 0);
  const wins = dayWindows(key);
  const dayStart = T.zoned(key, 0), dayEnd = T.zoned(T.add(key, 1), 0);
  const blocks = A.blocks.filter(b => b.s < dayEnd && b.e > dayStart);
  const allDay = blocks.find(b => b.s <= dayStart && b.e >= dayEnd);
  let meta = active.length ? `${plural(active.length, 'תור אחד', 'תורים')} · ${fmtDur(mins)}${money ? ' · ' + fmtPrice(money) : ''}` : allDay ? 'יום חסום' : wins.length ? 'אין תורים' : 'יום סגור';
  if (key === today) {
    const nx = active.find(a => a.s >= now);
    if (nx) meta += ` · הבא ב־${T.hm(nx.s)} ${firstName(nx.name)}`;
  }

  const hr = T.parts(now).h;
  const hello = hr < 5 ? 'לילה טוב' : hr < 12 ? 'בוקר טוב' : hr < 17 ? 'צהריים טובים' : hr < 21 ? 'ערב טוב' : 'לילה טוב';
  const todays = A.list.filter(a => T.key(a.s) === today && (a.status === 'confirmed' || a.status === 'done'));
  const nextToday = todays.filter(a => a.s >= now && a.status === 'confirmed').sort((x, y) => x.s - y.s)[0];
  const headSub = todays.length ? `${plural(todays.length, 'תור אחד', 'תורים')} היום${nextToday ? ` · הבא ב־${T.hm(nextToday.s)} ${firstName(nextToday.name)}` : ''}` : 'אין תורים היום';
  let html = `<header class="top"><div class="brand"><div class="eyebrow">יומן התורים</div><h1 class="studio">${esc(hello)}${(S.full && S.full.ownerName) ? ', ' + esc(S.full.ownerName) : ''}</h1><div class="sub">${esc(headSub)}</div></div></header>`;
  if (pend.length) {
    html += `<div class="section-title"><h2>ממתינות לאישור</h2><span class="hint">${pend.length}</span></div><div class="pending">${pend.map(a => `
      <div class="req">
        <button type="button" class="req-top" data-act="appt-open" data-id="${esc(a.id)}">
          <span class="who">${esc(a.name)}${a.is_new ? '<span class="tag-new">לקוחה חדשה</span>' : ''}</span>
          <span class="what">${esc(a.service_name)} · ${esc(T.long(a.s))} · ${T.hm(a.s)}</span>
          <span class="when">ביקשה ${esc(relAgo(Date.parse(a.created_at)))}${a.addons && a.addons.length ? ' · ' + esc(a.addons.join(', ')) : ''}${a.note ? ' · ' + esc(a.note) : ''}</span>
        </button>
        <div class="req-actions">
          <button type="button" class="btn wa" data-act="appt-wa" data-id="${esc(a.id)}" data-tpl="photo">${IC.chat}<span>וואטסאפ</span></button>
          <button type="button" class="btn primary" data-act="appt-approve" data-id="${esc(a.id)}"${S.canWrite ? '' : ' disabled'}>אישור</button>
          <button type="button" class="btn ghost" data-act="appt-decline" data-id="${esc(a.id)}"${S.canWrite ? '' : ' disabled'}>דחייה</button>
        </div>
      </div>`).join('')}</div>`;
  }
  if (toClose.length) {
    html += `<div class="section-title"><h2>לסגור תורים שעברו</h2><span class="hint">כדי שהניקובים יתעדכנו</span></div><div class="toclose">${toClose.map(a => `
      <div class="req close">
        <button type="button" class="req-top" data-act="appt-open" data-id="${esc(a.id)}">
          <span class="who">${esc(a.name)}</span>
          <span class="what">${esc(a.service_name)} · ${esc(T.long(a.s))} · ${T.hm(a.s)}</span>
        </button>
        <div class="req-actions">
          <button type="button" class="btn primary" data-act="appt-done" data-id="${esc(a.id)}"${S.canWrite ? '' : ' disabled'}>הגיעה ✓</button>
          <button type="button" class="btn ghost" data-act="appt-noshow" data-id="${esc(a.id)}"${S.canWrite ? '' : ' disabled'}>לא הגיעה</button>
        </div>
      </div>`).join('')}</div>`;
  }
  const tmr = T.add(today, 1);
  const rem = A.list.filter(a => a.status === 'confirmed' && T.key(a.s) === tmr).sort((x, y) => x.s - y.s);
  if (rem.length) {
    const left = rem.filter(a => !a.reminded_at).length;
    html += `<div class="section-title" id="remindSec"><h2>תזכורות למחר</h2><span class="hint">${left ? `${left} מתוך ${rem.length} לשליחה` : 'כולן נשלחו ✓'}</span></div>`;
    if (left) html += `<div class="remind">${rem.map(remRow).join('')}</div>`;
  }

  const weekStart = T.add(key, -T.wd(key));
  const days = [0, 1, 2, 3, 4, 5, 6].map(i => T.add(weekStart, i));
  html += `<div class="weeknav">
      <button type="button" class="icon-btn" data-act="week" data-d="-7" aria-label="שבוע קודם"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg></button>
      <span class="lbl">${esc(T.month(key))}</span>
      ${key !== today ? '<button type="button" class="head-btn" data-act="go-today">היום</button>' : ''}
      <button type="button" class="icon-btn" data-act="week" data-d="7" aria-label="שבוע הבא"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg></button>
    </div>
    <div class="week">${days.map(k => {
      const n = A.list.filter(a => T.key(a.s) === k && (a.status === 'pending' || a.status === 'confirmed' || a.status === 'done')).length;
      const cls = ['wd', k === today ? 'today' : '', dayWindows(k).length ? '' : 'closed'].join(' ');
      return `<button type="button" class="${cls}" data-act="day" data-k="${k}" aria-pressed="${k === key}" aria-label="${esc(T.keyLong(k))}${n ? ', ' + n + ' תורים' : ''}"><span class="w">${WD_SHORT[T.wd(k)]}</span><span class="n">${+k.slice(8)}</span><span class="c">${n || ''}</span></button>`;
    }).join('')}</div>
    <div class="dayhead"><div class="dh-text"><h2>${esc(T.keyLong(key))}${key === today ? ' <span class="st confirmed">היום</span>' : ''}</h2><div class="meta">${esc(meta)}</div></div>${key >= today && !allDay && wins.length && S.canWrite ? `<button type="button" class="head-btn" data-act="block-day" data-k="${key}">סגירת שעות</button>` : ''}</div>`;

  const rows = [];
  for (const a of dayItems) {
    const past = a.e <= now && a.status === 'confirmed';
    rows.push({ t: a.s, html: `<button type="button" class="ap ${a.status}${past ? ' past' : ''}" data-act="appt-open" data-id="${esc(a.id)}"><span class="t">${T.hm(a.s)}<small>${T.hm(a.e)}</small></span><span class="mid"><span class="who">${esc(a.name)}</span><br><span class="svc">${esc(a.service_name)} · ${fmtDur(a.minutes)}${a.price != null ? ' · ' + fmtPrice(a.price) : ''}</span></span><span class="st ${a.status}">${ST_LABEL[a.status]}</span></button>` });
  }
  for (const b of blocks) {
    if (b === allDay) continue;
    rows.push({ t: b.s, html: `<div class="blockrow"><span>חסום · <span dir="ltr">${T.hm(Math.max(b.s, dayStart))}–${T.hm(Math.min(b.e, dayEnd))}</span>${b.reason ? ' · ' + esc(b.reason) : ''}</span><button type="button" class="mini-btn" data-act="block-open" data-id="${esc(b.id)}">עריכה</button></div>` });
  }
  if (!allDay) {
    const busy = [...A.list.filter(a => T.key(a.s) === key && (a.status === 'pending' || a.status === 'confirmed')).map(a => [T.mod(a.s), T.mod(a.e) || 1440]), ...blocks.map(b => [b.s <= dayStart ? 0 : T.mod(b.s), b.e >= dayEnd ? 1440 : T.mod(b.e)])].sort((x, y) => x[0] - y[0]);
    const nowMin = key === today ? T.mod(now) : key < today ? 1440 : -1;
    for (const [ws, we] of wins) {
      let cur = Math.max(ws, nowMin);
      for (const [s, e] of busy) {
        if (s >= we) break;
        if (e <= cur) continue;
        if (s > cur && s - cur >= 20) rows.push({ t: T.zoned(key, cur), html: gapRow(key, cur, s) });
        cur = Math.max(cur, e);
      }
      if (we - cur >= 20) rows.push({ t: T.zoned(key, cur), html: gapRow(key, cur, we) });
    }
  }
  rows.sort((x, y) => x.t - y.t);
  let body;
  if (allDay) body = `<div class="blockrow"><span>היום חסום${allDay.reason ? ' · ' + esc(allDay.reason) : ''}</span><button type="button" class="mini-btn" data-act="block-open" data-id="${esc(allDay.id)}">עריכה</button></div>` + rows.map(r => r.html).join('');
  else if (rows.length) body = rows.map(r => r.html).join('');
  else body = wins.length ? '<div class="empty-day"><b>אין תורים</b>אפשר להוסיף תור בכפתור למטה.</div>' : '<div class="empty-day"><b>יום סגור</b>שעות הפעילות נקבעות בלשונית «שעות».</div>';
  html += `<div class="agenda">${body}</div>`;
  paint(v, html);
}
function gapRow(key, s, e) {
  const s5 = Math.ceil(s / 5) * 5;
  return `<div class="gap"><span>פנוי · <span dir="ltr">${T.hhmm(s)}–${T.hhmm(e)}</span> · ${fmtDur(e - s)}</span><span class="gap-acts"><button type="button" class="mini-btn ghost" data-act="block-gap" data-k="${key}" data-s="${s5}" data-e="${e}" aria-label="סגירת השעות ${T.hhmm(s5)}–${T.hhmm(e)}">סגירה</button><button type="button" class="mini-btn" data-act="appt-new" data-k="${key}" data-m="${s5}">+ תור</button></span></div>`;
}
function remRow(a) {
  const sent = !!a.reminded_at;
  return `<div class="rem${sent ? ' sent' : ''}">
    <button type="button" class="req-top" data-act="appt-open" data-id="${esc(a.id)}"><span class="who">${T.hm(a.s)} · ${esc(a.name)}</span><span class="what">${esc(a.service_name)}${sent ? ' · נשלחה ✓' : ''}</span></button>
    ${a.phone ? `<button type="button" class="btn ${sent ? 'ghost' : 'wa'} rem-btn" data-act="appt-wa" data-id="${esc(a.id)}" data-tpl="reminder">${sent ? 'שוב' : `${IC.chat}<span>תזכורת</span>`}</button>` : '<span class="muted small">אין טלפון</span>'}
  </div>`;
}
async function markReminded(id) {
  const a = apptById(id);
  if (!a || a.reminded_at || !S.canWrite) return;
  a.reminded_at = new Date().toISOString();
  render();
  const { error } = await sb.from('appointments').update({ reminded_at: a.reminded_at }).eq('id', id);
  if (error) { a.reminded_at = null; render(); }
}

/* ---------- appointment sheet ---------- */
function apptSheetHTML(spec) {
  const a = apptById(spec.id);
  if (!a) return sheetHead(spec, 'התור לא נמצא') + '<div class="sheet-body"><p class="help">ייתכן שהתור נמחק ממכשיר אחר.</p></div>';
  const c = clientForAppt(a), N = S.settings.cardSize, dis = S.canWrite ? '' : ' disabled';
  const svc = svcById(a.service_id), counts = svc ? svc.counts !== false : true;
  const id = esc(a.id), now = Date.now();
  const phoneRow = a.phone
    ? `<span class="phone" dir="ltr">${esc(fmtPhone(a.phone))}</span><button type="button" class="mini-btn" data-act="copy-text" data-v="${esc(fmtPhone(a.phone))}">${IC.copy}<span>העתקה</span></button>`
    : '<span class="muted">לא הוזן</span>';
  let actions = '';
  if (a.status === 'pending') {
    actions = `<button type="button" class="btn primary big" data-act="appt-approve" data-id="${id}"${dis}>אישור התור</button>
      <div class="actions-row"><button type="button" class="btn wa" data-act="appt-wa" data-id="${id}" data-tpl="photo">${IC.chat}<span>וואטסאפ</span></button><button type="button" class="btn ghost" data-act="appt-decline" data-id="${id}"${dis}>דחייה</button></div>
      <div class="text-row"><button type="button" class="text-btn" data-act="appt-edit" data-id="${id}"${dis}>${IC.edit}<span>שינוי שעה או פרטים</span></button></div>`;
  } else if (a.status === 'confirmed') {
    const full = c && c.punches >= N;
    const doneLabel = !counts ? 'הטיפול בוצע' : full ? 'הטיפול בוצע · מימוש המתנה 🎁' : c ? 'הטיפול בוצע · ניקוב' : 'הטיפול בוצע · פתיחת כרטיסייה';
    actions = `<button type="button" class="btn ${full && counts ? 'chrome' : 'primary'} big" data-act="appt-done" data-id="${id}"${dis}>${doneLabel}</button>
      <div class="actions-row"><button type="button" class="btn wa" data-act="appt-wa" data-id="${id}" data-tpl="${a.s - now < 2 * DAY && a.s > now ? 'reminder' : 'confirm'}">${IC.chat}<span>וואטסאפ</span></button><button type="button" class="btn ghost" data-act="appt-edit" data-id="${id}"${dis}>${IC.edit}<span>עריכה</span></button></div>
      <div class="text-row"><button type="button" class="text-btn" data-act="appt-noshow" data-id="${id}"${dis}>לא הגיעה</button><button type="button" class="text-btn danger-txt" data-act="appt-cancel" data-id="${id}"${dis}>ביטול התור</button></div>`;
  } else if (a.status === 'done') {
    actions = `<p class="help">${a.punched ? 'הטיפול סומן כבוצע ונוסף ניקוב בכרטיסייה.' : 'הטיפול סומן כבוצע.'}</p>
      <div class="actions-row">${c ? `<button type="button" class="btn wa" data-act="wa" data-id="${esc(c.id)}">${IC.chat}<span>עדכון כרטיסייה</span></button>` : ''}<button type="button" class="btn ghost" data-act="appt-reopen" data-id="${id}"${dis}>החזרה לתור פעיל</button></div>`;
  } else {
    actions = `<div class="actions-row"><button type="button" class="btn ghost" data-act="appt-reopen" data-id="${id}"${dis}>החזרה לתור פעיל</button><button type="button" class="btn wa" data-act="appt-wa" data-id="${id}" data-tpl="${a.status === 'cancelled' ? 'cancel' : 'confirm'}">${IC.chat}<span>וואטסאפ</span></button></div>
      ${spec.confirmDelete
        ? `<div class="confirm confirm-inline" role="alert"><p>למחוק את התור לגמרי?</p><div class="actions-row"><button type="button" class="btn danger" data-act="appt-delete-yes" data-id="${id}">מחיקה</button><button type="button" class="btn ghost" data-act="appt-delete-no">ביטול</button></div></div>`
        : `<div class="text-row"><button type="button" class="text-btn danger-txt" data-act="appt-delete-ask"${dis}>${IC.trash}<span>מחיקת התור</span></button></div>`}`;
  }
  const card = c
    ? `<div class="mini-card"><div><div>${nailRow(c.punches, N, 'mid')}</div><div class="lbl">${c.punches >= N ? 'הכרטיסייה מלאה, הטיפול הזה מתנה' : `${Math.min(c.punches, N)} מתוך ${N} ניקובים`}</div></div><button type="button" class="mini-btn" data-act="open" data-id="${esc(c.id)}">לכרטיסייה</button></div>`
    : a.status === 'pending' ? '<p class="help" style="margin-top:12px">עדיין אין לה כרטיסיית מועדון. כשהתור יאושר היא תצורף לכרטיסיות.</p>'
    : a.status === 'confirmed' && counts ? '<p class="help" style="margin-top:12px">עדיין אין לה כרטיסיית מועדון. כשהטיפול יסומן כבוצע תיפתח לה כרטיסייה עם ניקוב ראשון.</p>' : '';
  return sheetHead(spec, esc(a.name)) + `<div class="sheet-body">
    <div class="appt-tags"><span class="st ${a.status}">${ST_LABEL[a.status]}</span>${a.is_new ? '<span class="tag-new">לקוחה חדשה</span>' : ''}${a.source === 'online' ? '<span class="tag-new">נקבע באתר</span>' : ''}</div>
    <dl class="info">
      <div class="info-row"><dt>מתי</dt><dd>${esc(T.long(a.s))} · <span dir="ltr">${T.hm(a.s)}–${T.hm(a.e)}</span></dd></div>
      <div class="info-row"><dt>טיפול</dt><dd>${esc(a.service_name || '—')} · ${fmtDur(a.minutes)}</dd></div>
      ${a.price != null ? `<div class="info-row"><dt>מחיר</dt><dd>${fmtPrice(a.price)}</dd></div>` : ''}
      <div class="info-row"><dt>טלפון</dt><dd>${phoneRow}</dd></div>
      ${a.addons && a.addons.length ? `<div class="info-row"><dt>תוספות</dt><dd>${esc(a.addons.join(', '))}</dd></div>` : ''}
      ${a.note ? `<div class="info-row notes"><dt>הערה</dt><dd>${esc(a.note)}</dd></div>` : ''}
      <div class="info-row"><dt>נקבע</dt><dd>${a.source === 'online' ? 'באתר' : 'ידנית'} · ${esc(relAgo(Date.parse(a.created_at)))}</dd></div>
      ${a.reminded_at ? `<div class="info-row"><dt>תזכורת</dt><dd>נשלחה ${esc(relAgo(Date.parse(a.reminded_at)))}</dd></div>` : ''}
    </dl>
    ${(a.status === 'pending' || a.status === 'confirmed') && a.e > now - 3600e3 ? `<div class="extend"><span class="legend">צריך יותר זמן?</span><div class="chips">${[[15, 'עוד רבע שעה'], [30, 'עוד חצי שעה'], [60, 'עוד שעה']].map(([d, l]) => `<button type="button" class="chip" data-act="appt-extend" data-id="${id}" data-d="${d}"${dis}>${l}</button>`).join('')}</div></div>` : ''}
    ${card}
    <div class="actions">${actions}</div>
  </div>`;
}

/* ---------- appointment form ---------- */
function apptFormHTML(spec) {
  const a = spec.id ? apptById(spec.id) : null;
  const svcs = A.services.filter(s => s.active || (a && s.id === a.service_id));
  const svc0 = a ? svcById(a.service_id) : svcs[0];
  let key = a ? T.key(a.s) : (spec.k || A.day || T.today());
  if (!a && !spec.k && svc0) {
    for (let i = 0, k = key; i < 45; i++, k = T.add(k, 1)) { if (freeStarts(k, svc0.minutes).length) { key = k; break; } }
  }
  const m = a ? T.mod(a.s) : (spec.m != null ? +spec.m : null);
  const minutes = a ? a.minutes : (svc0 ? svc0.minutes : 60);
  const price = a ? a.price : (svc0 ? svc0.price : '');
  const names = [...S.clients.values()].map(c => `<option value="${esc(c.name)}"></option>`).join('');
  return sheetHead(spec, a ? 'עריכת תור' : 'תור חדש') + `<div class="sheet-body">
    <form class="form" id="apptForm" novalidate>
      <div class="field">
        <label for="a-name">שם הלקוחה</label>
        <input class="input" id="a-name" list="a-names" autocomplete="off" maxlength="60" value="${esc(a ? a.name : (spec.name || ''))}">
        <datalist id="a-names">${names}</datalist>
        <div class="err" id="a-name-err" hidden>צריך שם כדי לשמור.</div>
      </div>
      <div class="field">
        <label for="a-phone">טלפון <span class="opt">(לוואטסאפ ולכרטיסייה)</span></label>
        <input class="input ltr" id="a-phone" type="tel" inputmode="tel" autocomplete="off" dir="ltr" maxlength="20" placeholder="050-000-0000" value="${esc(a ? a.phone : (spec.phone || ''))}">
      </div>
      <div class="field">
        <label for="a-svc">טיפול</label>
        <select class="input" id="a-svc">${svcs.map(s => `<option value="${esc(s.id)}"${svc0 && s.id === svc0.id ? ' selected' : ''}>${esc(s.name)}</option>`).join('')}<option value=""${!svc0 ? ' selected' : ''}>אחר</option></select>
      </div>
      <div class="row2">
        <div class="field"><label for="a-date">תאריך</label><input class="input" id="a-date" type="date" value="${key}"></div>
        <div class="field"><label for="a-time">שעה</label><input class="input" id="a-time" type="time" step="300" value="${m != null ? T.hhmm(m) : ''}"></div>
      </div>
      <div class="field"><span class="legend">שעות פנויות ביום הזה</span><div class="chips wrap" id="a-free"></div></div>
      <div class="row2">
        <div class="field"><label for="a-min">משך בדקות</label><input class="input" id="a-min" type="number" inputmode="numeric" min="5" max="480" step="5" value="${minutes}"></div>
        <div class="field"><label for="a-price">מחיר</label><input class="input" id="a-price" type="number" inputmode="numeric" min="0" step="1" value="${price == null ? '' : esc(price)}"></div>
      </div>
      <div class="field"><label for="a-note">הערה <span class="opt">(לא חובה)</span></label><textarea class="input" id="a-note" rows="2" maxlength="300">${esc(a ? a.note : '')}</textarea></div>
      <div class="err-box" id="a-err" hidden></div>
      <button type="submit" class="btn primary big" id="a-save">${a ? 'שמירת שינויים' : 'שמירת התור'}</button>
    </form>
  </div>`;
}
function updateFreeChips(spec) {
  const r = spec.inner, box = $('#a-free', r);
  if (!box) return;
  const key = $('#a-date', r).value, minutes = clamp(parseInt($('#a-min', r).value, 10) || 0, 5, 480);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(key)) { box.innerHTML = ''; return; }
  const starts = freeStarts(key, minutes, spec.id);
  const cur = $('#a-time', r).value;
  box.innerHTML = starts.length
    ? starts.map(s => `<button type="button" class="chip" role="radio" aria-checked="${T.hm(s) === cur}" data-act="pick-time" data-v="${T.hm(s)}">${T.hm(s)}</button>`).join('')
    : `<span class="help">${dayWindows(key).length ? 'אין זמן פנוי באורך הזה. אפשר לבחור שעה ידנית.' : 'היום הזה סגור. אפשר לבחור שעה ידנית.'}</span>`;
}
async function submitAppt(spec) {
  if (!guardWrite()) return;
  const r = spec.inner;
  const name = $('#a-name', r).value.trim().replace(/\s+/g, ' ');
  const phone = $('#a-phone', r).value.trim();
  const key = $('#a-date', r).value, time = T.min($('#a-time', r).value);
  const minutes = clamp(parseInt($('#a-min', r).value, 10) || 0, 5, 480);
  const priceRaw = $('#a-price', r).value.trim();
  const svc = svcById($('#a-svc', r).value);
  const err = $('#a-err', r);
  $('#a-name-err', r).hidden = name.length >= 2;
  if (name.length < 2) { $('#a-name', r).focus(); return; }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(key) || time == null) { err.textContent = 'צריך תאריך ושעה.'; err.hidden = false; return; }
  const start = T.zoned(key, time), end = start + minutes * 60000;
  const p = normP(phone);
  const match = p ? [...S.clients.values()].find(c => normP(c.phone) === p) : [...S.clients.values()].find(c => c.name === name);
  const row = {
    starts_at: iso(start), ends_at: iso(end), minutes,
    service_id: svc ? svc.id : null, service_name: svc ? svc.name : 'טיפול',
    price: priceRaw === '' ? null : Number(priceRaw),
    name, phone: phone || (match ? match.phone : ''), note: $('#a-note', r).value.trim(),
  };
  if (match) row.client_id = match.id;
  const btn = $('#a-save', r);
  btn.disabled = true; err.hidden = true;
  let res;
  if (spec.id) res = await sb.from('appointments').update(row).eq('id', spec.id).select().single();
  else res = await sb.from('appointments').insert({ ...row, status: 'confirmed', source: 'admin', is_new: false }).select().single();
  if (res.error) {
    const e = dbErr(res.error);
    err.textContent = e.code === 'overlap' ? 'יש כבר תור שחופף לשעה הזו. בחרי שעה אחרת או קצרי את המשך.' : e.code === 'not_granted' ? 'אין הרשאה לשמור. צריך להתחבר מחדש.' : 'השמירה לא הצליחה. בדיקת החיבור לאינטרנט ואז ניסיון נוסף.';
    err.hidden = false; btn.disabled = false;
    return;
  }
  const saved = res.data;
  const newCard = !!(saved.client_id && !S.clients.has(saved.client_id) && await loadClient(saved.client_id));
  closeTop();
  A.day = T.key(start);
  await refreshBooking().catch(() => {});
  const msg = spec.id ? 'התור עודכן' : newCard ? `התור נשמר ו${firstName(name)} נוספה לכרטיסיות` : 'התור נשמר';
  toast(msg, saved.phone ? [{ label: 'וואטסאפ', fn: () => openApptWa(saved.id, 'confirm') }] : []);
}

/* ---------- appointment actions ---------- */
// The database opens a club card by itself when a booking is confirmed (see supabase/schema.sql).
// This brings that card into the screen right away, without waiting for the live update.
async function loadClient(id) {
  if (!id) return null;
  if (S.clients.has(id)) return S.clients.get(id);
  const { data, error } = await sb.from('clients').select('id,data').eq('id', id).maybeSingle();
  if (error || !data) return null;
  const c = normClient(data.id, data.data);
  S.clients.set(c.id, c);
  return c;
}
async function setApptStatus(id, patch) {
  const { data, error } = await sb.from('appointments').update(patch).eq('id', id).select().single();
  if (error) throw dbErr(error);
  const i = A.list.findIndex(a => a.id === id);
  const row = { ...data, s: Date.parse(data.starts_at), e: Date.parse(data.ends_at) };
  row.newCard = !!(row.client_id && !S.clients.has(row.client_id) && await loadClient(row.client_id));
  if (i >= 0) A.list[i] = row; else A.list.push(row);
  render();
  return row;
}
function apptFail(e) {
  if (e && e.code === 'overlap') toast('יש כבר תור אחר בשעה הזו, אז אי אפשר להחזיר אותו.');
  else handleWriteError(e);
}
async function approveAppt(id) {
  if (!guardWrite()) return;
  try {
    const row = await setApptStatus(id, { status: 'confirmed' });
    closeAll(true); render(); openApptWa(id, 'confirm');
    toast(row.newCard ? `התור אושר ו${firstName(row.name)} נוספה לכרטיסיות` : 'התור אושר');
  } catch (e) { apptFail(e); }
}
async function declineAppt(id) {
  if (!guardWrite()) return;
  try { await setApptStatus(id, { status: 'cancelled' }); closeAll(true); render(); openApptWa(id, 'decline'); toast('הבקשה נדחתה והשעה התפנתה'); }
  catch (e) { apptFail(e); }
}
async function cancelAppt(id) {
  if (!guardWrite()) return;
  try { await setApptStatus(id, { status: 'cancelled' }); closeAll(true); render(); toast('התור בוטל והשעה התפנתה', [{ label: 'הודעה ללקוחה', fn: () => openApptWa(id, 'cancel') }]); }
  catch (e) { apptFail(e); }
}
async function noShowAppt(id) {
  if (!guardWrite()) return;
  try { await setApptStatus(id, { status: 'noshow' }); toast('סומן שהלקוחה לא הגיעה', [{ label: 'ביטול', fn: () => setApptStatus(id, { status: 'confirmed' }).catch(apptFail) }]); }
  catch (e) { apptFail(e); }
}
async function reopenAppt(id) {
  if (!guardWrite()) return;
  try { await setApptStatus(id, { status: 'confirmed', punched: false }); toast('התור חזר להיות פעיל'); }
  catch (e) { apptFail(e); }
}
async function deleteAppt(id) {
  if (!guardWrite()) return;
  const { error } = await sb.from('appointments').delete().eq('id', id);
  if (error) { apptFail(dbErr(error)); return; }
  A.list = A.list.filter(a => a.id !== id);
  closeAll(); toast('התור נמחק');
}
async function completeAppt(id) {
  if (!guardWrite()) return;
  const a = apptById(id);
  if (!a || a.status !== 'confirmed') return;
  const svc = svcById(a.service_id), counts = svc ? svc.counts !== false : true;
  const N = S.settings.cardSize, now = Date.now();
  let c = null, kind = null;
  try {
    c = (a.client_id && await loadClient(a.client_id)) || clientForAppt(a);
    if (counts) {
      if (!c) {
        c = { id: newId(), name: a.name, phone: a.phone, g: 'f', notes: '', punches: 0, rewards: 0, visits: 0, createdAt: now, lastVisit: null, updatedAt: now, log: [{ t: now, a: 'join', p: 0 }] };
        await commit(null, c);
      }
      const prev = S.clients.get(c.id) || c;
      let next;
      if (prev.punches >= N) {
        const np = Math.max(0, prev.punches - N);
        next = { ...prev, punches: np, rewards: prev.rewards + 1, visits: prev.visits + 1, lastVisit: now, updatedAt: now, log: [...prev.log, { t: now, a: 'redeem', p: np, prev: prevOf(prev) }].slice(-LOG_MAX) };
        kind = 'redeem';
      } else {
        const np = prev.punches + 1;
        next = { ...prev, punches: np, visits: prev.visits + 1, lastVisit: now, updatedAt: now, log: [...prev.log, { t: now, a: 'punch', p: np, prev: prevOf(prev) }].slice(-LOG_MAX) };
        kind = 'punch';
        S.justPainted = { id: c.id, idx: prev.punches, at: now };
        setTimeout(() => { if (S.justPainted && S.justPainted.at === now) S.justPainted = null; }, 1200);
      }
      await commit(prev, next);
      c = next;
    }
    await setApptStatus(id, { status: 'done', punched: !!kind, client_id: c ? c.id : a.client_id });
    closeAll(true);
    if (c && kind) openWa(c.id, kind === 'redeem' ? 'redeem' : 'visit');
    else render();
    const msg = !kind ? 'הטיפול סומן כבוצע'
      : kind === 'redeem' ? `טיפול המתנה מומש ונפתחה כרטיסייה חדשה ל${firstName(a.name)}`
      : `ניקוב ל${firstName(a.name)} · ${Math.min(c.punches, N)}/${N}`;
    toast(msg, [{ label: 'ביטול', fn: () => undoComplete(id, kind ? c.id : null, now) }]);
  } catch (e) { handleWriteError(e); }
}
async function extendAppt(id, d) {
  if (!guardWrite()) return;
  const a = apptById(id);
  if (!a || !d) return;
  const prev = { ends_at: a.ends_at, minutes: a.minutes };
  const e = a.e + d * 60000;
  try {
    await setApptStatus(id, { ends_at: iso(e), minutes: (a.minutes || 0) + d });
    const clash = A.blocks.some(b => b.s < e && b.e > a.e);
    toast(`התור יסתיים ב־${T.hm(e)}${clash ? '. שימי לב: יש חסימה בזמן הזה' : ''}`, [{ label: 'ביטול', fn: () => setApptStatus(id, prev).catch(apptFail) }]);
  } catch (err) {
    if (err && err.code === 'overlap') toast('אי אפשר להאריך כל כך: מיד אחרי יש תור אחר.');
    else handleWriteError(err);
  }
}
async function undoComplete(apptId, clientId, t) {
  try {
    if (clientId) undo(clientId, t);
    await setApptStatus(apptId, { status: 'confirmed', punched: false });
  } catch (e) { handleWriteError(e); }
}

/* ---------- appointment WhatsApp messages ---------- */
const APPT_TPLS = [
  { k: 'confirm', label: 'אישור תור' },
  { k: 'photo', label: 'בקשת תמונה' },
  { k: 'reminder', label: 'תזכורת' },
  { k: 'decline', label: 'השעה לא מתאימה' },
  { k: 'cancel', label: 'ביטול' },
];
function openApptWa(id, tpl) {
  if (!apptById(id)) return;
  openSheet({ type: 'wa', id: null, apptId: id, tpl: tpl || 'confirm', custom: null, editing: false });
}

/* ---------- message wording: built-in texts that Sapir can change and save ---------- */
// {placeholders} are filled per client. A line whose placeholder is empty is left out
// (with the "…:" line right above it), so a missing address or link leaves no gap.
const V_CARD = [['שם', 'שם הלקוחה'], ['כרטיסייה', 'הכרטיסייה בלבבות'], ['מצב', 'כמה נשאר עד המתנה'], ['קישור לכרטיסייה', 'קישור לכרטיסייה'], ['מספר טיפולים', 'כמה טיפולים עד מתנה'], ['קישור לקביעת תור', 'קישור לקביעת תור'], ['שם הסטודיו', 'שם הסטודיו']];
const V_APPT = [['שם', 'שם הלקוחה'], ['טיפול', 'הטיפול'], ['מועד', 'יום ושעה'], ['מתי', 'היום / מחר / ביום…'], ['שעה', 'שעה'], ['כתובת', 'כתובת'], ['קישור לקביעת תור', 'קישור לקביעת תור'], ['שם הסטודיו', 'שם הסטודיו']];
const T_SIGN = '\n\n{שם הסטודיו} 💅';
const T_CARD = '\n\nלצפייה בכרטיסייה שלך:\n{קישור לכרטיסייה}';
const MSG_DEFS = [
  { k: 'a_confirm', group: 'appt', label: 'אישור תור', help: 'נשלחת אחרי שהתור אושר.', vars: V_APPT,
    f: 'היי {שם} 💕\nהתור שלך מאושר ✨\n{טיפול}\n{מועד}\n📍 {כתובת}\n\nמחכה לך!' + T_SIGN },
  { k: 'a_reminder', group: 'appt', label: 'תזכורת לתור', help: 'יום לפני התור, מהרשימה «תזכורות למחר» ביומן.', vars: V_APPT,
    f: 'היי {שם} 💕\nתזכורת לתור שלך {מתי} בשעה {שעה} ✨\n{טיפול}\n📍 {כתובת}\n\nאשמח לאישור הגעה 🙏' + T_SIGN },
  { k: 'a_photo', group: 'appt', label: 'בקשת תמונה', help: 'לבקשה שמחכה לאישור. ללקוחה חדשה מתווספת גם שורת המקדמה.', vars: [...V_APPT, ['מקדמה', 'שורת המקדמה']],
    f: 'היי {שם} 💕\nקיבלתי את הבקשה שלך לתור ל{טיפול}, ב{מועד}.\nאפשר לשלוח לי תמונה עדכנית של הציפורניים? ככה אדע איך להתכונן ✨\n\n{מקדמה}' },
  { k: 'a_deposit', group: 'appt', label: 'שורת המקדמה', help: 'מופיעה בתוך «בקשת תמונה», רק ללקוחות חדשות.', vars: [],
    f: 'ללקוחות חדשות יש מקדמה של 50₪ (ביט או פייבוקס) שמתקזזת ממחיר הטיפול, ואחריה התור מאושר.' },
  { k: 'a_decline', group: 'appt', label: 'השעה לא מתאימה', help: 'כשבקשה לתור נדחית.', vars: V_APPT,
    f: 'היי {שם} 💕\nלצערי השעה שביקשת ({מועד}) לא מתאימה לי.\nאפשר לבחור מועד אחר כאן:\n{קישור לקביעת תור}' + T_SIGN },
  { k: 'a_cancel', group: 'appt', label: 'ביטול תור', help: 'כשתור מבוטל.', vars: V_APPT,
    f: 'היי {שם},\nהתור שלך ב{מועד} בוטל.\nלקביעת מועד חדש:\n{קישור לקביעת תור}' + T_SIGN },
  { k: 'visit', group: 'card', label: 'אחרי טיפול', help: 'אחרי ניקוב רגיל בכרטיסייה.', vars: V_CARD,
    f: 'היי {שם} 💕\nתודה שבאת היום ✨\nהוספתי לך ניקוב בכרטיסייה:\n{כרטיסייה}\n{מצב}' + T_CARD + T_SIGN },
  { k: 'visit_full', group: 'card', label: 'הכרטיסייה התמלאה', help: 'אחרי הניקוב שממלא את הכרטיסייה.', vars: V_CARD,
    f: 'היי {שם} 🎉\nתודה שבאת היום! הכרטיסייה שלך התמלאה:\n{כרטיסייה}\n*הטיפול הבא שלך מתנה ממני* 🎁 מחכה לפנק אותך!' + T_CARD + T_SIGN },
  { k: 'redeem', group: 'card', label: 'אחרי טיפול מתנה', help: 'אחרי מימוש המתנה, עם הכרטיסייה החדשה.', vars: V_CARD,
    f: 'היי {שם} 💝\nתתחדשי על טיפול המתנה! תודה שאת איתי 💕\nפתחתי לך כרטיסייה חדשה:\n{כרטיסייה}\n{מצב}' + T_CARD + T_SIGN,
    m: 'היי {שם} 💝\nתתחדש על טיפול המתנה! תודה שאתה איתי 💕\nפתחתי לך כרטיסייה חדשה:\n{כרטיסייה}\n{מצב}' + T_CARD + T_SIGN },
  { k: 'welcome', group: 'card', label: 'הודעת הצטרפות', help: 'כשלקוחה מצטרפת לכרטיסייה.', vars: V_CARD,
    f: 'היי {שם} 💕\nברוכה הבאה לכרטיסיית המועדון שלי!\nעל כל טיפול את מקבלת ניקוב, ואחרי {מספר טיפולים} טיפולים הטיפול הבא מתנה ממני 🎁\n\nהכרטיסייה שלך:\n{כרטיסייה}\n{מצב}' + T_CARD + T_SIGN,
    m: 'היי {שם} 💕\nברוך הבא לכרטיסיית המועדון שלי!\nעל כל טיפול אתה מקבל ניקוב, ואחרי {מספר טיפולים} טיפולים הטיפול הבא מתנה ממני 🎁\n\nהכרטיסייה שלך:\n{כרטיסייה}\n{מצב}' + T_CARD + T_SIGN },
  { k: 'status', group: 'card', label: 'מצב הכרטיסייה', help: 'עדכון כללי על הכרטיסייה.', vars: V_CARD,
    f: 'היי {שם} 💕\nעדכון מהכרטיסייה שלך:\n{כרטיסייה}\n{מצב}' + T_CARD + T_SIGN },
  { k: 'reminder', group: 'card', label: 'הזמנה לחזור', help: 'ללקוחה שלא הגיעה כבר זמן מה.', vars: V_CARD,
    f: 'היי {שם} 💕\nמתגעגעת! עבר קצת זמן מאז הטיפול האחרון, אולי הגיע הזמן לחדש את הציפורניים? 💅\n\n{כרטיסייה}\n{מצב}\nהכרטיסייה שלך: {קישור לכרטיסייה}\n\nלקביעת תור:\n{קישור לקביעת תור}' + T_SIGN },
];
const MSG_BY_KEY = Object.fromEntries(MSG_DEFS.map(d => [d.k, d]));
const savedTpls = () => (S.full && S.full.templates && typeof S.full.templates === 'object' ? S.full.templates : {});
function tplText(key, g) {
  const t = savedTpls()[key];
  if (typeof t === 'string' && t.trim()) return t;
  const d = MSG_BY_KEY[key];
  return d ? (g === 'm' && d.m ? d.m : d.f) : '';
}
function fillTpl(text, vars) {
  const out = [];
  for (const line of String(text || '').replace(/\r/g, '').split('\n')) {
    let empty = false;
    const l = line.replace(/\{([^{}\n]{1,30})\}/g, (m, k) => {
      const key = k.trim();
      if (!Object.prototype.hasOwnProperty.call(vars, key)) return m;
      const v = vars[key];
      if (v == null || v === '') { empty = true; return ''; }
      return String(v);
    });
    if (empty) { if (out.length && /:\s*$/.test(out[out.length - 1])) out.pop(); continue; }
    out.push(l);
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}
function cardVars(c) {
  const N = S.settings.cardSize;
  return {
    'שם': firstName(c.name), 'כרטיסייה': progressLines(c.punches, N), 'מצב': statusLine(c.punches, N),
    'קישור לכרטיסייה': cardLink(c), 'מספר טיפולים': String(N), 'קישור לקביעת תור': bookLink(), 'שם הסטודיו': studioName(),
  };
}
const cardTplKey = (tpl, c) => (tpl === 'visit' && c.punches >= S.settings.cardSize ? 'visit_full' : MSG_BY_KEY[tpl] && MSG_BY_KEY[tpl].group === 'card' ? tpl : 'status');
function cardMessage(tpl, c) { return fillTpl(tplText(cardTplKey(tpl, c), c.g), cardVars(c)); }
function apptVars(a) {
  const today = T.today(), k = T.key(a.s);
  const v = {
    'שם': firstName(a.name), 'טיפול': a.service_name || 'טיפול',
    'מועד': `${T.long(a.s)} בשעה ${T.hm(a.s)}`, 'יום': T.long(a.s), 'שעה': T.hm(a.s),
    'מתי': k === today ? 'היום' : k === T.add(today, 1) ? 'מחר' : 'ב' + T.long(a.s),
    'כתובת': (S.full && S.full.address) || '', 'קישור לקביעת תור': bookLink(), 'שם הסטודיו': studioName(),
  };
  v['מקדמה'] = a.is_new ? fillTpl(tplText('a_deposit'), v) : '';
  return v;
}
function apptMessage(tpl, a) { return a ? fillTpl(tplText('a_' + tpl), apptVars(a)) : ''; }

// the editor
function tplSample(d, spec) {
  if (d.group === 'card') {
    const N = S.settings.cardSize;
    let c = (spec.cid && S.clients.get(spec.cid)) || [...S.clients.values()].find(x => x.punches > 0 && x.punches < N) || { ...EXAMPLE, phone: '', log: [] };
    if (d.k === 'visit_full') c = { ...c, punches: N };
    else if (d.k === 'welcome') c = { ...c, punches: 0 };
    else if (d.k === 'redeem') c = { ...c, punches: 0, rewards: Math.max(1, c.rewards || 0) };
    else if (d.k === 'visit' && c.punches >= N) c = { ...c, punches: N - 1 };
    return { vars: cardVars(c), who: firstName(c.name) };
  }
  const svc = A.services.find(s => s.active);
  let a = (spec.aid && apptById(spec.aid)) || { name: 'נועה לוי', service_name: svc ? svc.name : 'לק ג׳ל', s: T.zoned(T.add(T.today(), 1), 16 * 60 + 30), is_new: false };
  if (d.k === 'a_photo' || d.k === 'a_deposit') a = { ...a, is_new: true };
  return { vars: apptVars(a), who: firstName(a.name) };
}
const tplPreview = (d, spec, text) => fmtWa(fillTpl(text, tplSample(d, spec).vars));
function tplUnknown(d, spec, text) {
  const vars = tplSample(d, spec).vars, out = new Set();
  String(text).replace(/\{([^{}\n]{1,30})\}/g, (m, k) => { if (!Object.prototype.hasOwnProperty.call(vars, k.trim())) out.add(m); return m; });
  return out.size ? `${[...out].join(' ')} לא מוכר בהודעה הזו, ולכן יישלח כמו שהוא. אפשר להוסיף פרטים מהכפתורים למעלה.` : '';
}
function tplFormHTML(spec) {
  const d = MSG_BY_KEY[spec.key];
  if (!d) return sheetHead(spec, 'הנוסח לא נמצא') + '<div class="sheet-body"></div>';
  const saved = savedTpls()[d.k], custom = typeof saved === 'string' && saved.trim() !== '';
  const text = custom ? saved : d.f, who = tplSample(d, spec).who;
  return sheetHead(spec, esc(d.label)) + `<div class="sheet-body">
    <form class="form" id="tplForm" novalidate>
      <p class="help">${esc(d.help)}${custom ? ' <span class="tag-new">נוסח שלך</span>' : ''}</p>
      <div class="field"><label for="t-text">הנוסח</label><textarea class="input tpl-text" id="t-text" rows="9" maxlength="1500">${esc(text)}</textarea></div>
      ${d.vars.length ? `<div class="field"><span class="legend">הוספת פרט שמשתנה לכל לקוחה</span><div class="chips wrap">${d.vars.map(([tok, lbl]) => `<button type="button" class="chip" data-act="tpl-ins" data-v="${esc(tok)}">${esc(lbl)}</button>`).join('')}</div><p class="help">הפרט נכנס במקום שבו הסמן עומד. בהודעה עצמה יופיע הערך האמיתי במקום הסוגריים, ושורה שהערך שלה חסר לא תופיע.</p></div>` : ''}
      <div class="field"><span class="legend">כך זה ייראה${who ? ' אצל ' + esc(who) : ''}</span><div class="bubble" id="t-prev">${tplPreview(d, spec, text)}</div>
        <p class="fine warn-txt" id="t-warn"${tplUnknown(d, spec, text) ? '' : ' hidden'}>${esc(tplUnknown(d, spec, text))}</p></div>
      <div class="err-box" id="t-err" hidden></div>
      <button type="submit" class="btn primary big" id="t-save"${S.canWrite ? '' : ' disabled'}>שמירת הנוסח</button>
      ${custom ? `<button type="button" class="text-btn" data-act="tpl-reset" data-k="${esc(d.k)}">חזרה לנוסח המקורי</button>` : ''}
    </form>
  </div>`;
}
function updateTplPreview(spec) {
  const d = MSG_BY_KEY[spec.key], ta = $('#t-text', spec.inner), box = $('#t-prev', spec.inner), warn = $('#t-warn', spec.inner);
  if (!d || !ta || !box) return;
  box.innerHTML = tplPreview(d, spec, ta.value);
  if (warn) { const w = tplUnknown(d, spec, ta.value); warn.textContent = w; warn.hidden = !w; }
}
function insertTplToken(spec, tok) {
  const ta = $('#t-text', spec.inner);
  if (!ta) return;
  const ins = '{' + tok + '}';
  const s = ta.selectionStart == null ? ta.value.length : ta.selectionStart, e = ta.selectionEnd == null ? s : ta.selectionEnd;
  ta.value = ta.value.slice(0, s) + ins + ta.value.slice(e);
  ta.focus({ preventScroll: true });
  ta.setSelectionRange(s + ins.length, s + ins.length);
  updateTplPreview(spec);
}
async function saveTemplates(all, msg) {
  if (!guardWrite()) return false;
  try { await mergeSettings({ templates: all }); toast(msg); return true; }
  catch (e) { handleWriteError(e); return false; }
}
async function submitTpl(spec) {
  const d = MSG_BY_KEY[spec.key], err = $('#t-err', spec.inner), btn = $('#t-save', spec.inner);
  const text = $('#t-text', spec.inner).value.replace(/\r/g, '').replace(/[ \t]+$/gm, '').trim();
  if (!text) { err.textContent = 'ההודעה ריקה. אפשר לכתוב נוסח או לחזור לנוסח המקורי.'; err.hidden = false; return; }
  err.hidden = true;
  const all = { ...savedTpls() };
  if (text === d.f.trim()) delete all[d.k]; else all[d.k] = text;
  btn.disabled = true;
  if (await saveTemplates(all, 'הנוסח נשמר. מעכשיו ההודעה יוצאת כך.')) closeTop();
  else if (document.contains(btn)) btn.disabled = false;
}
async function resetTpl(key) {
  const all = { ...savedTpls() };
  delete all[key];
  if (await saveTemplates(all, 'חזרנו לנוסח המקורי')) closeTop();
}
function tplSnippet(d) {
  const text = fillTpl(tplText(d.k), tplSample(d, {}).vars);
  const lines = text.split('\n').map(x => x.replace(/^‏/, '').trim()).filter(Boolean);
  const l = lines.length > 1 && /^היי(\s|$)/.test(lines[0]) ? lines[1] : lines[0] || '';
  return l.length > 64 ? l.slice(0, 62) + '…' : l;
}
// settings: one entry; the full list opens in a sheet
function tplListHTML() {
  const n = MSG_DEFS.filter(d => savedTpls()[d.k]).length;
  return `<div class="section-title"><h2>נוסחי ההודעות</h2>${n ? `<span class="hint">${plural(n, 'נוסח אחד שלך', 'נוסחים שלך')}</span>` : ''}</div>
    <div class="card-box"><p class="help">ההודעות שיוצאות ללקוחות בוואטסאפ: אישור, תזכורת, ניקוב ועוד. אפשר לשנות כל נוסח ולשמור, ותמיד אפשר לחזור לנוסח המקורי.</p><button type="button" class="btn ghost" data-act="tpl-list">${IC.edit}<span>צפייה ועריכה</span></button></div>`;
}
function tplListSheetHTML(spec) {
  const saved = savedTpls();
  const row = d => `<button type="button" class="lrow" data-act="tpl-open" data-k="${d.k}"><span class="grow"><span class="title">${esc(d.label)}</span><br><span class="sub2">${esc(tplSnippet(d))}</span></span>${saved[d.k] ? '<span class="tag-new">נוסח שלך</span>' : ''}<span class="muted">›</span></button>`;
  return sheetHead(spec, 'נוסחי ההודעות') + `<div class="sheet-body">
    <div class="group-lbl">על תורים</div><div class="list-plain">${MSG_DEFS.filter(d => d.group === 'appt').map(row).join('')}</div>
    <div class="group-lbl" style="margin-top:14px">על הכרטיסייה</div><div class="list-plain">${MSG_DEFS.filter(d => d.group === 'card').map(row).join('')}</div>
  </div>`;
}
// the WhatsApp sheet links to the editor of the wording it shows
function waTplKey(spec) {
  if (spec.apptId) return MSG_BY_KEY['a_' + spec.tpl] ? 'a_' + spec.tpl : null;
  const c = spec.id ? S.clients.get(spec.id) : null;
  return c ? cardTplKey(spec.tpl, c) : null;
}
function waTplLink(spec) {
  const k = waTplKey(spec);
  return k && !spec.editing ? `<div class="text-row"><button type="button" class="text-btn" data-act="tpl-open" data-k="${k}">${IC.edit}<span>שינוי הנוסח הקבוע</span></button></div>` : '';
}

/* ---------- opening hours & blocks ---------- */
function renderHours() {
  const v = $('#vHours');
  if (!A.loaded) { paint(v, '<div class="skel-list" aria-hidden="true"><div class="skel"></div><div class="skel"></div></div>'); return; }
  if (!A.hoursDraft) A.hoursDraft = JSON.parse(JSON.stringify((S.full && S.full.hours) || {}));
  const d = A.hoursDraft, now = Date.now();
  const upcoming = A.blocks.filter(b => b.e > now).sort((x, y) => x.s - y.s);
  const html = `<header class="top"><div class="brand"><div class="eyebrow">זמינות</div><h1 class="studio">שעות וחופשות</h1><div class="sub">הלקוחות רואות באתר רק שעות פנויות בתוך השעות האלה.</div></div></header>
    <div class="list-plain">${[0, 1, 2, 3, 4, 5, 6].map(wd => {
      const wins = d[String(wd)] || [];
      return `<div class="hours-day">
        <label class="switch"><span class="lbl">יום ${WD_LONG[wd]}<small>${wins.length ? wins.map(w => `<span dir="ltr">${esc(w.from)}–${esc(w.to)}</span>`).join(', ') : 'סגור'}</small></span><input type="checkbox" data-hours-toggle="${wd}"${wins.length ? ' checked' : ''} aria-label="יום ${WD_LONG[wd]} פתוח"></label>
        ${wins.map((w, i) => `<div class="hours-win"><input class="input" type="time" step="300" value="${esc(w.from)}" data-hours="${wd}" data-i="${i}" data-f="from" aria-label="משעה"><span class="sep">עד</span><input class="input" type="time" step="300" value="${esc(w.to)}" data-hours="${wd}" data-i="${i}" data-f="to" aria-label="עד שעה"><button type="button" class="rm" data-act="hours-rm" data-wd="${wd}" data-i="${i}" aria-label="הסרת טווח">×</button></div>`).join('')}
        ${wins.length && wins.length < 3 ? `<button type="button" class="addwin" data-act="hours-add" data-wd="${wd}">+ טווח נוסף (למשל אחרי הפסקה)</button>` : ''}
      </div>`;
    }).join('')}</div>
    <button type="button" class="btn primary big" id="hoursSave" data-act="hours-save"${A.hoursDirty && S.canWrite ? '' : ' disabled'}>שמירת שעות הפעילות</button>
    <div class="section-title"><h2>חסימות וחופשות</h2><button type="button" class="head-btn" data-act="block-new">${IC.plus}<span>חסימה</span></button></div>
    <p class="help">חופשה, יום מקוצר או סידורים. השעות האלה לא יוצעו ללקוחות.</p>
    ${upcoming.length ? `<div class="list-plain">${upcoming.map(b => `<button type="button" class="lrow" data-act="block-open" data-id="${esc(b.id)}"><span class="grow"><span class="title">${b.all_day ? 'כל היום' : `<span dir="ltr">${T.hm(b.s)}–${T.hm(b.e)}</span>`}${b.reason ? ' · ' + esc(b.reason) : ''}</span><br><span class="sub2">${esc(T.long(b.s))}${b.all_day && T.key(b.e - 1) !== T.key(b.s) ? ' עד ' + esc(T.long(b.e - 1)) : ''}</span></span><span class="muted">›</span></button>`).join('')}</div>` : '<div class="empty-day">אין חסימות קרובות.</div>'}`;
  paint(v, html);
}
function blockFormHTML(spec) {
  const b = spec.id ? A.blocks.find(x => x.id === spec.id) : null;
  const hours = !b && spec.k ? dayWindows(spec.k) : [];
  const fromGap = !b && spec.s != null;
  // from a free gap: those exact hours; from a day: that day, starting with its opening hours
  const allDay = b ? b.all_day : !fromGap && !spec.k;
  const sMin = fromGap ? +spec.s : hours.length ? hours[0][0] : 12 * 60;
  const eMin = fromGap ? +spec.e : hours.length ? hours[hours.length - 1][1] : 14 * 60;
  const from = b ? T.key(b.s) : (spec.k || A.day || T.today());
  const to = b ? T.key(b.all_day ? b.e - 1 : b.s) : from;
  const title = b ? 'עריכת חסימה' : spec.k ? 'סגירת שעות' : 'חסימה חדשה';
  return sheetHead(spec, title) + `<div class="sheet-body">
    ${!b && spec.k ? '<p class="help">השעות האלה לא יוצעו ללקוחות באתר. למשל כשטיפול גדול צריך יותר זמן, או לסידורים.</p>' : ''}
    <form class="form" id="blockForm" novalidate>
      <div class="row2">
        <div class="field"><label for="b-from">מתאריך</label><input class="input" id="b-from" type="date" value="${from}"></div>
        <div class="field"><label for="b-to">עד תאריך</label><input class="input" id="b-to" type="date" value="${to}"></div>
      </div>
      <label class="switch"><span class="lbl">כל היום</span><input type="checkbox" id="b-all"${allDay ? ' checked' : ''}></label>
      <div class="row2" id="b-times"${allDay ? ' hidden' : ''}>
        <div class="field"><label for="b-s">משעה</label><input class="input" id="b-s" type="time" step="300" value="${b && !b.all_day ? T.hm(b.s) : T.hhmm(sMin)}"></div>
        <div class="field"><label for="b-e">עד שעה</label><input class="input" id="b-e" type="time" step="300" value="${b && !b.all_day ? T.hm(b.e) : T.hhmm(Math.min(eMin, 1439))}"></div>
      </div>
      <div class="field"><label for="b-reason">סיבה <span class="opt">(רק את רואה)</span></label><input class="input" id="b-reason" maxlength="60" value="${esc(b ? b.reason : '')}" placeholder="${spec.k ? 'למשל: בנייה גדולה' : 'למשל: חופשה'}"></div>
      <div class="err-box" id="b-err" hidden></div>
      <button type="submit" class="btn primary big" id="b-save">${b ? 'שמירת שינויים' : 'הוספת חסימה'}</button>
      ${b ? `<button type="button" class="text-btn danger-txt" data-act="block-delete" data-id="${esc(b.id)}">${IC.trash}<span>מחיקת החסימה</span></button>` : ''}
    </form>
  </div>`;
}
async function submitBlock(spec) {
  if (!guardWrite()) return;
  const r = spec.inner, err = $('#b-err', r);
  const from = $('#b-from', r).value, to = $('#b-to', r).value || from, all = $('#b-all', r).checked;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || to < from) { err.textContent = 'צריך תאריכים תקינים.'; err.hidden = false; return; }
  let s, e;
  if (all) { s = T.zoned(from, 0); e = T.zoned(T.add(to, 1), 0); }
  else {
    const a = T.min($('#b-s', r).value), b = T.min($('#b-e', r).value);
    if (a == null || b == null || b <= a) { err.textContent = 'שעת הסיום צריכה להיות אחרי שעת ההתחלה.'; err.hidden = false; return; }
    if (to !== from) { err.textContent = 'חסימה של שעות היא ליום אחד. לכמה ימים, סמני «כל היום».'; err.hidden = false; return; }
    s = T.zoned(from, a); e = T.zoned(from, b);
  }
  const row = { starts_at: iso(s), ends_at: iso(e), all_day: all, reason: $('#b-reason', r).value.trim() };
  $('#b-save', r).disabled = true;
  const res = spec.id ? await sb.from('blocks').update(row).eq('id', spec.id) : await sb.from('blocks').insert(row);
  if (res.error) { err.textContent = 'השמירה לא הצליחה. בדיקת החיבור ואז ניסיון נוסף.'; err.hidden = false; $('#b-save', r).disabled = false; return; }
  closeTop();
  await refreshBooking().catch(() => {});
  const clash = A.list.filter(x => (x.status === 'pending' || x.status === 'confirmed') && x.s < e && x.e > s).length;
  toast(clash ? `החסימה נשמרה. שימי לב: יש ${plural(clash, 'תור אחד', 'תורים')} בזמן הזה.` : 'החסימה נשמרה');
}

/* ---------- settings ("more" tab) ---------- */
const sel = (id, opts, cur) => `<select class="input" id="${id}">${opts.map(([v, l]) => `<option value="${v}"${String(v) === String(cur) ? ' selected' : ''}>${l}</option>`).join('')}</select>`;
function renderMore() {
  const v = $('#vMore');
  const st = S.full || {}, link = bookLink();
  const svcs = A.services;
  const html = `<header class="top"><div class="brand"><div class="eyebrow">הגדרות</div><h1 class="studio">${esc(studioName())}</h1></div></header>
    <div class="section-title"><h2>דף קביעת התורים</h2></div>
    ${link ? `<div class="card-box"><div class="linkbox"><span>${esc(link)}</span></div><div class="actions-row"><button type="button" class="btn ghost" data-act="copy-text" data-v="${esc(link)}">${IC.copy}<span>העתקה</span></button><a class="btn ghost" href="${esc(link)}" target="_blank" rel="noopener">פתיחה</a></div><p class="help">אפשר לשים את הקישור בביו של האינסטגרם ובסטורי.</p></div>` : '<p class="help">כשתוגדר כתובת האתר בהגדרות הכרטיסייה, הקישור יופיע כאן.</p>'}

    ${pushHTML()}

    <div class="section-title"><h2>טיפולים</h2><button type="button" class="head-btn" data-act="svc-new">${IC.plus}<span>טיפול</span></button></div>
    <div class="list-plain">${svcs.length ? svcs.map(s => `<button type="button" class="lrow${s.active ? '' : ' off'}" data-act="svc-open" data-id="${esc(s.id)}"><span class="grow"><span class="title">${esc(s.name)}</span><br><span class="sub2">${fmtDur(s.minutes)}${s.active ? '' : ' · מוסתר מהאתר'}${s.counts === false ? ' · לא נחשב לכרטיסייה' : ''}</span></span><span class="price">${fmtPrice(s.price)}</span></button>`).join('') : '<div class="empty-day">אין עדיין טיפולים.</div>'}</div>

    <div class="section-title"><h2>כללי קביעת תורים</h2></div>
    <form class="card-box form" id="rulesForm" novalidate>
      <div class="row2">
        <div class="field"><label for="r-step">שעות לבחירה</label>${sel('r-step', [[15, 'כל רבע שעה'], [20, 'כל 20 דק׳'], [30, 'כל חצי שעה'], [60, 'כל שעה']], st.slotMinutes || 30)}</div>
        <div class="field"><label for="r-buf">הפסקה בין תורים</label>${sel('r-buf', [[0, 'בלי'], [5, '5 דק׳'], [10, '10 דק׳'], [15, '15 דק׳'], [30, '30 דק׳']], st.bufferMinutes == null ? 10 : st.bufferMinutes)}</div>
        <div class="field"><label for="r-notice">התראה מינימלית</label>${sel('r-notice', [[0, 'בלי'], [60, 'שעה'], [120, 'שעתיים'], [240, '4 שעות'], [720, '12 שעות'], [1440, 'יום מראש']], st.minNoticeMinutes == null ? 120 : st.minNoticeMinutes)}</div>
        <div class="field"><label for="r-ahead">כמה זמן קדימה</label>${sel('r-ahead', [[14, 'שבועיים'], [30, 'חודש'], [60, 'חודשיים'], [90, '3 חודשים']], st.maxDaysAhead || 30)}</div>
      </div>
      <div class="field"><label for="r-appr">אישור תורים</label>${sel('r-appr', [['new', 'רק לקוחות חדשות מחכות לאישור'], ['all', 'כל תור מחכה לאישור שלי']], st.approval || 'new')}</div>
      <p class="help">לקוחה שכבר יש לה כרטיסייה או תור קודם מזוהה לפי הטלפון.</p>
      <button type="submit" class="btn primary" id="r-save"${S.canWrite ? '' : ' disabled'}>שמירה</button>
    </form>

    <div class="section-title"><h2>פרטי הסטודיו</h2></div>
    <form class="card-box form" id="studioForm" novalidate>
      <div class="field"><label for="d-owner">שם פרטי בהודעות</label><input class="input" id="d-owner" maxlength="30" value="${esc(st.ownerName || '')}"></div>
      <div class="field"><label for="d-phone">הוואטסאפ של הסטודיו</label><input class="input ltr" id="d-phone" type="tel" inputmode="tel" dir="ltr" maxlength="20" value="${esc(st.ownerPhone || '')}"><p class="help">לכאן מגיעות הודעות מהלקוחות מדף התורים.</p></div>
      <div class="field"><label for="d-addr">כתובת</label><input class="input" id="d-addr" maxlength="80" value="${esc(st.address || '')}"><p class="help">מופיעה ללקוחה אחרי קביעת התור ובהודעות האישור.</p></div>
      <div class="field"><label for="d-intro">משפט פתיחה בדף התורים</label><textarea class="input" id="d-intro" rows="2" maxlength="160">${esc(st.intro || '')}</textarea></div>
      <button type="submit" class="btn primary" id="d-save"${S.canWrite ? '' : ' disabled'}>שמירה</button>
    </form>

    ${tplListHTML()}

    <div class="section-title"><h2>כרטיסיית המועדון</h2></div>
    <div class="card-box"><p class="help">כמה טיפולים עד מתנה, שם הסטודיו וכתובת האתר.</p><button type="button" class="btn ghost" data-act="settings">הגדרות הכרטיסייה</button><button type="button" class="btn wa" data-act="summary">${IC.chat}<span>סיכום כרטיסיות לוואטסאפ</span></button></div>

    <div class="section-title"><h2>חשבון</h2></div>
    <form class="card-box form" id="pwForm" novalidate>
      <input type="email" autocomplete="username" value="${esc(CFG.adminEmail || '')}" hidden>
      <div class="field"><label for="p-new">סיסמה חדשה</label><input class="input ltr" id="p-new" type="password" autocomplete="new-password" minlength="8"></div>
      <div class="field"><label for="p-new2">שוב את הסיסמה החדשה</label><input class="input ltr" id="p-new2" type="password" autocomplete="new-password" minlength="8"></div>
      <div class="err" id="p-err" hidden></div>
      <button type="submit" class="btn ghost" id="p-save">החלפת סיסמה</button>
    </form>
    <button type="button" class="btn ghost" data-act="logout">יציאה מהחשבון</button>`;
  paint(v, html);
}
function svcFormHTML(spec) {
  const s = spec.id ? svcById(spec.id) : null;
  return sheetHead(spec, s ? 'עריכת טיפול' : 'טיפול חדש') + `<div class="sheet-body">
    <form class="form" id="svcForm" novalidate>
      <div class="field"><label for="v-name">שם הטיפול</label><input class="input" id="v-name" maxlength="60" value="${esc(s ? s.name : '')}"><div class="err" id="v-name-err" hidden>צריך שם.</div></div>
      <div class="row2">
        <div class="field"><label for="v-min">משך בדקות</label><input class="input" id="v-min" type="number" inputmode="numeric" min="5" max="480" step="5" value="${s ? s.minutes : 60}"></div>
        <div class="field"><label for="v-price">מחיר</label><input class="input" id="v-price" type="number" inputmode="numeric" min="0" step="1" value="${s && s.price != null ? esc(s.price) : ''}"></div>
      </div>
      <label class="switch"><span class="lbl">מוצג באתר<small>לקוחות יכולות לקבוע אותו לבד</small></span><input type="checkbox" id="v-active"${!s || s.active ? ' checked' : ''}></label>
      <label class="switch"><span class="lbl">נחשב לכרטיסייה<small>בסיום הטיפול מתווסף ניקוב</small></span><input type="checkbox" id="v-counts"${!s || s.counts !== false ? ' checked' : ''}></label>
      <div class="err-box" id="v-err" hidden></div>
      <button type="submit" class="btn primary big" id="v-save">${s ? 'שמירת שינויים' : 'הוספת הטיפול'}</button>
      ${s ? `<button type="button" class="text-btn danger-txt" data-act="svc-delete" data-id="${esc(s.id)}">${IC.trash}<span>מחיקת הטיפול</span></button>` : ''}
    </form>
  </div>`;
}
async function submitSvc(spec) {
  if (!guardWrite()) return;
  const r = spec.inner, err = $('#v-err', r);
  const name = $('#v-name', r).value.trim();
  $('#v-name-err', r).hidden = !!name;
  if (!name) return;
  const priceRaw = $('#v-price', r).value.trim();
  const row = { name, minutes: clamp(parseInt($('#v-min', r).value, 10) || 60, 5, 480), price: priceRaw === '' ? null : Number(priceRaw), active: $('#v-active', r).checked, counts: $('#v-counts', r).checked };
  $('#v-save', r).disabled = true;
  const res = spec.id ? await sb.from('services').update(row).eq('id', spec.id)
    : await sb.from('services').insert({ ...row, id: 's' + newId().slice(0, 9), sort: (A.services.reduce((m, s) => Math.max(m, s.sort || 0), 0) + 1) });
  if (res.error) { err.textContent = 'השמירה לא הצליחה.'; err.hidden = false; $('#v-save', r).disabled = false; return; }
  closeTop();
  await refreshBooking().catch(() => {});
  toast('הטיפול נשמר');
}
async function submitRules(form) {
  if (!guardWrite()) return;
  const patch = {
    slotMinutes: +$('#r-step').value, bufferMinutes: +$('#r-buf').value,
    minNoticeMinutes: +$('#r-notice').value, maxDaysAhead: +$('#r-ahead').value, approval: $('#r-appr').value,
  };
  try { $('#r-save').disabled = true; await mergeSettings(patch); toast('הכללים נשמרו'); }
  catch (e) { handleWriteError(e); }
  finally { const b = $('#r-save'); if (b) b.disabled = false; }
}
async function submitStudio(form) {
  if (!guardWrite()) return;
  const patch = { ownerName: $('#d-owner').value.trim(), ownerPhone: $('#d-phone').value.trim(), address: $('#d-addr').value.trim(), intro: $('#d-intro').value.trim() };
  try { $('#d-save').disabled = true; await mergeSettings(patch); toast('הפרטים נשמרו'); }
  catch (e) { handleWriteError(e); }
  finally { const b = $('#d-save'); if (b) b.disabled = false; }
}
async function submitPassword() {
  const a = $('#p-new').value, b = $('#p-new2').value, err = $('#p-err');
  err.hidden = true;
  if (a.length < 8) { err.textContent = 'צריך לפחות 8 תווים.'; err.hidden = false; return; }
  if (a !== b) { err.textContent = 'שתי הסיסמאות לא זהות.'; err.hidden = false; return; }
  $('#p-save').disabled = true;
  const { error } = await sb.auth.updateUser({ password: a });
  $('#p-save').disabled = false;
  if (error) { err.textContent = 'ההחלפה לא הצליחה. נסי שוב.'; err.hidden = false; return; }
  $('#p-new').value = ''; $('#p-new2').value = '';
  toast('הסיסמה הוחלפה. בפעם הבאה נכנסים עם הסיסמה החדשה.');
}

/* ---------- phone alerts (Web Push through the "notify" server function) ---------- */
const FN_URL = (CFG.url || '') + '/functions/v1/notify';
A.push = { state: 'unknown', busy: false, devices: 0, endpoint: null, checking: false };
const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const isStandalone = () => (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const unb64u = s => { const t = s.replace(/-/g, '+').replace(/_/g, '/'); return Uint8Array.from(atob(t + '==='.slice((t.length + 3) % 4)), c => c.charCodeAt(0)); };
function notifyPrefs() {
  const n = (S.full && S.full.notify) || {}, h = Number(n.eveningHour);
  return { booking: n.booking !== false, eveningHour: n.eveningHour == null || !Number.isFinite(h) ? 20 : h };
}
async function callFn(body) {
  const r = await fetch(FN_URL, { method: 'POST', headers: { 'Content-Type': 'application/json', apikey: CFG.key }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error('notify ' + r.status), { code: 'unavailable' });
  return j;
}
async function swReg() {
  if (!('serviceWorker' in navigator)) return null;
  try { return await navigator.serviceWorker.register('sw.js', { scope: './' }); } catch (_) { return null; }
}
const deviceLabel = () => (isIOS() ? 'iPhone' : /Android/i.test(navigator.userAgent) ? 'Android' : /Mac/.test(navigator.platform) ? 'Mac' : /Win/.test(navigator.platform) ? 'Windows' : 'דפדפן');
async function saveSub(sub) {
  const j = sub.toJSON();
  const { error } = await sb.from('push_subs').upsert({ endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth, label: deviceLabel() });
  if (error) throw dbErr(error);
}
async function checkPush() {
  if (A.push.checking) return;
  A.push.checking = true;
  try {
    const ok = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    if (!ok) A.push.state = isIOS() && !isStandalone() ? 'ios' : 'unsupported';
    else if (Notification.permission === 'denied') A.push.state = 'denied';
    else {
      const reg = await swReg();
      const sub = reg ? await reg.pushManager.getSubscription() : null;
      A.push.state = sub && Notification.permission === 'granted' ? 'on' : 'off';
      A.push.endpoint = sub ? sub.endpoint : null;
      if (A.push.state === 'on' && S.canWrite) await saveSub(sub).catch(() => {});
    }
    const { count } = await sb.from('push_subs').select('endpoint', { count: 'exact', head: true });
    A.push.devices = count || 0;
  } catch (_) {
    if (A.push.state === 'unknown') A.push.state = 'off';
  } finally { A.push.checking = false; render(); }
}
async function enablePush() {
  if (!guardWrite()) return;
  A.push.busy = true; render();
  try {
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') { toast(perm === 'denied' ? 'ההתראות נחסמו. אפשר לאפשר אותן בהגדרות הדפדפן.' : 'ההתראות לא הופעלו.'); return; }
    const reg = await swReg();
    if (!reg) throw new Error('no service worker');
    await navigator.serviceWorker.ready;
    const { publicKey } = await callFn({ op: 'key' });
    if (!publicKey) throw new Error('no key');
    let sub = await reg.pushManager.getSubscription();
    if (sub && sub.options && sub.options.applicationServerKey && b64u(sub.options.applicationServerKey) !== publicKey) { await sub.unsubscribe(); sub = null; }
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: unb64u(publicKey) });
    await saveSub(sub);
    toast('ההתראות הופעלו ✓ אפשר לשלוח התראת בדיקה.');
  } catch (_) {
    toast('ההפעלה לא הצליחה. בדיקת החיבור לאינטרנט ואז ניסיון נוסף.');
  } finally { A.push.busy = false; A.push.state = 'unknown'; checkPush(); }
}
async function testPush() {
  A.push.busy = true; render();
  try {
    const r = await callFn({ op: 'test', endpoint: A.push.endpoint });
    if (r.ok && r.sent) toast('נשלחה התראת בדיקה. היא אמורה להופיע תוך כמה שניות.');
    else if (r.error === 'wait') toast('אפשר לשלוח בדיקה נוספת בעוד כמה שניות.');
    else if (r.error === 'unknown') toast('הטלפון הזה לא רשום. כדאי לכבות ולהפעיל שוב.');
    else toast('ההתראה לא נשלחה. כדאי לכבות ולהפעיל שוב.');
  } catch (_) { toast('אין חיבור לשרת ההתראות כרגע.'); }
  finally { A.push.busy = false; render(); }
}
async function disablePush() {
  A.push.busy = true; render();
  try {
    const reg = await swReg(), sub = reg ? await reg.pushManager.getSubscription() : null;
    if (sub) { await sb.from('push_subs').delete().eq('endpoint', sub.endpoint); await sub.unsubscribe(); }
    toast('ההתראות כובו בטלפון הזה');
  } catch (_) { toast('הכיבוי לא הצליח'); }
  finally { A.push.busy = false; A.push.state = 'unknown'; checkPush(); }
}
async function savePushPrefs() {
  if (!guardWrite()) return;
  const notify = { booking: $('#n-booking').checked, eveningHour: +$('#n-evening').value };
  try { await mergeSettings({ notify }); toast('נשמר'); } catch (e) { handleWriteError(e); }
}
function pushHTML() {
  const P = A.push, pref = notifyPrefs(), busy = P.busy ? ' disabled' : '';
  if (P.state === 'unknown') setTimeout(checkPush, 0);
  let main;
  if (P.state === 'ios') main = `<p class="help">באייפון התראות עובדות רק כשפותחים את מסך הניהול מאייקון במסך הבית:</p>
      <ol class="steps"><li>ב־Safari לוחצים על כפתור השיתוף (ריבוע עם חץ למעלה)</li><li>בוחרים «הוספה למסך הבית» ואז «הוספה»</li><li>פותחים את «ספיר · ניהול» מהאייקון החדש, נכנסים עם הסיסמה וחוזרים לכאן</li></ol>`;
  else if (P.state === 'unsupported') main = '<p class="help">הדפדפן הזה לא תומך בהתראות. באנדרואיד זה עובד ב־Chrome, ובאייפון מאייקון במסך הבית.</p>';
  else if (P.state === 'denied') main = '<p class="help">ההתראות חסומות לאתר הזה בהגדרות של הדפדפן או של הטלפון. אחרי שמאפשרים אותן שם, חוזרים לכאן.</p>';
  else if (P.state === 'on') main = `<p class="ok-line">✓ ההתראות פעילות בטלפון הזה</p><div class="actions-row"><button type="button" class="btn ghost" data-act="push-test"${busy}>התראת בדיקה</button><button type="button" class="btn ghost" data-act="push-off"${busy}>כיבוי</button></div>`;
  else if (P.state === 'off') main = `<p class="help">התראה על כל תור חדש, גם כשמסך הניהול סגור.</p><button type="button" class="btn primary" data-act="push-on"${busy}${S.canWrite ? '' : ' disabled'}>הפעלת התראות בטלפון הזה</button>`;
  else main = '<p class="help">בודקת…</p>';
  return `<div class="section-title"><h2>התראות לטלפון</h2>${P.devices ? `<span class="hint">פעיל ב־${plural(P.devices, 'מכשיר אחד', 'מכשירים')}</span>` : ''}</div>
    <div class="card-box">${main}
      <label class="switch"><span class="lbl">תור חדש מהאתר<small>מיד כשלקוחה קובעת או מבקשת תור</small></span><input type="checkbox" id="n-booking"${pref.booking ? ' checked' : ''}${S.canWrite ? '' : ' disabled'}></label>
      <div class="field"><label for="n-evening">רשימת התורים של מחר</label>${sel('n-evening', [[-1, 'בלי'], [18, 'כל ערב ב־18:00'], [19, 'כל ערב ב־19:00'], [20, 'כל ערב ב־20:00'], [21, 'כל ערב ב־21:00'], [22, 'כל ערב ב־22:00']], pref.eveningHour)}<p class="help">עם לחיצה ישירה לשליחת התזכורות בוואטסאפ. בערב בלי תורים למחר לא נשלח כלום.</p></div>
    </div>`;
}

/* ---------- links from alerts: #appt=<id> opens the appointment, #remind the reminders list ---------- */
function handleRoute(h) {
  if (!h || !A.loaded) return false;
  if (h === '#remind') {
    A.day = T.today(); closeAll(true); setView('agenda');
    setTimeout(() => { const el = $('#remindSec'); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 120);
  } else if (h.startsWith('#appt=')) {
    const a = apptById(decodeURIComponent(h.slice(6)));
    if (!a) { toast('התור לא נמצא. אולי הוא כבר נמחק.'); return false; }
    A.day = T.key(a.s); closeAll(true); setView('agenda'); openSheet({ type: 'appt', id: a.id });
  } else return false;
  try { history.replaceState(null, '', location.pathname + location.search); } catch (_) {}
  return true;
}
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('message', e => {
    if (!e.data || e.data.type !== 'open' || !S.authed) return;
    const h = new URL(e.data.url, location.href).hash;
    refreshBooking().catch(() => {}).then(() => handleRoute(h));
  });
}

/* ---------- login ---------- */
async function doLogin() {
  const pw = $('#lPass').value, btn = $('#lBtn'), err = $('#lErr');
  if (!pw) { $('#lPass').focus(); return; }
  btn.disabled = true; err.hidden = true;
  let res;
  try { res = await sb.auth.signInWithPassword({ email: CFG.adminEmail, password: pw }); }
  catch (_) { res = { error: { message: 'network' } }; }
  btn.disabled = false;
  if (res.error) {
    err.textContent = /invalid|credentials/i.test(res.error.message || '') ? 'הסיסמה לא נכונה.' : 'אין חיבור כרגע. בדקי את האינטרנט ונסי שוב.';
    err.hidden = false;
    return;
  }
  $('#lPass').value = '';
  startApp();
}
async function logout() {
  try { await sb.auth.signOut(); } catch (_) {}
  location.reload();
}

/* ---------- events for the new parts ---------- */
function extraClick(act, el) {
  const id = el.dataset.id, spec = topSheet();
  switch (act) {
    case 'tab': setView(el.dataset.v); break;
    case 'day': A.day = el.dataset.k; render(); break;
    case 'week': A.day = T.add(A.day || T.today(), +el.dataset.d); render(); break;
    case 'go-today': A.day = T.today(); render(); break;
    case 'reload': refreshBooking().catch(() => {}); break;
    case 'appt-open': openSheet({ type: 'appt', id }); break;
    case 'appt-new': if (guardWrite()) openSheet({ type: 'apptForm', id: null, k: el.dataset.k, m: el.dataset.m }); break;
    case 'appt-edit': if (guardWrite()) openSheet({ type: 'apptForm', id }); break;
    case 'appt-approve': approveAppt(id); break;
    case 'appt-decline': declineAppt(id); break;
    case 'appt-cancel': cancelAppt(id); break;
    case 'appt-noshow': noShowAppt(id); break;
    case 'appt-reopen': reopenAppt(id); break;
    case 'appt-done': completeAppt(id); break;
    case 'appt-wa': openApptWa(id, el.dataset.tpl); break;
    case 'appt-delete-ask': if (spec) { spec.confirmDelete = true; fillSheet(spec, false); } break;
    case 'appt-delete-no': if (spec) { spec.confirmDelete = false; fillSheet(spec, false); } break;
    case 'appt-delete-yes': deleteAppt(id); break;
    case 'pick-time': if (spec) { $('#a-time', spec.inner).value = el.dataset.v; updateFreeChips(spec); } break;
    case 'copy-text': copyText(el.dataset.v, el.parentElement.querySelector('.phone')); break;
    case 'hours-add': {
      const d = A.hoursDraft, w = d[el.dataset.wd] || (d[el.dataset.wd] = []);
      const last = w[w.length - 1];
      w.push(last ? { from: last.to, to: T.hhmm(Math.min(1439, (T.min(last.to) || 0) + 120)) } : { from: '09:00', to: '17:00' });
      A.hoursDirty = true; render(); break;
    }
    case 'hours-rm': { const w = A.hoursDraft[el.dataset.wd] || []; w.splice(+el.dataset.i, 1); A.hoursDirty = true; render(); break; }
    case 'hours-save': saveHours(); break;
    case 'block-new': if (guardWrite()) openSheet({ type: 'blockForm', id: null }); break;
    case 'block-open': if (guardWrite()) openSheet({ type: 'blockForm', id }); break;
    case 'block-delete': deleteBlock(id); break;
    case 'svc-new': if (guardWrite()) openSheet({ type: 'svcForm', id: null }); break;
    case 'svc-open': if (guardWrite()) openSheet({ type: 'svcForm', id }); break;
    case 'svc-delete': deleteSvc(id); break;
    case 'block-gap': if (guardWrite()) openSheet({ type: 'blockForm', id: null, k: el.dataset.k, s: +el.dataset.s, e: +el.dataset.e }); break;
    case 'block-day': if (guardWrite()) openSheet({ type: 'blockForm', id: null, k: el.dataset.k }); break;
    case 'appt-extend': extendAppt(id, +el.dataset.d); break;
    case 'tpl-open': {
      const from = spec && spec.type === 'wa' ? spec : null;
      openSheet({ type: 'tplForm', key: el.dataset.k, cid: from ? from.id : null, aid: from ? from.apptId : null });
      break;
    }
    case 'tpl-list': openSheet({ type: 'tplList' }); break;
    case 'tpl-ins': if (spec && spec.type === 'tplForm') insertTplToken(spec, el.dataset.v); break;
    case 'tpl-reset': resetTpl(el.dataset.k); break;
    case 'wa-open':
      // the reminder counts as sent once WhatsApp is opened with it
      if (spec && spec.type === 'wa' && spec.apptId && spec.tpl === 'reminder') {
        const aid = spec.apptId;
        markReminded(aid);
        setTimeout(() => { const top = topSheet(); if (top && top.apptId === aid) closeTop(); }, 400);
      }
      break;
    case 'push-on': enablePush(); break;
    case 'push-test': testPush(); break;
    case 'push-off': disablePush(); break;
    case 'logout': logout(); break;
  }
}
async function saveHours() {
  if (!guardWrite()) return;
  const d = A.hoursDraft, clean = {};
  for (let wd = 0; wd < 7; wd++) {
    const wins = (d[String(wd)] || []).filter(w => T.min(w.from) != null && T.min(w.to) != null);
    for (const w of wins) if (T.min(w.to) <= T.min(w.from)) { toast(`ביום ${WD_LONG[wd]} שעת הסיום מוקדמת מההתחלה.`); return; }
    clean[String(wd)] = wins.map(w => ({ from: w.from, to: w.to })).sort((a, b) => T.min(a.from) - T.min(b.from));
  }
  try { await mergeSettings({ hours: clean }); A.hoursDraft = null; A.hoursDirty = false; render(); toast('שעות הפעילות נשמרו'); }
  catch (e) { handleWriteError(e); }
}
async function deleteBlock(id) {
  if (!guardWrite()) return;
  const { error } = await sb.from('blocks').delete().eq('id', id);
  if (error) { handleWriteError(dbErr(error)); return; }
  closeAll(true);
  await refreshBooking().catch(() => {});
  toast('החסימה נמחקה');
}
async function deleteSvc(id) {
  if (!guardWrite()) return;
  const { error } = await sb.from('services').delete().eq('id', id);
  if (error) { handleWriteError(dbErr(error)); return; }
  closeAll(true);
  await refreshBooking().catch(() => {});
  toast('הטיפול נמחק');
}
function extraSubmit(id, spec, form) {
  if (id === 'loginForm') doLogin();
  else if (id === 'apptForm' && spec) submitAppt(spec);
  else if (id === 'blockForm' && spec) submitBlock(spec);
  else if (id === 'svcForm' && spec) submitSvc(spec);
  else if (id === 'tplForm' && spec) submitTpl(spec);
  else if (id === 'rulesForm') submitRules(form);
  else if (id === 'studioForm') submitStudio(form);
  else if (id === 'pwForm') submitPassword();
}
function extraInput(e) {
  const t = e.target, spec = topSheet();
  if (t.matches && t.matches('[data-hours]')) {
    const w = (A.hoursDraft[t.dataset.hours] || [])[+t.dataset.i];
    if (w) { w[t.dataset.f] = t.value; A.hoursDirty = true; const b = $('#hoursSave'); if (b) b.disabled = !S.canWrite; }
    return;
  }
  if (!spec) return;
  if (spec.type === 'tplForm' && t.id === 't-text') { updateTplPreview(spec); return; }
  if (spec.type === 'apptForm') {
    if (t.id === 'a-svc') {
      const s = svcById(t.value);
      if (s) { $('#a-min', spec.inner).value = s.minutes; $('#a-price', spec.inner).value = s.price == null ? '' : s.price; }
    }
    if (t.id === 'a-name') {
      const c = [...S.clients.values()].find(x => x.name === t.value.trim());
      const ph = $('#a-phone', spec.inner);
      if (c && c.phone && !ph.value) ph.value = c.phone;
    }
    if (['a-svc', 'a-date', 'a-min', 'a-time'].includes(t.id)) updateFreeChips(spec);
  }
}
document.addEventListener('change', e => {
  const t = e.target;
  if (t.matches && t.matches('[data-hours-toggle]')) {
    const wd = t.dataset.hoursToggle;
    A.hoursDraft[wd] = t.checked ? [{ from: '09:00', to: '19:00' }] : [];
    A.hoursDirty = true; render();
  } else if (t.id === 'b-all') {
    const box = $('#b-times'); if (box) box.hidden = t.checked;
  } else if (t.id === 'n-booking' || t.id === 'n-evening') {
    savePushPrefs();
  } else extraInput(e);
});

/* ---------- start ---------- */
let started = false;
async function startApp() {
  if (started) return;
  started = true;
  S.authed = true;
  try { const v = localStorage.getItem('sapinails.view'); if (['agenda', 'cards', 'hours', 'more'].includes(v)) S.view = v; } catch (_) {}
  render();
  let ok = false;
  try { const { data, error } = await sb.rpc('is_admin'); ok = !error && data === true; } catch (_) {}
  S.canWrite = ok;
  S.db = DB;
  if (!ok) {
    S.status = 'nodb';
    toast('החשבון הזה לא מורשה לנהל את הסטודיו.');
    render();
    return;
  }
  subscribe();
  const route = location.hash;
  refreshBooking().then(() => handleRoute(route)).catch(() => {});
  sb.channel('sapinails-admin')
    .on('postgres_changes', { event: '*', schema: 'public', table: 'clients' }, () => notify('clients'))
    .on('postgres_changes', { event: '*', schema: 'public', table: 'settings' }, () => notify('settings'))
    .on('postgres_changes', { event: '*', schema: 'public', table: 'appointments' }, refreshSoon)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'blocks' }, refreshSoon)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'services' }, refreshSoon)
    .subscribe();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') { refreshSoon(); notify('clients'); }
  });
  window.addEventListener('hashchange', () => handleRoute(location.hash));
  setInterval(() => { if (document.visibilityState === 'visible') refreshSoon(); }, 120000);
}
async function boot() {
  $('#tabbar .in').innerHTML = [['agenda', 'יומן'], ['cards', 'כרטיסיות'], ['hours', 'שעות'], ['more', 'הגדרות']]
    .map(([k, l]) => `<button type="button" class="tab" data-act="tab" data-v="${k}">${TAB_ICONS[k]}<span>${l}</span>${k === 'agenda' ? '<span class="badge" id="pendBadge" hidden></span>' : ''}</button>`).join('');
  let session = null;
  try { const { data } = await sb.auth.getSession(); session = data && data.session; } catch (_) {}
  if (session) startApp();
  else { render(); setTimeout(() => { const p = $('#lPass'); if (p) p.focus(); }, 50); }
  sb.auth.onAuthStateChange(ev => { if (ev === 'SIGNED_OUT' && started) location.reload(); });
}
boot();
