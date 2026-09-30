# Stage-5 edge cases: a specialist leaves, separate panels per person, emergency access. Clones only.
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


def puser(n):
    login = 'ts.edge.%s@example.invalid' % n
    return U.search([('login', '=', login)], limit=1) or U.create(
        {'name': 'کاربر ' + n, 'login': login, 'group_ids': [(6, 0, [portal.id])]})


W, M, A, AUD = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment'], env['ts.audit.event']
u_o, u_a, u_b, u_p1, u_p2 = (puser(n) for n in ('owner', 'ca', 'cb', 'p1', 'p2'))
org = env['res.partner'].create({'name': 'مدرسهٔ مرزی', 'is_company': True})
w = W.create({'name': 'مدرسهٔ مرزی', 'purpose': 'education', 'partner_id': org.id})
w.write({'state': 'active'})
m_o = M.create({'workspace_id': w.id, 'user_id': u_o.id, 'role': 'owner'})
m_a = M.create({'workspace_id': w.id, 'user_id': u_a.id, 'role': 'counselor'})
m_b = M.create({'workspace_id': w.id, 'user_id': u_b.id, 'role': 'counselor'})
inst = env['ts.instrument'].search([('state', '=', 'published')], limit=1)


def mk(name, by):
    return A.create({'workspace_id': w.id, 'instrument_id': inst.id, 'invitee_name': name, 'invited_by_id': by.id})


def done(a, user):
    at = a.action_accept(user, True)
    at.write({'state': 'done', 'released': True})
    return at


# ---- a counselor leaves: the clients go back to the owner's unassigned queue
a1, a2 = mk('الف ۱', u_a), mk('الف ۲', u_a)
b1 = mk('ب ۱', u_b)
done(a1, u_p1); done(a2, u_p2)
at_i = mk('واردشده', u_o).action_accept(puser('imp'), False)
at_i.write({'source': 'import', 'state': 'done', 'responsible_id': m_a.id})
check('before leaving: counselor A sees own clients', a1.visible_results(m_a)[0] == 'education' and at_i.ts_org_visible_to(m_a))
before = AUD.search_count([('event_type', '=', 'assignment.responsible_change')])
m_a.write({'active': False})
check('leaving counselor: their participants become unassigned', not a1.responsible_id and not a2.responsible_id)
check('leaving counselor: their imported results become unassigned', not at_i.responsible_id)
check('other counselor keeps their own client', b1.responsible_id == m_b)
check('each release is audit-logged', AUD.search_count([('event_type', '=', 'assignment.responsible_change')]) == before + 2)
check('import release audit-logged', AUD.search_count([('event_type', '=', 'attempt.responsible_change'), ('res_id', '=', at_i.id)]) >= 2)
check('owner still sees the released results', a1.visible_results(m_o)[0] == 'education' and at_i.ts_org_visible_to(m_o))
check('the leaver no longer has access', a1.visible_results(m_a)[0] == 'none' and not m_a.can_act())
check('nothing disappeared: released results are in the unassigned queue',
      set((a1 | a2).ids) <= set(A.search([('workspace_id', '=', w.id), ('responsible_id', '=', False)]).ids))
check('owner can hand a released client to the other counselor', not raises(lambda: a1.write({'responsible_id': m_b.id})))

# ---- role change away from a responsible role releases too
m_c = M.create({'workspace_id': w.id, 'user_id': puser('cc').id, 'role': 'counselor'})
c1 = mk('پ ۱', m_c.user_id)
check('counselor inviter is responsible', c1.responsible_id == m_c)
m_c.write({'role': 'owner'})
check('owner-level role keeps responsibility (still a responsible role)', c1.responsible_id == m_c)
m_c.unlink()
check('deleting a member also releases their clients', not c1.responsible_id)

# ---- separate panels for the same person: nothing leaks between them
org_b = env['res.partner'].create({'name': 'کلینیک شخصی', 'is_company': True})
w_b = W.create({'name': 'پنل یک‌نفرهٔ مرزی', 'purpose': 'education', 'partner_id': org_b.id})
w_b.write({'state': 'active'})
m_a2 = M.create({'workspace_id': w_b.id, 'user_id': u_a.id, 'role': 'owner'})
a_priv = A.create({'workspace_id': w_b.id, 'instrument_id': inst.id, 'invitee_name': 'خصوصی', 'invited_by_id': u_a.id})
done(a_priv, puser('priv'))
check('same person, two panels: private client not visible in the institute panel',
      a_priv.visible_results(m_a2)[0] == 'education' and a_priv.visible_results(m_o)[0] == 'none' and a_priv.visible_results(m_b)[0] == 'none')
check('a person has one membership per panel', len(M.with_context(active_test=False).search([('user_id', '=', u_a.id)])) == 2 and len(M.search([('user_id', '=', u_a.id), ('active', '=', True)])) == 1)
check('members cannot be responsible across panels', raises(lambda: a_priv.write({'responsible_id': m_b.id})))

# ---- emergency access (clinical panel, platform manager, time-boxed, audited)
E = env['ts.emergency.access']
org_c = env['res.partner'].create({'name': 'کلینیک اضطراری', 'is_company': True})
w_c = W.create({'approved_on': '2026-01-01 00:00:00', 'name': 'کلینیک اضطراری', 'purpose': 'clinical', 'partner_id': org_c.id,
                'escalation_contact_id': org_c.id})
w_c.write({'state': 'active'})
u_dir = puser('dir')
M.create({'workspace_id': w_c.id, 'user_id': u_dir.id, 'role': 'owner'})
check('emergency access needs a real reason', raises(lambda: E.create({'workspace_id': w_c.id, 'reason': 'کوتاه'})))
check('emergency access is only for clinical panels', raises(lambda: E.create({'workspace_id': w.id, 'reason': 'شرکت‌کننده در خطر جدی است و باید تماس گرفت'})))
check('a panel user cannot open emergency access', raises(lambda: E.with_user(u_dir).create({'workspace_id': w_c.id, 'reason': 'شرکت‌کننده در خطر جدی است و باید تماس گرفت'}), (UserError, ValidationError, Exception)))
msgs = env['mail.message'].search_count([('model', '=', 'ts.workspace'), ('res_id', '=', w_c.id)])
e = E.create({'workspace_id': w_c.id, 'reason': 'شرکت‌کننده در خطر جدی است و باید تماس گرفت'})
check('opens for 24 hours', e.state == 'open' and 23 <= (e.expires_at - e.opened_at).total_seconds() / 3600 <= 25)
check('opening is audit-logged', AUD.search_count([('event_type', '=', 'emergency.open'), ('workspace_id', '=', w_c.id)]) == 1)
check('the panel owner is told', env['mail.message'].search_count([('model', '=', 'ts.workspace'), ('res_id', '=', w_c.id)]) > msgs)
act = e.action_view_results()
check('viewing results is allowed while open and is audit-logged',
      act['res_model'] == 'ts.assignment' and AUD.search_count([('event_type', '=', 'emergency.view'), ('workspace_id', '=', w_c.id)]) == 1)
e.action_close()
check('closing ends the access and is audit-logged', e.state == 'closed' and raises(lambda: e.action_view_results())
      and AUD.search_count([('event_type', '=', 'emergency.close'), ('workspace_id', '=', w_c.id)]) == 1)
e2 = E.create({'workspace_id': w_c.id, 'reason': 'دومین مورد اضطراری برای همان پنل بالینی'})
e2.write({'expires_at': fields.Datetime.now() - __import__('datetime').timedelta(minutes=1)})
check('expired access cannot be used', e2.state == 'expired' and raises(lambda: e2.action_view_results()))

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
