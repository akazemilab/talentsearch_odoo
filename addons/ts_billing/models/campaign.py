"""Group invitations of a prepaid panel (docs/clinic/04_billing_brief.md section 5.1).

* List launch: one clear refusal for the whole batch (available >= price x n is checked once), and all-or-nothing (the batch
  runs inside a savepoint; the first refused hold undoes every invitation of the batch).
* Open link: creating it needs available >= price x min(open_max or 10, 10). A join whose hold fails shows the participant a
  text without money words; the panel gets the credit.refused audit row and a low-balance notification."""
from odoo import api, models
from odoo.exceptions import UserError

from ..tools import credit_ask, fa_num, fmt_toman
from .wallet import INSUFFICIENT_BATCH, INSUFFICIENT_BATCH_ASK, CreditRefused

OPEN_LINK_FLOOR = 'برای پیوند باز دست‌کم %s اعتبار لازم است (هزینهٔ %s نفر).'
JOIN_FULL = 'ظرفیت این پیوند پر شده است. با مرکز مشاوره تماس بگیرید.'


class TsCampaignBilling(models.Model):
    _inherit = 'ts.campaign'

    def ts_unit_price(self):
        """Price of one invitation of this campaign for its panel (0 when free or unpriced)."""
        self.ensure_one()
        c = self.sudo()
        return c.workspace_id.ts_item_price(instrument=c.instrument_id, battery=c.battery_id)

    @api.model_create_multi
    def create(self, vals_list):
        WS = self.env['ts.workspace'].sudo()
        B = self.env['ts.battery'].sudo()
        Inst = self.env['ts.instrument'].sudo()
        for v in vals_list:
            if v.get('kind') != 'open_link' or not v.get('workspace_id'):
                continue
            ws = WS.browse(v['workspace_id'])
            if not ws.ts_is_prepaid():
                continue
            price = ws.ts_item_price(instrument=Inst.browse(v.get('instrument_id') or []),
                                     battery=B.browse(v.get('battery_id') or []))
            n = min(v.get('open_max') or 10, 10)
            need = price * n
            if need > 0:
                available = self.env['ts.wallet']._for_workspace(ws).ts_available()
                if available < need:
                    CreditRefused('', 'insufficient', ws, need).ts_log(self.env)
                    raise UserError(OPEN_LINK_FLOOR % (fmt_toman(need), fa_num(n)))
        return super().create(vals_list)

    def ts_launch(self, clients):
        self.ensure_one()
        ws = self.sudo().workspace_id
        if not ws.ts_is_prepaid():
            return super().ts_launch(clients)
        price = self.ts_unit_price()
        if price > 0 and self.kind == 'list' and self.state == 'open':
            mine = clients.sudo().filtered(lambda c: c.workspace_id == ws)
            to_invite, _skipped = self.ts_targets(mine, ws.id, self.instrument_id.id)
            total = price * len(to_invite)
            available = self.env['ts.wallet']._for_workspace(ws).ts_available()
            if total and available < total:
                creator = self.created_by_id
                if creator and not creator.sudo().has_perm('credits:read'):
                    text = INSUFFICIENT_BATCH_ASK % credit_ask(ws.purpose)
                else:
                    text = INSUFFICIENT_BATCH % (fa_num(len(to_invite)), fmt_toman(price), fmt_toman(total), fmt_toman(available))
                err = CreditRefused(text, 'insufficient', ws, total, creator)
                err.ts_log(self.env)
                self._ts_drop_if_empty()
                raise err
        try:
            with self.env.cr.savepoint():
                return super().ts_launch(clients)
        except CreditRefused as e:
            e.ts_log(self.env)          # the row written inside the batch was rolled back with it
            self._ts_drop_if_empty()
            raise

    def _ts_drop_if_empty(self):
        """The panel creates a list campaign and launches it in one request; a refused launch must not leave an empty,
        open campaign behind (the form keeps its draft, so nothing is typed twice)."""
        for c in self.sudo():
            if c.kind == 'list' and not c.assignment_ids:
                c.unlink()

    def ts_join(self, user, name):
        self.ensure_one()
        ws = self.sudo().workspace_id
        if not ws.ts_is_prepaid():
            return super().ts_join(user, name)
        try:
            with self.env.cr.savepoint():
                return super().ts_join(user, name)
        except CreditRefused as e:
            e.ts_log(self.env)
            self.env['ts.wallet']._for_workspace(ws)._ts_low_balance_notify(force=True)
            raise UserError(JOIN_FULL) from None
