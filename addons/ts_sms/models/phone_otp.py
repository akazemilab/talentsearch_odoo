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

    @staticmethod
    def _hash(salt, code):
        return hashlib.sha256((salt + ':' + code).encode()).hexdigest()

    @api.model
    def request_code(self, user, phone_raw):
        """Return (ok, reason). reason in: format, cooldown, limit, disabled, send."""
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
        rec = S.create({'user_id': user.id, 'phone': phone, 'salt': salt, 'code_hash': self._hash(salt, code),
                        'expires_at': now + timedelta(minutes=TTL_MIN)})
        if not self._send_code(company, phone, code):
            rec.unlink()
            return False, 'send'
        return True, None

    @api.model
    def _send_code(self, company, phone, code):
        tpl = company.ts_sms_otp_template_id
        try:
            if tpl and company.kv_has_lookup and tpl.approval == 'Approved':
                cl = company._kv_client()
                res = cl.lookup(phone, tpl.name, code, tag=company.kv_default_tag or None)
                e = res[0] if res else {}
                self.env['kavenegar.message'].sudo()._kv_log_sent([{
                    'company_id': company.id, 'kind': 'lookup', 'messageid': str(e.get('messageid') or ''),
                    'receptor': phone, 'sender': e.get('sender'), 'body': '***', 'template_name': tpl.name,
                    'kv_status': int(e.get('status') or 1), 'status_text': e.get('statustext'),
                    'cost': float(e.get('cost') or 0)}])
                return True
            body = _('کد تأیید تلنت سرچ: %s\nاین کد را به کسی ندهید.', code)
            sms = self.env['sms.sms'].sudo().create({'number': phone, 'body': body, 'sms_type': 'alert', 'kv_secret': True})
            sms.send(unlink_sent=False, raise_exception=False)
            ok = sms.state in ('process', 'pending', 'sent')
            sms.unlink()
            return ok
        except Exception:
            return False

    @api.model
    def verify_code(self, user, code):
        """Return (ok, reason, phone). reason: none, expired, wrong, attempts."""
        S = self.sudo()
        rec = S.search([('user_id', '=', user.id), ('used', '=', False)], limit=1)
        if not rec:
            return False, 'none', None
        if rec.expires_at < fields.Datetime.now():
            return False, 'expired', None
        if rec.attempts >= MAX_ATTEMPTS:
            return False, 'attempts', None
        rec.attempts += 1
        good = hmac.compare_digest(rec.code_hash, self._hash(rec.salt, (code or '').strip()))
        if not good:
            return False, 'wrong', None
        rec.used = True
        return True, None, rec.phone

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=2))]).unlink()
