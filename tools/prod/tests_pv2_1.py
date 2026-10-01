# Panel v2 S1 (permissions) P01-P17, P23. Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
# P24 (deny event survives the 404, throttled) needs a real request: see ts_http_pv2_1.py.
import re

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.ts_org.models.perms import ALL_PERMS, ROLE_PERMS
from odoo.addons.ts_core.models.audit import clean_detail, route_of
from odoo.addons.ts_core.models.workspace import ROLES_BY_PURPOSE

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


# The table of 05_permissions_matrix.md section 2, transcribed once (this copy is independent of perms.py).
TABLE = r'''
| `panel:view` (enter, dashboard) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `panel:profile` (name, logo, contact, client word) | ✓ | — | — | ✓ | — | ✓ | — | — |
| `panel:settings` (terms, ownership, closing) | ✓ | — | — | — | — | — | — | — |
| `panel:transfer` (hand ownership over) | ✓ | — | — | — | — | — | — | — |
| `panel:close` | ✓ | — | — | — | — | — | — | — |
| `members:read` | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `members:invite` (invite, send again, revoke an invitation) | ✓ | — | — | ✓ | — | ✓ | — | — |
| `members:manage` (role, deactivate) | ✓ | — | — | — | — | — | — | — |
| `members:add_owner` | ✓ | — | — | — | — | — | — | — |
| `clients:read_all` | ✓ | ✓ | — | ✓ | — | ✓ | — | ✓ |
| `clients:read_own` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `clients:read_unassigned` | ✓ | ✓ | ✓ edu | ✓ | — | ✓ | — | ✓ |
| `clients:write` (create, edit) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `clients:assign` (set responsible) | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `clients:be_responsible` | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `clients:archive` | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `clients:merge` | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `clients:import` (CSV) | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — |
| `clients:export` (list, no results) | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `groups:manage` | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — |
| `invites:create` (single) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `invites:bulk` (group, campaign, open link) | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — |
| `invites:manage` (withdraw, remind, extend) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `results:summary` | ✓ emp | — | — | — | — | ✓ | ✓ | ✓ |
| `results:education` | ✓ edu | — | ✓ | — | — | — | — | — |
| `results:clinical` | ✓ clin, only with `owner_practices` | — | — | ✓ | ✓ | — | — | — |
| `results:export` (identifiable results file) | ✓ edu, emp | — | — | — | — | ✓ | — | — |
| `reports:group` | ✓ edu, emp | — | ✓ | — | — | ✓ | — | ✓ |
| `credits:read` | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `audit:read` | ✓ | — | — | — | — | — | — | — |
| `audit:export` | ✓ | — | — | — | — | — | — | — |
| `support:view` (see platform access to this panel) | ✓ | — | — | — | — | — | — | — |
| `help:view` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
'''
COLS = ['owner', 'admin', 'counselor', 'clinic_director', 'clinician', 'hr_admin', 'hiring_manager', 'reviewer']
PCODE = {'education': 'edu', 'employment': 'emp', 'clinical': 'clin'}
DOC = {}   # perm -> {role: set of purposes}
for line in TABLE.strip().splitlines():
    cells = [c.strip() for c in line.strip().strip('|').split('|')]
    perm = re.match(r'`([a-z_]+:[a-z_]+)`', cells[0]).group(1)
    DOC[perm] = {}
    for role, cell in zip(COLS, cells[1:]):
        if not cell.startswith('✓'):
            continue
        only = {p for p, c in PCODE.items() if re.search(r'\b%s\b' % c, cell.split('only with')[0])}
        DOC[perm][role] = only or set(PCODE)

# ---------------------------------------------------------------- P01 / P02
check('P01 registry has exactly the 33 permissions of the table', set(DOC) == set(ALL_PERMS) and len(DOC) == 33, str(len(DOC)))
bad = []
for purpose in PCODE:
    for role in COLS:
        want = {p for p in DOC if purpose in DOC[p].get(role, ())}
        if set(ROLE_PERMS[(role, purpose)]) != want:
            bad.append((role, purpose, sorted(want ^ set(ROLE_PERMS[(role, purpose)]))))
check('P01 ROLE_PERMS equals the table for every role x purpose', not bad, str(bad[:3]))
check('P01 benefit_admin works exactly like admin',
      all(ROLE_PERMS[('benefit_admin', p)] == ROLE_PERMS[('admin', p)] for p in ('benefits', 'education')))

portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
_n = [0]


def puser(tag=None):
    _n[0] += 1
    login = 'ts.pv2s1.%s%d@example.invalid' % (tag or 'u', _n[0])
    return U.create({'name': login, 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


W, M, A = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment']


def panel(purpose, approved=True, state='pilot'):
    org = env['res.partner'].create({'name': 'پنل آزمون S1 ' + purpose, 'is_company': True})
    org.write({'is_company': True})
    vals = {'name': org.name, 'purpose': purpose, 'partner_id': org.id}
    if purpose == 'clinical':
        vals['escalation_contact_id'] = org.id
    ws = W.create(vals)
    if approved:
        ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = state
    return ws


def member(ws, role, verified=True, **kw):
    m = M.create(dict({'workspace_id': ws.id, 'user_id': puser(role).id, 'role': role}, **kw))
    if verified and role in ('clinician', 'clinic_director', 'counselor'):
        m.write({'license_number': 'T-%d' % m.id, 'verification_state': 'verified'})
    return m


# a member-level view of the table: effective perms in a healthy panel equal the role table
# (the only difference: an owner of a clinical panel has no results:clinical without owner_practices)
panels = {p: panel(p) for p in PCODE}
diff = []
for purpose, ws in panels.items():
    for role in sorted(ROLES_BY_PURPOSE[purpose]):
        m = member(ws, role)
        want = set(ROLE_PERMS[(role, purpose)])
        if role == 'owner' and purpose == 'clinical':
            want.discard('results:clinical')
        if set(m.perms()) != want:
            diff.append((purpose, role, sorted(set(m.perms()) ^ want)))
check('P01 member.perms() equals the table in a healthy panel', not diff, str(diff[:3]))
m_any = M.search([('workspace_id', '=', panels['education'].id)], limit=1)
check('P02 unknown permission string raises ValueError', raises(lambda: m_any.has_perm('clients:fly'), ValueError))

# ---------------------------------------------------------------- P03 .. P06
edu = panels['education']
own_e = M.search([('workspace_id', '=', edu.id), ('role', '=', 'owner')], limit=1)
c1 = M.search([('workspace_id', '=', edu.id), ('role', '=', 'counselor')], limit=1)
c1.active = False
check('P03 inactive member has an empty permission set', c1.perms() == frozenset() and c1.deactivated_on)
c1.active = True
check('P03 reactivation clears deactivated_on', not c1.deactivated_on)

ws_s = panel('education')
o_s = member(ws_s, 'owner'); c_s = member(ws_s, 'counselor')
ws_s.state = 'suspended'
check('P04 suspended panel: only panel:view', o_s.perms() == {'panel:view'} and c_s.perms() == {'panel:view'})
ws_s.state = 'closed'
check('P04 closed panel: only panel:view (+ owner export within 90 days when closed_on exists)',
      c_s.perms() == {'panel:view'} and {'panel:view'} <= set(o_s.perms()) <= {'panel:view', 'clients:export'})

ws_g = panel('employment', approved=False)
o_g = member(ws_g, 'owner'); h_g = member(ws_g, 'hr_admin')
check('P05 gated panel: invitations and import refused, the rest unchanged',
      ws_g.gated and not (o_g.perms() & {'invites:create', 'invites:bulk', 'clients:import'})
      and 'members:invite' in o_g.perms() and 'clients:read_all' in h_g.perms())

clin = panels['clinical']
cl_un = member(clin, 'clinician', verified=False)
cd_un = member(clin, 'clinic_director', verified=False)
check('P06 unverified clinician and clinic_director: only panel:view and help:view',
      cl_un.perms() == {'panel:view', 'help:view'} and cd_un.perms() == {'panel:view', 'help:view'})
cl_un.write({'license_number': 'T-x', 'verification_state': 'verified'})
check('P06 verified clinician gets the table', set(cl_un.perms()) == set(ROLE_PERMS[('clinician', 'clinical')]))
check('P06 an unverified clinician cannot act (404 today)', not cd_un.can_act() and cl_un.can_act())
ws_p = panel('clinical')
o_p = member(ws_p, 'owner', owner_practices=True)
check('P06 unverified practising owner: everything except results:clinical',
      set(o_p.perms()) == set(ROLE_PERMS[('owner', 'clinical')]) - {'results:clinical'})

# ---------------------------------------------------------------- results
inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')])
pub = env['ts.instrument'].search([('state', '=', 'published')])
emp_i = pub.filtered(lambda i: i.purpose == 'employment')[:1]
MENTAL = {'بیتابی روانی', 'نارضایتی از زندگی', 'مسائل نوجوان', 'مشکلات زناشویی', 'مشاوره ازدواج', 'مشکلات رفتاری کودک'}
mental = pub.filtered(lambda i: i.category in MENTAL)[:1]


def finish(att):
    att.give_consent()
    for it in att.active_items():
        att.save_answer(it.id, 1 + it.id % 5)
    att.action_submit()
    return att


def finish_matrix(att):
    att.give_consent()
    items = att.active_items()
    for n, label in enumerate(['ریاضی', 'هنر', 'ورزش', 'زبان']):
        f = att.ts_add_field(label)
        for i, it in enumerate(items):
            att.ts_save_cell(f, it.id, (i * (n % 3 + 1) + 2 * n + i // 5) % 5 + 1)
        att.ts_finish_field(f)
    assert att.action_submit()
    return att


def done_assignment(ws, instrument, owner_member, matrix=False, resp=None, share=True):
    a = A.sudo().create({'workspace_id': ws.id, 'instrument_id': instrument.id, 'invitee_name': 'مراجع آزمون',
                         'invited_by_id': owner_member.user_id.id,
                         'responsible_id': resp.id if resp else False})
    att = a.action_accept(puser('client'), share=share)
    (finish_matrix if matrix else finish)(att)
    return a


# solo psychologist (G1)
ws_solo = panel('clinical')
solo = member(ws_solo, 'owner', owner_practices=True)
solo.write({'license_number': 'T-solo', 'verification_state': 'verified'})
a_solo = done_assignment(ws_solo, mental, solo, resp=solo)
check('P07 verified solo psychologist sees clinical on the own client', a_solo.result_level(solo) == 'clinical')
solo.verification_state = 'pending'
check('P07 unverified solo psychologist sees only status', a_solo.result_level(solo) == 'status')
solo.verification_state = 'verified'
own_c = member(clin, 'owner')
a_c = done_assignment(clin, mental, own_c)
check('P08 owner of a clinical panel without owner_practices never gets clinical',
      a_c.result_level(own_c) == 'status' and own_c.owner_practices is False)

# P09 admin
ws_a = {p: panel(p) for p in PCODE}
lv = {}
for p, ws in ws_a.items():
    o = member(ws, 'owner'); ad = member(ws, 'admin')
    if p == 'education':
        a = done_assignment(ws, inst, o, matrix=True)
    elif p == 'employment':
        a = done_assignment(ws, emp_i, o)
    else:
        a = done_assignment(ws, mental, o)
    lv[p] = (a.result_level(ad), ad.can_see(a), a.visible_results(ad)[0])
check('P09 admin sees participants and gets status on every result in all three purposes',
      all(v == ('status', True, 'none') for v in lv.values()), str(lv))

# P10 R0
cx = member(panels['employment'], 'hr_admin')
check('P10 R0: member of panel A gets none for a client of panel B',
      a_c.result_level(cx) == 'none' and not cx.can_see(a_c))
both = puser('both')
ws_b1, ws_b2 = panel('education'), panel('employment')
M.create({'workspace_id': ws_b1.id, 'user_id': both.id, 'role': 'owner'})
M.create({'workspace_id': ws_b2.id, 'user_id': both.id, 'role': 'owner'})
check('P13 the same person may be a member of two panels', M.search_count([('user_id', '=', both.id)]) == 2)

# P11 R2/R3
ws_r = panel('education')
o_r = member(ws_r, 'owner'); co_r = member(ws_r, 'counselor'); co2_r = member(ws_r, 'counselor')
a_un = done_assignment(ws_r, inst, o_r, matrix=True)
a_mine = done_assignment(ws_r, inst, o_r, matrix=True, resp=co_r)
check('P11 education counselor sees own and unassigned, not a colleague\'s',
      co_r.can_see(a_un) and co_r.can_see(a_mine) and not co2_r.can_see(a_mine))
ws_h = panel('employment')
o_h = member(ws_h, 'owner'); hm = member(ws_h, 'hiring_manager'); hm2 = member(ws_h, 'hiring_manager')
a_h_un = done_assignment(ws_h, emp_i, o_h)
a_h_mine = done_assignment(ws_h, emp_i, o_h, resp=hm)
check('P11 hiring manager does not see unassigned or a colleague\'s client',
      not hm.can_see(a_h_un) and hm.can_see(a_h_mine) and not hm2.can_see(a_h_mine))
ws_cl = panel('clinical')
cl_a = member(ws_cl, 'clinician'); cl_b = member(ws_cl, 'clinician')
a_cl_un = done_assignment(ws_cl, mental, cl_a)
check('P11 clinician does not see unassigned clients', not cl_a.can_see(a_cl_un))

# P12 result level steps
a_nothing = A.sudo().create({'workspace_id': ws_h.id, 'instrument_id': emp_i.id, 'invitee_name': 'بدون تلاش',
                             'invited_by_id': o_h.user_id.id, 'responsible_id': hm.id})
check('P12 step 2: invitation without attempt gives status', a_nothing.result_level(hm) == 'status')
a_acc = A.sudo().create({'workspace_id': ws_h.id, 'instrument_id': emp_i.id, 'invitee_name': 'نیمه‌کاره',
                         'invited_by_id': o_h.user_id.id, 'responsible_id': hm.id})
a_acc.action_accept(puser('c'), share=True)
check('P12 step 3: unfinished attempt gives status', a_acc.result_level(hm) == 'status')
check('P12 step 8: employment summary for a hiring manager / owner / reviewer',
      a_h_mine.result_level(hm) == 'summary' and a_h_mine.result_level(o_h) == 'summary'
      and a_h_mine.result_level(member(ws_h, 'reviewer')) == 'summary')
a_h_mine.attempt_id.sudo().write({'released': False})
check('P12 step 5: unreleased result gives status', a_h_mine.result_level(hm) == 'status')
a_h_mine.attempt_id.sudo().write({'released': True})
a_h_mine.action_revoke_share(a_h_mine.user_id)
check('P12 step 6: revoked share gives status', a_h_mine.result_level(hm) == 'status')
check('P12 step 9: education counselor gets education', a_mine.result_level(co_r) == 'education'
      and a_mine.visible_results(co_r)[0] == 'education')
ws_k = panel('clinical')
cd_k = member(ws_k, 'clinic_director')
a_k = done_assignment(ws_k, mental, cd_k, resp=member(ws_k, 'clinician'))
check('P12 step 10: clinic director gets clinical, owner without practice only status',
      a_k.result_level(cd_k) == 'clinical' and a_k.result_level(member(ws_k, 'owner')) == 'status')
check('P12 old interface: status maps to none', a_k.visible_results(member(ws_k, 'owner'))[0] == 'none')

# P13 one active membership per person per panel
dup = puser('dup')
M.create({'workspace_id': ws_b1.id, 'user_id': dup.id, 'role': 'counselor'})
check('P13 a second active membership in the same panel is refused',
      raises(lambda: M.create({'workspace_id': ws_b1.id, 'user_id': dup.id, 'role': 'owner'}), Exception))
first = M.search([('workspace_id', '=', ws_b1.id), ('user_id', '=', dup.id)])
first.active = False
env.flush_all()
check('P13 after deactivation the person can be added again',
      bool(M.create({'workspace_id': ws_b1.id, 'user_id': dup.id, 'role': 'owner'})))

# P14 last owner
only_o = M.search([('workspace_id', '=', ws_r.id), ('role', '=', 'owner')])
check('P14 last owner cannot be deactivated', raises(lambda: only_o.write({'active': False}), UserError))
check('P14 last owner cannot be demoted', raises(lambda: only_o.write({'role': 'counselor'}), UserError))

# P15 responsible
rv = member(ws_h, 'reviewer')
check('P15 responsible without clients:be_responsible is refused (reviewer)',
      raises(lambda: a_h_un.write({'responsible_id': rv.id}), ValidationError))
check('P15 admin cannot be responsible', raises(lambda: a_h_un.write({'responsible_id': member(ws_h, 'admin').id}), ValidationError))
self_m = M.create({'workspace_id': ws_h.id, 'user_id': a_h_un.user_id.id, 'role': 'hiring_manager'})
check('P15 the client\'s own account cannot be responsible', raises(lambda: a_h_un.write({'responsible_id': self_m.id}), ValidationError))

# P16 leaving releases clients
hm.active = False
check('P16 member leaves -> clients go to unassigned', not a_h_mine.responsible_id)
aud = env['ts.audit.event'].search([('res_model', '=', 'ts.assignment'), ('res_id', '=', a_h_mine.id),
                                    ('event_type', '=', 'assignment.responsible_change')])
check('P16 and the change is audited', len(aud) >= 1)

# P17 audit cleaning
d = clean_detail({'reason': 'x', 'note': 'y', 'phone': '09121234567', 'name': 'n', 'role': 'owner',
                  'free': '09121234567', 'mail': 'a@b.co', 'nest': {'answer': 1, 'ok': 2}, 'n': 3})
check('P17 deny-listed keys dropped, phone/email values masked',
      set(d) == {'role', 'free', 'mail', 'nest', 'n'} and d['free'] == '***' and d['mail'] == '***'
      and d['nest'] == {'ok': 2} and d['n'] == 3, str(d))
check('P17 route_of replaces ids and tokens',
      route_of('/my/workspaces/12/a/34') == '/my/workspaces/<id>/a/<id>' and route_of('/join/abc123') == '/join/<token>')
ev = env['ts.audit.event'].log('pv2.test', ws_r, workspace=ws_r, reason='secret text', phone='09121234567', keep=1)
check('P17 stored detail has no raw reason/phone and the raw IP column is not written',
      'secret' not in (ev.detail or '') and '0912' not in (ev.detail or '') and not ev.ip_address and ev.outcome == 'ok')
h1 = env['ts.audit.event']._hash_ip('203.0.113.9')
check('P17 an address is stored only as a salted hash (16 hex)', bool(h1) and len(h1) == 16 and '203' not in h1 and h1 == env['ts.audit.event']._hash_ip('203.0.113.9'))
ws_n = panel('education')
ws_n.write({'approval_note': 'یادداشت محرمانه'})
env['ts.audit.event'].search([('workspace_id', '=', ws_n.id)])
check('P17 audit rows never carry the approval note text',
      not env['ts.audit.event'].search_count([('workspace_id', '=', ws_n.id), ('detail', 'ilike', 'محرمانه')]))

# P23 accepting a colleague invitation while already an active member
ws_i = panel('employment')
o_i = member(ws_i, 'owner')
person = puser('inv')
person.partner_id.phone = '09125550000'
inv = env['ts.member.invite'].ts_create(o_i, 'hr_admin', email_raw=person.email)
check('P23 colleague invitation by an owner works', inv.state == 'pending')
M.create({'workspace_id': ws_i.id, 'user_id': person.id, 'role': 'hiring_manager'})
try:
    with env.cr.savepoint():
        inv.action_accept(person, license_number=None)
    msg = ''
except UserError as e:
    msg = str(e.args[0])
check('P23 accepting while already an active member gives a Persian message, not a database error',
      'عضو فعال' in msg, msg)
check('P23 admin cannot invite colleagues', raises(lambda: env['ts.member.invite'].ts_create(
    member(ws_i, 'admin'), 'hiring_manager', email_raw='x@example.invalid'), UserError))

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
