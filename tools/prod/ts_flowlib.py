"""Shared helpers for the HTTP flow tests (clones only)."""
import http.cookiejar, os, re, subprocess, urllib.error, urllib.parse, urllib.request

DB = PORT = BASE = None
results = []
_SLOT = os.environ.get('TS_SLOT', '0')   # slot N>0 rehearses from /opt/odoo/talentsearch_stage_sN
AP = '/opt/odoo/talentsearch_stage%s/addons,' % ('' if _SLOT == '0' else '_s' + _SLOT) + '/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons'


def setup(db, port):
    global DB, PORT, BASE
    assert db.startswith('eot_ts'), 'clones only'
    DB, PORT, BASE = db, port, 'http://127.0.0.1:%s' % port


def check(name, ok, detail=''):
    results.append(bool(ok))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)


def summary():
    print('SUMMARY %d/%d passed' % (sum(results), len(results)))


def shell(code):
    r = subprocess.run(['sudo', '-u', 'odoo', 'env', 'HOME=/opt/odoo', '/opt/odoo/venv/bin/python3', '/opt/odoo/odoo/odoo-bin', 'shell',
                        '-c', '/etc/odoo20.conf', '-d', DB, '--db-filter=^%s$' % DB, '--addons-path=' + AP,
                        '--no-http', '--log-level=warn'], input=code, text=True, capture_output=True, cwd='/tmp')
    return r.stdout + r.stderr


_ENSURED = set()


def ensure_user(login):
    pw_file = '/root/.ts_flow_%s_%s' % (DB, login.split('@')[0])
    if not os.path.exists(pw_file):
        pw = os.urandom(12).hex()
        old = os.umask(0o077); open(pw_file, 'w').write(pw); os.umask(old)
    if login not in _ENSURED:  # a re-used clone name can carry a stale password file: always upsert the user once per run
        pw = open(pw_file).read().strip()
        _ENSURED.add(login)
        shell(("u=env['res.users'].with_context(no_reset_password=True).search([('login','=','%s')])\n"
               "u=u or env['res.users'].with_context(no_reset_password=True).create({'name':'آزمون جریان','login':'%s','group_ids':[(6,0,[env.ref('base.group_portal').id])]})\n"
               "u.password=%r\nenv.cr.commit()\n") % (login, login, pw))
    return open(pw_file).read().strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def follow(client, loc, hops=3):
    """GET `loc` and follow up to `hops` redirects (the test client never does). Returns (status, location, body)."""
    path = path_of(loc)
    for _ in range(hops + 1):
        st, loc, body = client.req(path)
        if st in (301, 302, 303) and loc:
            path = path_of(loc)
            continue
        break
    return st, loc, body


def path_of(loc):
    s = urllib.parse.urlsplit(loc)
    return s.path + (('?' + s.query) if s.query else '')


class Client:
    def __init__(self, host):
        self.host = host
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect())

    OLD_RESULT = re.compile(r'^/my/workspaces/\d+/(a|p)/\d+$')

    def req(self, path, data=None, follow_old=True):
        """One request. S13 moved the result pages: the old `W/a/<id>` and `W/p/<id>` GET routes redirect to
        `W/clients/<c>/r/<attempt>`; older suites still ask for the old URLs, so that one redirect is followed
        (follow_old=False shows the redirect itself)."""
        st, loc, body = self._req(path, data)
        if follow_old and data is None and st in (302, 303) and self.OLD_RESULT.match(path.split('?')[0]) and '/clients/' in loc:
            return self._req(urllib.parse.urlsplit(loc).path)
        return st, loc, body

    def _req(self, path, data=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        path = urllib.parse.quote(path, safe="/?=&%:#;,+")  # hrefs carry raw Persian slugs
        r = urllib.request.Request(BASE + path, data=body, headers={'Host': self.host, 'X-Forwarded-Proto': 'https'})
        try:
            resp = self.op.open(r, timeout=60)
            return resp.status, resp.headers.get('Location', ''), resp.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get('Location', ''), e.read().decode('utf-8', 'ignore')

    def csrf(self, page):
        m = re.search(r'name="csrf_token" value="([^"]+)"', page)
        return m.group(1) if m else ''

    def login(self, login, pw):
        _, _, p = self.req('/web/login')
        st, loc, _ = self.req('/web/login', {'csrf_token': self.csrf(p), 'login': login, 'password': pw, 'redirect': '/my'})
        return st in (302, 303)


# ---------------------------------------------------------------------- a local fake Kavenegar (clones never text anyone)
CLONE_API_BASE = 'http://127.0.0.1:9/v1/%s/%s.json'     # what ts_db.sh sets on every clone: a closed local port
FAKE_REQS = []


def fake_kavenegar(port=None):
    """Start a local fake Kavenegar on 127.0.0.1 and point the clone at it (Kavenegar on, a fake key and line). A suite
    whose flows may send an SMS calls this first, so nothing depends on what an earlier suite left. At exit the clone goes
    back to the state ts_db.sh gave it: Kavenegar off, no key, the address on a closed local port. Returns FAKE_REQS, the
    list of (method path, params) the clone sent."""
    import atexit, http.server, json, threading
    port = port or 18092 + 10 * int(_SLOT)

    class Fake(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _do(self):
            n = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(n).decode() if n else ''
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            q.update(dict(urllib.parse.parse_qsl(body)))
            path = urllib.parse.urlsplit(self.path).path.split('/v1/', 1)[-1].split('/', 1)[-1][:-5]
            FAKE_REQS.append((path, q))
            ent = []
            if path in ('sms/send', 'sms/sendarray', 'verify/lookup'):
                rec = q.get('receptor', '')
                try:
                    recs = json.loads(rec) if rec.startswith('[') else rec.split(',')
                except ValueError:
                    recs = rec.split(',')
                for i, r in enumerate(recs):
                    ent.append({'messageid': 970000 + len(FAKE_REQS) * 100 + i, 'message': q.get('message', ''), 'status': 1,
                                'statustext': 'q', 'sender': '10004346', 'receptor': r, 'cost': 100})
            out = json.dumps({'return': {'status': 200, 'message': 'ok'}, 'entries': ent}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(out)

        do_GET = do_POST = do_DELETE = _do

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out = shell("""
assert env.cr.dbname.startswith('eot_ts')
env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', 'http://127.0.0.1:%d/v1/%%s/%%s.json')
c = env.company.sudo()
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346'})
env.cr.commit()
print('FAKEKV ok')
""" % port)
    assert 'FAKEKV ok' in out, out[-1500:]

    def _back():
        srv.shutdown()
        shell("""
assert env.cr.dbname.startswith('eot_ts')
env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', %r)
env.company.sudo().write({'kv_enabled': False, 'kv_api_key': False})
env.cr.commit()
""" % CLONE_API_BASE)
    atexit.register(_back)
    return FAKE_REQS
