# Assessment engine acceptance tests. Run ONLY on an eot_ts* clone via odoo-bin shell.
# Golden parity: ORM engine vs an independent re-implementation of the source
# engine S09-V3.0 computed straight from the raw source records (psy_source.json).
import json
import random
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import file_path

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
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


# ------------------------------------------------------------------ catalog
Inst = env['ts.instrument']
pub = Inst.search([('state', '=', 'published')])
ret = Inst.search([('state', '=', 'retired')])
check('33 instruments published', len(pub) == 33, str(len(pub)))
check('3 instruments retired (009, 011, 024)', sorted(ret.mapped('code')) == ['inventory_009', 'inventory_011', 'inventory_024'])
check('every published version passed exhaustive band validation', all(i.current_version_id.validation_ok for i in pub),
      str([i.code for i in pub if not i.current_version_id.validation_ok]))
check('every published instrument approved with intended use + rights', all(i.approved_at and i.intended_use and i.rights_note for i in pub))
V = pub.mapped('current_version_id')
check('1,340 source items imported', env['ts.instrument.item'].search_count([]) == 1340)
check('393 bands imported and approved', env['ts.instrument.band'].search_count([('approved_at', '!=', False)]) == 393)
check('versions locked', all(V.mapped('locked')))
check('locked version refuses contract edits', raises(lambda: V[0].write({'reverse_rule': 'x'}), UserError))
stats = Inst._ts_load_source()
check('loader is idempotent (second run creates nothing)', stats['created'] == 0 and stats['versions'] == 0, str(stats))

# ------------------------------------------------ independent reference engine
src = json.load(open(file_path('ts_assessment/data/source/psy_source.json')))
A = {a['id']: a for a in src['x_psy_assessment']}
F = {f['id']: f for f in src['x_psy_factor']}
m2o = lambda v: v[0] if isinstance(v, list) else v
ref_items, ref_bands = {}, {}
rule_of = {m2o(r['x_factor_id']): r['id'] for r in src['x_psy_factor_scoring_rule']}
for t in src['x_psy_factor_threshold_rule']:
    ref_bands.setdefault(m2o(t['x_rule_id']), []).append((t['x_band'].lower(), t['x_min_score'], t['x_max_score']))
for it in src['x_psy_assessment_item']:
    f = F[m2o(it['x_factor_id'])]
    code = A[m2o(f['x_assessment_id'])]['x_code']
    if not it['x_disabled']:
        ref_items.setdefault(code, []).append((int(it['x_source_question_id']), f['x_code'], rule_of.get(f['id']), bool(it['x_reverse'])))


def reference(code, answers_by_qid):
    out = {}
    per = {}
    for qid, fcode, rule, rev in ref_items[code]:
        v = answers_by_qid[qid]
        per.setdefault((fcode, rule), []).append(6 - v if rev else v)
    for (fcode, rule), vals in per.items():
        s = sum(vals) / len(vals)
        hits = [b for b, lo, hi in ref_bands[rule] if lo <= s <= hi]
        assert len(hits) == 1
        out[fcode] = (round(s, 9), hits[0])
    return out


portal = env.ref('base.group_portal')
mk = lambda login: env['res.users'].with_context(no_reset_password=True).create(
    {'name': login, 'login': login + '@example.invalid', 'group_ids': [(6, 0, [portal.id])]})
u1, u2 = mk('ts_t_part1'), mk('ts_t_part2')
Attempt = env['ts.attempt']


def run(inst, user, chooser, role='self'):
    a = Attempt.create({'user_id': user.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
    a.give_consent(role='guardian' if inst.audience in ('child', 'adolescent') else role)
    by_qid = {}
    for it in a.active_items():
        v = chooser(it)
        a.save_answer(it.id, v)
        by_qid[it.source_question_id] = v
    a.action_submit()
    return a, by_qid


mismatch, cases = [], 0
for inst in pub:
    for label, chooser in [('all1', lambda it: 1), ('all3', lambda it: 3), ('all5', lambda it: 5),
                           ('rnd1', None), ('rnd2', None), ('rnd3', None)]:
        rng = random.Random('%s-%s' % (inst.code, label))
        ch = chooser or (lambda it, rng=rng: rng.randint(1, 5))
        a, by_qid = run(inst, u1, ch)
        cases += 1
        exp = reference(inst.code, by_qid)
        got = {r.factor_id.code: (round(r.score, 9), r.band) for r in a.result_ids}
        if a.state != 'done' or got != exp:
            mismatch.append((inst.code, label, a.state))
check('golden parity: ORM engine == independent source engine (%d attempts, 33 instruments x 6 answer sets)' % cases,
      not mismatch, str(mismatch[:5]))

# boundary: a factor averaging exactly 2.5 -> medium, exactly 4.0 -> high (inventory_001 factor with an even item count)
inst = pub.filtered(lambda i: i.code == 'inventory_001')
v = inst.current_version_id
f = v.factor_ids.filtered('scored')[0]
f_items = v.item_ids.filtered(lambda i: not i.disabled and i.factor_id == f)


def boundary_chooser(target):
    # scored value target per item: reverse items get 6 - target
    def ch(it):
        if it.factor_id != f:
            return 3
        return (6 - target) if it.reverse else target
    return ch


for target, band in [(4, 'high'), (3, 'medium'), (2, 'low'), (1, 'low'), (5, 'high')]:
    a, _ = run(inst, u1, boundary_chooser(target))
    r = a.result_ids.filtered(lambda r: r.factor_id == f)
    check('boundary: factor average %.1f -> %s' % (target, band), abs(r.score - target) < 1e-9 and r.band == band, '%s %s' % (r.score, r.band))
if len(f_items) % 2 == 0:
    half = len(f_items) // 2
    ordered = f_items.sorted('id')
    def ch25(it):
        if it.factor_id != f:
            return 3
        target = 2 if it in ordered[:half] else 3
        return (6 - target) if it.reverse else target
    a, _ = run(inst, u1, ch25)
    r = a.result_ids.filtered(lambda r: r.factor_id == f)
    check('boundary: factor average exactly 2.5 -> medium', abs(r.score - 2.5) < 1e-9 and r.band == 'medium', '%s %s' % (r.score, r.band))

# ------------------------------------------------ rules
inst = pub.filtered(lambda i: i.code == 'inventory_014')
a = Attempt.create({'user_id': u1.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
item0 = a.active_items()[0]
check('no answer before consent', raises(lambda: a.save_answer(item0.id, 3), UserError))
a.give_consent()
check('value 0 refused', raises(lambda: a.save_answer(item0.id, 0), UserError))
check('value 6 refused', raises(lambda: a.save_answer(item0.id, 6), UserError))
disabled = a.version_id.item_ids.filtered('disabled')[:1]
if disabled:
    check('disabled item refused', raises(lambda: a.save_answer(disabled.id, 3), UserError))
other = pub.filtered(lambda i: i.code == 'inventory_001').current_version_id.item_ids[:1]
check('item from another instrument refused', raises(lambda: a.save_answer(other.id, 3), UserError))
for it in a.active_items()[:-1]:
    a.save_answer(it.id, 4)
check('submit with a missing answer refused, no score', raises(lambda: a.action_submit(), UserError) and not a.result_ids and a.state == 'in_progress')
a.save_answer(a.active_items()[-1].id, 2)
a.save_answer(item0.id, 5)
check('answer can change before submit (one row per item)', len(a.answer_ids) == len(a.active_items()) and a.answers_map()[item0.id] == 5)
a.action_submit()
n_res, h = len(a.result_ids), a.output_hash
a.action_submit()
check('double submit is idempotent', a.state == 'done' and len(a.result_ids) == n_res and a.output_hash == h)
check('no edits after submit', raises(lambda: a.save_answer(item0.id, 1), UserError))
check('historical re-score reproduces the same output hash', a.rescore_matches())
check('results snapshot approved client + therapist texts', all(r.client_text and r.therapist_text and r.content_version for r in a.result_ids))
check('report sections parsed into Persian headings (no English band word)',
      all(all(('Low' not in (h or '') and 'High' not in (h or '') and 'Medium' not in (h or '')) for h, b in r.client_sections()) for r in a.result_ids))
child = pub.filtered(lambda i: i.audience == 'child')[:1]
c = Attempt.create({'user_id': u1.id, 'instrument_id': child.id, 'version_id': child.current_version_id.id})
check('child instrument requires guardian respondent', raises(lambda: c.give_consent(role='self'), UserError))

# ------------------------------------------------ privacy
check('other participant cannot read my attempt', raises(lambda: a.with_user(u2).read(['name']), AccessError))
check('other participant cannot read my results', raises(lambda: a.result_ids.with_user(u2).read(['score']), AccessError))
check('participant reads own attempt', a.with_user(u1).read(['name']) and True)
check('participant cannot read instrument therapist texts directly', raises(lambda: a.result_ids[:1].band_id.with_user(u1).read(['therapist_text']), AccessError))
check('participant cannot write own results', raises(lambda: a.result_ids[:1].with_user(u1).write({'score': 5}), AccessError))
check('audit trail for consent + submit', env['ts.audit.event'].search_count([('res_model', '=', 'ts.attempt'), ('res_id', '=', a.id)]) >= 2)

env.cr.rollback()
fails = [n for n, ok in results if not ok]
print('SUMMARY %d/%d passed%s' % (len(results) - len(fails), len(results), ('; FAILED: ' + '; '.join(fails)) if fails else ''))
