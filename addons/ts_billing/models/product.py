"""Products of the catalog (docs/clinic/04_billing_brief.md section 2): one service product per published instrument and per
published battery, plus the top-up product. Prices are entered in Rial and must be multiples of 10."""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ts_instrument_id = fields.Many2one('ts.instrument', 'سنجهٔ استعدادیاب', readonly=True, index=True, copy=False,
                                       ondelete='set null')
    ts_battery_id = fields.Many2one('ts.battery', 'مجموعهٔ استعدادیاب', readonly=True, index=True, copy=False,
                                    ondelete='set null')
    ts_topup = fields.Boolean('اعتبار پیش‌پرداخت استعدادیاب', copy=False,
                              help='محصول فاکتورهای شارژ اعتبار پنل؛ از راه پنل فروخته نمی‌شود.')

    @api.constrains('list_price', 'ts_instrument_id', 'ts_battery_id', 'ts_topup')
    def _check_ts_rial_price(self):
        for t in self:
            if (t.ts_instrument_id or t.ts_battery_id or t.ts_topup) and round(t.list_price or 0) % 10:
                raise ValidationError('قیمت به ریال و مضربی از ۱۰ است (مثلاً ۱۲۰۰۰۰۰).')
            if (t.ts_instrument_id or t.ts_battery_id or t.ts_topup) and (t.list_price or 0) != round(t.list_price or 0):
                raise ValidationError('قیمت ریالی اعشار ندارد.')


class AccountMoveLineTopup(models.Model):
    _inherit = 'account.move.line'

    @api.constrains('price_unit', 'product_id')
    def _check_ts_topup_price(self):
        for line in self:
            if line.product_id.product_tmpl_id.ts_topup and round(line.price_unit or 0) % 10:
                raise ValidationError('مبلغ شارژ اعتبار به ریال و مضربی از ۱۰ است.')
