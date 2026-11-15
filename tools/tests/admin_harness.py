"""A stand-in for the studio's Supabase project, for testing the admin screen locally.
It keeps clients, settings and appointments in memory and answers the calls the admin app makes."""
import base64, copy, datetime, json, re, time, urllib.parse
from harness import BASE, SUPA

DAY = 86400000
NOW = lambda: int(time.time() * 1000)


def b64(d): return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')


def session():
    exp = int(time.time()) + 3600
    token = '.'.join([b64({'alg': 'HS256', 'typ': 'JWT'}), b64({'sub': 'u-1', 'role': 'authenticated', 'aud': 'authenticated', 'exp': exp, 'email': 'sapir@sapinails.co.il'}), 'sig'])
    user = {'id': 'u-1', 'aud': 'authenticated', 'role': 'authenticated', 'email': 'sapir@sapinails.co.il', 'app_metadata': {}, 'user_metadata': {}, 'created_at': '2026-10-21T00:00:00Z'}
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': 3600, 'expires_at': exp, 'refresh_token': 'refresh-1', 'user': user}


def client(name, phone, punches, last_days, g='f', rewards=0, notes='', extra=None):
    now = NOW()
    last = now - last_days * DAY if last_days is not None else None
    log = [{'t': now - 200 * DAY, 'a': 'join', 'p': 0}]
    for i in range(punches):
        log.append({'t': (last or now) - (punches - 1 - i) * 21 * DAY, 'a': 'punch', 'p': i + 1, 'prev': {'p': i, 'r': rewards, 'v': i, 'lv': None}})
    d = {'name': name, 'phone': phone, 'g': g, 'notes': notes, 'punches': punches, 'rewards': rewards, 'visits': punches + rewards * 6,
         'createdAt': now - 200 * DAY, 'lastVisit': last, 'updatedAt': now - 1000, 'log': log}
    if extra: d.update(extra)
    return d


def fresh_state():
    tomorrow = datetime.datetime.now(datetime.timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    iso = lambda d: d.isoformat().replace('+00:00', 'Z')
    return {
        'clients': {
            'c-noa': client('נועה לוי', '050-111-2233', 4, 60, notes='אוהבת גווני ניוד'),
            'c-dana': client('דנה כהן', '052-222-3344', 6, 10),
            'c-maya': client('מאיה ישראלי', '054-333-4455', 2, 3),
            'c-yossi': client('יוסי מזרחי', '053-444-5566', 1, 90, g='m'),
        },
        'settings': {
            'studioName': 'הסטודיו של ספיר', 'cardSize': 6, 'ownerPhone': '0543439530', 'siteUrl': 'https://kgbg-3.github.io/sapinails',
            'slotMinutes': 30, 'bufferMinutes': 0, 'minNoticeMinutes': 120, 'maxDaysAhead': 30, 'address': 'תל אביב',
            'hours': {'0': [{'from': '16:00', 'to': '20:00'}], '1': [{'from': '14:00', 'to': '20:00'}], '2': [{'from': '16:00', 'to': '20:00'}],
                      '3': [{'from': '16:00', 'to': '20:00'}], '4': [{'from': '16:00', 'to': '20:00'}], '5': [], '6': []},
            'addons': ['פרנץ׳', 'ציורים או אבנים'], 'templates': {}, 'notify': {'booking': True, 'dailyAt': '20:00'},
        },
        'services': [
            {'id': 'gel', 'name': 'לק ג׳ל (כולל מניקור)', 'minutes': 90, 'price': 130, 'sort': 1, 'active': True, 'counts': True},
            {'id': 'build', 'name': 'בנייה בג׳ל', 'minutes': 120, 'price': 200, 'sort': 2, 'active': True, 'counts': True},
            {'id': 'remove', 'name': 'הסרה בלבד', 'minutes': 15, 'price': 50, 'sort': 4, 'active': True, 'counts': False},
        ],
        'appointments': [
            {'id': 'a-1', 'service_id': 'gel', 'service_name': 'לק ג׳ל (כולל מניקור)', 'name': 'מאיה ישראלי', 'phone': '054-333-4455', 'note': '', 'addons': [],
             'starts_at': iso(tomorrow), 'ends_at': iso(tomorrow + datetime.timedelta(minutes=90)), 'status': 'confirmed', 'is_new': False, 'client_id': 'c-maya',
             'punched': False, 'price': 130, 'source': 'site', 'created_at': iso(tomorrow - datetime.timedelta(days=2)), 'reminded_at': None, 'notified_at': None},
        ],
        'blocks': [],
    }


def mock_admin(context, state, calls=None, external=None):
    def reply(route, body, status=200):
        route.fulfill(status=status, content_type='application/json', body=json.dumps(body) if not isinstance(body, str) else body)

    def supa(route):
        req = route.request
        u = urllib.parse.urlsplit(req.url); q = urllib.parse.parse_qs(u.query); path = u.path
        body = None
        if req.post_data:
            try: body = json.loads(req.post_data)
            except Exception: body = req.post_data
        if calls is not None: calls.append((req.method, path + ('?' + u.query if u.query else ''), body))
        eq = lambda col: (q.get(col, [''])[0][3:] if q.get(col, [''])[0].startswith('eq.') else None)
        want_object = 'vnd.pgrst.object' in (req.headers.get('accept') or '')
        if path.startswith('/auth/v1/token'): return reply(route, session())
        if path.startswith('/auth/v1/user'): return reply(route, session()['user'])
        if path.startswith('/auth/v1/logout'): return route.fulfill(status=204, body='')
        if path == '/rest/v1/rpc/is_admin': return reply(route, True)
        if path == '/rest/v1/rpc/merge_settings':
            state['settings'].update(body.get('p_patch') or {})
            return reply(route, state['settings'])
        if path == '/rest/v1/clients':
            if req.method == 'GET':
                rows = [{'id': k, 'data': v} for k, v in state['clients'].items() if eq('id') in (None, k)]
                if want_object: return reply(route, rows[0]) if rows else reply(route, {'code': 'PGRST116', 'message': 'no rows'}, 406)
                return reply(route, rows)
            if req.method == 'POST':
                for r in (body if isinstance(body, list) else [body]): state['clients'][r['id']] = copy.deepcopy(r['data'])
                return route.fulfill(status=201, body='')
            if req.method == 'DELETE':
                state['clients'].pop(eq('id'), None); return route.fulfill(status=204, body='')
        if path == '/rest/v1/settings':
            rows = [{'data': state['settings']}]
            return reply(route, rows[0] if want_object else rows)
        if path in ('/rest/v1/appointments', '/rest/v1/blocks', '/rest/v1/services'):
            key = path.rsplit('/', 1)[1]
            if req.method == 'GET': return reply(route, state[key])
            if req.method == 'PATCH':
                out = []
                for r in state[key]:
                    if r['id'] == eq('id'): r.update(body); out.append(r)
                return reply(route, out[0] if want_object and out else out)
            if req.method == 'POST':
                rows = body if isinstance(body, list) else [body]
                for r in rows: r.setdefault('id', 'new-' + str(len(state[key]) + 1)); state[key].append(r)
                return reply(route, rows[0] if want_object else rows, 201)
            if req.method == 'DELETE':
                state[key][:] = [r for r in state[key] if r['id'] != eq('id')]; return route.fulfill(status=204, body='')
        if path.startswith('/functions/v1/'): return reply(route, {'ok': True})
        if path.startswith('/rest/v1/push_subs'): return reply(route, [])
        print('UNHANDLED', req.method, path, u.query)
        return reply(route, {'message': 'not mocked'}, 404)
    context.route(SUPA + '/**', supa)

    def other(route):
        url = route.request.url
        if external is not None: external.append(url)
        route.abort()
    context.route(lambda url: not url.startswith(BASE) and not url.startswith(SUPA), other)

    # live updates: accept the connection and answer joins and heartbeats, so the app sits quietly
    def ws(sock):
        def on_message(msg):
            try: m = json.loads(msg)
            except Exception: return
            if isinstance(m, list): join_ref, ref, topic, event, payload = m
            else: join_ref, ref, topic, event, payload = m.get('join_ref'), m.get('ref'), m.get('topic'), m.get('event'), m.get('payload') or {}
            resp = {}
            if event == 'phx_join':
                pc = ((payload.get('config') or {}).get('postgres_changes')) or []
                resp = {'postgres_changes': [dict(x, id=i + 1) for i, x in enumerate(pc)]}
            out = {'status': 'ok', 'response': resp}
            if isinstance(m, list): sock.send(json.dumps([join_ref, ref, topic, 'phx_reply', out]))
            else: sock.send(json.dumps({'topic': topic, 'event': 'phx_reply', 'payload': out, 'ref': ref, 'join_ref': join_ref}))
        sock.on_message(on_message)
    context.route_web_socket(re.compile(r'^wss://.*supabase\.co/'), ws)


def login(page):
    page.goto(BASE + 'admin/'); page.wait_for_selector('#lPass', state='visible')
    page.fill('#lPass', 'test-password'); page.click('#lBtn')
    page.wait_for_selector('#tabbar:not([hidden])')
    page.wait_for_timeout(500)
