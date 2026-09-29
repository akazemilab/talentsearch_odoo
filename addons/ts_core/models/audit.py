import json

from odoo import api, fields, models
from odoo.exceptions import UserError


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
    workspace_id = fields.Many2one('ts.workspace', 'فضای کاری', readonly=True, index=True, ondelete='restrict')
    purpose = fields.Selection(related='workspace_id.purpose', store=True, readonly=True)
    res_model = fields.Char('مدل', readonly=True, index=True)
    res_id = fields.Integer('شناسه رکورد', readonly=True)
    detail = fields.Text('جزئیات (JSON)', readonly=True)
    ip_address = fields.Char('IP', readonly=True)

    @api.model
    def log(self, event_type, record=None, workspace=None, **detail):
        """Record one audit event. ``record`` may be any recordset of size <= 1."""
        ip = False
        try:
            from odoo.http import request
            if request and request.httprequest:
                ip = request.httprequest.remote_addr
        except (ImportError, RuntimeError):
            pass
        vals = {
            'event_type': event_type,
            'actor_id': self.env.uid,
            'workspace_id': workspace.id if workspace else (
                record.workspace_id.id if record and 'workspace_id' in record._fields else False),
            'res_model': record._name if record else False,
            'res_id': record.id if record else 0,
            'detail': json.dumps(detail, ensure_ascii=False, default=str) if detail else False,
            'ip_address': ip,
        }
        return self.sudo().with_context(ts_audit_create=True).create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('ts_audit_create'):
            raise UserError('رویداد ممیزی فقط از طریق سامانه ثبت می‌شود.')
        return super().create(vals_list)

    def write(self, vals):
        raise UserError('رویدادهای ممیزی قابل ویرایش نیستند.')

    def unlink(self):
        raise UserError('رویدادهای ممیزی قابل حذف نیستند.')
