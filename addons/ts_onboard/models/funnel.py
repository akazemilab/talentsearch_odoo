"""Funnel events of onb2 (design §6, measured weekly by the EOT team). One row per step reached, with no personal data and
nothing that points at a person: the step, the channel (a guest, a signed-in visitor, or how the invitation reached the
person), the instrument, a salted hash, and the day and hour (Tehran time). No invitation, account, website, address or
access columns (`_log_access = False`: no create/write user). Kept 180 days (daily cron). Cheap: at most one indexed
lookup and one insert, only at the steps themselves (never on every answer).

The hash: a visitor with a session gets a random funnel id kept in that session (never the session id); a GET without
any cookie (a first visit, a link preview) writes nothing into a session and is counted at most once per hashed address
and minute. Obvious robots (empty agent, crawlers, link-preview fetchers, command-line clients) are not counted."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
TEHRAN = ZoneInfo('Asia/Tehran')
BOT_RE = re.compile(r'bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|skype|discord|slack|curl|wget|'
                    r'python-requests|go-http-client|okhttp|headless|lighthouse|monitor|scan', re.I)


def is_bot(httprequest):
    ua = httprequest.headers.get('User-Agent') or ''
    return not ua.strip() or bool(BOT_RE.search(ua))


class TsFunnelEvent(models.Model):
    _name = 'ts.funnel.event'
    _description = 'Talent Search funnel event (no personal data)'
    _order = 'id desc'
    _log_access = False

    step = fields.Selection(STEPS, 'گام', required=True, index=True, readonly=True)
    entry = fields.Selection(ENTRIES, 'کانال', index=True, readonly=True)
    instrument_id = fields.Many2one('ts.instrument', 'سنجه', ondelete='set null', index=True, readonly=True)
    session_hash = fields.Char('شناسهٔ بی‌نام', index=True, readonly=True)
    day = fields.Date('روز', required=True, index=True, readonly=True,
                      default=lambda s: datetime.now(TEHRAN).date())
    hour = fields.Integer('ساعت', readonly=True, default=lambda s: datetime.now(TEHRAN).hour)

    @api.model
    def _ts_salt(self):
        ICP = self.env['ir.config_parameter'].sudo()
        salt = ICP.get_str('ts_onboard.funnel_salt')
        if not salt:
            salt = secrets.token_hex(16)
            ICP.set_str('ts_onboard.funnel_salt', salt)
        return salt

    def _ts_hash(self, request):
        """The salted hash of this visitor, or None for a robot. A cookie-less GET never writes into a session."""
        hr = request.httprequest
        if is_bot(hr):
            return None
        salt = self._ts_salt()
        if hr.method in ('GET', 'HEAD') and 'session_id' not in hr.cookies:
            ip = self.env['ts.audit.event'].sudo()._hash_ip(hr.remote_addr)
            minute = datetime.now(TEHRAN).strftime('%Y%m%d%H%M')
            return hashlib.sha256(('%s:ip:%s:%s' % (salt, ip, minute)).encode()).hexdigest()[:24]
        sess = request.session
        fid = sess.get(FID_KEY)
        if not fid:
            fid = secrets.token_hex(12)
            sess[FID_KEY] = fid
        return hashlib.sha256(('%s:%s' % (salt, fid)).encode()).hexdigest()[:24]

    @api.model
    def ts_log(self, request, step, instrument=None, assignment=None, once=True, entry=None):
        """One row for `step`; with `once`, at most one row per hash, step, channel and instrument. `entry` defaults to how
        the invitation reached the person (`assignment` is read for that only, never stored), else guest / user. Never
        raises."""
        try:
            h = self._ts_hash(request)
            if not h:
                return self.browse()
            if not entry:
                if assignment:
                    entry = assignment.sudo().delivered_via or 'manual'
                else:
                    entry = 'guest' if request.env.user._is_public() else 'user'
            vals = {'step': step, 'entry': entry, 'session_hash': h, 'instrument_id': instrument.id if instrument else False}
            S = self.sudo()
            if once and S.search_count([('step', '=', step), ('session_hash', '=', h), ('entry', '=', entry),
                                        ('instrument_id', '=', vals['instrument_id'])], limit=1):
                return S.browse()
            with self.env.cr.savepoint():
                return S.create(vals)
        except Exception:       # noqa: BLE001 - measuring never breaks the page
            return self.browse()

    @api.model
    def _cron_retention(self):
        old = self.sudo().search([('day', '<', fields.Date.today() - timedelta(days=RETENTION_DAYS))])
        n = len(old)
        old.unlink()
        return n
