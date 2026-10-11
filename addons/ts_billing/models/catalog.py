"""Catalog -> products (docs/clinic/04_billing_brief.md section 2).

`_ts_ensure_product()` gives every published instrument and battery one service product (created on publish, by the data
function on install/upgrade for every published record, and the product name follows a rename). The base price lives on the
product (`list_price`, Rial); the back office edits it through «قیمت پایه (ریال)» on the instrument and battery forms."""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def _product_vals(env, name, code, link_field, rec_id):
    categ = env.ref('ts_billing.product_category_instruments', raise_if_not_found=False)
    vals = {'name': name, 'type': 'service', 'sale_ok': True, 'purchase_ok': False, 'default_code': code,
            'list_price': 0, 'taxes_id': [fields.Command.clear()], 'supplier_taxes_id': [fields.Command.clear()],
            link_field: rec_id}
    if categ:
        vals['categ_id'] = categ.id
    return vals


class _TsProductMixin(models.AbstractModel):
    _name = 'ts.billing.product.mixin'
    _description = 'Talent Search: a catalog record with one product'
    _ts_link_field = None       # ts_instrument_id | ts_battery_id on product.template

    def _ts_ensure_product(self):
        """Create the product of every published record that has none; sync name and code. Idempotent."""
        P = self.env['product.product'].sudo().with_context(active_test=False)
        n = 0
        for rec in self.sudo():
            if rec.product_id:
                tmpl = rec.product_id.product_tmpl_id
                vals = {}
                if tmpl.name != rec.name:
                    vals['name'] = rec.name
                if tmpl.default_code != rec.code:
                    vals['default_code'] = rec.code
                if vals:
                    tmpl.write(vals)
                continue
            if rec.state != 'published':
                continue
            prod = P.search([(self._ts_link_field, '=', rec.id)], limit=1)
            if not prod:
                prod = P.create(_product_vals(self.env, rec.name, rec.code, self._ts_link_field, rec.id))
                n += 1
            rec.with_context(ts_billing_product_sync=True).write({'product_id': prod.id})
        return n

    @api.model
    def _ts_sync_all_products(self):
        recs = self.sudo().with_context(active_test=False).search(['|', ('state', '=', 'published'), ('product_id', '!=', False)])
        n = recs._ts_ensure_product()
        _logger.info('ts_billing: %s products synced (%d created)', self._name, n)
        return n

    def action_ts_open_product(self):
        self.ensure_one()
        if not self.product_id:
            self._ts_ensure_product()
        return {'type': 'ir.actions.act_window', 'res_model': 'product.template', 'view_mode': 'form',
                'res_id': self.product_id.product_tmpl_id.id, 'target': 'current'}


class TsInstrumentProduct(models.Model):
    _name = 'ts.instrument'
    _inherit = ['ts.instrument', 'ts.billing.product.mixin']
    _ts_link_field = 'ts_instrument_id'

    product_id = fields.Many2one('product.product', 'محصول', copy=False, readonly=True, ondelete='set null', index=True)
    ts_list_price = fields.Float('قیمت پایه (ریال)', related='product_id.list_price', readonly=False, digits=(16, 0),
                                 help='قیمت فهرست، به ریال و مضربی از ۱۰. فهرست قیمت ویژهٔ یک مرکز روی طرف حساب آن مرکز تعیین می‌شود.')

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs.filtered(lambda r: r.state == 'published')._ts_ensure_product()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('ts_billing_product_sync') and ('state' in vals or 'name' in vals or 'code' in vals):
            self._ts_ensure_product()
        return res


class TsBatteryProduct(models.Model):
    _name = 'ts.battery'
    _inherit = ['ts.battery', 'ts.billing.product.mixin']
    _ts_link_field = 'ts_battery_id'

    ts_list_price = fields.Float('قیمت پایه (ریال)', related='product_id.list_price', readonly=False, digits=(16, 0),
                                 help='قیمت فهرست کل مجموعه، به ریال و مضربی از ۱۰.')

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs.filtered(lambda r: r.state == 'published')._ts_ensure_product()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('ts_billing_product_sync') and ('state' in vals or 'name' in vals or 'code' in vals):
            self._ts_ensure_product()
        return res
