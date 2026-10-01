# Panel v2 S3 (members, re-authentication). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.addons.ts_org.models.perms import ALL_PERMS
from odoo.addons.ts_panel.perm_labels import LIVE, PERM_LABELS, ROLE_ORDER

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=UserError):
    try:
        with env.cr.savepoint():
            fn()
    except exc:
        return True
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, I, A = env['ts.workspace'], env['ts.workspace.member'], env['ts.member.invite'], env['ts.assignment']
R = env['ts.reauth.code']
_n = [0]


def puser(phone=None):
    _n[0] += 1
    login = 'ts.pv2s3.%d@example.invalid' % _n[0]
    u = U.create({'name': login, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
    if phone:
        u.partner_id.sudo().write({'ts_phone': phone})
    return u


def panel(purpose):
    org = env['res.partner'].create({'name': 'پنل آزمون S3', 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': org.name, 'purpose': purpose, 'partner_id': org.id,
                   'escalation_contact_id': org.id if purpose == 'clinical' else False})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role, user=None):
    m = M.create({'workspace_id': ws.id, 'user_id': (user or puser()).id, 'role': role})
    if role in ('counselor', 'clinician'):
        m.write({'license_number': 'T', 'verification_state': 'verified'})
    return m


# --- labels
check('every permission has a Persian label and the registry has no extra', set(PERM_LABELS) == set(ALL_PERMS))
check('LIVE is a subset of the permissions', LIVE <= set(ALL_PERMS))
check('ROLE_ORDER covers each role once', len(set(ROLE_ORDER)) == len(ROLE_ORDER) == 8)

# --- invites
ws = panel('education')
o = member(ws, 'owner')
adm = member(ws, 'admin')
cou = member(ws, 'counselor')
inv = I.ts_create(o, 'counselor', phone_raw='09121110001')
old_token = inv.token
new = inv.ts_resend(o)
check('resend: old invite revoked and token differs', inv.state == 'revoked' and new.state == 'pending' and new.token != old_token)
check('resend: only a pending invite', raises(lambda: inv.ts_resend(o)))
check('resend: counselor cannot', raises(lambda: new.ts_resend(cou)))
check('resend of an owner invite by an admin refused', raises(lambda: I.ts_create(adm, 'owner', phone_raw='09121110002')))

# --- change role, clients, last owner
inst = env['ts.instrument'].search([], limit=1)
a1 = A.sudo().create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'مراجع S3',
                      'invited_by_id': o.user_id.id, 'responsible_id': cou.id})
check('client count counts the responsible member', cou.ts_client_count() == 1)
check('admin cannot change roles', raises(lambda: cou.ts_change_role(adm, 'admin')))
check('role outside the purpose refused', raises(lambda: cou.ts_change_role(o, 'clinician')))
check('change to the same role is a no-op', cou.ts_change_role(o, 'counselor') is False)
check('counselor -> admin works', cou.ts_change_role(o, 'admin') is True and cou.role == 'admin')
check('and the client goes back to the unassigned queue', not a1.responsible_id)
check('making an owner needs the owner', raises(lambda: adm.ts_change_role(adm, 'owner')))
check('last owner cannot be demoted', raises(lambda: o.ts_change_role(o, 'admin'), (UserError, ValidationError)))
cou.ts_change_role(o, 'owner')
env.flush_all()
check('a second owner can be made by an owner', cou.role == 'owner')
check('now the first owner can step down', o.ts_change_role(cou, 'admin') and o.role == 'admin')
check('sole owner cannot be deactivated', raises(lambda: cou.ts_deactivate(cou), (UserError, ValidationError)))

# --- deactivate / reactivate
c2 = member(ws, 'counselor')
a2 = A.sudo().create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'مراجع دو',
                      'invited_by_id': cou.user_id.id, 'responsible_id': c2.id})
check('deactivate returns the number of released clients', c2.ts_deactivate(cou) == 1)
env.flush_all()
check('deactivated: inactive and client released', not c2.active and not a2.responsible_id and c2.ts_state_key() == 'inactive')
check('deactivate twice refused', raises(lambda: c2.ts_deactivate(cou)))
c2.ts_reactivate(cou)
check('reactivate', c2.active and raises(lambda: c2.ts_reactivate(cou)))
check('counselor cannot deactivate others', raises(lambda: c2.ts_deactivate(c2)))

# --- practising owner
cl = panel('clinical')
co = member(cl, 'owner')
check('practising owner in a clinical panel needs a licence', raises(lambda: co.ts_set_practising(co, True)))
co.ts_set_practising(co, True, 'N-123')
check('with a licence it is saved', co.owner_practices and co.license_number == 'N-123')
check('only the owner for themselves', raises(lambda: co.ts_set_practising(member(cl, 'admin'), True)))

# --- re-authentication codes (the sender is patched: no real SMS from a clone)
nophone = puser()
check('no verified mobile: password path', R.ts_phone_of(nophone) is False and R.ts_request(nophone) == (False, 'nophone'))
u = puser('09125550101')
sent = []
with patch('odoo.addons.ts_sms.models.phone_otp.TsPhoneOtp._send_code', autospec=True,
           side_effect=lambda self, company, phone, code: sent.append((phone, code)) or True):
    ok, why = R.ts_request(u)
    check('code goes to the verified mobile only', ok and len(sent) == 1 and sent[0][0] == u.partner_id.ts_phone)
    check('cooldown blocks a second request', R.ts_request(u) == (False, 'cooldown'))
    code = sent[0][1]
    wrong = '000000' if code != '000000' else '111111'
    check('wrong code refused', R.ts_verify(u, wrong) == (False, 'wrong'))
    fa = code.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
    check('Persian digits accepted', R.ts_verify(u, fa) == (True, None))
    check('a code works once', R.ts_verify(u, code) == (False, 'none'))
    R.search([('user_id', '=', u.id)]).unlink()
    R.ts_request(u)
    rec = R.search([('user_id', '=', u.id)], limit=1)
    rec.expires_at = '2000-01-01 00:00:00'
    check('expired code refused', R.ts_verify(u, sent[-1][1]) == (False, 'expired'))
    rec.write({'expires_at': '2999-01-01 00:00:00', 'attempts': 99})
    check('too many attempts refused', R.ts_verify(u, sent[-1][1]) == (False, 'attempts'))

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
