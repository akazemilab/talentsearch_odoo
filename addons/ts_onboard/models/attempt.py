"""O3: guest attempts (a starter test answered before any account).

A guest attempt is an ordinary ts.attempt owned by the website's public user with `ts_guest` set, keyed by the digest of
a signed random token that lives only in this browser's HttpOnly cookie (ts_guest). It has no panel and no invitation, so
no panel ever sees it and nothing is billed. Consent is recorded on the attempt (service, optional research, version,
time) when the visitor taps «۱۸ سال یا بیشتر دارم؛ موافقم و شروع می‌کنم»; the consent ledger rows are written at the claim,
when the person is known. On sign-in by mobile code the attempt is claimed: re-owned by the account, the token digest
cleared (atomically: the row is locked, a second or racing claim finds it claimed and does nothing). Unclaimed guest
attempts and their answers are deleted 48 hours after their last activity (hourly cron).

Funnel (models/funnel.py): the first answer (q1) and the end (finish) of a guest attempt, of a signed-in attempt of a
guest-ok instrument and of an invitation (its first part / all its parts) are counted here, for every player."""
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.http import request

from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION

_logger = logging.getLogger(__name__)
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
        """Move a guest attempt into `user`'s account (once, atomically). The ledger gets the consent the visitor gave at
        the start. A second claim, or a claim racing this one, finds the attempt claimed and returns False."""
        self.ensure_one()
        at = self.sudo()
        if not user or user._is_public():
            return False
        at.flush_recordset()
        self.env.cr.execute('SELECT ts_guest FROM ts_attempt WHERE id = %s FOR UPDATE', [at.id])
        row = self.env.cr.fetchone()
        at.invalidate_recordset()
        if not row or not row[0]:
            return False
        at.write({'user_id': user.id, 'ts_guest': False, 'ts_guest_hash': False, 'ts_guest_claimed_at': fields.Datetime.now()})
        if 'ts.consent.record' in self.env:
            Rec = self.env['ts.consent.record']
            Rec._log('service', user, attempt=at, version=at.consent_version, method='checkbox', given_as='self')
            if at.consent_research:
                Rec._log('research', user, attempt=at, version=at.consent_version, method='checkbox', given_as='self')
        self.env['ts.audit.event'].sudo().log('attempt.guest_claim', at, instrument=at.instrument_id.code, state=at.state)
        return True

    # ------------------------------------------------------------------ funnel: first answer and end, every player
    def _ts_funnel_target(self):
        """(counted, invitation or None): a guest attempt, a signed-in attempt of a guest-ok instrument and the attempts
        of an invitation are counted; nothing else (imported results, other self-started attempts)."""
        s = self.sudo()
        if s.ts_guest:
            return True, None
        if s.workspace_id:
            a = s.assignment_id if 'assignment_id' in s._fields else self.env['ts.assignment']
            a = a or self.env['ts.assignment'].sudo().search([('attempt_id', '=', s.id)], limit=1)
            return bool(a), (a or None)
        return bool(s.instrument_id.ts_guest_ok), None

    def _ts_funnel_first(self):
        """Before an answer is saved: is this the first answer of a counted attempt? One indexed probe, and only for a
        counted attempt in a web request."""
        self.ensure_one()
        if not request or self.state != 'in_progress':
            return False
        s = self.sudo()
        if not (s.ts_guest or s.workspace_id or s.instrument_id.ts_guest_ok):
            return False
        self.env.cr.execute('SELECT 1 FROM ts_attempt_answer WHERE attempt_id = %s LIMIT 1', [self.id])
        if self.env.cr.fetchone():
            return False
        if 'ts.attempt.cell' in self.env:
            self.env.cr.execute('SELECT 1 FROM ts_attempt_cell WHERE attempt_id = %s LIMIT 1', [self.id])
            if self.env.cr.fetchone():
                return False
        return True

    def _ts_funnel(self, step):
        try:
            counted, a = self._ts_funnel_target()
            if not counted:
                return
            if a:
                parts = a.ts_battery_attempts()
                if step == 'q1' and parts[:1] != self:
                    return                          # the invitation's first answer is in its first part
                if step == 'finish' and parts.filtered(lambda t: t.state != 'done'):
                    return                          # the invitation is finished when every part is
                self.env['ts.funnel.event'].ts_log(request, step, instrument=a.instrument_id, assignment=a)
            else:
                self.env['ts.funnel.event'].ts_log(request, step, instrument=self.instrument_id)
        except Exception:        # noqa: BLE001 - measuring never breaks answering
            _logger.exception('ts_onboard: funnel step %s not counted', step)

    def save_answer(self, item_id, value):
        first = self._ts_funnel_first()
        res = super().save_answer(item_id, value)
        if first:
            self._ts_funnel('q1')
        return res

    def ts_save_cell(self, field, item_id, value):
        first = self._ts_funnel_first()
        res = super().ts_save_cell(field, item_id, value)
        if first:
            self._ts_funnel('q1')
        return res

    def action_submit(self, *args, **kwargs):
        was_done = {t.id for t in self if t.state == 'done'}
        res = super().action_submit(*args, **kwargs)
        if res and request:
            for t in self:
                if t.id not in was_done and t.state == 'done':
                    t._ts_funnel('finish')
        return res

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
