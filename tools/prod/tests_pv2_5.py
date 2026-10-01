# Panel v2 S5 (client edit, groups, merge, handover, saved views). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
# The clone has already been upgraded, so the migration ran once on a copy of live data.
import psycopg2
from odoo.exceptions import UserError, ValidationError
from odoo.addons.ts_panel.models.text import norm_text
from odoo.addons.ts_panel.controllers.clients import visible_domain

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=(UserError, ValidationError, psycopg2.IntegrityError)):
    try:
        with env.cr.savepoint():
            fn()
            env.flush_all()
    except exc:
        return True
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, T, C = (env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment'], env['ts.attempt'],
                 env['ts.panel.client'])
_n = [0]


def puser(phone=None):
    _n[0] += 1
    login = 'ts.pv2s5.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose):
    org = env['res.partner'].create({'name': 'پنل آزمون S5', 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': org.name, 'purpose': purpose, 'partner_id': org.id,
                   'escalation_contact_id': org.id if purpose == 'clinical' else False})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role):
    m = M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role})
    if role in ('counselor', 'clinician'):
        m.write({'license_number': 'T', 'verification_state': 'verified'})
    return m



G, SV = env['ts.panel.group'], env['ts.saved.view']
inst = env['ts.instrument'].search([('state', '=', 'published')], limit=1)
ws = panel('education')
o, c1, c2, adm = member(ws, 'owner'), member(ws, 'counselor'), member(ws, 'counselor'), member(ws, 'admin')
ws2 = panel('education')
o2 = member(ws2, 'owner')


def invite(name, by=None, **kw):
    vals = {'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': name}
    vals.update(kw)
    return A.sudo().create(vals)


# ---- unique code per panel
x = C.create({'workspace_id': ws.id, 'name': 'الف', 'code': 'S-1', 'source': 'manual'})
check('code is unique inside a panel', raises(lambda: C.create({'workspace_id': ws.id, 'name': 'ب', 'code': 'S-1', 'source': 'manual'})))
y = C.create({'workspace_id': ws2.id, 'name': 'پ', 'code': 'S-1', 'source': 'manual'})
check('the same code is fine in another panel', y.code == 'S-1')

# ---- duplicates warn, never block
d = C.create({'workspace_id': ws.id, 'name': 'علیرضا کریمی', 'phone': '09121110001', 'source': 'manual'})
check('duplicate by normalised name', d in C.ts_duplicates(ws.id, name='عليرضا  كريمي'))
check('duplicate by phone', d in C.ts_duplicates(ws.id, phone='0912 111 0001'))
check('a duplicate does not block creating', bool(C.create({'workspace_id': ws.id, 'name': 'علیرضا کریمی', 'source': 'manual'})))
check('duplicates never cross panels', d not in C.ts_duplicates(ws2.id, name='علیرضا کریمی'))

# ---- groups
g = G.create({'workspace_id': ws.id, 'name': 'کلاس هفتم', 'kind': 'class'})
check('group name is unique among active groups', raises(lambda: G.create({'workspace_id': ws.id, 'name': ' کلاس  هفتم '.replace('  ', ' ')})))
g.write({'client_ids': [(4, x.id), (4, d.id)]})
check('group counts its clients', g.client_count == 2)
g.write({'active': False})
check('archiving a group keeps its clients', len(g.client_ids) == 2 and x.group_ids == g)
check('an archived group frees its name', bool(G.create({'workspace_id': ws.id, 'name': 'کلاس هفتم'})))

# ---- archive / restore
a_in = invite('بایگانی', invitee_email='arch@example.invalid')
cl = a_in.client_id
check('only a member with clients:archive may archive', raises(lambda: cl.ts_archive(c1)) and raises(lambda: cl.ts_archive(c2)))
cl.ts_archive(o)
check('archive: state, date, audit', cl.state == 'archived' and cl.archived_on and env['ts.audit.event'].search_count(
    [('event_type', '=', 'client.archive'), ('res_id', '=', cl.id)]) == 1)
check('an archived client gets no new invitation', raises(lambda: A.sudo().create(
    {'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'x', 'client_id': cl.id})))
cl.ts_restore(o)
check('restore brings it back', cl.state == 'active' and not cl.archived_on)

# ---- merge
m1 = invite('ادغام یک', invitee_email='m1@example.invalid').client_id
m2 = invite('ادغام دو', invitee_phone='09125550002').client_id
g2 = G.create({'workspace_id': ws.id, 'name': 'گروه ادغام'})
g2.write({'client_ids': [(4, m2.id)]})
m2.write({'code': 'M-2'})
check('merge needs clients:merge', raises(lambda: m1.ts_merge(m2, c1)))
prev = m1.ts_merge_preview(m2)
check('preview counts what moves', prev['assignments'] == 1 and prev['groups'] == 1)
m1.ts_merge(m2, o)
check('merge moves invitations and groups, fills empty fields',
      len(m1.assignment_ids) == 2 and g2 in m1.group_ids and m1.phone == '09125550002' and m1.code == 'M-2')
check('merged row is archived, points to the survivor and keeps nothing live',
      m2.state == 'archived' and m2.merged_into_id == m1 and not m2.code and not m2.group_ids and not m2.assignment_ids)
check('merge is audited', env['ts.audit.event'].search_count([('event_type', '=', 'client.merge'), ('res_id', '=', m1.id)]) >= 1)
check('a merged row cannot be merged or restored back to life',
      raises(lambda: m1.ts_merge(m2, o)) and (m2.ts_restore(o) or m2.state == 'archived'))
check('merge refuses itself and other panels', raises(lambda: m1.ts_merge(m1, o)) and raises(lambda: m1.ts_merge(y, o)))

# two accounts never merge
u1, u2 = puser(), puser()
k1 = C.create({'workspace_id': ws.id, 'name': 'حساب یک', 'user_id': u1.id, 'source': 'manual'})
k2 = C.create({'workspace_id': ws.id, 'name': 'حساب دو', 'user_id': u2.id, 'source': 'manual'})
check('two different accounts refuse to merge', raises(lambda: k1.ts_merge(k2, o)))

# imported (locked) people never merge
p = env['res.partner'].create({'name': 'واردشده'})
ic = C.ts_for_import(ws.id, p)
check('a locked imported client refuses to merge', raises(lambda: x.ts_merge(ic, o)) and raises(lambda: ic.ts_merge(x, o)))

# ---- handover
h = invite('واگذاری', invitee_email='h@example.invalid', invited_by_id=c1.user_id.id).client_id
h.write({'responsible_id': c1.id})
check('only the responsible specialist asks for handover', raises(lambda: h.ts_request_handover(c2, c1)))
check('handover to oneself or an admin is refused', raises(lambda: h.ts_request_handover(c1, c1)) and raises(lambda: h.ts_request_handover(c1, adm)))
check('a counselor request waits for confirmation', h.ts_request_handover(c1, c2) == 'requested' and h.responsible_id == c1 and h.handover_to_id == c2)
check('a counselor cannot confirm', raises(lambda: h.ts_decide_handover(c1, True)))
h.ts_decide_handover(o, False)
check('declined: nothing changes, request cleared', h.responsible_id == c1 and not h.handover_to_id)
h.ts_request_handover(c1, c2)
h.ts_decide_handover(o, True)
check('accepted: responsible changes, request cleared', h.responsible_id == c2 and not h.handover_to_id)
h.write({'responsible_id': o.id})
check('the owner hands over at once', h.ts_request_handover(o, c1) == 'done' and h.responsible_id == c1)

# ---- saved views
SV.create({'member_id': c1.id, 'page': 'clients', 'name': 'من', 'query': 'filter=mine'})
check('view name is unique per member and page', raises(lambda: SV.create({'member_id': c1.id, 'page': 'clients', 'name': 'من', 'query': ''})))
for i in range(9):
    SV.create({'member_id': c1.id, 'page': 'clients', 'name': 'نما %d' % i, 'query': ''})
check('at most 10 saved views per member and page', raises(lambda: SV.create({'member_id': c1.id, 'page': 'clients', 'name': 'یازدهم', 'query': ''})))
check('the same name is fine for another member', bool(SV.create({'member_id': c2.id, 'page': 'clients', 'name': 'من', 'query': ''})))

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
