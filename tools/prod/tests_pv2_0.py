# Panel v2 S0 (G28 usage event for TALENT-INV-15).
# Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits (rolls back at the end).
from odoo.exceptions import UserError, ValidationError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)


def puser(n):
    login = 'ts.pv2s0.%s@example.invalid' % n
    return U.search([('login', '=', login)], limit=1) or U.create(
        {'name': 'کاربر ' + n, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')])
v = inst.current_version_id
owner, student = puser('owner'), puser('student')
org = env['res.partner'].create({'name': 'مؤسسهٔ آزمون S0', 'is_company': True})
ws = env['ts.workspace'].create({'name': 'مؤسسهٔ آزمون S0', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00'})
ws.state = 'pilot'
env['ts.workspace.member'].create({'workspace_id': ws.id, 'user_id': owner.id, 'role': 'owner'})
a = env['ts.assignment'].sudo().create({
    'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'دانش‌آموز آزمون', 'invited_by_id': owner.id})
att = a.action_accept(student, share=True)
check('accepted invitation creates a matrix attempt in the panel', att.workspace_id == ws and att.ts_is_matrix())
att.give_consent()
items = att.active_items()
for n, label in enumerate(['ریاضی', 'هنر']):
    f = att.ts_add_field(label)
    for i, it in enumerate(items):
        att.ts_save_cell(f, it.id, (i * (n + 1) + n) % 5 + 1)
    att.ts_finish_field(f)
Usage = env['ts.usage.event'].sudo()
check('no usage event before the attempt is scored', not Usage.search_count([('attempt_id', '=', att.id)]))
check('submit ok', att.action_submit() is True and att.state == 'done')
ev = Usage.search([('attempt_id', '=', att.id)])
check('G28: one usage event written for a TALENT-INV-15 completion',
      len(ev) == 1 and ev.workspace_id == ws and ev.assignment_id == a)
check('submit again is idempotent (still one event)',
      att.action_submit() is True and Usage.search_count([('attempt_id', '=', att.id)]) == 1)

# a self-taken matrix attempt (no panel) writes no event
solo = puser('solo')
att2 = env['ts.attempt'].create({'user_id': solo.id, 'instrument_id': inst.id, 'version_id': v.id})
att2.give_consent()
for n, label in enumerate(['ریاضی', 'هنر']):
    f = att2.ts_add_field(label)
    for i, it in enumerate(att2.active_items()):
        att2.ts_save_cell(f, it.id, (i + n) % 5 + 1)
    att2.ts_finish_field(f)
att2.action_submit()
check('self-taken result (no panel) writes no usage event',
      att2.state == 'done' and not Usage.search_count([('attempt_id', '=', att2.id)]))

# imported results never count
imp = env['ts.attempt'].search([('source', '=', 'import'), ('workspace_id', '!=', False)], limit=1)
n0 = Usage.search_count([('attempt_id', '=', imp.id)]) if imp else 0
if imp:
    imp._ts_panel_record_usage()
check('imported results are never counted', (not imp) or Usage.search_count([('attempt_id', '=', imp.id)]) == n0)

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
env.cr.rollback()
