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
check('matrix version 2/4/8 fields', v.mode == 'matrix' and (v.field_min, v.field_default, v.field_max) == (2, 4, 8))
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
check('progress computed (3 of 4 suggested fields answered)', att.progress >= 75, str(att.progress))
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

# entekhab-1405: fields side by side
gap = prof['interpretation'].get('gap', 10)
cr = R.compare_rows(prof, gap)
check('compare: 6 rows over every field', [r['code'] for r in cr] == ['ANA', 'EXP', 'ACA', 'NOV', 'DUT', 'TOT']
      and all(len(r['cells']) == len(prof['fields']) for r in cr))
check('compare: exactly the top value(s) are best; near within gap', all(
    (c['mark'] == 'best') == (abs(c['score'] - max(x['score'] for x in r['cells'])) < 1e-9)
    and (c['mark'] != 'near' or max(x['score'] for x in r['cells']) - c['score'] <= gap)
    for r in cr for c in r['cells']))
check('compare: bar percent maps 20..100 to 0..100', all(abs(c['pct'] - (c['score'] - 20) / 80.0 * 100) < 0.06 for r in cr for c in r['cells']))
fake = {'fields': [{'label': 'الف', 'scales': dict(ANA=80, EXP=80, ACA=60, NOV=40, DUT=20), 'composites': {'TOT': 56.0}, 'flags': {}},
                   {'label': 'ب', 'scales': dict(ANA=72, EXP=80, ACA=59, NOV=40, DUT=20), 'composites': {'TOT': 54.2}, 'flags': {}}]}
fr = {r['code']: r for r in R.compare_rows(fake, 10)}
check('compare: exact tie -> both best', [c['mark'] for c in fr['EXP']['cells']] == ['best', 'best'])
check('compare: 8 below top is near, 1 below is near', fr['ANA']['cells'][1]['mark'] == 'near' and fr['ACA']['cells'][1]['mark'] == 'near')
check('compare: cards list every field with high/low', len(R.field_cards(prof, gap)) == len(prof['fields']))
check('compare: two neutral lines, no "best major" wording', len(R.compare_lines(prof['interpretation'])) == 2
      and not any('بهترین رشته' in x for x in R.compare_lines(prof['interpretation'])))

# imported (historical) participant: contact only, no user
partner = env['res.partner'].create({'name': 'شرکت‌کنندهٔ آزمون ورود'})
imp = env['ts.attempt'].create({'person_id': partner.id, 'instrument_id': inst.id, 'version_id': v.id,
                                'source': 'import', 'source_ref': 'test:import:1', 'state': 'done', 'released': False})
check('imported attempt has no user and is not released', not imp.user_id and imp.person_id == partner and not imp.released)
check('source_ref is unique', raises(lambda: env['ts.attempt'].create({
    'person_id': partner.id, 'instrument_id': inst.id, 'version_id': v.id, 'source': 'import', 'source_ref': 'test:import:1'}),
    exc=Exception))


# entekhab-1405: institute (education) view of imported results, answers never included
org_p = env['res.partner'].create({'name': 'مؤسسهٔ آزمون', 'is_company': True})
w_edu = env['ts.workspace'].create({'name': 'مؤسسهٔ آزمون', 'purpose': 'education', 'partner_id': org_p.id})
check('education workspace is gated until approved', w_edu.gated and raises(lambda: w_edu.write({'state': 'pilot'})))
check('approval is manager-only', raises(lambda: w_edu.with_user(user).action_approve(), exc=Exception))
w_edu.action_approve()
check('approval recorded and gate lifted', not w_edu.gated and w_edu.approved_by_id and w_edu.approved_on
      and env['ts.audit.event'].search_count([('res_model', '=', 'ts.workspace'), ('res_id', '=', w_edu.id), ('event_type', '=', 'workspace.approve')]) == 1)
w_edu.state = 'pilot'
c_user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'مشاور آزمون', 'login': 'ts.talent.counselor@example.invalid', 'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
m_c = env['ts.workspace.member'].create({'workspace_id': w_edu.id, 'user_id': c_user.id, 'role': 'counselor'})
imp.write({'workspace_id': w_edu.id})
check('counselor can act and sees the imported result', m_c.can_act() and imp.ts_org_visible_to(m_c))
imp2 = env['ts.attempt'].create({'person_id': partner.id, 'instrument_id': inst.id, 'version_id': v.id, 'source': 'import',
                                 'source_ref': 'test:import:2', 'state': 'done', 'released': False})
check('an import of another workspace stays invisible', not imp2.ts_org_visible_to(m_c))
check('a web attempt without a shared assignment is invisible', not att.ts_org_visible_to(m_c))
m_c.active = False
check('inactive member sees nothing', not imp.ts_org_visible_to(m_c))
m_c.active = True
w_edu.state = 'suspended'
check('suspended workspace hides imports', not imp.ts_org_visible_to(m_c))

# field cap
att2 = env['ts.attempt'].create({'user_id': user.id, 'instrument_id': inst.id, 'version_id': v.id})
att2.give_consent()
for n in range(8):
    f = att2.ts_add_field('زمینه %d' % (n + 1))
    answer(f, p1 if n % 2 else p3)
    att2.ts_finish_field(f)
check('ninth field refused', raises(lambda: att2.ts_add_field('زمینه ۹')))


# ---- import helpers (pure)
from datetime import date
from odoo.addons.ts_assessment.models.attempt import g2j
from odoo.addons.ts_talent.models import importer as IM

bad = 0
d = date(1991, 3, 1)
while d < date(2031, 3, 1):
    jy, jm, jd = g2j(d.year, d.month, d.day)
    if IM.j2g(jy, jm, jd) != (d.year, d.month, d.day):
        bad += 1
    d = date.fromordinal(d.toordinal() + 1)
check('Jalali -> Gregorian round-trips for 40 years of days', bad == 0, str(bad))
check('stamp 1403/05/17 14:32 Tehran -> 11:02 UTC', str(IM.parse_stamp('1403/05/17 14:32')) == '2024-08-07 11:02:00')
check('Persian digits in a stamp', str(IM.parse_stamp('۱۴۰۳/۰۵/۱۷ ۱۴:۳۲')) == '2024-08-07 11:02:00')
check('phone forms all normalize alike', {IM.norm_phone(x) for x in ('09121234567', '9121234567', '+98 912 123 4567', '۰۹۱۲۱۲۳۴۵۶۷', '00989121234567')} == {'+989121234567'})
check('bad phone / e-mail rejected', IM.norm_phone('12345') is None and IM.norm_email('abc') is None and IM.norm_email(' A@B.co ') == 'a@b.co')

failed = [n for n, ok in results if not ok]
env.cr.rollback()
print('SUMMARY %d/%d passed' % (len(results) - len(failed), len(results)))
