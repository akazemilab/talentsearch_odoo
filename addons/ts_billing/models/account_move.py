"""Top-up by customer invoice (docs/clinic/04_billing_brief.md section 5.4).

A posted customer invoice of a panel (`ts_workspace_id`) that is paid or in payment credits the panel wallet once
(`topup:<move id>`) with the untaxed amount of its top-up lines (or the whole untaxed amount when it has none). A posted, paid
(or reconciled-with-the-invoice) credit note of such an invoice takes back at most what that invoice credited
(`topup-rev:<credit note id>`). Triggers: write(), the paid hook, reversal, posting, and a daily cron as the safety net.
Invoices name the institution only: no participant data is ever written to an accounting record."""
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..tools import rial_int

_logger = logging.getLogger(__name__)
PAID = ('paid', 'in_payment')


class AccountMoveTopup(models.Model):
    _inherit = 'account.move'

    ts_workspace_id = fields.Many2one('ts.workspace', 'پنل استعدادیاب', index=True, copy=False, tracking=True,
                                      help='فاکتور شارژ اعتبار این پنل؛ با پرداخت، مبلغ اقلام «اعتبار پیش‌پرداخت» به اعتبار پنل افزوده می‌شود.')

    @api.constrains('ts_workspace_id', 'partner_id', 'move_type')
    def _check_ts_workspace(self):
        for m in self.filtered('ts_workspace_id'):
            if m.move_type not in ('out_invoice', 'out_refund'):
                raise ValidationError('فقط فاکتور فروش و برگشت از فروش به پنل وصل می‌شود.')
            if m.partner_id.commercial_partner_id != m.ts_workspace_id.sudo().partner_id.commercial_partner_id:
                raise ValidationError('طرف حساب فاکتور باید همان سازمانِ پنل «%s» باشد.' % m.ts_workspace_id.sudo().name)

    # ------------------------------------------------------------------ amounts
    def _ts_company_amount(self, amount):
        self.ensure_one()
        company = self.company_id
        if self.currency_id and self.currency_id != company.currency_id:
            amount = self.currency_id._convert(amount, company.currency_id, company, self.invoice_date or fields.Date.today())
        return rial_int(amount)

    def _ts_topup_amount(self):
        self.ensure_one()
        lines = self.invoice_line_ids.filtered(lambda l: l.product_id.product_tmpl_id.ts_topup)
        amount = sum(lines.mapped('price_subtotal')) if lines else self.amount_untaxed
        return self._ts_company_amount(amount)

    # ------------------------------------------------------------------ the sync (idempotent on the ledger keys)
    def _ts_billing_candidates(self):
        return self.sudo().filtered(lambda m: m.state == 'posted' and (
            (m.move_type == 'out_invoice' and m.ts_workspace_id)
            or (m.move_type == 'out_refund' and (m.ts_workspace_id or m.reversed_entry_id.ts_workspace_id))))

    def _ts_billing_sync(self):
        """Post the missing topup / topup-rev rows of these moves. Returns the number of rows written."""
        if self.env.context.get('ts_billing_no_sync'):
            return 0
        Txn = self.env['ts.wallet.txn'].sudo()
        Audit = self.env['ts.audit.event'].sudo()
        n = 0
        for m in self._ts_billing_candidates():
            if m.move_type == 'out_invoice':
                key = 'topup:%d' % m.id
                if m.payment_state not in PAID or Txn.search_count([('idem_key', '=', key)]):
                    continue
                amount = m._ts_topup_amount()
                if amount <= 0:
                    continue
                w = self.env['ts.wallet']._for_workspace(m.ts_workspace_id)
                w._post('topup', amount, 0, key, 'topup', free=False, move=m)
                Audit.log('credit.topup', m.ts_workspace_id, workspace=m.ts_workspace_id, amount=amount, move=m.name)
                w._ts_after_topup()
                n += 1
            else:
                key = 'topup-rev:%d' % m.id
                if m.payment_state not in PAID + ('reversed',) or Txn.search_count([('idem_key', '=', key)]):
                    continue
                orig = m.reversed_entry_id
                ws = m.ts_workspace_id or orig.ts_workspace_id
                topped = Txn.search([('idem_key', '=', 'topup:%d' % orig.id)], limit=1) if orig else Txn
                taken = rial_int(min(m._ts_company_amount(m.amount_untaxed), topped.amount)) if topped else 0
                if taken <= 0:
                    continue
                self.env['ts.wallet']._for_workspace(ws)._post('adjust', -taken, 0, key, 'topup_reversal', free=False, move=m)
                Audit.log('credit.topup_reversal', ws, workspace=ws, amount=taken, move=m.name, invoice=orig.name)
                n += 1
        return n

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('ts_billing_no_sync'):
            todo = self._ts_billing_candidates()
            if todo:
                todo._ts_billing_sync()
        return res

    def _invoice_paid_hook(self):
        parent = getattr(super(), '_invoice_paid_hook', None)
        res = parent() if parent else None
        self._ts_billing_sync()
        return res

    def _post(self, soft=True):
        res = super()._post(soft=soft)
        self._ts_billing_sync()
        return res

    def _reverse_moves(self, default_values_list=None, cancel=False):
        reverses = super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
        for r in reverses.sudo():
            if r.move_type == 'out_refund' and not r.ts_workspace_id and r.reversed_entry_id.ts_workspace_id:
                r.with_context(ts_billing_no_sync=True).write({'ts_workspace_id': r.reversed_entry_id.ts_workspace_id.id})
        reverses._ts_billing_sync()
        return reverses

    @api.model
    def _cron_sync_topups(self):
        """Daily safety net: posted invoices / credit notes of panels whose ledger row is missing."""
        moves = self.sudo().search([('state', '=', 'posted'), '|', ('ts_workspace_id', '!=', False),
                                    ('reversed_entry_id.ts_workspace_id', '!=', False),
                                    ('move_type', 'in', ('out_invoice', 'out_refund'))])
        n = moves._ts_billing_sync()
        if n:
            _logger.info('ts_billing: %d top-up row(s) written by the daily sync', n)
        return n


class AccountPaymentRegisterTopup(models.TransientModel):
    """The «Register payment» dialog: the paid state of an invoice is a stored compute, not a write of the move, and a payment
    without its own journal entry never reaches the reconcile hook; sync the invoices the dialog paid right after it."""
    _inherit = 'account.payment.register'

    def _create_payments(self):
        moves = self.line_ids.move_id
        res = super()._create_payments()
        moves.invalidate_recordset(['payment_state'])
        moves._ts_billing_sync()
        return res


class AccountPaymentTopup(models.Model):
    _inherit = 'account.payment'

    def _ts_billing_moves(self):
        moves = self.env['account.move']
        for f in ('invoice_ids', 'reconciled_invoice_ids'):
            if f in self._fields:
                moves |= self.mapped(f)
        return moves

    def action_post(self):
        res = super().action_post()
        self._ts_billing_moves()._ts_billing_sync()
        return res


class TsWalletAfterTopup(models.Model):
    _inherit = 'ts.wallet'

    def _ts_after_topup(self):
        """A top-up re-arms the low-balance alert."""
        self.ensure_one()
        if self.low_alert_sent_on and self.ts_available() >= self.low_threshold:
            self.sudo().low_alert_sent_on = False
