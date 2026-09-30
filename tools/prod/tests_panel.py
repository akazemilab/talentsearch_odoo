# Panel self-service tests (ts_core/ts_org/ts_sms). Run ONLY on an eot_ts* clone via odoo-bin shell.
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=(UserError, ValidationError)):
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


def puser(n, phone=None, email=True):
    login = 'ts.panel.%s@example.invalid' % n
    u = U.search([('login', '=', login)], limit=1)
    if not u:
        u = U.create({'name': 'کاربر ' + n, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
    if phone:
        u.partner_id.sudo().write({'ts_phone': phone})
    return u


W = env['ts.workspace']
M = env['ts.workspace.member']
I = env['ts.member.invite']
AUD = env['ts.audit.event']

u1, u2, u3, u4 = puser('o1', '09120000001'), puser('o2', '09120000002'), puser('o3', '09120000003'), puser('o4', '09120000004')
u_col = puser('col', '09129990001')
u_other = puser('other', '09129990002')
u_cl = puser('clin', '09129990003')

# ---- creation: education is live at once
before_aud = AUD.search_count([('event_type', '=', 'workspace.self_create')])
ws1 = W.ts_panel_create(u1, 'TSP مدرسه', 'school', terms=True)
check('education panel is active at once', ws1.state == 'active' and not ws1.gated and ws1.purpose == 'education')
own = M.search([('workspace_id', '=', ws1.id)])
check('creator is the owner', len(own) == 1 and own.role == 'owner' and own.user_id == u1 and own.can_act())
check('terms version + time + user recorded', ws1.terms_version and ws1.terms_accepted_on and ws1.terms_accepted_by_id == u1)
check('self-create and terms accept are audit-logged',
      AUD.search_count([('event_type', '=', 'workspace.self_create')]) == before_aud + 1
      and AUD.search_count([('event_type', '=', 'workspace.terms_accept'), ('workspace_id', '=', ws1.id)]) == 1)
check('company partner is a company', ws1.partner_id.is_company)
check('education owner can invite participants at once', own.can_invite_participants())

# ---- creation: organization = limited pending mode
msgs_before = env['mail.message'].search_count([('model', '=', 'ts.workspace')])
ws2 = W.ts_panel_create(u2, 'TSP سازمان', 'org', terms=True)
o2 = M.search([('workspace_id', '=', ws2.id)])
check('organization panel starts in limited pilot and is gated', ws2.state == 'pilot' and ws2.gated)
check('pending owner can act (build panel) but not invite participants', o2.can_act() and o2.can_invite() and not o2.can_invite_participants())
inst = env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
check('participant invite refused while pending approval',
      raises(lambda: env['ts.assignment'].create({'workspace_id': ws2.id, 'instrument_id': inst.id, 'invitee_name': 'x'})))
check('platform admins are notified of the pending panel',
      env['mail.message'].search_count([('model', '=', 'ts.workspace')]) > msgs_before)

# ---- creation: clinic needs the escalation acceptance
check('clinic panel refused without escalation acceptance', raises(lambda: W.ts_panel_create(u3, 'TSP کلینیک', 'clinic', terms=True)))
ws3 = W.ts_panel_create(u3, 'TSP کلینیک', 'clinic', terms=True, escalation_ok=True)
check('clinic panel pending with escalation contact', ws3.gated and ws3.state == 'pilot' and ws3.escalation_contact_id == u3.partner_id)

# ---- creation: validation
check('terms are required', raises(lambda: W.ts_panel_create(u4, 'TSP بدون شرایط', 'school', terms=False)))
check('unknown kind refused', raises(lambda: W.ts_panel_create(u4, 'TSP x', 'bogus', terms=True)))
check('too-short name refused', raises(lambda: W.ts_panel_create(u4, 'x', 'school', terms=True)))
check('solo needs a valid work type', raises(lambda: W.ts_panel_create(u4, 'TSP solo', 'solo', solo_as='zzz', terms=True)))
ws4 = W.ts_panel_create(u4, 'TSP مستقل', 'solo', solo_as='counselor', terms=True)
check('solo counselor = one-person education panel', ws4.purpose == 'education' and ws4.state == 'active' and ws4.member_count == 1)
W.ts_panel_create(u4, 'TSP مستقل ۲', 'solo', solo_as='hr', terms=True)
W.ts_panel_create(u4, 'TSP مستقل ۳', 'solo', solo_as='psychologist', terms=True, escalation_ok=True)
check('more than 3 panels a day by one person refused', raises(lambda: W.ts_panel_create(u4, 'TSP چهارم', 'school', terms=True)))
pub = env['res.users'].browse(env.ref('base.public_user').id)
check('public visitor cannot create a panel', raises(lambda: W.ts_panel_create(pub, 'TSP عمومی', 'school', terms=True)))

# ---- profile
import base64
png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
ws1.ts_update_profile(name='TSP مدرسهٔ نو', logo_bytes=png)
check('profile rename + logo', ws1.name == 'TSP مدرسهٔ نو' and ws1.partner_id.name == 'TSP مدرسهٔ نو' and ws1.partner_id.image_1920)
check('non-image logo refused', raises(lambda: ws1.ts_update_profile(logo_bytes=b'<script>alert(1)</script>')))
check('fake PNG that cannot be decoded refused', raises(lambda: ws1.ts_update_profile(logo_bytes=b'\x89PNG\r\n\x1a\n' + b'0' * 50)))
check('oversized logo refused', raises(lambda: ws1.ts_update_profile(logo_bytes=b'\x89PNG\r\n\x1a\n' + b'0' * 600000)))

# ---- colleague invitations (ws2 = organization, owner o2)
inv = I.ts_create(o2, 'hr_admin', phone_raw='۰۹۱۲۹۹۹۰۰۰۱')
check('invite normalises Persian digits and builds a /join link', inv.phone == '09129990001' and '/join/' in inv.invite_url())
check('invite audit-logged', AUD.search_count([('event_type', '=', 'member.invite'), ('workspace_id', '=', ws2.id)]) >= 1)
check('duplicate pending invite refused', raises(lambda: I.ts_create(o2, 'hr_admin', phone_raw='09129990001')))
check('role outside the panel kind refused', raises(lambda: I.ts_create(o2, 'clinician', phone_raw='09129990009')))
check('bad phone refused', raises(lambda: I.ts_create(o2, 'hr_admin', phone_raw='12345')))
check('invite needs phone or email', raises(lambda: I.ts_create(o2, 'hr_admin')))
check('someone with the wrong number cannot accept', raises(lambda: inv.action_accept(u_other)))
check('anonymous cannot accept', raises(lambda: inv.action_accept(pub)))
m_col = inv.action_accept(u_col)
check('matching mobile accepts; member created with the role', m_col.role == 'hr_admin' and m_col.workspace_id == ws2 and inv.state == 'accepted')
check('used link cannot be reused', raises(lambda: inv.action_accept(u_other)))
check('accept audit-logged', AUD.search_count([('event_type', '=', 'member.invite_accept'), ('workspace_id', '=', ws2.id)]) == 1)
check('second admin can invite colleagues too', bool(I.ts_create(m_col, 'hiring_manager', email_raw='New.Person@Example.com')))
inv_e = I.search([('workspace_id', '=', ws2.id), ('email', '!=', False)], limit=1)
check('email invite is lower-cased', inv_e.email == 'new.person@example.com')
u_mail = U.create({'name': 'ایمیلی', 'login': 'new.person@example.com', 'email': 'new.person@example.com', 'group_ids': [(6, 0, [portal.id])]})
check('email identity accepts', inv_e.action_accept(u_mail).role == 'hiring_manager')
check('hiring manager cannot invite colleagues', raises(lambda: I.ts_create(M.search([('user_id', '=', u_mail.id)], limit=1), 'hiring_manager', phone_raw='09120001111')))
inv_x = I.ts_create(o2, 'hr_admin', phone_raw='09125550001')
inv_x.action_revoke()
check('revoked invite cannot be accepted', inv_x.state == 'revoked' and raises(lambda: inv_x.action_accept(puser('rev', '09125550001'))))
inv_old = I.ts_create(o2, 'hr_admin', phone_raw='09125550002')
inv_old.write({'expires_at': fields.Datetime.now() - timedelta(minutes=1)})
check('expired invite refused', inv_old.usable_state() == 'expired' and raises(lambda: inv_old.action_accept(puser('exp', '09125550002'))))
for i in range(30):
    try:
        with env.cr.savepoint():
            I.ts_create(o2, 'hr_admin', phone_raw='0913%07d' % (1000 + i))
    except UserError:
        break
check('pending invite cap is enforced', i < 25)

# ---- clinician invite needs a licence and starts unverified
oc = M.search([('workspace_id', '=', ws3.id)])
inv_c = I.ts_create(oc, 'clinician', phone_raw='09129990003')
check('clinician accept needs a licence number', raises(lambda: inv_c.action_accept(u_cl)))
mc = inv_c.action_accept(u_cl, license_number='TEST-99')
check('clinician joins unverified (cannot act yet)', mc.verification_state == 'pending' and not mc.can_act())

# ---- last owner can never be removed
check('the only owner cannot be deactivated', raises(lambda: own.write({'active': False})))
check('the only owner cannot be deleted', raises(lambda: own.unlink()))

# ---- platform admin side
check('pending queue action exists', bool(env.ref('ts_core.ts_workspace_pending_action')))
ws2.rejection_note = 'مدارک ناقص است'
ws2.action_reject()
check('reject records time + note, panel stays limited', ws2.rejected_on and ws2.gated and ws2.state == 'pilot')
check('reject audit-logged', AUD.search_count([('event_type', '=', 'workspace.reject'), ('workspace_id', '=', ws2.id)]) == 1)
ws2.action_approve()
check('approve lifts the gate and clears rejection', not ws2.gated and not ws2.rejected_on and ws2.approved_on)
check('after approval the owner can invite participants', o2.can_invite_participants())
a = env['ts.assignment'].create({'workspace_id': ws2.id, 'instrument_id': inst.id, 'invitee_name': 'x'})
check('participant invite works after approval', a.state == 'invited')
ws2.action_suspend()
check('suspend stops the panel', ws2.state == 'suspended' and not o2.can_act())
check('suspended panel refuses new participants', raises(lambda: env['ts.assignment'].create({'workspace_id': ws2.id, 'instrument_id': inst.id, 'invitee_name': 'y'})))
check('suspend audit-logged', AUD.search_count([('event_type', '=', 'workspace.suspend'), ('workspace_id', '=', ws2.id)]) == 1)
ws2.action_resume()
check('resume returns to pilot', ws2.state == 'pilot' and o2.can_act())
check('a panel owner cannot approve', raises(lambda: ws3.with_user(u3).action_approve(), (UserError, ValidationError, Exception)))


# ---- participant sends a finished self-taken result to a counselor panel (by code)
A = env['ts.assignment']
u_part, u_part2 = puser('part', '09128880001'), puser('part2', '09128880002')
at = env['ts.attempt'].create({'user_id': u_part.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
check('unfinished result cannot be shared', raises(lambda: A.ts_share_attempt(at, ws1.code, u_part)))
at.give_consent()
for it in at.active_items():
    at.save_answer(it.id, 1 + it.id % 5)
at.action_submit()
check('self-taken attempt is finished and has no panel', at.state == 'done' and not at.workspace_id)
check('usage is not recorded for self-taken attempts', not env['ts.usage.event'].search_count([('attempt_id', '=', at.id)]))
check('unknown panel code refused', raises(lambda: A.ts_share_attempt(at, 'TSW-99999', u_part)))
check('organization panel code is not a counselor panel', raises(lambda: A.ts_share_attempt(at, ws2.code, u_part)))
check('someone else cannot share my result', raises(lambda: A.ts_share_attempt(at, ws1.code, u_part2)))
sh = A.ts_share_attempt(at, ' ' + ws1.code.lower() + ' ', u_part)
check('share creates an accepted summary-level assignment in the education panel',
      sh.workspace_id == ws1 and sh.share_level == 'summary' and sh.user_id == u_part and sh.attempt_id == at and sh.state == 'done')
check('shared result lands in the unassigned queue', not sh.responsible_id)
check('panel owner sees the band summary, never raw answers', sh.visible_results(own)[0] == 'education')
check('share audit-logged', AUD.search_count([('event_type', '=', 'assignment.self_share'), ('workspace_id', '=', ws1.id)]) == 1)
check('second share of the same result refused', raises(lambda: A.ts_share_attempt(at, ws4.code, u_part)))
sh.action_revoke_share(u_part)
check('participant can stop sharing at any time', sh.visible_results(own)[0] == 'none')
print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
