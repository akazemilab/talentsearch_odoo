# Panel v2 S6 (invitations: expiry, opened, extend, cron, migration). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
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
    env.flush_all()
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
    login = 'ts.pv2s6.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose):
    org = env['res.partner'].create({'name': 'پنل آزمون S6', 'is_company': True})
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




from datetime import timedelta
from odoo import fields
inst = env['ts.instrument'].search([('state', '=', 'published')], limit=1)
ws = panel('education')
o, c1 = member(ws, 'owner'), member(ws, 'counselor')
now = fields.Datetime.now()


def invite(name, **kw):
    vals = {'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': name, 'invited_by_id': o.user_id.id}
    vals.update(kw)
    return A.sudo().create(vals)


# ---- defaults
a = invite('الف')
ttl = env['ir.config_parameter'].sudo().get_int('ts_panel.invite_ttl_days', 30) or 30
check('a new invitation is "invited" with an expiry ttl days ahead', a.state == 'invited' and not a.expired
      and abs((a.expires_at - now).total_seconds() - ttl * 86400) < 120, str(a.expires_at))
check('channel defaults to link', a.channel == 'link' and not a.remind_ok)
d = invite('مهلت', deadline=(now + timedelta(days=3)).date())
check('with a deadline, expiry is the end of that day', d.expires_at.date() == d.deadline and d.expires_at.hour == 23, str(d.expires_at))

# ---- opened
a.action_mark_opened()
check('first visit marks it opened', a.opened_at and a.state == 'opened')
t0 = a.opened_at
a.action_mark_opened()
check('opening twice keeps the first time', a.opened_at == t0)
check('invite_state is ok while open and in time', a.invite_state() == 'ok')

# ---- expiry
e = invite('منقضی')
e.sudo().write({'expires_at': now - timedelta(hours=1)})
check('past expiry without the flag: the link already says expired', e.invite_state() == 'expired' and e.state == 'invited')
n = A._cron_expire_invitations()
check('the cron flags exactly the late unaccepted invitation', n >= 1 and e.expired and e.state == 'expired' and not a.expired and not d.expired)
check('expired state comes before opened', (a.write({'expires_at': now - timedelta(minutes=5)}) or A._cron_expire_invitations() or True) and a.state == 'expired')
check('an expired invitation cannot be accepted', raises(lambda: a.action_accept(puser(), share=False)))

# ---- extend
a.action_extend(14, o)
check('extend: new expiry, flag cleared, state back to opened', not a.expired and a.state == 'opened'
      and abs((a.expires_at - now).total_seconds() - 14 * 86400) < 120 and a.invite_state() == 'ok')
check('extend is audited', env['ts.audit.event'].search_count([('event_type', '=', 'assignment.extend'), ('res_id', '=', a.id)]) == 1)
check('extend refuses a bad number of days', raises(lambda: a.action_extend(0, o)) and raises(lambda: a.action_extend(400, o)))
old = invite('قدیمی')
env.cr.execute("UPDATE ts_assignment SET create_date = create_date - interval '40 days' WHERE id = %s", [old.id])
old.invalidate_recordset()
check('the old read-time rule (created + 30 days) no longer expires an invitation whose stored expiry is in the future', old.invite_state() == 'ok')

# ---- expiry only before acceptance
u = puser()
acc = invite('پذیرفته')
acc.action_accept(u, share=False)
acc.sudo().write({'expires_at': now - timedelta(days=1)})
A._cron_expire_invitations()
check('an accepted invitation never expires', not acc.expired and acc.state in ('accepted', 'in_progress'))
check('and it cannot be extended', raises(lambda: acc.action_extend(7, o)))

# ---- withdraw, decline keep their place in the order
w = invite('لغو')
w.action_mark_opened()
w.action_withdraw()
check('withdrawn beats opened', w.state == 'withdrawn')
check('a withdrawn invitation cannot be extended', raises(lambda: w.action_extend(7, o)))
w.sudo().write({'expires_at': now - timedelta(days=1)})
A._cron_expire_invitations()
check('the cron skips withdrawn invitations', not w.expired and w.state == 'withdrawn')

# ---- client counters
cl = a.client_id
check('open_count counts opened and invited invitations', cl.open_count >= 1)

# ---- migration
env.cr.execute("UPDATE ts_assignment SET expires_at = NULL, expired = FALSE WHERE id IN %s", [(old.id, e.id)])
env.invalidate_all()
r1 = A.ts_migrate_s6()
check('migration fills a missing expiry and flags the late ones', r1['expires_at'] >= 2 and old.expires_at and e.expires_at)
env.invalidate_all()
r2 = A.ts_migrate_s6()
check('a second run changes nothing', r2['expires_at'] == 0 and r2['expired'] == 0, str(r2))

# ---- channel of an SMS invitation
s = invite('پیامکی', invitee_phone='09125550000')
s.sudo().write({'sms_sent_at': now})
env.cr.execute("UPDATE ts_assignment SET channel = 'link' WHERE id = %s", [s.id])
env.invalidate_all()
A.ts_migrate_s6()
check('migration sets channel sms for an invitation that sent an SMS', s.channel == 'sms')

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
