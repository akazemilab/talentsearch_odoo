# Responsible-specialist tests (ts_org). Run ONLY on an eot_ts* clone via odoo-bin shell.
from odoo import fields
from odoo.exceptions import UserError, ValidationError

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


portal = env.ref('base.group_portal')


def puser(n):
    U = env['res.users'].with_context(no_reset_password=True)
    login = 'ts.resp.%s@example.invalid' % n
    return U.search([('login', '=', login)]) or U.create({'name': 'کاربر ' + n, 'login': login, 'group_ids': [(6, 0, [portal.id])]})


u_o, u_a, u_b, u_p, u_p2 = (puser(n) for n in ('owner', 'ca', 'cb', 'p1', 'p2'))
pub = env['ts.instrument'].search([('state', '=', 'published')])
inst = pub.filtered(lambda i: i.code == 'TALENT-INV-15')[:1] or pub[:1]
org = env['res.partner'].create({'name': 'مدرسهٔ آزمون مسئول', 'is_company': True})
WS, M, A = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment']
w = WS.create({'name': 'مدرسهٔ مسئول', 'purpose': 'education', 'partner_id': org.id})
w.write({'approved_on': fields.Datetime.now()})  # education is gated until the platform owner approves
w.state = 'active'
m_o = M.create({'workspace_id': w.id, 'user_id': u_o.id, 'role': 'owner'})


def mk(name, by, ws=w, ins=inst):
    return A.create({'workspace_id': ws.id, 'instrument_id': ins.id, 'invitee_name': name, 'invited_by_id': by.id})


def done(a, user, share=True):
    at = a.action_accept(user, share)
    at.write({'state': 'done', 'released': True})
    return at


# ---- solo owner is responsible for what they invite, and may test their own invite
a_solo = mk('انفرادی', u_o)
check('solo owner defaults to responsible', a_solo.responsible_id == m_o)
at = a_solo.action_accept(u_o, True)
check('owner accepting own invite drops the self-responsibility', not a_solo.responsible_id and at)

m_a = M.create({'workspace_id': w.id, 'user_id': u_a.id, 'role': 'counselor'})
m_b = M.create({'workspace_id': w.id, 'user_id': u_b.id, 'role': 'counselor'})
check('team owner invite starts unassigned', not mk('تیم', u_o).responsible_id)
a1 = mk('شرکت‌کنندهٔ الف', u_a)
check('counselor inviter is responsible', a1.responsible_id == m_a)
done(a1, u_p)
check('responsible counselor sees the result', a1.visible_results(m_a)[0] == 'education')
check('other counselor does not see it', a1.visible_results(m_b)[0] == 'none')
check('owner sees everything', a1.visible_results(m_o)[0] == 'education')
check('other counselor cannot open the participant report', not a1.attempt_id.ts_org_visible_to(m_b)
      and a1.attempt_id.ts_org_visible_to(m_a) and a1.attempt_id.ts_org_visible_to(m_o))

# ---- unassigned queue (education: counselors see it)
a2 = mk('بی‌مسئول', u_o)
done(a2, u_p2)
check('education counselor sees the unassigned queue', not a2.responsible_id and a2.visible_results(m_b)[0] == 'education')

# ---- handing over, audit, rules
a2.responsible_id = m_a
check('assigned participant leaves the queue for other counselors', a2.visible_results(m_b)[0] == 'none'
      and a2.visible_results(m_a)[0] == 'education')
a2.responsible_id = m_b
check('reassign moves access', a2.visible_results(m_a)[0] == 'none' and a2.visible_results(m_b)[0] == 'education')
ev = env['ts.audit.event'].search_count([('event_type', '=', 'assignment.responsible_change'), ('res_id', '=', a2.id)])
check('each responsible change is audited', ev == 2, str(ev))
check('only owner/manager may assign', m_o.can_assign() and not m_a.can_assign())
check('nobody is their own responsible specialist', raises(lambda: a1.write({'responsible_id': m_o.id, 'user_id': u_o.id}), ValidationError))
m_self = M.create({'workspace_id': w.id, 'user_id': u_p.id, 'role': 'counselor'})
check('participant who is also a counselor cannot be responsible for themselves',
      raises(lambda: a1.write({'responsible_id': m_self.id}), ValidationError))
org2 = env['res.partner'].create({'name': 'سازمان دیگر', 'is_company': True})
w2 = WS.create({'approved_on': '2026-01-01 00:00:00', 'name': 'دیگر', 'purpose': 'employment', 'partner_id': org2.id})
w2.state = 'active'
m_x = M.create({'workspace_id': w2.id, 'user_id': puser('x').id, 'role': 'hr_admin'})
check('responsible must belong to the same workspace', raises(lambda: a1.write({'responsible_id': m_x.id}), ValidationError))

# ---- imported results
at_i = mk('واردشده', u_o).action_accept(puser('imp'), False)
at_i.write({'source': 'import', 'state': 'done'})
check('unassigned import visible to counselors and owner', at_i.ts_org_visible_to(m_a) and at_i.ts_org_visible_to(m_o))
at_i.responsible_id = m_b
check('assigned import visible only to its responsible counselor and owner',
      at_i.ts_org_visible_to(m_b) and at_i.ts_org_visible_to(m_o) and not at_i.ts_org_visible_to(m_a))
check('import responsible change audited', env['ts.audit.event'].search_count(
    [('event_type', '=', 'attempt.responsible_change'), ('res_id', '=', at_i.id)]) == 1)
check('import responsible must be a specialist of that workspace', raises(lambda: at_i.write({'responsible_id': m_x.id}), ValidationError))

# ---- clinic: unassigned queue is not shown to a clinician
org3 = env['res.partner'].create({'name': 'کلینیک آزمون', 'is_company': True})
wc = WS.create({'approved_on': '2026-01-01 00:00:00', 'name': 'کلینیک مسئول', 'purpose': 'clinical', 'partner_id': org3.id, 'escalation_contact_id': org3.id})
wc.state = 'active'
m_dir = M.create({'workspace_id': wc.id, 'user_id': puser('dir').id, 'role': 'clinic_director', 'license_number': 'D-1'})
m_cl = M.create({'workspace_id': wc.id, 'user_id': puser('cl').id, 'role': 'clinician', 'license_number': 'C-1'})
m_dir.action_verify()
m_cl.action_verify()
ac = mk('مراجع', u_o, ws=wc, ins=pub[0])
done(ac, u_p)
check('clinic unassigned: clinician sees nothing, director sees', ac.visible_results(m_cl)[0] == 'none'
      and ac.visible_results(m_dir)[0] == 'clinical')
ac.responsible_id = m_cl
check('clinic assigned: clinician now sees it', ac.visible_results(m_cl)[0] == 'clinical')

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
