# Talent inventory (ts_talent) acceptance tests. Run ONLY on an eot_ts* clone via odoo-bin shell.

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


from odoo.addons.ts_talent.models import engine_matrix as EM

inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')])
check('instrument exists and is published', len(inst) == 1 and inst.state == 'published')
v = inst.current_version_id
check('matrix version 2/3/8 fields', v.mode == 'matrix' and (v.field_min, v.field_default, v.field_max) == (2, 3, 8))
check('15 verbatim items', len(v.item_ids) == 15)
check('5 scale + 7 composite factors', len(v.factor_ids.filtered(lambda f: f.kind == 'scale')) == 5 and len(v.factor_ids.filtered(lambda f: f.kind == 'composite')) == 7)
check('version is locked against edits', raises(lambda: v.write({'field_max': 9})))

env['res.users'].search([('login', '=', 'ts.talent.a@example.invalid')]).unlink()
user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'آزمون فهرست', 'login': 'ts.talent.a@example.invalid',
    'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
att = env['ts.attempt'].create({'user_id': user.id, 'instrument_id': inst.id, 'version_id': v.id})
check('attempt starts in consent', att.state == 'consent' and att.ts_is_matrix())
check('cannot add a field before consent', raises(lambda: att.ts_add_field('ریاضی')))
att.give_consent()
check('consent -> in_progress', att.state == 'in_progress')
items = att.active_items()
check('active items are the 15', len(items) == 15)

f1 = att.ts_add_field('  ریاضي ')
check('label cleaned (Arabic ye -> Persian)', f1.label == 'ریاضی', f1.label)
check('second field refused while first is a draft', raises(lambda: att.ts_add_field('علوم')))


def answer(field, pattern):
    for it, val in zip(items, pattern):
        field.attempt_id.ts_save_cell(field, it.id, val)


check('invalid value refused', raises(lambda: att.ts_save_cell(f1, items[0].id, 6)))
check('finish refused with unanswered items', raises(lambda: att.ts_finish_field(f1)))
p1 = [5, 4, 3, 2, 1, 5, 4, 3, 2, 1, 5, 4, 3, 2, 1]
answer(f1, p1)
check('cell re-save updates, no duplicate', (att.ts_save_cell(f1, items[0].id, 4), len(f1.cell_ids))[1] == 15)
att.ts_save_cell(f1, items[0].id, 5)
check('finish field ok', att.ts_finish_field(f1) == 'ok' and f1.state == 'done')
check('answers of a done field are locked', raises(lambda: att.ts_save_cell(f1, items[0].id, 1)))
check('same name refused (Arabic kaf/ye variant)', raises(lambda: att.ts_add_field('رياضي')))
check('submit refused with one field', raises(lambda: att.action_submit()))

f2 = att.ts_add_field('فارسی')
answer(f2, [3] * 15)
check('all-equal answers need confirmation', att.ts_finish_field(f2) == 'straight' and f2.state == 'draft')
check('confirmed straight-line accepted and flagged', att.ts_finish_field(f2, confirm_straight=True) == 'ok' and f2.flag_straight)
f3 = att.ts_add_field('هنر')
p3 = [1, 2, 3, 4, 5] * 3
answer(f3, p3)
att.ts_finish_field(f3)
check('progress computed (all answered)', att.progress >= 99, str(att.progress))
ok = att.action_submit()
check('submit ok', ok and att.state == 'done' and att.released and bool(att.profile_json))
prof = att.ts_profile()
ref = EM.score_matrix([{'label': 'ریاضی', 'answers': p1, 'seconds': None}, {'label': 'فارسی', 'answers': [3] * 15, 'seconds': None},
                       {'label': 'هنر', 'answers': p3, 'seconds': None}])
check('stored scores equal the pure engine (ignoring timing flags)',
      [f['scales'] for f in prof['fields']] == [f['scales'] for f in ref['fields']] and prof['mean'] == ref['mean'])
check('interpretation stored with 7 levels', all(k in prof['interpretation'] for k in ('brief', 'composite', 'focal', 'detail', 'types', 'weak', 'programs')))
check('rescore matches stored hash', att.rescore_matches())
check('submit is idempotent', att.action_submit() is True)
check('cannot add fields after submit', raises(lambda: att.ts_add_field('تاریخ')))

# report helpers run on the stored profile
from odoo.addons.ts_talent.models import report as R
lv = R.levels(prof['interpretation'], prof)
check('report: 7 levels of text', len(lv) == 7 and all(l['lines'] for l in lv))
check('report: charts for each field', all('<svg' in str(R.field_chart(f)) for f in prof['fields']))
check('report: programs use book names', any(p[1].startswith('آموزش جبرانی') for p in R.programs_list(prof['interpretation'])))

# imported (historical) participant: contact only, no user
partner = env['res.partner'].create({'name': 'شرکت‌کنندهٔ آزمون ورود'})
imp = env['ts.attempt'].create({'person_id': partner.id, 'instrument_id': inst.id, 'version_id': v.id,
                                'source': 'import', 'source_ref': 'test:import:1', 'state': 'done', 'released': False})
check('imported attempt has no user and is not released', not imp.user_id and imp.person_id == partner and not imp.released)
check('source_ref is unique', raises(lambda: env['ts.attempt'].create({
    'person_id': partner.id, 'instrument_id': inst.id, 'version_id': v.id, 'source': 'import', 'source_ref': 'test:import:1'}),
    exc=Exception))

# field cap
att2 = env['ts.attempt'].create({'user_id': user.id, 'instrument_id': inst.id, 'version_id': v.id})
att2.give_consent()
for n in range(8):
    f = att2.ts_add_field('زمینه %d' % (n + 1))
    answer(f, p1 if n % 2 else p3)
    att2.ts_finish_field(f)
check('ninth field refused', raises(lambda: att2.ts_add_field('زمینه ۹')))

failed = [n for n, ok in results if not ok]
env.cr.rollback()
print('SUMMARY %d/%d passed' % (len(results) - len(failed), len(results)))
