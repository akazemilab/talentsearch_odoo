#!/usr/bin/env python3
"""Panel v2 S16 (minors, guardian consent) over HTTP against a served CLONE:  ts_http_pv2_16.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('adult', 'teen', 'noage', 'owner')
L = {n: 'ts.pv2s16.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
org = env['res.partner'].search([('name', '=', 'S16 http school')], limit=1) or env['res.partner'].create({'name': 'S16 http school', 'is_company': True})
org.write({'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'S16 http school', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
ou = user('owner')
env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', ou.id)]) or env['ts.workspace.member'].create(
    {'workspace_id': ws.id, 'user_id': ou.id, 'role': 'owner'})
mc = env['ts.panel.client'].search([('workspace_id', '=', ws.id), ('name', '=', 'S16 minor http')], limit=1) or env['ts.panel.client'].create(
    {'workspace_id': ws.id, 'name': 'S16 minor http', 'age_group': 'minor'})
inst = env['ts.instrument'].search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)
T = env['ts.attempt']
toks = []
for n in ('adult', 'teen', 'noage'):
    u = user(n)
    a = T.search([('user_id', '=', u.id), ('state', '=', 'consent')], limit=1) or T.create(
        {'user_id': u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
    toks.append(a.access_token)
env.cr.commit()
print('IDS', ws.id, mc.id, inst.id, *toks)
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\S+) (\S+) (\S+)', out)
assert mm, out[-1500:]
WS, MC, INST, T_ADULT, T_TEEN, T_NOAGE = mm.groups()


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def get(c, path):
    for _ in range(4):
        st, loc, body = c.req(path)
        if st in (301, 302, 303) and loc:
            path = path_of(loc)
            continue
        break
    return st, body


def post(c, path, data=None):
    pairs = list((data or {}).items())
    pairs.append(('csrf_token', c.csrf(c.req('/web/login')[2])))
    return c.req(path, pairs)


def q(sql):
    o = shell("cr = env.cr; cr.execute(%r); print('Q', cr.fetchall())" % sql)
    m = re.findall(r'^Q (.*)$', o, re.M)
    return m[-1] if m else o


# ---- consent page: the age question
ad = login('adult')
st, page = get(ad, '/take/%s' % T_ADULT)
check('the consent page asks for the age', st == 200 and 'age18' in page and 'ts-age-box' in page, st)
st, loc, _ = post(ad, '/take/%s/consent' % T_ADULT, {'consent_service': '1'})
check('no age answer: refused', 'error=age' in (loc or ''), loc)
st, loc, _ = post(ad, '/take/%s/consent' % T_ADULT, {'consent_service': '1', 'age18': 'yes'})
check('an adult goes on', st in (302, 303) and 'error' not in (loc or ''), loc)
check('an adult has a service ledger row and no guardian row',
      "(1,)" in q("select count(*) from ts_consent_record r join ts_attempt a on a.id=r.attempt_id where a.access_token='%s' and r.kind='service'" % T_ADULT)
      and "(0,)" in q("select count(*) from ts_consent_record r join ts_attempt a on a.id=r.attempt_id where a.access_token='%s' and r.kind='guardian'" % T_ADULT))

te = login('teen')
st, loc, _ = post(te, '/take/%s/consent' % T_TEEN, {'consent_service': '1', 'age18': 'no'})
check('under 18 without a guardian tick: refused', 'error=guardian_ok' in (loc or ''), loc)
st, page = get(te, '/take/%s?error=guardian_ok' % T_TEEN)
check('the refusal is explained on the page', 'ولی یا سرپرست' in page)
st, loc, _ = post(te, '/take/%s/consent' % T_TEEN, {'consent_service': '1', 'age18': 'no', 'guardian_ok': '1'})
check('under 18 with a guardian tick goes on', st in (302, 303) and 'error=age' not in (loc or '') and 'error=guardian_ok' not in (loc or ''), loc)
check('a guardian ledger row exists for the teen',
      "(1,)" in q("select count(*) from ts_consent_record r join ts_attempt a on a.id=r.attempt_id where a.access_token='%s' and r.kind='guardian' and r.given_as='guardian'" % T_TEEN))

# ---- the wizard asks the panel to attest a minor's guardian consent
ow = login('owner')
base = '/my/workspaces/%s/invites/new' % WS
post(ow, base, {'step': '1', 'choose': MC})
post(ow, base, {'step': '2', 'instrument_id': INST})
post(ow, base, {'step': '3'})
st, page = get(ow, base + '?step=4')
check('review step shows the guardian tick for a minor', 'ts-guardian-box' in page and 'guardian_ok' in page, st)
st, loc, _ = post(ow, base, {'step': '4'})
check('creating without the tick is refused', '/invites/' not in (loc or '') or 'step=4' in (loc or ''), loc)
check('no invitation was made without the tick', "(0,)" in q("select count(*) from ts_assignment where client_id=%s" % MC))
st, loc, _ = post(ow, base, {'step': '4', 'guardian_ok': '1'})
check('with the tick the invitation is created', st in (302, 303) and '/invites/' in (loc or '') and 'step=4' not in (loc or ''), loc)
check('the client is attested and the ledger has the row',
      "('attested',)" in q("select guardian_consent from ts_panel_client where id=%s" % MC)
      and "(1,)" in q("select count(*) from ts_consent_record where kind='guardian_attest' and client_id=%s" % MC))

summary()
