# Webhook HTTP checks against a clone (usage: ts_http_kv.py DB PORT). Needs /tmp/kv_http_fixture.json from tests_kavenegar.py.
import json, sys, urllib.request, urllib.error
db, port = sys.argv[1], sys.argv[2]
assert db.startswith('eot_ts')
fx = json.load(open('/tmp/kv_http_fixture.json'))
res = []


def req(path, host, method='GET', data=None, headers=None):
    r = urllib.request.Request('http://127.0.0.1:%s%s' % (port, path), method=method, headers=dict(headers or {}, Host=host), data=data)
    try:
        with urllib.request.urlopen(r, timeout=30) as f:
            return f.status, f.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, ''


def check(n, ok, d=''):
    res.append(ok); print('%s  %s %s' % ('PASS' if ok else 'FAIL', n, d))


S, M = fx['secret'], fx['messageid']
ts = 'ts.innerquest.me'
st, body = req('/kavenegar/%s/status?messageid=%s&status=10&statustext=x' % (S, M), ts)
check('status GET on website 2 -> 200 OK', st == 200 and body == 'OK', '%s %s' % (st, body))
st, body = req('/kavenegar/%s/status' % S, ts, 'POST', ('messageid=%s&status=11' % M).encode(), {'Content-Type': 'application/x-www-form-urlencoded'})
check('status POST form -> 200', st == 200)
st, body = req('/kavenegar/%s/status' % S, ts, 'POST', json.dumps({'messageid': M, 'status': 10}).encode(), {'Content-Type': 'application/json'})
check('status POST json -> 200', st == 200)
st, _b = req('/kavenegar/WRONGSECRET/status?messageid=%s&status=10' % M, ts)
check('wrong secret -> 404', st == 404, str(st))
st, _b = req('/kavenegar/%s/status?messageid=%s&status=10' % (S, M), 'www.eot.ir')
check('eot.ir host -> 404 even with secret', st == 404, str(st))
st, _b = req('/kavenegar/%s/status?messageid=%s&status=10' % (S, M), 'eot.ir')
check('eot.ir apex -> 404', st == 404, str(st))
st, body = req('/kavenegar/%s/inbound' % S, ts, 'POST', 'from=09129998877&to=10004346&message=hello&messageid=88001&date=1700000000'.encode(), {'Content-Type': 'application/x-www-form-urlencoded'})
check('inbound POST -> 200', st == 200 and body == 'OK')
st, body = req('/kavenegar/%s/inbound?from=09129998877&to=10004346&message=hello2&messageid=88002' % S, ts)
check('inbound GET -> 200', st == 200)
print('SUMMARY %d/%d passed' % (sum(res), len(res)))
