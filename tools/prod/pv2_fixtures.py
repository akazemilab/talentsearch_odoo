# Panel v2 shared fixture builder (S0, rule 10). Run inside `odoo shell` on a CLONE:
#   ... odoo-bin shell -d eot_tsNN < tools/prod/pv2_fixtures.py
# Fictional data only. Logins ts.pv2.<panel>.<role>@example.invalid, panel names «پنل آزمایشی ...».
# Upserts on every run: two runs give identical counts (test P22). Later stages extend this file
# (clients, every invitation state, new roles); it never touches records it did not create.
from odoo import fields

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run fixtures outside a clone'

portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment']
inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')])

PANELS = [  # (key, name, purpose, roles present in the panel)
    ('edu', 'پنل آزمایشی آموزشی', 'education', ['owner', 'counselor']),
    ('clin', 'پنل آزمایشی بالینی', 'clinical', ['owner', 'clinician', 'clinic_director']),
    ('emp', 'پنل آزمایشی استخدامی', 'employment', ['owner', 'hr_admin', 'hiring_manager', 'reviewer']),
]


def user(key, name):
    login = 'ts.pv2.%s@example.invalid' % key
    return U.search([('login', '=', login)], limit=1) or U.create(
        {'name': name, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(name, purpose):
    org = env['res.partner'].search([('name', '=', name), ('is_company', '=', True)], limit=1) or env['res.partner'].create(
        {'name': name, 'is_company': True})
    ws = W.search([('partner_id', '=', org.id)], limit=1) or W.create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, u, role):
    m = M.search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)], limit=1) or M.create(
        {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    if m.role != role:
        m.role = role
    if role in ('clinician', 'clinic_director', 'counselor') and m.verification_state != 'verified':
        # action_verify needs the platform-manager group; fixtures record the same outcome directly
        m.write({'license_number': 'TEST-%s' % m.id, 'verification_state': 'verified', 'verified_on': fields.Datetime.now()})
    return m


def finish_matrix(att):
    att.give_consent()
    items = att.active_items()
    for n, label in enumerate(['ریاضی', 'هنر', 'ورزش', 'زبان']):
        f = att.ts_add_field(label)
        for i, it in enumerate(items):
            att.ts_save_cell(f, it.id, (i * (n % 3 + 1) + 2 * n + i // 5) % 5 + 1)
        att.ts_finish_field(f)
    assert att.action_submit()
    return att


made = {}
for key, name, purpose, roles in PANELS:
    ws = panel(name, purpose)
    members = {}
    for role in roles:
        members[role] = member(ws, user('%s.%s' % (key, role), 'آزمایشی %s %s' % (key, role)), role)
    made[key] = (ws, members)

# one finished and shared result in the education panel, produced by the real action_submit
ws_edu, mem_edu = made['edu']
stu = user('edu.student', 'دانش‌آموز آزمایشی')
a = A.search([('workspace_id', '=', ws_edu.id), ('invitee_name', '=', 'دانش‌آموز آزمایشی'), ('withdrawn', '=', False)], limit=1)
if not a:
    a = A.sudo().create({'workspace_id': ws_edu.id, 'instrument_id': inst.id, 'invitee_name': 'دانش‌آموز آزمایشی',
                         'invited_by_id': mem_edu['owner'].user_id.id})
    finish_matrix(a.action_accept(stu, share=True))
env.cr.commit()
ids = [w.id for w, _ in made.values()]
print('FIXTURES panels=%d members=%d assignments=%d done_attempts=%d usage=%d' % (
    len(ids),
    M.search_count([('workspace_id', 'in', ids)]),
    A.search_count([('workspace_id', 'in', ids)]),
    env['ts.attempt'].search_count([('workspace_id', 'in', ids), ('state', '=', 'done')]),
    env['ts.usage.event'].sudo().search_count([('workspace_id', 'in', ids)])))
