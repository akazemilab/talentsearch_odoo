# Organization / clinician acceptance tests. Run ONLY on an eot_ts* clone via odoo-bin shell.
from odoo.exceptions import AccessError, UserError, ValidationError

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


Inst = env['ts.instrument']
pub = Inst.search([('state', '=', 'published')])
emp = pub.filtered(lambda i: i.purpose == 'employment')
MENTAL = {'بیتابی روانی', 'نارضایتی از زندگی', 'مسائل نوجوان', 'مشکلات زناشویی', 'مشاوره ازدواج', 'مشکلات رفتاری کودک'}
check('employment catalog is non-empty', len(emp) > 0, str(len(emp)))
check('no mental-health category usable for hiring', not (set(emp.mapped('category')) & MENTAL), str(set(emp.mapped('category'))))
check('no child/adolescent instrument usable for hiring', set(emp.mapped('audience')) == {'adult'})

portal = env.ref('base.group_portal')


def puser(login):
    U = env['res.users'].with_context(no_reset_password=True)
    return U.search([('login', '=', login)]) or U.create({'name': login, 'login': login, 'group_ids': [(6, 0, [portal.id])]})


hr, rev, clin, clin2, p1, p2, outsider = (puser('ts.org.%s@example.invalid' % n) for n in
                                          ('hr', 'rev', 'clin', 'clin2', 'p1', 'p2', 'out'))
org = env['res.partner'].create({'name': 'سازمان آزمون', 'is_company': True})
WS = env['ts.workspace']
w_emp = WS.create({'name': 'استخدام آزمون', 'purpose': 'employment', 'partner_id': org.id})
w_emp.state = 'active'
w_cli = WS.create({'name': 'مرکز آزمون', 'purpose': 'clinical', 'partner_id': org.id, 'escalation_contact_id': org.id})
w_cli.state = 'active'
M = env['ts.workspace.member']
m_hr = M.create({'workspace_id': w_emp.id, 'user_id': hr.id, 'role': 'hr_admin'})
m_rev = M.create({'workspace_id': w_emp.id, 'user_id': rev.id, 'role': 'reviewer'})
m_clin = M.create({'workspace_id': w_cli.id, 'user_id': clin.id, 'role': 'clinician', 'license_number': 'T-1'})
m_clin2 = M.create({'workspace_id': w_cli.id, 'user_id': clin2.id, 'role': 'clinician', 'license_number': 'T-2'})
m_clin.action_verify()
check('unverified clinician cannot act', not m_clin2.can_act() and m_clin.can_act())
check('hr admin may invite, reviewer may not', m_hr.can_invite() and not m_rev.can_invite())
check('employment member sees only employment instruments', set(m_hr.allowed_instruments().ids) == set(emp.ids))
check('clinical member sees whole published catalog', set(m_clin.allowed_instruments().ids) == set(pub.ids))

A = env['ts.assignment']
mental = pub.filtered(lambda i: i.category in MENTAL)[:1]
check('employment invite of a mental-health instrument refused',
      raises(lambda: A.create({'workspace_id': w_emp.id, 'instrument_id': mental.id, 'invitee_name': 'x'}), ValidationError))
w_draft = WS.create({'name': 'پیش‌نویس', 'purpose': 'employment', 'partner_id': org.id})
check('invite from a draft workspace refused',
      raises(lambda: A.create({'workspace_id': w_draft.id, 'instrument_id': emp[0].id, 'invitee_name': 'x'}), ValidationError))


def finish(attempt):
    attempt.give_consent()
    for it in attempt.active_items():
        attempt.save_answer(it.id, 1 + it.id % 5)
    attempt.action_submit()


a1 = A.create({'workspace_id': w_emp.id, 'instrument_id': emp[0].id, 'invitee_name': 'شرکت‌کنندهٔ یک'})
check('assignment numbered and invited', a1.name.startswith('TSI-') and a1.state == 'invited')
check('invite url on website 2 domain', a1.invite_url().startswith('https://talentsearch.ir/invite/'), a1.invite_url())
check('nothing visible before completion', a1.visible_results(m_hr)[0] == 'none')
at1 = a1.action_accept(p1, share=True)
check('accept creates attempt tied to workspace', at1.workspace_id == w_emp and a1.state == 'accepted' and a1.share_level == 'summary')
check('another account cannot take over the invitation', raises(lambda: a1.action_accept(p2, share=True), UserError))
finish(at1)
check('state follows attempt -> done', a1.state == 'done')
lvl, res = a1.visible_results(m_hr)
check('hr admin sees band summary only', lvl == 'summary' and res)
check('reviewer sees band summary', a1.visible_results(m_rev)[0] == 'summary')
check('clinical member of another workspace sees nothing', a1.visible_results(m_clin)[0] == 'none')
check('workspace member has no ACL on attempts/answers/results',
      raises(lambda: at1.with_user(hr).read(['name']), AccessError)
      and raises(lambda: at1.answer_ids[:1].with_user(hr).read(['value']), AccessError)
      and raises(lambda: at1.result_ids[:1].with_user(hr).read(['score']), AccessError))
check('portal users have no ACL on assignments', raises(lambda: a1.with_user(hr).read(['name']), AccessError))
check('outsider has no membership', not M.search([('user_id', '=', outsider.id)]))
check('only the participant can revoke sharing', raises(lambda: a1.action_revoke_share(hr), UserError))
a1.action_revoke_share(p1)
check('after revoke organization sees nothing', a1.visible_results(m_hr)[0] == 'none')
check('completed assignment cannot be withdrawn', raises(lambda: a1.action_withdraw(), UserError))

a2 = A.create({'workspace_id': w_emp.id, 'instrument_id': emp[0].id, 'invitee_name': 'بدون اشتراک'})
at2 = a2.action_accept(p2, share=False)
finish(at2)
check('declined sharing -> nothing visible', a2.share_level == 'none' and a2.visible_results(m_hr)[0] == 'none')

a3 = A.create({'workspace_id': w_cli.id, 'instrument_id': mental.id, 'invitee_name': 'مراجع'})
at3 = a3.action_accept(p1, share=True)
finish(at3)
lvl, res = a3.visible_results(m_clin)
check('verified clinician sees full clinical report', lvl == 'clinical' and all(r.therapist_text for r in res))
check('unverified clinician sees nothing', a3.visible_results(m_clin2)[0] == 'none')
check('employment member of another workspace sees nothing', a3.visible_results(m_hr)[0] == 'none')

a4 = A.create({'workspace_id': w_emp.id, 'instrument_id': emp[0].id, 'invitee_name': 'لغو'})
a4.action_withdraw()
check('withdrawn invite cannot be accepted', a4.state == 'withdrawn' and raises(lambda: a4.action_accept(p1, True), UserError))
a5 = A.create({'workspace_id': w_emp.id, 'instrument_id': emp[0].id, 'invitee_name': 'رد'})
a5.action_decline(p2)
check('declined invite recorded', a5.state == 'declined')
ev = env['ts.audit.event'].search_count([('res_model', '=', 'ts.assignment'), ('res_id', 'in', (a1 | a3 | a4 | a5).ids)])
check('audit trail for create/accept/revoke/withdraw/decline', ev >= 8, str(ev))
check('participant report knows its assignment', at1.ts_org_assignment() == a1)

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
