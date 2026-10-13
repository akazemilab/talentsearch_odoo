"""O2: how an invitation reached the person, the secret that proves it, and the browser it is bound to.

* `delivered_via`: sms / email / manual (a link or QR code the panel copied, a panel that typed no number) / campaign (the
  person joined through an open link or a class code). sms and email are set by the existing SMS and e-mail send paths
  when they report success (invitation or reminder); the number or address the message went to is kept
  (`delivered_phone`, `delivered_email`).
* The delivery secret (risk review HIGH 1): the panel shows and copies the same invitation link the message carries, so
  the link alone proves nothing. Every message the system sends (invitation or reminder, SMS or e-mail) carries a fresh
  secret of 22 random url-safe characters: `/i/<code>/<secret>` in an SMS, `/invite/<token>?d=<secret>` in an e-mail.
  Only its digest is stored (`dlv_sms_hash`, `dlv_email_hash`); the secret exists in memory only while the message is
  rendered (a send window, below) and is never part of `invite_url()` anywhere else: no panel page, copy button, export,
  audit row or log line ever holds it (the Kavenegar log row of such an SMS is masked: `kv_secret`). A new message
  replaces the secret of its channel (older links then get a code, as a copied link does); a message that did not go out
  keeps the previous one.
* `device_hash`, `device_until`: sha256 of the browser token of the first accept (cookie ts_dev, HttpOnly, SameSite=Lax)
  and the end of that binding (30 days when «این دستگاه شخصی من است» was ticked, 12 hours otherwise). The raw token is
  never stored.
* `ts_account_made`: the account that accepted was made by the one-tap flow for this invitation (an e-mail link with its
  secret to an address that had no account, or an SMS to a number that had none).
* The welcome screen's POST is the consent: `welcome_version` (the consent text version) and `welcome_at`.
"""
import hmac
import secrets
import threading
from contextlib import contextmanager

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_sms.models.phone_otp import iran_mobile

from .common import DLV_BYTES, DLV_RE, dlv_digest

DELIVERY = [('manual', 'پیوند یا کد QR'), ('sms', 'پیامک'), ('email', 'ایمیل'), ('campaign', 'پیوند باز یا کد کلاس')]
CHANNELS = ('sms', 'email')
_OUT = threading.local()       # open send windows of this thread: {(db, assignment id): {'sms': raw, 'email': raw, ...}}


def _windows():
    m = getattr(_OUT, 'map', None)
    if m is None:
        m = _OUT.map = {}
    return m


def sending():
    """Is a message with a delivery secret being rendered in this thread?"""
    return bool(_windows())


class TsAssignmentDelivery(models.Model):
    _inherit = 'ts.assignment'

    delivered_via = fields.Selection(DELIVERY, 'راه رسیدن دعوت', default='manual', required=True, readonly=True, copy=False)
    delivered_phone = fields.Char('شماره‌ای که پیامک دعوت به آن رسید', readonly=True, copy=False,
                                  groups='ts_core.group_ts_manager')
    delivered_email = fields.Char('نشانی‌ای که ایمیل دعوت به آن رسید', readonly=True, copy=False,
                                  groups='ts_core.group_ts_manager')
    dlv_sms_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    dlv_email_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    device_hash = fields.Char(readonly=True, copy=False, index=True, groups='base.group_system')
    device_until = fields.Datetime(readonly=True, copy=False, groups='base.group_system')
    ts_account_made = fields.Boolean(readonly=True, copy=False, groups='base.group_system')
    welcome_version = fields.Char('نسخهٔ متن رضایت (صفحهٔ خوش‌آمد)', readonly=True, copy=False)
    welcome_at = fields.Datetime('زمان رضایت (صفحهٔ خوش‌آمد)', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('campaign_id') and not vals.get('delivered_via'):
                vals['delivered_via'] = 'campaign'
        return super().create(vals_list)

    @api.model
    def _ts_seed_delivery(self):
        """Data step (install and every update, idempotent): invitations made by joining a campaign are «campaign»."""
        self.env.flush_all()
        self.env.cr.execute("UPDATE ts_assignment SET delivered_via = 'campaign' "
                            "WHERE campaign_id IS NOT NULL AND delivered_via = 'manual'")
        n = self.env.cr.rowcount
        self.env.invalidate_all()
        return n

    # ------------------------------------------------------------------ the delivery secret (send windows)
    @contextmanager
    def _ts_dlv_window(self):
        """While a message of this invitation is rendered and sent: its links carry a delivery secret, made at the first
        link of each channel. Yields the window ({'sms': raw|None, 'email': raw|None, 'prev': {...}})."""
        self.ensure_one()
        s = self.sudo()
        key = (self.env.cr.dbname, self.id)
        win = {'sms': None, 'email': None, 'prev': {'sms': s.dlv_sms_hash, 'email': s.dlv_email_hash}}
        _windows()[key] = win
        try:
            yield win
        finally:
            _windows().pop(key, None)
            if 'ts_sms_link' in self._fields:
                self.invalidate_recordset(['ts_sms_link'])      # the rendered link never outlives the window

    def _ts_dlv_raw(self, channel):
        """Inside a send window: the secret of `channel` for this message (made once per window, its digest stored).
        Outside a window: None (every other caller of invite_url() gets the plain link)."""
        if len(self) != 1 or not self.id:
            return None
        win = _windows().get((self.env.cr.dbname, self.id))
        if win is None:
            return None
        if not win[channel]:
            raw = secrets.token_urlsafe(DLV_BYTES)
            self.sudo().write({'dlv_%s_hash' % channel: dlv_digest(raw)})
            win[channel] = raw
        return win[channel]

    def _ts_dlv_keep_old(self, win, sent):
        """Channels that did not go out keep the previous secret (their older message still proves its contact)."""
        vals = {'dlv_%s_hash' % c: win['prev'][c] for c in CHANNELS if win[c] and c not in sent}
        if vals:
            self.sudo().write(vals)

    def ts_short_url(self):
        url = super().ts_short_url()
        raw = self._ts_dlv_raw('sms')
        return '%s/%s' % (url, raw) if raw else url

    def invite_url(self):
        url = super().invite_url()
        if self.env.context.get('ts_sms_short'):
            return url                   # the SMS short link (ts_short_url above) carries the SMS secret
        raw = self._ts_dlv_raw('email')
        return '%s?d=%s' % (url, raw) if raw else url

    def ts_dlv_channel(self, raw):
        """The channel whose latest message carried `raw` ('sms' / 'email'), else None. Constant-time comparisons."""
        self.ensure_one()
        if not raw or not isinstance(raw, str) or not DLV_RE.match(raw):
            return None
        s = self.sudo()
        d = dlv_digest(raw)
        if s.dlv_sms_hash and hmac.compare_digest(d, s.dlv_sms_hash) and s.delivered_phone:
            return 'sms'
        if s.dlv_email_hash and hmac.compare_digest(d, s.dlv_email_hash) and s.delivered_email:
            return 'email'
        return None

    def ts_dlv_value(self, channel):
        s = self.sudo()
        return s.delivered_phone if channel == 'sms' else s.delivered_email

    # ------------------------------------------------------------------ the send paths report delivery
    def _ts_mark_delivered(self, via, phone=None, email=None):
        for a in self.sudo():
            if via == 'sms' and phone:
                a.write({'delivered_via': 'sms', 'delivered_phone': phone})
            elif via == 'email' and email and '@' in email:
                vals = {'delivered_email': email.strip().lower()}
                if a.delivered_via != 'sms':
                    vals['delivered_via'] = 'email'
                a.write(vals)

    def _ts_send_invite_sms(self):
        with self._ts_dlv_window() as win:
            ok = super()._ts_send_invite_sms()
            self._ts_dlv_keep_old(win, {'sms'} if ok else set())
        if ok:
            self._ts_mark_delivered('sms', phone=iran_mobile(self.invitee_phone or ''))
        return ok

    def _ts_send_invite_email(self):
        with self._ts_dlv_window() as win:
            ok = super()._ts_send_invite_email()
            self._ts_dlv_keep_old(win, {'email'} if ok else set())
        if ok:
            self._ts_mark_delivered('email', email=self.invitee_email)
        return ok

    def _ts_do_reminder(self):
        with self._ts_dlv_window() as win:
            used = super()._ts_do_reminder()
            self._ts_dlv_keep_old(win, set(used or ()))
        if 'sms' in used:
            self._ts_mark_delivered('sms', phone=iran_mobile(self.invitee_phone or ''))
        if 'email' in used:
            self._ts_mark_delivered('email', email=self.invitee_email)
        return used

    def action_decline(self, user):
        """«نمی‌خواهم شرکت کنم» from a visitor who is not signed in (the link is the key of this one invitation): the
        invitation is declined without tying it to any account; the panel's hold is released as for any decline."""
        if user and user._is_public():
            for a in self.sudo():
                if a.user_id or a.attempt_id:
                    raise UserError('این دعوت دیگر قابل رد نیست.')
                a.write({'declined': True})
                self.env['ts.audit.event'].sudo().log('assignment.decline', a, workspace=a.workspace_id, signed_in=False)
            if hasattr(self, '_ts_billing_release'):
                self._ts_billing_release('decline')
            return True
        return super().action_decline(user)

    # ------------------------------------------------------------------ who the invitation is for
    def ts_proof(self):
        """(via, value): where the system's message went ('sms', number), ('email', address) or (None, None). Since the
        risk review this is the contact the invitation names, not a proof: only the delivery secret proves it."""
        self.ensure_one()
        s = self.sudo()
        if s.delivered_via == 'sms' and s.delivered_phone:
            return 'sms', s.delivered_phone
        if s.delivered_via == 'email' and s.delivered_email:
            return 'email', s.delivered_email
        return None, None

    def ts_invite_phone(self):
        """The number of this invitation: the one the SMS reached, else the number the panel wrote (may be empty)."""
        self.ensure_one()
        s = self.sudo()
        return s.delivered_phone or iran_mobile(s.invitee_phone or '') or ''

    def ts_contact_matches(self, user):
        """True / False when the invitation names a number (or an e-mail address it reached) and `user` holds it or not;
        None when the invitation names neither (a copied link or QR code without a number): then nothing is checked."""
        self.ensure_one()
        via, value = self.ts_proof()
        phone = self.ts_invite_phone()
        if phone and via != 'email':
            phones = set(user.sudo()._ts_verified_phones() or []) | {user.sudo().login}
            return phone in phones
        if via == 'email':
            u = user.sudo()
            return value in {(u.login or '').strip().lower(), (u.email or '').strip().lower()}
        return None


class TsSmsSecret(models.Model):
    """An SMS rendered inside a send window carries a delivery secret: the Kavenegar log keeps «***» instead of its text
    (the same mask as a sign-in code)."""
    _inherit = 'sms.sms'

    @api.model_create_multi
    def create(self, vals_list):
        if sending() and 'kv_secret' in self._fields:
            for vals in vals_list:
                vals['kv_secret'] = True
        return super().create(vals_list)
