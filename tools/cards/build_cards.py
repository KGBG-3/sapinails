#!/usr/bin/env python3
"""Build the public card pages + WhatsApp preview images for sapinails.il.

usage: python3 build_cards.py <app.html> <site.html> <out_dir> <fonts_dir> <base_url> [--no-images]

Writes, for every card size N (3..12) and punch count p (0..N):
  out/k/{N}/{p}/index.html   page the client opens (og tags point to the image)
  out/og/{N}-{p}.jpg         1200x630 card image WhatsApp shows inside the message
plus out/index.html, out/assets/*, out/favicon.svg, out/.nojekyll
"""
import sys, re, glob, math, html, pathlib, urllib.parse, io

APP, SITE, OUT, FONTS, BASE = sys.argv[1:6]
NO_IMAGES = '--no-images' in sys.argv
BASE = BASE.rstrip('/')
OUT = pathlib.Path(OUT)
VER = '2'
WA_NUM = '972543439530'
IG = 'https://www.instagram.com/sapinails.il/'
SIZES = range(3, 13)

app = pathlib.Path(APP).read_text(encoding='utf-8')
site = pathlib.Path(SITE).read_text(encoding='utf-8')


def js_const(name):
    m = re.search(r"^const %s = '(.*)';$" % name, app, re.M)
    if not m:
        raise SystemExit('missing ' + name)
    return m.group(1)


ROSE_CARD = js_const('ROSE_SVG')       # line-art rose in the card corner (fill=currentColor)
MARK_SVG = js_const('MARK_SVG')        # marker swipe behind "כרטיסיית מועדון"
NAIL = js_const('NAIL')
SHINE = js_const('SHINE')
SPARK = js_const('SPARK')
STOPS = re.search(r"^const STOPS = \[(.*)\];$", app, re.M).group(1)
STOPS = re.findall(r"'(#[0-9A-Fa-f]{6})'", STOPS)


def site_symbol(sym_id):
    """Inner markup of <g id="sym_id"> from the site's rose defs."""
    start = site.index('<g id="%s">' % sym_id)
    i, depth = start, 0
    tag = re.compile(r'<(/?)g\b[^>]*?(/?)>')
    for m in tag.finditer(site, start):
        if m.group(1):
            depth -= 1
        elif not m.group(2):
            depth += 1
        if depth == 0:
            return site[start + len('<g id="%s">' % sym_id):m.start()]
    raise SystemExit('unclosed ' + sym_id)


def standalone_svg(inner, viewbox, fill):
    inner = inner.replace('currentColor', fill)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">{inner}</svg>'


# ---------- card markup (mirrors the app's nailRow / pcardHTML) ----------
def js_round(v):
    return math.floor(v + 0.5)


def shade(i, N):
    t = 1 if N <= 1 else i / (N - 1)
    x = t * (len(STOPS) - 1)
    k = min(len(STOPS) - 2, math.floor(x))
    f = x - k
    a = [int(STOPS[k][j:j + 2], 16) for j in (1, 3, 5)]
    b = [int(STOPS[k + 1][j:j + 2], 16) for j in (1, 3, 5)]
    return '#' + ''.join('%02x' % js_round(av + (bv - av) * f) for av, bv in zip(a, b))


def nail(kind, color=None, n=None):
    if kind == 'full':
        return (f'<svg class="nail" viewBox="0 0 32 44" aria-hidden="true"><path class="edge" d="{NAIL}" style="fill:{color}"/>'
                f'<path d="{SHINE}" fill="#fff" opacity=".5"/><ellipse cx="12.6" cy="8.8" rx="1" ry="1.6" fill="#fff" opacity=".55"/></svg>')
    if kind == 'empty':
        num = f'<text class="num" x="16" y="29.5">{n}</text>' if n else ''
        return f'<svg class="nail" viewBox="0 0 32 44" aria-hidden="true"><path class="slot" d="{NAIL}"/>{num}</svg>'
    if kind == 'gift-on':
        return (f'<svg class="nail gift-ready" viewBox="0 0 32 44" aria-hidden="true"><path class="edge" d="{NAIL}" fill="url(#chrome)"/>'
                f'<path d="{SHINE}" fill="#fff" opacity=".75"/><path class="spark-on" d="{SPARK}"/></svg>')
    return f'<svg class="nail" viewBox="0 0 32 44" aria-hidden="true"><path class="slot" d="{NAIL}"/><path class="spark-off" d="{SPARK}"/></svg>'


def nails_inner(p, N):
    f = min(p, N)
    out = ''.join(nail('full', color=shade(i, N)) if i < f else nail('empty', n=i + 1) for i in range(N))
    return out + nail('gift-on' if p >= N else 'gift-off')


def nails_label(p, N):
    return f'הכרטיסייה מלאה, {N} מתוך {N}' if p >= N else f'{min(p, N)} מתוך {N} ניקובים'


def left_txt(left):
    return 'טיפול אחד' if left == 1 else f'{left} טיפולים'


def card_status(p, N):
    f, left = min(p, N), N - min(p, N)
    if p >= N:
        return '<b>הכרטיסייה מלאה</b> · הטיפול הבא מתנה'
    if p <= 0:
        return f'כרטיסייה חדשה · {N} טיפולים עד המתנה'
    return f'<b>{f} מתוך {N}</b> · עוד {left_txt(left)} עד טיפול מתנה'


ORD = {4: 'הרביעי', 5: 'החמישי', 6: 'השישי', 7: 'השביעי', 8: 'השמיני', 9: 'התשיעי', 10: 'העשירי'}


def ordinal(n):
    return ORD.get(n, f'ה-{n}')


CHROME_DEFS = ('<svg class="defs" aria-hidden="true" focusable="false"><defs><linearGradient id="chrome" x1="0" y1="0" x2="1" y2="1">'
               '<stop offset="0" stop-color="#FCF1F5"/><stop offset=".32" stop-color="#E7C3D2"/><stop offset=".56" stop-color="#F8E8D5"/>'
               '<stop offset=".8" stop-color="#D8B2C5"/><stop offset="1" stop-color="#F5E1EA"/></linearGradient></defs></svg>')

# ---------- texts per state ----------
def texts(p, N):
    f, left, full = min(p, N), N - min(p, N), p >= N
    if full:
        return dict(
            og_title='הכרטיסייה שלך מלאה! 🎉',
            og_desc='הטיפול הבא שלך מתנה ממני 🎁',
            head='הכרטיסייה מלאה!',
            sub='הטיפול הבא שלך מתנה ממני',
            cta='לקביעת טיפול המתנה',
            wa='היי ספיר, הכרטיסייה שלי מלאה! אשמח לקבוע את טיפול המתנה',
            tab=f'הכרטיסייה מלאה · sapinails.il')
    if p <= 0:
        return dict(
            og_title='כרטיסיית המועדון שלך 💅',
            og_desc=f'{N} טיפולים, והטיפול {ordinal(N + 1)} מתנה ממני 🎁',
            head='כרטיסייה חדשה',
            sub='הניקוב הראשון מחכה לך בטיפול הבא',
            cta='לקביעת התור הבא',
            wa='היי ספיר, אשמח לקבוע תור',
            tab='כרטיסייה חדשה · sapinails.il')
    return dict(
        og_title=f'{f} מתוך {N} · כרטיסיית המועדון שלך 💅',
        og_desc=f'עוד {left_txt(left)} עד טיפול מתנה 🎁',
        head=f'עוד {left_txt(left)}<br>עד טיפול מתנה',
        sub=f'{f} מתוך {N} ניקובים בכרטיסייה' + (', כמעט שם!' if left == 1 else ''),
        cta='לקביעת התור הבא',
        wa='היי ספיר, אשמח לקבוע תור',
        tab=f'{f} מתוך {N} · sapinails.il')


# ---------- page ----------
FONTS_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
              '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800'
              '&amp;family=Frank+Ruhl+Libre:wght@500&amp;family=Playpen+Sans+Hebrew&amp;family=Ms+Madi&amp;display=swap">')

WA_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11.6a8 8 0 0 1-11.7 7.1L4 20l1.3-4A8 8 0 1 1 20 11.6Z"/>'
           '<path d="M9 10.5h6M9 13.5h4"/></svg>')
CAL_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15.5" rx="3"/>'
            '<path d="M3.5 10h17M8 3v4M16 3v4"/></svg>')
IG_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="5"/>'
           '<circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r=".6" fill="currentColor"/></svg>')


def esc(s):
    return html.escape(s, quote=True)


def card_html(p, N, root):
    total, full = N + 1, p >= N
    cols = total if total <= 7 else math.ceil(total / 2)
    return f'''<article class="pcard{' is-full' if full else ''}">
    <img class="pc-rose" src="{root}assets/rose-card.svg?v={VER}" alt="" width="136" height="136">
    <div class="pcard-top"><div><div class="pcard-eyebrow">{MARK_SVG}<span>כרטיסיית מועדון</span></div><div class="pcard-studio" dir="ltr">sapinails.il</div></div></div>
    <div class="nails big{' dense' if total > 7 else ''}" role="img" aria-label="{nails_label(p, N)}" style="grid-template-columns:repeat({cols},auto)">{nails_inner(p, N)}</div>
    <div class="pcard-foot"><div class="pcard-who"><div class="pcard-name">הכרטיסייה שלך</div><div class="pcard-status">{card_status(p, N)}</div></div><div class="pcard-no" id="cardNo" hidden></div></div>
  </article>'''


def page_html(p, N):
    t, root = texts(p, N), '../../../'
    url = f'{BASE}/k/{N}/{p}/'
    img = f'{BASE}/og/{N}-{p}.jpg?v={VER}'
    wa = f'https://wa.me/{WA_NUM}?text=' + urllib.parse.quote(t['wa'])
    alt = f'כרטיסיית מועדון sapinails.il: {nails_label(p, N)}'
    return f'''<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(t['tab'])}</title>
<meta name="description" content="{esc(t['og_desc'])}">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#FAE9EE">
<meta property="og:type" content="website">
<meta property="og:site_name" content="sapinails.il">
<meta property="og:locale" content="he_IL">
<meta property="og:title" content="{esc(t['og_title'])}">
<meta property="og:description" content="{esc(t['og_desc'])}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img}">
<meta property="og:image:secure_url" content="{img}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(alt)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
{FONTS_LINK}
<link rel="stylesheet" href="{root}assets/card.css?v={VER}">
</head>
<body>
{CHROME_DEFS}
<div class="decos" aria-hidden="true"><img class="deco deco-a" src="{root}assets/rose.svg?v={VER}" alt="" width="173" height="132"><img class="deco deco-b" src="{root}assets/stem.svg?v={VER}" alt="" width="287" height="154"></div>
<main class="page">
  <header class="intro">
    <p class="kicker">כרטיסיית המועדון שלך</p>
    <h1 class="title">{t['head']}</h1>
    <p class="sub">{t['sub']}</p>
  </header>
  {card_html(p, N, root)}
  <div class="actions">
    <a class="btn primary" href="{root}book/{'?gift=1' if p >= N else ''}">{CAL_ICON}<span>{t['cta']}</span></a>
    <a class="btn line" href="{IG}" target="_blank" rel="noopener">{IG_ICON}<span>העבודות שלי באינסטגרם</span></a>
    <a class="small-link" href="{esc(wa)}" target="_blank" rel="noopener">שאלה? וואטסאפ לספיר</a>
  </div>
  <section class="how" aria-labelledby="how-h">
    <h2 id="how-h">איך זה עובד</h2>
    <ol>
      <li><b>1</b><span>על כל טיפול נוסף ניקוב בכרטיסייה.</span></li>
      <li><b>2</b><span>אחרי {N} טיפולים הכרטיסייה מתמלאת.</span></li>
      <li><b>3</b><span>הטיפול {ordinal(N + 1)} מתנה ממני, ואז מתחילים כרטיסייה חדשה.</span></li>
    </ol>
  </section>
  <footer class="foot"><span dir="ltr">sapinails.il</span></footer>
</main>
<script>
(function () {{
  var c = parseInt(new URLSearchParams(location.search).get('c'), 10), el = document.getElementById('cardNo');
  if (el && c > 0 && c < 1000) {{ el.textContent = 'כרטיסייה מס׳ ' + c; el.hidden = false; }}
}})();
</script>
</body>
</html>
'''


def home_html():
    wa = f'https://wa.me/{WA_NUM}?text=' + urllib.parse.quote('היי ספיר, אשמח לקבוע תור')
    img = f'{BASE}/og/home.jpg?v={VER}'
    return f'''<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>sapinails.il · ציפורניים בקליניקה פרטית</title>
<meta name="description" content="ציפורניים מטופחות, בקליניקה פרטית. לקביעת תור בוואטסאפ.">
<meta name="theme-color" content="#FAE9EE">
<meta property="og:type" content="website">
<meta property="og:site_name" content="sapinails.il">
<meta property="og:locale" content="he_IL">
<meta property="og:title" content="sapinails.il 💅">
<meta property="og:description" content="ציפורניים מטופחות, בקליניקה פרטית. לקביעת תור בוואטסאפ.">
<meta property="og:url" content="{BASE}/">
<meta property="og:image" content="{img}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
{FONTS_LINK}
<link rel="stylesheet" href="assets/card.css?v={VER}">
</head>
<body class="home">
<div class="decos" aria-hidden="true"><img class="deco deco-a" src="assets/rose.svg?v={VER}" alt="" width="173" height="132"><img class="deco deco-b" src="assets/stem.svg?v={VER}" alt="" width="287" height="154"></div>
<main class="page">
  <header class="intro">
    <p class="brand" dir="ltr">sapinails.il</p>
    <h1 class="title">ציפורניים מטופחות,<br>בקליניקה פרטית</h1>
  </header>
  <div class="actions">
    <a class="btn primary" href="book/">{CAL_ICON}<span>לקביעת תור</span></a>
    <a class="btn line" href="{IG}" target="_blank" rel="noopener">{IG_ICON}<span>העבודות שלי באינסטגרם</span></a>
    <a class="small-link" href="{esc(wa)}" target="_blank" rel="noopener">שאלה? וואטסאפ לספיר</a>
  </div>
</main>
</body>
</html>
'''


CSS = r''':root{
  --bg:#FAE9EE;--surface:#FFFAFB;--ink:#2E1D24;--ink-2:#7D5566;--ink-3:#A48D98;
  --line:#F0D7E0;--line-strong:#E5C1CE;
  --accent:#BE4B74;--accent-hover:#A63D63;--accent-soft:#F8DCE6;
  --card-flat:#F7DAE2;--sheen:rgba(255,255,255,.38);--marker:#D9809F;
  --nail-empty-fill:rgba(255,255,255,.6);--nail-empty-stroke:#D9AFBF;--nail-edge:rgba(90,25,50,.2);
  --shadow-md:0 18px 36px -18px rgba(190,75,116,.35),0 3px 8px rgba(120,40,70,.06);
  --font-display:"Frank Ruhl Libre","David Libre",David,Georgia,serif;
  --font-hand:"Playpen Sans Hebrew","Assistant",cursive;
  --font-script:"Ms Madi","Mrs Saint Delafield",cursive;
  --font-ui:"Assistant","Heebo","Arial Hebrew","Segoe UI",Arial,sans-serif;
  color-scheme:light;
}
*,*::before,*::after{box-sizing:border-box}
[hidden]{display:none!important}
html{background:var(--bg);-webkit-text-size-adjust:100%}
body{margin:0;min-height:100vh;min-height:100dvh;position:relative;background:var(--bg);color:var(--ink);font-family:var(--font-ui);font-size:16px;line-height:1.5;-webkit-font-smoothing:antialiased}
svg{display:block}
img{display:block;max-width:100%}
a{color:inherit}
:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
.defs{position:absolute;width:0;height:0;overflow:hidden}

/* corner roses, like the site */
.decos{position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:0}
.deco{position:absolute;height:auto;opacity:.9}
.deco-a{width:150px;right:-46px;top:-30px;transform:rotate(-12deg)}
.deco-b{width:150px;left:-40px;bottom:-34px;transform:rotate(-58deg)}

.page{position:relative;z-index:1;max-width:460px;margin:0 auto;padding:calc(34px + env(safe-area-inset-top,0px)) 16px calc(34px + env(safe-area-inset-bottom,0px));display:flex;flex-direction:column;gap:22px}

.intro{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px}
.kicker{margin:0;font-size:13px;font-weight:800;letter-spacing:.08em;color:var(--accent)}
.title{margin:0;font-family:var(--font-display);font-weight:500;font-size:clamp(34px,10vw,42px);line-height:1.08;color:var(--accent);text-wrap:balance}
.sub{margin:0;font-size:17px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.brand{margin:0;font-family:var(--font-script);font-size:64px;line-height:1;color:var(--accent)}

/* the punch card (same look as Sapir's app) */
.pcard{position:relative;overflow:hidden;border-radius:24px;padding:18px;color:var(--ink);background:var(--card-flat);border:1px solid var(--line);box-shadow:var(--shadow-md)}
.pc-rose{position:absolute;left:-4px;top:-18px;width:136px;height:136px;pointer-events:none}
.pcard::after{content:"";position:absolute;top:-60%;inset-inline-end:-25%;width:75%;height:190%;background:linear-gradient(105deg,transparent 35%,var(--sheen) 50%,transparent 64%);transform:rotate(10deg);pointer-events:none}
.pcard.is-full{box-shadow:0 0 0 1.5px rgba(196,150,112,.55),var(--shadow-md)}
.pcard-top{position:relative;z-index:1;display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.pcard-eyebrow{position:relative;isolation:isolate;display:inline-block;padding:3px 16px 7px;font-family:var(--font-display);font-weight:500;font-size:19px;line-height:1.15}
.pcard-eyebrow svg{position:absolute;left:0;top:0;width:100%;height:100%;z-index:-1}
.pcard-eyebrow .mk{fill:var(--marker)}
.pcard-studio{font-family:var(--font-script);font-size:34px;line-height:1.05;color:var(--accent);margin:2px 6px 0 0}
.pcard-foot{position:relative;z-index:1;display:flex;align-items:flex-end;justify-content:space-between;gap:8px 12px;flex-wrap:wrap}
.pcard-who{min-width:0}
.pcard-name{font-family:var(--font-hand);font-weight:400;font-size:27px;line-height:1.2}
.pcard-status{margin-top:5px;font-size:14.5px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.pcard-status b{color:var(--ink);font-weight:800}
.pcard-no{flex:none;font-size:12px;font-weight:800;color:var(--ink-2);background:var(--card-flat);border:1px solid var(--line-strong);border-radius:999px;padding:3px 10px;white-space:nowrap;font-variant-numeric:tabular-nums}
.pcard-no[hidden]{display:none}

.nails{position:relative;z-index:1;display:grid;justify-content:center;align-items:end;gap:10px 9px;margin-block:16px 18px}
.nails .nail{width:34px;height:47px}
.nails.dense .nail{width:29px;height:40px}
.nail .slot{fill:var(--nail-empty-fill);stroke:var(--nail-empty-stroke);stroke-width:1.3;stroke-dasharray:3.2 2.6}
.nail .edge{stroke:var(--nail-edge);stroke-width:1}
.nail .num{font-family:var(--font-ui);font-size:10.5px;font-weight:800;fill:var(--ink-3);text-anchor:middle}
.nail .spark-off{fill:none;stroke:var(--nail-empty-stroke);stroke-width:1.2;stroke-linejoin:round}
.nail .spark-on{fill:#fff;stroke:#BF946B;stroke-width:.8;stroke-linejoin:round;transform-box:fill-box;transform-origin:center}
.nail.gift-ready .spark-on{animation:twinkle 2.8s ease-in-out infinite}
@keyframes twinkle{0%,100%{transform:scale(1)}50%{transform:scale(1.22)}}

/* actions */
.actions{display:flex;flex-direction:column;gap:10px}
.btn{display:flex;align-items:center;justify-content:center;gap:10px;min-height:56px;padding:0 22px;border-radius:999px;border:1.5px solid transparent;font-weight:800;font-size:17.5px;line-height:1.1;text-decoration:none;transition:background-color .15s,border-color .15s,transform .1s}
.btn:active{transform:scale(.98)}
.btn svg{width:22px;height:22px;flex:none;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.btn.primary{background:var(--accent);color:#fff;box-shadow:0 14px 26px -16px rgba(190,75,116,.85)}
.btn.primary:hover{background:var(--accent-hover)}
.btn.line{min-height:52px;font-weight:700;font-size:16.5px;color:var(--accent-hover);border-color:var(--line-strong);background:rgba(255,255,255,.35)}
.btn.line:hover{border-color:var(--accent)}
.small-link{align-self:center;padding:6px 4px;font-size:14.5px;font-weight:700;color:var(--accent-hover);text-underline-offset:3px}

/* how it works */
.how{margin-top:6px}
.how h2{margin:0 0 10px;text-align:center;font-family:var(--font-display);font-weight:500;font-size:24px;color:var(--ink)}
.how ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.how li{display:flex;gap:12px;align-items:center;padding:12px 16px;border:1px solid var(--line);border-radius:18px;background:rgba(255,250,251,.75);font-weight:600;font-size:15.5px}
.how b{flex:none;width:24px;text-align:center;font-family:var(--font-display);font-weight:500;font-size:28px;line-height:1;color:var(--accent)}
.foot{text-align:center;font-family:var(--font-script);font-size:34px;line-height:1;color:var(--accent);opacity:.85;padding-top:6px}

.home .page{min-height:100vh;min-height:100dvh;justify-content:center;gap:34px}
.home .title{font-size:clamp(32px,9vw,40px)}

@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
'''

FAVICON = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 44"><path d="{NAIL}" fill="#C15075"/>'
           f'<path d="{SHINE}" fill="#fff" opacity=".55"/></svg>')

# ---------- OG image template (rendered locally, 1200x630) ----------
def fonts_css():
    out = []
    for pkg, weights in (('fontsource-assistant-*', (400, 600, 700, 800)), ('fontsource-frank-ruhl-libre-*', (500,)),
                         ('fontsource-playpen-sans-hebrew-*', (400,)), ('fontsource-ms-madi-*', (400,))):
        d = sorted(p for p in glob.glob(str(pathlib.Path(FONTS) / pkg)) if pathlib.Path(p).is_dir())[-1]
        for w in weights:
            css = pathlib.Path(d, f'{w}.css').read_text(encoding='utf-8')
            out.append(css.replace('url(./files/', 'url(file://' + str(pathlib.Path(d).resolve()) + '/files/'))
    return '\n'.join(out)


OG_CSS = r'''
html,body{margin:0;background:#F7DAE2}
.og{position:relative;width:1200px;height:630px;overflow:hidden;background:#F7DAE2;color:#2E1D24;font-family:var(--font-ui)}
.og::after{content:"";position:absolute;top:-60%;left:-22%;width:70%;height:190%;background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.42) 50%,transparent 64%);transform:rotate(10deg);pointer-events:none}
.og .rose{position:absolute;left:-18px;top:-58px;width:330px;height:330px;color:#F7DAE2}
.og .rose g{stroke:#C4567E}
.og .top{position:absolute;right:70px;top:46px;z-index:1;display:flex;flex-direction:column;align-items:flex-end}
.og .pcard-eyebrow{font-size:44px;padding:6px 34px 14px}
.og .pcard-studio{font-size:82px;margin:4px 12px 0 0}
.og .row{position:absolute;left:0;right:0;z-index:1;display:flex;justify-content:center;align-items:flex-end}
.og .row .nail{flex:none}
.og .og-foot{position:absolute;right:70px;left:70px;bottom:50px;z-index:1;display:flex;flex-direction:column;align-items:flex-start}
.og .pcard-name{font-size:60px;line-height:1.15}
.og .pcard-status{margin-top:8px;font-size:36px;line-height:1.3}
.og .nail .num{font-size:10px}
'''


def og_body(p, N, label='הכרטיסייה שלך'):
    T = N + 1
    w = min(104, 1020 / (T + 0.28 * (T - 1)))
    g = 0.28 * w
    h = w * 44 / 32
    rose = ROSE_CARD.replace('class="pc-rose"', 'class="rose"')
    row = nails_inner(p, N).replace('<svg class="nail', f'<svg style="width:{w:.1f}px;height:{h:.1f}px;margin:0 {g / 2:.1f}px" class="nail')
    top_y = 260 if T <= 9 else 268
    return f'''<div class="og">{rose}
  <div class="top"><div class="pcard-eyebrow">{MARK_SVG}<span>כרטיסיית מועדון</span></div><div class="pcard-studio" dir="ltr">sapinails.il</div></div>
  <div class="row" style="top:{top_y}px">{row}</div>
  <div class="og-foot"><div class="pcard-name">{label}</div><div class="pcard-status">{card_status(p, N)}</div></div>
</div>'''


def build():
    (OUT / 'assets').mkdir(parents=True, exist_ok=True)
    (OUT / 'og').mkdir(parents=True, exist_ok=True)
    (OUT / '.nojekyll').write_text('', encoding='utf-8')
    (OUT / 'assets' / 'card.css').write_text(CSS, encoding='utf-8')
    (OUT / 'favicon.svg').write_text(FAVICON, encoding='utf-8')
    rc = re.sub(r'^<svg class="pc-rose" viewBox="([^"]+)"[^>]*>', r'<svg xmlns="http://www.w3.org/2000/svg" viewBox="\1">', ROSE_CARD)
    (OUT / 'assets' / 'rose-card.svg').write_text(rc.replace('currentColor', '#F7DAE2'), encoding='utf-8')
    (OUT / 'assets' / 'rose.svg').write_text(standalone_svg(site_symbol('r1'), '-81 -85 173 132', '#FAE9EE'), encoding='utf-8')
    (OUT / 'assets' / 'stem.svg').write_text(standalone_svg(site_symbol('s5'), '-6 -78 287 154', '#FAE9EE'), encoding='utf-8')
    home = OUT / 'index.html'
    if home.exists() and 'data-full-site' in home.read_text(encoding='utf-8'):
        print('index.html is the full site (tools/site/build_site.py), left as is')
    else:
        home.write_text(home_html(), encoding='utf-8')
    n_pages = 0
    for N in SIZES:
        for p in range(N + 1):
            d = OUT / 'k' / str(N) / str(p)
            d.mkdir(parents=True, exist_ok=True)
            (d / 'index.html').write_text(page_html(p, N), encoding='utf-8')
            n_pages += 1
    print('pages', n_pages)
    if NO_IMAGES:
        return
    from playwright.sync_api import sync_playwright
    from PIL import Image
    tpl = OUT.parent / '_og_template.html'
    tpl.write_text('<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><style>' + fonts_css()
                   + CSS.replace('body{margin:0;min-height:100vh;min-height:100dvh;', 'body{margin:0;') + OG_CSS
                   + '</style></head><body>' + CHROME_DEFS + '<div id="stage"></div></body></html>', encoding='utf-8')
    jobs = [(N, p, f'{N}-{p}', 'הכרטיסייה שלך') for N in SIZES for p in range(N + 1)]
    jobs.append((6, 0, 'home', 'כרטיסיית המועדון'))
    sizes = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={'width': 1200, 'height': 630}, device_scale_factor=1)
        pg.goto('file://' + str(tpl.resolve()))
        for N, p, name, label in jobs:
            pg.evaluate('h => { document.getElementById("stage").innerHTML = h; return document.fonts.ready.then(() => 1); }', og_body(p, N, label))
            png = pg.locator('.og').screenshot()
            im = Image.open(io.BytesIO(png)).convert('RGB')
            path = OUT / 'og' / f'{name}.jpg'
            im.save(path, 'JPEG', quality=88, optimize=True)
            sizes.append(path.stat().st_size)
        b.close()
    tpl.unlink()
    print('images', len(sizes), 'max KB', max(sizes) // 1024, 'avg KB', sum(sizes) // len(sizes) // 1024)


build()
