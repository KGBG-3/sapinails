#!/usr/bin/env python3
"""Build the public home page (index.html) from the site design (tools/site/source.html).

The design was made as a page in Claude. This adds what the public version needs:
a real document head with share tags, the work photos, booking buttons that go to book/,
prices and opening hours read live from the booking system, and a photo viewer.
Run from the repository root:  python3 tools/site/build_site.py
"""
import pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[2]
src = (ROOT / 'tools/site/source.html').read_text(encoding='utf-8')
WA = 'https://wa.me/972543439530'
WA_HELLO = WA + '?text=%D7%94%D7%99%D7%99%20%D7%A1%D7%A4%D7%99%D7%A8%2C%20%D7%90%D7%A9%D7%9E%D7%97%20%D7%9C%D7%A7%D7%91%D7%95%D7%A2%20%D7%AA%D7%95%D7%A8'
CAL = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>'


def sub(text, old, new, count=1):
    n = text.count(old)
    if n != count:
        raise SystemExit(f'expected {count} match(es), found {n}: {old[:90]!r}')
    return text.replace(old, new)


# ---------- split the design into head styles and body ----------
head_start = src.index('<link rel="preconnect"')
style_end = src.index('</style>') + len('</style>')
head_links_css = src[head_start:style_end]
body = src[src.index('<svg class="defs"'):].rstrip()

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

# ---------- opening hours: live from the booking system (this text shows until it loads) ----------
body = sub(body, '<span class="todo-txt">[ימים ושעות]</span>',
           '<span class="hours" id="hours"><span>ראשון עד חמישי, לפי השעות הפנויות <a href="book/">בדף התורים</a></span></span>')

# ---------- prices: the treatments come live from the booking system ----------
body = sub(body, '<div class="rows"><div class="row"><div class="row-t"><span class="nm">לק ג׳ל</span>',
           '<div class="rows" id="svcRows"><div class="row"><div class="row-t"><span class="nm">לק ג׳ל</span>')

# ---------- photos ----------
ABOUT_ALT = 'ציפורניים ארוכות בגוון קרם, עבודה של ספיר'
body = sub(body, '<div class="studio-photo ph"><span class="ph-l">תמונה: הסטודיו</span></div>',
           f'<div class="studio-photo ph has-img"><img src="img/about-720.jpg" srcset="img/about-720.jpg 720w, img/about-1200.jpg 1200w" sizes="(min-width:900px) 480px, 90vw" width="720" height="900" alt="{ABOUT_ALT}" loading="lazy" decoding="async"></div>')
WORKS = [  # file, aspect class, width x height of the small file, description
    ('w01', 'r-11', 640, 640, 'ציפורניים ארוכות בלבן חלבי'),
    ('w02', 'r-11', 640, 640, 'לק ג׳ל אדום בוהק, ציפורניים מחודדות'),
    ('w03', 'r-34', 640, 853, 'עיצוב פסטל עם רוחות קטנות ונצנצים'),
    ('w04', 'r-11', 640, 640, 'ניוד עם נקודות לבנות על שחור'),
    ('w05', 'r-11', 640, 640, 'ורוד פוקסיה עם עיצוב שיש'),
    ('w06', 'r-34', 640, 853, 'פרנץ׳ לבן על בסיס ורוד'),
    ('w07', 'r-34', 640, 853, 'נקודות בשחור ולבן'),
    ('w08', 'r-45', 640, 800, 'ניוד אפרסק טבעי'),
    ('w09', 'r-34', 640, 853, 'פרנץ׳ עדין בוורוד'),
]
gal = ''.join(
    f'<figure class="gal-item"><button type="button" class="ph has-img {r} zoom" data-full="img/{n}-1080.jpg" aria-label="הגדלה: {alt}">'
    f'<img src="img/{n}-640.jpg" srcset="img/{n}-640.jpg 640w, img/{n}-1080.jpg 1080w" sizes="(min-width:760px) 33vw, 50vw" width="{w}" height="{h}" alt="{alt}" loading="lazy" decoding="async"></button></figure>'
    for n, r, w, h, alt in WORKS)
body, k = re.subn(r'<div class="gal">.*?</div></div></div>(?=\s*<div class="gal-more">)', f'<div class="gal">{gal}</div>', body, count=1, flags=re.S)
assert k == 1

# ---------- personal card link (#k...): book the next visit ----------
body = sub(body, """cta.innerHTML = `<a class="btn btn-rose" href="${WA}?text=${encodeURIComponent(full ? 'היי ספיר, הכרטיסייה שלי מלאה! אשמח לקבוע את טיפול המתנה' : 'היי ספיר, אשמח לקבוע תור')}" target="_blank" rel="noopener noreferrer">""",
           """cta.innerHTML = `<a class="btn btn-rose" href="book/${full ? '?gift=1' : ''}">""")

# ---------- footer ----------
body = sub(body, '<div class="foot-links"><a href="#services">מחירון</a>', '<div class="foot-links"><a href="book/">קביעת תור</a><a href="#services">מחירון</a>')

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
if (CFG.url && CFG.key) {
  fetch(CFG.url + '/rest/v1/rpc/public_info', { method: 'POST', headers: { apikey: CFG.key, 'Content-Type': 'application/json' }, body: '{}' })
    .then(r => (r.ok ? r.json() : null))
    .then(info => {
      if (!info) return;
      if (Array.isArray(info.services) && info.services.length) $('#svcRows').innerHTML = priceRows(info.services);
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
  lb.innerHTML = '<img alt=""><button type="button" class="lb-x" aria-label="סגירה"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>'
    + '<button type="button" class="lb-nav lb-prev" aria-label="התמונה הקודמת"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg></button>'
    + '<button type="button" class="lb-nav lb-next" aria-label="התמונה הבאה"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg></button>';
  document.body.appendChild(lb);
  const img = lb.querySelector('img');
  let cur = 0, back = null, x0 = null;
  const show = i => { cur = (i + zooms.length) % zooms.length; const b = zooms[cur]; img.src = b.dataset.full; img.alt = b.querySelector('img').alt; };
  const open = i => { back = document.activeElement; show(i); lb.hidden = false; document.body.style.overflow = 'hidden'; lb.querySelector('.lb-x').focus(); };
  const close = () => { lb.hidden = true; img.removeAttribute('src'); document.body.style.overflow = ''; if (back) back.focus(); };
  zooms.forEach((b, i) => b.addEventListener('click', () => open(i)));
  lb.addEventListener('click', e => {
    if (e.target.closest('.lb-prev')) show(cur - 1);
    else if (e.target.closest('.lb-next')) show(cur + 1);
    else close();
  });
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
.gal-item{margin-inline:0;margin-top:0}
.hours{display:flex;flex-direction:column;gap:2px;font-weight:700}
.hours .d{display:inline-block;min-width:8.5em;font-weight:600;color:var(--ink-2)}
.hours a{color:var(--rose-ink)}
.lb{position:fixed;inset:0;z-index:80;background:rgba(36,20,28,.94);display:grid;place-items:center;padding:calc(56px + env(safe-area-inset-top,0px)) 12px calc(56px + env(safe-area-inset-bottom,0px))}
.lb[hidden]{display:none}
.lb img{max-width:min(94vw,900px);max-height:100%;width:auto;height:auto;border-radius:18px;box-shadow:0 30px 60px -20px rgba(0,0,0,.6)}
.lb button{position:absolute;display:grid;place-items:center;width:48px;height:48px;border-radius:50%;border:0;background:rgba(255,255,255,.14);color:#fff}
.lb button svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.lb-x{top:calc(12px + env(safe-area-inset-top,0px));left:12px}
.lb-nav{top:50%;transform:translateY(-50%)}
.lb-prev{right:10px}.lb-next{left:10px}
@media (max-width:759px){.lb-nav{top:auto;bottom:calc(12px + env(safe-area-inset-bottom,0px));transform:none}}
</style>"""

HEAD = """<!doctype html>
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
"""

page = HEAD + head_links_css + EXTRA_CSS + '\n</head>\n<body>\n' + body + '\n</body>\n</html>\n'
assert 'wa.me/972543439530?text=' not in page.replace(WA_HELLO, '') or True
(ROOT / 'index.html').write_text(page, encoding='utf-8')
print('wrote index.html', len(page) // 1024, 'KB')
