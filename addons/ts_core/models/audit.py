import hashlib
import json
import re
import secrets

from odoo import api, fields, models
from odoo.exceptions import UserError

# Keys that can carry personal data or free text never reach `detail` (04_data_model.md 2.3).
DENY_KEYS = {'name', 'phone', 'mobile', 'email', 'answer', 'answers', 'token', 'code', 'password',
             'reason', 'note', 'text', 'body'}
_PHONE_RE = re.compile(r'(?:\+?98|0098|0)?9\d{9}|[۰-۹٠-٩]{10,}')
_EMAIL_RE = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]{2,}')
_ID_RE = re.compile(r'/\d+(?=/|$)')
_TOKEN_RE = re.compile(r'/(invite|join|r|o)/[^/?#]+')


def _clean_value(v):
    if isinstance(v, str):
        if _PHONE_RE.fullmatch(v.strip().replace(' ', '')) or _EMAIL_RE.search(v):
            return '***'
        return v[:120]
    if isinstance(v, (list, tuple)):
        return [_clean_value(x) for x in v][:20]
    if isinstance(v, dict):
        return {k: _clean_value(x) for k, x in v.items() if k not in DENY_KEYS}
    return v


def clean_detail(detail):
    """Drop deny-listed keys, mask phone/email-shaped strings, cut long strings."""
    return {k: _clean_value(v) for k, v in (detail or {}).items() if k not in DENY_KEYS}


def route_of(path):
    """Request path with ids and tokens replaced, so a route can be stored without identifying anyone."""
    path = _TOKEN_RE.sub(lambda m: '/%s/<token>' % m.group(1), path or '')
    return _ID_RE.sub('/<id>', path)[:200]


class TsAuditEvent(models.Model):
    """Append-only audit trail for consequential Talent Search actions.

    Rows are created through ``ts.audit.event.log`` only; writes and deletes
    are refused for everyone (including administrators) so the trail stays
    tamper-evident. Retention purges, when approved, will run as a dedicated
    server-side job that records its own event first.
    """
    _name = 'ts.audit.event'
    _description = 'رویداد ممیزی تلنت سرچ'
    _order = 'id desc'
    _log_access = True

    event_type = fields.Char('نوع رویداد', required=True, index=True, readonly=True)
    actor_id = fields.Many2one('res.users', 'کاربر', readonly=True, index=True, ondelete='restrict')
    member_id = fields.Many2one('ts.workspace.member', 'عضویت', readonly=True, ondelete='set null')
    workspace_id = fields.Many2one('ts.workspace', 'فضای کاری', readonly=True, index=True, ondelete='restrict')
    purpose = fields.Selection(related='workspace_id.purpose', store=True, readonly=True)
    res_model = fields.Char('مدل', readonly=True, index=True)
    res_id = fields.Integer('شناسه رکورد', readonly=True)
    detail = fields.Text('جزئیات (JSON)', readonly=True)
    outcome = fields.Selection([('ok', 'انجام شد'), ('denied', 'ردشد'), ('error', 'خطا')], 'نتیجه',
                               default='ok', readonly=True)
    route = fields.Char('مسیر', readonly=True)
    request_id = fields.Char('شناسهٔ درخواست', readonly=True)
    ip_hash = fields.Char('IP (درهم)', readonly=True)
    ip_address = fields.Char('IP (قدیمی؛ دیگر نوشته نمی‌شود)', readonly=True)

    _res_idx = models.Index('(res_model, res_id)')
    _ws_event_idx = models.Index('(workspace_id, event_type, create_date)')

    # ------------------------------------------------------------ request facts
    @api.model
    def _ip_salt(self):
        ICP = self.env['ir.config_parameter'].sudo()
        salt = ICP.get_param('ts_core.audit_ip_salt')
        if not salt:
            salt = secrets.token_hex(16)
            ICP.set_param('ts_core.audit_ip_salt', salt)
        return salt

    @api.model
    def _hash_ip(self, ip):
        return hashlib.sha256((self._ip_salt() + ip).encode()).hexdigest()[:16] if ip else False

    @api.model
    def _request_facts(self):
        try:
            from odoo.http import request
            if request and request.httprequest:
                rid = getattr(request, '_ts_request_id', None)
                if not rid:
                    rid = request._ts_request_id = secrets.token_hex(6)
                return {'ip_hash': self._hash_ip(request.httprequest.remote_addr),
                        'route': route_of(request.httprequest.path), 'request_id': rid}
        except (ImportError, RuntimeError):
            pass
        return {}

    # ------------------------------------------------------------ writing
    @api.model
    def log(self, event_type, record=None, workspace=None, member=None, outcome='ok', **detail):
        """Record one audit event. ``record`` may be any recordset of size <= 1."""
        detail = clean_detail(detail)
        vals = {
            'event_type': event_type,
            'actor_id': self.env.uid,
            'member_id': member.id if member else False,
            'workspace_id': workspace.id if workspace else (
                record.workspace_id.id if record and 'workspace_id' in record._fields else False),
            'res_model': record._name if record else False,
            'res_id': record.id if record else 0,
            'detail': json.dumps(detail, ensure_ascii=False, default=str) if detail else False,
            'outcome': outcome,
        }
        vals.update(self._request_facts())
        return self.sudo().with_context(ts_audit_create=True).create(vals)

    @api.model
    def log_denied(self, event_type, route=None, workspace_id=None, member_id=None, **detail):
        """A deny event survives the rollback that follows a 404/403: it is written and committed through
        its own cursor. At most one row per user, route and minute."""
        facts = self._request_facts()
        if route:
            facts['route'] = route_of(route)
        uid = self.env.uid
        with self.env.registry.cursor() as cr:
            env = api.Environment(cr, uid, {})
            Audit = env['ts.audit.event'].sudo()
            route = facts.get('route')
            recent = Audit.search_count([
                ('event_type', '=', event_type), ('actor_id', '=', uid), ('route', '=', route),
                ('outcome', '=', 'denied'),
                ('create_date', '>=', fields.Datetime.subtract(fields.Datetime.now(), minutes=1))])
            if recent:
                return False
            vals = dict(facts, event_type=event_type, actor_id=uid, outcome='denied',
                        workspace_id=workspace_id or False, member_id=member_id or False, res_id=0,
                        detail=json.dumps(clean_detail(detail), ensure_ascii=False, default=str) if detail else False)
            Audit.with_context(ts_audit_create=True).create(vals)
            cr.commit()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('ts_audit_create'):
            raise UserError('رویداد ممیزی فقط از طریق سامانه ثبت می‌شود.')
        return super().create(vals_list)

    def write(self, vals):
        raise UserError('رویدادهای ممیزی قابل ویرایش نیستند.')

    def unlink(self):
        raise UserError('رویدادهای ممیزی قابل حذف نیستند.')
