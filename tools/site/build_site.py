#!/usr/bin/env python3
"""Build the public home page (index.html) from the site design (tools/site/source.html).

The design was made as a page in Claude. This adds what the public version needs:
a real document head with share tags, the work photos, booking buttons that go to book/,
prices and opening hours read live from the booking system, a photo viewer,
fonts served from the site itself, and the accessibility work (skip link, keyboard-safe
menu and photo viewer, readable colours, links to the accessibility, privacy and terms pages).
Run from the repository root:  python3 tools/site/build_site.py
"""
import pathlib, re, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
src = (ROOT / 'tools/site/source.html').read_text(encoding='utf-8')
WA = 'https://wa.me/972543439530'
WA_HELLO = WA + '?text=%D7%94%D7%99%D7%99%20%D7%A1%D7%A4%D7%99%D7%A8%2C%20%D7%90%D7%A9%D7%9E%D7%97%20%D7%9C%D7%A7%D7%91%D7%95%D7%A2%20%D7%AA%D7%95%D7%A8'
WA_CANCEL = 'https://api.whatsapp.com/send?phone=972543439530&amp;text=' + urllib.parse.quote('היי ספיר, אשמח לבטל או לשנות תור')
CAL = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>'
NEW_TAB = '<span class="ax-sr"> (נפתח בחלון חדש)</span>'
VER = '1'   # for assets/fonts.css, site.css, site.js


def sub(text, old, new, count=1):
    n = text.count(old)
    if n != count:
        raise SystemExit(f'expected {count} match(es), found {n}: {old[:90]!r}')
    return text.replace(old, new)


# ---------- split the design into head styles and body ----------
style_start = src.index('<style>')
style_end = src.index('</style>') + len('</style>')
css = src[style_start:style_end]
body = src[src.index('<svg class="defs"'):].rstrip()

# ---------- colours that are readable on the pink background (contrast of 4.5:1 and up) ----------
css = sub(css, '--ink-3:#A48D98', '--ink-3:#7A5A68')
css = sub(css, ':focus-visible{outline:3px solid var(--rose);outline-offset:3px}', ':focus-visible{outline:3px solid var(--rose-ink);outline-offset:3px}')

# ---------- booking buttons go to the booking page ----------
wa_btn = re.compile(r'<a class="btn btn-rose( hdr-cta)?" href="' + re.escape(WA_HELLO) + r'" target="_blank" rel="noopener noreferrer">(.*?)</a>', re.S)
found = wa_btn.findall(body)
assert len(found) == 4, len(found)
wa_icon = re.search(r'<svg viewBox="0 0 24 24" aria-hidden="true">.*?</svg>', found[1][1], re.S).group(0)
def to_book(m):
    if m.group(1):
        return '<a class="btn btn-rose hdr-cta" href="book/">לקביעת תור</a>'
    return f'<a class="btn btn-rose" href="book/">{CAL}לקביעת תור</a>'
body = wa_btn.sub(to_book, body)

# ---------- contact: booking first, WhatsApp for questions ----------
body = sub(body, '<h2 class="h-display" id="ct-h">הכי פשוט בוואטסאפ</h2>', '<h2 class="h-display" id="ct-h">קביעת תור</h2>')
body = sub(body, '<p>כותבים מה רוצים לעשות, מצרפים תמונה של הציפורניים, ומתאמים שעה. ללקוחות חדשות התור נשמר אחרי המקדמה.</p>',
           '<p>בוחרים טיפול, יום ושעה פנויה, והתור נשמר. לקוחה חדשה? אחרי הבקשה שולחים לי תמונה של הציפורניים, והתור מאושר אחרי המקדמה. לשאלות אני בוואטסאפ.</p>')
body = sub(body, f'<a class="btn btn-rose" href="book/">{CAL}לקביעת תור</a>\n        <a class="btn btn-line" href="https://www.instagram.com/sapinails.il/"',
           f'<a class="btn btn-rose" href="book/">{CAL}לקביעת תור</a>\n        <a class="btn btn-line" href="{WA}" target="_blank" rel="noopener noreferrer">{wa_icon}וואטסאפ</a>\n        <a class="btn btn-line" href="https://www.instagram.com/sapinails.il/"')
body = sub(body, '<span class="phone" dir="ltr">054-343-9530</span><button type="button" class="copy" id="copyPhone">',
           '<a class="phone" dir="ltr" href="tel:+972543439530">054-343-9530</a><button type="button" class="copy" id="copyPhone" aria-label="העתקה של מספר הטלפון">')
body = sub(body, '<div class="ct-row"><span class="k">איפה</span><span class="v"><span>תל אביב · הכתובת המדויקת נשלחת אחרי קביעת התור</span></span></div>',
           '<div class="ct-row"><span class="k">איפה</span><span class="v"><span>תל אביב · הכתובת המדויקת נשלחת אחרי קביעת התור</span></span></div>\n'
           '      <div class="ct-row"><span class="k">הגעה ונגישות</span><span class="v"><span>קומה שנייה בלי מעלית · חניה ברחוב · <a href="accessibility/">הצהרת נגישות</a></span></span></div>')

# ---------- opening hours: live from the booking system (this text shows until it loads) ----------
body = sub(body, '<span class="todo-txt">[ימים ושעות]</span>',
           '<span class="hours" id="hours"><span>ראשון עד חמישי, לפי השעות הפנויות <a href="book/">בדף התורים</a></span></span>')

# ---------- prices: the treatments come live from the booking system ----------
body = sub(body, '<div class="rows"><div class="row"><div class="row-t"><span class="nm">לק ג׳ל</span>',
           '<div class="rows" id="svcRows"><div class="row"><div class="row-t"><span class="nm">לק ג׳ל</span>')

# ---------- photos ----------
ABOUT_ALT = 'הידיים של ספיר: ציפורניים ארוכות בלבן חלבי עם פפיונים קטנים, ליד פרחים סגולים'
body = sub(body, '<div class="studio-photo ph"><span class="ph-l">תמונה: הסטודיו</span></div>',
           f'<div class="studio-photo ph has-img"><img src="img/sapir-720.jpg" srcset="img/sapir-720.jpg 720w, img/sapir-1200.jpg 1200w" sizes="(min-width:900px) 480px, 90vw" width="720" height="900" alt="{ABOUT_ALT}" loading="lazy" decoding="async"></div>')
WORKS = [  # file, aspect class, width x height of the small file, description
    ('w13', 'r-34', 640, 853, 'פרנץ׳ אדום על בסיס ניוד'),
    ('w01', 'r-11', 640, 640, 'ציפורניים ארוכות בלבן חלבי'),
    ('w12', 'r-34', 640, 853, 'ורוד עז, עם דוגמת נמר על שתי ציפורניים'),
    ('w03', 'r-34', 640, 853, 'עיצוב פסטל עם רוחות קטנות ונצנצים'),
    ('w04', 'r-11', 640, 640, 'ניוד עם נקודות לבנות על שחור'),
    ('w10', 'r-45', 640, 800, 'ציפורניים ארוכות בגוון קרם, ליד עציץ'),
    ('w02', 'r-11', 640, 640, 'לק ג׳ל אדום בוהק, ציפורניים מחודדות'),
    ('w06', 'r-34', 640, 853, 'פרנץ׳ לבן על בסיס ורוד'),
    ('w11', 'r-11', 640, 640, 'לבן חלבי עם פפיון קטן ופנינים'),
    ('w05', 'r-11', 640, 640, 'ורוד פוקסיה עם עיצוב שיש'),
    ('w07', 'r-34', 640, 853, 'נקודות בשחור ולבן'),
    ('w08', 'r-45', 640, 800, 'ניוד אפרסק טבעי'),
    ('w09', 'r-34', 640, 853, 'פרנץ׳ עדין בוורוד'),
]
for n, *_ in WORKS:
    for w in (640, 1080):
        assert (ROOT / f'img/{n}-{w}.jpg').exists(), f'missing img/{n}-{w}.jpg'
gal = ''.join(
    f'<figure class="gal-item"><button type="button" class="ph has-img {r} zoom" data-full="img/{n}-1080.jpg" aria-label="הגדלה: {alt}">'
    f'<img src="img/{n}-640.jpg" srcset="img/{n}-640.jpg 640w, img/{n}-1080.jpg 1080w" sizes="(min-width:760px) 33vw, 50vw" width="{w}" height="{h}" alt="{alt}" loading="lazy" decoding="async"></button></figure>'
    for n, r, w, h, alt in WORKS)
body, k = re.subn(r'<div class="gal">.*?</div></div></div>(?=\s*<div class="gal-more">)', f'<div class="gal">{gal}</div>', body, count=1, flags=re.S)
assert k == 1

# ---------- personal card link (#k...): book the next visit ----------
body = sub(body, """cta.innerHTML = `<a class="btn btn-rose" href="${WA}?text=${encodeURIComponent(full ? 'היי ספיר, הכרטיסייה שלי מלאה! אשמח לקבוע את טיפול המתנה' : 'היי ספיר, אשמח לקבוע תור')}" target="_blank" rel="noopener noreferrer">""",
           """cta.innerHTML = `<a class="btn btn-rose" href="book/${full ? '?gift=1' : ''}">""")

# ---------- studio policy: how to cancel, and the law comes first ----------
# the refund line, in the narrower wording Moshe approved on 15.11.2026 (the design file still has the sweeping one)
body = sub(body, 'לא יינתן החזר כספי מכל סיבה שהיא, מלבד ביטול שנעשה עד 24 שעות.',
           'המקדמה ודמי הביטול לא יוחזרו בביטול של פחות מ־24 שעות לפני התור.')
body = sub(body, '<span>בבקשה שמרו על התקנון</span></p></div>',
           '<span>בבקשה שמרו על התקנון</span></p></div>\n'
           f'      <p class="pol-legal">לביטול או שינוי תור כותבים לספיר <a href="{WA_CANCEL}" target="_blank" rel="noopener noreferrer">בוואטסאפ</a>. '
           'התקנון לא גורע מזכויות שמגיעות לך לפי חוק הגנת הצרכן. <a href="terms/">תנאי השימוש המלאים</a></p>')

# ---------- footer ----------
body = sub(body, '<div class="foot-links"><a href="#services">מחירון</a>', '<div class="foot-links"><a href="book/">קביעת תור</a><a href="#services">מחירון</a>')
body = sub(body, '<a class="logo" href="#top" dir="ltr">sapinails.il</a>', '<a class="logo" href="#top" dir="ltr" aria-label="sapinails.il, לראש הדף">sapinails.il</a>')
body = sub(body, '<span>© 2026 sapinails.il · כל הזכויות שמורות</span>\n  </div>',
           '<span>© 2026 sapinails.il · כל הזכויות שמורות</span>\n  </div>\n'
           '  <nav class="wrap foot-legal" aria-label="נגישות, פרטיות ותנאים"><a href="accessibility/">הצהרת נגישות</a><a href="privacy/">מדיניות פרטיות</a><a href="terms/">תנאי שימוש</a>'
           f'<a href="{WA_CANCEL}" target="_blank" rel="noopener noreferrer">ביטול או שינוי תור</a></nav>')

# ---------- keyboard and screen readers ----------
body = sub(body, '<div dir="rtl" lang="he" id="page">', '<a class="skip" href="#top">דילוג לתוכן הראשי</a>\n<div dir="rtl" lang="he" id="page">')
body = sub(body, '<main id="top">', '<main id="top" tabindex="-1">')
body = sub(body, '<div class="mnav" id="mnav" aria-hidden="true">', '<div class="mnav" id="mnav" role="dialog" aria-modal="true" aria-label="תפריט">')
body = sub(body, '</footer>\n\n</div>', '</footer>\n<div class="sr" id="live" role="status"></div>\n\n</div>')
# links that open a new window say so
html_part, script_part = body.split('<script>', 1)
html_part, n_new = re.subn(r'(<a\b[^>]*\btarget="_blank"[^>]*>)(.*?)</a>', lambda m: m.group(1) + m.group(2) + NEW_TAB + '</a>', html_part, flags=re.S)
assert n_new == 6, n_new
body = html_part + '<script>' + script_part

body = sub(body, "const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;",
           "const reduce = () => matchMedia('(prefers-reduced-motion: reduce)').matches || root.classList.contains('ax-still');")
body = sub(body, "behavior: reduce ? 'auto' : 'smooth'", "behavior: reduce() ? 'auto' : 'smooth'")

MENU_JS = r"""/* an open dialog (the menu, the photo viewer) keeps the keyboard inside it, and the page behind it is switched off */
const trapTab = (box, e) => {
  if (e.key !== 'Tab') return;
  const f = [...box.querySelectorAll('a[href],button:not([disabled])')].filter(n => n.getClientRects().length);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1], at = document.activeElement;
  if (e.shiftKey && (at === first || !box.contains(at))) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && (at === last || !box.contains(at))) { e.preventDefault(); first.focus(); }
};
const say = msg => { const r = $('#live'); r.textContent = ''; setTimeout(() => { r.textContent = msg; }, 60); };
const setMenu = (open, refocus = true) => {
  if (open === mnav.classList.contains('open')) return;
  mnav.classList.toggle('open', open);
  menuBtn.setAttribute('aria-expanded', String(open));
  [...mnav.parentElement.children].forEach(n => { if (n !== mnav) n.inert = open; });
  document.body.style.overflow = open ? 'hidden' : '';
  if (open) $('#menuClose').focus(); else if (refocus) menuBtn.focus();
};
menuBtn.addEventListener('click', () => setMenu(true));
$('#menuClose').addEventListener('click', () => setMenu(false));
mnav.querySelectorAll('a').forEach(a => a.addEventListener('click', () => setMenu(false, false)));
mnav.addEventListener('keydown', e => trapTab(mnav, e));
addEventListener('keydown', e => { if (e.key === 'Escape' && mnav.classList.contains('open')) setMenu(false); });
const wide = matchMedia('(min-width:900px)');
if (wide.addEventListener) wide.addEventListener('change', e => { if (e.matches) setMenu(false, false); });

"""
a, b = body.index('const setMenu = open => {'), body.index('/* copy phone */')
assert 0 < a < b and 'aria-hidden' in body[a:b]
body = body[:a] + MENU_JS + body[b:]
body = sub(body, "const done = msg => { const el = document.createElement('div'); el.className = 'toast'; el.textContent = msg; document.body.appendChild(el); setTimeout(() => el.remove(), 2200); };",
           "const done = msg => { const el = document.createElement('div'); el.className = 'toast'; el.setAttribute('aria-hidden', 'true'); el.textContent = msg; document.body.appendChild(el); setTimeout(() => el.remove(), 2600); say(msg); };")

# ---------- live prices & hours, photo viewer ----------
LIVE_JS = r"""
/* prices and opening hours, live from the booking system */
const CFG = window.SAPI || {};
const DAYS = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'];
const DESC = { gel: 'כולל מניקור', build: 'הארכה ועיצוב צורה', mani: 'ללא לק', remove: 'ג׳ל או בנייה' };
const escH = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function hoursHTML(hours) {
  const groups = [];
  for (let d = 0; d < 7; d++) {
    const k = (hours[String(d)] || []).map(w => `${w.from}–${w.to}`).join(', ');
    const g = groups[groups.length - 1];
    if (g && g.k === k) g.to = d; else groups.push({ from: d, to: d, k });
  }
  return groups.map(g => `<span><span class="d">${DAYS[g.from]}${g.to > g.from ? '–' + DAYS[g.to] : ''}</span> ${g.k ? `<span dir="ltr">${escH(g.k)}</span>` : '<span>סגור</span>'}</span>`).join('');
}
function priceRows(list) {
  return list.map(s => {
    const m = /^(.*?)\s*\(([^)]*)\)\s*$/.exec(s.name || '');
    const nm = m ? m[1] : s.name, ds = DESC[s.id] || (m ? m[2] : '');
    const pr = s.price == null ? '<span class="pr soft">לפי התאמה</span>' : `<span class="pr">${Number(s.price).toLocaleString('he-IL')}₪</span>`;
    return `<div class="row"><div class="row-t"><span class="nm">${escH(nm)}</span>${ds ? `<span class="ds">${escH(ds)}</span>` : ''}</div><span class="dots" aria-hidden="true"></span>${pr}</div>`;
  }).join('');
}
/* a screen reader hears each price list as a list */
const listRoles = () => document.querySelectorAll('.rows').forEach(r => { r.setAttribute('role', 'list'); [...r.children].forEach(c => c.setAttribute('role', 'listitem')); });
listRoles();
if (CFG.url && CFG.key) {
  fetch(CFG.url + '/rest/v1/rpc/public_info', { method: 'POST', headers: { apikey: CFG.key, 'Content-Type': 'application/json' }, body: '{}' })
    .then(r => (r.ok ? r.json() : null))
    .then(info => {
      if (!info) return;
      if (Array.isArray(info.services) && info.services.length) { $('#svcRows').innerHTML = priceRows(info.services); listRoles(); }
      const h = info.settings && info.settings.hours;
      if (h && Object.keys(h).length) $('#hours').innerHTML = hoursHTML(h);
    })
    .catch(() => {});
}

/* photo viewer */
const zooms = [...document.querySelectorAll('.zoom')];
if (zooms.length) {
  const lb = document.createElement('div');
  lb.className = 'lb'; lb.hidden = true;
  lb.setAttribute('role', 'dialog'); lb.setAttribute('aria-modal', 'true'); lb.setAttribute('aria-label', 'תמונה מוגדלת');
  lb.innerHTML = '<img alt=""><p class="sr" role="status"></p><button type="button" class="lb-x" aria-label="סגירה"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>'
    + '<button type="button" class="lb-nav lb-prev" aria-label="התמונה הקודמת"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg></button>'
    + '<button type="button" class="lb-nav lb-next" aria-label="התמונה הבאה"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg></button>';
  document.body.appendChild(lb);
  const img = lb.querySelector('img'), status = lb.querySelector('[role="status"]');
  let cur = 0, back = null, x0 = null;
  const show = i => {
    cur = (i + zooms.length) % zooms.length;
    const b = zooms[cur];
    img.src = b.dataset.full; img.alt = b.querySelector('img').alt;
    status.textContent = `תמונה ${cur + 1} מתוך ${zooms.length}: ${img.alt}`;
  };
  const rest = on => [...document.body.children].forEach(n => { if (n !== lb && n.tagName !== 'SCRIPT') n.inert = on; });
  const open = i => { back = document.activeElement; show(i); lb.hidden = false; rest(true); document.body.style.overflow = 'hidden'; lb.querySelector('.lb-x').focus(); };
  const close = () => { lb.hidden = true; img.removeAttribute('src'); rest(false); document.body.style.overflow = ''; if (back) back.focus(); };
  zooms.forEach((b, i) => b.addEventListener('click', () => open(i)));
  lb.addEventListener('click', e => {
    if (e.target.closest('.lb-prev')) show(cur - 1);
    else if (e.target.closest('.lb-next')) show(cur + 1);
    else close();
  });
  lb.addEventListener('keydown', e => trapTab(lb, e));
  addEventListener('keydown', e => {
    if (lb.hidden) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft') show(cur + 1);
    else if (e.key === 'ArrowRight') show(cur - 1);
  });
  lb.addEventListener('touchstart', e => { x0 = e.touches[0].clientX; }, { passive: true });
  lb.addEventListener('touchend', e => {
    if (x0 == null) return;
    const dx = e.changedTouches[0].clientX - x0; x0 = null;
    if (Math.abs(dx) > 50) { e.preventDefault(); show(dx > 0 ? cur + 1 : cur - 1); }
  });
}
"""
body = sub(body, "renderClub(!!parseToken(location.hash));", LIVE_JS + "\nrenderClub(!!parseToken(location.hash));")
body = sub(body, '<script>\n(() => {', '<script src="assets/config.js?v=1"></script>\n<script>\n(() => {')

EXTRA_CSS = """
<style>
/* public site additions: photos, live hours, photo viewer */
.ph.has-img{background:#EED3DC}
.ph.has-img::before{display:none}
.zoom{display:grid;width:100%;padding:0;border:0;border-radius:inherit;cursor:zoom-in}
.zoom img{transition:transform .35s ease}
@media (hover:hover){.zoom:hover img{transform:scale(1.03)}}
.zoom:focus-visible{outline:4px solid #fff;outline-offset:-4px}
.gal-item:has(.zoom:focus-visible){outline:3px solid var(--rose-ink);outline-offset:3px}
.gal-item{margin-inline:0;margin-top:0}
.hours{display:flex;flex-direction:column;gap:2px;font-weight:700}
.hours .d{display:inline-block;min-width:8.5em;font-weight:600;color:var(--ink-2)}
.hours a{color:var(--rose-ink)}
.lb{position:fixed;inset:0;z-index:80;background:rgba(36,20,28,.94);display:grid;place-items:center;padding:calc(56px + env(safe-area-inset-top,0px)) 12px calc(56px + env(safe-area-inset-bottom,0px))}
.lb[hidden]{display:none}
.lb img{max-width:min(94vw,900px);max-height:100%;width:auto;height:auto;border-radius:18px;box-shadow:0 30px 60px -20px rgba(0,0,0,.6)}
.lb button{position:absolute;display:grid;place-items:center;width:48px;height:48px;border-radius:50%;border:0;background:rgba(255,255,255,.14);color:#fff}
.lb button:focus-visible{outline-color:#fff}
.lb button svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.lb-x{top:calc(12px + env(safe-area-inset-top,0px));left:12px}
.lb-nav{top:50%;transform:translateY(-50%)}
.lb-prev{right:10px}.lb-next{left:10px}
@media (max-width:759px){.lb-nav{top:auto;bottom:calc(12px + env(safe-area-inset-bottom,0px));transform:none}}

/* accessibility: what is hidden is really hidden, links look like links, the footer leaves room for the floating button */
main:focus{outline:none}
.hdr .logo{transition:opacity .3s,visibility 0s}
.hdr:not(.solid) .logo{visibility:hidden;transition:opacity .3s,visibility 0s .3s}
.mnav{visibility:hidden;transition:opacity .25s,transform .25s,visibility 0s .25s}
.mnav.open{visibility:visible;transition:opacity .25s,transform .25s,visibility 0s}
.phone{text-decoration:underline;text-decoration-thickness:1.5px;text-underline-offset:4px}
.ct-row .v a{color:var(--rose-ink);font-weight:700;text-underline-offset:3px}
.pol-legal{margin:0;text-align:center;font-size:15.5px;line-height:1.6;color:var(--ink-2);text-wrap:balance}
.pol-legal a{color:var(--rose-ink);font-weight:700;text-underline-offset:3px}
/* the punch card may not push its section wider than the screen */
@media (max-width:959px){.club{grid-template-columns:minmax(0,1fr)}}
@media (min-width:960px){.club{grid-template-columns:minmax(0,1.05fr) minmax(0,1fr)}}
@media (max-width:379px){.nails{gap:10px 7px}.nails .nail{width:30px;height:41px}}
.foot{padding-bottom:calc(84px + env(safe-area-inset-bottom,0px))}
.foot-legal{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:18px;padding-top:16px;border-top:1px solid var(--line);font-size:15px;color:var(--ink-2)}
.foot-legal a{font-weight:700;text-underline-offset:3px}
</style>"""

HEAD = f"""<!doctype html>
<html lang="he" dir="rtl" data-full-site>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>sapinails.il · ציפורניים בקליניקה פרטית בתל אביב</title>
<meta name="description" content="לק ג׳ל, בנייה, מניקור ועיצובים בקליניקה פרטית בתל אביב. מחירון, עבודות, כרטיסיית מועדון וקביעת תור אונליין.">
<meta name="theme-color" content="#F7DAE2">
<meta property="og:type" content="website">
<meta property="og:site_name" content="sapinails.il">
<meta property="og:locale" content="he_IL">
<meta property="og:title" content="sapinails.il 💅">
<meta property="og:description" content="לק ג׳ל, בנייה ומניקור בקליניקה פרטית בתל אביב. קביעת תור אונליין.">
<meta property="og:url" content="https://kgbg-3.github.io/sapinails/">
<meta property="og:image" content="https://kgbg-3.github.io/sapinails/og/home.jpg?v=2">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="admin/icon-180.png">
<link rel="preload" href="assets/fonts/assistant-hebrew.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="assets/fonts/frank-ruhl-libre-500-hebrew.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="assets/fonts/ms-madi-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="assets/fonts.css?v={VER}">
"""
TAIL_HEAD = f"""
<link rel="stylesheet" href="assets/site.css?v={VER}">
<script src="assets/site.js?v={VER}"></script>
</head>
<body>
"""

page = HEAD + css + EXTRA_CSS + TAIL_HEAD + body + '\n</body>\n</html>\n'
assert 'fonts.googleapis' not in page and 'fonts.gstatic' not in page
assert 'img/about-' not in page
(ROOT / 'index.html').write_text(page, encoding='utf-8')
print('wrote index.html', len(page) // 1024, 'KB')
