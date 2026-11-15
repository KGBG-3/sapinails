"""The "no invitations" mark in the admin screen, against the stand-in backend (admin_harness.py).
Run:  python3 tools/tests/check_admin_marks.py"""
import json, time
from playwright.sync_api import sync_playwright
from harness import server, HERE, BASE
from admin_harness import *
fails = []
def check(name, cond, detail=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' :: ' + str(detail) if detail and not cond else ''))
    if not cond: fails.append(name)
def last_write(calls, cid):
    for m, p, b in reversed(calls):
        if m == 'POST' and p.startswith('/rest/v1/clients') and isinstance(b, dict) and b.get('id') == cid: return b['data']
    return None
with server(), sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, locale='he-IL', timezone_id='Asia/Jerusalem')
    state = fresh_state(); calls = []; ext = []
    mock_admin(ctx, state, calls, ext)
    pg = ctx.new_page(); errs = []
    pg.on('console', lambda m: errs.append(m.type + ': ' + m.text[:200]) if m.type in ('error', 'warning') and 'ERR_FAILED' not in m.text else None)
    pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
    login(pg)
    pg.click('.tab[data-v=cards]'); pg.wait_for_timeout(400)
    sheet = lambda: pg.locator('#sheets .layer').last

    print('1. before marking')
    pg.click('.row-main[data-id=c-noa]'); pg.wait_for_timeout(300)
    row = sheet().locator('.info-row', has_text='הזמנות לחזור')
    check('the row is in the client sheet', row.count() == 1)
    check('default state', 'אפשר לשלוח' in row.inner_text() and 'ביקשה להפסיק' in row.inner_text(), row.inner_text())
    check('no pills in the list yet', pg.locator('.pill.stop').count() == 0)
    sheet().locator('[data-act=wa]').click(); pg.wait_for_timeout(300)
    chips = [(c.text_content(), c.get_attribute('aria-checked')) for c in sheet().locator('.chip').all()]
    check('invitation offered and chosen for a client who has been away', ('הזמנה לחזור', 'true') in chips, chips)
    msg = sheet().locator('#wa-preview').inner_text()
    check('the invitation says how to stop', 'אפשר להשיב "הסר"' in msg, msg[-120:])
    check('no note', sheet().locator('.stop-note').count() == 0)
    href = sheet().locator('#wa-link').get_attribute('href')
    check('link goes to WhatsApp with the phone', href.startswith('https://api.whatsapp.com/send?phone=972501112233&text='), href[:80])
    sheet().locator('.icon-btn[data-act=close]').click(); pg.wait_for_timeout(200)

    print('2. marking')
    t0 = int(time.time() * 1000)
    sheet().locator('[data-act=promo-off]').click(); pg.wait_for_timeout(400)
    w = last_write(calls, 'c-noa')
    check('saved to the database with the time', bool(w) and isinstance(w.get('noPromo'), int) and abs(w['noPromo'] - t0) < 5000, w and w.get('noPromo'))
    check('nothing else on the card changed', bool(w) and w['punches'] == 4 and w['name'] == 'נועה לוי' and w['phone'] == '050-111-2233' and len(w['log']) == 5 and w['notes'] == 'אוהבת גווני ניוד', w)
    row = sheet().locator('.info-row', has_text='הזמנות לחזור')
    check('row shows the mark and the date', 'לא לשלוח' in row.inner_text() and 'ביטול' in row.inner_text(), row.inner_text())
    check('toast', 'לא לשלוח לנועה' in pg.locator('#toasts').inner_text(), pg.locator('#toasts').inner_text())

    print('3. the message sheet for a marked client')
    sheet().locator('[data-act=wa]').click(); pg.wait_for_timeout(300)
    chips = [(c.text_content(), c.get_attribute('aria-checked')) for c in sheet().locator('.chip').all()]
    check('invitation is not offered', all(t != 'הזמנה לחזור' for t, _ in chips), chips)
    check('card status is chosen instead', ('מצב הכרטיסייה', 'true') in chips, chips)
    msg = sheet().locator('#wa-preview').inner_text()
    check('message is the card status, not the invitation', 'עדכון מהכרטיסייה' in msg and 'מתגעגעת' not in msg and 'הסר' not in msg, msg)
    check('note explains why', 'נועה ביקשה לא לקבל הזמנות לחזור. לכן ההודעה «הזמנה לחזור» לא מופיעה כאן' in sheet().locator('.stop-note').inner_text())
    sheet().locator('.icon-btn[data-act=close]').click(); pg.wait_for_timeout(150)
    sheet().locator('.icon-btn[data-act=close]').click(); pg.wait_for_timeout(250)

    print('4. the list and the summary')
    pill_rows = pg.locator('.row', has=pg.locator('.pill.stop')).locator('.nm').all_text_contents()
    check('pill on her row only', pill_rows == ['נועה לוי'], pill_rows)
    check('still counted as away', pg.locator('#n-away').text_content() == '2')
    pg.click('#vCards [data-act=settings]'); pg.wait_for_timeout(300)
    sheet().locator('[data-act=summary]').click(); pg.wait_for_timeout(300)
    summ = sheet().locator('#wa-preview').inner_text()
    check('summary marks her', 'נועה לוי · לפני חודשיים · בלי הזמנות' in summ and 'יוסי מזרחי · לפני 3 חודשים\n' in summ + '\n', summ)
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200); pg.keyboard.press('Escape'); pg.wait_for_timeout(250)
    check('sheets closed', pg.locator('#sheets .layer').count() == 0)

    print('5. the mark survives other changes to the card')
    pg.click('.punch-quick[data-id=c-noa]'); pg.wait_for_timeout(400)
    w = last_write(calls, 'c-noa')
    check('after a punch', w['punches'] == 5 and isinstance(w.get('noPromo'), int), (w['punches'], w.get('noPromo')))
    pg.click('.row-main[data-id=c-noa]'); pg.wait_for_timeout(300)
    sheet().locator('[data-act=undo]').click(); pg.wait_for_timeout(400)
    w = last_write(calls, 'c-noa')
    check('after undoing the punch', w['punches'] == 4 and isinstance(w.get('noPromo'), int), (w['punches'], w.get('noPromo')))
    sheet().locator('[data-act=edit]').click(); pg.wait_for_timeout(300)
    sheet().locator('#f-notes').fill('אוהבת גווני ניוד, צורת שקד'); sheet().locator('#f-save').click(); pg.wait_for_timeout(500)
    w = last_write(calls, 'c-noa')
    check('after editing her details', w['notes'].endswith('צורת שקד') and isinstance(w.get('noPromo'), int), (w['notes'], w.get('noPromo')))

    print('6. after reloading the page')
    pg.reload(); pg.wait_for_selector('#tabbar:not([hidden])'); pg.wait_for_timeout(700)
    check('still marked in the list', pg.locator('.row', has=pg.locator('.pill.stop')).locator('.nm').all_text_contents() == ['נועה לוי'])

    print('7. a second card with the same phone number')
    state['clients']['c-noa2'] = client('נועה ל.', '0501112233', 0, None)
    pg.reload(); pg.wait_for_selector('#tabbar:not([hidden])'); pg.wait_for_timeout(700)
    check('both rows carry the pill', sorted(pg.locator('.row', has=pg.locator('.pill.stop')).locator('.nm').all_text_contents()) == ['נועה ל.', 'נועה לוי'])
    pg.click('.row-main[data-id=c-noa2]'); pg.wait_for_timeout(300)
    row = sheet().locator('.info-row', has_text='הזמנות לחזור')
    check('second card shows the mark', 'לא לשלוח' in row.inner_text(), row.inner_text())
    n_before = len(calls)
    sheet().locator('[data-act=promo-on]').click(); pg.wait_for_timeout(500)
    writes = [(b['id'], 'noPromo' in b['data']) for m, p, b in calls[n_before:] if m == 'POST' and p.startswith('/rest/v1/clients')]
    check('clearing from the second card clears the first', writes == [('c-noa', False)], writes)
    check('no card is marked now', 'noPromo' not in state['clients']['c-noa'] and 'noPromo' not in state['clients']['c-noa2'])
    row = sheet().locator('.info-row', has_text='הזמנות לחזור')
    check('row is back to default', 'אפשר לשלוח' in row.inner_text(), row.inner_text())
    sheet().locator('.icon-btn[data-act=close]').click(); pg.wait_for_timeout(250)
    check('no pills left', pg.locator('.pill.stop').count() == 0)

    print('8. a male client, and undo from the toast')
    pg.click('.row-main[data-id=c-yossi]'); pg.wait_for_timeout(300)
    row = sheet().locator('.info-row', has_text='הזמנות לחזור')
    check('masculine wording on the button', 'ביקש להפסיק' in row.inner_text() and 'ביקשה' not in row.inner_text(), row.inner_text())
    sheet().locator('[data-act=promo-off]').click(); pg.wait_for_timeout(300)
    sheet().locator('[data-act=wa]').click(); pg.wait_for_timeout(300)
    check('masculine wording in the note', 'יוסי ביקש לא לקבל' in sheet().locator('.stop-note').inner_text())
    sheet().locator('.icon-btn[data-act=close]').click(); pg.wait_for_timeout(200)
    sheet().locator('[data-act=delete-ask]').click(); pg.wait_for_timeout(200)
    check('delete warning mentions the mark', 'גם הסימון «לא לשלוח הזמנות» יימחק' in sheet().locator('.confirm').inner_text(), sheet().locator('.confirm').inner_text())
    sheet().locator('[data-act=delete-no]').click(); pg.wait_for_timeout(150)
    pg.locator('#toasts button', has_text='ביטול').click(); pg.wait_for_timeout(400)
    check('undo from the toast clears it', 'noPromo' not in state['clients']['c-yossi'], state['clients']['c-yossi'].get('noPromo'))
    sheet().locator('.icon-btn[data-act=close]').click(); pg.wait_for_timeout(250)

    print('9. the rest of the screen still works')
    for v in ('agenda', 'hours', 'more', 'cards'):
        pg.click(f'.tab[data-v={v}]'); pg.wait_for_timeout(350)
        check(f'tab {v} shows', pg.locator(f'#v{v[0].upper() + v[1:]}').is_visible())
    pg.click('.tab[data-v=more]'); pg.wait_for_timeout(300)
    pg.locator('[data-act=tpl-list]').first.click(); pg.wait_for_timeout(300)
    sheet().locator('[data-act=tpl-open][data-k=reminder]').click(); pg.wait_for_timeout(300)
    ta = sheet().locator('textarea').first.input_value()
    check('the editor shows the new default invitation', ta.endswith('לא רוצה לקבל ממני הזמנות כאלה? אפשר להשיב "הסר" 🙏'), ta[-90:])
    print('console problems:', errs)
    check('no console errors', not errs, errs)
    check('only the fonts were asked from outside', set(e.split('?')[0] for e in ext) <= {'https://fonts.googleapis.com/css2'}, set(ext))
    ctx.close()

    b.close()
print('\nFAILED:' if fails else '\nALL PASSED', fails or '')
import sys; sys.exit(1 if fails else 0)
