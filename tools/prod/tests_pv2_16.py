# Panel v2 S16 (minors and guardian consent). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, T, CL = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.assignment', 'ts.attempt', 'ts.panel.client'))
Inst, Rec = env['ts.instrument'], env['ts.consent.record']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s16.%d@example.invalid' % _n[0]
    return U.create({'name': 'u16 %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


org = env['res.partner'].create({'name': 'S16 school', 'is_company': True})
org.write({'is_company': True})
ws = W.create({'name': 'S16 school', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00'})
ws.state = 'pilot'
owner = M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': 'owner'})
couns = M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': 'counselor', 'license_number': 'T-1',
                  'verification_state': 'verified'})
inst = Inst.search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)


def finish(att):
    att.give_consent()
    for it in att.active_items():
        att.save_answer(it.id, 1 + it.id % 5)
    att.action_submit()
    return att


minor = CL.create({'workspace_id': ws.id, 'name': 'minor 16', 'age_group': 'minor'})
adult = CL.create({'workspace_id': ws.id, 'name': 'adult 16', 'age_group': 'adult'})
unknown = CL.create({'workspace_id': ws.id, 'name': 'unknown 16'})
check('a new minor has no guardian consent', minor.guardian_consent == 'none' and minor.ts_needs_guardian())
check('an adult needs none', not adult.ts_needs_guardian())
check('unknown age needs none', not unknown.ts_needs_guardian())

# result withheld until attested
a = A.sudo().create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': minor.name, 'client_id': minor.id})
at = finish(a.action_accept(puser(), share=True))
a.invalidate_recordset()
check('minor result is status only without guardian consent', a.result_level(couns) == 'status', a.result_level(couns))
n_audit = env['ts.audit.event'].search_count([('event_type', '=', 'guardian.attest')])
minor.ts_attest_guardian(owner)
a.invalidate_recordset()
row = Rec.search([('kind', '=', 'guardian_attest'), ('client_id', '=', minor.id)])
check('attest writes one ledger row by the panel member', len(row) == 1 and row.given_as == 'panel_member' and row.method == 'attestation')
check('attest sets attested', minor.guardian_consent == 'attested' and minor.guardian_consent_on)
check('attest audits once', env['ts.audit.event'].search_count([('event_type', '=', 'guardian.attest')]) == n_audit + 1)
check('after attest the counselor sees the education level', a.result_level(couns) == 'education', a.result_level(couns))
minor.ts_attest_guardian(owner)
check('attest twice writes nothing new', Rec.search_count([('kind', '=', 'guardian_attest'), ('client_id', '=', minor.id)]) == 1)
adult.ts_attest_guardian(owner)
check('an adult is never attested', adult.guardian_consent == 'none')

# service ledger rows from give_consent
rows = Rec.search([('kind', '=', 'service'), ('attempt_id', '=', at.id)])
check('give_consent wrote a service ledger row', len(rows) == 1 and rows.client_id == minor)
at2 = T.create({'user_id': puser().id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
at2.give_consent(research=True)
check('research consent wrote a research row', Rec.search_count([('kind', '=', 'research'), ('attempt_id', '=', at2.id)]) == 1)

# campaign fields
check('campaign carries the attestation fields', {'guardian_attested_by_id', 'guardian_attested_on'} <= set(env['ts.campaign']._fields))

print('S16 ORM: %d/%d' % (sum(1 for _, ok in results if ok), len(results)))
env.cr.rollback()
