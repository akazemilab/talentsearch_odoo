from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

PURPOSES = [
    ('employment', 'استخدام و منابع انسانی'),
    ('clinical', 'بالینی و مشاوره'),
    ('education', 'دانشگاه و مدرسه'),
    ('benefits', 'رفاه کارکنان'),
]
# Organizations, clinics and benefit programs are reviewed by the platform owner before the first real
# participant can be invited (the panel may already be set up and colleagues invited). Education
# (schools, counseling centers) is active immediately.
GATED_PURPOSES = {'employment', 'clinical', 'benefits'}

ROLES_BY_PURPOSE = {
    'employment': {'owner', 'hr_admin', 'hiring_manager', 'reviewer'},
    'clinical': {'owner', 'clinic_director', 'clinician'},
    'education': {'owner', 'counselor'},
    'benefits': {'owner', 'benefit_admin'},
}
ROLES = [
    ('owner', 'مالک سازمان'),
    ('hr_admin', 'مدیر منابع انسانی'),
    ('hiring_manager', 'مدیر استخدام'),
    ('reviewer', 'ارزیاب'),
    ('clinic_director', 'مدیر مرکز بالینی'),
    ('clinician', 'متخصص بالینی دارای مجوز'),
    ('counselor', 'مشاور'),
    ('benefit_admin', 'مدیر طرح رفاهی'),
]


class TsWorkspace(models.Model):
    """Top tenancy boundary (blueprint §4). One organization can hold several
    workspaces, one per purpose; data never crosses workspaces or purposes."""
    _name = 'ts.workspace'
    _description = 'فضای کاری تلنت سرچ'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char('نام فضای کاری', required=True, tracking=True)
    code = fields.Char('کد', readonly=True, copy=False, index=True, default='/')
    purpose = fields.Selection(PURPOSES, 'هدف', required=True, tracking=True,
                               help='هدف فضای کاری پس از فعال‌سازی قابل تغییر نیست.')
    partner_id = fields.Many2one('res.partner', 'سازمان', required=True, tracking=True, index=True,
                                 domain=[('is_company', '=', True)])
    state = fields.Selection([
        ('draft', 'پیش‌نویس'),
        ('pilot', 'پایلوت'),
        ('active', 'فعال'),
        ('suspended', 'معلق'),
        ('closed', 'بسته'),
    ], 'وضعیت', default='draft', required=True, tracking=True)
    gated = fields.Boolean('نیازمند تأیید', compute='_compute_gated', store=True,
                           help='هدف‌های دانشگاه/مدرسه و رفاه کارکنان تا تأیید مالک پلتفرم غیرفعال می‌مانند.')
    approved_by_id = fields.Many2one('res.users', 'تأییدکنندهٔ مالک پلتفرم', readonly=True, copy=False)
    approved_on = fields.Datetime('تاریخ تأیید', readonly=True, copy=False)
    approval_note = fields.Char('یادداشت تأیید', copy=False)
    rejected_on = fields.Datetime('تاریخ رد', readonly=True, copy=False)
    rejection_note = fields.Char('دلیل رد (برای مالک پنل نمایش داده می‌شود)', copy=False)
    terms_version = fields.Char('نسخهٔ شرایط پذیرفته‌شده', readonly=True, copy=False)
    terms_accepted_on = fields.Datetime('تاریخ پذیرش شرایط', readonly=True, copy=False)
    terms_accepted_by_id = fields.Many2one('res.users', 'پذیرنده‌ی شرایط', readonly=True, copy=False)
    owner_user_id = fields.Many2one('res.users', 'مالک پنل', compute='_compute_owner_user')
    member_ids = fields.One2many('ts.workspace.member', 'workspace_id', 'اعضا')
    member_count = fields.Integer(compute='_compute_member_count')
    data_contact_id = fields.Many2one('res.partner', 'مسئول داده', tracking=True)
    escalation_contact_id = fields.Many2one('res.partner', 'مسئول پاسخ فوری بالینی', tracking=True,
                                            help='برای فضای بالینی الزامی است پیش از فعال‌سازی.')
    note = fields.Html('یادداشت داخلی')
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)

    _code_unique = models.Constraint('unique(code)', 'کد فضای کاری باید یکتا باشد.')

    @api.depends('member_ids.role', 'member_ids.active', 'member_ids.user_id')
    def _compute_owner_user(self):
        for ws in self:
            ws.owner_user_id = ws.member_ids.filtered(lambda m: m.active and m.role == 'owner')[:1].user_id

    @api.depends('purpose', 'approved_on')
    def _compute_gated(self):
        for ws in self:
            ws.gated = ws.purpose in GATED_PURPOSES and not ws.approved_on

    def action_approve(self):
        """Platform-owner approval that lifts the gate on one education/benefits
        workspace (rights, consent and operations reviewed for that customer)."""
        if not self.env.user.has_group('ts_core.group_ts_manager'):
            raise UserError('فقط مدیر پلتفرم می‌تواند فضای کاری را تأیید کند.')
        for ws in self:
            if ws.purpose not in GATED_PURPOSES:
                raise UserError('این فضای کاری نیاز به تأیید ندارد.')
            if ws.approved_on:
                continue
            ws.write({'approved_by_id': self.env.uid, 'approved_on': fields.Datetime.now(),
                      'rejected_on': False, 'rejection_note': False})
            self.env['ts.audit.event'].log('workspace.approve', ws, workspace=ws, purpose=ws.purpose)

    def _check_manager(self):
        if not self.env.user.has_group('ts_core.group_ts_manager'):
            raise UserError('فقط مدیر پلتفرم می‌تواند این کار را انجام دهد.')

    def action_reject(self):
        """Platform owner declines a pending panel; the note is shown to the panel owner."""
        self._check_manager()
        for ws in self:
            if not ws.gated:
                raise UserError('این فضای کاری در انتظار تأیید نیست.')
            if not ws.rejection_note:
                raise UserError('دلیل رد را در فیلد «دلیل رد» بنویسید.')
            ws.rejected_on = fields.Datetime.now()
            self.env['ts.audit.event'].log('workspace.reject', ws, workspace=ws, purpose=ws.purpose,
                                           note=ws.rejection_note)

    def action_suspend(self):
        self._check_manager()
        for ws in self:
            if ws.state not in ('pilot', 'active'):
                raise UserError('فقط فضای پایلوت یا فعال معلق می‌شود.')
            ws.write({'state': 'suspended'})
            self.env['ts.audit.event'].log('workspace.suspend', ws, workspace=ws, note=ws.approval_note or False)

    def action_resume(self):
        self._check_manager()
        for ws in self:
            if ws.state != 'suspended':
                raise UserError('این فضای کاری معلق نیست.')
            ws.write({'state': 'pilot'})
            self.env['ts.audit.event'].log('workspace.resume', ws, workspace=ws)

    def _compute_member_count(self):
        for ws in self:
            ws.member_count = len(ws.member_ids.filtered('active'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', '/') == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('ts.workspace') or '/'
        records = super().create(vals_list)
        for ws in records:
            self.env['ts.audit.event'].log('workspace.create', ws, workspace=ws, purpose=ws.purpose)
        return records

    def write(self, vals):
        if 'purpose' in vals:
            locked = self.filtered(lambda w: w.state != 'draft' and w.purpose != vals['purpose'])
            if locked:
                raise UserError('هدف فضای کاری پس از خروج از پیش‌نویس قابل تغییر نیست.')
        res = super().write(vals)
        if 'state' in vals:
            for ws in self:
                self.env['ts.audit.event'].log('workspace.state', ws, workspace=ws, state=vals['state'])
        return res

    @api.constrains('state', 'purpose', 'escalation_contact_id')
    def _check_activation(self):
        for ws in self:
            if ws.state in ('pilot', 'active'):
                if ws.gated and ws.state == 'active':
                    raise ValidationError('این نوع فضای کاری هنوز تأیید نشده و قابل فعال‌سازی نیست.')
                if ws.purpose == 'clinical' and not ws.escalation_contact_id:
                    raise ValidationError('فضای بالینی بدون مسئول پاسخ فوری فعال نمی‌شود.')

    def action_view_audit(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'رویدادهای ممیزی', 'res_model': 'ts.audit.event',
            'view_mode': 'list,form', 'domain': [('workspace_id', '=', self.id)],
        }


class TsWorkspaceMember(models.Model):
    _name = 'ts.workspace.member'
    _description = 'عضو فضای کاری تلنت سرچ'
    _order = 'workspace_id, role'

    workspace_id = fields.Many2one('ts.workspace', required=True, ondelete='cascade', index=True)
    purpose = fields.Selection(related='workspace_id.purpose', store=True)
    user_id = fields.Many2one('res.users', 'کاربر', required=True, index=True, ondelete='restrict')
    role = fields.Selection(ROLES, 'نقش', required=True)
    active = fields.Boolean(default=True)
    # Professional verification (blueprint journey B1): clinicians unlock
    # clinical instruments only once an operator records the verification.
    license_number = fields.Char('شماره پروانه/نظام')
    verification_state = fields.Selection([
        ('not_required', 'لازم نیست'),
        ('pending', 'در انتظار بررسی'),
        ('verified', 'تأیید شده'),
        ('rejected', 'رد شده'),
    ], 'وضعیت احراز صلاحیت', compute='_compute_verification_state', store=True, readonly=False)
    verified_by_id = fields.Many2one('res.users', 'تأییدکننده', readonly=True)
    verified_on = fields.Datetime('تاریخ تأیید', readonly=True)

    _user_ws_role_unique = models.Constraint('unique(workspace_id, user_id, role)', 'این نقش قبلاً برای این کاربر ثبت شده است.')

    @api.depends('role')
    def _compute_verification_state(self):
        for m in self:
            if not m.verification_state or m.verification_state == 'not_required':
                m.verification_state = 'pending' if m.role in ('clinician', 'clinic_director', 'counselor') else 'not_required'

    @api.constrains('role', 'workspace_id')
    def _check_role_matches_purpose(self):
        for m in self:
            if m.role not in ROLES_BY_PURPOSE.get(m.purpose, set()):
                raise ValidationError('نقش «%s» با هدف این فضای کاری سازگار نیست.' % dict(ROLES)[m.role])

    @api.constrains('user_id')
    def _check_portal_user(self):
        for m in self:
            if not m.user_id.share:
                raise ValidationError('اعضای سازمان مشتری باید کاربر پرتال باشند، نه کاربر داخلی.')

    def action_verify(self):
        if not self.env.user.has_group('ts_core.group_ts_manager'):
            raise UserError('فقط مدیر پلتفرم می‌تواند صلاحیت را تأیید کند.')
        for m in self:
            if not m.license_number:
                raise UserError('شماره پروانه ثبت نشده است.')
            m.write({'verification_state': 'verified', 'verified_by_id': self.env.uid,
                     'verified_on': fields.Datetime.now()})
            self.env['ts.audit.event'].log('member.verify', m, workspace=m.workspace_id,
                                           user=m.user_id.id, role=m.role)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for m in records:
            self.env['ts.audit.event'].log('member.add', m, workspace=m.workspace_id, user=m.user_id.id, role=m.role)
        return records

    def write(self, vals):
        if vals.get('active') is False or ('role' in vals and vals['role'] != 'owner'):
            for m in self.filtered(lambda m: m.active and m.role == 'owner'):
                others = m.workspace_id.member_ids.filtered(lambda x: x.active and x.role == 'owner' and x not in self)
                if not others:
                    raise UserError('هر فضای کاری باید دست‌کم یک مالک فعال داشته باشد؛ ابتدا مالک دیگری اضافه کنید.')
        res = super().write(vals)
        if {'role', 'active', 'user_id'} & set(vals):
            for m in self:
                self.env['ts.audit.event'].log('member.change', m, workspace=m.workspace_id,
                                               **{k: vals[k] for k in ('role', 'active', 'user_id') if k in vals})
        return res
