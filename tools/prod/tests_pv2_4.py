# Panel v2 S4 (clients, migration M3-M5). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
# The clone has already been upgraded, so the migration ran once on a copy of live data.
from odoo.exceptions import UserError, ValidationError
from odoo.addons.ts_panel.models.text import norm_text
from odoo.addons.ts_panel.controllers.clients import visible_domain

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


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, T, C = (env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment'], env['ts.attempt'],
                 env['ts.panel.client'])
_n = [0]


def puser(phone=None):
    _n[0] += 1
    login = 'ts.pv2s4.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose):
    org = env['res.partner'].create({'name': 'پنل آزمون S4', 'is_company': True})
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


# ---- text normalisation
check('norm_text: Arabic ي/ك and digits, ZWNJ, case',
      norm_text('عليرضا  كريمي ۱۲٣') == 'علیرضا کریمی 123' and norm_text('می‌خواهم') == 'می خواهم' and norm_text(None) == '')

# ---- the migration ran on a copy of live data
imp_total = T.search_count([('source', '=', 'import'), ('workspace_id', '!=', False), ('person_id', '!=', False)])
imp_clients = C.search([('source', '=', 'import')])
groups = {(t.workspace_id.id, t.person_id.id) for t in T.search([('source', '=', 'import'), ('workspace_id', '!=', False), ('person_id', '!=', False)])}
check('M4: one client per (panel, historical person)', len(imp_clients) == len(groups), '%s clients / %s people / %s results' % (len(imp_clients), len(groups), imp_total))
check('M4: every imported result has its client', not T.search_count([('source', '=', 'import'), ('workspace_id', '!=', False), ('person_id', '!=', False), ('client_id', '=', False)]))
check('M4: imported clients carry no phone, email or account and are locked',
      all(not c.phone and not c.email and not c.user_id and c.contact_locked and c.partner_id for c in imp_clients))
check('M4: nothing was released', not T.search_count([('source', '=', 'import'), ('released', '=', True)]))
check('M3: every invitation has a client of its own panel',
      not A.search_count([('client_id', '=', False)]) and not A.search([]).filtered(lambda a: a.client_id.workspace_id != a.workspace_id))
r1 = C.ts_migrate_s4()
check('migration is idempotent: a second run changes nothing', not any(r1.values()), str(r1))
if imp_clients:
    ic = imp_clients[0]
    check('P20: contact fields of an imported client are refused', raises(lambda: ic.write({'phone': '09121234567'}))
          and raises(lambda: ic.write({'guardian_name': 'x'})))
    inst0 = env['ts.instrument'].search([('state', '=', 'published')], limit=1)
    check('P20: an invitation for an imported client is refused', raises(lambda: A.create(
        {'workspace_id': ic.workspace_id.id, 'instrument_id': inst0.id, 'invitee_name': 'x', 'client_id': ic.id})))
    ICP = env['ir.config_parameter'].sudo()
    ICP.set_str('ts_panel.import_contact_unlocked', '1')
    ic.invalidate_recordset()
    unlocked = not ic.contact_locked
    ICP.set_str('ts_panel.import_contact_unlocked', '')
    ic.invalidate_recordset()
    check('P20: only the platform setting unlocks them', unlocked and ic.contact_locked)

# ---- the client is the single place of responsibility
inst = env['ts.instrument'].search([('state', '=', 'published')], limit=1)
ws = panel('education')
o = member(ws, 'owner')
c1, c2 = member(ws, 'counselor'), member(ws, 'counselor')
adm = member(ws, 'admin')


def invite(by, name, email=None, phone=None, **kw):
    vals = {'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': name, 'invited_by_id': by.user_id.id}
    if email:
        vals['invitee_email'] = email
    if phone:
        vals['invitee_phone'] = phone
    vals.update(kw)
    return A.with_user(by.user_id).sudo().create(vals) if False else A.sudo().create(vals)


a1 = invite(c1, 'سارا', email='sara@example.invalid')
check('new invitation -> new client (source invite) with the creator as responsible',
      a1.client_id.source == 'invite' and a1.client_id.responsible_id == c1 and a1.responsible_id == c1)
a2 = invite(c2, 'سارا دوم', email='Sara@Example.invalid')
check('same exact email -> same client (never by name)', a2.client_id == a1.client_id)
a3 = invite(c1, 'سارا', email='other@example.invalid')
check('same name, other email -> another client', a3.client_id != a1.client_id)
a1.write({'invitee_phone': '۰۹۱۲۳۴۵۶۷۸۹'})
check('a phone written later is copied to a client without one', a1.client_id.phone == '09123456789')
a4 = invite(c2, 'سارا سوم', phone='09123456789')
check('exact phone matches too', a4.client_id == a1.client_id)
a5 = invite(o, 'مدیر', email='own@example.invalid')
check('an owner of a panel with colleagues is not made responsible', not a5.client_id.responsible_id)
a1.client_id.responsible_id = c2
check('changing the client changes its invitations', a1.responsible_id == c2 and a2.responsible_id == c2)
a1.responsible_id = False
check('writing the old field writes the client', not a1.client_id.responsible_id and not a2.responsible_id)
aud = env['ts.audit.event'].search_count([('event_type', '=', 'client.responsible_change'), ('res_id', '=', a1.client_id.id)])
check('and it is audited on the client', aud >= 2, str(aud))
check('responsible must be a specialist of this panel', raises(lambda: a1.client_id.write({'responsible_id': adm.id})))

# ---- visibility R0-R3 for clients
a1.client_id.responsible_id = c1
cl = a1.client_id
other = a3.client_id
other.responsible_id = c2
free = a5.client_id
check('R0 owner sees every client', all(o.can_see(x) for x in (cl, other, free)))
check('R1 counselor sees own, not a colleague\'s', c1.can_see(cl) and not c1.can_see(other))
check('R2 counselor of an education panel sees unassigned', c1.can_see(free))
check('admin sees participants (clients:read_all)', adm.can_see(cl))
dom_c1 = C.search(visible_domain(c1))
check('the list domain gives the same answer as can_see', set(dom_c1.ids) == {x.id for x in C.search([('workspace_id', '=', ws.id)]) if c1.can_see(x)})

# ---- accept links the account; auto link
u = puser()
a1.write({'invitee_email': u.email})
check('accept links the account to the client', bool(a1.action_accept(u, True)) and a1.client_id.user_id == u)
check('the accepted attempt knows the client', a1.attempt_id.client_id == a1.client_id)
x = invite(c1, 'همان شخص', email='x@example.invalid')
x_client = x.client_id
x.action_accept(u, True)
check('auto link: the invitation moves to the account\'s client, the empty row is archived',
      x.client_id == cl and x_client.state == 'archived' and x_client.merged_into_id == cl)
check('auto link is audited', env['ts.audit.event'].search_count([('event_type', '=', 'client.auto_link')]) >= 1)
y = invite(c1, 'برای دیگری', email='y@example.invalid')
y.client_id.user_id = puser()
check('an invitation whose client belongs to another account is refused on accept', raises(lambda: y.action_accept(u, True)))
# the responsible person cannot be the accepting account
sp = puser()
m_sp = M.create({'workspace_id': ws.id, 'user_id': sp.id, 'role': 'counselor'})
m_sp.write({'license_number': 'T', 'verification_state': 'verified'})
z = invite(m_sp, 'خودش', email=sp.email)
check('creator is responsible by default', z.responsible_id == m_sp)
z.action_accept(sp, True)
check('accepting your own invitation clears the self-responsibility', not z.client_id.responsible_id and z.client_id.user_id == sp)

# ---- leaving releases clients, even those without an invitation
lonely = C.create({'workspace_id': ws.id, 'name': 'بدون دعوت', 'responsible_id': c2.id})
check('manually made client keeps its responsible', lonely.responsible_id == c2)
c2.active = False
env.flush_all()
check('deactivating the specialist releases clients with and without invitations',
      not lonely.responsible_id and not other.responsible_id)

# ---- default responsible: a solo owner who practises
ws2 = panel('education')
solo = member(ws2, 'owner')
solo.owner_practices = True
s = A.sudo().create({'workspace_id': ws2.id, 'instrument_id': inst.id, 'invitee_name': 'تکی', 'invited_by_id': solo.user_id.id})
check('a solo practising owner is responsible for their invitations', s.responsible_id == solo)

# ---- imported attempt created later joins the person's client
if imp_clients:
    ic = imp_clients[0]
    before = C.search_count([])
    t = T.sudo().create({'user_id': False, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id,
                         'workspace_id': ic.workspace_id.id, 'person_id': ic.partner_id.id, 'source': 'import'}) \
        if 'user_id' in T._fields and not T._fields['user_id'].required else None
    check('a new imported result of a known person joins the existing client', t is None or (t.client_id == ic and C.search_count([]) == before))

# ---- counts
check('open and done counters', a1.client_id.open_count + a1.client_id.done_count >= 1)

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
