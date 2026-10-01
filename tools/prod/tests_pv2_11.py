# Panel v2 S11 (wallet and ledger). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError

import psycopg2

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
W, M, A, Wal, Txn = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.assignment', 'ts.wallet', 'ts.wallet.txn'))
Inst = env['ts.instrument']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s11.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id,
                   **({'escalation_contact_id': org.id} if purpose == 'clinical' else {})})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def finish(attempt):
    attempt.give_consent()
    for it in attempt.active_items():
        attempt.save_answer(it.id, 1 + it.id % 5)
    attempt.action_submit()


def txns(ws, type_=None):
    dom = [('workspace_id', '=', ws.id)] + ([('type', '=', type_)] if type_ else [])
    return Txn.sudo().search(dom)


plain = Inst.search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
talent = Inst.search([('code', '=', 'TALENT-INV-15')], limit=1)
emp, edu = panel('employment', 'پنل S11 کاری'), panel('education', 'پنل S11 آموزشی')
mgr = U.create({'name': 'مدیر S11', 'login': 'ts.pv2s11.mgr@example.invalid', 'email': 'ts.pv2s11.mgr@example.invalid',
                'group_ids': [(6, 0, [env.ref('base.group_user').id, env.ref('ts_core.group_ts_manager').id])]})
ordinary = puser()

# ---- one debit per finished panel attempt (WAL-1, G14)
w = Wal._for_workspace(emp)
check('a panel gets one wallet, created on first use', w and Wal._for_workspace(emp) == w and Wal.search_count([('workspace_id', '=', emp.id)]) == 1)
check('a second wallet for the same panel is refused', raises(lambda: Wal.sudo().create({'workspace_id': emp.id})))
check('the wallet starts empty', w.balance == 0 and w.units_used == 0 and w.committed() == 0)

a1 = A.create({'workspace_id': emp.id, 'instrument_id': plain.id, 'invitee_name': 'کارجو یک'})
check('an open invitation is counted as committed', w.committed() == 1)
at1 = a1.action_accept(puser(), share=True)
finish(at1)
check('finishing the attempt wrote one usage event', env['ts.usage.event'].search_count([('attempt_id', '=', at1.id)]) == 1)
d1 = txns(emp, 'debit_usage')
check('...and one debit in the free mode: amount 0, one unit, marked free, key usage:<id>',
      len(d1) == 1 and d1.amount == 0 and d1.units == 1 and d1.free and d1.idem_key == 'usage:%d' % at1.id and d1.reason_code == 'completion')
check('...with its attempt, assignment and usage event linked', d1.attempt_id == at1 and d1.assignment_id == a1 and d1.usage_event_id)
check('...and the wallet shows the unit used, balance untouched', w.units_used == 1 and w.balance == 0 and w.committed() == 0)
at1._ts_panel_record_usage()
w._debit_usage(at1)
check('recording again is idempotent', len(txns(emp, 'debit_usage')) == 1 and env['ts.usage.event'].search_count([('attempt_id', '=', at1.id)]) == 1)

# TALENT-INV-15 is scored without super(): the hook still debits (G28, P22)
we = Wal._for_workspace(edu)
b1 = A.create({'workspace_id': edu.id, 'instrument_id': talent.id, 'invitee_name': 'دانش‌آموز یک'})
bt = b1.action_accept(puser(), share=True)
bt.write({'state': 'done', 'released': True, 'submitted_at': fields.Datetime.now()})
bt._ts_panel_record_usage()
check('a finished TALENT-INV-15 attempt in a panel is debited too', len(txns(edu, 'debit_usage')) == 1 and we.units_used == 1)

# not charged: a self-taken attempt, an import, a result shared later by code
self_at = env['ts.attempt'].sudo().search([('workspace_id', '=', False), ('state', '=', 'done')], limit=1)
if self_at:
    self_at._ts_panel_record_usage()
    check('a self-taken attempt (no panel) is never charged', not Txn.sudo().search_count([('attempt_id', '=', self_at.id)]))
b2 = A.create({'workspace_id': edu.id, 'instrument_id': talent.id, 'invitee_name': 'دانش‌آموز دو'})
bi = b2.action_accept(puser(), share=True)
bi.write({'state': 'done', 'source': 'import', 'submitted_at': fields.Datetime.now()})
bi._ts_panel_record_usage()
check('an imported attempt is not charged', not Txn.sudo().search_count([('attempt_id', '=', bi.id)])
      and not env['ts.usage.event'].search_count([('attempt_id', '=', bi.id)]))

# ---- append-only and unique
check('a ledger row cannot be edited', raises(lambda: d1.sudo().write({'amount': 5})))
check('a ledger row cannot be deleted', raises(lambda: d1.sudo().unlink()))
check('the same idempotency key cannot be written twice', raises(lambda: Txn.sudo().create(
    {'wallet_id': w.id, 'type': 'adjust', 'amount': 1, 'idem_key': d1.idem_key})))

# ---- paid mode (not live, but the rule exists): the debit takes one credit
icp = env['ir.config_parameter'].sudo()
icp.set_str('ts_panel.credit_mode', 'paid')
a2 = A.create({'workspace_id': emp.id, 'instrument_id': plain.id, 'invitee_name': 'کارجو دو'})
at2 = a2.action_accept(puser(), share=True)
finish(at2)
d2 = txns(emp, 'debit_usage').filtered(lambda t: t.attempt_id == at2)
check('in the paid mode a debit takes one credit and is not marked free', d2.amount == -1 and not d2.free and d2.balance_after == -1)
check('...and the wallet balance follows', w.balance == -1 and w.units_used == 2)
icp.set_str('ts_panel.credit_mode', 'free')

# ---- grants and adjustments (WAL-6): platform manager only
check('a panel member cannot grant credits', raises(lambda: w.with_user(ordinary).ts_grant(5, 'promo')))
wm = w.with_user(mgr)
g = wm.ts_grant(5, 'promo')
check('a manager grant adds credits, with a reason code and no free text', g.type == 'grant' and g.amount == 5 and g.reason_code == 'promo' and w.balance == 4)
check('...and is audited', env['ts.audit.event'].search_count([('event_type', '=', 'wallet.grant'), ('workspace_id', '=', emp.id)]) == 1)
wm.ts_adjust(-2, 'correction')
check('an adjustment of either sign is possible', w.balance == 2)
check('a zero or unknown-reason grant is refused', raises(lambda: wm.ts_grant(0, 'promo')) and raises(lambda: wm.ts_grant(3, 'whatever')))
check('a zero adjustment is refused', raises(lambda: wm.ts_adjust(0, 'manual')))
check('balance_after follows the running sum', txns(emp)[0].balance_after == w.balance)

# ---- void -> exactly one refund (WAL-5)
check('only a platform manager may void an attempt', raises(lambda: at1.with_user(ordinary).action_void('duplicate')))
check('an unknown void reason is refused', raises(lambda: at1.with_user(mgr).action_void('because')))
check('voiding an attempt that is not finished is refused', raises(lambda: A.create(
    {'workspace_id': emp.id, 'instrument_id': plain.id, 'invitee_name': 'نیمه'}).action_accept(puser(), share=True).with_user(mgr).action_void('other')))
used_before = w.units_used
check('a manager voids a finished attempt', at1.with_user(mgr).action_void('duplicate') is True and at1.voided and at1.void_reason_code == 'duplicate'
      and at1.voided_by_id == mgr)
rf = txns(emp, 'refund')
check('...which writes one refund for what the debit took', len(rf) == 1 and rf.amount == 0 and rf.units == 1 and rf.idem_key == 'refund:%d' % at1.id and rf.reason_code == 'void')
check('...and the wallet shows one unit less', w.units_used == used_before - 1)
check('voiding again does nothing and refunds nothing more', at1.with_user(mgr).action_void('duplicate') is False and len(txns(emp, 'refund')) == 1)
check('the void is audited', env['ts.audit.event'].search_count([('event_type', '=', 'attempt.void'), ('workspace_id', '=', emp.id)]) == 1)
at2.with_user(mgr).action_void('technical')
r2 = txns(emp, 'refund').filtered(lambda t: t.attempt_id == at2)
check('voiding a paid-mode attempt gives the credit back, once', len(r2) == 1 and r2.amount == 1 and not r2.free)

# ---- reconcile, from the attempts (G14)
mine = (emp.id, edu.id)
env.flush_all()
bad = [p for p in Wal._reconcile() if p[1] in mine]
check('reconcile finds nothing wrong on consistent data', not bad, str(bad))
env.cr.execute("DELETE FROM ts_wallet_txn WHERE idem_key = %s", ['usage:%d' % bt.id])
env.invalidate_all()
bad = [p for p in Wal._reconcile() if p[1] in mine]
check('reconcile detects an attempt that lost its debit', any(p[0] == 'attempt' and p[2] == bt.id for p in bad), str(bad))
n = Wal._cron_reconcile()
check('the cron writes an error audit event for it', n >= 1 and env['ts.audit.event'].search_count(
    [('event_type', '=', 'wallet.reconcile_mismatch'), ('workspace_id', '=', edu.id), ('outcome', '=', 'error')]) >= 1)
Wal._migrate_m6()
bad = [p for p in Wal._reconcile() if p[1] in mine]
check('the M6 migration restores the missing debit, once', not bad and len(txns(edu, 'debit_usage')) == 1, str(bad))
Wal._migrate_m6()
check('...and running it again changes nothing', len(txns(edu, 'debit_usage')) == 1 and len(txns(emp, 'debit_usage')) == 2)
env.cr.execute("UPDATE ts_wallet SET balance = balance + 7 WHERE id = %s", [w.id])
env.invalidate_all()
bad = [p for p in Wal._reconcile() if p[1] in mine]
check('reconcile detects a balance that differs from the ledger', any(p[0] == 'balance' for p in bad), str(bad))
env.cr.execute("UPDATE ts_wallet SET balance = balance - 7 WHERE id = %s", [w.id])
env.invalidate_all()

# ---- numbers for the page
months = w.usage_by_month()
check('usage per month lists the current month with its units', bool(months) and sum(months[0][2].values()) == w.current_month_units())
check('this month\'s usage equals debits minus refunds', w.current_month_units() == 0, str(w.current_month_units()))
check('the credits menu item needs credits:read', any(i['key'] == 'credits' and i['perm'] == 'credits:read'
                                                     for i in __import__('odoo.addons.ts_panel.controllers.base', fromlist=['MENU']).MENU))

passed = sum(1 for _n_, ok in results if ok)
print('SUMMARY %d/%d passed' % (passed, len(results)))
env.cr.rollback()
