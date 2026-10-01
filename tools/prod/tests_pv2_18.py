# Panel v2 S18 (lifecycle: transfer, close, anonymise, retention dry-run, erase). Run ONLY on an eot_ts* clone via odoo-bin shell.
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn):
    try:
        with env.cr.savepoint():
            fn()
    except Exception:
        return True
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, T, CL = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.assignment', 'ts.attempt', 'ts.panel.client'))
DR, RL, N, C = env['ts.data.request'], env['ts.retention.log'], env['ts.notification'], env['ts.consent.record']
Inst = env['ts.instrument']
_n = [0]


def puser(groups=None):
    _n[0] += 1
    login = 'ts.pv2s18.%d@example.invalid' % _n[0]
    return U.create({'name': 'u18 %d' % _n[0], 'login': login, 'email': login,
                     'group_ids': [(6, 0, groups or [portal.id])]})


def panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role, **kw):
    m = M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role, **kw})
    if role in ('counselor', 'clinician'):
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m


def finish(att):
    att.give_consent()
    for it in att.active_items():
        att.save_answer(it.id, 1 + it.id % 5)
    att.action_submit()
    return att


inst = Inst.search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)
mgr = puser([env.ref('base.group_user').id, env.ref('ts_core.group_ts_manager').id])
op = puser([env.ref('base.group_user').id, env.ref('ts_core.group_ts_user').id])

# ---- ORG-7 transfer
edu = panel('education', 'S18 edu')
o1, adm, couns = member(edu, 'owner'), member(edu, 'admin'), member(edu, 'counselor')
n0 = N.sudo().search_count([('type', '=', 'panel_transferred')])
check('a non-owner cannot transfer', raises(lambda: edu.ts_transfer(couns, adm)))
check('the owner cannot hand over to themself', raises(lambda: edu.ts_transfer(o1, o1)))
other_ws_member = member(panel('education', 'S18 other'), 'owner')
check('a member of another panel is refused', raises(lambda: edu.ts_transfer(o1, other_ws_member)))
edu.ts_transfer(o1, adm, stay='admin')
check('the chosen member is the owner', adm.role == 'owner')
check('the old owner became admin', o1.role == 'admin')
check('both are notified', N.sudo().search_count([('type', '=', 'panel_transferred')]) == n0 + 2)
check('the transfer is audited', env['ts.audit.event'].sudo().search_count([('event_type', '=', 'panel.transfer'), ('res_id', '=', edu.id)]) == 1)
edu.ts_transfer(adm, couns, stay='owner')
check('stay as owner keeps two owners', adm.role == 'owner' and couns.role == 'owner')
check('an already-owner target is refused', raises(lambda: edu.ts_transfer(adm, couns)))

# ---- ORG-8 close
check('a non-owner cannot close', raises(lambda: edu.ts_close(o1)))
nc = N.sudo().search_count([('type', '=', 'panel_closed')])
edu.ts_close(adm)
check('the panel is closed with a time', edu.state == 'closed' and edu.closed_on)
check('owners are told', N.sudo().search_count([('type', '=', 'panel_closed')]) == nc + 2)
check('a closed panel gives staff only the view permission', o1.perms() == frozenset({'panel:view'}), o1.perms())
check('the owner may export within 90 days', 'clients:export' in adm.perms())
env.cr.execute("UPDATE ts_workspace SET closed_on = now() - interval '91 days' WHERE id = %s", [edu.id])
edu.invalidate_recordset()
adm.invalidate_recordset()
check('after 90 days the export right is gone', 'clients:export' not in adm.perms())
check('a closed panel cannot be closed again', raises(lambda: edu.ts_close(adm)))
check('the close is audited', env['ts.audit.event'].sudo().search_count([('event_type', '=', 'panel.close'), ('res_id', '=', edu.id)]) == 1)

# ---- anonymise
c1 = CL.create({'workspace_id': edu.id, 'name': 'Real Name', 'phone': '09121110001', 'email': 'a@example.invalid',
                'guardian_name': 'G', 'code': 'S18-1'})
ia = A.sudo().create({'workspace_id': edu.id, 'instrument_id': adm.allowed_instruments()[:1].id, 'invitee_name': 'Real Name', 'invitee_email': 'a@example.invalid',
                      'client_id': c1.id})
check('anonymise counts one client', c1.ts_anonymise() == 1)
check('contact fields are emptied', not (c1.phone or c1.email or c1.guardian_name or c1.code) and c1.name != 'Real Name' and c1.anonymised_on)
check('the invitation identity is emptied', ia.invitee_name != 'Real Name' and not ia.invitee_email)
check('anonymise is idempotent', c1.ts_anonymise() == 0)

# ---- retention: dry-run then on
c2 = CL.create({'workspace_id': edu.id, 'name': 'Second', 'phone': '09121110002'})
old_n = N.sudo().create({'user_id': puser().id, 'type': 'invite', 'title': 'x'}) if 'title' in N._fields else None
if old_n is None:
    old_n = N.sudo().search([], limit=1)
env.cr.execute("UPDATE ts_notification SET create_date = now() - interval '200 days' WHERE id = %s", [old_n.id])
old_n.invalidate_recordset()
env['ir.config_parameter'].sudo().set_param('ts_panel.retention_enabled', '0')
out = RL._cron_run()
check('dry-run counts the closed panel client', out['closed_panels'] >= 1, out)
check('dry-run counts the old notification', out['notifications'] >= 1)
check('dry-run deletes nothing', c2.exists() and not c2.anonymised_on and old_n.exists())
last = RL.search([('rule', '=', 'closed_panels')], limit=1)
check('the dry-run log says not applied', not last.applied and last.removed == 0 and last.would_remove >= 1)
env['ir.config_parameter'].sudo().set_param('ts_panel.retention_enabled', '1')
out = RL._cron_run()
c2.invalidate_recordset()
check('switched on, the closed panel client is anonymised', c2.anonymised_on and not c2.phone)
check('switched on, the old notification is deleted', not old_n.exists())
check('the run is audited with counts', env['ts.audit.event'].sudo().search_count([('event_type', '=', 'retention.run')]) == 2)
env['ir.config_parameter'].sudo().set_param('ts_panel.retention_enabled', '0')

# ---- PRV-4 erase
person = puser()
emp = panel('employment', 'S18 emp')
at = T.create({'user_id': person.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
finish(at)
share = A.ts_share_attempt(at, panel('education', 'S18 edu2').code, person)
cl = CL.create({'workspace_id': emp.id, 'name': 'Person Client', 'user_id': person.id, 'phone': '09121110003'})
req = DR.ts_open(person, 'erase')
check('an operator cannot run an erase', raises(lambda: req.with_user(op).action_erase()))
req.with_user(mgr).action_erase()
at.invalidate_recordset()
check('answers and results are gone', not at.answer_ids and not at.result_ids)
check('the attempt row stays with its dates', at.exists() and at.submitted_at and at.erased_on)
check('the share is revoked', share.share_level == 'none')
check('a share_revoke ledger row was written', C.search_count([('kind', '=', 'share_revoke'), ('user_id', '=', person.id)]) >= 1)
check('the client row linked to the account is anonymised', cl.anonymised_on and not cl.phone)
check('the account is deactivated', not person.active)
check('the request is done', req.state == 'done' and req.decision_code == 'done')
check('the erase is audited with counts', env['ts.audit.event'].sudo().search_count([('event_type', '=', 'data.erase'), ('res_id', '=', req.id)]) == 1)

# clinical panel: restricted, account kept
person2 = puser()
clin = panel('clinical', 'S18 clin')
at2 = T.create({'user_id': person2.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id, 'workspace_id': clin.id})
finish(at2)
req2 = DR.ts_open(person2, 'erase')
req2.with_user(mgr).action_erase()
at2.invalidate_recordset()
check('a clinical attempt is hidden, not erased', at2.answer_ids and not at2.released and not at2.erased_on)
check('the clinical request closes with legal_hold and the account stays', req2.decision_code == 'legal_hold' and person2.active)

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
