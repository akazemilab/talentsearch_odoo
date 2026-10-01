# Panel v2 S12 (dashboard definitions). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
from datetime import timedelta

from odoo import fields

from odoo.addons.ts_panel.controllers.clients import visible_domain
from odoo.addons.ts_panel.controllers.invites import assignment_domain
from odoo.addons.ts_panel.models import dashboard as dash

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, C, A = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.panel.client', 'ts.assignment'))
Inst = env['ts.instrument']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s12.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose, name, approved=True):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00' if approved else False})
    ws.state = 'pilot'
    return ws


def member(ws, role, **kw):
    m = M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role, **kw})
    if role == 'counselor':
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m


def line(m, key):
    return next((a for a in m.dash_attention() if a['key'] == key), None)


def tile(m, key, days=30):
    return next((t for t in m.dash_tiles(days) if t['key'] == key), None)


def sql(q, *p):
    env.flush_all()
    env.cr.execute(q, p)
    env.invalidate_all()


talent = Inst.search([('code', '=', 'TALENT-INV-15')], limit=1)
edu = panel('education', 'پنل S12 آموزشی')
owner, c1, c2 = member(edu, 'owner'), member(edu, 'counselor'), member(edu, 'counselor')
now = fields.Datetime.now()

# ---- period helpers
check('a period starts at Tehran midnight, `days - 1` days back', dash.period_start(1) <= now and dash.period_start(7) < dash.period_start(1)
      and (dash.period_start(1) - dash.period_start(2)) == timedelta(days=1))
check('only 7, 30 and 90 are accepted as periods', dash.clean_filters({'period': '5', 'kind': 'sent'}) == {'kind': 'sent'}
      and dash.clean_filters({'period': '90', 'kind': 'x', 'overdue': '1', 'evil': '1'}) == {'period': '90', 'overdue': '1'})

# ---- unassigned and handover (clients)
k1 = C.create({'workspace_id': edu.id, 'name': 'بدون مسئول یک'})
k2 = C.create({'workspace_id': edu.id, 'name': 'بدون مسئول دو'})
k3 = C.create({'workspace_id': edu.id, 'name': 'مراجع کارشناس یک', 'responsible_id': c1.id})
k4 = C.create({'workspace_id': edu.id, 'name': 'مراجع کارشناس دو', 'responsible_id': c2.id})
ln = line(owner, 'unassigned')
check('unassigned: the owner is told how many, with the filtered list', ln and ln['n'] == 2 and ln['url'].endswith('/clients?filter=unassigned'))
dom = visible_domain(owner) + [('state', '=', 'active'), ('responsible_id', '=', False)]
check('...and the number equals what the list filter finds', C.search_count(dom) == ln['n'])
check('a counselor without the right is not told about the unassigned queue', line(c1, 'unassigned') is None or c1.has_perm('clients:read_unassigned'))
k3.write({'handover_to_id': c2.id, 'handover_by_id': c1.id, 'handover_on': now})
check('handover requests appear for those who can assign', line(owner, 'handover') and line(owner, 'handover')['n'] == 1 and line(c1, 'handover') is None)

# ---- overdue / expiring / unseen
atts = {}


def inv(client, **kw):
    a = A.create({'workspace_id': edu.id, 'instrument_id': talent.id, 'client_id': client.id, 'invitee_name': client.name})
    return a


a_over = inv(k3)
a_ok = inv(k4)
a_today = inv(k1)
a_far = inv(k2)
today = dash.today_tehran()
sql("UPDATE ts_assignment SET deadline = %s WHERE id = %s", today - timedelta(days=2), a_over.id)
sql("UPDATE ts_assignment SET deadline = %s WHERE id = %s", today, a_today.id)
sql("UPDATE ts_assignment SET deadline = %s, expires_at = now() at time zone 'utc' + interval '2 days' WHERE id = %s", today + timedelta(days=9), a_ok.id)
sql("UPDATE ts_assignment SET expires_at = now() at time zone 'utc' + interval '20 days' WHERE id = %s", a_far.id)
dom = assignment_domain(owner)
check('overdue: the deadline is before today, the state is open', A.search(dom + dash.overdue_domain()) == a_over)
check('...the owner dashboard line and its list agree', line(owner, 'overdue')['n'] == A.search_count(dom + dash.overdue_domain()) == 1)
check('a counselor sees overdue only for their own clients', line(c1, 'overdue')['n'] == 1 and line(c2, 'overdue') is None)
check('expiring: within 3 days, open', A.search(dom + dash.expiring_domain()) == a_ok and line(owner, 'expiring')['n'] == 1)
sql("UPDATE ts_assignment SET expires_at = now() at time zone 'utc' - interval '1 hour' WHERE id = %s", a_ok.id)
check('...an invitation already past its expiry is not "expiring"', not A.search_count(dom + dash.expiring_domain()))

# a finished, shared result nobody has opened
b = inv(k4)
at = b.action_accept(puser(), share=True)
at.write({'state': 'done', 'released': True, 'started_at': now - timedelta(minutes=20), 'submitted_at': now})
check('unseen: a finished shared result nobody opened is listed', b.id in dash.unseen_ids(env, owner, assignment_domain(owner)) and line(owner, 'unseen')['n'] >= 1)
env['ts.audit.event'].sudo().with_user(owner.user_id).log('assignment.result_view', b, workspace=edu, level='education')
check('...and leaves the list once this member has opened it', b.id not in dash.unseen_ids(env, owner, assignment_domain(owner)))
check('...but stays for another member who has not', b.id in dash.unseen_ids(env, c2, assignment_domain(c2)))

# ---- KPI tiles
t_sent = tile(owner, 'sent')
check('sent counts the invitations created in the period', t_sent['n'] == A.search_count(assignment_domain(owner) + dash.kind_domain('sent', 30)) >= 5)
check('...and the tile links to the list with the same filter', t_sent['url'].endswith('/invites?kind=sent&period=30'))
base30 = A.search_count(assignment_domain(owner) + dash.kind_domain('sent', 30))
sql("UPDATE ts_assignment SET create_date = now() at time zone 'utc' - interval '40 days' WHERE id = %s", a_far.id)
a_far_in_90 = A.search_count(assignment_domain(owner) + dash.kind_domain('sent', 90))
check('the 90-day count includes it, the 30-day count does not', a_far_in_90 == base30 and A.search_count(assignment_domain(owner) + dash.kind_domain('sent', 30)) == base30 - 1)
check('done counts finished attempts submitted in the period', tile(owner, 'done')['n'] == 1)
check('the median completion time is hidden below 5 finished', tile(owner, 'median') is None)
check('noshare counts finished attempts whose result is not shared', tile(owner, 'noshare')['n'] == 0)
for i in range(5):
    x = inv(C.create({'workspace_id': edu.id, 'name': 'تکمیل %d' % i}))
    xt = x.action_accept(puser(), share=False)
    xt.write({'state': 'done', 'released': True, 'started_at': now - timedelta(minutes=10 + i), 'submitted_at': now})
check('with five finished the median appears (minutes)', tile(owner, 'median') and tile(owner, 'median')['n'] == 12, str(tile(owner, 'median')))
check('...and the unshared ones are counted', tile(owner, 'noshare')['n'] == 5)
rate = tile(owner, 'rate')
check('the completion rate shows x of y once y reaches 5', rate and rate['text'][1] >= 5 and rate['text'][0] == 6, str(rate))
check('the median and the unshared tile are for owner and managers only', tile(c1, 'median') is None and tile(c1, 'noshare') is None)
check('a counselor\'s tiles count only their own clients', tile(c1, 'sent')['n'] < tile(owner, 'sent')['n'])
check('the specialist tile counts open clients of the member', tile(c1, 'mine_open') is not None)
check('the usage tile needs credits:read and says free', tile(owner, 'usage') and tile(owner, 'usage')['text'] == 'رایگان در این فصل' and tile(c1, 'usage') is None)

# ---- funnel and filters
fun = owner.dash_funnel(30)
check('the funnel lists invited, opened, accepted, in progress, done for the period', [f[0] for f in fun] == ['invited', 'opened', 'accepted', 'in_progress', 'done'])
check('...and each count equals its list filter', all(f[2] == A.search_count(assignment_domain(owner) + dash.kind_domain('created', 30) + [('state', '=', f[0])]) for f in fun))
check('invite_filters builds the same domain the tile uses', dash.invite_filters(env, owner, assignment_domain(owner), {'kind': 'done', 'period': '7'})[0] == dash.kind_domain('done', 7))
check('...and ignores unknown parameters', dash.invite_filters(env, owner, assignment_domain(owner), {'kind': 'zzz', 'period': '3', 'x': '1'})[0] == [])

# ---- workload (owner and managers)
wl = owner.dash_workload()
check('workload lists the members who can be responsible, with clients and open invitations',
      {w[0] for w in wl} >= {c1, c2} and next(w for w in wl if w[0] == c1)[1] == 1 and next(w for w in wl if w[0] == c1)[2] >= 1)
check('a counselor gets no workload table', c1.dash_workload() == [])

# ---- checklist
steps = owner.dash_checklist()
check('the owner sees the checklist while steps are open', steps and steps[0][1] and not all(s[1] for s in steps))
check('a counselor does not', c1.dash_checklist() == [])
edu.sudo().onboarding_dismissed_on = now
check('dismissing hides it', owner.dash_checklist() == [])
edu.sudo().onboarding_dismissed_on = False

# ---- gated panel line, the page never carries a score or band
pend = panel('employment', 'پنل S12 در انتظار', approved=False)
pown = member(pend, 'owner')
check('a panel awaiting approval tells its owner', line(pown, 'gated') is not None)
blob = str([owner.dash_attention(), owner.dash_tiles(30), owner.dash_funnel(30), owner.dash_checklist()]).lower()
check('no dashboard block carries a score or a band', not any(w in blob for w in ('score', 'band', 'نمره', 'سطح کم', 'سطح زیاد')))

passed = sum(1 for _n_, ok in results if ok)
print('SUMMARY %d/%d passed' % (passed, len(results)))
env.cr.rollback()
