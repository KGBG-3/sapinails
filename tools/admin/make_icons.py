"""Home-screen icons for the admin screen (iPhone, Android) and the small alert badge."""
import pathlib, sys
from playwright.sync_api import sync_playwright
OUT = pathlib.Path(sys.argv[1])
NAIL = 'M16 1.6C23 5.2 29.4 14.2 29.4 26.2C29.4 36.6 23.4 42.6 16 42.6C8.6 42.6 2.6 36.6 2.6 26.2C2.6 14.2 9 5.2 16 1.6Z'
SHINE = 'M8.6 14.4C6.9 19.4 6.5 25.2 7.5 31C7.8 32.5 9.5 32.3 9.4 30.8C8.9 25.2 9.5 19.8 11 15.3C11.5 13.8 9.2 12.9 8.6 14.4Z'
SPARK = 'M0 -6L1.6 -1.6L6 0L1.6 1.6L0 6L-1.6 1.6L-6 0L-1.6 -1.6Z'
def icon(size, scale):
    # nail height = scale * size, centred a touch low; one sparkle top-left
    h = size * scale; w = h * 32 / 44; x = (size - w) / 2; y = (size - h) / 2 + size * 0.015; k = h / 44
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FCEFF3"/><stop offset="1" stop-color="#F4D6E0"/></linearGradient>
    <linearGradient id="n" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#DC8AA0"/><stop offset=".55" stop-color="#C15075"/><stop offset="1" stop-color="#8E2C55"/></linearGradient>
  </defs>
  <rect width="{size}" height="{size}" fill="url(#bg)"/>
  <g transform="translate({x:.2f} {y:.2f}) scale({k:.4f})">
    <path d="{NAIL}" fill="url(#n)"/>
    <path d="{SHINE}" fill="#fff" opacity=".6"/>
  </g>
  <g transform="translate({x + w * 1.02:.2f} {y + h * 0.16:.2f}) scale({h / 70:.4f})"><path d="{SPARK}" fill="#C15075" opacity=".85"/></g>
</svg>'''
def badge(size):
    h = size * 0.8; w = h * 32 / 44; x = (size - w) / 2; y = (size - h) / 2; k = h / 44
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}"><g transform="translate({x:.2f} {y:.2f}) scale({k:.4f})"><path d="{NAIL}" fill="#fff"/></g></svg>'
jobs = [('icon-180.png', 180, icon(180, .62), False), ('icon-192.png', 192, icon(192, .62), False), ('icon-512.png', 512, icon(512, .62), False),
        ('icon-maskable-512.png', 512, icon(512, .50), False), ('badge-96.png', 96, badge(96), True)]
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for name, size, svg, transparent in jobs:
        pg = b.new_page(viewport={'width': size, 'height': size})
        pg.set_content(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
        pg.screenshot(path=str(OUT / name), omit_background=transparent)
        pg.close()
    b.close()
print('icons written to', OUT)
