import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.addons.ts_kavenegar.tools.kavenegar import normalize_receptor

TTL_MIN = 5
MAX_ATTEMPTS = 5
COOLDOWN_S = 60
MAX_PER_HOUR_USER = 5
MAX_PER_HOUR_PHONE = 5


def iran_mobile(number):
    n = normalize_receptor(number)
    return n if n and len(n) == 11 and n.startswith('09') else False


class TsPhoneOtp(models.Model):
    _name = 'ts.phone.otp'
    _description = 'Talent Search mobile verification code'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    phone = fields.Char(required=True, index=True)
    salt = fields.Char(required=True)
    code_hash = fields.Char(required=True)
    expires_at = fields.Datetime(required=True)
    attempts = fields.Integer()
    used = fields.Boolean()
    # onb1 risk review: a number another account holds gets a row like any other but no SMS; every code is then wrong
    blocked = fields.Boolean()

    @staticmethod
    def _hash(salt, code):
        return hashlib.sha256((salt + ':' + code).encode()).hexdigest()

    @api.model
    def request_code(self, user, phone_raw):
        """Return (ok, reason). reason in: format, cooldown, limit, disabled, send. A number that belongs to another
        account is never revealed here: the answer is the same as a normal send, nothing is sent, and the code step
        refuses every code with the neutral «wrong» text (one number, one account)."""
        company = self.env.company.sudo()
        phone = iran_mobile(phone_raw)
        if not phone:
            return False, 'format'
        if not (company.kv_enabled and company.ts_sms_otp):
            return False, 'disabled'
        now = fields.Datetime.now()
        S = self.sudo()
        last = S.search([('user_id', '=', user.id)], limit=1)
        if last and last.create_date > now - timedelta(seconds=COOLDOWN_S):
            return False, 'cooldown'
        hour = now - timedelta(hours=1)
        if S.search_count([('user_id', '=', user.id), ('create_date', '>=', hour)]) >= MAX_PER_HOUR_USER \
                or S.search_count([('phone', '=', phone), ('create_date', '>=', hour)]) >= MAX_PER_HOUR_PHONE:
            return False, 'limit'
        code = '%06d' % secrets.randbelow(10 ** 6)
        salt = secrets.token_hex(8)
        if self.env['res.users'].ts_phone_owner(phone, exclude=user):
            S.create({'user_id': user.id, 'phone': phone, 'salt': salt, 'code_hash': self._hash(salt, secrets.token_hex(16)),
                      'expires_at': now + timedelta(minutes=TTL_MIN), 'blocked': True})
            return True, None
        rec = S.create({'user_id': user.id, 'phone': phone, 'salt': salt, 'code_hash': self._hash(salt, code),
                        'expires_at': now + timedelta(minutes=TTL_MIN)})
        if not self._send_code(company, phone, code):
            rec.unlink()
            return False, 'send'
        return True, None

    @api.model
    def _send_code(self, company, phone, code):
        """Every OTP (sign-in, signup, phone verify, re-auth) goes through the approved Kavenegar Verify Lookup
        template «otp» (id 1543452). There is no plain-SMS fallback: if the lookup fails the code is not sent."""
        tpl = company.ts_sms_otp_template_id
        name = tpl.name if tpl else 'otp'
        try:
            cl = company._kv_client()
            res = cl.lookup(phone, name, code, tag=company.kv_default_tag or None)
            e = res[0] if res else {}
            self.env['kavenegar.message'].sudo()._kv_log_sent([{
                'company_id': company.id, 'kind': 'lookup', 'messageid': str(e.get('messageid') or ''),
                'receptor': phone, 'sender': e.get('sender'), 'body': '***', 'template_name': name,
                'kv_status': int(e.get('status') or 1), 'status_text': e.get('statustext'),
                'cost': float(e.get('cost') or 0)}])
            return True
        except Exception:
            return False

    @api.model
    def _ts_otp_host(self):
        """The host of talentsearch.ir for the WebOTP line «@host #code» (the browser checks it against the page)."""
        from urllib.parse import urlsplit
        site = self.env.ref('ts_website.website_ts', raise_if_not_found=False)
        host = urlsplit(site.domain if '://' in (site.domain or '') else 'https://%s' % (site.domain or '')).hostname if site else None
        return (host or 'talentsearch.ir').lower()

    @api.model
    def _ts_otp_body(self, code, phone=None):
        """Text of the plain-SMS code (no Kavenegar lookup template). ts_brand renders it from an sms.template. The last
        line is the WebOTP / iOS one-time-code line."""
        return 'استعدادیاب\nکد ورود: %s\nاین کد را به کسی ندهید.\n@%s #%s' % (code, self._ts_otp_host(), code)

    @api.model
    def verify_code(self, user, code):
        """Return (ok, reason, phone). reason: short, none, expired, wrong, attempts."""
        from .signup_otp import clean_code
        if len(clean_code(code)) != 6:
            return False, 'short', None
        S = self.sudo()
        rec = S.search([('user_id', '=', user.id), ('used', '=', False)], limit=1)
        if not rec:
            return False, 'none', None
        if rec.expires_at < fields.Datetime.now():
            return False, 'expired', None
        if rec.attempts >= MAX_ATTEMPTS:
            return False, 'attempts', None
        rec.attempts += 1
        good = hmac.compare_digest(rec.code_hash, self._hash(rec.salt, clean_code(code)))
        if not good or rec.blocked:
            return False, 'wrong', None
        rec.used = True
        return True, None, rec.phone

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=2))]).unlink()
