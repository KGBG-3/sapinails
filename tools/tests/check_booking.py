"""The booking form from start to finish, against the stand-in booking system (harness.py):
what the page sends with and without the box "no invitations", what the client is told, what happens when the
server does not know the field or is down, and that the box works from the keyboard and passes the axe checker.
Run:  python3 tools/tests/check_booking.py   (add a folder name to keep screenshots there)"""
import sys, pathlib
from playwright.sync_api import sync_playwright
from harness import *
SHOTS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
if SHOTS: SHOTS.mkdir(parents=True, exist_ok=True)
fails = []
def check(name, cond, detail=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' :: ' + str(detail) if detail and not cond else ''))
    if not cond: fails.append(name)
SIX = {'p_service', 'p_start', 'p_name', 'p_phone', 'p_note', 'p_addons'}
LABEL = 'לא לשלוח לי הזמנות לקבוע תור חדש'
DONE = 'הבקשה שלך נרשמה: לא יישלחו אלייך הזמנות לקבוע תור חדש.'

def to_details(pg, name='נועה בדיקה', phone='050-123-4567', note=''):
    pg.goto(BASE + 'book/'); pg.wait_for_selector('.svc')
    pg.locator('.svc').first.click(); pg.wait_for_selector('.slot')
    pg.locator('.slot').first.click(); pg.wait_for_selector('#stDetails:not([hidden])')
    pg.fill('#fName', name); pg.fill('#fPhone', phone)
    if note: pg.fill('#fNote', note)

def bookings(calls): return [b for n, b in calls if n == 'request_booking']

with server(), sync_playwright() as pw:
    b = pw.chromium.launch()

    def run(label, server='new', status='pending', width=390, tick=False, note='', shot=None):
        ctx = b.new_context(viewport={'width': width, 'height': 844}, device_scale_factor=2 if shot and SHOTS else 1, locale='he-IL', timezone_id='Asia/Jerusalem')
        calls = []; ext = []; mock_backend(ctx, booking_status=status, calls=calls, external=ext, server=server)
        pg = ctx.new_page(); errs = []
        pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
        pg.on('console', lambda m: errs.append(m.text[:160]) if m.type == 'error' and 'status of 404' not in m.text and 'status of 503' not in m.text else None)
        to_details(pg, note=note)
        if tick: pg.locator('#fNoPromo').check()
        if shot and SHOTS: settle(pg); pg.locator('#stDetails').screenshot(path=str(SHOTS / f'{shot}-form.png'))
        pg.click('#send'); pg.wait_for_timeout(900)
        if shot and SHOTS and pg.locator('#result').is_visible(): pg.locator('#result').screenshot(path=str(SHOTS / f'{shot}-result.png'))
        return ctx, pg, calls, errs, ext

    print('1. the box is there, off by default, and reachable')
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='he-IL', timezone_id='Asia/Jerusalem')
    calls = []; mock_backend(ctx, calls=calls)
    pg = ctx.new_page(); to_details(pg)
    box = pg.locator('#fNoPromo')
    check('the box exists and is not ticked', box.count() == 1 and not box.is_checked())
    check('its label is its name', pg.get_by_label(LABEL, exact=False).count() == 1 and pg.get_by_role('checkbox', name=LABEL, exact=False).count() == 1)
    check('the label says the reminders still come', 'אישור ותזכורת לתור הזה יישלחו כרגיל' in pg.locator('label.check', has=box).inner_text())
    order = pg.evaluate("""() => [...document.querySelectorAll('#form input, #form textarea, #form button')].filter(e => e.offsetParent).map(e => e.id || e.dataset.act)""")
    check('order: remember, the box, then the button', order[-3:] == ['fRemember', 'fNoPromo', 'send'], order)
    pg.locator('#fRemember').focus(); pg.keyboard.press('Tab')
    check('Tab moves from "remember" to the box', pg.evaluate('document.activeElement.id') == 'fNoPromo')
    pg.keyboard.press('Space'); check('Space ticks it', box.is_checked())
    ring = pg.evaluate("""() => { const s = getComputedStyle(document.activeElement); return s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2; }""")
    check('the focus ring shows on the box', ring)
    pg.keyboard.press('Space'); check('Space clears it', not box.is_checked())
    pg.locator('label.check', has=box).locator('span').first.click(); check('a tap on the text ticks it', box.is_checked())
    size = box.bounding_box()
    check('the box is big enough to tap (label row at least 24px high)', pg.locator('label.check', has=box).bounding_box()['height'] >= 24 and size['width'] >= 22, size)
    check('the note under the button points at the box', 'אפשר לסמן את זה כאן למעלה' in pg.locator('#form').inner_text())
    for w in (390, 320):
        pg.set_viewport_size({'width': w, 'height': 844}); pg.wait_for_timeout(200)
        res = axe(pg, f'book/ details step @{w}')
        check(f'axe: no violations on the details step @{w}', not res['violations'], [v['id'] for v in res['violations']])
        check(f'nothing wider than the screen @{w}', pg.evaluate('document.documentElement.scrollWidth') <= w, pg.evaluate('document.documentElement.scrollWidth'))
    ctx.close()

    print('2. without the box: the page sends what it always sent')
    ctx, pg, calls, errs, ext = run('plain', shot='1-plain')
    bk = bookings(calls)
    check('one booking call with the six fields only', len(bk) == 1 and set(bk[0]) == SIX, bk and sorted(bk[0]))
    check('the result shows, with no line about invitations', pg.locator('#result').is_visible() and DONE not in pg.locator('#result').inner_text())
    check('no errors, nothing asked from outside', not errs and not ext, (errs, ext))
    ctx.close()

    print('3. with the box: the field travels, and she is told it was taken')
    ctx, pg, calls, errs, ext = run('ticked', tick=True, note='ורוד בבקשה', shot='2-ticked')
    bk = bookings(calls)
    check('one booking call, with p_no_promo: true', len(bk) == 1 and set(bk[0]) == SIX | {'p_no_promo'} and bk[0]['p_no_promo'] is True, bk and sorted(bk[0]))
    check('her note is sent as she wrote it', bk[0]['p_note'] == 'ורוד בבקשה', bk[0]['p_note'])
    check('the result says the request was taken', DONE in pg.locator('#result').inner_text(), pg.locator('#result').inner_text()[-200:])
    check('the heading of the result has the focus', pg.evaluate("document.activeElement === document.querySelector('#result h2')"))
    res = axe(pg, 'book/ result with the line')
    check('axe: no violations on the result', not res['violations'], [v['id'] for v in res['violations']])
    check('no errors', not errs, errs)
    # a second booking in the same visit: the box stays as she left it
    pg.locator('[data-act=again]').click(); pg.wait_for_selector('.svc')
    pg.locator('.svc').first.click(); pg.wait_for_selector('.slot'); pg.locator('.slot').nth(1).click(); pg.wait_for_selector('#stDetails:not([hidden])')
    check('"another booking": the box is still ticked', pg.locator('#fNoPromo').is_checked())
    ctx.close()

    print('4. with the box, confirmed at once (a returning client)')
    ctx, pg, calls, errs, ext = run('ticked-confirmed', status='confirmed', tick=True, shot='3-confirmed')
    check('the confirmed result also says the request was taken', 'התור נקבע' in pg.locator('#result').inner_text() and DONE in pg.locator('#result').inner_text())
    ctx.close()

    print('5. a server that does not know the field (after an undo of the database change)')
    ctx, pg, calls, errs, ext = run('old-server', server='old', tick=True, note='ורוד בבקשה')
    bk = bookings(calls)
    check('first the new call, then the six fields again', len(bk) == 2 and 'p_no_promo' in bk[0] and set(bk[1]) == SIX, [sorted(x) for x in bk])
    check('the request reaches Sapir in the note, before the client\'s own words', len(bk) == 2 and bk[1]['p_note'] == 'ביקשה לא לקבל הזמנות לקבוע תור. ורוד בבקשה', bk and bk[-1]['p_note'])
    check('the booking is saved and she is told', pg.locator('#result').is_visible() and DONE in pg.locator('#result').inner_text())
    ctx.close()
    ctx, pg, calls, errs, ext = run('old-server-long-note', server='old', tick=True, note='א' * 300)
    bk = bookings(calls)
    check('a full-length note is cut to 300 and still starts with the request', len(bk) == 2 and len(bk[1]['p_note']) == 300 and bk[1]['p_note'].startswith('ביקשה לא לקבל הזמנות'), bk and len(bk[-1]['p_note']))
    ctx.close()
    ctx, pg, calls, errs, ext = run('old-server-plain', server='old')
    check('without the box an old server gets one plain call', len(bookings(calls)) == 1 and set(bookings(calls)[0]) == SIX and pg.locator('#result').is_visible())
    ctx.close()

    print('6. the server is down')
    ctx, pg, calls, errs, ext = run('down', server='down', tick=True)
    check('one call only, no second try without the field', len(bookings(calls)) == 1, len(bookings(calls)))
    check('she sees the connection message and can try again', pg.locator('#sendErr').is_visible() and 'אין חיבור' in pg.locator('#sendErr').inner_text() and pg.locator('#send').is_enabled() and not pg.locator('#result').is_visible())
    check('the box is still ticked for the next try', pg.locator('#fNoPromo').is_checked())
    ctx.close()

    print('7. the box in the accessibility modes')
    for mode, w in (('text-130', 390), ('text-130', 320), ('contrast', 390), ('font', 390)):
        ctx = b.new_context(viewport={'width': w, 'height': 844}, device_scale_factor=2 if SHOTS else 1, locale='he-IL', timezone_id='Asia/Jerusalem')
        mock_backend(ctx)
        ctx.add_init_script("try { localStorage.setItem('sapinails.ax', JSON.stringify(%s)); localStorage.setItem('sapinails.notice', '1'); } catch (e) {}" % {
            'text-130': '{"size":2}', 'contrast': '{"contrast":true}', 'font': '{"font":true}'}[mode])
        pg = ctx.new_page(); to_details(pg); pg.locator('#fNoPromo').check(); settle(pg)
        applied = pg.evaluate("(document.documentElement.className + ' ' + (document.documentElement.getAttribute('data-ax-size') ? 'size-' + document.documentElement.getAttribute('data-ax-size') : '')).trim()")
        lab = pg.locator('label.check', has=pg.locator('#fNoPromo')).bounding_box()
        sw = pg.evaluate('document.documentElement.scrollWidth')
        check(f'{mode} @{w}: applied ({applied.strip() or "no class"}), label inside the screen, no sideways scroll', bool(applied.strip()) and lab['x'] >= 0 and lab['x'] + lab['width'] <= w + 1 and sw <= w, (applied, lab, sw))
        res = axe(pg, f'book/ details {mode} @{w}')
        check(f'{mode} @{w}: axe', not res['violations'], [v['id'] for v in res['violations']])
        if SHOTS: pg.locator('#stDetails').screenshot(path=str(SHOTS / f'4-{mode}-{w}.png'))
        ctx.close()
    b.close()
print('\nFAILED:' if fails else '\nALL PASSED', fails or '')
sys.exit(1 if fails else 0)
