import uuid
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ts_core.models.workspace import ROLES, ROLES_BY_PURPOSE

from .panel import norm_email, norm_phone

INVITE_DAYS = 7
MAX_PENDING = 20


class TsMemberInvite(models.Model):
    """Invitation of a colleague (specialist, manager, second admin) into a workspace. The link is bound to
    ONE identity (verified mobile or email), expires, and can be revoked."""
    _name = 'ts.member.invite'
    _description = 'Talent Search workspace member invitation'
    _order = 'id desc'

    workspace_id = fields.Many2one('ts.workspace', required=True, ondelete='cascade', index=True)
    role = fields.Selection(ROLES, 'نقش', required=True)
    phone = fields.Char('موبایل دعوت‌شده')
    email = fields.Char('ایمیل دعوت‌شده')
    token = fields.Char(required=True, copy=False, index=True, default=lambda s: uuid.uuid4().hex)
    invited_by_id = fields.Many2one('res.users', readonly=True, default=lambda s: s.env.user)
    expires_at = fields.Datetime(required=True, default=lambda s: fields.Datetime.now() + timedelta(days=INVITE_DAYS))
    state = fields.Selection([('pending', 'در انتظار'), ('accepted', 'پذیرفته'), ('revoked', 'لغو')],
                             default='pending', required=True, index=True)
    accepted_at = fields.Datetime(readonly=True)
    member_id = fields.Many2one('ts.workspace.member', readonly=True, ondelete='set null')
    sms_sent = fields.Boolean(readonly=True)

    _token_unique = models.Constraint('unique(token)', 'توکن دعوت باید یکتا باشد.')

    @api.constrains('phone', 'email', 'role', 'workspace_id')
    def _check_identity_role(self):
        for i in self:
            if not (i.phone or i.email):
                raise ValidationError('شمارهٔ موبایل یا ایمیل دعوت‌شده لازم است.')
            if i.role not in ROLES_BY_PURPOSE.get(i.workspace_id.purpose, set()):
                raise ValidationError('این نقش با نوع این پنل سازگار نیست.')

    # ------------------------------------------------------------ creation
    @api.model
    def ts_create(self, by_member, role, phone_raw=None, email_raw=None):
        ws = by_member.workspace_id
        if not by_member.has_perm('members:invite'):
            raise UserError('فقط مالک یا مدیر پنل می‌تواند همکار دعوت کند.')
        if role not in ROLES_BY_PURPOSE.get(ws.purpose, set()):
            raise UserError('این نقش برای این نوع پنل مجاز نیست.')
        if role == 'owner' and by_member.role != 'owner':
            raise UserError('فقط مالک می‌تواند مالک دیگری اضافه کند.')
        phone, email = norm_phone(phone_raw), norm_email(email_raw)
        if (phone_raw and not phone) or (email_raw and not email) or not (phone or email):
            raise UserError('شمارهٔ موبایل (۰۹۱۲۳۴۵۶۷۸۹) یا ایمیل معتبر وارد کنید.')
        S = self.sudo()
        pend = S.search([('workspace_id', '=', ws.id), ('state', '=', 'pending'), ('expires_at', '>', fields.Datetime.now())])
        if len(pend) >= MAX_PENDING:
            raise UserError('تعداد دعوت‌های در انتظار زیاد است؛ چند دعوت را لغو کنید.')
        if any(p.role == role and ((phone and p.phone == phone) or (email and p.email == email)) for p in pend):
            raise UserError('برای این نفر و نقش دعوت در انتظار وجود دارد.')
        inv = S.create({'workspace_id': ws.id, 'role': role, 'phone': phone or False, 'email': email or False,
                        'invited_by_id': by_member.user_id.id})
        self.env['ts.audit.event'].sudo().log('member.invite', inv, workspace=ws, role=role,
                                              by=by_member.user_id.id, via='phone' if phone else 'email')
        return inv

    # ------------------------------------------------------------- reading
    def invite_url(self):
        self.ensure_one()
        base = self.env.ref('ts_website.website_ts').domain or ''
        return '%s/join/%s' % (base.rstrip('/'), self.token)

    def usable_state(self):
        """ok | expired | accepted | revoked | suspended"""
        self.ensure_one()
        if self.state != 'pending':
            return self.state
        if self.expires_at < fields.Datetime.now():
            return 'expired'
        if self.workspace_id.state not in ('pilot', 'active'):
            return 'suspended'
        return 'ok'

    def matches(self, user):
        """Does this signed-in user hold the identity the link was issued to?"""
        self.ensure_one()
        if self.phone and self.phone in user._ts_verified_phones():
            return True
        ident = (user.email or '').strip().lower() or (user.login or '').strip().lower()
        return bool(self.email and ident == self.email)

    # ------------------------------------------------------------ acceptance
    def action_accept(self, user, license_number=None):
        self.ensure_one()
        st = self.usable_state()
        if st != 'ok':
            raise UserError('این دعوت دیگر معتبر نیست.')
        if not user.share or user._is_public():
            raise UserError('با حساب کاربری خود وارد شوید.')
        if not self.matches(user):
            raise UserError('این دعوت برای شمارهٔ موبایل یا ایمیل دیگری صادر شده است.')
        if self.role in ('clinician', 'clinic_director') and not (license_number or '').strip():
            raise UserError('شمارهٔ پروانه یا نظام حرفه‌ای لازم است.')
        M = self.env['ts.workspace.member'].sudo()
        if M.search_count([('workspace_id', '=', self.workspace_id.id), ('user_id', '=', user.id), ('active', '=', True)]):
            raise UserError('شما هم‌اکنون عضو فعال این پنل هستید؛ نقش را مالک پنل تغییر می‌دهد.')
        member = M.create({'workspace_id': self.workspace_id.id, 'user_id': user.id, 'role': self.role,
                           'license_number': (license_number or '').strip()[:60] or False})
        self.sudo().write({'state': 'accepted', 'accepted_at': fields.Datetime.now(), 'member_id': member.id})
        self.env['ts.audit.event'].sudo().log('member.invite_accept', self, workspace=self.workspace_id,
                                              role=self.role, user=user.id)
        return member

    def action_revoke(self):
        for i in self:
            if i.state == 'pending':
                i.sudo().state = 'revoked'
                self.env['ts.audit.event'].sudo().log('member.invite_revoke', i, workspace=i.workspace_id, role=i.role)

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('state', '!=', 'accepted'),
                            ('create_date', '<', fields.Datetime.now() - timedelta(days=90))]).unlink()
