# Stage 1 acceptance tests. Run ONLY on an eot_ts* clone:
#   sudo -u odoo env HOME=/opt/odoo odoo-bin shell -d eot_tsN ... < tests_stage1.py
# Creates throwaway records, prints PASS/FAIL per check, then rolls back.
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
    except Exception as e:  # wrong exception type is a failure
        print('    unexpected', type(e).__name__, str(e)[:120])
        return False
    return False


site = env.ref('ts_website.website_ts')
check('website 2 exists and is not website 1', site.id != 1, 'id=%s' % site.id)
check('website 2 domain', site.domain == 'https://ts.innerquest.me', site.domain)
check('website 2 is Persian only', site.language_ids.mapped('code') == ['fa_IR'])
check('website 1 untouched name/domain', env['website'].browse(1).domain == 'https://www.eot.ir')
check('website 2 own top menu', site.menu_id.website_id == site and len(site.menu_id.child_id) == 7)
home = env['website.page'].search([('website_id', '=', site.id), ('url', '=', '/')])
check('website 2 homepage uses ts_website.home', len(home) == 1 and 'ts_website.home' in home.view_id.arch_db)
ts_views = env['ir.ui.view'].search([('key', '=like', 'ts_website.%')])
check('every ts_website view is bound to website 2', ts_views and all(v.website_id == site for v in ts_views), '%d views' % len(ts_views))
leaked = env['ir.ui.view'].search_count([('website_id', '=', 1), ('key', '=like', 'ts_%')])
check('no ts view on website 1', leaked == 0)

portal = env.ref('base.group_portal')
mk = lambda login: env['res.users'].with_context(no_reset_password=True).create(
    {'name': login, 'login': login + '@example.invalid', 'group_ids': [(6, 0, [portal.id])]})
u_emp, u_cli, u_out = mk('ts_t_hr'), mk('ts_t_clin'), mk('ts_t_out')
org1 = env['res.partner'].create({'name': 'TS Test Org 1', 'is_company': True})
org2 = env['res.partner'].create({'name': 'TS Test Org 2', 'is_company': True})
W = env['ts.workspace']
ws_emp = W.create({'name': 'TS test employment', 'purpose': 'employment', 'partner_id': org1.id})
ws_cli = W.create({'name': 'TS test clinical', 'purpose': 'clinical', 'partner_id': org2.id})
check('workspace codes assigned', ws_emp.code.startswith('TSW-') and ws_cli.code.startswith('TSW-'), ws_emp.code)
M = env['ts.workspace.member']
M.create({'workspace_id': ws_emp.id, 'user_id': u_emp.id, 'role': 'hr_admin'})
M.create({'workspace_id': ws_cli.id, 'user_id': u_cli.id, 'role': 'clinician', 'license_number': 'TEST-1'})

check('role must match purpose (clinician in employment refused)',
      raises(lambda: M.create({'workspace_id': ws_emp.id, 'user_id': u_out.id, 'role': 'clinician'}), ValidationError))
check('internal users cannot be customer members',
      raises(lambda: M.create({'workspace_id': ws_emp.id, 'user_id': env.ref('base.user_admin').id, 'role': 'hr_admin'}), ValidationError))
check('clinician starts unverified', M.search([('user_id', '=', u_cli.id)]).verification_state == 'pending')
check('clinical workspace cannot go live without escalation owner',
      raises(lambda: ws_cli.write({'state': 'pilot'}), ValidationError))
ws_edu = W.create({'name': 'TS test education', 'purpose': 'education', 'partner_id': org1.id})
check('gated purpose cannot be activated', ws_edu.gated and raises(lambda: ws_edu.write({'state': 'active'}), ValidationError))
ws_emp.write({'state': 'pilot'})
check('purpose locked after draft', raises(lambda: ws_emp.write({'purpose': 'clinical'}), UserError))

vis_emp = W.with_user(u_emp).search([])
check('HR portal user sees only own workspace', vis_emp == ws_emp, str(vis_emp.ids))
check('HR portal user cannot read clinical workspace', raises(lambda: ws_cli.with_user(u_emp).read(['name']), AccessError))
check('clinician cannot read employment workspace', raises(lambda: ws_emp.with_user(u_cli).read(['name']), AccessError))
check('outsider sees no workspace', not W.with_user(u_out).search([]))
check('outsider sees no members', not M.with_user(u_out).search([]))
check('portal user cannot create workspace', raises(lambda: W.with_user(u_emp).create({'name': 'x', 'purpose': 'employment', 'partner_id': org1.id}), AccessError))
check('portal user cannot read audit', raises(lambda: env['ts.audit.event'].with_user(u_emp).search([]), AccessError))

A = env['ts.audit.event']
ev = A.search([('workspace_id', '=', ws_emp.id)])
check('audit events recorded (create, member, state)', len(ev) >= 3, str(sorted(set(ev.mapped('event_type')))))
check('audit cannot be edited (even admin)', raises(lambda: ev[:1].write({'event_type': 'x'}), UserError))
check('audit cannot be deleted (even admin)', raises(lambda: ev[:1].unlink(), UserError))
check('audit cannot be created directly', raises(lambda: A.create({'event_type': 'forged'}), UserError))

team = env.ref('ts_website.crm_team_ts')
stages = env['crm.stage'].search([('team_ids', 'in', team.ids)])
check('Talent Search pipeline has 8 own stages', len(stages.filtered(lambda s: s.team_ids == team)) == 8)
check('stock CRM stages not in Talent Search pipeline', not stages.filtered(lambda s: s.team_ids != team))
if 'helpdesk.team' in env:
    check('no helpdesk team on website 1', not env['helpdesk.team'].with_context(active_test=False).search([('website_id', '=', 1)]))

env.cr.rollback()
fails = [n for n, ok in results if not ok]
print('SUMMARY %d/%d passed%s' % (len(results) - len(fails), len(results), ('; FAILED: ' + '; '.join(fails)) if fails else ''))
