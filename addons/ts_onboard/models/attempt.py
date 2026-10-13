"""O3: guest attempts (a starter test answered before any account).

A guest attempt is an ordinary ts.attempt owned by the website's public user with `ts_guest` set, keyed by the digest of
a signed random token that lives only in this browser's HttpOnly cookie (ts_guest). It has no panel and no invitation, so
no panel ever sees it and nothing is billed. Consent is recorded on the attempt (service, optional research, version,
time) when the visitor taps «۱۸ سال یا بیشتر دارم؛ موافقم و شروع می‌کنم»; the consent ledger rows are written at the claim,
when the person is known. On sign-in by mobile code the attempt is claimed: re-owned by the account, the token digest
cleared. Unclaimed guest attempts and their answers are deleted 48 hours after their last activity (hourly cron)."""
from datetime import timedelta

from odoo import api, fields, models

from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION

GUEST_TTL_H = 48


class TsAttemptGuest(models.Model):
    _inherit = 'ts.attempt'

    ts_guest = fields.Boolean('بدون حساب (مهمان)', readonly=True, index=True, copy=False)
    ts_guest_hash = fields.Char(readonly=True, index=True, copy=False, groups='base.group_system')
    ts_guest_seen = fields.Datetime('آخرین فعالیت مهمان', readonly=True, copy=False)
    ts_guest_claimed_at = fields.Datetime('زمان نگه‌داشتن نتیجهٔ مهمان', readonly=True, copy=False)

    # ------------------------------------------------------------------ consent and activity
    def ts_guest_consent(self, research=False):
        """The start button is the consent of an adult (age and service), recorded on the attempt."""
        now = fields.Datetime.now()
        for at in self.sudo().filtered(lambda a: a.ts_guest and a.state == 'consent'):
            at.write({'consent_service': True, 'consent_research': bool(research), 'consent_at': now,
                      'consent_version': CONSENT_VERSION, 'state': 'in_progress', 'started_at': now,
                      'respondent_role': 'self', 'ts_guest_seen': now})
            self.env['ts.audit.event'].sudo().log('attempt.consent', at, research=bool(research), role='self',
                                                  consent_version=CONSENT_VERSION, guest=True, age18='yes')

    def ts_guest_touch(self):
        self.sudo().filtered('ts_guest').write({'ts_guest_seen': fields.Datetime.now()})

    def ts_guest_claim(self, user):
        """Move a guest attempt into `user`'s account (once). The ledger gets the consent the visitor gave at the start."""
        self.ensure_one()
        at = self.sudo()
        if not at.ts_guest or not user or user._is_public():
            return False
        at.write({'user_id': user.id, 'ts_guest': False, 'ts_guest_hash': False, 'ts_guest_claimed_at': fields.Datetime.now()})
        if 'ts.consent.record' in self.env:
            Rec = self.env['ts.consent.record']
            Rec._log('service', user, attempt=at, version=at.consent_version, method='checkbox', given_as='self')
            if at.consent_research:
                Rec._log('research', user, attempt=at, version=at.consent_version, method='checkbox', given_as='self')
        self.env['ts.audit.event'].sudo().log('attempt.guest_claim', at, instrument=at.instrument_id.code, state=at.state)
        return True

    # ------------------------------------------------------------------ nothing is sent for a guest
    def _ts_notify_done(self):
        if self.sudo().ts_guest:
            return None
        return super()._ts_notify_done()

    def _ts_notify_result_ready(self):
        if self.sudo().ts_guest:
            return False
        return super()._ts_notify_result_ready()

    # ------------------------------------------------------------------ clean-up
    @api.model
    def _cron_guest_cleanup(self):
        """Delete unclaimed guest attempts (and, by cascade, their answers and results) 48 hours after their last activity.
        Only rows that are still guest attempts of a public user are touched; claimed attempts are ordinary attempts."""
        cut = fields.Datetime.now() - timedelta(hours=GUEST_TTL_H)
        old = self.sudo().search([('ts_guest', '=', True), '|', ('ts_guest_seen', '<', cut),
                                  '&', ('ts_guest_seen', '=', False), ('create_date', '<', cut)])
        old = old.filtered(lambda a: a.user_id._is_public() and not a.workspace_id)
        n = len(old)
        if n:
            old.unlink()
            self.env['ts.audit.event'].sudo().log('attempt.guest_cleanup', None, count=n)
        return n
