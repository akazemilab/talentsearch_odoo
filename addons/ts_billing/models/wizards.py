"""Back-office dialogs: void of an attempt (shows what is given back) and grant / correction of a panel wallet (Rial)."""
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools import fmt_toman, rial_int

VOID_REASONS = [('wrong_person', 'فرد اشتباه'), ('duplicate', 'تکراری'), ('technical', 'مشکل فنی'), ('other', 'سایر')]


class TsAttemptVoidWizard(models.TransientModel):
    _name = 'ts.attempt.void.wizard'
    _description = 'ابطال اجرا'

    attempt_id = fields.Many2one('ts.attempt', required=True, ondelete='cascade')
    reason = fields.Selection(VOID_REASONS, 'دلیل ابطال', required=True, default='technical')
    refund_text = fields.Char('بازگشت اعتبار', compute='_compute_refund_text')

    @api.depends('attempt_id')
    def _compute_refund_text(self):
        for w in self:
            amount = w.attempt_id.ts_void_refund() if w.attempt_id else 0
            note = ''
            if w.attempt_id and w.attempt_id.sudo().assignment_id.battery_id:
                note = ' (در مجموعه، فقط نخستین سنجهٔ تکمیل‌شده هزینهٔ کل مجموعه را دارد؛ ابطال سنجه‌های دیگر چیزی برنمی‌گرداند.)'
            w.refund_text = 'بازگشت اعتبار: %s%s' % (fmt_toman(amount), note)

    def action_confirm(self):
        self.ensure_one()
        self.attempt_id.action_void(self.reason)
        return {'type': 'ir.actions.act_window_close'}


class TsAttemptVoidButton(models.Model):
    _inherit = 'ts.attempt'

    def action_ts_void_dialog(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'ابطال اجرا', 'res_model': 'ts.attempt.void.wizard',
                'view_mode': 'form', 'target': 'new', 'context': {'default_attempt_id': self.id}}


class TsWalletGrantWizard(models.TransientModel):
    _name = 'ts.wallet.grant.wizard'
    _description = 'اعتبار هدیه یا اصلاح کیف اعتبار'

    wallet_id = fields.Many2one('ts.wallet', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wallet_id.currency_id')
    kind = fields.Selection([('grant', 'اعتبار هدیه'), ('adjust', 'اصلاح')], 'نوع', required=True, default='grant')
    amount = fields.Monetary('مبلغ (ریال)', currency_field='currency_id', required=True,
                             help='به ریال و مضربی از ۱۰؛ برای اصلاح، مقدار منفی کم می‌کند.')
    reason = fields.Selection([('promo', 'تبلیغاتی'), ('manual', 'دستی'), ('correction', 'اصلاح')], 'دلیل', required=True,
                              default='manual')

    def action_confirm(self):
        self.ensure_one()
        amount = rial_int(self.amount)
        if self.kind == 'grant':
            self.wallet_id.ts_grant(amount, self.reason)
        else:
            if self.reason == 'promo':
                raise UserError('اصلاح با دلیل «دستی» یا «اصلاح» ثبت می‌شود.')
            self.wallet_id.ts_adjust(amount, self.reason)
        return {'type': 'ir.actions.act_window_close'}
