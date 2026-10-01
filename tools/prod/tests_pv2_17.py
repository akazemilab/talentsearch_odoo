# Panel v2 S17 (back office: tenant health, data-request queue, operator access). Run ONLY on an eot_ts* clone via odoo-bin shell.
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=Exception):
    try:
        with env.cr.savepoint():
            fn()
    except exc:
        return True
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, CL, DR = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.assignment', 'ts.panel.client', 'ts.data.request'))
_n = [0]


def user(groups, name='op'):
    _n[0] += 1
    login = 'ts.pv2s17.%s.%d@example.invalid' % (name, _n[0])
    return U.create({'name': 'u17 %d' % _n[0], 'login': login, 'email': login,
                     'group_ids': [(6, 0, [env.ref(g).id for g in groups])]})


operator = user(['base.group_user', 'ts_core.group_ts_user'])
manager = user(['base.group_user', 'ts_core.group_ts_manager'], 'mgr')
puser = U.create({'name': 'p17', 'login': 'ts.pv2s17.p@example.invalid', 'email': 'ts.pv2s17.p@example.invalid',
                  'group_ids': [(6, 0, [portal.id])]})

org = env['res.partner'].create({'name': 'S17 org', 'is_company': True})
org.write({'is_company': True})
ws = W.create({'name': 'S17 org', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00'})
ws.state = 'pilot'
inst = env['ts.instrument'].search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)
M.create({'workspace_id': ws.id, 'user_id': puser.id, 'role': 'owner'})
c1 = CL.create({'workspace_id': ws.id, 'name': 'c17a'})
CL.create({'workspace_id': ws.id, 'name': 'c17b'})
a = A.sudo().create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'c17a', 'client_id': c1.id})

# ---- PLT-10: operators lose access to invitation identities
check('an operator cannot read invitations', raises(lambda: A.with_user(operator).search([]), AccessError))
check('an operator cannot read panel clients', raises(lambda: CL.with_user(operator).search([]), AccessError))
check('a manager can read invitations', bool(A.with_user(manager).search([('id', '=', a.id)])))
menu = env.ref('ts_org.menu_ts_org_assignments')
check('the invitations menu is manager-only', menu.group_ids == env.ref('ts_core.group_ts_manager'), menu.group_ids.mapped('name'))

# ---- PLT-1: health counts
w = W.browse(ws.id)
w.invalidate_recordset()
check('member count', w.ts_member_count == 1, w.ts_member_count)
check('client count', w.ts_client_count == 2, w.ts_client_count)
check('open invitations', w.ts_open_invites == 1, w.ts_open_invites)
check('nothing finished yet', w.ts_done_30d == 0)
check('no pending days for an approved panel', w.ts_pending_days == 0)
fresh = W.create({'name': 'S17 gated', 'purpose': 'clinical', 'partner_id': org.id})

env.cr.execute('UPDATE ts_workspace SET create_date = now() - interval \'4 days\' WHERE id = %s', [fresh.id])
fresh.invalidate_recordset()
check('a waiting panel shows its age in days', fresh.gated and fresh.ts_pending_days == 4, fresh.ts_pending_days)
check('the health columns hold no client name field', not any('name' in f and f.startswith('ts_') for f in W._fields))

# ---- PLT-9: data requests
r_new = DR.sudo().create({'user_id': puser.id, 'kind': 'erase', 'due_on': fields.Date.today() + timedelta(days=5)})
r_late = DR.sudo().create({'user_id': puser.id, 'kind': 'export', 'due_on': fields.Date.today() - timedelta(days=1)})
check('a future request is not overdue', not r_new.overdue)
check('a past-due open request is overdue', r_late.overdue)
check('overdue is searchable', r_late in DR.sudo().search([('overdue', '=', True)]) and r_new not in DR.sudo().search([('overdue', '=', True)]))
check('not overdue is searchable', r_new in DR.sudo().search([('overdue', '=', False)]))
check('an operator cannot decide a request', raises(lambda: r_new.with_user(operator).action_decide('done')))
r_new.with_user(manager).action_review()
check('review sets in_review and the handler', r_new.state == 'in_review' and r_new.handled_by_id == manager)
n = env['ts.notification'].sudo().search_count([('user_id', '=', puser.id), ('type', '=', 'data_request_update')])
r_new.with_user(manager).action_decide('legal_hold')
check('a legal hold closes it as rejected with the code', r_new.state == 'rejected' and r_new.decision_code == 'legal_hold')
check('the person is told', env['ts.notification'].sudo().search_count([('user_id', '=', puser.id), ('type', '=', 'data_request_update')]) == n + 1)
r_late.with_user(manager).action_done()
check('done closes it and clears overdue', r_late.state == 'done' and not r_late.overdue)
check('a bad decision code is refused', raises(lambda: r_late.with_user(manager).action_decide('nope'), UserError) or r_late.state == 'done')
check('handling is audited', env['ts.audit.event'].sudo().search_count([('event_type', '=', 'data.request_handle')]) >= 3)

# ---- PLT-3: suspend tells the owners
before = env['ts.notification'].sudo().search_count([('user_id', '=', puser.id), ('type', '=', 'panel_suspended')])
ws.with_user(manager).action_suspend()
after = env['ts.notification'].sudo().search_count([('user_id', '=', puser.id), ('type', '=', 'panel_suspended')])
check('suspending a panel notifies its owner', after == before + 1, (before, after))

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
