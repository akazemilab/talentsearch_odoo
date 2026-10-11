"""Per-panel catalog grants (docs/clinic/01_architecture.md 2.2).

catalog_mode 'purpose' keeps today's behaviour (everything the panel purpose allows); 'granted' limits the
panel to its allow-lists. A member restriction, when set, narrows further. Every reader goes through sudo:
portal members have no ACL on instruments or batteries."""
from odoo import api, fields, models
from odoo.exceptions import UserError

from .battery import PURPOSE_FLAG

CATALOG_MODES = [('purpose', 'بر اساس هدف پنل'), ('granted', 'فقط موارد مجاز')]
WS_CATALOG_FIELDS = ('catalog_mode', 'catalog_instrument_ids', 'catalog_battery_ids')
MEMBER_CATALOG_FIELDS = ('restrict_instrument_ids', 'restrict_battery_ids', 'catalog_restricted')
NOT_IN_CATALOG = 'این سنجه برای این پنل فعال نیست.'
BATTERY_NOT_IN_CATALOG = 'این مجموعه برای این پنل فعال نیست.'


class TsWorkspace(models.Model):
    _inherit = 'ts.workspace'

    catalog_mode = fields.Selection(CATALOG_MODES, 'کاتالوگ پنل', default='purpose', required=True, tracking=True,
                                    help='«بر اساس هدف پنل»: همهٔ سنجه‌هایی که هدف پنل اجازه می‌دهد. '
                                         '«فقط موارد مجاز»: فقط سنجه‌ها و باتری‌های فهرست‌شده در این پنل.')
    catalog_instrument_ids = fields.Many2many('ts.instrument', 'ts_workspace_catalog_instrument_rel',
                                              'workspace_id', 'instrument_id', 'سنجه‌های مجاز')
    catalog_battery_ids = fields.Many2many('ts.battery', 'ts_workspace_catalog_battery_rel',
                                           'workspace_id', 'battery_id', 'باتری‌های مجاز')

    def ts_catalog_instruments(self):
        """The panel catalog of instruments, before any member restriction (sudo)."""
        self.ensure_one()
        ws = self.sudo()
        Inst = self.env['ts.instrument'].sudo()
        if ws.catalog_mode == 'granted':
            dom = [('id', 'in', ws.catalog_instrument_ids.ids), ('state', '=', 'published')]
            if ws.purpose == 'employment':
                dom.append(('purpose', '=', 'employment'))
            return Inst.search(dom)
        dom = [('state', '=', 'published')]       # mode 'purpose': the ts_org rule (TsWorkspaceMember.allowed_instruments)
        if ws.purpose == 'employment':
            dom.append(('purpose', '=', 'employment'))
        elif ws.purpose == 'education':
            dom.append(('code', '=', 'TALENT-INV-15'))
        return Inst.search(dom)

    def ts_catalog_batteries(self):
        """The panel catalog of batteries, before any member restriction (sudo)."""
        self.ensure_one()
        ws = self.sudo()
        B = self.env['ts.battery'].sudo()
        flag = PURPOSE_FLAG.get(ws.purpose)
        if not flag:
            return B
        dom = [('state', '=', 'published'), (flag, '=', True), ('has_retired', '=', False)]
        if ws.catalog_mode == 'granted':
            dom.append(('id', 'in', ws.catalog_battery_ids.ids))
        return B.search(dom)

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

    # Clinic phase 3: the panel's owner/admin/director chooses from the panel member page. Ticked = the two lists below
    # are exact (an empty list then means none of that kind, so a counselor can be limited to batteries only).
    # Not ticked = the Phase 2 rule: an empty list inherits the panel catalog.
    catalog_restricted = fields.Boolean(
        'فهرست مجاز دقیق', help='روشن: این عضو فقط به موارد دو فهرست زیر دعوت می‌کند (فهرست خالی یعنی هیچ). '
                                 'خاموش: فهرست خالی یعنی همهٔ موارد کاتالوگ پنل.')

    restrict_instrument_ids = fields.Many2many(
        'ts.instrument', 'ts_member_restrict_instrument_rel', 'member_id', 'instrument_id', 'محدود به سنجه‌ها',
        help='خالی: همهٔ سنجه‌های کاتالوگ پنل. پر: این عضو فقط به همین سنجه‌ها دعوت می‌کند.')
    restrict_battery_ids = fields.Many2many(
        'ts.battery', 'ts_member_restrict_battery_rel', 'member_id', 'battery_id', 'محدود به باتری‌ها',
        help='خالی: همهٔ باتری‌های کاتالوگ پنل. پر: این عضو فقط به همین باتری‌ها دعوت می‌کند.')

    def _ts_log_restrict(self, changed):
        by = self.env['ts.workspace.member'].browse(self.env.context.get('ts_catalog_by') or [])
        for m in self:
            self.env['ts.audit.event'].sudo().log(
                'catalog.change', m, workspace=m.workspace_id, member=by or None, user=m.user_id.id, fields=sorted(changed),
                restricted=bool(m.catalog_restricted), instruments=len(m.restrict_instrument_ids),
                batteries=len(m.restrict_battery_ids))

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
            res = ws.ts_catalog_instruments()
        else:
            res = super().allowed_instruments()
        if me.catalog_restricted or me.restrict_instrument_ids:
            res = Inst.search([('id', 'in', res.ids), ('id', 'in', me.restrict_instrument_ids.ids)])
        return res

    def allowed_batteries(self):
        """Published batteries flagged for the panel purpose (and without a retired instrument); mode 'granted'
        keeps only the panel allow-list; a member restriction intersects."""
        self.ensure_one()
        me = self.sudo()
        res = me.workspace_id.ts_catalog_batteries()
        if res and (me.catalog_restricted or me.restrict_battery_ids):
            res = res.filtered(lambda b: b in me.restrict_battery_ids)
        return res

    def ts_set_catalog(self, by, restricted, instrument_ids=(), battery_ids=()):
        """The panel member page (catalog:assign): «همهٔ موارد پنل» (restricted=False, both lists cleared) or an exact
        checklist of the panel's own catalog. Ids outside the panel catalog are refused; one catalog.change audit row
        (counts only) is written by write(). Returns True when something changed."""
        self.ensure_one()
        if not by.has_perm('catalog:assign') or by.workspace_id != self.workspace_id:
            raise UserError('تعیین سنجه‌های مجاز اعضا با مالک، هماهنگ‌کننده یا مدیر پنل است.')
        ws = self.sudo().workspace_id
        if restricted:
            insts = ws.ts_catalog_instruments()
            bats = ws.ts_catalog_batteries()
            want_i = {int(i) for i in instrument_ids}
            want_b = {int(b) for b in battery_ids}
            if not want_i <= set(insts.ids) or not want_b <= set(bats.ids):
                raise UserError('فقط موارد کاتالوگ همین پنل را می‌توان انتخاب کرد.')
            if not want_i and not want_b:
                raise UserError('دست‌کم یک سنجه یا مجموعه را انتخاب کنید، یا «همهٔ موارد پنل» را برگزینید.')
            vals = {'catalog_restricted': True, 'restrict_instrument_ids': [fields.Command.set(sorted(want_i))],
                    'restrict_battery_ids': [fields.Command.set(sorted(want_b))]}
            same = (self.catalog_restricted and set(self.restrict_instrument_ids.ids) == want_i
                    and set(self.restrict_battery_ids.ids) == want_b)
        else:
            vals = {'catalog_restricted': False, 'restrict_instrument_ids': [fields.Command.clear()],
                    'restrict_battery_ids': [fields.Command.clear()]}
            same = not (self.catalog_restricted or self.restrict_instrument_ids or self.restrict_battery_ids)
        if same:
            return False
        self.sudo().with_context(ts_catalog_by=by.id).write(vals)
        return True


class TsAssignment(models.Model):
    _inherit = 'ts.assignment'

    @api.constrains('instrument_id', 'workspace_id')
    def _check_instrument_in_catalog(self):
        """Server-side grant check (mode 'granted' only; mode 'purpose' keeps ts_org's rule unchanged). A battery
        invitation is checked against the battery catalog instead (run.py, _check_battery)."""
        for a in self.sudo():
            ws = a.workspace_id
            if 'battery_id' in a._fields and a.battery_id:
                continue
            if ws.catalog_mode == 'granted' and a.instrument_id not in ws.catalog_instrument_ids:
                raise UserError(NOT_IN_CATALOG)
