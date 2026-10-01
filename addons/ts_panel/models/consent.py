"""Consent ledger (S15, PRV-1; 04_data_model.md 3.4).

Append-only: a row is written when a result is shared with a panel and when the person stops sharing (S16 adds the
service, research and guardian kinds). A row never holds free text, names or phone numbers: kind, version, ids, the share
level in a word and a hashed address only. Changing or deleting a row is refused for everyone.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

KINDS = [('service', 'خدمت'), ('research', 'پژوهش'), ('share', 'اشتراک نتیجه'), ('share_revoke', 'لغو اشتراک'),
         ('guardian', 'ولی'), ('guardian_attest', 'تأیید مؤسسه برای ولی'), ('assent', 'رضایت کودک'), ('sms', 'پیامک'),
         ('terms', 'شرایط پنل'), ('privacy', 'حریم خصوصی')]
SHARE_VERSION = 'TS-SHARE-1405-07-v1'


class TsConsentRecord(models.Model):
    _name = 'ts.consent.record'
    _description = 'Talent Search consent ledger'
    _order = 'id desc'

    kind = fields.Selection(KINDS, required=True, index=True, readonly=True)
    version = fields.Char(readonly=True)
    user_id = fields.Many2one('res.users', ondelete='set null', index=True, readonly=True)
    given_as = fields.Selection([('self', 'خود فرد'), ('guardian', 'ولی'), ('panel_member', 'عضو پنل')], default='self', readonly=True)
    method = fields.Selection([('checkbox', 'تیک'), ('otp_verified', 'کد پیامکی'), ('attestation', 'گواهی مؤسسه')],
                              default='checkbox', readonly=True)
    client_id = fields.Many2one('ts.panel.client', ondelete='set null', readonly=True)
    assignment_id = fields.Many2one('ts.assignment', ondelete='set null', index=True, readonly=True)
    attempt_id = fields.Many2one('ts.attempt', ondelete='set null', index=True, readonly=True)
    workspace_id = fields.Many2one('ts.workspace', ondelete='set null', index=True, readonly=True)
    campaign_id = fields.Many2one('ts.campaign', ondelete='set null', readonly=True)
    level = fields.Char(readonly=True)
    at = fields.Datetime(default=fields.Datetime.now, readonly=True, index=True)
    ip_hash = fields.Char(readonly=True)

    @api.model
    def _log(self, kind, user, assignment=None, attempt=None, workspace=None, level=False, version=False, method='checkbox',
             given_as='self', client=None):
        """Write one ledger row. Never raises into the caller's flow."""
        try:
            with self.env.cr.savepoint():
                vals = {'kind': kind, 'version': version or SHARE_VERSION, 'user_id': user.id if user else False,
                        'method': method, 'given_as': given_as, 'level': level or False,
                        'assignment_id': assignment.id if assignment else False,
                        'attempt_id': attempt.id if attempt else (assignment.attempt_id.id if assignment else False),
                        'workspace_id': workspace.id if workspace else (assignment.workspace_id.id if assignment else False),
                        'client_id': client.id if client else (assignment.client_id.id if assignment and 'client_id' in assignment._fields else False),
                        'ip_hash': self.env['ts.audit.event']._request_facts().get('ip_hash')}
                return self.sudo().with_context(ts_consent_create=True).create(vals)
        except Exception:                                       # the ledger must not break the action it records
            return self.browse()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('ts_consent_create'):
            raise UserError('سابقهٔ رضایت فقط از طریق سامانه ثبت می‌شود.')
        return super().create(vals_list)

    def write(self, vals):
        raise UserError('سابقهٔ رضایت قابل ویرایش نیست.')

    def unlink(self):
        raise UserError('سابقهٔ رضایت قابل حذف نیست.')
