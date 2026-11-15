"""The everyday admin flows against the stand-in backend: agenda, completing a treatment, new client, gift, search, delete.
Run:  python3 tools/tests/check_admin_flows.py"""
import json, time
from playwright.sync_api import sync_playwright
from harness import server, HERE, BASE
from admin_harness import *
fails = []
def check(name, cond, detail=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' :: ' + str(detail) if detail and not cond else ''))
    if not cond: fails.append(name)
def writes(calls, since=0):
    return [(b['id'], b['data']) for m, p, b in calls[since:] if m == 'POST' and p.startswith('/rest/v1/clients') and isinstance(b, dict)]
with server(), sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1, locale='he-IL', timezone_id='Asia/Jerusalem')
    state = fresh_state(); calls = []
    # an appointment for someone without a card, to be completed today
    now = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
    iso = lambda d: d.isoformat().replace('+00:00', 'Z')
    state['appointments'].append({'id': 'a-2', 'service_id': 'gel', 'service_name': 'לק ג׳ל (כולל מניקור)', 'name': 'שירה אברהם', 'phone': '058-777-8899', 'note': '', 'addons': [],
        'starts_at': iso(now - datetime.timedelta(hours=2)), 'ends_at': iso(now - datetime.timedelta(minutes=30)), 'status': 'confirmed', 'is_new': True, 'client_id': None,
        'punched': False, 'price': 130, 'source': 'site', 'created_at': iso(now - datetime.timedelta(days=1)), 'reminded_at': None, 'notified_at': None})
    # the same, for someone who ticked "no invitations" in the booking form
    state['appointments'].append({'id': 'a-3', 'service_id': 'gel', 'service_name': 'לק ג׳ל (כולל מניקור)', 'name': 'הילה בן דוד', 'phone': '058-555-6677', 'note': '', 'addons': [],
        'starts_at': iso(now - datetime.timedelta(hours=5)), 'ends_at': iso(now - datetime.timedelta(hours=3, minutes=30)), 'status': 'confirmed', 'is_new': True, 'client_id': None,
        'punched': False, 'price': 130, 'source': 'online', 'no_promo': True, 'created_at': iso(now - datetime.timedelta(days=1)), 'reminded_at': None, 'notified_at': None})
    for a in state['appointments']: a.setdefault('no_promo', False)
    mock_admin(ctx, state, calls)
    pg = ctx.new_page(); errs = []
    pg.on('console', lambda m: errs.append(m.type + ': ' + m.text[:200]) if m.type in ('error', 'warning') and 'ERR_FAILED' not in m.text else None)
    pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
    login(pg)
    sheet = lambda: pg.locator('#sheets .layer').last
    close = lambda: (pg.keyboard.press('Escape'), pg.wait_for_timeout(250))

    print('agenda')
    txt = pg.locator('#vAgenda').inner_text()
    check('agenda lists the appointments', 'מאיה' in txt and 'שירה' in txt, txt[:300])
    pg.locator('[data-act=appt-open][data-id=a-2]').first.click(); pg.wait_for_timeout(300)
    check('appointment sheet opens', 'שירה אברהם' in sheet().inner_text())
    check('no line about invitations for a booking without the box', 'הזמנות לחזור' not in sheet().inner_text())
    sheet().locator('[data-act=appt-wa]').first.click(); pg.wait_for_timeout(300)
    chips = [c.text_content() for c in sheet().locator('.chip').all()]
    check('appointment messages offered, without a note', 'אישור' in ' '.join(chips) and sheet().locator('.stop-note').count() == 0, chips)
    close()
    n = len(calls)
    sheet().locator('[data-act=appt-done]').click(); pg.wait_for_timeout(700)
    ws = writes(calls, n)
    check('completing the appointment opened a card and punched it', len(ws) >= 2 and ws[-1][1]['name'] == 'שירה אברהם' and ws[-1][1]['punches'] == 1 and 'noPromo' not in ws[-1][1], [(i, d.get('punches'), 'noPromo' in d) for i, d in ws])
    patch = [b for m, p, b in calls[n:] if m == 'PATCH' and p.startswith('/rest/v1/appointments')]
    check('appointment marked done', bool(patch) and patch[-1].get('status') == 'done' and patch[-1].get('punched') is True, patch)
    msg = sheet().locator('#wa-preview').inner_text()
    check('the after-treatment message opened', 'תודה שבאת היום' in msg and 'הסר' not in msg, msg[:80])
    close()

    print('a booking with "no invitations" ticked in the form')
    pg.locator('[data-act=appt-open][data-id=a-3]').first.click(); pg.wait_for_timeout(300)
    row = sheet().locator('.info-row', has_text='הזמנות לחזור')
    check('the appointment sheet says what she asked', row.count() == 1 and 'ביקשה בטופס לא לקבל' in row.inner_text(), sheet().inner_text()[:300])
    n = len(calls); t0 = int(time.time() * 1000)
    sheet().locator('[data-act=appt-done]').click(); pg.wait_for_timeout(700)
    ws = writes(calls, n)
    check('the card that is opened at the end of the treatment carries the mark', len(ws) >= 2 and ws[0][1]['name'] == 'הילה בן דוד' and all(isinstance(d.get('noPromo'), int) and abs(d['noPromo'] - t0) < 5000 for _, d in ws) and ws[-1][1]['punches'] == 1,
          [(d.get('name'), d.get('punches'), d.get('noPromo')) for _, d in ws])
    close()
    pg.click('.tab[data-v=cards]'); pg.wait_for_timeout(400)
    check('her row in the list carries the pill', pg.locator('.row', has=pg.locator('.pill.stop')).locator('.nm').all_text_contents() == ['הילה בן דוד'], pg.locator('.row', has=pg.locator('.pill.stop')).locator('.nm').all_text_contents())
    pg.click('.tab[data-v=agenda]'); pg.wait_for_timeout(300)

    print('cards')
    pg.click('.tab[data-v=cards]'); pg.wait_for_timeout(400)
    check('six cards listed', pg.locator('#vCards .row').count() == 6, pg.locator('#vCards .row').count())
    # a new client from the form
    n = len(calls)
    pg.click('#addBtn'); pg.wait_for_timeout(300)
    sheet().locator('#f-name').fill('רותם שלום'); sheet().locator('#f-phone').fill('050-999-0000'); sheet().locator('#f-save').click(); pg.wait_for_timeout(600)
    ws = writes(calls, n)
    check('new client saved, with no mark', len(ws) == 1 and ws[0][1]['name'] == 'רותם שלום' and 'noPromo' not in ws[0][1] and set(ws[0][1]) == {'name', 'phone', 'g', 'notes', 'punches', 'rewards', 'visits', 'createdAt', 'lastVisit', 'updatedAt', 'log'}, ws and sorted(ws[0][1]))
    row = sheet().locator('.info-row', has_text='הזמנות לחזור')
    check('her sheet shows the default state', 'אפשר לשלוח' in row.inner_text())
    sheet().locator('[data-act=wa]').click(); pg.wait_for_timeout(300)
    chips = [(c.text_content(), c.get_attribute('aria-checked')) for c in sheet().locator('.chip').all()]
    check('welcome message chosen for a new client, invitation still offered', ('הודעת הצטרפות', 'true') in chips and ('הזמנה לחזור', 'false') in chips, chips)
    sheet().locator('.chip', has_text='הזמנה לחזור').click(); pg.wait_for_timeout(250)
    check('switching to the invitation works', 'מתגעגעת' in sheet().locator('#wa-preview').inner_text())
    close(); close()
    # a full card: gift
    pg.click('.row-main[data-id=c-dana]'); pg.wait_for_timeout(300)
    n = len(calls)
    sheet().locator('[data-act=redeem]').click(); pg.wait_for_timeout(500)
    ws = writes(calls, n)
    check('gift redeemed', len(ws) == 1 and ws[0][1]['punches'] == 0 and ws[0][1]['rewards'] == 1, ws and (ws[0][1]['punches'], ws[0][1]['rewards']))
    close()
    # search and filters
    pg.fill('#q', 'נועה'); pg.wait_for_timeout(250)
    check('search finds her', pg.locator('#vCards .row .nm').all_text_contents() == ['נועה לוי'])
    pg.fill('#q', ''); pg.locator('.toolbar .chip[data-f=away]').click(); pg.wait_for_timeout(250)
    check('away filter', sorted(pg.locator('#vCards .row .nm').all_text_contents()) == ['יוסי מזרחי', 'נועה לוי'], pg.locator('#vCards .row .nm').all_text_contents())
    # delete
    pg.locator('.toolbar .chip[data-f=all]').click(); pg.wait_for_timeout(200)
    pg.click('.row-main[data-id=c-yossi]'); pg.wait_for_timeout(300)
    sheet().locator('[data-act=delete-ask]').click(); pg.wait_for_timeout(200)
    check('plain delete warning for an unmarked client', 'הסימון' not in sheet().locator('.confirm').inner_text())
    sheet().locator('[data-act=delete-yes]').click(); pg.wait_for_timeout(500)
    check('client deleted', 'c-yossi' not in state['clients'])
    print('console problems:', errs)
    check('no console errors', not errs, errs)
    ctx.close(); b.close()
print('\nFAILED:' if fails else '\nALL PASSED', fails or '')
import sys; sys.exit(1 if fails else 0)
