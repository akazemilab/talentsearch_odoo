"""Consent rows next to the share actions (S15, PRV-1). The existing flows are untouched; a row is added after them."""
from odoo import models

LEVEL_WORDS = {
    'education': 'گزارش نیمرخ شما، بدون پاسخ‌های خام',
    'summary': 'فقط بازهٔ هر بُعد (کم، متوسط، زیاد)، بدون نمره و پاسخ‌ها',
    'clinical': 'گزارش بالینی همراه با متن‌های متخصص',
}


class TsAssignmentConsent(models.Model):
    _inherit = 'ts.assignment'

    def action_accept(self, user, share):
        fresh = {a.id for a in self if not a.user_id}
        res = super().action_accept(user, share)
        for a in self:
            if a.id in fresh and a.share_level != 'none':
                self.env['ts.consent.record']._log('share', user, assignment=a, level=a.share_level)
        return res

    def ts_share_attempt(self, attempt, code, user):
        a = super().ts_share_attempt(attempt, code, user)
        if a:
            self.env['ts.consent.record']._log('share', user, assignment=a, level=a.share_level)
        return a

    def action_revoke_share(self, user):
        was = {a.id: a.share_level for a in self}
        res = super().action_revoke_share(user)
        for a in self:
            if was.get(a.id) not in (None, 'none'):
                self.env['ts.consent.record']._log('share_revoke', user, assignment=a, level='none')
        return res

    def ts_level_word(self):
        """What the panel sees of the result, in words for the participant (PRV-2)."""
        self.ensure_one()
        if self.share_level == 'none':
            return 'اشتراک لغو شده است'
        purpose = self.workspace_id.purpose
        return LEVEL_WORDS['education'] if purpose == 'education' else (
            LEVEL_WORDS['clinical'] if purpose == 'clinical' else LEVEL_WORDS['summary'])
