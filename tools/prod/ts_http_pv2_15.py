#!/usr/bin/env python3
"""Panel v2 S15 (participant home, account, sharing, my data) over HTTP against a served CLONE:  ts_http_pv2_15.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell, path_of = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell, lib.path_of
TS = 'talentsearch.ir'
NAMES = ('new', 'res', 'inv', 'going', 'other', 'cns')
L = {n: 'ts.pv2s15.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}

code = r"""
L = %r
from odoo import fields
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
    return ws
E1, E2, E3 = panel('پنل S15 یک', 'education'), panel('پنل S15 دو', 'education'), panel('پنل S15 سه', 'education')
EMP = panel('پنل S15 کاری', 'employment')
cns_u = user('cns')
m = env['ts.workspace.member'].search([('workspace_id', '=', E1.id), ('user_id', '=', cns_u.id)]) or env['ts.workspace.member'].create(
    {'workspace_id': E1.id, 'user_id': cns_u.id, 'role': 'counselor'})
m.write({'license_number': 'T-1', 'verification_state': 'verified'})
inst = env['ts.instrument'].search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)
talent = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1)
T = env['ts.attempt']
def finish(att):
    att.give_consent()
    for it in att.active_items():
        att.save_answer(it.id, 1 + it.id %% 5)
    att.action_submit()
def finish_matrix(att):
    att.give_consent()
    items = att.active_items()
    for n, label in enumerate(['ریاضی', 'هنر']):
        f = att.ts_add_field(label)
        for i, it in enumerate(items):
            att.ts_save_cell(f, it.id, (i * (n %% 3 + 1) + 2 * n + i // 5) %% 5 + 1)
        att.ts_finish_field(f)
    assert att.action_submit()
res = user('res')
at = T.search([('user_id', '=', res.id), ('instrument_id', '=', inst.id), ('state', '=', 'done')], limit=1)
if not at:
    at = T.create({'user_id': res.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id}); finish(at)
tat = T.search([('user_id', '=', res.id), ('instrument_id', '=', talent.id), ('state', '=', 'done')], limit=1)
if not tat:
    tat = T.create({'user_id': res.id, 'instrument_id': talent.id, 'version_id': talent.current_version_id.id}); finish_matrix(tat)
A = env['ts.assignment']
for ws in (E1, E2, E3):
    if not A.search_count([('attempt_id', '=', at.id), ('workspace_id', '=', ws.id)]):
        A.ts_share_attempt(at, ws.code, res)
# the counselor of E1 opens the result (one audit event with a member)
if not env['ts.audit.event'].search_count([('event_type', '=', 'result.view'), ('res_id', '=', at.id), ('workspace_id', '=', E1.id)]):
    env['ts.audit.event'].with_user(cns_u).log('result.view', at, workspace=E1, member=m, level='education')
# a client of the employment panel linked to the account 'inv' with a waiting invitation
inv_u = user('inv')
cl = env['ts.panel.client'].search([('workspace_id', '=', EMP.id), ('user_id', '=', inv_u.id)], limit=1) or env['ts.panel.client'].create(
    {'workspace_id': EMP.id, 'name': 'دعوت‌شدهٔ S15', 'user_id': inv_u.id})
ia = A.search([('client_id', '=', cl.id)], limit=1) or A.create({'workspace_id': EMP.id, 'instrument_id': inst.id, 'invitee_name': 'دعوت‌شدهٔ S15', 'client_id': cl.id})
# an unfinished attempt of 'going'
go_u = user('going')
ga = T.search([('user_id', '=', go_u.id), ('state', 'in', ('consent', 'in_progress'))], limit=1)
if not ga:
    ga = T.create({'user_id': go_u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id}); ga.give_consent()
env.cr.commit()
print('IDS', at.id, tat.id, E1.id, E2.id, E3.id, ia.id, ga.id, ga.access_token, ia.token)
""" % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\S+) (\S+)', out)
assert mm, out[-1500:]
AT, TAT, E1, E2, E3, IA, GA, GTOK, ITOK = mm.groups()


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


new, res, inv, going, other, cns = (login(n) for n in NAMES)

# ---- PRT-1 home
check('anonymous /my goes to sign in', Client(TS).req('/my')[0] in (302, 303))
st, body = get(new, '/my')
check('a new user sees the empty home with one primary action', st == 200 and 'ts-home-empty' in body and '/assessments' in body and 'ts-home-results' not in body, str(st))
check('the home has the participant navigation', '/my/sharing' in body and '/my/assessments' in body and '/my/account' in body   # portal v3: four destinations, privacy sits under the account hub)
st, body = get(inv, '/my')
check('an invited user sees the waiting invitation with its link', st == 200 and 'ts-home-invites' in body and '/invite/%s' % ITOK in body)
st, body = get(going, '/my')
check('a user with an unfinished attempt sees the resume card', st == 200 and 'ts-home-going' in body and '/take/%s' % GTOK in body)
st, body = get(res, '/my')
check('a user with results sees them and the sharing count', st == 200 and 'ts-home-results' in body and '/my/assessments/%s' % AT in body and 'به اشتراک گذاشته' in body)
check('the home of a user with results does not offer the empty card', 'ts-home-empty' not in body)
e = Client('www.eot.ir'); e.login(L['new'], pw[L['new']])
st, body = get(e, '/my')
check('eot.ir /my is the stock page, not ours', st == 200 and 'ts-home-' not in body and 'tsp-section' not in body, str(st))
check('eot.ir has none of the new pages', all(e.req(p)[0] == 404 for p in ('/my/sharing', '/my/privacy')))

# ---- ACC-1, ACC-2 account
st, body = get(new, '/my/account')
check('the account page shows the name form and the phone link', st == 200 and 'acc-name' in body and '/my/phone' in body and 'acc-contact' in body)
check('the login email is shown', L['new'] in body)
st, loc, _ = post(new, '/my/account/name', {'name': '  نام   تازهٔ   آزمون  '})
check('saving the name redirects back', st in (302, 303) and path_of(loc) == '/my/account', '%s %s' % (st, loc))
check('the name is stored with spaces collapsed', 'نام تازهٔ آزمون' in q("select name from res_partner where id=(select partner_id from res_users where login='%s')" % L['new']))
st, loc, _ = post(new, '/my/account/name', {'name': 'x'})
st2, body = get(new, '/my/account')
check('a one-letter name is refused and the old one stays', 'نام باید' in body and 'نام تازهٔ آزمون' in body)
check('anonymous cannot save a name', Client(TS).req('/my/account/name', [('name', 'مهاجم')])[0] in (302, 303, 400, 403, 404))
check('eot.ir account page is stock (no name form of ours)', 'acc-name' not in get(e, '/my/account')[1])

# ---- PRV-2, AUD-4 sharing page
st, body = get(res, '/my/sharing')
check('the sharing page lists the three panels', st == 200 and all(n in body for n in ('پنل S15 یک', 'پنل S15 دو', 'پنل S15 سه')), str(st))
check('...with the level in words and the specialist state', 'بدون پاسخ‌های خام' in body and 'هنوز تعیین نشده' in body)
check('...a revoke button for each', body.count('لغو اشتراک با این پنل') >= 3)
check('...views by role and date, never a name', 'مشاور' in body and 'ts-sharing-row' in body)
check('...the panel that has not opened it says so', 'هنوز نتیجه را باز نکرده است' in body)
st, body = get(new, '/my/sharing')
check('a user without results sees the empty state', st == 200 and 'هنوز نتیجه‌ای ندارید' in body)
sid = re.search(r'/my/sharing/(\d+)/revoke', get(res, '/my/sharing')[1]).group(1)
st, _, _ = post(other, '/my/sharing/%s/revoke' % sid)
check('another user cannot revoke my share (404)', st == 404, str(st))
check('...and it stays active', "'summary'" in q("select share_level from ts_assignment where id=%s" % sid))
st, loc, _ = post(res, '/my/sharing/%s/revoke' % sid)
check('I revoke one panel', st in (302, 303) and path_of(loc) == '/my/sharing', '%s %s' % (st, loc))
check('...it is now none in the database', "'none'" in q("select share_level from ts_assignment where id=%s" % sid))
check('...a share_revoke ledger row exists', "(1,)" in q("select count(*) from ts_consent_record where assignment_id=%s and kind='share_revoke'" % sid) or
      "(2,)" in q("select count(*) from ts_consent_record where assignment_id=%s and kind='share_revoke'" % sid))
body = get(res, '/my/sharing')[1]
check('...the page shows two active panels and the send-to-counselor link again', body.count('لغو اشتراک با این پنل') == 2 and '/share' in body)
revoked_ws = q("select workspace_id from ts_assignment where id=%s" % sid)
wid = re.search(r'\d+', revoked_ws).group(0)
wcode = re.search(r"'([^']+)'", q("select code from ts_workspace where id=%s" % wid)).group(1)
st, loc, _ = post(res, '/my/assessments/%s/share/confirm' % AT, {'code': wcode})
check('re-sharing with the same panel through the old form works', st in (302, 303), '%s %s' % (st, loc))
check('...the same record is active again', "'summary'" in q("select share_level from ts_assignment where id=%s" % sid))
check('...no second row for that panel', "(1,)" in q("select count(*) from ts_assignment where attempt_id=%s and workspace_id=%s" % (AT, wid)))

# ---- report blocks (PRT-3)
st, body = get(res, '/my/assessments/%s' % AT)
check('the instrument report has the who-can-see block with the panels', st == 200 and 'ts-who-sees' in body and 'پنل S15 یک' in body)
st, body = get(res, '/my/assessments/%s' % TAT)
check('the talent report has the who-can-see block (no sharing yet)', st == 200 and 'ts-who-sees' in body and 'فقط شما' in body)
check('the block links to the sharing page', '/my/sharing' in body)

# ---- ACC-5, ACC-6 my data
st, body = get(res, '/my/privacy')
check('the privacy page offers export and erase', st == 200 and 'prv-export' in body and 'prv-erase' in body and 'prv-list' in body)
st, loc, _ = post(res, '/my/privacy/export')
check('an export without a fresh re-authentication goes to /my/reauth', st in (302, 303) and '/my/reauth' in loc, '%s %s' % (st, loc))
st, loc, _ = post(res, '/my/reauth/verify', {'password': pw[L['res']], 'next': '/my/privacy'})
check('re-authentication with the password succeeds', st in (302, 303) and path_of(loc) == '/my/privacy', '%s %s' % (st, loc))
st, loc, _ = post(res, '/my/privacy/export')
check('the export request redirects to the job page', st in (302, 303) and '/my/privacy/jobs/' in loc, '%s %s' % (st, loc))
jp = path_of(loc)
st, body = get(res, jp)
check('the job page says the file is ready with a download button', st == 200 and 'prv-download' in body, str(st))
st, loc2, body = res.req(jp + '/download')
check('the download is a ZIP', st == 200 and body[:2] == 'PK', '%s %r' % (st, body[:4]))
check('another user gets 404 on my job page and file', get(other, jp)[0] == 404 and other.req(jp + '/download')[0] == 404)
check('anonymous gets sent to sign in', Client(TS).req(jp + '/download')[0] in (302, 303))
check('eot.ir has no such page', e.req(jp)[0] == 404)
jid = re.search(r'/jobs/(\d+)', jp).group(1)
shell("from odoo import fields; job = env['ts.job'].browse(%s); job.expires_at = fields.Datetime.subtract(fields.Datetime.now(), minutes=5); env.cr.commit()" % jid)
check('after the expiry the download is refused', res.req(jp + '/download')[0] == 404)
st, body = get(res, jp)
check('...and the page explains it', st == 200 and 'prv-download' not in body)
st, loc, _ = post(res, '/my/privacy/erase')
body = get(res, '/my/privacy')[1]
check('an erase request is recorded and shown with its state', st in (302, 303) and 'حذف داده‌ها' in body and 'ثبت شد' in body)
st, loc, _ = post(res, '/my/privacy/erase')
body = get(res, '/my/privacy')[1]
check('a second erase request is refused with a message', 'پیش‌تر ثبت شده' in body)
check('the erase request only exists as a record (nothing erased)', "'done'" in q("select state from ts_attempt where id=%s" % AT))
check('only one open erase request', "(1,)" in q("select count(*) from ts_data_request r join res_users u on u.id=r.user_id where u.login='%s' and r.kind='erase'" % L['res']))
check('the new user has none of my requests', 'ثبت شد' not in get(new, '/my/privacy')[1].split('prv-list')[1])

summary()
