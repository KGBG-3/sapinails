#!/usr/bin/env python3
"""Assemble admin/index.html from the card app + the new admin parts."""
import pathlib, sys

HERE = pathlib.Path(__file__).parent
OUT = pathlib.Path(sys.argv[1])

css = (HERE / 'punch.css.part').read_text(encoding='utf-8')
css = css.replace('<style>\n', '', 1).rsplit('</style>', 1)[0]
extra_css = (HERE / 'extra.css').read_text(encoding='utf-8')
defs = (HERE / 'defs.html.part').read_text(encoding='utf-8')
cards = (HERE / 'cards.html.part').read_text(encoding='utf-8')
js = (HERE / 'punch.js.part').read_text(encoding='utf-8')
app = (HERE / 'app.js').read_text(encoding='utf-8')


def sub(text, old, new, count=1):
    if text.count(old) != count:
        raise SystemExit(f'expected {count} match(es) for: {old[:80]!r}, found {text.count(old)}')
    return text.replace(old, new)


# ---- card screen markup becomes one of the views ----
cards_view = cards.split('<button type="button" class="btn primary fab"', 1)[0]
cards_view = sub(cards_view, '<div class="app" dir="rtl" lang="he">', '<section class="view" id="vCards" hidden>')
cards_view = cards_view.rstrip()
assert cards_view.endswith('</div>')
cards_view = cards_view[: -len('</div>')] + '</section>'

# ---- card app logic, adapted ----
js = sub(js, """function render() {
  renderHeader();
  renderBanner();
  renderToolbar();
  renderMain();
  updateSheets();
  $('#addBtn').hidden = S.stack.length > 0 || S.status !== 'ready' || !S.canWrite || S.clients.size === 0;
  root.classList.toggle('locked', S.stack.length > 0);
}""", """function renderCards() {
  renderHeader();
  renderBanner();
  renderToolbar();
  renderMain();
}""")
js = sub(js, """  if (spec.type === 'client') html = clientSheetHTML(spec);
  else if (spec.type === 'wa') {
    if (!first && spec.editing) { updateWaLink(spec); return; }
    html = waSheetHTML(spec);
  } else if (first) {
    html = spec.type === 'edit' ? editFormHTML(spec) : settingsHTML(spec);
  } else return;""", """  if (spec.type === 'client') html = clientSheetHTML(spec);
  else if (spec.type === 'appt') html = apptSheetHTML(spec);
  else if (spec.type === 'tplList') html = tplListSheetHTML(spec);
  else if (spec.type === 'wa') {
    if (!first && spec.editing) { updateWaLink(spec); return; }
    html = waSheetHTML(spec);
  } else if (first) {
    html = spec.type === 'edit' ? editFormHTML(spec) : spec.type === 'settings' ? settingsHTML(spec)
      : spec.type === 'apptForm' ? apptFormHTML(spec) : spec.type === 'blockForm' ? blockFormHTML(spec)
      : spec.type === 'tplForm' ? tplFormHTML(spec) : svcFormHTML(spec);
  } else return;""")
js = sub(js, """  const nb = $('.sheet-body', spec.inner);
  if (nb && !first) nb.scrollTop = top;
}""", """  const nb = $('.sheet-body', spec.inner);
  if (nb && !first) nb.scrollTop = top;
  if (first && spec.type === 'apptForm') updateFreeChips(spec);
}""")
js = sub(js, """function waText(spec) {
  if (spec.custom != null) return spec.custom;
  if (!spec.id) return buildSummary();""", """function waText(spec) {
  if (spec.custom != null) return spec.custom;
  if (spec.apptId) return apptMessage(spec.tpl, apptById(spec.apptId));
  if (!spec.id) return buildSummary();""")
js = sub(js, """function waPhone(spec) {
  if (!spec.id) return S.settings.ownerPhone;""", """function waPhone(spec) {
  if (spec.apptId) { const ap = apptById(spec.apptId); return ap ? ap.phone : ''; }
  if (!spec.id) return S.settings.ownerPhone;""")
js = sub(js, """  const chips = c ? `<div class="chips wrap" role="radiogroup" aria-label="סוג ההודעה">""", """  const ap = spec.apptId ? apptById(spec.apptId) : null;
  const chips = ap ? `<div class="chips wrap" role="radiogroup" aria-label="סוג ההודעה">${APPT_TPLS.map(t => `<button type="button" class="chip" role="radio" aria-checked="${t.k === spec.tpl}" data-act="tpl" data-k="${t.k}">${t.label}</button>`).join('')}</div>`
    : c ? `<div class="chips wrap" role="radiogroup" aria-label="סוג ההודעה">""")
js = sub(js, """    : c ? 'אין מספר שמור, וואטסאפ יבקש לבחור איש קשר.' : 'לא הוגדר מספר, וואטסאפ יבקש לבחור צ׳אט.';
  const title = c ? `הודעה ל${esc(firstName(c.name))}` : 'סיכום לוואטסאפ';""", """    : (c || ap) ? 'אין מספר שמור, וואטסאפ יבקש לבחור איש קשר.' : 'לא הוגדר מספר, וואטסאפ יבקש לבחור צ׳אט.';
  const title = ap ? `הודעה ל${esc(firstName(ap.name))}` : c ? `הודעה ל${esc(firstName(c.name))}` : 'סיכום לוואטסאפ';""")
js = sub(js, """      if (el.dataset.t === 's-n') {
        $('#s-preview').innerHTML = nailRow(v, v, 'mid');
        $('#s-n-help').textContent = cardHelp(v);
      }
      break;
    }
  }
});""", """      if (el.dataset.t === 's-n') {
        $('#s-preview').innerHTML = nailRow(v, v, 'mid');
        $('#s-n-help').textContent = cardHelp(v);
      }
      break;
    }
    case 'appt-new-for': {
      const c = S.clients.get(id);
      if (c && guardWrite()) openSheet({ type: 'apptForm', id: null, name: c.name, phone: c.phone });
      break;
    }
    default: extraClick(act, el);
  }
});""")
js = sub(js, """document.addEventListener('submit', e => {
  e.preventDefault();
  const spec = topSheet();
  if (!spec) return;
  if (e.target.id === 'clientForm') submitClient(spec);
  else if (e.target.id === 'settingsForm') submitSettings(spec);
});""", """document.addEventListener('submit', e => {
  e.preventDefault();
  const spec = topSheet();
  if (e.target.id === 'clientForm' && spec) submitClient(spec);
  else if (e.target.id === 'settingsForm' && spec) submitSettings(spec);
  else extraSubmit(e.target.id, spec, e.target);
});""")
js = sub(js, """  else if (e.target.id === 'f-phone') { const spec = topSheet(); if (spec) spec.dupAck = null; }
});""", """  else if (e.target.id === 'f-phone') { const spec = topSheet(); if (spec) spec.dupAck = null; }
  else extraInput(e);
});""")
js = sub(js, """  S.unsubS = S.db.doc('meta/settings').onSnapshot(snap => {
    S.settings = normSettings(snap.exists ? snap.data() : null);
    render();""", """  S.unsubS = S.db.doc('meta/settings').onSnapshot(snap => {
    S.settings = normSettings(snap.exists ? snap.data() : null);
    S.full = (snap.exists && snap.data()) || {};
    if (!A.hoursDirty) A.hoursDraft = null;
    render();""")
js = sub(js, "${nailRow(c.punches, N, 'big', paintIdx)}", "${nailRow(c.punches, N, 'big', paintIdx, Array.isArray(c.log) ? punchDates(c, N) : null)}")
js = sub(js, """function nailRow(p, N, size, paintIdx = -1) {
  const f = Math.min(p, N), full = p >= N;
  let out = '';
  for (let i = 0; i < N; i++) {
    if (i < f) {
      const col = shade(i, N);
      out += i === paintIdx && size === 'big'
        ? `<span class="nailbox">${nail('empty', { n: i + 1 })}${nail('full', { color: col, cls: 'painting' })}</span>`
        : nail('full', { color: col });
    } else {
      out += nail('empty', { n: size === 'big' ? i + 1 : '' });
    }
  }
  out += nail(full ? 'gift-on' : 'gift-off');""", """function nailRow(p, N, size, paintIdx = -1, dates = null) {
  const f = Math.min(p, N), full = p >= N;
  const cell = (h, i) => (dates ? `<span class="nailcell">${h}<span class="nd">${i != null && i < f ? nailDate(dates[i]) : ''}</span></span>` : h);
  let out = '';
  for (let i = 0; i < N; i++) {
    if (i < f) {
      const col = shade(i, N);
      out += cell(i === paintIdx && size === 'big'
        ? `<span class="nailbox">${nail('empty', { n: i + 1 })}${nail('full', { color: col, cls: 'painting' })}</span>`
        : nail('full', { color: col }), i);
    } else {
      out += cell(nail('empty', { n: size === 'big' ? i + 1 : '' }), i);
    }
  }
  out += cell(nail(full ? 'gift-on' : 'gift-off'), null);""")
js = sub(js, """        <div class="info-row"><dt>ביקור אחרון</dt><dd>${esc(c.lastVisit ? rel(c.lastVisit) + ' · ' + fmtDate(c.lastVisit) : 'עוד לא נרשם')}</dd></div>""",
         """        <div class="info-row"><dt>ביקור אחרון</dt><dd>${esc(c.lastVisit ? rel(c.lastVisit) + ' · ' + fmtDate(c.lastVisit) : 'עוד לא נרשם')}</dd></div>
        ${(() => { const nx = nextApptFor(c); return nx ? `<div class="info-row"><dt>התור הבא</dt><dd><button type="button" class="text-btn" data-act="appt-open" data-id="${esc(nx.id)}">${esc(T.long(nx.s))} · ${T.hm(nx.s)}</button></dd></div>` : ''; })()}""")
js = sub(js, """      <div class="actions">${primary}<div class="actions-row">${waBtn}${undoBtn}</div></div>""",
         """      <div class="actions">${primary}<div class="actions-row">${waBtn}${undoBtn}</div><button type="button" class="text-btn" data-act="appt-new-for" data-id="${id}"${dis}>${IC.plus}<span>קביעת תור</span></button></div>""")
js = sub(js, """  if (S.status === 'nodb') html = '<strong>רשימת הלקוחות לא נטענה בתצוגה הזו.</strong> הנתונים נשמרים בתוך Claude, ולכן הכרטיסייה עובדת כשפותחים את הדף מתוך Claude, בחשבון שקיבל גישה אליו.';
  else if (S.status === 'ready' && !S.canWrite) html = '<strong>מצב צפייה בלבד.</strong> כדי לנקב ולעדכן לקוחות צריך הרשאת עריכה בדף.';""",
         """  if (S.status === 'nodb') html = S.canWrite ? '<strong>רשימת הלקוחות לא נטענה.</strong> כדאי לבדוק את החיבור לאינטרנט ולרענן את הדף.' : '<strong>אין הרשאה.</strong> צריך להתחבר עם הסיסמה של הסטודיו.';
  else if (S.status === 'ready' && !S.canWrite) html = '<strong>מצב צפייה בלבד.</strong> צריך להתחבר עם הסיסמה של הסטודיו.';""")
js = sub(js, "toast('השינוי לא נשמר: אין הרשאת עריכה בדף הזה.');", "toast('השינוי לא נשמר: צריך להתחבר מחדש עם הסיסמה.');")
js = sub(js, "  el.appendChild(span);\n", "  el.appendChild(span);\n  span.addEventListener('click', () => el.remove());\n")
js = sub(js, "function buildMessage(tpl, c) {\n", "function buildMessage(tpl, c) { return cardMessage(tpl, c); }\nfunction buildMessageBuiltin(tpl, c) {\n")
js = sub(js, "{ k: 'reminder', label: 'תזכורת לתור' },", "{ k: 'reminder', label: 'הזמנה לחזור' },")
js = sub(js, """<button type="button" class="text-btn" data-act="wa-edit">${spec.editing ? 'חזרה לנוסח המוכן' : 'עריכת הנוסח'}</button></div>""",
         """<button type="button" class="text-btn" data-act="wa-edit">${spec.editing ? 'חזרה לנוסח המוכן' : 'עריכה חד־פעמית'}</button></div>
    ${waTplLink(spec)}""")
js = sub(js, '<a class="btn wa" id="wa-link" href=', '<a class="btn wa" id="wa-link" data-act="wa-open" href=')
# replace the artifact start-up with the new one
head, tail = js.split('async function init() {', 1)
assert tail.rstrip().endswith('})();')
js = head + app + '\n})();\n'

page = f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>ניהול · sapinails.il</title>
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#FAE9EE">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="ספיר · ניהול">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700;800&amp;family=Frank+Ruhl+Libre:wght@400;500&amp;family=Playpen+Sans+Hebrew:wght@400&amp;family=Ms+Madi&amp;display=swap">
<style>
{css.strip()}

{extra_css.strip()}
</style>
</head>
<body>
{defs.strip()}

<div class="app" id="app" dir="rtl" lang="he">
  <section class="view login" id="vLogin" hidden>
    <div class="login-card">
      <p class="script" dir="ltr">sapinails.il</p>
      <h1>הסטודיו של ספיר</h1>
      <form class="form" id="loginForm" novalidate>
        <input type="email" name="username" autocomplete="username" value="" hidden>
        <div class="field">
          <label for="lPass">סיסמה</label>
          <input class="input ltr" id="lPass" name="password" type="password" autocomplete="current-password" enterkeyhint="go">
        </div>
        <p class="err" id="lErr" hidden></p>
        <button type="submit" class="btn primary big" id="lBtn">כניסה</button>
      </form>
    </div>
  </section>
  <section class="view" id="vAgenda" hidden></section>
  {cards_view.strip()}
  <section class="view" id="vHours" hidden></section>
  <section class="view" id="vMore" hidden></section>
</div>

<button type="button" class="btn primary fab" id="addBtn" dir="rtl" hidden></button>
<nav class="tabbar" id="tabbar" aria-label="ניווט" hidden><div class="in"></div></nav>
<div id="sheets" dir="rtl" lang="he"></div>
<div class="toasts" id="toasts" dir="rtl" lang="he" aria-live="polite"></div>

<script src="../assets/config.js?v=1"></script>
<script src="../assets/vendor/supabase-2.117.3.js"></script>
<script>
{js.strip()}
</script>
</body>
</html>
"""
page = page.replace('<input type="email" name="username" autocomplete="username" value="" hidden>',
                    '<input type="email" name="username" autocomplete="username" value="sapir@sapinails.co.il" hidden>')
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page, encoding='utf-8')
print('wrote', OUT, len(page.splitlines()), 'lines')
