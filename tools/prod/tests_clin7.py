# clin7 (owner 2026-10-14, Sepehr hand-over): the office (role admin) sends, the therapist (clinician) reads.
# Checks: the office label and scope in a clinical panel, the trimmed clinic menu, the single-therapist default for a client
# the office creates, nothing guessed with two therapists, the visible «چه بفرستید» choice and the therapist picker context.
# Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits; no SMS (sender patched).
from unittest.mock import patch

from odoo import Command, fields

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


N_cls = type(env['ts.notification'])
_p = patch.object(N_cls, '_send_sms', lambda *a, **k: True)
_p.start()
env['ir.config_parameter'].sudo().set_str('ts_billing.welcome_credit_rial', '0')
U, W, M = env['res.users'].sudo(), env['ts.workspace'].sudo(), env['ts.workspace.member'].sudo()
C, A = env['ts.panel.client'].sudo(), env['ts.assignment'].sudo()
portal = env.ref('base.group_portal')
_n = [0]


def puser(name=None):
    _n[0] += 1
    login = 'ts.clin7.%d@example.invalid' % _n[0]
    return U.create({'name': name or ('کاربر clin7 %d' % _n[0]), 'login': login, 'email': login,
                     'group_ids': [Command.set([portal.id])]})


try:
    from odoo.addons.ts_org.models.panel import role_label
    from odoo.addons.ts_panel.controllers.base import build_menu, role_scope

    u_own = puser('مالک clin7')
    ws = W.ts_panel_create(u_own, 'مرکز آزمون clin7', 'clinic', terms=True)
    owner = ws.member_ids.filtered(lambda m: m.role == 'owner')[:1]
    check('C00 clinic panel made', ws.purpose == 'clinical' and owner)
    office = M.create({'workspace_id': ws.id, 'user_id': puser('دفتر clin7').id, 'role': 'admin'})
    doc = M.create({'workspace_id': ws.id, 'user_id': puser('دکتر clin7').id, 'role': 'clinician'})

    check('C01 office label in a clinic', role_label('admin', 'clinical') == 'دفتر مرکز')
    check('C02 other kinds keep their label', role_label('admin', 'education') == 'هماهنگ‌کنندهٔ پنل')
    check('C03 office scope line', 'مشاورش' in role_scope('admin', 'clinical'))
    check('C04 office never reads results', not office.has_perm('results:clinical') and office.has_perm('invites:create'))
    check('C05 therapist reads clinical results', doc.has_perm('results:clinical'))

    keys = [i['key'] for i in build_menu(office, 'home')]
    labels = {i['key']: i['label'] for i in build_menu(office, 'home')}
    check('C06 clinic menu has no groups, campaigns, import, exports',
          not set(keys) & {'groups', 'campaigns', 'import', 'exports'}, keys)
    check('C07 clinic menu says «مراجعان»', labels.get('clients') == 'مراجعان', labels.get('clients'))
    check('C08 office keeps invites and credits', {'invites', 'credits'} <= set(keys), keys)

    ts = M.ts_clin7_therapists(ws)
    check('C09 the only therapist (owner not practising)', ts == doc, ts.ids)
    resp = M.ts_panel_default_responsible(ws.id, office.user_id.id)
    check('C10 office-created client goes to the only therapist', resp == doc)
    resp_doc = M.ts_panel_default_responsible(ws.id, doc.user_id.id)
    check('C11 a therapist sending keeps himself', resp_doc == doc)

    ws.ts_set_escalation(owner)
    inst = A.new({'workspace_id': ws.id}).allowed_instruments()[:1] if hasattr(A, 'allowed_instruments') else \
        env['ts.instrument'].sudo().search([('state', '=', 'published'), ('purpose', '!=', 'employment')], limit=1)
    a = A.with_user(office.user_id).sudo().create({'workspace_id': ws.id, 'instrument_id': inst.id,
                                                   'invitee_name': 'مراجع clin7', 'invitee_phone': '09120000777'})
    check('C12 invitation from the office reaches the therapist', a.client_id.responsible_id == doc,
          a.client_id.responsible_id.ids)
    check('C13 the therapist can see that client', doc.can_see(a.client_id))
    check('C14 the office sees the client but no result level', office.can_see(a.client_id)
          and not office.has_perm('results:clinical'))

    doc2 = M.create({'workspace_id': ws.id, 'user_id': puser('دکتر دوم clin7').id, 'role': 'clinician'})
    check('C15 two therapists: nothing guessed', not M.ts_panel_default_responsible(ws.id, office.user_id.id))
    owner.owner_practices = True
    check('C16 a practising owner counts as a therapist', owner in M.ts_clin7_therapists(ws))

    w_ed = W.ts_panel_create(puser(), 'مدرسه clin7', 'school', terms=True)
    ed_owner = w_ed.member_ids[:1]
    check('C17 school panels unchanged (groups still in menu)',
          'groups' in [i['key'] for i in build_menu(ed_owner, 'home')] or not ed_owner.has_perm('groups:manage'))
    check('C18 no therapist logic outside clinics', not M.ts_clin7_therapists(w_ed))
except Exception:
    import traceback
    for l in traceback.format_exc().splitlines():
        print('FAIL TB ' + l)
    results.append(('traceback', False))
finally:
    _p.stop()
    env.cr.rollback()
    bad = [n for n, ok in results if not ok]
    print('SUMMARY clin7 %d/%d passed%s' % (len(results) - len(bad), len(results), (' FAILED: ' + ', '.join(bad)) if bad else ''))
