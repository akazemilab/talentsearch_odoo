from datetime import datetime, timedelta
# Mobile sign-in (pre-login OTP), one-time login token and invite expiry. Run ONLY on an eot_ts* clone via odoo-bin shell.
from odoo.exceptions import AccessDenied, UserError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc):
    try:
        with env.cr.savepoint():
            fn()
    except exc:
        return True
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


def age(table, where, minutes=2):
    env.cr.execute("update %s set create_date = create_date - interval '%d minutes' where %s" % (table, minutes, where))
    env.invalidate_all()


c = env.company.sudo()
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_otp': True, 'ts_sms_otp_template_id': False})
Otp = env['ts.signup.otp']
sent = []
Phone = type(env['ts.phone.otp'])
orig = Phone._send_code


def fake(self, company, phone, code):
    sent.append((phone, code))
    return True


Phone._send_code = fake
try:
    P = '09121112222'
    check('bad number refused', Otp.request_code('123')[:2] == (False, 'format'))
    c.ts_sms_otp = False
    check('disabled until the owner turns OTP on', Otp.request_code(P)[:2] == (False, 'disabled'))
    c.ts_sms_otp = True
    ok, why, phone = Otp.request_code('۰۹۱۲۱۱۱۲۲۲۲', '10.0.0.1')
    check('Persian digits accepted and normalised', ok and phone == P and sent[-1][0] == P)
    code = sent[-1][1]
    rec = Otp.sudo().search([('phone', '=', P)], limit=1)
    check('code is stored hashed, not in clear', code not in (rec.code_hash, rec.salt) and len(rec.code_hash) == 64)
    check('second request within a minute is refused', Otp.request_code(P, '10.0.0.1')[:2] == (False, 'cooldown'))
    check('wrong code refused', Otp.verify_code(P, '000000' if code != '000000' else '111111') == (False, 'wrong'))
    fa = code.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
    check('right code accepted (Persian digits too)', Otp.verify_code(P, fa) == (True, None))
    check('a code works once', Otp.verify_code(P, code) == (False, 'none'))

    age('ts_signup_otp', "phone = '%s'" % P)
    Otp.request_code(P, '10.0.0.1')
    code2 = sent[-1][1]
    wrong = '000000' if code2 != '000000' else '111111'
    for _ in range(5):
        Otp.verify_code(P, wrong)
    check('locked after 5 wrong tries, even with the right code', Otp.verify_code(P, code2) == (False, 'attempts'))

    age('ts_signup_otp', "phone = '%s'" % P)
    Otp.request_code(P, '10.0.0.1')
    Otp.sudo().search([('used', '=', False)], order='id desc', limit=1).write({'expires_at': datetime.utcnow() - timedelta(minutes=1)})
    env.flush_all()
    env.invalidate_all()
    res = Otp.verify_code(P, sent[-1][1])
    check('expired code refused', res == (False, 'expired'), str(res) + ' rows=%d' % Otp.sudo().search_count([('phone', '=', P), ('used', '=', False)]))

    for _ in range(6):
        age('ts_signup_otp', "phone = '%s'" % P)
        res = Otp.request_code(P, '10.0.0.1')
    check('per-phone hourly limit', res[:2] == (False, 'limit'), str(res[:2]))

    res = None
    for i in range(21):
        res = Otp.request_code('0912300%04d' % i, '10.9.9.9')
    check('per-IP hourly limit', res[:2] == (False, 'limit'), str(res[:2]))
    check('another IP is not affected', Otp.request_code('09123999999', '10.8.8.8')[0])
finally:
    Phone._send_code = orig

# ---- one-time login token consumed by the stock credential check
U = env['res.users'].with_context(no_reset_password=True)
u1 = U.create({'name': 'کاربر یک', 'login': '09125550001', 'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
u2 = U.create({'name': 'کاربر دو', 'login': '09125550002', 'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
T = env['ts.login.token']
tok = T.issue(u1)
info = u1.with_user(u1).sudo()._check_credentials({'type': 'ts_phone_login', 'login': u1.login, 'token': tok}, {})
check('token logs the right user in without a password', info['uid'] == u1.id and info['mfa'] == 'skip')
check('token is single use', raises(lambda: u1.with_user(u1).sudo()._check_credentials({'type': 'ts_phone_login', 'token': tok}, {}), AccessDenied))
tok2 = T.issue(u1)
check("one user's token does not work for another user", raises(lambda: u2.with_user(u2).sudo()._check_credentials({'type': 'ts_phone_login', 'token': tok2}, {}), AccessDenied))
env.cr.execute("update ts_login_token set expires_at = now() - interval '1 second' where user_id = %s", [u1.id])
check('expired token refused', raises(lambda: u1.with_user(u1).sudo()._check_credentials({'type': 'ts_phone_login', 'token': tok2}, {}), AccessDenied))
check('empty token refused', raises(lambda: u1.with_user(u1).sudo()._check_credentials({'type': 'ts_phone_login', 'token': ''}, {}), AccessDenied))
check('a wrong password still fails as before', raises(lambda: u1.with_user(u1).sudo()._check_credentials({'type': 'password', 'login': u1.login, 'password': 'nope-nope'}, {}), AccessDenied))

# ---- invite states
inst = env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
org = env['res.partner'].create({'name': 'سازمان دعوت', 'is_company': True})
ws = env['ts.workspace'].create({'name': 'دعوت آزمون', 'purpose': 'employment', 'partner_id': org.id})
ws.state = 'active'
A = env['ts.assignment']


def mk(n):
    return A.create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': n})


a = mk('تازه')
check('fresh invite is ok', a.invite_state() == 'ok')
b = mk('قدیمی')
age('ts_assignment', 'id = %d' % b.id, minutes=31 * 24 * 60)
b.invalidate_recordset()
check('invite older than 30 days is expired', b.invite_state() == 'expired')
check('expired invite cannot be accepted', raises(lambda: b.action_accept(u1, True), UserError))
d = mk('مهلت'); d.deadline = '2020-01-01'
check('passed deadline expires an unaccepted invite', d.invite_state() == 'expired')
e = mk('لغو'); e.action_withdraw()
check('withdrawn state', e.invite_state() == 'withdrawn')
f = mk('رد'); f.action_decline(u2)
check('declined state', f.invite_state() == 'declined')
g = mk('استفاده'); g.action_accept(u1, True)
check('used state after acceptance', g.invite_state() == 'used')
check('accepted invite stays acceptable for the same user', g.action_accept(u1, True) == g.attempt_id)

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
