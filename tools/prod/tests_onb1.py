# onb1 (owner decisions 2026-10-12): panels need no approval (first-week invite limit, super-admin suspend, «پنل‌های
# تازه» list), the licence is a badge, and S-AUTH (one mobile sign-in: codes, lock, WebOTP line, names, sessions).
# Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits; never sends an SMS or an e-mail (no code here reaches a
# provider: codes are written straight into the code tables, and every request_code below stops before sending).
import importlib.util
import json
import os
import tempfile
import time
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_path

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=Exception, text=None):
    try:
        with env.cr.savepoint():
            fn()
    except exc as e:
        return text is None or text in str(e.args[0] if e.args else e)
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment']
AUD = env['ts.audit.event']
_n = [0]


def puser(phone=None):
    _n[0] += 1
    login = 'ts.onb1.%d@example.invalid' % _n[0]
    u = U.create({'name': 'آزمون onb1 %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
    if phone:
        u.partner_id.write({'ts_phone': phone, 'ts_phone_verified_at': fields.Datetime.now()})
    return u


def bo_panel(purpose, name):
    """A panel the EOT team made in the back office (not self-service)."""
    org = env['res.partner'].create({'name': name, 'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id,
                   **({'escalation_contact_id': org.id} if purpose == 'clinical' else {})})
    ws.state = 'active'
    return ws


def member(ws, role, **kw):
    return M.create(dict({'workspace_id': ws.id, 'user_id': puser().id, 'role': role}, **kw))


def load(module, rel):
    spec = importlib.util.spec_from_file_location('onb1_mig_%d' % len(results), os.path.join(get_module_path(module), rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


edu_inst = env['ts.instrument'].search([('state', '=', 'published'), ('code', '=', 'TALENT-INV-15')], limit=1) \
    or env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '!=', 'employment')], limit=1)
emp_inst = env['ts.instrument'].search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)

# ================================================================ A. no approval
sel = dict(W._fields['state'].selection)
check('A01 the panel states are draft / active / suspended / closed; «pilot» is gone',
      set(sel) == {'draft', 'active', 'suspended', 'closed'} and sel['suspended'] == 'متوقف', sel)
check('A02 the approval machinery is gone (no gated, approve, reject)',
      not any(f in W._fields for f in ('gated', 'approved_on', 'approved_by_id', 'rejection_note', 'rejected_on'))
      and not hasattr(W, 'action_approve') and not hasattr(W, 'action_reject'))
env.cr.execute("SELECT count(*) FROM ts_workspace WHERE state = 'pilot'")
check('A03 the clone holds no «pilot» panel after the upgrade', env.cr.fetchone()[0] == 0)
w7, w2 = W.browse(7).exists(), W.browse(2).exists()
check('A04 live workspace 7 (clinical, waited for approval) is active; workspace 2 (closed) stays closed',
      (not w7 or w7.state == 'active') and (not w2 or w2.state == 'closed'), (w7.state if w7 else '-', w2.state if w2 else '-'))

owner_u = puser()
kinds = {}
for kind, extra in (('school', {}), ('org', {}), ('clinic', {'escalation_ok': True}),
                    ('solo', {'solo_as': 'psychologist', 'escalation_ok': True, 'license_number': 'PSY-77'}), ('solo', {'solo_as': 'hr'})):
    u = puser()
    ws = W.ts_panel_create(u, 'پنل onb1 %s %s' % (kind, extra.get('solo_as', '')), kind, terms=True, **extra)
    kinds[(kind, extra.get('solo_as'))] = (ws, M.search([('workspace_id', '=', ws.id)]))
check('A05 every kind of self-service panel is active at once and marked self-service',
      all(ws.state == 'active' and ws.self_service for ws, _ in kinds.values()), [(k, w.state) for k, (w, _) in kinds.items()])
check('A06 every owner can invite participants at once (invites, bulk, import)',
      all(m.can_act() and m.can_invite_participants() and {'invites:create'} <= m.perms() for _, m in kinds.values()))
ws_org, own_org = kinds[('org', None)]
a_org = A.create({'workspace_id': ws_org.id, 'instrument_id': emp_inst.id, 'invitee_name': 'داوطلب onb1'})
check('A07 a participant invitation in a brand-new employment panel is created (the HR invite was blocked before)', a_org.state == 'invited')
check('A08 nobody is e-mailed when a panel is created; a back-office note is left',
      env['mail.message'].search_count([('model', '=', 'ts.workspace'), ('res_id', '=', ws_org.id),
                                        ('subtype_id', '=', env.ref('mail.mt_note').id)]) >= 1)
act = env.ref('ts_core.ts_workspace_pending_action')
check('A09 back office: «پنل‌های تازه (۷ روز)» opens on the 7-day filter, the menu is for platform managers only',
      act.name == 'پنل‌های تازه (۷ روز)' and 'search_default_new7' in (act.context or '')
      and env.ref('ts_core.group_ts_manager') in env.ref('ts_core.menu_ts_pending').group_ids)
new7 = W.search([('create_date', '>=', fields.Datetime.now() - timedelta(days=7))])
check('A10 the new panels of the week are found by that filter', all(ws in new7 for ws, _ in kinds.values()))

# migration (pre / post) on synthetic rows, inside this transaction
pre = load('ts_core', 'migrations/20.0.2.0.0/pre-migrate.py')
post = load('ts_core', 'migrations/20.0.2.0.0/post-migrate.py')
wp = bo_panel('clinical', 'پنل onb1 قدیمی در انتظار')
wc = bo_panel('education', 'پنل onb1 بسته')
wc.state = 'closed'
mp = member(wp, 'clinician')
env.cr.execute("UPDATE ts_workspace SET state = 'pilot' WHERE id = %s", [wp.id])
env.cr.execute("UPDATE ts_workspace_member SET verification_state = 'pending', license_number = NULL WHERE id = %s", [mp.id])
aud0 = AUD.search_count([('event_type', '=', 'workspace.state'), ('workspace_id', '=', wp.id)])
pre.migrate(env.cr, '20.0.1.1.0')
env.invalidate_all()
check('M01 migration: a «pilot» panel becomes active with one audit row; a closed panel stays closed',
      wp.state == 'active' and wc.state == 'closed'
      and AUD.search_count([('event_type', '=', 'workspace.state'), ('workspace_id', '=', wp.id)]) == aud0 + 1)
check('M02 migration: a «pending» member without a licence number gets no badge state', mp.verification_state == 'not_required')
pre.migrate(env.cr, '20.0.1.1.0')
env.invalidate_all()
check('M03 migration is idempotent (a second run moves nothing)',
      AUD.search_count([('event_type', '=', 'workspace.state'), ('workspace_id', '=', wp.id)]) == aud0 + 1)
ws_old_self = bo_panel('education', 'پنل onb1 سلف‌سرویس قدیمی')
AUD.log('workspace.self_create', ws_old_self, workspace=ws_old_self, kind='school')
post.migrate(env.cr, '20.0.1.1.0')
env.invalidate_all()
check('M04 migration marks old self-service panels (audit workspace.self_create) and leaves back-office panels alone',
      ws_old_self.self_service and not wp.self_service)

# ================================================================ B. first-week invitation limit
ws_q, own_q = kinds[('school', None)]
q = ws_q.ts_invite_quota()
check('B01 a new self-service panel has 50 invitations per 24 hours', q == (50, 50), q)
check('B02 the invite forms show a calm line with Persian digits', '۵۰' in (ws_q.ts_invite_quota_note() or ''), ws_q.ts_invite_quota_note())
check('B03 a back-office panel has no such limit', bo_panel('education', 'پنل onb1 دفتر').ts_invite_quota() is None)
for i in range(48):
    A.create({'workspace_id': ws_q.id, 'instrument_id': edu_inst.id, 'invitee_name': 'شرکت‌کنندهٔ سهمیه %d' % i})
check('B04 48 invitations leave 2', ws_q.ts_invite_quota() == (50, 2), ws_q.ts_invite_quota())
K, C = env['ts.campaign'], env['ts.panel.client']
camp = K.create({'workspace_id': ws_q.id, 'name': 'گروه onb1', 'instrument_id': edu_inst.id, 'kind': 'list', 'created_by_id': own_q.id})
cl3 = C.browse()
for i in range(3):
    cl3 |= C.create({'workspace_id': ws_q.id, 'name': 'عضو گروه onb1 %d' % i})
n_before = A.search_count([('workspace_id', '=', ws_q.id)])
check('B05 a list campaign larger than what is left is refused whole, before anything is made',
      raises(lambda: camp.ts_launch(cl3), UserError, 'امروز فقط ۲ دعوت دیگر') and A.search_count([('workspace_id', '=', ws_q.id)]) == n_before)
camp.ts_launch(cl3[:2])
check('B06 a batch that fits goes through and fills the day', ws_q.ts_invite_quota() == (50, 0))
check('B07 the 51st invitation of the day is refused with a clear Persian message',
      raises(lambda: A.create({'workspace_id': ws_q.id, 'instrument_id': edu_inst.id, 'invitee_name': 'یکی بیشتر'}), UserError, 'سهم ۲۴ ساعت گذشته پر شده'))
oc = K.create({'workspace_id': ws_q.id, 'name': 'پیوند باز onb1', 'instrument_id': edu_inst.id, 'kind': 'open_link',
               'created_by_id': own_q.id, 'open_max': 5})
joined = oc.ts_join(puser(), 'دانش‌آموز پیوند باز')
check('B08 a self-join through an open/class link is not counted (it has its own limits)', joined and joined.channel == 'open_link')
env.cr.execute("UPDATE ts_workspace SET create_date = now() - interval '8 days' WHERE id = %s", [ws_q.id])
ws_q.invalidate_recordset(['create_date'])
check('B09 after the first week the limit is gone', ws_q.ts_invite_quota() is None
      and not raises(lambda: A.create({'workspace_id': ws_q.id, 'instrument_id': edu_inst.id, 'invitee_name': 'هفتهٔ دوم'})))
ws_p, _ = kinds[('solo', 'hr')]
env['ir.config_parameter'].sudo().set_str('ts_panel.new_panel_daily_invites', '3')
check('B10 the daily number is a setting (ts_panel.new_panel_daily_invites)', ws_p.ts_invite_quota() == (3, 3))
env['ir.config_parameter'].sudo().set_str('ts_panel.new_panel_daily_invites', '50')

# ================================================================ C. suspend (replaces approval)
ws_s, own_s = kinds[('clinic', None)]
inv_s = A.create({'workspace_id': ws_s.id, 'instrument_id': edu_inst.id, 'invitee_name': 'مراجع onb1'})
part = puser()
check('C01 a panel owner cannot suspend', raises(lambda: ws_s.with_user(own_s.user_id).action_suspend()))
ws_s.action_suspend()
check('C02 the super admin suspends: state, time and audit row',
      ws_s.state == 'suspended' and ws_s.suspended_on and AUD.search_count([('event_type', '=', 'workspace.suspend'), ('workspace_id', '=', ws_s.id)]) == 1)
check('C03 members only see the panel (no invitations, no results)', not own_s.can_act() and own_s.perms() == {'panel:view'})
check('C04 no new invitation in a suspended panel',
      raises(lambda: A.create({'workspace_id': ws_s.id, 'instrument_id': edu_inst.id, 'invitee_name': 'تازه'}), ValidationError))
check('C05 an open invitation cannot be accepted while suspended (no new attempt)',
      raises(lambda: inv_s.action_accept(part, share=True), UserError, 'موقتاً متوقف'))
check('C06 the owners are told in the panel', env['ts.notification'].search_count(
      [('user_id', '=', own_s.user_id.id), ('type', '=', 'panel_suspended')]) == 1)
ws_s.action_resume()
check('C07 resume returns the panel to active and the invitation can be accepted again',
      ws_s.state == 'active' and not ws_s.suspended_on and inv_s.action_accept(part, share=True))

# a suspended panel sends nothing (risk review): automatic or manual reminders, staff SMS, HR e-mail, invitation SMS
from odoo.addons.ts_panel.models import notify as nt
inv_r = A.create({'workspace_id': ws_s.id, 'instrument_id': edu_inst.id, 'invitee_name': 'یادآوری onb1'})
env.cr.execute("UPDATE ts_assignment SET create_date = now() - interval '10 days' WHERE id = %s", [inv_r.id])
inv_r.invalidate_recordset(['create_date'])
today = env['ts.notification']._tehran_now().date()
due_active = inv_r._ts_reminder_due(today)
ws_s.action_suspend()
inv_r.sudo().write({'invitee_phone': '09127779941', 'sms_consent': True})
check('C08 an open invitation of a suspended panel is never due for the automatic reminder', due_active and not inv_r._ts_reminder_due(today))
check('C09 no reminder by the cron path or by hand', inv_r._ts_do_reminder() == set() and inv_r.reminder_count == 0
      and inv_r.ts_manual_reminder(own_s)[0] is False)
env.company.sudo().write({'kv_enabled': True, 'ts_sms_staff': True, 'ts_sms_invite': True})
own_s.user_id.partner_id.write({'ts_phone': '09127779942', 'ts_phone_verified_at': fields.Datetime.now()})
calls, NN = [], env['ts.notification'].sudo()
with patch.object(nt.TsNotification, '_send_sms', lambda self, *a, **k: calls.append(a) or True), \
        patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: False):
    for t in ('result_ready_staff', 'panel_suspended'):
        NN.create({'user_id': own_s.user_id.id, 'workspace_id': ws_s.id, 'type': t, 'title': t})._sms_leg()
check('C10 staff SMS of a suspended panel: none, except the notice of the suspension itself', len(calls) == 1, len(calls))
with patch.object(type(inv_r), '_ts_email_enabled', lambda self: True):
    hire = inv_r._ts_send_template('ts_hire.mail_reminder', email_to='onb1@example.invalid')
check('C11 no HR e-mail from a suspended panel', hire == (False, 'پنل فعال نیست'), hire)
sent = []
with patch.object(type(env['sms.sms']), 'send', lambda self, *a, **k: sent.append(1)):
    sms_ok = inv_r._ts_send_invite_sms()
check('C12 no invitation SMS from a suspended panel', sms_ok is False and not sent)
ws_s.action_resume()

# ================================================================ D. licence badge
wcl = bo_panel('clinical', 'مرکز onb1 پروانه')
cl = member(wcl, 'clinician')
check('D01 a clinician joins without a licence number: no badge, full work', cl.verification_state == 'not_required'
      and cl.can_act() and cl.has_perm('results:clinical'))
cl.write({'license_number': 'NZ-123'})
check('D02 a number added later starts unverified; access unchanged', cl.verification_state == 'pending' and cl.has_perm('results:clinical'))
cl.action_verify()
check('D03 the super admin verifies: badge «پروانهٔ تأییدشده» with who and when',
      cl.verification_state == 'verified' and cl.verified_by_id and cl.verified_on
      and dict(M._fields['verification_state'].selection)['verified'] == 'پروانهٔ تأییدشده')
check('D04 reports print the licence only when verified', cl.ts_license_shown() == 'NZ-123')
cl.write({'license_number': 'NZ-123', 'title': 'مشاور'})
check('D05 saving the same number keeps the badge', cl.verification_state == 'verified')
cl.write({'license_number': 'NZ-124'})
check('D06 editing the number resets the badge to unverified; not printed on reports',
      cl.verification_state == 'pending' and not cl.verified_by_id and cl.ts_license_shown() is False)
cl.action_unverify()
check('D07 «تأیید نشد» hides the badge but never the work', cl.verification_state == 'rejected' and cl.can_act())
check('D08 a portal member cannot verify', raises(lambda: cl.with_user(cl.user_id).action_verify()))
cl.ts_brand_save(cl, {'license_number': '  ۹۸-۷۶۵ '})
check('D09 the member edits his own number (Persian digits normalised); it starts unverified',
      cl.license_number == '98-765' and cl.verification_state == 'pending', cl.license_number)
other = member(wcl, 'clinic_director')
try:
    with env.cr.savepoint():
        cl.ts_brand_save(other, {'license_number': 'X-1', 'title': 'مشاور ارشد'})
except UserError:
    pass
check('D10 a director cannot change a counselor\'s licence number (only the member himself)', cl.license_number == '98-765')
inviter = member(wcl, 'owner')
inv_m = env['ts.member.invite'].ts_create(inviter, 'clinician', phone_raw='09127779931')
joiner = puser('09127779931')
mj = inv_m.action_accept(joiner)
check('D11 joining as a clinician needs no licence number', mj.role == 'clinician' and mj.verification_state == 'not_required' and mj.can_act())
own_np = member(wcl, 'owner')
check('D12 A5b kept: a counseling-center owner who does not counsel never gets the full report',
      not own_np.has_perm('results:clinical') and own_np.has_perm('invites:create'))
check('D13 an owner who says «I counsel here» must give a licence number (self-declared, risk review)',
      raises(lambda: own_np.ts_set_practising(own_np, True), UserError, 'شمارهٔ پروانه') and not own_np.owner_practices)
own_np.ts_set_practising(own_np, True, 'NZ-555')
listed = M.search([('role', '=', 'owner'), ('owner_practices', '=', True), ('workspace_id.purpose', '=', 'clinical')])
check('D14 with the number: full reports at once, badge unverified, audit row, listed «مالک مشاور شد (بررسی پروانه)»',
      own_np.has_perm('results:clinical') and own_np.verification_state == 'pending' and own_np.practising_since
      and AUD.search_count([('event_type', '=', 'member.practice'), ('res_id', '=', own_np.id)]) >= 1 and own_np in listed
      and env.ref('ts_org.ts_member_practising_action').name == 'مالک مشاور شد (بررسی پروانه)')
check('D15 a solo psychologist panel needs the number too',
      raises(lambda: W.ts_panel_create(puser(), 'پنل onb1 روان‌شناس', 'solo', solo_as='psychologist', terms=True,
                                       escalation_ok=True), UserError, 'شمارهٔ پروانه'))
nn = puser()
nn.partner_id.write({'ts_name_unknown': True})
check('D16 an account without a name cannot become a member (colleagues see members by name)',
      raises(lambda: M.create({'workspace_id': wcl.id, 'user_id': nn.id, 'role': 'clinician'}), UserError, 'نام'))

# ================================================================ E. S-AUTH (models)
from odoo.addons.ts_sms.models import signup_otp as so
from odoo.addons.ts_sms.models import ir_http as tsih
from odoo.addons.ts_sms.models.res_partner import fmt_mobile

company = env.company.sudo()
company.write({'kv_enabled': True, 'ts_sms_otp': True})      # no send happens below: every request stops earlier
check('E01 codes accept Persian/Arabic digits, spaces and dashes', so.clean_code(' ۱۲۳ ٤٥-6 ') == '123456')
check('E02 the mobile is shown formatted with Persian digits', fmt_mobile('09123456789') == '۰۹۱۲ ۳۴۵ ۶۷۸۹')
OTP = env['ts.signup.otp'].sudo()
PH = '09127779901'


def code_row(phone, code='123456'):
    return OTP.create({'phone': phone, 'salt': 's', 'code_hash': so._h('s', code), 'expires_at': fields.Datetime.now() + timedelta(minutes=5)})


IP_A, IP_B = '203.0.113.7', '198.51.100.9'
Lock = env['ts.signup.lock'].sudo()
lock_row = lambda phone, ip: Lock.search([('phone', '=', phone), ('ip_hash', '=', '*' if ip == '*' else Lock._key(ip))])
r1 = code_row(PH)
check('E03 a code shorter than six digits is «short» and costs no attempt', OTP.verify_code(PH, '12345', IP_A) == (False, 'short') and r1.attempts == 0)
for _ in range(5):
    OTP.verify_code(PH, '000000', IP_A)
check('E04 wrong codes are counted per number and address, and per number for the day',
      lock_row(PH, IP_A).wrong == 5 and lock_row(PH, '*').wrong == 5 and r1.attempts == 5)
check('E05 the sixth try on the same code is refused (5 per code, as before)', OTP.verify_code(PH, '123456', IP_A) == (False, 'attempts'))
r2 = code_row(PH)
check('E06 a new code does not reset the wrong-code count', lock_row(PH, IP_A).wrong == 5)
outs = [OTP.verify_code(PH, '000000', IP_A) for _ in range(5)]
la = lock_row(PH, IP_A)
check('E07 the 10th wrong code from one address locks the number there for 15 minutes', outs[-1] == (False, 'locked') and la.locked_until
      and 14 * 60 < (la.locked_until - fields.Datetime.now()).total_seconds() <= 15 * 60, outs)
r3 = code_row(PH, '654321')
check('E08 from that address even the right code is refused, and no new code is sent',
      OTP.verify_code(PH, '654321', IP_A) == (False, 'locked') and OTP.request_code(PH, IP_A) == (False, 'locked', PH))
check('E08b a stranger cannot lock the owner out: the right code still works from another address',
      OTP.verify_code(PH, '654321', IP_B) == (True, None))
la.locked_until = fields.Datetime.now() - timedelta(seconds=1)
code_row(PH, '765432')
check('E09 after the lock the right code works there too and that count is cleared', OTP.verify_code(PH, '۷۶۵ ۴۳۲', IP_A) == (True, None) and la.wrong == 0)
PG, outs = '09127779905', []
for i in range(30):
    if i % 5 == 0:
        code_row(PG, '999999')
    outs.append(OTP.verify_code(PG, '000000', '10.0.0.%d' % (i // 9))[1])
g = lock_row(PG, '*')
code_row(PG, '999999')
check('E09c 30 wrong codes within a day, from any addresses, lock the number everywhere for 1 hour',
      outs[-1] == 'locked' and 'locked' not in outs[:-1] and g.locked_until
      and 59 * 60 < (g.locked_until - fields.Datetime.now()).total_seconds() <= 60 * 60
      and OTP.verify_code(PG, '999999', '10.9.9.9') == (False, 'locked'), outs[-3:])
r10 = code_row('09127779902')
# create_date is the start of this (long) test transaction: stamp the row with the wall clock, as a real request would
env.cr.execute("UPDATE ts_signup_otp SET create_date = clock_timestamp() AT TIME ZONE 'UTC' WHERE id = %s", [r10.id])
r10.invalidate_recordset(['create_date'])
check('E10 the resend countdown follows the server cooldown (about 60 s)', 55 <= OTP.seconds_to_resend('09127779902') <= 60)
check('E11 a number never asked has no countdown', OTP.seconds_to_resend('09127779903') == 0)

host = env['ts.phone.otp']._ts_otp_host()
code_row('09127779904', '111111')
body = env['ts.phone.otp'].with_context(ts_otp_kind='signup')._ts_otp_body('482913', '09127779904')
lines = body.split('\n')
check('E12 sign-in SMS: «استعدادیاب / کد ورود / ...», the last line «@host #code» in Latin digits, under 140 characters',
      lines[0] == 'استعدادیاب' and lines[1] == 'کد ورود: 482913' and lines[-1] == '@%s #482913' % host and len(body) <= 140, body)
check('E13 the WebOTP host is talentsearch.ir (the site of website 4)', host.endswith('talentsearch.ir'), host)
fb = env['ts.phone.otp'].with_context(ts_otp_kind='other')._ts_otp_body('112233', None)
check('E14 the fallback text (no template) keeps the WebOTP line', fb.split('\n')[-1] == '@%s #112233' % host and len(fb) <= 140, fb)

ua, ub = puser('09127779911'), puser()
Owner = env['res.users']
check('E15 the owner of a number is found by verified mobile and by login', Owner.ts_phone_owner('09127779911') == ua)
r16 = env['ts.phone.otp'].request_code(ub, '۰۹۱۲۷۷۷۹۹۱۱')
blk = env['ts.phone.otp'].sudo().search([('user_id', '=', ub.id)], limit=1)
check('E16 /my/phone never reveals that another account holds a number: same answer as a send, no SMS, every code refused',
      r16 == (True, None) and blk.blocked and blk.phone == '09127779911'
      and env['ts.phone.otp'].verify_code(ub, '123456') == (False, 'wrong', None), r16)
check('E16b the cooldown applies first, as for any number',
      env['ts.phone.otp'].request_code(ub, '09127779911') == (False, 'cooldown'))
PO = env['ts.phone.otp'].sudo()
PO.create({'user_id': ub.id, 'phone': '09127779912', 'salt': 'x', 'code_hash': PO._hash('x', '246810'),
           'expires_at': fields.Datetime.now() + timedelta(minutes=5)})
check('E17 /my/phone accepts Persian digits and spaces', PO.verify_code(ub, '۲۴۶ ۸۱۰') == (True, None, '09127779912'))
check('E18 /my/phone says «کد ۶ رقمی است» for a short code', PO.verify_code(ub, '۲۴۶') == (False, 'short', None))

np = env['res.partner'].with_context(ts_name_placeholder=True).create({'name': '0912 777 9921', 'ts_name_unknown': True})
check('E19 a mobile-only account has no name for the site', np.ts_known_name() == '' and np.name == '0912 777 9921')
np.with_context(ts_name_placeholder=True).write({'phone': '09127779921'})
check('E20 internal writes keep «name unknown»', np.ts_name_unknown)
np = env['res.partner'].browse(np.id)          # a plain environment, as on the account page
np.write({'name': 'مینا آزمون'})
check('E21 a real name ends «name unknown»', not np.ts_name_unknown and np.ts_known_name() == 'مینا آزمون')

# ---------------------------------------------------------------- sessions: only 'long' ones outlive Odoo's own limit
tmp = tempfile.mkdtemp(prefix='onb1_sess_')
os.makedirs(os.path.join(tmp, 'ab'))
now = time.time()
spec = {'young': ({'uid': 5}, 0), 'old_plain': ({'uid': 5}, 10), 'old_long': ({'uid': 5, 'ts_session_mode': 'long'}, 10),
        'old_browser': ({'uid': 5, 'ts_session_mode': 'browser'}, 10), 'ancient_long': ({'uid': 5, 'ts_session_mode': 'long'}, 40)}
for name, (data, days) in spec.items():
    p = os.path.join(tmp, 'ab', name)
    with open(p, 'w') as f:
        json.dump(data, f)
    os.utime(p, (now - days * 86400, now - days * 86400))


class _Store:
    path = tmp


with patch.object(tsih, 'session_store', lambda: _Store()), patch.object(tsih, 'get_session_max_inactivity', lambda e: 7 * 86400):
    env['ir.http']._gc_sessions()
left = sorted(os.listdir(os.path.join(tmp, 'ab')))
check('E22 session clean-up: a 10-day-old «personal device» session stays; plain, browser-only and >30-day ones go',
      left == ['old_long', 'young'], left)
check('E23 the 30-day cookie length is 2592000 s', tsih.LONG_SESSION_S == 2592000)


class _Sess(dict):
    def __init__(self, uid, **kw):
        super().__init__(**kw)
        self.uid = uid


pu, ts_site, eot_site = puser(), env.ref('ts_website.website_ts'), env['website'].browse(1)
check('E24 the 30-day cookie only for a portal account on talentsearch.ir that chose it (not for staff, not on eot.ir)',
      tsih.cookie_mode(_Sess(pu.id, ts_session_mode='long'), pu, ts_site) == 'long'
      and tsih.cookie_mode(_Sess(pu.id, ts_session_mode='browser'), pu, ts_site) == 'browser'
      and tsih.cookie_mode(_Sess(pu.id, ts_session_mode='long'), pu, eot_site) is None
      and tsih.cookie_mode(_Sess(2, ts_session_mode='long'), env.ref('base.user_admin'), ts_site) is None
      and tsih.cookie_mode(_Sess(pu.id), pu, ts_site) is None and tsih.cookie_mode(_Sess(None, ts_session_mode='long'), None, ts_site) is None)

# ================================================================ S. return paths (risk review): one validator
from odoo.addons.ts_core.safe_url import local_path
from odoo.addons.ts_sms.controllers.signup import safe_next
BAD = ['//evil.com', '/\\evil.com', '/%09/evil.com', '/%2F/evil.com', '/%2f%2fevil.com', '/%5C/evil.com', '/%5c/evil.com',
       '/\t/evil.com', '/\n/evil.com', ' //evil.com', '\t//evil.com', '/%0a/evil.com', '/%0d%0a//evil.com', 'https://evil.com',
       'HTTPS://evil.com', 'javascript:alert(1)', '//', 'evil.com', '/my\\x', '', None, '/\x00x', '/ x', '/%5C%5Cevil.com']
GOOD = ['/my', '/my/workspaces/3?tab=1', '/invite/abc-123', '/assessments/%D9%81%D9%87%D8%B1%D8%B3%D8%AA', '/signup?next=/my']
check('S01 a return path is refused when it could lead elsewhere (tab, newline, encoded, backslash, scheme, //)',
      all(local_path(b) == '/my' and safe_next(b) == '/my' for b in BAD), [b for b in BAD if local_path(b) != '/my'])
check('S02 ordinary paths of the site are kept', all(local_path(g) == g for g in GOOD), [g for g in GOOD if local_path(g) != g])

# migration: a member with a number but no state at all becomes «registered, not yet checked»
env.cr.execute("ALTER TABLE ts_workspace_member ALTER COLUMN verification_state DROP NOT NULL")
mm = member(wcl, 'clinician')
env.cr.execute("UPDATE ts_workspace_member SET verification_state = NULL, license_number = 'NZ-9' WHERE id = %s", [mm.id])
pre.migrate(env.cr, '20.0.1.1.0')
env.invalidate_all()
check('M05 migration: a licence number without a state becomes «ثبت‌شده، هنوز تأیید نشده»', mm.verification_state == 'pending')

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
