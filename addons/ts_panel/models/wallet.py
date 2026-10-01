"""Credit wallet and ledger (S11: WAL-1, WAL-2, WAL-3, WAL-5, WAL-6, PLT-4, G14; 04_data_model.md 3.5).

One wallet per panel. Every completed panel attempt writes one `debit_usage` row (idempotent on `usage:<attempt id>`).
While `ts_panel.credit_mode` is `free` the row carries `amount = 0` and nothing is ever blocked; the paid phase
(purchase, expiry lots, gateway) is not built. Ledger rows are append-only, hold ids only and no free text.
"""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.ts_assessment.models.attempt import g2j

TXN_TYPES = [('grant', 'اعتبار هدیه'), ('purchase', 'خرید'), ('debit_usage', 'مصرف'), ('refund', 'بازگشت'),
             ('expire', 'انقضا'), ('adjust', 'اصلاح')]
REASONS = [('completion', 'تکمیل سنجه'), ('void', 'ابطال اجرا'), ('manual', 'دستی'), ('promo', 'تبلیغاتی'),
           ('correction', 'اصلاح')]
OPEN_STATES = ('invited', 'opened', 'accepted', 'in_progress')


class TsWallet(models.Model):
    _name = 'ts.wallet'
    _description = 'Talent Search panel wallet'

    workspace_id = fields.Many2one('ts.workspace', required=True, index=True, ondelete='restrict')
    txn_ids = fields.One2many('ts.wallet.txn', 'wallet_id')
    balance = fields.Integer('موجودی', compute='_compute_totals', store=True)
    units_used = fields.Integer('مصرف', compute='_compute_totals', store=True)
    low_threshold = fields.Integer('آستانهٔ هشدار', default=0)
    low_alert_sent_on = fields.Datetime(readonly=True)

    _ws_unique = models.Constraint('unique(workspace_id)', 'هر پنل فقط یک کیف اعتبار دارد.')

    @api.depends('txn_ids.amount', 'txn_ids.units', 'txn_ids.type')
    def _compute_totals(self):
        for w in self:
            w.balance = sum(w.txn_ids.mapped('amount'))
            w.units_used = (sum(w.txn_ids.filtered(lambda t: t.type == 'debit_usage').mapped('units'))
                            - sum(w.txn_ids.filtered(lambda t: t.type == 'refund').mapped('units')))

    # ------------------------------------------------------------------ access
    @api.model
    def _for_workspace(self, workspace):
        """The panel's wallet; created on first use."""
        W = self.sudo()
        w = W.search([('workspace_id', '=', workspace.id)], limit=1)
        if not w:
            with self.env.cr.savepoint():
                w = W.create({'workspace_id': workspace.id})
        return w

    @api.model
    def _free_mode(self):
        return (self.env['ir.config_parameter'].sudo().get_str('ts_panel.credit_mode') or 'free') == 'free'

    def committed(self):
        """Open invitations of the panel: what may still be consumed (no reservation is made)."""
        self.ensure_one()
        return self.env['ts.assignment'].sudo().search_count(
            [('workspace_id', '=', self.workspace_id.id), ('state', 'in', list(OPEN_STATES))])

    # ------------------------------------------------------------------ the only writers of the ledger
    def _post(self, type_, amount, units, idem_key, reason, attempt=None, actor=None, free=None):
        """Append one ledger row. Idempotent on `idem_key`: a second call returns the existing row.
        Locks the wallet row while it computes `balance_after` (same pattern as action_submit)."""
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM ts_wallet WHERE id = %s FOR UPDATE', [self.id])
        Txn = self.env['ts.wallet.txn'].sudo()
        old = Txn.search([('idem_key', '=', idem_key)], limit=1)
        if old:
            return old
        self.env.flush_all()
        self.env.cr.execute('SELECT COALESCE(SUM(amount), 0) FROM ts_wallet_txn WHERE wallet_id = %s', [self.id])
        before = self.env.cr.fetchone()[0]
        a = self.env['ts.assignment'].sudo().search([('attempt_id', '=', attempt.id)], limit=1) if attempt else False
        ev = self.env['ts.usage.event'].sudo().search([('attempt_id', '=', attempt.id)], limit=1) if attempt else False
        row = Txn.create({
            'wallet_id': self.id, 'type': type_, 'amount': amount, 'units': units, 'idem_key': idem_key,
            'reason_code': reason, 'attempt_id': attempt.id if attempt else False,
            'assignment_id': a.id if a else False, 'usage_event_id': ev.id if ev else False,
            'actor_id': (actor or self.env.user).id, 'balance_after': before + amount,
            'free': self._free_mode() if free is None else free,
        })
        return row

    def _debit_usage(self, attempt):
        """One debit per finished panel attempt. Free mode: amount 0, nothing blocks."""
        self.ensure_one()
        amount = 0 if self._free_mode() else -1
        return self._post('debit_usage', amount, 1, 'usage:%d' % attempt.id, 'completion', attempt)

    def _refund_usage(self, attempt, actor=None):
        """The refund of a voided attempt: once, for exactly what the debit took."""
        self.ensure_one()
        debit = self.env['ts.wallet.txn'].sudo().search([('idem_key', '=', 'usage:%d' % attempt.id)], limit=1)
        if not debit:
            return False
        return self._post('refund', -debit.amount, debit.units, 'refund:%d' % attempt.id, 'void', attempt, actor,
                          free=debit.free)

    def ts_grant(self, amount, reason, actor=None):
        """Back-office grant (WAL-6). `reason` is one of promo / manual / correction."""
        self.ensure_one()
        self._need_manager()
        amount = int(amount)
        if amount <= 0 or reason not in ('promo', 'manual', 'correction'):
            raise UserError('مقدار و دلیل اعتبار را درست وارد کنید.')
        row = self._post('grant', amount, 0, 'grant:%s' % uuid.uuid4().hex, reason, actor=actor, free=False)
        self.env['ts.audit.event'].log('wallet.grant', row, workspace=self.workspace_id, amount=amount, reason=reason)
        return row

    def ts_adjust(self, amount, reason, actor=None):
        """Back-office correction of any sign (WAL-6)."""
        self.ensure_one()
        self._need_manager()
        amount = int(amount)
        if not amount or reason not in ('manual', 'correction'):
            raise UserError('مقدار و دلیل اصلاح را درست وارد کنید.')
        row = self._post('adjust', amount, 0, 'adjust:%s' % uuid.uuid4().hex, reason, actor=actor, free=False)
        self.env['ts.audit.event'].log('wallet.adjust', row, workspace=self.workspace_id, amount=amount, reason=reason)
        return row

    def _need_manager(self):
        if not (self.env.su or self.env.user.has_group('ts_core.group_ts_manager')):
            raise AccessError('این کار فقط برای مدیر پلتفرم است.')

    # ------------------------------------------------------------------ reconcile (from the attempts, not from the events)
    @api.model
    def _reconcile(self):
        """-> list of (kind, workspace id, record id). Checks wallet.balance == sum(amount) and that every done, non-import
        panel attempt has exactly one usage event and one debit."""
        cr = self.env.cr
        self.env.flush_all()
        problems = []
        cr.execute("""SELECT w.id, w.workspace_id, w.balance, COALESCE(SUM(t.amount), 0)
                        FROM ts_wallet w LEFT JOIN ts_wallet_txn t ON t.wallet_id = w.id
                       GROUP BY w.id HAVING w.balance != COALESCE(SUM(t.amount), 0)""")
        for wid, ws, bal, total in cr.fetchall():
            problems.append(('balance', ws, wid))
        cr.execute("""SELECT a.id, a.workspace_id,
                             (SELECT count(*) FROM ts_usage_event u WHERE u.attempt_id = a.id),
                             (SELECT count(*) FROM ts_wallet_txn t WHERE t.attempt_id = a.id AND t.type = 'debit_usage')
                        FROM ts_attempt a
                       WHERE a.state = 'done' AND a.workspace_id IS NOT NULL AND a.source IS DISTINCT FROM 'import'""")
        for aid, ws, ev, deb in cr.fetchall():
            if ev != 1 or deb != 1:
                problems.append(('attempt', ws, aid))
        return problems

    @api.model
    def _cron_reconcile(self):
        problems = self._reconcile()
        Audit = self.env['ts.audit.event'].sudo()
        WS = self.env['ts.workspace'].sudo()
        for kind, ws, ref in problems:
            Audit.log('wallet.reconcile_mismatch', workspace=WS.browse(ws) if ws else None,
                      outcome='error', kind=kind, ref=ref)
        return len(problems)

    @api.model
    def _migrate_m6(self):
        """M6: one wallet per panel and one free debit per existing usage event. Idempotent."""
        for ws in self.env['ts.workspace'].sudo().search([]):
            self._for_workspace(ws)
        for ev in self.env['ts.usage.event'].sudo().search([('attempt_id.source', '!=', 'import')], order='id'):
            w = self._for_workspace(ev.workspace_id)
            w._post('debit_usage', 0, ev.units or 1, 'usage:%d' % ev.attempt_id.id, 'completion', ev.attempt_id,
                    free=True)
        return True

    # ------------------------------------------------------------------ numbers for the pages
    def usage_by_month(self, months=12):
        """[(jalali year, month, {instrument name: units})] newest first; units = debits minus refunds, summed per day in SQL."""
        self.ensure_one()
        cr = self.env.cr
        self.env.flush_all()
        cr.execute("""SELECT (timezone('Asia/Tehran', timezone('UTC', t.txn_date)))::date, COALESCE(i.name, '—'),
                             SUM(CASE WHEN t.type = 'debit_usage' THEN t.units WHEN t.type = 'refund' THEN -t.units ELSE 0 END)
                        FROM ts_wallet_txn t LEFT JOIN ts_instrument i ON i.id = t.instrument_id
                       WHERE t.wallet_id = %s AND t.type IN ('debit_usage', 'refund') AND t.txn_date >= now() - interval '400 days'
                       GROUP BY 1, 2""", [self.id])
        out = {}
        for day, name, units in cr.fetchall():
            y, m, _d = g2j(day.year, day.month, day.day)
            by = out.setdefault((y, m), {})
            by[name] = by.get(name, 0) + units
        return [(y, m, out[(y, m)]) for y, m in sorted(out, reverse=True)[:months]]

    def current_month_units(self):
        self.ensure_one()
        now = datetime.now(ZoneInfo('Asia/Tehran'))
        y, m, _d = g2j(now.year, now.month, now.day)
        for yy, mm, by in self.usage_by_month(2):
            if (yy, mm) == (y, m):
                return sum(by.values())
        return 0


class TsWalletTxn(models.Model):
    _name = 'ts.wallet.txn'
    _description = 'Talent Search wallet ledger row (append-only)'
    _order = 'id desc'

    wallet_id = fields.Many2one('ts.wallet', required=True, index=True, ondelete='restrict')
    workspace_id = fields.Many2one('ts.workspace', related='wallet_id.workspace_id', store=True, index=True)
    type = fields.Selection(TXN_TYPES, required=True, index=True)
    amount = fields.Integer(required=True)
    units = fields.Integer()
    free = fields.Boolean()
    idem_key = fields.Char(required=True, index=True)
    txn_date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    attempt_id = fields.Many2one('ts.attempt', ondelete='restrict', index=True)
    instrument_id = fields.Many2one('ts.instrument', related='attempt_id.instrument_id', store=True)
    usage_event_id = fields.Many2one('ts.usage.event', ondelete='set null')
    assignment_id = fields.Many2one('ts.assignment', ondelete='set null')
    actor_id = fields.Many2one('res.users', ondelete='set null')
    reason_code = fields.Selection(REASONS)
    balance_after = fields.Integer()

    _idem_unique = models.Constraint('unique(idem_key)', 'این ردیف دفتر پیش‌تر ثبت شده است.')

    def write(self, vals):
        raise UserError('ردیف‌های دفتر اعتبار قابل ویرایش نیستند.')

    def unlink(self):
        raise UserError('ردیف‌های دفتر اعتبار قابل حذف نیستند.')


class TsWorkspaceWallet(models.Model):
    _inherit = 'ts.workspace'

    def ts_wallet(self):
        self.ensure_one()
        return self.env['ts.wallet']._for_workspace(self)


class TsAttemptVoid(models.Model):
    _inherit = 'ts.attempt'

    voided = fields.Boolean('باطل‌شده', readonly=True, copy=False)
    voided_on = fields.Datetime(readonly=True, copy=False)
    voided_by_id = fields.Many2one('res.users', readonly=True, copy=False, ondelete='set null')
    void_reason_code = fields.Selection([('wrong_person', 'فرد اشتباه'), ('duplicate', 'تکراری'), ('technical', 'مشکل فنی'),
                                         ('other', 'سایر')], readonly=True, copy=False)

    def action_void(self, reason):
        """Platform manager only: the attempt is marked void and its usage refunded once."""
        self.ensure_one()
        if not (self.env.su or self.env.user.has_group('ts_core.group_ts_manager')):
            raise AccessError('ابطال اجرا فقط برای مدیر پلتفرم است.')
        if reason not in ('wrong_person', 'duplicate', 'technical', 'other'):
            raise UserError('دلیل ابطال را از فهرست برگزینید.')
        if self.voided:
            return False
        if self.state != 'done' or not self.workspace_id:
            raise UserError('فقط اجرای تکمیل‌شدهٔ یک پنل را می‌شود باطل کرد.')
        self.sudo().write({'voided': True, 'voided_on': fields.Datetime.now(), 'voided_by_id': self.env.uid,
                           'void_reason_code': reason})
        self.env['ts.wallet']._for_workspace(self.workspace_id)._refund_usage(self, self.env.user)
        self.env['ts.audit.event'].log('attempt.void', self, workspace=self.workspace_id, reason=reason)
        return True
