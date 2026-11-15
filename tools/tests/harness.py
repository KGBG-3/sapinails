"""Test helpers: a local server for the site's files and a stand-in for the booking system.
Nothing here talks to the real database: every call the pages make is answered locally."""
import contextlib, functools, http.server, json, pathlib, socketserver, threading, datetime

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]


def axe_source():
    f = HERE / 'node_modules/axe-core/axe.min.js'
    if not f.exists(): raise SystemExit('The accessibility checker is missing. Run once, in tools/tests:  npm install axe-core')
    return f.read_text(encoding='utf-8')
PORT = 8765
BASE = f'http://localhost:{PORT}/'
SUPA = 'https://gjmeuimtupsordxqepcz.supabase.co'

INFO = {
    'now': None,
    'settings': {
        'slotMinutes': 30, 'bufferMinutes': 0, 'minNoticeMinutes': 120, 'maxDaysAhead': 30,
        'hours': {'0': [{'from': '09:00', 'to': '18:00'}], '1': [{'from': '09:00', 'to': '18:00'}], '2': [{'from': '09:00', 'to': '18:00'}],
                  '3': [{'from': '09:00', 'to': '18:00'}], '4': [{'from': '09:00', 'to': '16:00'}], '5': [], '6': []},
        'addons': ['פרנץ׳', 'ציורים או אבנים', 'השלמת ציפורן'], 'address': 'תל אביב', 'ownerPhone': '0543439530',
    },
    'services': [
        {'id': 'gel', 'name': 'לק ג׳ל (כולל מניקור)', 'minutes': 75, 'price': 130},
        {'id': 'build', 'name': 'בנייה בג׳ל', 'minutes': 120, 'price': 200},
        {'id': 'mani', 'name': 'מניקור', 'minutes': 30, 'price': 60},
        {'id': 'remove', 'name': 'הסרה בלבד', 'minutes': 30, 'price': 50},
    ],
}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


@contextlib.contextmanager
def server():
    handler = functools.partial(Quiet, directory=str(REPO))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('127.0.0.1', PORT), handler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
        try: yield
        finally: httpd.shutdown()


def mock_backend(context, booking_status='pending', calls=None, external=None, server='new'):
    """Answer the booking system's calls locally, and record any request that leaves the site.
    server: 'new' knows the field p_no_promo; 'old' answers like a database from before 2026-11-15
    (404, function not found, when the field is sent); 'down' fails every booking."""
    mode = server if isinstance(server, dict) else {'server': server}
    def supa(route):
        req = route.request
        name = req.url.rsplit('/', 1)[-1]
        body = json.loads(req.post_data or '{}')
        if calls is not None: calls.append((name, body))
        if name == 'public_info':
            info = dict(INFO); info['now'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            route.fulfill(status=200, content_type='application/json', body=json.dumps(info))
        elif name == 'public_busy':
            route.fulfill(status=200, content_type='application/json', body='[]')
        elif name == 'request_booking':
            if mode['server'] == 'down':
                return route.fulfill(status=503, content_type='application/json', body='{"message":"down"}')
            if mode['server'] == 'old' and 'p_no_promo' in body:
                return route.fulfill(status=404, content_type='application/json', body=json.dumps({'code': 'PGRST202', 'message': 'Could not find the function public.request_booking(...) in the schema cache'}))
            start = datetime.datetime.fromisoformat(body['p_start'].replace('Z', '+00:00'))
            svc = next(s for s in INFO['services'] if s['id'] == body['p_service'])
            res = {'ok': True, 'id': 'test-1', 'status': booking_status, 'service': svc['name'], 'price': svc['price'],
                   'start': start.isoformat(), 'end': (start + datetime.timedelta(minutes=svc['minutes'])).isoformat()}
            route.fulfill(status=200, content_type='application/json', body=json.dumps(res))
        else:
            route.fulfill(status=404, body='{}')
    context.route(SUPA + '/**', supa)

    def other(route):
        url = route.request.url
        if url.startswith(BASE) or url.startswith('data:') or url.startswith('blob:'):
            return route.fallback()
        if external is not None: external.append(url)
        route.abort()
    context.route(lambda url: not url.startswith(BASE) and not url.startswith(SUPA), other)


def axe(page, label, tags=('wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice')):
    page.evaluate(axe_source())
    res = page.evaluate("""(tags) => axe.run(document, { runOnly: { type: 'tag', values: tags } }).then(r => ({
        violations: r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map(n => ({ target: n.target.join(' '), html: n.html.slice(0, 160), summary: (n.failureSummary || '').split('\\n').slice(0, 3).join(' | ') })) })),
        incomplete: r.incomplete.map(v => ({ id: v.id, n: v.nodes.length })), passes: r.passes.length }))""", list(tags))
    print(f'--- axe: {label}: {len(res["violations"])} violation type(s), {res["passes"]} passing rules, to review by hand: {[(i["id"], i["n"]) for i in res["incomplete"]]}')
    for v in res['violations']:
        print(f'  [{v["impact"]}] {v["id"]}: {v["help"]} ({len(v["nodes"])} nodes)')
        for n in v['nodes'][:6]:
            print(f'      {n["target"]} :: {n["html"]}\n        {n["summary"]}')
    return res


def settle(page):
    """Fonts and every image (also the lazy ones) are in before a screenshot."""
    page.evaluate('document.fonts.ready')
    page.evaluate('''async () => {
        document.querySelectorAll('img[loading=lazy]').forEach(i => { i.loading = 'eager'; });
        await Promise.all([...document.images].map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; })));
        await Promise.all([...document.images].map(i => i.decode ? i.decode().catch(() => {}) : null));
    }''')
    page.wait_for_timeout(300)
