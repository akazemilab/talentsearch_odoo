# Panel v2 S2 (shell). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
from odoo.addons.ts_panel.controllers.base import MENU, build_menu

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M = env['ts.workspace'], env['ts.workspace.member']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s2.%d@example.invalid' % _n[0]
    return U.create({'name': login, 'login': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose):
    org = env['res.partner'].create({'name': 'پنل آزمون S2', 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': org.name, 'purpose': purpose, 'partner_id': org.id,
                   'escalation_contact_id': org.id if purpose == 'clinical' else False})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


check('menu: keys unique, help is last (WCAG 3.2.6)', len({i['key'] for i in MENU}) == len(MENU)
      and sorted(MENU, key=lambda i: i['seq'])[-1]['key'] == 'help')

u0 = puser()
check('header link: nobody -> False', u0.ts_panel_home() is False)
check('header link: public user -> False', env.ref('base.public_user').ts_panel_home() is False)
a, b = panel('education'), panel('employment')
m1 = M.create({'workspace_id': a.id, 'user_id': u0.id, 'role': 'owner'})
check('header link: exactly one panel -> its dashboard', u0.ts_panel_home() == '/my/workspaces/%s/home' % a.id)
M.create({'workspace_id': b.id, 'user_id': u0.id, 'role': 'owner'})
check('header link: several panels -> the list', u0.ts_panel_home() == '/my/workspaces')
M.create({'workspace_id': b.id, 'user_id': puser().id, 'role': 'owner'})   # a panel keeps one active owner
M.search([('workspace_id', '=', b.id), ('user_id', '=', u0.id)]).active = False
check('header link: a deactivated membership does not count', u0.ts_panel_home() == '/my/workspaces/%s/home' % a.id)

keys = {}
for role in ('owner', 'admin', 'counselor'):
    m = m1 if role == 'owner' else M.create({'workspace_id': a.id, 'user_id': puser().id, 'role': role})
    if role == 'counselor':
        m.write({'license_number': 'T', 'verification_state': 'verified'})
    keys[role] = [i['key'] for i in build_menu(m, 'home')]
check('menu per role: owner has settings, admin and counselor do not',
      keys['owner'] == ['home', 'legacy', 'members', 'settings', 'help'] and keys['admin'] == ['home', 'legacy', 'members', 'help']
      and keys['counselor'] == ['home', 'legacy', 'help'], str(keys))
cl = panel('clinical')
unv = M.create({'workspace_id': cl.id, 'user_id': puser().id, 'role': 'clinician'})
check('menu for an unverified clinician: dashboard and help only', [i['key'] for i in build_menu(unv, 'home')] == ['home', 'help'])
check('current item is flagged', [i['current'] for i in build_menu(m1, 'settings')] == [False, False, False, True, False])

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
