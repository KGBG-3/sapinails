"""Check every public page at four screen widths: console errors, requests that leave the site, cookies,
content wider than the screen, links that resolve, new-window links that say so, and the axe accessibility checker.
Run:  python3 tools/tests/check_public.py     (needs Playwright with Chromium, and axe-core: see README)"""
import re, sys, pathlib, urllib.parse
from playwright.sync_api import sync_playwright
from harness import *
PAGES = ['index.html', 'book/', 'accessibility/', 'privacy/', 'terms/', 'k/6/0/', 'k/6/3/', 'k/6/6/?c=7', 'k/3/1/', 'k/12/12/']
OVER = '''() => { const w = innerWidth; return [...document.querySelectorAll('body *')].filter(n => { const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0 && (r.right > w + 1 || r.left < -1) && !n.closest('.ro,.decos,.days,.pc-rose,.mnav,.defs,.ax-sr,.sr,.skip,.pcard') ; }).slice(0, 5).map(n => n.tagName.toLowerCase() + '.' + String(n.className.baseVal || n.className).split(' ').join('.') + ' ' + Math.round(n.getBoundingClientRect().left) + '..' + Math.round(n.getBoundingClientRect().right)); }'''
problems = []
with server(), sync_playwright() as pw:
    b = pw.chromium.launch()
    for w, h in ((320, 640), (390, 844), (768, 1024), (1280, 800)):
        ctx = b.new_context(viewport={'width': w, 'height': h}, device_scale_factor=1, locale='he-IL')
        ext = []; mock_backend(ctx, external=ext)
        for path in PAGES:
            pg = ctx.new_page(); errs = []
            pg.on('console', lambda m: errs.append(m.text) if m.type in ('error', 'warning') else None)
            pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
            pg.on('requestfailed', lambda r: errs.append('FAILED ' + r.url))
            pg.on('response', lambda r: errs.append(f'{r.status} {r.url}') if r.status >= 400 else None)
            pg.goto(BASE + path); pg.wait_for_load_state('networkidle'); settle(pg)
            over = pg.evaluate(OVER)
            sw = pg.evaluate('document.documentElement.scrollWidth')
            res = axe(pg, f'{path} @{w}') if w in (390, 1280) else {'violations': []}
            # links
            links = pg.evaluate('''() => [...document.querySelectorAll('a[href]')].map(a => ({ href: a.getAttribute('href'), abs: a.href, blank: a.target === '_blank', rel: a.rel, hint: !!a.querySelector('.ax-sr'), text: (a.getAttribute('aria-label') || a.textContent).trim().slice(0, 30) }))''')
            for l in links:
                if l['blank'] and (not l['hint'] or 'noopener' not in l['rel']): problems.append((path, 'new-window link without hint/noopener', l))
                if not l['text']: problems.append((path, 'link without a name', l))
                if l['abs'].startswith(BASE):
                    u = urllib.parse.urlsplit(l['abs']); f = REPO / urllib.parse.unquote(u.path.lstrip('/'))
                    if f.is_dir(): f = f / 'index.html'
                    if not f.exists(): problems.append((path, 'broken link', l))
                    elif u.fragment and not re.match(r'k\d', u.fragment):
                        if f'id="{u.fragment}"' not in f.read_text(encoding='utf-8'): problems.append((path, 'missing anchor', l))
            if errs or over or sw > w or res['violations']:
                problems.append((path, w, {'errors': errs, 'overflow': over, 'scrollWidth': sw, 'axe': [v['id'] for v in res['violations']]}))
            pg.close()
        keys = None
        print(f'width {w}: outside requests {ext}; cookies {ctx.cookies()}')
        ctx.close()
    b.close()
print('PROBLEMS:', len(problems))
for p in problems: print('  ', p)
sys.exit(1 if problems else 0)
