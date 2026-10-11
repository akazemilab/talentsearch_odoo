"""Workspace and member fields of prepaid billing (docs/clinic/04_billing_brief.md sections 2, 3, 5.4, 6)."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..tools import CAPPED_ROLES, fa_num, fmt_toman, rial_int, round10

BILLING_MODES = [('free', 'رایگان'), ('prepaid', 'پیش‌پرداخت')]


class TsWorkspaceBilling(models.Model):
    _inherit = 'ts.workspace'

    billing_mode = fields.Selection(BILLING_MODES, 'شیوهٔ پرداخت', default='free', required=True, tracking=True,
                                    help='«پیش‌پرداخت»: هر دعوت هزینهٔ سنجه یا مجموعه را از اعتبار پنل رزرو می‌کند و با تکمیل '
                                         'آن کسر می‌شود. دعوت‌های باز پیش از تغییر، رایگان می‌مانند.')
    ts_invoice_count = fields.Integer('فاکتورها', compute='_compute_ts_invoice_count')

    def _compute_ts_invoice_count(self):
        Move = self.env['account.move'].sudo()
        for ws in self:
            ws.ts_invoice_count = Move.search_count([('ts_workspace_id', '=', ws.id)]) if ws.id else 0

    # ------------------------------------------------------------------ prices
    def ts_is_prepaid(self):
        self.ensure_one()
        return self.sudo().billing_mode == 'prepaid'

    def ts_price(self, product):
        """Price of `product` for this panel in Rial: the institution's own pricelist when the super admin set one on its
        partner, else the list price; rounded to a multiple of 10 Rial (an integer toman)."""
        self.ensure_one()
        if not product:
            return 0
        ws = self.sudo()
        product = product.sudo()
        partner = ws.partner_id.commercial_partner_id
        # only an explicit pricelist: the computed property falls back to "the first pricelist", which would hand one
        # institution's special prices to every other panel
        pl = partner.specific_property_product_pricelist or ws.partner_id.specific_property_product_pricelist
        if pl:
            price = pl._get_product_price(product, 1.0)
            company = ws.company_id or self.env.company
            if pl.currency_id and pl.currency_id != company.currency_id:
                price = pl.currency_id._convert(price, company.currency_id, company, fields.Date.today())
        else:
            price = product.list_price
        return round10(price)

    def ts_item_price(self, instrument=None, battery=None):
        """Price of an invitation item (battery wins) for this panel; 0 when the panel is free or the item has no product."""
        self.ensure_one()
        if not self.ts_is_prepaid():
            return 0
        product = (battery.sudo().product_id if battery else instrument.sudo().product_id if instrument else False)
        return self.ts_price(product) if product else 0

    def ts_toman(self, rial):
        return fmt_toman(rial)

    def ts_fa_num(self, n):
        return fa_num(n)

    # ------------------------------------------------------------------ mode change (super admin, audited)
    def write(self, vals):
        old = {ws.id: ws.billing_mode for ws in self} if 'billing_mode' in vals else {}
        if old and not (self.env.su or self.env.user.has_group('ts_core.group_ts_manager')):
            raise AccessError('شیوهٔ پرداخت پنل را فقط مدیر پلتفرم تغییر می‌دهد.')
        res = super().write(vals)
        for ws in self:
            if ws.id in old and old[ws.id] != ws.billing_mode:
                self.env['ts.audit.event'].sudo().log('billing.mode', ws, workspace=ws, old=old[ws.id], new=ws.billing_mode)
                if ws.billing_mode == 'prepaid':
                    self.env['ts.wallet']._for_workspace(ws)
        return res

    # ------------------------------------------------------------------ back office: invoices
    def _ts_topup_product(self):
        return self.env.ref('ts_billing.product_topup', raise_if_not_found=False)

    def action_ts_topup_invoice(self):
        """«صدور فاکتور اعتبار»: a new customer invoice for the panel's institution with one top-up line (price typed)."""
        self.ensure_one()
        if not self.ts_is_prepaid():
            raise UserError('فاکتور اعتبار فقط برای پنل پیش‌پرداخت صادر می‌شود.')
        prod = self._ts_topup_product()
        line = {'product_id': prod.id, 'quantity': 1, 'price_unit': 0, 'tax_ids': [fields.Command.clear()]} if prod else {}
        ctx = {'default_move_type': 'out_invoice', 'default_partner_id': self.partner_id.id,
               'default_ts_workspace_id': self.id}
        if line:
            ctx['default_invoice_line_ids'] = [fields.Command.create(line)]
        return {'type': 'ir.actions.act_window', 'name': 'فاکتور اعتبار', 'res_model': 'account.move', 'view_mode': 'form',
                'views': [(self.env.ref('account.view_move_form').id, 'form')], 'target': 'current', 'context': ctx}

    def action_ts_invoices(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'فاکتورهای اعتبار', 'res_model': 'account.move',
                'view_mode': 'list,form', 'domain': [('ts_workspace_id', '=', self.id)],
                'context': {'default_move_type': 'out_invoice', 'default_partner_id': self.partner_id.id,
                            'default_ts_workspace_id': self.id}}

    def action_ts_wallet(self):
        self.ensure_one()
        w = self.env['ts.wallet']._for_workspace(self)
        return {'type': 'ir.actions.act_window', 'name': 'کیف اعتبار', 'res_model': 'ts.wallet', 'view_mode': 'form',
                'res_id': w.id}

    def ts_invoices(self):
        """Posted customer invoices of the panel (newest first), for the credits page."""
        self.ensure_one()
        return self.env['account.move'].sudo().search([('ts_workspace_id', '=', self.id), ('move_type', '=', 'out_invoice'),
                                                        ('state', '=', 'posted')], order='invoice_date desc, id desc', limit=50)


class TsWorkspaceMemberBilling(models.Model):
    _inherit = 'ts.workspace.member'

    currency_id = fields.Many2one('res.currency', related='workspace_id.company_id.currency_id', string='ارز')
    monthly_cap = fields.Monetary('سقف ماهانه', currency_field='currency_id', default=0,
                                  help='سقف هزینهٔ دعوت‌های این عضو در هر ماه شمسی (ریال). ۰ = بدون سقف. فقط برای مشاور، '
                                       'مشاور مرکز، مدیر استخدام و بازبین.')

    def ts_is_capped_role(self):
        self.ensure_one()
        return self.sudo().role in CAPPED_ROLES

    def ts_set_cap(self, by, amount):
        """Owner / admin / director / hr_admin of the same panel (credits:manage). Rial, multiple of 10, 0 = no cap."""
        self.ensure_one()
        if not by.has_perm('credits:manage') or by.workspace_id != self.workspace_id:
            raise UserError('سقف ماهانه را مالک، هماهنگ‌کننده یا مدیر پنل تعیین می‌کند.')
        if not self.ts_is_capped_role():
            raise UserError('برای این نقش سقف ماهانه تعیین نمی‌شود.')
        amount = rial_int(amount)
        if amount < 0 or amount % 10:
            raise UserError('سقف را به ریال و مضربی از ۱۰ بنویسید؛ ۰ یعنی بدون سقف.')
        if rial_int(self.monthly_cap) == amount:
            return False
        self.sudo().with_context(ts_cap_by=by.id).write({'monthly_cap': amount})
        return True

    def write(self, vals):
        old = {m.id: rial_int(m.monthly_cap) for m in self} if 'monthly_cap' in vals else {}
        res = super().write(vals)
        if old:
            by = self.env['ts.workspace.member'].sudo().browse(self.env.context.get('ts_cap_by') or [])
            for m in self:
                new = rial_int(m.monthly_cap)
                if old.get(m.id) != new:      # panel page (by = the deciding member) or back office (by = none)
                    self.env['ts.audit.event'].sudo().log('credit.cap_change', m, workspace=m.workspace_id, member=by or None,
                                                          target=m.id, old=old.get(m.id), new=new)
        return res

    @api.constrains('monthly_cap')
    def _check_monthly_cap(self):
        for m in self:
            if m.monthly_cap < 0 or rial_int(m.monthly_cap) % 10:
                raise ValidationError('سقف ماهانه به ریال، مثبت و مضربی از ۱۰ است.')

    # ------------------------------------------------------------------ numbers for the pages (sudo after the caller's checks)
    def ts_bill_state(self):
        """What the pages of this member show about money; None for a free panel.
        {available, held, month, can_read, can_manage, cap, spent, capped}"""
        self.ensure_one()
        me = self.sudo()
        ws = me.workspace_id
        if not ws.ts_is_prepaid():
            return None
        w = self.env['ts.wallet']._for_workspace(ws)
        can_read = me.has_perm('credits:read')
        capped = me.ts_is_capped_role() and me.monthly_cap > 0
        out = {'can_read': can_read, 'can_manage': me.has_perm('credits:manage'), 'capped': capped,
               'cap': rial_int(me.monthly_cap), 'spent': w.ts_month_spend(me) if me.ts_is_capped_role() else 0,
               'available': w.ts_available(), 'held': w.ts_held(), 'month': w.ts_month_spend() if can_read else 0}
        out['cap_left'] = max(out['cap'] - out['spent'], 0) if capped else None
        out['cap_pct'] = min(100, int(100.0 * out['spent'] / out['cap'])) if capped and out['cap'] else 0
        return out

    def ts_bill_prices(self):
        """Prices of the items this member may invite (prepaid panels): {'inst': {id: rial}, 'bat': {id: rial},
        'ok_inst': {id: bool}, 'ok_bat': {id: bool}, 'available': rial}; None for a free panel. An item is «ok» when the
        panel can hold its price and the member's cap allows it (the server decides again at creation)."""
        self.ensure_one()
        st = self.ts_bill_state()
        if st is None:
            return None
        me = self.sudo()
        ws = me.workspace_id
        inst = {i.id: ws.ts_item_price(instrument=i) for i in me.allowed_instruments()}
        bat = {b.id: ws.ts_item_price(battery=b) for b in me.allowed_batteries()} if hasattr(me, 'allowed_batteries') else {}
        room = st['available']
        if st['capped']:
            room = min(room, st['cap'] - st['spent'])

        def ok(price):
            return price <= room
        return {'inst': inst, 'bat': bat, 'ok_inst': {k: ok(v) for k, v in inst.items()},
                'ok_bat': {k: ok(v) for k, v in bat.items()}, 'available': st['available'], 'state': st}
