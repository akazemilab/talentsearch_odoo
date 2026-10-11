"""Per-panel catalog grants (docs/clinic/01_architecture.md 2.2).

catalog_mode 'purpose' keeps today's behaviour (everything the panel purpose allows); 'granted' limits the
panel to its allow-lists. A member restriction, when set, narrows further. Every reader goes through sudo:
portal members have no ACL on instruments or batteries."""
from odoo import api, fields, models
from odoo.exceptions import UserError

from .battery import PURPOSE_FLAG

CATALOG_MODES = [('purpose', 'بر اساس هدف پنل'), ('granted', 'فقط موارد مجاز')]
WS_CATALOG_FIELDS = ('catalog_mode', 'catalog_instrument_ids', 'catalog_battery_ids')
MEMBER_CATALOG_FIELDS = ('restrict_instrument_ids', 'restrict_battery_ids')
NOT_IN_CATALOG = 'این سنجه برای این پنل فعال نیست.'


class TsWorkspace(models.Model):
    _inherit = 'ts.workspace'

    catalog_mode = fields.Selection(CATALOG_MODES, 'کاتالوگ پنل', default='purpose', required=True, tracking=True,
                                    help='«بر اساس هدف پنل»: همهٔ سنجه‌هایی که هدف پنل اجازه می‌دهد. '
                                         '«فقط موارد مجاز»: فقط سنجه‌ها و باتری‌های فهرست‌شده در این پنل.')
    catalog_instrument_ids = fields.Many2many('ts.instrument', 'ts_workspace_catalog_instrument_rel',
                                              'workspace_id', 'instrument_id', 'سنجه‌های مجاز')
    catalog_battery_ids = fields.Many2many('ts.battery', 'ts_workspace_catalog_battery_rel',
                                           'workspace_id', 'battery_id', 'باتری‌های مجاز')

    def _ts_log_catalog(self, changed):
        for ws in self:
            self.env['ts.audit.event'].sudo().log(
                'catalog.change', ws, workspace=ws, fields=sorted(changed), mode=ws.catalog_mode,
                instruments=len(ws.catalog_instrument_ids), batteries=len(ws.catalog_battery_ids))

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for ws, vals in zip(recs, vals_list):
            changed = [f for f in WS_CATALOG_FIELDS if vals.get(f) and not (f == 'catalog_mode' and vals[f] == 'purpose')]
            if changed:
                ws._ts_log_catalog(changed)
        return recs

    def write(self, vals):
        res = super().write(vals)
        changed = [f for f in WS_CATALOG_FIELDS if f in vals]
        if changed:
            self._ts_log_catalog(changed)
        return res


class TsWorkspaceMember(models.Model):
    _inherit = 'ts.workspace.member'

    restrict_instrument_ids = fields.Many2many(
        'ts.instrument', 'ts_member_restrict_instrument_rel', 'member_id', 'instrument_id', 'محدود به سنجه‌ها',
        help='خالی: همهٔ سنجه‌های کاتالوگ پنل. پر: این عضو فقط به همین سنجه‌ها دعوت می‌کند.')
    restrict_battery_ids = fields.Many2many(
        'ts.battery', 'ts_member_restrict_battery_rel', 'member_id', 'battery_id', 'محدود به باتری‌ها',
        help='خالی: همهٔ باتری‌های کاتالوگ پنل. پر: این عضو فقط به همین باتری‌ها دعوت می‌کند.')

    def _ts_log_restrict(self, changed):
        for m in self:
            self.env['ts.audit.event'].sudo().log(
                'catalog.change', m, workspace=m.workspace_id, user=m.user_id.id, fields=sorted(changed),
                instruments=len(m.restrict_instrument_ids), batteries=len(m.restrict_battery_ids))

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for m, vals in zip(recs, vals_list):
            changed = [f for f in MEMBER_CATALOG_FIELDS if vals.get(f)]
            if changed:
                m._ts_log_restrict(changed)
        return recs

    def write(self, vals):
        res = super().write(vals)
        changed = [f for f in MEMBER_CATALOG_FIELDS if f in vals]
        if changed:
            self._ts_log_restrict(changed)
        return res

    def allowed_instruments(self):
        """Mode 'purpose': the ts_org rule. Mode 'granted': published instruments of the panel allow-list
        (employment panels still only employment instruments). A member restriction intersects."""
        self.ensure_one()
        me = self.sudo()
        ws = me.workspace_id
        Inst = self.env['ts.instrument'].sudo()
        if ws.catalog_mode == 'granted':
            dom = [('id', 'in', ws.catalog_instrument_ids.ids), ('state', '=', 'published')]
            if ws.purpose == 'employment':
                dom.append(('purpose', '=', 'employment'))
            res = Inst.search(dom)
        else:
            res = super().allowed_instruments()
        if me.restrict_instrument_ids:
            res = Inst.search([('id', 'in', res.ids), ('id', 'in', me.restrict_instrument_ids.ids)])
        return res

    def allowed_batteries(self):
        """Published batteries flagged for the panel purpose (and without a retired instrument); mode 'granted'
        keeps only the panel allow-list; a member restriction intersects."""
        self.ensure_one()
        me = self.sudo()
        ws = me.workspace_id
        B = self.env['ts.battery'].sudo()
        flag = PURPOSE_FLAG.get(ws.purpose)
        if not flag:
            return B
        dom = [('state', '=', 'published'), (flag, '=', True), ('has_retired', '=', False)]
        if ws.catalog_mode == 'granted':
            dom.append(('id', 'in', ws.catalog_battery_ids.ids))
        if me.restrict_battery_ids:
            dom.append(('id', 'in', me.restrict_battery_ids.ids))
        return B.search(dom)


class TsAssignment(models.Model):
    _inherit = 'ts.assignment'

    @api.constrains('instrument_id', 'workspace_id')
    def _check_instrument_in_catalog(self):
        """Server-side grant check (mode 'granted' only; mode 'purpose' keeps ts_org's rule unchanged)."""
        for a in self.sudo():
            ws = a.workspace_id
            if ws.catalog_mode == 'granted' and a.instrument_id not in ws.catalog_instrument_ids:
                raise UserError(NOT_IN_CATALOG)
