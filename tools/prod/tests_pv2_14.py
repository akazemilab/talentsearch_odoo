# Panel v2 S14 (audit page definitions, support access). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
from datetime import timedelta

import psycopg2
from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.ts_org.models.panel import ROLE_LABELS
from odoo.addons.ts_panel.models import audit_view as av

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=(UserError, ValidationError, AccessError, psycopg2.IntegrityError)):
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
W, M, EA, Ev, View = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.emergency.access', 'ts.audit.event', 'ts.audit.view'))
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s14.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id,
                   **({'escalation_contact_id': org.id} if purpose == 'clinical' else {})})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role):
    return M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role})


mgr = U.create({'name': 'مدیر S14', 'login': 'ts.pv2s14.mgr@example.invalid', 'email': 'ts.pv2s14.mgr@example.invalid',
                'group_ids': [(6, 0, [env.ref('base.group_user').id, env.ref('ts_core.group_ts_manager').id])]})
edu, other, clin = panel('education', 'پنل S14 آموزشی'), panel('employment', 'پنل S14 دیگر'), panel('clinical', 'پنل S14 بالینی')
owner, c1, o2 = member(edu, 'owner'), member(edu, 'counselor'), member(other, 'owner')

# ---- the catalogue
check('every family of an event is a known family', {f for f, _s in av.EVENTS.values()} <= {f for f, _l in av.FAMILIES})
check('every family has at least one event type', all(av.types_of(f) for f, _l in av.FAMILIES))
check('an unknown event type falls back to «رویداد دیگر»', av.family_of('no.such.event') == 'other')
check('the result-view events of every stage are in the results family', all(av.family_of(t) == 'results' for t in ('assignment.result_view', 'attempt.result_view', 'result.view', 'result.print')))
check('a date is read in Latin or Persian digits', av.parse_day('2026-10-01') == av.parse_day('۲۰۲۶-۱۰-۰۱') and av.parse_day('x') is None)
check('a Tehran day starts at 20:30 UTC of the day before', av.tehran_day_start(av.parse_day('2026-10-01')).isoformat().startswith('2026-09-30T20:30'))
f = av.clean_filters({'from': '2026-10-01', 'to': 'bad', 'family': 'results', 'member': str(owner.id)}, M.search([('workspace_id', '=', edu.id)]))
check('filters keep only valid values', f == {'from': '2026-10-01', 'family': 'results', 'member': str(owner.id)})
check('a member of another panel is dropped from the filters', 'member' not in av.clean_filters({'member': str(o2.id)}, M.search([('workspace_id', '=', edu.id)])))
check('an unknown family is dropped', 'family' not in av.clean_filters({'family': 'zzz'}, M.search([('workspace_id', '=', edu.id)])))

# ---- rows are the panel's own
Ev.sudo().with_user(owner.user_id).log('export.create', edu, workspace=edu, member=owner)
Ev.sudo().with_user(c1.user_id).log('member.add', edu, workspace=edu, member=c1)
Ev.sudo().with_user(o2.user_id).log('export.create', other, workspace=other, member=o2)
Ev.sudo().log('weird.new_event', edu, workspace=edu)
rows, total = View.rows(edu, {})
check('the audit page of a panel holds only its own events', total == len(rows) and all(r['id'] in Ev.search([('workspace_id', '=', edu.id)]).ids for r in rows))
check('...and none of another panel', not {r['id'] for r in rows} & set(Ev.search([('workspace_id', '=', other.id)]).ids))
check('each row is a plain sentence naming the actor', any(r['type'] == 'export.create' and owner.user_id.name in r['text'] for r in rows))
check('an unknown event shows the fallback family', any(r['type'] == 'weird.new_event' and r['family'] == 'رویداد دیگر' for r in rows))
check('family filter: exports only', {r['type'] for r in View.rows(edu, {'family': 'exports'})[0]} == {'export.create'})
check('family filter «other» finds the unknown event', [r['type'] for r in View.rows(edu, {'family': 'other'})[0]] == ['weird.new_event'])
check('member filter: only that member\'s events', {r['actor'] for r in View.rows(edu, {'member': str(c1.id)})[0]} == {c1.user_id.name})
check('a date range after today finds nothing', View.rows(edu, {'from': (fields.Date.today() + timedelta(days=2)).isoformat()})[1] == 0)
check('a date range up to today finds the events', View.rows(edu, {'to': (fields.Date.today() + timedelta(days=1)).isoformat()})[1] >= 3)
check('paging: a page of one row', len(View.rows(edu, {}, page=0, limit=1)[0]) == 1 and View.rows(edu, {}, page=1, limit=1)[0][0]['id'] != View.rows(edu, {}, page=0, limit=1)[0][0]['id'])

# ---- support access (SUP-1)
nref = env['ts.notification'].sudo().search_count([('user_id', '=', owner.user_id.id)])
a = EA.with_user(mgr).create({'workspace_id': edu.id, 'kind': 'support', 'ticket_ref': 'TCK-1042', 'reason': 'کمک به مالک برای رفع مشکل ورود اعضا'})
check('a support access opens on an education panel', a.kind == 'support' and a.state == 'open')
check('...for 8 hours', abs((a.expires_at - a.opened_at) - timedelta(hours=8)) < timedelta(minutes=1))
check('...the owner got an in-app notice', env['ts.notification'].sudo().search_count([('user_id', '=', owner.user_id.id), ('type', '=', 'support_access_opened')]) >= 1 and
      env['ts.notification'].sudo().search_count([('user_id', '=', owner.user_id.id)]) > nref)
check('...a colleague who is not an owner was not told', not env['ts.notification'].sudo().search_count([('user_id', '=', c1.user_id.id), ('type', '=', 'support_access_opened')]))
check('...and it is on the audit page of that panel only', any(s['id'] == a.id for s in View.support_rows(edu)) and not View.support_rows(other))
check('...with an audit row in the support family', any(r['family'] == 'پشتیبانی' for r in View.rows(edu, {'family': 'support'})[0]))
check('a support access needs a ticket reference', raises(lambda: EA.with_user(mgr).create({'workspace_id': edu.id, 'kind': 'support', 'reason': 'کمک به مالک برای رفع مشکل ورود اعضا'})))
check('...and a reason of a full sentence', raises(lambda: EA.with_user(mgr).create({'workspace_id': edu.id, 'kind': 'support', 'ticket_ref': 'TCK-1', 'reason': 'کوتاه'})))
check('an emergency access is still clinical only', raises(lambda: EA.with_user(mgr).create({'workspace_id': edu.id, 'reason': 'مراجعی در معرض خطر است و باید تماس بگیریم'})))
e = EA.with_user(mgr).create({'workspace_id': clin.id, 'reason': 'مراجعی در معرض خطر است و باید تماس بگیریم'})
check('an emergency access on a clinical panel keeps its 24 hours', e.kind == 'emergency' and abs((e.expires_at - e.opened_at) - timedelta(hours=24)) < timedelta(minutes=1))
check('a panel owner cannot open one', raises(lambda: EA.with_user(owner.user_id).create({'workspace_id': edu.id, 'kind': 'support', 'ticket_ref': 'TCK-9', 'reason': 'تلاش مالک برای باز کردن دسترسی'})))
env.flush_all()
env.cr.execute("UPDATE ts_emergency_access SET expires_at = now() at time zone 'utc' - interval '1 minute' WHERE id = %s", [a.id])
env.invalidate_all()
check('an expired access is listed as expired', a.state == 'expired' and next(s for s in View.support_rows(edu) if s['id'] == a.id)['state'] == 'منقضی')
check('...and cannot open the results', raises(lambda: a.with_user(mgr).action_view_results()))

# ---- who saw this result (AUD-4)
inv = env['ts.assignment'].sudo().create({'workspace_id': edu.id, 'instrument_id': env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1).id, 'invitee_name': 'مراجع ممیزی'})
at = inv.action_accept(puser(), share=True)
Ev.sudo().with_user(c1.user_id).log('result.view', at, workspace=edu, member=c1, level='education')
v = View.viewers(edu, at)
check('who saw a result: role and date, no name', len(v) == 1 and v[0][1] == ROLE_LABELS['counselor'] and c1.user_id.name not in str(v))
check('another panel\'s events do not leak into it', not View.viewers(other, at))

passed = sum(1 for _n_, ok in results if ok)
print('SUMMARY %d/%d passed' % (passed, len(results)))
