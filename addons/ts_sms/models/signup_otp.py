import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessDenied

from .phone_otp import COOLDOWN_S, MAX_ATTEMPTS, TTL_MIN, iran_mobile

MAX_PER_HOUR_PHONE = 5
MAX_PER_HOUR_IP = 20
LOGIN_TOKEN_TTL_S = 120
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _h(salt, value):
    return hashlib.sha256((salt + ':' + value).encode()).hexdigest()


class TsSignupOtp(models.Model):
    """One-time code sent to a mobile number BEFORE any account exists (sign-up / sign-in by mobile)."""
    _name = 'ts.signup.otp'
    _description = 'Talent Search sign-in code'
    _order = 'id desc'

    phone = fields.Char(required=True, index=True)
    ip_hash = fields.Char(index=True)
    salt = fields.Char(required=True)
    code_hash = fields.Char(required=True)
    expires_at = fields.Datetime(required=True)
    attempts = fields.Integer()
    used = fields.Boolean()

    @api.model
    def ip_digest(self, ip):
        return hashlib.sha256(('ts-ip:' + (ip or '')).encode()).hexdigest()[:32]

    @api.model
    def request_code(self, phone_raw, ip=None):
        """Return (ok, reason, phone). reason in: format, disabled, cooldown, limit, send."""
        company = self.env.company.sudo()
        phone = iran_mobile(phone_raw)
        if not phone:
            return False, 'format', None
        if not (company.kv_enabled and company.ts_sms_otp):
            return False, 'disabled', None
        S, now = self.sudo(), fields.Datetime.now()
        last = S.search([('phone', '=', phone)], limit=1)
        if last and last.create_date > now - timedelta(seconds=COOLDOWN_S):
            return False, 'cooldown', phone
        hour, ipd = now - timedelta(hours=1), self.ip_digest(ip)
        if S.search_count([('phone', '=', phone), ('create_date', '>=', hour)]) >= MAX_PER_HOUR_PHONE \
                or (ip and S.search_count([('ip_hash', '=', ipd), ('create_date', '>=', hour)]) >= MAX_PER_HOUR_IP):
            return False, 'limit', phone
        code = '%06d' % secrets.randbelow(10 ** 6)
        salt = secrets.token_hex(8)
        rec = S.create({'phone': phone, 'ip_hash': ipd if ip else False, 'salt': salt, 'code_hash': _h(salt, code),
                        'expires_at': now + timedelta(minutes=TTL_MIN)})
        if not self.env['ts.phone.otp']._send_code(company, phone, code):
            rec.unlink()
            return False, 'send', phone
        return True, None, phone

    @api.model
    def verify_code(self, phone, code):
        """Return (ok, reason). reason: none, expired, wrong, attempts."""
        rec = self.sudo().search([('phone', '=', phone), ('used', '=', False)], limit=1)
        if not rec:
            return False, 'none'
        if rec.expires_at < fields.Datetime.now():
            return False, 'expired'
        if rec.attempts >= MAX_ATTEMPTS:
            return False, 'attempts'
        rec.attempts += 1
        if not hmac.compare_digest(rec.code_hash, _h(rec.salt, (code or '').strip().translate(_DIGITS))):
            return False, 'wrong'
        rec.used = True
        return True, None

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=2))]).unlink()


class TsLoginToken(models.Model):
    """Single-use, short-lived proof that a mobile code was just verified for this user; consumed by
    res.users._check_credentials so the stock session login can run without a password."""
    _name = 'ts.login.token'
    _description = 'Talent Search one-time login token'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    token_hash = fields.Char(required=True, index=True)
    expires_at = fields.Datetime(required=True)
    used = fields.Boolean()

    @api.model
    def issue(self, user):
        raw = secrets.token_urlsafe(32)
        self.sudo().create({'user_id': user.id, 'token_hash': hashlib.sha256(raw.encode()).hexdigest(),
                            'expires_at': fields.Datetime.now() + timedelta(seconds=LOGIN_TOKEN_TTL_S)})
        return raw

    @api.model
    def consume(self, user, raw):
        if not raw:
            return False
        rec = self.sudo().search([('user_id', '=', user.id), ('used', '=', False),
                                  ('token_hash', '=', hashlib.sha256(raw.encode()).hexdigest())], limit=1)
        if not rec or rec.expires_at < fields.Datetime.now():
            return False
        rec.used = True
        return True

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=1))]).unlink()


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _check_credentials(self, credential, env):
        if credential.get('type') == 'ts_phone_login':
            if not self.env['ts.login.token'].consume(self, credential.get('token')):
                raise AccessDenied()
            return {'uid': self.id, 'auth_method': 'password', 'mfa': 'skip'}
        return super()._check_credentials(credential, env)
