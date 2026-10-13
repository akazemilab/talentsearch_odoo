# onb3 (release 3 of onboarding): the first session inside a panel. One form (kind, panel name, «نام شما»), the escalation
# question moved to the first client invitation, the kind-driven starter (and the HR sample position), the member's own
# try-out («پیش‌نمایش») never billed or counted, «شروع کار» and «پنل را کامل کنید», the permanent link, guide SMS (welcome,
# 3 h, 24 h, first result, weekly digest; quiet hours, one a day, opt-out, suspended), the 7-day back-office follow-up, the
# colleague join SMS, the welcome credit, sample reports and the activation funnel. Run ONLY on an eot_ts* clone via
# odoo-bin shell. Never commits; never sends an SMS or an e-mail (the one SMS path is replaced by a recorder and the
# Kavenegar address points at a closed local port).
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError

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


TEHRAN = ZoneInfo('Asia/Tehran')
ICP = env['ir.config_parameter'].sudo()
ICP.set_str('ts_kavenegar.api_base', 'http://127.0.0.1:9/v1/%s/%s.json')     # safety net: nothing can reach a provider
ICP.set_str('ts_onboard.nudges_enabled', '1')
ICP.set_str('ts_billing.welcome_credit_rial', '0')
company = env.company.sudo()
company.write({'kv_enabled': True})
SENT = []


def fake_send(self, company, number, body, partner_id=False):
    SENT.append((number, body))
    return True


N_cls = type(env['ts.notification'])
_p_sms = patch.object(N_cls, '_send_sms', fake_send)
_p_sms.start()
Nudge = env['ts.onb.nudge'].sudo()
NudgeCls = type(env['ts.onb.nudge'])
NOW = [datetime.now(TEHRAN).replace(hour=10, minute=0, second=0, microsecond=0)]
_p_now = patch.object(NudgeCls, '_tehran_now', lambda self: NOW[0])
_p_now.start()

portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, Att, C = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment'].sudo(), env['ts.attempt'].sudo(), \
    env['ts.panel.client'].sudo()
F, Audit, Txn = env['ts.funnel.event'].sudo(), env['ts.audit.event'].sudo(), env['ts.wallet.txn'].sudo()
_n = [0]
PH = ['091266545%02d' % i for i in range(0, 20)]
for p in PH:
    env['res.partner'].with_context(active_test=False).search([('ts_phone', '=', p)]).write({'ts_phone': False})
    for u in U.with_context(active_test=False).search([('login', '=', p)]):
        u.write({'login': 'old.onb3.%d' % u.id})


def puser(phone=None, name=None):
    _n[0] += 1
    login = 'ts.onb3.orm.%d@example.invalid' % _n[0]
    u = U.create({'name': name or ('مالک آزمون onb3 %d' % _n[0]), 'login': login, 'email': login,
                  'group_ids': [Command.set([portal.id])]})
    if phone:
        u.partner_id.write({'ts_phone': phone, 'ts_phone_verified_at': fields.Datetime.now()})
    return u


def make(kind, phone=None, name=None, **kw):
    u = puser(phone)
    ws = W.ts_panel_create(u, name or ('پنل آزمون onb3 %s %d' % (kind, _n[0])), kind, terms=True, **kw)
    return ws, ws.member_ids.filtered(lambda m: m.role == 'owner')[:1], u


def finish(at):
    at = at.sudo()
    if at.state == 'consent':
        at.give_consent(research=False, role='self')
    for it in at.active_items():
        at.save_answer(it.id, 1 + it.id % 4)
    return at.action_submit()


def finish_all(a):
    a = a.sudo()
    for _ in range(12):
        a.invalidate_recordset()
        left = a.ts_battery_attempts().filtered(lambda t: t.state != 'done')
        if not left:
            break
        finish(left[0])
    a.invalidate_recordset()
    return a.state


def fevents(step, kind=None):
    dom = [('step', '=', step)] + ([('panel_kind', '=', kind)] if kind else [])
    return F.search_count(dom)


Inst = env['ts.instrument'].sudo()
adult = Inst.search([('state', '=', 'published'), ('audience', '=', 'adult'), ('purpose', '!=', 'employment'),
                     ('code', 'not in', ('TALENT-INV-15', 'inventory_002'))], order='id', limit=1)
f_before = {k: fevents('panel_created', k) for k in ('clinic', 'solo', 'school', 'hr')}

# ================================================================ P. one form, kind-driven starter
w_cl, o_cl, u_cl = make('clinic', PH[0])
w_so, o_so, u_so = make('solo', PH[1])
w_sc, o_sc, u_sc = make('school', PH[2])
w_hr, o_hr, u_hr = make('org', PH[3])
check('P01 four kinds from one form: purposes, kinds and «شروع کار» on; no licence, no escalation asked',
      (w_cl.purpose, w_so.purpose, w_sc.purpose, w_hr.purpose) == ('clinical', 'clinical', 'education', 'employment')
      and (w_cl.ts_kind, w_so.ts_kind, w_sc.ts_kind, w_hr.ts_kind) == ('clinic', 'solo', 'school', 'hr')
      and all(w.ts_onb_start and w.state == 'active' for w in (w_cl, w_so, w_sc, w_hr))
      and not w_cl.escalation_contact_id and not w_so.escalation_contact_id and not o_so.license_number,
      str([w.ts_kind for w in (w_cl, w_so, w_sc, w_hr)]))
check('P02 a solo practitioner is a counseling panel whose owner counsels (listed for the after-the-fact licence review)',
      o_so.owner_practices and o_so.practising_since and Audit.search_count([('event_type', '=', 'member.licence_self_declared'),
                                                                              ('workspace_id', '=', w_so.id)]) == 1)
b, i = w_cl.ts_onb_starter(o_cl)
b2, i2 = w_so.ts_onb_starter(o_so)
b3, i3 = w_sc.ts_onb_starter(o_sc)
b4, i4 = w_hr.ts_onb_starter(o_hr)
check('P03 the starter: clinic and solo BAT-INTAKE-1, school TALENT-INV-15 (no battery), HR BAT-HR-SHORT',
      b.code == 'BAT-INTAKE-1' and i and b2.code == 'BAT-INTAKE-1' and not b3 and i3.code == 'TALENT-INV-15'
      and b4.code == 'BAT-HR-SHORT' and i4, str((b.code, b2.code, i3.code, b4.code)))
sp = w_hr.ts_onb_sample_position(create=False)
check('P04 an employment panel starts with the sample position «کارشناس فروش (نمونه)»: open, marked sample, a sales occupation, '
      'the short battery, 30-day deadline', sp and sp.name == 'کارشناس فروش (نمونه)' and sp.ts_sample and sp.state == 'open'
      and sp.occupation_id.code in ('41-4012.00', '41-3091.00', '41-2031.00') and sp.battery_choice == 'short'
      and sp.battery_id.code == 'BAT-HR-SHORT', '%s %s' % (sp.occupation_id.code, sp.state))
check('P05 the sample position is editable like any other (rename)', not raises(lambda: sp.write({'name': 'کارشناس فروش شعبهٔ آزمون'})))
sp.name = 'کارشناس فروش (نمونه)'
check('P06 only one sample position per panel', w_hr.ts_onb_sample_position() == sp)
check('P07 words per kind', (w_cl.ts_onb_words()['one'], w_sc.ts_onb_words()['one'], w_hr.ts_onb_words()['one']) == ('مراجع', 'دانش‌آموز', 'داوطلب'))
check('P08 where the first invitation is made: clinic one screen, school the permanent link, HR the sample position',
      o_cl.ts_onb_invite_url().endswith('/invites/new') and o_sc.ts_onb_invite_url().endswith('/invites/new?mode=link')
      and o_hr.ts_onb_invite_url().endswith('/positions/%d#tsh-invite' % sp.id))
check('P09 a missing kind or terms is still refused',
      raises(lambda: W.ts_panel_create(puser(), 'پنل بی‌نوع', 'x', terms=True), UserError)
      and raises(lambda: W.ts_panel_create(puser(), 'پنل بی‌شرایط', 'clinic', terms=False), UserError))
check('P10 activation event «panel_created» per kind (no personal data: no panel, person or address column)',
      all(fevents('panel_created', k) == f_before[k] + 1 for k in ('clinic', 'solo', 'school', 'hr'))
      and not {'workspace_id', 'user_id', 'partner_id', 'ip'} & set(F._fields), str({k: fevents('panel_created', k) - f_before[k] for k in f_before}))

# ================================================================ E. escalation asked once, at the first client invitation
check('E01 a counseling panel invites no client before its escalation contact exists',
      raises(lambda: A.create({'workspace_id': w_cl.id, 'instrument_id': adult.id, 'invitee_name': 'مراجع بی‌پیگیری'}),
             ValidationError, 'پیگیری فوری'))
check('E02 ...nor opens a group invitation or link', raises(lambda: env['ts.campaign'].sudo().create(
    {'workspace_id': w_cl.id, 'name': 'پیوند بی‌پیگیری', 'instrument_id': adult.id, 'kind': 'open_link', 'created_by_id': o_cl.id}),
    ValidationError, 'پیگیری فوری'))
check('E03 ...nor makes its permanent link', raises(lambda: w_cl.ts_onb_permanent_link(o_cl), UserError))

# ================================================================ T. the member's own try-out («پیش‌نمایش»)
n_notif = env['ts.notification'].sudo().search_count([])
pv = o_cl.ts_onb_try()
parts = pv.ts_battery_attempts()
check('T01 a try-out needs no escalation: preview invitation, channel «preview», a preview client, shared, accepted by the member',
      pv.ts_preview and pv.channel == 'preview' and pv.client_id.source == 'preview' and pv.user_id == u_cl
      and pv.state in ('accepted', 'in_progress') and pv.share_level != 'none' and pv.invitee_name.startswith('پیش‌نمایش — '),
      '%s %s %s' % (pv.channel, pv.state, pv.share_level))
check('T02 every part of the battery is a try-out (ts_preview)', parts and all(t.ts_preview for t in parts), str(len(parts)))
check('T03 starting again returns the same try-out', o_cl.ts_onb_try() == pv)
from odoo.addons.ts_panel.controllers.clients import visible_domain
from odoo.addons.ts_panel.controllers.invites import assignment_domain
tiles = {t['key']: t['n'] for t in o_cl.dash_tiles(30)}
check('T04 in no list or count of the panel: clients, invitations, dashboard tiles and funnel',
      not C.search_count(visible_domain(o_cl)) and not A.search_count(assignment_domain(o_cl))
      and tiles.get('sent', 0) == 0 and sum(x[2] for x in o_cl.dash_funnel(30)) == 0 and not o_cl.ts_onb_recent(), str(tiles))
check('T05 the member still sees his own try-out (can_see), a colleague without read-all does not',
      o_cl.can_see(pv) and o_cl.can_see(pv.client_id))
check('T06 no reminder is ever due for a try-out; a manual reminder is refused; no notification row was written',
      not pv._ts_reminder_due(fields.Date.today() + timedelta(days=5)) and pv.ts_manual_reminder(o_cl)[0] is False
      and env['ts.notification'].sudo().search_count([]) == n_notif)
card = o_cl.ts_onb_start_card()
check('C01 «شروع کار»: ۱ از ۴, the current step «خودتان امتحان کنید», one primary action «ادامهٔ پیش‌نمایش» while it is going',
      card and card['total'] == 4 and card['done_n'] == 1 and card['current']['key'] == 'try'
      and card['hero']['url'] and card['hero']['btn'] == 'ادامهٔ پیش‌نمایش' and card['help'] == '/help/panel#start-clinic',
      str(card and (card['done_n'], card['current'])))
ev0 = fevents('self_test_done', 'clinic')
st = finish_all(pv)
check('T07 the try-out finishes like any battery', st == 'done', st)
check('T08 never counted: no usage event for any of its attempts, the funnel ignores it, the step event is logged once',
      not env['ts.usage.event'].sudo().search_count([('attempt_id', 'in', pv.ts_battery_attempts().ids)])
      and all(t._ts_funnel_target() == (False, None) for t in pv.ts_battery_attempts())
      and fevents('self_test_done', 'clinic') == ev0 + 1)
check('T09 its report shows as the panel\'s practitioners see a client\'s (clinical level), never the A5b status-only view',
      pv.result_level(o_cl) == 'clinical', pv.result_level(o_cl))
check('T10 no «result ready» notice and no first-result SMS for a try-out',
      env['ts.notification'].sudo().search_count([]) == n_notif and not w_cl.ts_onb_result_ready_at)
card = o_cl.ts_onb_start_card()
check('C02 after the try-out: ۲ از ۴, the current step is the first invitation, its button goes to the one-screen invite',
      card['done_n'] == 2 and card['current']['key'] == 'invite' and card['hero']['url'].endswith('/invites/new')
      and card['hero']['second'][0] and '?preview=1' in card['hero']['second'][0])
coach = o_cl.ts_onb_coach()
check('C03 the coach line under the report: «حالا نخستین مراجع را دعوت کنید»', coach and coach['cta'] == 'حالا نخستین مراجع را دعوت کنید')

# escalation once, then the first real invitation
check('E04 ts_set_escalation: the inviting member takes it, once (audited)', w_cl.ts_set_escalation(o_cl) is True
      and w_cl.escalation_contact_id == u_cl.partner_id and w_cl.ts_set_escalation(o_cl) is False
      and Audit.search_count([('event_type', '=', 'workspace.escalation'), ('workspace_id', '=', w_cl.id)]) == 1)
fi0 = fevents('first_invite', 'clinic')
real = A.with_user(u_cl).sudo().create({'workspace_id': w_cl.id, 'instrument_id': adult.id, 'invitee_name': 'مراجع آزمون onb3',
                                       'invited_by_id': u_cl.id})
check('E05 after it, client invitations work; the first one is marked (event «first_invite», once)',
      real.channel != 'preview' and w_cl.ts_onb_first_invite_at and fevents('first_invite', 'clinic') == fi0 + 1)
A.with_user(u_cl).sudo().create({'workspace_id': w_cl.id, 'instrument_id': adult.id, 'invitee_name': 'مراجع دوم onb3',
                                 'invited_by_id': u_cl.id})
check('E06 a second invitation logs nothing more', fevents('first_invite', 'clinic') == fi0 + 1)
card = o_cl.ts_onb_start_card()
check('C04 ۳ از ۴: waiting for the first result (no button, the text says an SMS will come)',
      card['done_n'] == 3 and card['current']['key'] == 'result' and card['hero'].get('wait') and not card['hero'].get('url'))
tiles = {t['key']: t['n'] for t in o_cl.dash_tiles(30)}
check('T11 counts start at the first real invitation (the try-out is not in them)', tiles.get('sent', 0) >= 1 and 'rate' not in tiles,
      str(tiles))
recent = o_cl.ts_onb_recent()
check('C05 the live stepper lists real invitations only, step 0 «فرستاده شد»', real in recent and pv not in recent
      and real.ts_onb_step() == 0)

# the first real result: owner + inviting member get the first-result SMS (not capped), not a test or a client name
SENT.clear()
colleague_u = puser(PH[4], name='همکار آزمون onb3')
colleague = M.create({'workspace_id': w_cl.id, 'user_id': colleague_u.id, 'role': 'clinician', 'license_number': 'T-ONB3'})
real2 = A.with_user(colleague_u).sudo().create({'workspace_id': w_cl.id, 'instrument_id': adult.id,
                                                'invitee_name': 'مراجع همکار onb3', 'invited_by_id': colleague_u.id})
cand = puser(PH[5], name='مراجع شرکت‌کننده onb3')
at = real2.action_accept(cand, share=True)
finish(at)
real2.invalidate_recordset()
rows = Nudge.search([('workspace_id', '=', w_cl.id), ('kind', '=', 'first_result')])
bodies = [b_ for _n_, b_ in SENT]
check('G01 first real shared result: ready mark, one SMS to the owner and one to the inviting member, «نخستین نتیجه در پنل … آماده است»',
      real2.state == 'done' and w_cl.ts_onb_result_ready_at and set(rows.mapped('member_id').ids) == {o_cl.id, colleague.id}
      and set(rows.mapped('state')) == {'sent'} and {n_ for n_, _b in SENT} >= {PH[0], PH[4]}
      and all('نخستین نتیجه در پنل' in b_ and 'آماده است' in b_ for b_ in bodies),
      str([(r.member_id.id, r.state, r.reason) for r in rows]))
check('G02 the text names no test, no client and no result', bodies and not any(
    adult.ts_title() in b_ or 'مراجع همکار' in b_ or 'شرکت‌کننده onb3' in b_ for b_ in bodies))
check('G03 the first-result SMS is not held back by the one-a-day cap (the welcome went out today too)',
      Nudge.search_count([('member_id', '=', o_cl.id), ('kind', '=', 'welcome'), ('state', '=', 'sent')]) == 1)
SENT.clear()
real3 = A.with_user(u_cl).sudo().create({'workspace_id': w_cl.id, 'instrument_id': adult.id, 'invitee_name': 'مراجع سوم onb3',
                                       'invited_by_id': u_cl.id})
finish(real3.action_accept(puser(), share=True))
check('G04 the second result sends nothing', not SENT and Nudge.search_count([('workspace_id', '=', w_cl.id), ('kind', '=', 'first_result')]) == 2)
card = o_cl.ts_onb_start_card()
check('C06 ready, not opened: «نخستین نتیجه آماده است» with «دیدن نتیجه»', card['current']['key'] == 'result'
      and card['hero']['btn'] == 'دیدن نتیجه' and not card['hero'].get('wait'))
fo0 = fevents('first_result_opened', 'clinic')
Audit.log('result.view', pv.attempt_id, workspace=w_cl, member=o_cl)
check('C07 opening the member\'s own try-out report does not count as the first result', not w_cl.ts_onb_result_opened_at)
Audit.log('result.view', real2.attempt_id, workspace=w_cl, member=o_cl)
card = o_cl.ts_onb_start_card()
check('C08 opening a real result: ۴ از ۴, the start card is finished (the dashboard hides it), event once',
      w_cl.ts_onb_result_opened_at and card['finished'] and card['done_n'] == 4 and fevents('first_result_opened', 'clinic') == fo0 + 1)
Audit.log('result.view', real3.attempt_id, workspace=w_cl, member=o_cl)
check('C09 ...a second view logs nothing more', fevents('first_result_opened', 'clinic') == fo0 + 1)
more = o_cl.ts_onb_more_card()
keys = [x['key'] for x in more['items']] if more else []
check('M01 «پنل را کامل کنید» after the first real result was opened: identity, colleagues (team done: a counselor joined), '
      'SMS name; a celebration line in the first week', more and keys[:1] == ['identity'] and 'team' in keys
      and next(x for x in more['items'] if x['key'] == 'team')['done'] and more['celebrate'], str(keys))
check('M02 no licence item for a center owner who does not counsel; no credit or caps for a free panel',
      'licence' not in keys and 'credit' not in keys and 'caps' not in keys)
o_cl.ts_onb_hide('more')
check('M03 «بعداً» hides the second card for this member only', o_cl.ts_onb_more_card() is None)
check('C10 a colleague (no members:invite) sees only his own try-out step, until he did it',
      colleague.ts_onb_start_card() and colleague.ts_onb_start_card()['total'] == 2
      and colleague.ts_onb_start_card()['current']['key'] == 'try')
o_cl.ts_onb_hide('start')
check('C11 «بعداً» hides «شروع کار» for this member only', o_cl.ts_onb_start_card() is None and colleague.ts_onb_start_card())

# ================================================================ solo: the second card has the licence, never colleagues
pv_s = o_so.ts_onb_try()
finish_all(pv_s)
w_so.ts_set_escalation(o_so)
rs = A.with_user(u_so).sudo().create({'workspace_id': w_so.id, 'instrument_id': adult.id, 'invitee_name': 'مراجع مستقل onb3',
                                     'invited_by_id': u_so.id})
finish(rs.action_accept(puser(), share=True))
Audit.log('result.view', rs.attempt_id, workspace=w_so, member=o_so)
ks = [x['key'] for x in (o_so.ts_onb_more_card() or {}).get('items', [])]
check('M04 solo: «رسیدگی به پروانه» is in, «دعوت همکاران» is not', 'licence' in ks and 'team' not in ks, str(ks))

# ================================================================ B. never billed (prepaid panel)
w_pp, o_pp, u_pp = make('clinic', PH[6])
w_pp.billing_mode = 'prepaid'
intake = env['ts.battery'].sudo().search([('code', '=', 'BAT-INTAKE-1')], limit=1)
intake.write({'ts_list_price': 3000000})
w_pp.sudo().escalation_contact_id = u_pp.partner_id
env['ts.wallet']._for_workspace(w_pp).sudo().ts_grant(10000000, 'promo')
pvp = o_pp.ts_onb_try()
check('B01 a try-out on a prepaid panel holds nothing (no hold row, no price held)',
      not Txn.search_count([('assignment_id', '=', pvp.id)]) and not pvp.price_held)
finish_all(pvp)
check('B02 ...and is never debited; the reconcile ignores it',
      not Txn.search_count([('attempt_id', 'in', pvp.ts_battery_attempts().ids)])
      and not [p for p in env['ts.wallet']._reconcile() if p[1] == w_pp.id])
rp = A.with_user(u_pp).sudo().create({'workspace_id': w_pp.id, 'battery_id': intake.id, 'instrument_id': intake.ts_first_instrument().id,
                                     'invitee_name': 'مراجع پیش‌پرداخت onb3', 'invited_by_id': u_pp.id})
check('B03 control: a real invitation of the same battery holds its price', rp.price_held == 3000000, str(rp.price_held))
check('B04 the usage line is for free panels only («تا امروز … نتیجه؛ در دورهٔ آزمایشی رایگان»)',
      w_pp.ts_onb_usage_line() is None and w_cl.ts_onb_usage_line() == 'تا امروز ۲ نتیجه؛ در دورهٔ آزمایشی رایگان',
      w_cl.ts_onb_usage_line())

# ================================================================ W. welcome credit (off by default)
w_w0 = make('clinic', name='پنل خوش‌آمد صفر onb3')[0]
w_w0.billing_mode = 'prepaid'
check('W01 welcome credit 0 (default): a new prepaid panel gets nothing', not Txn.search_count([('workspace_id', '=', w_w0.id), ('type', '=', 'grant')]))
ICP.set_str('ts_billing.welcome_credit_rial', '2000005')
w_w1 = make('clinic', name='پنل خوش‌آمد onb3')[0]
w_w1.billing_mode = 'prepaid'
g = Txn.search([('workspace_id', '=', w_w1.id), ('type', '=', 'grant')])
check('W02 welcome credit > 0: one grant through the back-office path (rounded to whole toman), audited',
      len(g) == 1 and g.amount == 2000000 and w_w1.ts_welcome_credit_on
      and Audit.search_count([('event_type', '=', 'billing.welcome_credit'), ('workspace_id', '=', w_w1.id)]) == 1, str(g.mapped('amount')))
w_w1.billing_mode = 'free'
w_w1.billing_mode = 'prepaid'
check('W03 ...once only', Txn.search_count([('workspace_id', '=', w_w1.id), ('type', '=', 'grant')]) == 1)
check('W04 a panel that was prepaid before (it already has a grant) gets nothing', not w_pp._ts_welcome_credit()
      and Txn.search_count([('workspace_id', '=', w_pp.id), ('type', '=', 'grant')]) == 1)
check('W05 no invoice and no payment is ever recorded for it', not env['account.move'].sudo().search_count(
    [('ts_workspace_id', 'in', [w_w1.id])]) if 'ts_workspace_id' in env['account.move']._fields else True)
ICP.set_str('ts_billing.welcome_credit_rial', '0')

# ================================================================ H. hiring: the HR admin is the first candidate of the sample position
pvh = o_hr.ts_onb_try()
check('H01 the try-out of an employment panel is a «پیش‌نمایش» candidate of the sample position (BAT-HR-SHORT)',
      pvh.position_id == sp and pvh.ts_preview and pvh.battery_id.code == 'BAT-HR-SHORT' and pvh.ts_fair_asked)
check('H02 the position counts leave it out', sp.ts_counts() == {'invited': 0, 'done': 0, 'going': 0, 'strong': 0}, str(sp.ts_counts()))
pvh.sudo().write({'hire_decision': 'shortlist', 'ts_gender': 'female'})
check('H03 fairness never counts a try-out', sp.ts_fairness()['ts_gender']['decided'] == 0)
check('H04 no «candidate done» e-mail for a try-out', pvh._ts_mail_candidate_done() is False)
check('H05 the HR card points at the sample position', o_hr.ts_onb_start_card()['steps'][2]['label'] == 'دعوت داوطلب‌ها')
card_s = o_sc.ts_onb_start_card()
check('H06 school labels: «پیوند کلاس», «نخستین گزارش کلاس»', [s_['label'] for s_ in card_s['steps']][2:] == ['پیوند کلاس', 'نخستین گزارش کلاس'])

# ================================================================ N. norms
TaskNorm = type(env['ts.task.norm']) if 'ts.task.norm' in env else None
seen = []
orig_search = type(Att).search


def spy(self, domain, *a, **k):
    if self._name == 'ts.attempt':
        seen.append(list(domain))
    return orig_search(self, domain, *a, **k)


if TaskNorm:
    with patch.object(type(Att), 'search', spy):
        with env.cr.savepoint():
            env['ts.task.norm'].sudo()._ts_rebuild()
check('N01 the task norms are rebuilt from real attempts only (no try-out, no voided attempt)',
      TaskNorm and any(('ts_preview', '=', False) in d and ('voided', '=', False) in d for d in seen), str(seen[:1]))

# ================================================================ L. the permanent link
lk = w_sc.ts_onb_permanent_link(o_sc)
check('L01 school: an open link of the starter that never closes by itself; asked again, the same one',
      lk.kind == 'open_link' and lk.ts_permanent and lk.instrument_id.code == 'TALENT-INV-15' and lk.open_state() == 'ok'
      and not lk.open_expires_at and w_sc.ts_onb_permanent_link(o_sc) == lk and w_sc.ts_perm_campaign_id == lk)
lk.state = 'closed'
check('L02 a closed permanent link stays closed (none is offered until a new one is made)', lk.open_state() == 'closed'
      and not w_sc.ts_onb_permanent_link(o_sc, create=False))
lk2 = w_sc.ts_onb_permanent_link(o_sc)
check('L03 ...made on the next request', lk2 != lk and lk2.open_state() == 'ok')
lkc = w_cl.ts_onb_permanent_link(o_cl)
check('L04 a counseling panel (escalation set) gets the intake battery as its permanent link', lkc.battery_id.code == 'BAT-INTAKE-1')
rev = M.create({'workspace_id': w_hr.id, 'user_id': puser().id, 'role': 'reviewer'})
check('L05 a member who may not invite cannot make it (a reviewer)', not rev.has_perm('invites:create')
      and raises(lambda: w_hr.ts_onb_permanent_link(rev), UserError))

# ================================================================ G. guide SMS rules
SENT.clear()
w_q, o_q, u_q = (None, None, None)
NOW[0] = datetime.now(TEHRAN).replace(hour=23, minute=0, second=0, microsecond=0)
w_q, o_q, u_q = make('school', PH[7])
wq_row = Nudge.search([('workspace_id', '=', w_q.id), ('kind', '=', 'welcome')])
check('G05 the welcome SMS at 23:00 Tehran waits in the queue (quiet hours 22:00–08:00)', wq_row.state == 'queued' and not SENT)
NOW[0] = NOW[0].replace(hour=8, minute=30) + timedelta(days=1)
Nudge._cron_onb_nudges()
check('G06 ...and goes out from 08:00 with the hourly run', wq_row.state == 'sent' and SENT and SENT[-1][0] == PH[7]
      and 'پنل' in SENT[-1][1] and 'ساخته شد. نخستین قدم: خودتان امتحان کنید.' in SENT[-1][1]
      and '/my/workspaces/%d' % w_q.id in SENT[-1][1], str(SENT[-1:]))
# stall 3 h: same Tehran day as the welcome -> held back by the one-a-day cap; next day -> sent
env.flush_all()
env.cr.execute("UPDATE ts_workspace SET create_date = now() at time zone 'UTC' - interval '4 hours' WHERE id = %s", [w_q.id])
w_q.invalidate_recordset()
SENT.clear()
Nudge._cron_onb_nudges()
r3 = Nudge.search([('workspace_id', '=', w_q.id), ('kind', '=', 'stall_3h')])
check('G07 3 hours without a try-out or an invitation: the nudge is due but the one-a-day cap holds it', r3.state == 'queued' and not SENT,
      r3.state)
NOW[0] = NOW[0] + timedelta(days=1)
Nudge._cron_onb_nudges()
check('G08 ...the next day it goes, «اول خودتان ببینید دانش‌آموز چه می‌بیند»', r3.state == 'sent' and SENT
      and 'اول خودتان ببینید دانش‌آموز چه می‌بیند' in SENT[-1][1], str(SENT[-1:]))
# 24 h: a stall_24h row, the link to the permanent link; the 3 h nudge of another panel still queued gives way
w_r, o_r, u_r = make('clinic', PH[8])
env.flush_all()
env.cr.execute("UPDATE ts_workspace SET create_date = now() at time zone 'UTC' - interval '25 hours' WHERE id = %s", [w_r.id])
w_r.invalidate_recordset()
NOW[0] = NOW[0] + timedelta(days=1)
SENT.clear()
Nudge._cron_onb_nudges()
r24 = Nudge.search([('workspace_id', '=', w_r.id), ('kind', '=', 'stall_24h')])
r3b = Nudge.search([('workspace_id', '=', w_r.id), ('kind', '=', 'stall_3h')])
check('G09 a day without an invitation: «پیوند همیشگی پنل … آماده است» with the link to it; the 3-hour nudge is superseded',
      r24.state == 'sent' and '/invites/new?mode=link' in SENT[-1][1] and 'پیوند همیشگی پنل' in SENT[-1][1]
      and r3b.state == 'skipped' and r3b.reason == 'superseded', '%s %s %s' % (r24.state, r3b.state, SENT[-1:]))
# step done -> skipped; opt-out; suspended panel; switch off
w_d, o_d, u_d = make('clinic', PH[9])
env.flush_all()
env.cr.execute("UPDATE ts_workspace SET create_date = now() at time zone 'UTC' - interval '4 hours' WHERE id = %s", [w_d.id])
w_d.invalidate_recordset()
finish_all(o_d.ts_onb_try())
NOW[0] = NOW[0] + timedelta(days=1)
Nudge._cron_onb_nudges()
rd = Nudge.search([('workspace_id', '=', w_d.id), ('kind', '=', 'stall_3h')])
check('G10 a stall nudge stops once its step is done (try-out done: «step_done»)', rd.state == 'skipped' and rd.reason == 'step_done',
      '%s %s' % (rd.state, rd.reason))
w_o, o_o, u_o = make('clinic', PH[10])
o_o.ts_guide_sms = False
env.flush_all()
env.cr.execute("UPDATE ts_workspace SET create_date = now() at time zone 'UTC' - interval '4 hours' WHERE id = %s", [w_o.id])
w_o.invalidate_recordset()
NOW[0] = NOW[0] + timedelta(days=1)
Nudge._cron_onb_nudges()
ro = Nudge.search([('workspace_id', '=', w_o.id), ('kind', '=', 'stall_3h')])
check('G11 «پیامک‌های راهنما» off on the member\'s own profile: nothing goes («opted_out»)', ro.state == 'skipped' and ro.reason == 'opted_out',
      '%s %s' % (ro.state, ro.reason))
w_s, o_s, u_s = make('clinic', PH[11])
row_s, _new = Nudge._new(w_s, o_s, 'stall_3h')
w_s.sudo().state = 'suspended' if 'suspended' in dict(W._fields['state'].selection) else 'closed'
row_s._ts_try_send()
check('G12 a suspended or closed panel gets nothing («panel_inactive»)', row_s.state == 'skipped' and row_s.reason == 'panel_inactive')
w_x, o_x, u_x = make('clinic', PH[12])
row_x, _new = Nudge._new(w_x, o_x, 'stall_24h', key='stall_24h')
ICP.set_str('ts_onboard.nudges_enabled', '0')
row_x._ts_try_send()
check('G13 the switch ts_onboard.nudges_enabled=0 stops every guide SMS', row_x.state == 'skipped' and row_x.reason == 'switch_off'
      and Nudge._cron_onb_nudges() == 0)
ICP.set_str('ts_onboard.nudges_enabled', '1')
# 7 days without a result: a back-office activity, never an SMS
w_7, o_7, u_7 = make('clinic', PH[13])
env.flush_all()
env.cr.execute("UPDATE ts_workspace SET create_date = now() at time zone 'UTC' - interval '7 days 2 hours' WHERE id = %s", [w_7.id])
w_7.invalidate_recordset()
SENT.clear()
NOW[0] = NOW[0] + timedelta(days=1)
Nudge._cron_onb_nudges()
act = env['mail.activity'].sudo().search([('res_model', '=', 'ts.workspace'), ('res_id', '=', w_7.id)])
check('G14 7 days without a result: one activity «تماس شخصی با پنل …» for a platform manager, marked once',
      len(act) == 1 and act.summary == 'تماس شخصی با پنل %s' % w_7.name and w_7.ts_onb_followup_at
      and (not act.user_id or not act.user_id.share), str(act.mapped('summary')))
Nudge._cron_onb_nudges()
check('G15 ...not again', env['mail.activity'].sudo().search_count([('res_model', '=', 'ts.workspace'), ('res_id', '=', w_7.id)]) == 1)
check('G16 the follow-up itself sends no SMS to the panel', not any(n_ == PH[13] and 'تماس' in b_ for n_, b_ in SENT))
# the weekly digest: Saturday from 09:00, counts only
sat = NOW[0]
while sat.weekday() != 5:
    sat += timedelta(days=1)
NOW[0] = sat.replace(hour=9, minute=30)
SENT.clear()
Nudge._cron_onb_nudges()
dg = Nudge.search([('workspace_id', '=', w_cl.id), ('kind', '=', 'digest')])
dbody = [b_ for n_, b_ in SENT if n_ == PH[0]]
check('G17 the weekly digest (Saturday from 09:00): counts only, Persian digits, no names',
      len(dg) == 1 and dg.key.startswith('digest:') and dbody and 'این هفته در پنل' in dbody[0] and '۴ دعوت' in dbody[0]
      and '۲ نتیجه' in dbody[0] and 'مراجع' not in dbody[0], str((dbody[:1], dg.mapped('state'), dg.mapped('reason'), len(SENT))))
Nudge._cron_onb_nudges()
check('G18 ...once a week', Nudge.search_count([('workspace_id', '=', w_cl.id), ('kind', '=', 'digest')]) == 1)
check('G19 a panel made before onb3 (follow-up marked by the migration) never gets a stall SMS',
      not Nudge.search_count([('workspace_id.ts_onb_followup_at', '!=', False), ('kind', 'in', ('stall_3h', 'stall_24h')),
                              ('workspace_id.create_date', '<', fields.Datetime.now() - timedelta(days=30))]))
check('G20 one row per member and kind: a second welcome is impossible', Nudge._new(w_q, o_q, 'welcome')[1] is False)
from odoo.addons.ts_onboard.models.onb3 import sms_allowed
ICP.set_str('ts_kavenegar.api_base', 'https://api.kavenegar.com/v1/%s/%s.json')
row_c, _new = Nudge._new(w_x, o_x, 'stall_3h')
SENT.clear()
row_c._ts_try_send()
check('G21 a clone (any database but eot_main) with the live gateway sends no guide SMS («not_production»)',
      not sms_allowed(env) and row_c.state == 'skipped' and row_c.reason == 'not_production' and not SENT)
ICP.set_str('ts_kavenegar.api_base', 'http://127.0.0.1:9/v1/%s/%s.json')
check('G22 ...a local fake gateway (the test suites) is allowed', sms_allowed(env))

# ================================================================ J. the colleague join SMS
SENT.clear()
inv = env['ts.member.invite'].sudo().ts_create(o_sc, 'counselor', phone_raw=PH[14])
check('J01 a colleague invited with a mobile number gets the join SMS from the system (/j/ link), marked sent, audited',
      inv.sms_sent and SENT and SENT[-1][0] == PH[14] and '/j/' in SENT[-1][1]
      and Audit.search_count([('event_type', '=', 'member.invite_sms'), ('res_id', '=', inv.id)]) == 1, str(SENT[-1:]))
SENT.clear()
inv_e = env['ts.member.invite'].sudo().ts_create(o_sc, inv.role, email_raw='ts.onb3.colleague@example.invalid')
check('J02 invited by e-mail only: no SMS', not SENT and not inv_e.sms_sent)
new = inv.ts_resend(o_sc)
check('J03 «ساخت پیوند تازه» sends a fresh SMS', new.sms_sent and SENT and SENT[-1][0] == PH[14])
joined = new.action_accept(puser(PH[14]))
check('J04 the colleague joins with that number; no licence is asked at the door', joined and joined.active
      and joined.workspace_id == w_sc and not joined.license_number, str(joined))

# ================================================================ S. sample reports (in memory)
env.flush_all()
cnt = lambda: (Att.search_count([]), env['res.partner'].sudo().with_context(active_test=False).search_count([]), W.search_count([]))
before = cnt()
S = env['ts.onb.sample'].sudo()
sc, ss, sh = S.ts_kind_sample('clinic'), S.ts_kind_sample('school'), S.ts_kind_sample('hr')
env.flush_all()
check('S01 a sample report per kind from the real engines: clinic (intake parts with bands), school (talent profile), HR (job fit)',
      sc and sc['sections'] and all(len(s_['results']) for s_ in sc['sections']) and ss and ss['attempt'].profile_json
      and sh and sh['res'].get('band') and S.ts_kind_sample('solo')['kind'] == 'clinic',
      '%s %s %s' % (bool(sc), bool(ss), bool(sh)))
check('S02 nothing is stored: no attempt, person or panel row behind a sample', cnt() == before, '%s %s' % (before, cnt()))

# ================================================================ Z. the migration on the live panels of this clone
ws4 = W.browse(4).exists()
if ws4 and ws4.purpose == 'clinical':
    om = ws4.member_ids.filtered(lambda m: m.active and m.role == 'owner')[:1]
    check('Z01 the live prepaid counseling panel (workspace 4) sees its finished state: no start card, no second card',
          not ws4.ts_onb_start and (not om or (om.ts_onb_start_card() is None and om.ts_onb_more_card() is None))
          and ws4.ts_onb_followup_at, '%s %s' % (ws4.ts_onb_start, ws4.ts_kind))
old = W.search([('create_date', '<', fields.Datetime.now() - timedelta(days=9))])
bad = [w.id for w in old if w.ts_onb_start and w.ts_onb_first_invite_at and w.ts_onb_first_invite_at < w.ts_onb_followup_at]
check('Z02 every older panel: «شروع کار» off when it had sent a real invitation; the team follow-up marked; a kind set',
      old and not bad and all(w.ts_onb_followup_at and w.ts_kind for w in old), str(bad[:5]))

# ================================================================ F. back office
check('F01 «فعال‌شدن پنل‌ها» (pivot by step and kind) and «پیامک‌های راهنما» are managers-only menus',
      env.ref('ts_onboard.menu_ts_funnel_panels').group_ids == env.ref('ts_core.group_ts_manager')
      and env.ref('ts_onboard.menu_ts_onb_nudges').group_ids == env.ref('ts_core.group_ts_manager'))
check('F02 no access for portal users to the guide SMS rows', not env['ts.onb.nudge'].with_user(u_cl).has_access('read'))

_p_now.stop()
_p_sms.stop()
print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
