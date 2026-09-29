import base64

from odoo import fields, models, _
from odoo.exceptions import UserError

LIMITS = {'image/jpeg': 10, 'image/gif': 10, 'video/mp4': 20}  # MB


class KavenegarMedia(models.Model):
    _name = 'kavenegar.media'
    _description = 'Kavenegar media (internal messenger lines)'
    _order = 'id desc'

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    file = fields.Binary(attachment=True)
    filename = fields.Char()
    mimetype = fields.Char()
    remote_id = fields.Char('Media id (GUID)', readonly=True, copy=False, index=True)
    remote_info = fields.Text(readonly=True)

    def action_upload(self):
        for m in self:
            if not m.company_id.kv_has_messenger:
                raise UserError(_('Media needs an internal messenger line (enable it in Settings).'))
            if not m.file:
                raise UserError(_('Choose a file.'))
            mime = m.mimetype or ('video/mp4' if (m.filename or '').lower().endswith('.mp4')
                                  else 'image/gif' if (m.filename or '').lower().endswith('.gif') else 'image/jpeg')
            raw = base64.b64decode(m.file)
            if mime not in LIMITS or len(raw) > LIMITS[mime] * 1024 * 1024:
                raise UserError(_('Allowed: jpg/gif up to 10 MB, mp4 up to 20 MB (max 60 s).'))
            res = m.company_id._kv_call(m.company_id._kv_client().media_upload, m.filename or m.name, raw, mime)
            e = res[0] if res else {}
            m.write({'remote_id': str(e.get('id') or e.get('mediaid') or ''), 'remote_info': str(e)})
        return True

    def action_info(self):
        for m in self.filtered('remote_id'):
            res = m.company_id._kv_call(m.company_id._kv_client().media_get, m.remote_id)
            m.remote_info = str(res[0] if res else '')
        return True

    def action_delete_remote(self):
        for m in self.filtered('remote_id'):
            m.company_id._kv_call(m.company_id._kv_client().media_delete, m.remote_id)
            m.remote_id = False
        return True
