"""Funnel events of onb2 (design §6, measured weekly by the EOT team). One row per step reached, with no personal data:
the step, the kind of entry (a guest, a signed-in visitor, or how the invitation reached the person), the instrument or
invitation, a salted hash of a random funnel id kept in the visitor's session (never the session id, the address, a phone
number or a name), the website and the time. Kept 180 days (daily cron). The invitation path has the same «first answer»
and «finished» steps (q1, finish) with the invitation set; the instrument path has them without. Cheap: at most one
indexed lookup and one insert, only at the steps themselves (never on every answer)."""
import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models

STEPS = [
    ('start_view', 'دیدن صفحهٔ شروع'), ('start', 'شروع سنجه'), ('q1', 'پاسخ به نخستین پرسش'), ('finish', 'پایان سنجه'),
    ('gate_view', 'دیدن صفحهٔ نتیجه (ورود)'), ('gate_signed_in', 'ورود و نگه‌داشتن نتیجه'), ('report_view', 'دیدن گزارش'),
    ('invite_view', 'دیدن دعوت'), ('invite_accept', 'پذیرفتن دعوت'),
]
ENTRIES = [
    ('guest', 'بدون حساب'), ('user', 'با حساب'), ('sms', 'دعوت با پیامک'), ('email', 'دعوت با ایمیل'),
    ('manual', 'دعوت با پیوند یا QR'), ('campaign', 'پیوند باز یا کلاس'),
]
RETENTION_DAYS = 180
FID_KEY = 'ts_fid'


class TsFunnelEvent(models.Model):
    _name = 'ts.funnel.event'
    _description = 'Talent Search funnel event (no personal data)'
    _order = 'id desc'

    step = fields.Selection(STEPS, 'گام', required=True, index=True, readonly=True)
    entry = fields.Selection(ENTRIES, 'نوع ورود', index=True, readonly=True)
    instrument_id = fields.Many2one('ts.instrument', 'سنجه', ondelete='set null', index=True, readonly=True)
    assignment_id = fields.Many2one('ts.assignment', 'دعوت', ondelete='set null', index=True, readonly=True)
    session_hash = fields.Char('شناسهٔ بی‌نام نشست', index=True, readonly=True)
    website_id = fields.Many2one('website', 'وب‌سایت', ondelete='set null', readonly=True)

    @api.model
    def _ts_salt(self):
        ICP = self.env['ir.config_parameter'].sudo()
        salt = ICP.get_str('ts_onboard.funnel_salt')
        if not salt:
            salt = secrets.token_hex(16)
            ICP.set_str('ts_onboard.funnel_salt', salt)
        return salt

    @api.model
    def ts_log(self, request, step, instrument=None, assignment=None, once=True, entry=None):
        """One row for `step`; with `once`, at most one row per funnel id, step and instrument/invitation. `entry` defaults
        to how the invitation reached the person, else guest / user. Never raises."""
        try:
            sess = request.session
            fid = sess.get(FID_KEY)
            if not fid:
                fid = secrets.token_hex(12)
                sess[FID_KEY] = fid
            h = hashlib.sha256(('%s:%s' % (self._ts_salt(), fid)).encode()).hexdigest()[:24]
            if not entry:
                if assignment:
                    entry = assignment.sudo().delivered_via or 'manual'
                else:
                    entry = 'guest' if request.env.user._is_public() else 'user'
            vals = {'step': step, 'entry': entry, 'session_hash': h, 'instrument_id': instrument.id if instrument else False,
                    'assignment_id': assignment.id if assignment else False,
                    'website_id': request.env.website.id if request.env.website else False}
            S = self.sudo()
            if once and S.search_count([('step', '=', step), ('session_hash', '=', h),
                                        ('instrument_id', '=', vals['instrument_id']),
                                        ('assignment_id', '=', vals['assignment_id'])], limit=1):
                return S.browse()
            with self.env.cr.savepoint():
                return S.create(vals)
        except Exception:       # noqa: BLE001 - measuring never breaks the page
            return self.browse()

    @api.model
    def _cron_retention(self):
        old = self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=RETENTION_DAYS))])
        n = len(old)
        old.unlink()
        return n
