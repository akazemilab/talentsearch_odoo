import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models

from odoo.addons.ts_sms.models.phone_otp import COOLDOWN_S, MAX_ATTEMPTS, TTL_MIN

PER_HOUR = 5
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


class TsReauthCode(models.Model):
    """Proof of identity for sensitive actions (05_permissions_matrix.md section 6). Deliberately not
    ts.phone.otp: that model accepts the newest unused code whatever number it was sent to and re-enables an SMS
    preference, which is right for verifying a phone and wrong for proving identity. The code goes ONLY to the
    account's already verified mobile (partner.ts_phone)."""
    _name = 'ts.reauth.code'
    _description = 'Talent Search re-authentication code'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    salt = fields.Char(required=True)
    code_hash = fields.Char(required=True)
    expires_at = fields.Datetime(required=True)
    attempts = fields.Integer()
    used = fields.Boolean()

    @staticmethod
    def _hash(salt, code):
        return hashlib.sha256((salt + ':' + code).encode()).hexdigest()

    @api.model
    def ts_phone_of(self, user):
        """The verified mobile code recipient, or False (then the password is used)."""
        return user.sudo().partner_id.ts_phone or False

    @api.model
    def ts_request(self, user):
        """Send a code to the verified mobile. Returns (ok, reason); reason: nophone, cooldown, limit, send."""
        phone = self.ts_phone_of(user)
        if not phone:
            return False, 'nophone'
        S = self.sudo()
        now = fields.Datetime.now()
        last = S.search([('user_id', '=', user.id)], limit=1)
        if last and last.create_date > now - timedelta(seconds=COOLDOWN_S):
            return False, 'cooldown'
        if S.search_count([('user_id', '=', user.id), ('create_date', '>=', now - timedelta(hours=1))]) >= PER_HOUR:
            return False, 'limit'
        code = '%06d' % secrets.randbelow(10 ** 6)
        salt = secrets.token_hex(8)
        rec = S.create({'user_id': user.id, 'salt': salt, 'code_hash': self._hash(salt, code),
                        'expires_at': now + timedelta(minutes=TTL_MIN)})
        if not self.env['ts.phone.otp']._send_code(self.env.company.sudo(), phone, code):
            rec.unlink()
            return False, 'send'
        return True, None

    @api.model
    def ts_verify(self, user, code):
        """Returns (ok, reason); reason: none, expired, attempts, wrong. Persian and Arabic digits are accepted."""
        S = self.sudo()
        rec = S.search([('user_id', '=', user.id), ('used', '=', False)], limit=1)
        if not rec:
            return False, 'none'
        if rec.expires_at < fields.Datetime.now():
            return False, 'expired'
        if rec.attempts >= MAX_ATTEMPTS:
            return False, 'attempts'
        rec.attempts += 1
        given = (code or '').strip().translate(_DIGITS)
        if not hmac.compare_digest(rec.code_hash, self._hash(rec.salt, given)):
            return False, 'wrong'
        rec.used = True
        return True, None

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=2))]).unlink()
