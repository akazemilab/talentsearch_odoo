# Panel v2 S13 (result levels, group report, suppression). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
import psycopg2
from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.ts_panel.models.group_report import suppress

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, T = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.assignment', 'ts.attempt'))
Inst = env['ts.instrument']
GR = env['ts.group.report']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s13.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role, **kw):
    m = M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role, **kw})
    if role == 'counselor':
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m


def finish(att):
    att.give_consent()
    for it in att.active_items():
        att.save_answer(it.id, 1 + it.id % 5)
    att.action_submit()
    return att


def finish_matrix(att):
    att.give_consent()
    items = att.active_items()
    for n, label in enumerate(['ریاضی', 'هنر', 'ورزش']):
        f = att.ts_add_field(label)
        for i, it in enumerate(items):
            att.ts_save_cell(f, it.id, (i * (n % 3 + 1) + 2 * n + i // 5) % 5 + 1)
        att.ts_finish_field(f)
    assert att.action_submit()
    return att


def done(ws, inst, share=True):
    a = A.sudo().create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'مراجع %d' % (_n[0] + 1)})
    at = a.action_accept(puser(), share=share)
    (finish_matrix if inst.code == 'TALENT-INV-15' else finish)(at)
    return a, at


def band_all(attempts, band):
    env.flush_all()
    env.cr.execute('UPDATE ts_attempt_result SET band = %s WHERE attempt_id IN %s', [band, tuple(attempts.ids)])
    env.invalidate_all()


# ---- suppress(): the rule on its own (P18)
check('every cell at or above k is shown', suppress({'a': 5, 'b': 6, 'c': 9}, 5) == {'a': 5, 'b': 6, 'c': 9})
check('a cell below k is hidden, zero included, and so is the next-smallest', suppress({'a': 0, 'b': 5, 'c': 9}, 5) == {'a': None, 'b': None, 'c': 9})
check('two hidden cells need no extra hiding', suppress({'a': 0, 'b': 2, 'c': 9}, 5) == {'a': None, 'b': None, 'c': 9})
check('all small: all hidden', suppress({'a': 1, 'b': 2, 'c': 1}, 5) == {'a': None, 'b': None, 'c': None})
check('one hidden cell with nothing left to pair is just hidden', suppress({'a': 3}, 5) == {'a': None})

plain = Inst.search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
talent = Inst.search([('code', '=', 'TALENT-INV-15')], limit=1)
emp, edu = panel('employment', 'پنل S13 کاری'), panel('education', 'پنل S13 آموزشی')
e_owner, hr = member(emp, 'owner'), member(emp, 'hr_admin')
hm = member(emp, 'hiring_manager')
o_owner, c1 = member(edu, 'owner'), member(edu, 'counselor')

# ---- result levels on attempts (P12)
a1, at1 = done(emp, plain)
check('hr sees the summary level of a shared employment result', at1.ts_result_level(hr) == 'summary')
check('the other panel owner sees nothing of it', at1.ts_result_level(o_owner) == 'none')
a2, at2 = done(emp, plain, share=False)
check('an unshared result is status only', at2.ts_result_level(hr) == 'status')

# ---- group report threshold (P18)
rep = GR.build(hr, {})
row = next((r for r in rep['instruments'] if r['id'] == plain.id), None)
check('one shared result: the instrument row says n=1 of m=2, not ok', row and row['n'] == 1 and row['m'] == 2 and not row['ok'] and not row['factors'])
check('the threshold text is the owner-approved sentence', rep['text'] == 'برای گزارش گروهی دست‌کم ۵ نتیجهٔ به‌اشتراک‌گذاشته‌شده لازم است.')
more = [done(emp, plain) for _i in range(3)]
rep = GR.build(hr, {})
row = next(r for r in rep['instruments'] if r['id'] == plain.id)
check('four shared results: still below five', row['n'] == 4 and not row['ok'] and not row['factors'])
more.append(done(emp, plain))
band_all(T.browse([x[1].id for x in [(a1, at1)] + more]), 'mid')
rep = GR.build(hr, {})
row = next(r for r in rep['instruments'] if r['id'] == plain.id)
check('five shared results: the table appears, n=5', row['n'] == 5 and row['ok'] and row['factors'])
f0 = row['factors'][0]
check('every visible cell is at least k, the rest hidden', all(v is None or v >= rep['k'] for f in row['factors'] for v in f['cells'].values()))
check('five in one band: that band shown (5), the two empty ones hidden', f0['cells'] == {'low': None, 'mid': 5, 'high': None}, str(f0['cells']))
band_all(T.browse([x[1].id for x in more[:2]]), 'low')
rep = GR.build(hr, {})
f0 = next(r for r in rep['instruments'] if r['id'] == plain.id)['factors'][0]
check('a split 2/3/0 shows nothing: every cell is below five', set(f0['cells'].values()) == {None})

# ---- filters
check('a group filter with no such group gives no rows', not GR.build(hr, {'group_id': '999999999'})['instruments'])
check('a period of 30 days keeps today\'s results', next(r for r in GR.build(hr, {'period': '30'})['instruments'] if r['id'] == plain.id)['n'] == 5)
check('an instrument filter for another instrument gives no rows', not [r for r in GR.build(hr, {'instrument_id': str(talent.id)})['instruments'] if r['id'] == plain.id])

# ---- voided attempts are left out
at_v = more[-1][1]
at_v.sudo().write({'voided': True})
rep = GR.build(hr, {})
row = next((r for r in rep['instruments'] if r['id'] == plain.id), None)
check('a voided attempt is not counted any more', row and row['n'] == 4)
at_v.sudo().write({'voided': False})

# ---- the talent profile at education level
tb = [done(edu, talent) for _i in range(5)]
for _a, _at in tb:
    _a.client_id.sudo().responsible_id = o_owner.id        # the owner's own clients: the counselor has none of them
rep = GR.build(o_owner, {})
trow = next((r for r in rep['instruments'] if r['id'] == talent.id), None)
check('five shared talent profiles: scale means shown, 20-100', trow and trow['talent'] and trow['talent']['n'] == 5
      and all(20 <= v <= 100 for v in trow['talent']['means'].values()), str(trow and trow['talent']))
check('no field name travels in the group report', 'ریاضی' not in str(trow) and 'هنر' not in str(trow))
check('the counselor sees only their own clients: below five, no profile', not (next((r for r in GR.build(c1, {})['instruments'] if r['id'] == talent.id), {}) or {}).get('talent'))
check('a hiring manager has no group report permission', not hm.has_perm('reports:group'))
check('hr and owner do', hr.has_perm('reports:group') and e_owner.has_perm('reports:group'))

passed = sum(1 for _n_, ok in results if ok)
print('SUMMARY %d/%d passed' % (passed, len(results)))
