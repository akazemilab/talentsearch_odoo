# Clinic phase 2 (ts_battery): batteries, starter data, panel catalog grants, server-side enforcement, audit.
# Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits (rolls back at the end).
import math
import os

import odoo.addons.ts_battery as ts_battery_pkg
from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.ts_battery.models.battery import STARTER, STARTER_LEGACY, est_minutes
from odoo.addons.ts_battery.models.catalog import BATTERY_NOT_IN_CATALOG, NOT_IN_CATALOG

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []
Command = fields.Command


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


def error_text(fn):
    try:
        with env.cr.savepoint():
            fn()
    except Exception as e:
        return str(e.args[0]) if e.args else str(e)
    return ''


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, B, Inst = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment'], env['ts.battery'], env['ts.instrument']
Audit = env['ts.audit.event']
_n = [0]


def puser(tag='u'):
    _n[0] += 1
    login = 'ts.bat.%s%d@example.invalid' % (tag, _n[0])
    return U.create({'name': login, 'login': login, 'email': login, 'group_ids': [Command.set([portal.id])]})


def panel(purpose, mode='purpose'):
    org = env['res.partner'].create({'name': 'پنل آزمون باتری ' + purpose, 'is_company': True})
    org.write({'is_company': True})
    vals = {'name': org.name, 'purpose': purpose, 'partner_id': org.id, 'catalog_mode': mode}
    if purpose == 'clinical':
        vals['escalation_contact_id'] = org.id
    ws = W.create(vals)
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role):
    m = M.create({'workspace_id': ws.id, 'user_id': puser(role).id, 'role': role})
    if role in ('clinician', 'clinic_director', 'counselor'):
        m.write({'license_number': 'T-%d' % m.id, 'verification_state': 'verified'})
    return m


def ids(recs):
    return set(recs.ids)


# ---------------------------------------------------------------- starter batteries
codes = [s['code'] for s in STARTER]
starters = B.search([('code', 'in', codes)])
by_code = {b.code: b for b in starters}
check('B01 six starter batteries exist', len(starters) == 6, str(sorted(by_code)))
check('B01 all six starter batteries are published', all(b.state == 'published' for b in starters),
      str([(b.code, b.state) for b in starters if b.state != 'published']))
bad_lines = [s['code'] for s in STARTER if s['code'] in by_code and
             by_code[s['code']].line_ids.sorted('sequence').mapped('instrument_id.code') != s['instruments']]
check('B02 starter lines are the handoff instruments in order', not bad_lines, str(bad_lines))
check('B02 starter audiences (child battery = child)', by_code.get('BAT-CHILD-1') and by_code['BAT-CHILD-1'].audience == 'child'
      and all(by_code[c].audience == 'adult' for c in codes if c != 'BAT-CHILD-1' and c in by_code))
check('B02 purpose flags (no starter battery for schools)', by_code.get('BAT-CHILD-1') and not any(b.for_education for b in starters)
      and by_code['BAT-WORK-1'].for_employment and all(b.for_clinical for b in starters)
      and not by_code['BAT-INTAKE-1'].for_employment and not by_code['BAT-INTAKE-1'].for_education)
LIMIT = 'این مجموعه برای کمک به گفت‌وگوی مشاوره است، نه تشخیص.'
check('B03 descriptions end with the limit sentence and follow the voice rules',
      all((b.description or '').endswith(LIMIT) and '!' not in b.description and 'متأسفانه' not in b.description
          for b in starters))
stats = B._ts_load_starter()
check('B04 starter loader is idempotent', stats.get('created') == 0 and stats.get('existing') == 6
      and B.search_count([('code', 'in', codes)]) == 6 and stats.get('renamed') == 0, str(stats))
# Owner decision 2026-10-11: counseling wording. Battery 1 is «ارزیابی آغاز مشاوره»; no starter text speaks of therapy.
THERAPY = ('درمان', 'بالینی', 'کلینیک', 'بیمار')
check('B04b starter names/descriptions use counseling wording',
      by_code.get('BAT-INTAKE-1') and by_code['BAT-INTAKE-1'].name == 'ارزیابی آغاز مشاوره'
      and all(b.name == s['name'] for s in STARTER for b in starters if b.code == s['code'])
      and not [b.code for b in starters if any(w in (b.name or '') + (b.description or '') for w in THERAPY)],
      str([(b.code, b.name) for b in starters]))
intake, couple = by_code['BAT-INTAKE-1'], by_code['BAT-COUPLE-1']
cur = {'n': intake.name, 'd': couple.description}
intake.write({'name': STARTER_LEGACY['BAT-INTAKE-1']['name'][0]})
couple.write({'description': STARTER_LEGACY['BAT-COUPLE-1']['description'][0]})
n1 = B._ts_refresh_starter_texts()
n2 = B._ts_refresh_starter_texts()
check('B04c legacy starter texts are renamed on upgrade, once', n1 == 2 and n2 == 0 and intake.name == cur['n']
      and couple.description == cur['d'], str((n1, n2, intake.name)))
intake.write({'name': 'نام دستی مالک'})
check('B04c a hand-edited starter name is never overwritten', B._ts_refresh_starter_texts() == 0 and intake.name == 'نام دستی مالک')
intake.write({'name': cur['n']})

# ---------------------------------------------------------------- computed counts
check('B05 est_minutes: 8 s per item rounded up to 5 minutes',
      (est_minutes(0), est_minutes(1), est_minutes(37), est_minutes(38), est_minutes(111)) == (0, 5, 5, 10, 15))
bad_counts = []
for b in starters:
    n = sum(b.line_ids.mapped('instrument_id.current_version_id.active_item_count'))
    if b.item_count != n or b.est_minutes != math.ceil(n * 8 / 60 / 5) * 5:
        bad_counts.append((b.code, b.item_count, n, b.est_minutes))
check('B05 item_count = sum of current-version active items, est_minutes from it', not bad_counts, str(bad_counts))

# ---------------------------------------------------------------- constraints
adult = Inst.search([('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '=like', 'inventory_%')])
child = Inst.search([('state', '=', 'published'), ('audience', '=', 'child')], limit=1)
unpub = Inst.search([('state', '!=', 'published'), ('audience', '=', 'adult')], limit=1)
starter_insts = starters.mapped('line_ids.instrument_id')
free = adult - starter_insts          # instruments no starter battery uses (retiring them leaves starters alone)
check('B06 fixtures: enough published adult instruments', len(adult) >= 6 and len(free) >= 2 and child, '%d/%d' % (len(adult), len(free)))
a0, a1, a2, a3 = adult[0], adult[1], adult[2], adult[3]
f0, f1 = free[0], free[1]

b = B.create({'code': 'BAT-TEST-1', 'name': 'باتری آزمون یک', 'audience': 'adult',
              'line_ids': [Command.create({'instrument_id': a0.id})]})
check('B07 a battery with one line cannot be published', raises(b.action_publish, UserError))
check('B09 an instrument of another audience is refused',
      raises(lambda: b.write({'line_ids': [Command.create({'instrument_id': child.id})]}), ValidationError))
if unpub:
    check('B10 an unpublished instrument cannot be added',
          raises(lambda: b.write({'line_ids': [Command.create({'instrument_id': unpub.id})]}), ValidationError))
check('B11 a battery with no purpose cannot be published',
      raises(lambda: (b.write({'for_clinical': False, 'line_ids': [Command.create({'instrument_id': a1.id})]}),
                      b.action_publish()), UserError))
b.write({'line_ids': [Command.create({'instrument_id': a1.id})]})
# a duplicate INSERT would hit the SQL unique constraint first (and log a database error line); a write is checked
# by the Python constraint before the flush
check('B08 the same instrument twice is refused',
      raises(lambda: b.line_ids.filtered(lambda l: l.instrument_id == a1).write({'instrument_id': a0.id}), ValidationError))
b.action_publish()
check('B12 two published lines of one audience publish', b.state == 'published')
check('B12 publishing writes an audit event', Audit.search_count([('event_type', '=', 'battery.publish'),
                                                                   ('res_model', '=', 'ts.battery'), ('res_id', '=', b.id)]) == 1)
check('B13 audience of a published battery cannot change', raises(lambda: b.write({'audience': 'child'}), ValidationError))
check('B14 a published battery cannot drop below two lines', raises(lambda: b.line_ids[:1].unlink(), ValidationError))
# (no duplicate insert here: a unique violation logs a database error line the rehearsal greps for)
env.cr.execute("""SELECT conrelid::regclass::text FROM pg_constraint
                   WHERE contype = 'u' AND conrelid IN ('ts_battery'::regclass, 'ts_battery_line'::regclass)""")
check('B15 unique constraints exist for battery code and (battery, instrument)',
      {r[0] for r in env.cr.fetchall()} == {'ts_battery', 'ts_battery_line'})
emp_bad = B.create({'code': 'BAT-TEST-EMP', 'name': 'استخدامی نادرست', 'audience': 'adult', 'for_employment': True,
                    'line_ids': [Command.create({'instrument_id': i.id})
                                 for i in (adult.filtered(lambda x: x.purpose != 'employment')[:1] | adult.filtered(lambda x: x.purpose == 'employment')[:1])]})
check('B16 an employment battery needs employment instruments', raises(emp_bad.action_publish, UserError))

b2 = B.create({'code': 'BAT-TEST-2', 'name': 'باتری آزمون دو', 'audience': 'adult',
               'line_ids': [Command.create({'sequence': 1, 'instrument_id': f0.id}),
                            Command.create({'sequence': 2, 'instrument_id': f1.id})]})
check('B17 item_count / est_minutes on a new battery',
      b2.item_count == f0.active_item_count + f1.active_item_count and b2.est_minutes == est_minutes(b2.item_count))
f1.write({'state': 'retired'})
check('B18 retiring an instrument flags the battery (has_retired), state unchanged', b2.has_retired and b2.state == 'draft')
msg = error_text(b2.action_publish)
check('B19 a retired instrument blocks publishing, with a Persian reason', 'بازنشسته' in msg, msg[:80])
f1.write({'state': 'published'})
check('B19 re-publishing the instrument clears the flag', not b2.has_retired)

# ---------------------------------------------------------------- allowed_instruments
ws_p = panel('clinical')
cl_p = member(ws_p, 'clinician')
base_clin = Inst.search([('state', '=', 'published')])
if 'invite_only' in Inst._fields:
    base_clin = base_clin.filtered(lambda i: not i.invite_only)   # HR instruments (ts_tasks/ts_hire) belong to employment panels only
check('C01 purpose mode keeps the ts_org rule (clinical: every published instrument)', ids(cl_p.allowed_instruments()) == ids(base_clin))
ws_e = panel('employment')
hr_e = member(ws_e, 'hr_admin')
check('C01 purpose mode keeps the ts_org rule (employment)',
      ids(hr_e.allowed_instruments()) == ids(Inst.search([('state', '=', 'published'), ('purpose', '=', 'employment')])))
ws_d = panel('education')
co_d = member(ws_d, 'counselor')
check('C01 purpose mode keeps the ts_org rule (education)',
      ids(co_d.allowed_instruments()) == ids(Inst.search([('state', '=', 'published'), ('code', '=', 'TALENT-INV-15')])))

ws_g = panel('clinical', mode='granted')
owner_g = member(ws_g, 'owner')
cl_g = member(ws_g, 'clinician')
cat = a0 | a1 | child | (unpub or Inst.browse())
ws_g.write({'catalog_instrument_ids': [Command.set(cat.ids)],
            'catalog_battery_ids': [Command.set([by_code['BAT-INTAKE-1'].id, b2.id])]})
check('C02 granted mode: published instruments of the allow-list only', ids(cl_g.allowed_instruments()) == ids(a0 | a1 | child))
cl_g.write({'restrict_instrument_ids': [Command.set([a0.id, a2.id])]})
check('C03 a member restriction intersects the catalog', ids(cl_g.allowed_instruments()) == {a0.id})
check('C03 other members keep the whole catalog', ids(owner_g.allowed_instruments()) == ids(a0 | a1 | child))
cl_p.write({'restrict_instrument_ids': [Command.set([a2.id])]})
check('C04 a member restriction also narrows purpose mode', ids(cl_p.allowed_instruments()) == {a2.id})
check('C05 a portal member can compute its own list (no ACL error)',
      ids(cl_g.with_user(cl_g.user_id).allowed_instruments()) == {a0.id}
      and ids(cl_g.with_user(cl_g.user_id).allowed_batteries()) == {by_code['BAT-INTAKE-1'].id})

# ---------------------------------------------------------------- allowed_batteries
pub_for = lambda flag: ids(B.search([('state', '=', 'published'), (flag, '=', True), ('has_retired', '=', False)]))
check('D01 purpose mode, clinical: every published battery flagged clinical', ids(member(ws_p, 'clinic_director').allowed_batteries()) == pub_for('for_clinical')
      and ids(starters) <= pub_for('for_clinical'))
check('D02 purpose mode, education: only batteries flagged education',
      not (ids(starters) & ids(co_d.allowed_batteries())) and ids(co_d.allowed_batteries()) == pub_for('for_education'))
check('D03 purpose mode, employment: only batteries flagged employment',
      ids(hr_e.allowed_batteries()) == pub_for('for_employment') and by_code['BAT-WORK-1'].id in ids(hr_e.allowed_batteries())
      and by_code['BAT-INTAKE-1'].id not in ids(hr_e.allowed_batteries()))
ws_b = panel('benefits')
check('D04 benefits panels have no batteries', not member(ws_b, 'owner').allowed_batteries())
check('D05 granted mode: published allow-list only (a draft battery in the list is ignored)',
      ids(owner_g.allowed_batteries()) == {by_code['BAT-INTAKE-1'].id})
cl_g.write({'restrict_battery_ids': [Command.set([by_code['BAT-LIFE-1'].id])]})
check('D06 a member restriction outside the catalog leaves nothing', not cl_g.allowed_batteries())
ws_ge = panel('employment', mode='granted')
ws_ge.write({'catalog_battery_ids': [Command.set([by_code['BAT-INTAKE-1'].id, by_code['BAT-WORK-1'].id])]})
check('D07 granted mode still requires the purpose flag', ids(member(ws_ge, 'owner').allowed_batteries()) == {by_code['BAT-WORK-1'].id})
if f0 not in b.line_ids.mapped('instrument_id'):
    b.write({'line_ids': [Command.create({'instrument_id': f0.id})]})   # b: published, clinical, adult
check('D08 a published test battery is offered in clinical purpose mode', b.id in ids(cl_p.allowed_batteries()))
f0.write({'state': 'retired'})
check('D08 a battery with a retired instrument is no longer offered', b.has_retired and b.id not in ids(cl_p.allowed_batteries()))
f0.write({'state': 'published'})

# ---------------------------------------------------------------- server-side enforcement
outside = a2 if a2 not in cat else a3
msg = error_text(lambda: A.create({'workspace_id': ws_g.id, 'instrument_id': outside.id, 'invitee_name': 'بیرون از کاتالوگ'}))
check('E01 granted mode: invitation outside the catalog refused with the spec message', msg == NOT_IN_CATALOG, msg[:80])
check('E01 the refusal is a UserError', raises(lambda: A.create({'workspace_id': ws_g.id, 'instrument_id': outside.id,
                                                                  'invitee_name': 'بیرون'}), UserError))
ok_a = A.create({'workspace_id': ws_g.id, 'instrument_id': a0.id, 'invitee_name': 'درون کاتالوگ'})
check('E02 granted mode: invitation inside the catalog works', ok_a.id and ok_a.instrument_id == a0)
p_a = A.create({'workspace_id': ws_p.id, 'instrument_id': outside.id, 'invitee_name': 'پنل هدف‌محور'})
check('E03 purpose mode: unchanged (any published instrument the purpose allows)', bool(p_a.id))
check('E04 a campaign outside the member list is refused (ts_panel check follows allowed_instruments)',
      raises(lambda: env['ts.campaign'].create({'workspace_id': ws_g.id, 'name': 'دعوت گروهی آزمون', 'instrument_id': outside.id,
                                                'created_by_id': owner_g.id}), ValidationError))
check('E04 a campaign inside the catalog is accepted',
      not raises(lambda: env['ts.campaign'].create({'workspace_id': ws_g.id, 'name': 'دعوت گروهی آزمون', 'instrument_id': a1.id,
                                                    'created_by_id': owner_g.id}), Exception))

# ---------------------------------------------------------------- audit and access
def cat_events(rec):
    return Audit.search([('event_type', '=', 'catalog.change'), ('res_model', '=', rec._name), ('res_id', '=', rec.id)])


n0 = len(cat_events(ws_g))
ws_g.write({'catalog_battery_ids': [Command.link(by_code['BAT-LIFE-1'].id)]})
ev = cat_events(ws_g)
check('F01 a catalog change writes one catalog.change event', len(ev) == n0 + 1 and ev[0].workspace_id == ws_g, '%d -> %d' % (n0, len(ev)))
check('F01 the event carries counts, not names', '"batteries": 3' in (ev[0].detail or '') and 'BAT-' not in (ev[0].detail or '')
      and 'ارزیابی' not in (ev[0].detail or ''), (ev[0].detail or '')[:120])
n1 = len(cat_events(ws_g))
ws_g.write({'approval_note': 'بدون تغییر کاتالوگ'})
check('F02 an unrelated workspace edit writes no catalog event', len(cat_events(ws_g)) == n1)
check('F03 a member restriction change writes catalog.change on the member',
      len(cat_events(cl_g)) == 2 and cat_events(cl_g)[0].workspace_id == ws_g)
check('F04 creating a granted panel logs its catalog', len(cat_events(ws_ge)) >= 1)
pu = cl_g.user_id
check('F05 portal users have no ACL on batteries', not B.with_user(pu).has_access('read')
      and not env['ts.battery.line'].with_user(pu).has_access('read'))

# ================================================================ clinic phase 3: battery run
# A small published clinical battery of the three published adult instruments with the fewest items (fast to answer).
small = Inst.search([('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '=like', 'inventory_%')]) \
    .sorted(lambda i: (i.active_item_count, i.id))[:3]
run_b = B.create({'code': 'BAT-TEST-RUN', 'name': 'آزمون اجرا', 'audience': 'adult', 'for_clinical': True,
                  'line_ids': [Command.create({'sequence': 10 * (n + 1), 'instrument_id': i.id}) for n, i in enumerate(small)]})
run_b.action_publish()
N = len(run_b.line_ids)
ws_r = panel('clinical', mode='granted')
own_r = member(ws_r, 'owner')
dir_r = member(ws_r, 'clinic_director')
cl_r = member(ws_r, 'clinician')
cl_r2 = member(ws_r, 'clinician')
ws_r.write({'catalog_battery_ids': [Command.set([run_b.id, by_code['BAT-INTAKE-1'].id])]})
check('G00 fixtures: a published 3-instrument battery inside a granted clinical panel',
      N == 3 and run_b.state == 'published' and run_b in cl_r.allowed_batteries(), str(N))


def invite_battery(by_member, battery, name='مراجع مجموعه'):
    return A.create({'workspace_id': ws_r.id, 'battery_id': battery.id, 'invitee_name': name,
                     'invited_by_id': by_member.user_id.id})


def finish(at):
    for it in at.active_items():
        at.save_answer(it.id, 1 + it.id % 5)
    return at.action_submit()


ab = invite_battery(cl_r, run_b)
first_inst = run_b.line_ids.sorted('sequence')[0].instrument_id
check('G01 a battery invitation carries the battery and the first line\'s instrument',
      ab.battery_id == run_b and ab.instrument_id == first_inst and ab.state == 'invited')
check('G01 the battery instruments need not be in the panel instrument list (granted mode)',
      not (run_b.line_ids.mapped('instrument_id') & ws_r.catalog_instrument_ids))
msg = error_text(lambda: invite_battery(own_r, by_code['BAT-LIFE-1']))
check('G02 a battery outside the panel catalog is refused with the spec message', msg == BATTERY_NOT_IN_CATALOG, msg[:80])
pu_r = puser('bat')
first = ab.action_accept(pu_r, share=True)
ab.invalidate_recordset()
rows = ab.ts_battery_attempts()
check('G03 accept creates one attempt per line, in sequence order, all in consent',
      len(rows) == N and rows.mapped('instrument_id') == run_b.line_ids.sorted('sequence').mapped('instrument_id')
      and set(rows.mapped('state')) == {'consent'} and rows.mapped('battery_seq') == list(range(1, N + 1)),
      str([(r.battery_seq, r.instrument_id.code, r.state) for r in rows]))
check('G03 every attempt carries assignment_id, workspace, client and the participant; attempt_id is the first',
      all(r.assignment_id == ab and r.workspace_id == ws_r and r.client_id == ab.client_id and r.user_id == pu_r for r in rows)
      and ab.attempt_id == first == rows[0] and bool(ab.client_id))
check('G03 accepting again changes nothing', ab.action_accept(pu_r, share=True) == first and len(ab.attempt_ids) == N)
check('G03 state after accept is «accepted»', ab.state == 'accepted', ab.state)
check('G04 consent info only on the first attempt (siblings never show their own consent page)',
      first.ts_battery_info() and first.ts_battery_info()['count'] == N and not rows[1].ts_battery_info())
first.give_consent(research=True, role='self')
rows.invalidate_recordset()
from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION
check('G05 consent given once is copied to every sibling with the same values',
      set(rows.mapped('state')) == {'in_progress'} and all(r.consent_service and r.consent_research and r.consent_version == CONSENT_VERSION
                                                        and r.respondent_role == 'self' for r in rows),
      str(rows.mapped('state')))
check('G05 CONSENT_VERSION is v3', CONSENT_VERSION.endswith('-v3') and CONSENT_VERSION.startswith('TS-CONSENT-'))
Rec = env['ts.consent.record']
check('G05 the consent ledger keeps one service row per attempt',
      Rec.search_count([('attempt_id', 'in', rows.ids), ('kind', '=', 'service')]) == N)
Rec._log('assent', pu_r, attempt=first, workspace=ws_r, version='TEST', client=first.client_id)
check('G05 an assent row on the first attempt is copied to the siblings',
      Rec.search_count([('attempt_id', 'in', rows.ids), ('kind', '=', 'assent')]) == N)
check('G06 state after consent is «in_progress»', ab.state == 'in_progress', ab.state)
check('G06 player helpers: label, order, earlier open instrument',
      rows[1].ts_battery_label() == 'مجموعهٔ %s · سنجهٔ ۲ از ۳' % run_b.name and rows[1].ts_battery_earlier_open() == first
      and first.ts_battery_next() == first and not first.ts_battery_earlier_open(), rows[1].ts_battery_label())
finish(first)
ab.invalidate_recordset()
check('G07 after the first instrument the battery is still in progress; next = the second',
      first.state == 'done' and ab.state == 'in_progress' and first.ts_battery_next() == rows[1], ab.state)
check('G07 result level: the whole battery at the clinician\'s level, an unfinished instrument only «status»',
      ab.result_level(cl_r) == 'clinical' and first.ts_result_level(cl_r) == 'clinical' and rows[1].ts_result_level(cl_r) == 'status',
      '%s %s %s' % (ab.result_level(cl_r), first.ts_result_level(cl_r), rows[1].ts_result_level(cl_r)))
check('G07 another clinician of the panel (not responsible) sees nothing',
      ab.result_level(cl_r2) == 'none' and rows[1].ts_result_level(cl_r2) == 'none')
check('G07 the participant\'s report lookup finds the invitation from any attempt',
      rows[2].ts_org_assignment() == ab and rows[2].ts_shares() == ab)
N0 = env['ts.notification'].search_count([('user_id', '=', pu_r.id), ('type', '=', 'result_ready_participant')])
for r in rows[1:]:
    finish(r)
ab.invalidate_recordset()
check('G08 the battery is done when every instrument is done', ab.state == 'done' and set(rows.mapped('state')) == {'done'}, ab.state)
notes = env['ts.notification'].search([('user_id', '=', pu_r.id), ('type', '=', 'result_ready_participant')])
check('G08 the participant is told once, with the battery page', len(notes) - N0 == 1 and (notes[:1].url or '').endswith('/my/assessments/battery/%s' % ab.id),
      str([(n.url) for n in notes]))
check('G08 every instrument is visible at the clinician\'s level once done', all(r.ts_result_level(cl_r) == 'clinical' for r in rows))
_sms_b = ab._ts_invite_sms_body()
# clinic phase 5 (docs/clinic/05_sms_texts.md): no assessment or battery name in an SMS (lock-screen privacy); a short link
check('G08 the SMS invitation names neither the battery nor its assessments and carries the short link',
      run_b.name not in _sms_b and first_inst.name not in _sms_b and '/i/' in _sms_b, _sms_b[:120])

# expiry: an accepted battery never expires mid-way; an unaccepted one does
ab2 = invite_battery(dir_r, run_b, 'مراجع دوم')
ab2.action_accept(puser('bat'), share=True)
ab3 = invite_battery(dir_r, run_b, 'مراجع سوم')
past = fields.Datetime.subtract(fields.Datetime.now(), days=1)
(ab2 | ab3).write({'expires_at': past})
A._cron_expire_invitations()
check('G09 the expiry cron leaves an accepted battery alone and expires an unaccepted one', not ab2.expired and ab3.expired
      and ab3.invite_state() == 'expired', '%s %s' % (ab2.expired, ab3.expired))
ab4 = invite_battery(dir_r, run_b, 'مراجع چهارم')
ab4.action_withdraw()
check('G09 a battery invitation can be withdrawn like a single one', ab4.state == 'withdrawn')

# the panel decides each member's catalog (catalog:assign)
check('G10 catalog:assign: owner, admin, clinic_director, hr_admin; not clinician',
      own_r.has_perm('catalog:assign') and dir_r.has_perm('catalog:assign') and not cl_r.has_perm('catalog:assign'))
check('G10 a clinician cannot set a colleague\'s catalog', raises(lambda: cl_r2.ts_set_catalog(cl_r, True, [], [run_b.id]), UserError))
check('G10 an item outside the panel catalog is refused',
      raises(lambda: cl_r2.ts_set_catalog(own_r, True, [], [by_code['BAT-LIFE-1'].id]), UserError))
check('G10 an empty checklist is refused', raises(lambda: cl_r2.ts_set_catalog(own_r, True, [], []), UserError))
n_ev = len(cat_events(cl_r2))
cl_r2.ts_set_catalog(dir_r, True, [], [by_code['BAT-INTAKE-1'].id])
check('G11 batteries only: the member keeps that battery and no single instrument',
      ids(cl_r2.allowed_batteries()) == {by_code['BAT-INTAKE-1'].id} and not cl_r2.allowed_instruments())
ev = cat_events(cl_r2)
check('G11 the change is audited once as catalog.change, by the deciding member, counts only',
      len(ev) == n_ev + 1 and ev[0].member_id == dir_r and '"restricted": true' in (ev[0].detail or '') and 'BAT-' not in (ev[0].detail or ''),
      (ev[0].detail or '')[:120] if ev else '')
msg = error_text(lambda: invite_battery(cl_r2, run_b))
check('G11 the server refuses a battery outside the member\'s list', msg == BATTERY_NOT_IN_CATALOG, msg[:80])
check('G11 setting the same list again changes nothing', cl_r2.ts_set_catalog(own_r, True, [], [by_code['BAT-INTAKE-1'].id]) is False)
cl_r2.ts_set_catalog(own_r, False)
check('G12 «همهٔ موارد پنل» clears the restriction', not cl_r2.catalog_restricted and run_b in cl_r2.allowed_batteries()
      and not cl_r2.restrict_battery_ids)

# group invitations of a battery
Cl = env['ts.panel.client']
clients = Cl.create([{'workspace_id': ws_r.id, 'name': 'گروهی %d' % k} for k in range(2)])
camp = env['ts.campaign'].create({'workspace_id': ws_r.id, 'name': 'دعوت گروهی مجموعه', 'battery_id': run_b.id, 'kind': 'list',
                                  'created_by_id': dir_r.id})
made, _sk = camp.ts_launch(clients)
check('G13 a list campaign of a battery creates battery invitations',
      len(made) == 2 and set(made.mapped('battery_id').ids) == {run_b.id} and camp.instrument_id == first_inst)
camp_o = env['ts.campaign'].create({'workspace_id': ws_r.id, 'name': 'پیوند باز مجموعه', 'battery_id': run_b.id, 'kind': 'open_link',
                                    'created_by_id': dir_r.id, 'open_max': 5})
joined = camp_o.ts_join(puser('bat'), 'پیوسته')
check('G13 an open-link campaign of a battery gives battery invitations', joined.battery_id == run_b)
cl_r.ts_set_catalog(own_r, True, [], [by_code['BAT-INTAKE-1'].id])
check('G13 a campaign of a battery outside the creator\'s list is refused',
      raises(lambda: env['ts.campaign'].create({'workspace_id': ws_r.id, 'name': 'بیرون از فهرست', 'battery_id': run_b.id,
                                                'kind': 'list', 'created_by_id': cl_r.id}), ValidationError))

# single invitations unchanged
single = A.create({'workspace_id': ws_p.id, 'instrument_id': a0.id, 'invitee_name': 'تکی'})
s_at = single.action_accept(puser('single'), share=True)
check('G14 a single invitation: one attempt, attempt_ids == attempt_id, no battery label',
      not single.battery_id and single.attempt_ids == s_at and not s_at.ts_battery_label() and not s_at.ts_battery_info())

# the Sepehr seed (owner decision 2026-10-11): by default no colleague invitations
os.environ.pop('TS_SEPEHR_INVITES', None)
seed_path = os.path.join(os.path.dirname(os.path.dirname(ts_battery_pkg.__path__[0])), 'tools', 'prod', 'clinic_seed_sepehr.py')
I = env['ts.member.invite']
inv0 = I.search_count([])
g = {'env': env, 'TS_SEED_NO_FINISH': True, '__name__': 'ts_seed_test'}
try:
    with env.cr.savepoint():
        exec(compile(open(seed_path, encoding='utf-8').read(), seed_path, 'exec'), g)
        res = g.get('SEPEHR_RESULT') or {}
        seed_ws = res.get('workspace')
        check('G15 the seed by default creates the panel and the owner, and NO colleague invitation',
              seed_ws and res.get('owner') and res['created'].get('invites') == 0 and not res.get('invites_on')
              and I.search_count([]) == inv0 and seed_ws.catalog_mode == 'granted' and not seed_ws.gated,
              str(res.get('created')))
except Exception as e:
    check('G15 the seed by default creates the panel and the owner, and NO colleague invitation', False, repr(e)[:200])

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
