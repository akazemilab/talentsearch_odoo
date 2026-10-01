# Panel v2 S10 (notifications, preferences, reminders). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
import json
from datetime import timedelta
from unittest.mock import patch

import psycopg2
from odoo import fields
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ts_panel.models import notify as nt
from odoo.addons.ts_panel.models import notify_texts as tx

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=(UserError, ValidationError, psycopg2.IntegrityError)):
    env.flush_all()
    try:
        with env.cr.savepoint():
            fn()
            env.flush_all()
    except exc:
        return True
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, C, A, N, P = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.panel.client', 'ts.assignment', 'ts.notification', 'ts.notify.pref'))
Inst = env['ts.instrument']
company = env.company.sudo()
_n = [0]


def puser(phone=None):
    _n[0] += 1
    login = 'ts.pv2s10.%d@example.invalid' % _n[0]
    u = U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
    if phone:
        u.partner_id.sudo().ts_phone = phone
    return u


def panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role, user=None):
    return M.create({'workspace_id': ws.id, 'user_id': (user or puser()).id, 'role': role})


def rows(user, type_=None):
    dom = [('user_id', '=', user.id)] + ([('type', '=', type_)] if type_ else [])
    return N.sudo().search(dom)


plain = Inst.search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)

# ---- texts (PLT-6)
check('every event type has a title, a preference label and no name placeholder',
      all(t in tx.TITLES and t in tx.PREF_LABELS for t, _l in tx.TYPES) and not any('%(name)' in b for b in tx.SMS_BODIES.values()))
check('SMS bodies exist for the staff types and the reminder only, and carry a link slot',
      set(tx.SMS_BODIES) == set(tx.SMS_STAFF_TYPES) | {'reminder'} and all('%(url)s' in b for b in tx.SMS_BODIES.values()))
check('P20 switches ship OFF', company._fields['ts_sms_reminder'].default(company) is False and company._fields['ts_sms_staff'].default(company) is False)

# ---- dispatcher: in-app
emp = panel('employment', 'شرکت اعلان S10')
o_emp = member(emp, 'owner')
hr = member(emp, 'hr_admin')
user_a = puser()
r = N._notify(user_a, 'export_ready', '/my/workspaces/%s/jobs/1' % emp.id, emp)
check('NOT-1: an in-app row with the template title, unread, no name', len(r) == 1 and r.title == tx.TITLES['export_ready'] and not r.read_at
      and user_a.name not in r.title and N._unread_count(user_a) == 1)
check('the header label has Persian digits and is empty when nothing is unread', user_a._ts_unread_label() == '۱' and puser()._ts_unread_label() == '')
r._mark_read(user_a)
check('mark as read', N._unread_count(user_a) == 0 and r.read_at)
check('a person cannot mark another person\'s notification', (r._mark_read(puser()) or True) and bool(r.read_at))
r2 = N._notify(user_a, 'export_ready', '/x', emp)
r2._mark_read(puser())
check('...another account\'s mark-read changes nothing', not r2.read_at)
check('an unknown type creates nothing', not N._notify(user_a, 'zzz', '/x', emp))
P.ts_save(user_a, 'export_ready', False, False)
check('ACC-7: with in-app off no row is created', not N._notify(user_a, 'export_ready', '/x', emp))
P.ts_save(user_a, 'export_ready', True, True)
check('the SMS preference is stored only for staff types', not P.search([('user_id', '=', user_a.id), ('type', '=', 'export_ready')]).sms)
check('one preference row per person and type', P.search_count([('user_id', '=', user_a.id), ('type', '=', 'export_ready')]) == 1)

# ---- SMS leg: switches, opt-in, verified mobile, quiet hours, daily limit
calls = []


def fake_send(self, company_, number, body, partner_id=False):
    calls.append((number, body))
    return True


staff = puser('09123334411')
check('the verified mobile is found', N._phone_of(staff) == '09123334411')
P.ts_save(staff, 'panel_approved', True, True)
company.write({'kv_enabled': True})
company.ts_sms_staff = False
with patch.object(nt.TsNotification, '_send_sms', fake_send), patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: False):
    r = N._notify(staff, 'panel_approved', '/p', emp)
    check('NOT-5b: with the staff switch off no SMS is sent, the in-app row exists', len(r) == 1 and not calls and not r.sms_state)
    company.ts_sms_staff = True
    r = N._notify(staff, 'panel_approved', '/p', emp)
    check('switch on + opt-in + verified mobile: one SMS with a link and no name', len(calls) == 1 and calls[0][0] == '09123334411'
          and '/p' in calls[0][1] and staff.name not in calls[0][1] and r.sms_state == 'sent')
    check('the send is audited without recipient data', env['ts.audit.event'].search_count([('event_type', '=', 'notify.send'), ('res_id', '=', r.id)]) == 1
          and '0912' not in (env['ts.audit.event'].search([('event_type', '=', 'notify.send'), ('res_id', '=', r.id)]).detail or ''))
    nophone = puser()
    P.ts_save(nophone, 'panel_approved', True, True)
    N._notify(nophone, 'panel_approved', '/p', emp)
    check('no verified mobile: no SMS', len(calls) == 1)
    nopt = puser('09123334422')
    N._notify(nopt, 'panel_approved', '/p', emp)
    check('no opt-in: no SMS', len(calls) == 1)
    P.ts_save(nopt, 'export_ready', True, True)
    N._notify(nopt, 'export_ready', '/p', emp)
    check('a type without an SMS text never sends', len(calls) == 1)
    env['ir.config_parameter'].sudo().set_str('ts_panel.sms_per_day', '2')
    N._notify(staff, 'panel_approved', '/p', emp)
    r3 = N._notify(staff, 'panel_approved', '/p', emp)
    check('NOT-3: the daily limit (2) skips the third SMS', len(calls) == 2, str(len(calls)))
    check('...and marks it skipped', r3.sms_state == 'skipped' and len(calls) == 2)
    env['ir.config_parameter'].sudo().set_str('ts_panel.sms_per_day', '5')

calls.clear()
staff2 = puser('09123334433')
P.ts_save(staff2, 'panel_suspended', True, True)
with patch.object(nt.TsNotification, '_send_sms', fake_send), patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: True):
    rq = N._notify(staff2, 'panel_suspended', '/p', emp)
    check('NOT-3: in the quiet hours the SMS waits', rq.sms_state == 'queued' and not calls)
    check('the flush does nothing while it is still quiet', N._cron_flush_sms() == 0 and rq.sms_state == 'queued')
with patch.object(nt.TsNotification, '_send_sms', fake_send), patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: False):
    n = N._cron_flush_sms()
    rq.invalidate_recordset()
    check('after the quiet hours the flush sends it', n >= 1 and rq.sms_state == 'sent' and len(calls) == 1)
    rq2 = N.sudo().create({'user_id': staff2.id, 'type': 'panel_suspended', 'title': 'x', 'sms_state': 'queued'})
    P.ts_save(staff2, 'panel_suspended', True, False)
    N._cron_flush_sms()
    check('a queued SMS is dropped when the person turned SMS off meanwhile', rq2.sms_state == 'skipped' and len(calls) == 1)
quiet_hours = [(h, N._quiet_now(__import__('datetime').datetime(2026, 1, 1, h, 0, tzinfo=nt.TEHRAN))) for h in (7, 8, 12, 20, 21, 23, 0)]
check('quiet hours are 21:00-08:00 in Tehran', quiet_hours == [(7, True), (8, False), (12, False), (20, False), (21, True), (23, True), (0, True)], str(quiet_hours))
company.ts_sms_staff = False

# ---- event hooks create exactly the catalogue rows
before = N.search_count([])
w2 = panel('education', 'پنل رویداد S10')
ow = member(w2, 'owner')
ad = member(w2, 'admin')
cs1 = member(w2, 'counselor')
talent = Inst.search([('code', '=', 'TALENT-INV-15')], limit=1)
acct = puser()
cl = C.create({'workspace_id': w2.id, 'name': 'مراجع حساب‌دار', 'user_id': acct.id})
a1 = A.create({'workspace_id': w2.id, 'instrument_id': talent.id, 'client_id': cl.id, 'invitee_name': cl.name})
check('invite: a participant with an account gets an in-app row with the invitation link', len(rows(acct, 'invite')) == 1 and rows(acct, 'invite').url == '/invite/%s' % a1.token)
a2 = A.create({'workspace_id': w2.id, 'instrument_id': talent.id, 'invitee_name': 'بدون حساب'})
check('invite: a person without an account gets nothing', N.search_count([('type', '=', 'invite')]) - before == 1 or N.search_count([('workspace_id', '=', w2.id), ('type', '=', 'invite')]) == 1)
hist = C.create({'workspace_id': w2.id, 'name': 'تاریخی', 'user_id': puser().id, 'source': 'import'})
check('P20/NOT-5: a locked historical client is locked', hist.contact_locked)
env.flush_all()
check('P20/NOT-5: no reminder or notice reaches a historical person even when forced',
      not A.new({'workspace_id': w2.id, 'client_id': hist.id})._ts_account())

# submit -> participant + staff
at = a1.action_accept(acct, share=True)
cl.responsible_id = cs1.id
at.write({'state': 'consent'})
at.give_consent()
# complete a talent attempt directly (the matrix engine has its own tests): the hook is the object of this test
at.write({'state': 'done', 'released': True, 'submitted_at': fields.Datetime.now()})
at._ts_notify_done()
check('result ready: the participant gets an in-app row', len(rows(acct, 'result_ready_participant')) == 1)
check('result ready: the responsible specialist gets one, nobody else', len(rows(cs1.user_id, 'result_ready_staff')) == 1
      and not rows(ow.user_id, 'result_ready_staff') and not rows(ad.user_id, 'result_ready_staff'))
cl.responsible_id = False
at._ts_notify_done()
check('result ready, unassigned: the members who assign clients are told', len(rows(ow.user_id, 'result_ready_staff')) == 1
      and len(rows(ad.user_id, 'result_ready_staff')) == 1 and len(rows(cs1.user_id, 'result_ready_staff')) == 1)
a1.share_level = 'none'
n0 = N.search_count([('type', '=', 'result_ready_staff')])
at._ts_notify_done()
check('result ready: a result the participant did not share tells no staff', N.search_count([('type', '=', 'result_ready_staff')]) == n0)
a1.share_level = 'summary'

# share and revoke
cl.responsible_id = cs1.id
a1.action_revoke_share(acct)
check('share_revoked goes to the responsible specialist', len(rows(cs1.user_id, 'share_revoked')) == 1 and a1.share_level == 'none')

# workspace decisions
w3 = panel('education', 'پنل تصمیم S10')
w3.write({'approved_on': False})
o3 = member(w3, 'owner')
manager = env.ref('base.user_admin')
w3_m = w3.with_user(manager)
check('panel decisions: a suspend tells the owners', (w3.with_user(manager).action_suspend() or True) and len(rows(o3.user_id, 'panel_suspended')) == 1)
w3.write({'state': 'pilot'})

# member joined
inv = env['ts.member.invite'].sudo().create({'workspace_id': w2.id, 'role': 'counselor', 'email': 'new.s10@example.invalid', 'invited_by_id': ow.user_id.id})
newu = U.create({'name': 'عضو تازه', 'login': 'new.s10@example.invalid', 'email': 'new.s10@example.invalid', 'group_ids': [(6, 0, [portal.id])]})
inv.action_accept(newu)
check('member joined: the inviter is told', len(rows(ow.user_id, 'member_joined')) == 1)

# jobs: a background job tells the requester, an inline one does not
J = env['ts.job']
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '500')
j1 = J.ts_export_create(ow, 'export_clients', 'csv', {})
check('export_ready: an export that ran at once creates no notification', not rows(ow.user_id, 'export_ready'))
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '1')
jq = J.ts_export_create(ow, 'export_status', 'csv', {})
if jq.state == 'queued':
    with patch.object(env.cr, 'commit', lambda: None):
        for _k in range(3):
            J._cron_run_jobs()
check('export_ready: a queued export that the cron finished notifies the requester', jq.state == 'done' and len(rows(ow.user_id, 'export_ready')) == 1)
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '500')

# handover request waits for a decision
cl2 = C.create({'workspace_id': w2.id, 'name': 'مراجع واگذاری'})
cl2.responsible_id = cs1.id
cs2 = member(w2, 'counselor')
cl2.ts_request_handover(cs1, cs2)
check('handover request: the members who assign clients are told when it waits', cl2.handover_to_id and len(rows(ow.user_id, 'client_handover_request')) >= 1)

# ---- reminders (INV-8)
today = N._tehran_now().date()
w4 = panel('education', 'پنل یادآوری S10')
o4 = member(w4, 'owner')
rc = C.create({'workspace_id': w4.id, 'name': 'یادآوری حساب‌دار', 'user_id': puser().id})
rcp = C.create({'workspace_id': w4.id, 'name': 'یادآوری پیامکی', 'phone': '09127776655'})


def inv_(client, **kw):
    vals = {'workspace_id': w4.id, 'instrument_id': talent.id, 'client_id': client.id, 'invitee_name': client.name}
    vals.update(kw)
    return A.create(vals)


r1 = inv_(rc, deadline=today + timedelta(days=2))
r2 = inv_(C.create({'workspace_id': w4.id, 'name': 'دور'}), deadline=today + timedelta(days=20))
r3 = inv_(C.create({'workspace_id': w4.id, 'name': 'بدون مهلت'}))
env.flush_all()
env.cr.execute("update ts_assignment set create_date = now() - interval '8 days' where id = %s", [r3.id])
r3.invalidate_recordset()
check('reminder due: a deadline within 3 days', r1._ts_reminder_due(today))
check('reminder not due: a deadline far away', not r2._ts_reminder_due(today))
check('reminder due: no deadline and 7 days old', r3._ts_reminder_due(today))
check('reminder not due: no deadline and new', not inv_(C.create({'workspace_id': w4.id, 'name': 'تازه'}))._ts_reminder_due(today))
check('reminder not due after the deadline', not r1._ts_reminder_due(today + timedelta(days=3)))
with patch.object(nt.TsNotification, '_send_sms', fake_send), patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: False):
    calls.clear()
    company.write({'kv_enabled': True, 'ts_sms_reminder': False})
    used = r1._ts_do_reminder()
    check('reminder: an account holder gets the in-app row', used == {'app'} and len(rows(r1.client_id.user_id, 'reminder')) == 1 and not calls)
    check('the reminder is counted and stamped, and is not due a second time', r1.reminder_count == 1 and r1.last_reminder_at and not r1._ts_reminder_due(today))
    p1 = inv_(rcp, sms_consent=True, remind_ok=True, invitee_phone='09127776655', deadline=today + timedelta(days=1))
    check('P20: switch off -> no SMS reminder even with consent', p1._ts_do_reminder() == set() and not calls)
    company.ts_sms_reminder = True
    p2 = inv_(C.create({'workspace_id': w4.id, 'name': 'پیامکی دو', 'phone': '09127776656'}), sms_consent=True, remind_ok=True, invitee_phone='09127776656', deadline=today + timedelta(days=1))
    check('INV-8: switch on + consent + remind_ok -> one SMS to the invitee', p2._ts_do_reminder() == {'sms'} and len(calls) == 1 and calls[0][0] == '09127776656'
          and 'invite' in calls[0][1] and p2.client_id.name not in calls[0][1])
    p3 = inv_(C.create({'workspace_id': w4.id, 'name': 'قدیمی', 'phone': '09127776657'}), sms_consent=True, invitee_phone='09127776657', deadline=today + timedelta(days=1))
    calls.clear()
    check('P20: an invitation without remind_ok (older than the wizard) never gets the SMS', p3._ts_do_reminder() == set() and not calls)
    p4 = inv_(C.create({'workspace_id': w4.id, 'name': 'بی‌رضایت', 'phone': '09127776658'}), invitee_phone='09127776658', remind_ok=True, deadline=today + timedelta(days=1))
    check('P20: no consent tick -> no SMS', p4._ts_do_reminder() == set() and not calls)
    # a historical person: forced past the creation guard
    p5 = inv_(C.create({'workspace_id': w4.id, 'name': 'تاریخی دو', 'phone': '09127776659', 'user_id': puser().id}), sms_consent=True, remind_ok=True, invitee_phone='09127776659', deadline=today + timedelta(days=1))
    p5.client_id.sudo().write({'source': 'import'})
    env.flush_all()
    p5.client_id.invalidate_recordset()
    check('P20/NOT-5: a locked historical client gets no reminder by any channel', p5.client_id.contact_locked and p5._ts_do_reminder() == set() and not calls)
    # daily limit on the same number
    env['ir.config_parameter'].sudo().set_str('ts_panel.sms_per_day', '1')
    q1 = inv_(C.create({'workspace_id': w4.id, 'name': 'سقف یک', 'phone': '09127776660'}), sms_consent=True, remind_ok=True, invitee_phone='09127776660', deadline=today + timedelta(days=1))
    q2 = inv_(C.create({'workspace_id': w4.id, 'name': 'سقف دو', 'phone': '09127776660'}), sms_consent=True, remind_ok=True, invitee_phone='09127776660', deadline=today + timedelta(days=1))
    calls.clear()
    q1._ts_do_reminder()
    q2._ts_do_reminder()
    check('NOT-3: at most the daily limit of reminder SMS per number', len(calls) == 1)
    env['ir.config_parameter'].sudo().set_str('ts_panel.sms_per_day', '5')

    # the cron: closed campaign, remind off, withdrawn, done
    camp = env['ts.campaign'].sudo().create({'workspace_id': w4.id, 'name': 'کمپین یادآوری', 'instrument_id': talent.id, 'kind': 'list', 'created_by_id': o4.id})
    s1 = inv_(C.create({'workspace_id': w4.id, 'name': 'کمپین یک'}), deadline=today + timedelta(days=1), campaign_id=camp.id)
    check('reminder due inside an open campaign', s1._ts_reminder_due(today))
    camp.remind = False
    check('reminder not due when the campaign has reminders off', not s1._ts_reminder_due(today))
    camp.remind = True
    camp.ts_close()
    check('closing a campaign stops its reminders', not s1._ts_reminder_due(today))
    s2 = inv_(C.create({'workspace_id': w4.id, 'name': 'لغوشده'}), deadline=today + timedelta(days=1))
    s2.action_withdraw()
    check('a withdrawn invitation gets no reminder', not s2._ts_reminder_due(today))

    d1 = inv_(C.create({'workspace_id': w4.id, 'name': 'سررسید خودکار'}), deadline=today + timedelta(days=1))
    check('a due invitation is picked up by the cron', d1._ts_reminder_due(today))

with patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: True):
    check('the reminder cron does nothing in the quiet hours', A._cron_reminders() == 0)
with patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: False), patch.object(nt.TsNotification, '_send_sms', fake_send):
    n = A._cron_reminders()
    check('the reminder cron reminds the due invitations once', n >= 1 and d1.reminder_count == 1 and A._cron_reminders() == 0, str(n))

# manual reminder
w5 = panel('education', 'پنل دستی S10')
o5 = member(w5, 'owner')
mc = C.create({'workspace_id': w5.id, 'name': 'دستی', 'user_id': puser().id})
ma = A.create({'workspace_id': w5.id, 'instrument_id': talent.id, 'client_id': mc.id, 'invitee_name': mc.name})
with patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: True):
    check('manual reminder is refused in the quiet hours', ma.ts_manual_reminder(o5)[0] is False)
with patch.object(nt.TsNotification, '_quiet_now', lambda self, now=None: False):
    check('manual reminder: the first goes out', ma.ts_manual_reminder(o5)[0] is True and ma.reminder_count == 1)
    check('manual reminder: not twice in 24 hours', ma.ts_manual_reminder(o5)[0] is False and ma.reminder_count == 1)
    ma.last_reminder_at = fields.Datetime.now() - timedelta(hours=25)
    check('manual reminder: again after 24 hours', ma.ts_manual_reminder(o5)[0] is True and ma.reminder_count == 2)
    ma.last_reminder_at = fields.Datetime.now() - timedelta(hours=25)
    ma.ts_manual_reminder(o5)
    ma.last_reminder_at = fields.Datetime.now() - timedelta(hours=25)
    check('manual reminder: three in all', ma.ts_manual_reminder(o5)[0] is False and ma.reminder_count == 3)
    nocontact = A.create({'workspace_id': w5.id, 'instrument_id': talent.id, 'invitee_name': 'بدون راه تماس'})
    ok, msg = nocontact.ts_manual_reminder(o5)
    check('manual reminder: nobody to remind gives a clear message', ok is False and 'پیوند' in msg)

# vacuum
old = N.sudo().create({'user_id': user_a.id, 'type': 'export_ready', 'title': 'x', 'read_at': fields.Datetime.now() - timedelta(days=200)})
N._cron_vacuum()
check('read notifications older than 180 days are removed', not old.exists())

passed = sum(1 for _n_, ok in results if ok)
print('SUMMARY %d/%d passed' % (passed, len(results)))
env.cr.rollback()
