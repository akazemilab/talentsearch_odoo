"""Hold at invitation, release when an invitation ends unused (docs/clinic/04_billing_brief.md sections 3, 5.1, 5.3).

The hold runs in `create`, after ts_battery's catalog check (a constraint inside super().create), in the same transaction and
under the wallet row lock. A refusal rolls back the invitation itself (savepoint), writes a `credit.refused` audit row and
raises the panel text, so the page shows it as its usual error."""
from odoo import api, fields, models

from .wallet import CreditRefused

NO_HOLD_CHANNELS = ('self_share', 'import')


class TsAssignmentBilling(models.Model):
    _inherit = 'ts.assignment'

    currency_id = fields.Many2one('res.currency', related='workspace_id.company_id.currency_id', string='ارز')
    price_held = fields.Monetary('هزینهٔ رزروشده', currency_field='currency_id', readonly=True, copy=False, default=0)
    priced_product_id = fields.Many2one('product.product', 'محصول قیمت‌گذاری‌شده', readonly=True, copy=False,
                                        ondelete='set null')

    @api.model_create_multi
    def create(self, vals_list):
        WS = self.env['ts.workspace'].sudo()
        if not any(WS.browse(v['workspace_id']).billing_mode == 'prepaid' for v in vals_list if v.get('workspace_id')):
            return super().create(vals_list)
        try:
            with self.env.cr.savepoint():
                recs = super().create(vals_list)
                for a in recs.sudo():
                    a._ts_billing_hold()
        except CreditRefused as e:
            e.ts_log(self.env)
            raise
        return recs

    def _ts_billing_member(self):
        """The inviting member (invited_by in this panel), else the responsible member."""
        self.ensure_one()
        M = self.env['ts.workspace.member'].sudo()
        m = M.search([('workspace_id', '=', self.workspace_id.id), ('user_id', '=', self.invited_by_id.id),
                      ('active', '=', True)], limit=1) if self.invited_by_id else M
        return m or self.responsible_id

    def _ts_billing_product(self):
        self.ensure_one()
        return self.battery_id.product_id if self.battery_id else self.instrument_id.product_id

    def _ts_billing_hold(self):
        """Hold the price of one new invitation of a prepaid panel (no row when the price is 0)."""
        self.ensure_one()
        ws = self.workspace_id
        if not ws.ts_is_prepaid() or self.channel in NO_HOLD_CHANNELS or self.attempt_id:
            return False
        product = self._ts_billing_product()
        price = ws.ts_price(product) if product else 0
        if price <= 0:
            return False
        return self.env['ts.wallet']._for_workspace(ws).ts_hold(self, price, self._ts_billing_member(), product)

    def _ts_billing_release(self, reason):
        for a in self.sudo().filtered(lambda r: r.price_held > 0):
            self.env['ts.wallet']._for_workspace(a.workspace_id).ts_release(a, reason)

    # ------------------------------------------------------------------ 5.3 release
    def action_withdraw(self):
        res = super().action_withdraw()
        self._ts_billing_release('withdraw')
        return res

    def action_decline(self, user):
        res = super().action_decline(user)
        self._ts_billing_release('decline')
        return res

    @api.model
    def _cron_release_expired_holds(self):
        """Daily: holds of invitations never accepted whose link has expired. An accepted invitation is never released here."""
        self.env.flush_all()
        self.env.cr.execute("SELECT assignment_id FROM ts_wallet_txn WHERE type = 'release' AND assignment_id IS NOT NULL")
        released = {r[0] for r in self.env.cr.fetchall()}
        rows = self.sudo().search([('price_held', '>', 0), ('user_id', '=', False)])
        n = 0
        for a in rows:
            if a.id in released or a.invite_state() != 'expired':
                continue
            if self.env['ts.wallet']._for_workspace(a.workspace_id).ts_release(a, 'expiry'):
                n += 1
        return n


class TsAttemptVoidText(models.Model):
    _inherit = 'ts.attempt'

    def ts_void_refund(self):
        """What a void of this attempt gives back (the void dialog shows it): exactly its debit. For a battery the first
        attempt to finish carried the whole price, every other attempt 0."""
        self.ensure_one()
        debit = self.env['ts.wallet.txn'].sudo().search([('idem_key', '=', 'usage:%d' % self.id)], limit=1)
        return -debit.amount if debit else 0
