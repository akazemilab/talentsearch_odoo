"""O3: instruments a visitor may start before any account (`ts_guest_ok`) and the starter («سنجهٔ آغاز»).

Only a short, general, self-scored adult questionnaire may be guest-ok: no child or adolescent instrument, no employment
or invite-only instrument, no talent inventory (matrix) and no timed task. The data file sets the flag on ONE starter
(inventory_002 «فهرست ارجمندی», 17 statements: docs/onboarding/02_invites_and_guest.md explains the choice)."""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

STARTER_CODE = 'inventory_002'
MAX_GUEST_ITEMS = 40


class TsInstrumentGuest(models.Model):
    _inherit = 'ts.instrument'

    ts_guest_ok = fields.Boolean('شروع بدون حساب', help='بازدیدکننده این سنجه را پیش از ساختن حساب پاسخ می‌دهد و نتیجه را '
                                                       'با شمارهٔ موبایل می‌بیند و نگه می‌دارد (پاسخ‌ها ۴۸ ساعت نگه داشته می‌شود).')

    def ts_guest_allowed(self):
        """May this instrument be answered as a guest at all (the rule behind the flag)."""
        self.ensure_one()
        v = self.current_version_id
        return bool(self.state == 'published' and self.audience == 'adult' and self.purpose != 'employment'
                    and not getattr(self, 'invite_only', False) and v and (v.mode or 'single') == 'single'
                    and 0 < (self.active_item_count or 0) <= MAX_GUEST_ITEMS and self.code != 'TALENT-INV-15')

    @api.constrains('ts_guest_ok', 'audience', 'purpose', 'state')
    def _check_guest_ok(self):
        for inst in self:
            if inst.ts_guest_ok and inst.state == 'published' and not inst.ts_guest_allowed():
                raise ValidationError('شروع بدون حساب فقط برای یک پرسش‌نامهٔ کوتاه و عمومی بزرگسالان (حداکثر ۴۰ جمله) '
                                      'ممکن است؛ نه سنجهٔ کودک و نوجوان، استخدامی یا زمان‌دار.')

    def ts_guest_ready(self):
        self.ensure_one()
        return bool(self.ts_guest_ok and self.ts_guest_allowed())

    def ts_minutes_fa(self):
        """«۳»: the approximate minutes in Persian digits (the home hero line)."""
        self.ensure_one()
        return str(self.duration_minutes or 0).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))

    def ts_guest_lead(self):
        """What it measures, in one line for the start screen: «این سنجه ۴ عامل را توصیف می‌کند: الف، ب، ج و د.»
        (the scored factors of the current version; the intended use, a longer book text, stays under «بیشتر بدانید»)."""
        self.ensure_one()
        names = [f.name for f in self.current_version_id.factor_ids.filtered('scored').sorted(lambda f: (f.sequence, f.id))
                 if f.name]
        if not names:
            return self.ts_intended_use()
        joined = names[0] if len(names) == 1 else '%s و %s' % ('، '.join(names[:-1]), names[-1])
        n = str(len(names)).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
        return 'این سنجه %s عامل را توصیف می‌کند: %s.' % (n, joined)

    @api.model
    def ts_starter(self):
        """«سنجهٔ آغاز»: the configured starter when it is guest-ok, else the shortest guest-ok instrument."""
        code = self.env['ir.config_parameter'].sudo().get_str('ts_onboard.starter_code') or STARTER_CODE
        insts = self.sudo().search([('state', '=', 'published'), ('ts_guest_ok', '=', True)]).filtered(
            lambda i: i.ts_guest_allowed())
        return insts.filtered(lambda i: i.code == code)[:1] or insts.sorted(lambda i: (i.active_item_count, i.id))[:1]

    @api.model
    def _ts_seed_starter(self):
        """Data step (install and every update, once): the starter instrument gets the flag. A later change by the EOT team
        in the back office is never undone (the marker ts_onboard.starter_seeded)."""
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_str('ts_onboard.starter_seeded'):
            return False
        inst = self.sudo().search([('code', '=', STARTER_CODE), ('state', '=', 'published')], limit=1)
        if not inst or not inst.ts_guest_allowed():
            return False
        inst.ts_guest_ok = True
        ICP.set_str('ts_onboard.starter_seeded', STARTER_CODE)
        return True
