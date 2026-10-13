"""Clinic phase 6, slimmed in onb3: what stays of the counseling-center set-up guide.

The six-step list «راه‌اندازی مرکز» gave way to ts_onboard's «شروع کار» card (four steps that end with the first real
result) and its second card «پنل را کامل کنید» (identity on reports, colleagues, SMS name, credit, caps, licence). What
stays here, computed from real data on every page load:

* «بدون سقف بماند»: the owner / admin / director of a prepaid panel records once that the counselors work without a
  monthly cap (the «سقف‌ها» item of the second card counts it).
* A first-run card for a counselor (role `clinician`) whose own report identity is empty (no title), linking to their member
  page section «هویت شما در گزارش‌ها»; dismissible per member, and gone by itself once a title is saved.
* The time a counselor's catalog form was last saved (`ts_catalog_seen_on`).

Nothing here grants or checks access.
"""
from odoo import fields, models
from odoo.exceptions import UserError

from .brand import clean_line


class TsWorkspaceOnboarding(models.Model):
    _inherit = 'ts.workspace'

    ts_onb_nocap_on = fields.Datetime('«بدون سقف» برای مشاوران', readonly=True, copy=False,
                                      help='زمانی که مالک یا مدیر پنل گفت مشاوران بدون سقف ماهانه کار کنند.')

    def ts_onb_mark_nocap(self, by):
        """«بدون سقف بماند» (the «سقف‌ها» item of «پنل را کامل کنید»): the owner / admin / director (credits:manage) of this prepaid panel decides that the
        counselors work without a monthly cap. Returns True when it was not recorded yet."""
        self.ensure_one()
        if by.workspace_id != self or not by.has_perm('credits:manage') or not by.can_act():
            raise UserError('سقف ماهانه را مالک، هماهنگ‌کننده یا مدیر پنل تعیین می‌کند.')
        if not self.ts_is_prepaid():
            raise UserError('سقف ماهانه فقط در پنل پیش‌پرداخت معنا دارد.')
        if self.sudo().ts_onb_nocap_on:
            return False
        self.sudo().ts_onb_nocap_on = fields.Datetime.now()
        self.env['ts.audit.event'].sudo().log('onboarding.nocap', self, workspace=self, member=by)
        return True


class TsMemberOnboarding(models.Model):
    _inherit = 'ts.workspace.member'

    ts_onb_card_hidden_on = fields.Datetime('یادآوری هویت در گزارش‌ها بسته شد', readonly=True, copy=False)
    ts_catalog_seen_on = fields.Datetime('فهرست مجاز بررسی شد', readonly=True, copy=False,
                                         help='آخرین بار که فرم «سنجه‌ها و مجموعه‌های مجاز» این عضو ذخیره شد، حتی بدون تغییر.')

    # ------------------------------------------------------------------ counselor first-run card
    def ts_onb_card(self):
        """True when a counselor of a running counseling-center panel has no title on reports yet and has not closed the card."""
        self.ensure_one()
        m = self.sudo()
        ws = m.workspace_id
        return bool(m.active and m.role == 'clinician' and ws.purpose == 'clinical' and ws.state == 'active'
                    and ws.ts_brand_enabled() and not clean_line(m.title) and not m.ts_onb_card_hidden_on)

    def ts_onb_card_hide(self, by):
        self.ensure_one()
        if by != self or not self.active:
            raise UserError('این یادآوری را فقط خود عضو می‌بندد.')
        self.sudo().ts_onb_card_hidden_on = fields.Datetime.now()
        return True

    # ------------------------------------------------------------------ catalog decision marker
    def ts_set_catalog(self, by, restricted, instrument_ids=(), battery_ids=()):
        """ts_battery's member catalog form; a successful save (changed or not) is recorded as a decision."""
        changed = super().ts_set_catalog(by, restricted, instrument_ids, battery_ids)
        self.sudo().ts_catalog_seen_on = fields.Datetime.now()
        return changed
