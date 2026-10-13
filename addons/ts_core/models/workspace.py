from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

PURPOSES = [
    ('employment', 'استخدام و منابع انسانی'),
    ('clinical', 'مشاوره'),
    ('education', 'دانشگاه و مدرسه'),
    ('benefits', 'رفاه کارکنان'),
]
# Owner decision 2026-10-12 (onb1): no panel waits for approval. Every panel is active when it is created; misuse is
# handled after the fact (new-panel invite limit, super-admin suspend, the «پنل‌های تازه» back-office list, audit log).

ROLES_BY_PURPOSE = {
    'employment': {'owner', 'admin', 'hr_admin', 'hiring_manager', 'reviewer'},
    'clinical': {'owner', 'admin', 'clinic_director', 'clinician'},
    'education': {'owner', 'admin', 'counselor'},
    'benefits': {'owner', 'benefit_admin'},
}
ROLES = [
    ('owner', 'مالک پنل'),
    ('admin', 'هماهنگ‌کنندهٔ پنل'),
    ('hr_admin', 'مدیر منابع انسانی'),
    ('hiring_manager', 'مدیر استخدام'),
    ('reviewer', 'ارزیاب'),
    ('clinic_director', 'مدیر مرکز مشاوره'),
    ('clinician', 'مشاور مرکز دارای پروانه'),
    ('counselor', 'مشاور'),
    ('benefit_admin', 'مدیر طرح رفاهی'),
]


class TsWorkspace(models.Model):
    """Top tenancy boundary (blueprint §4). One organization can hold several
    workspaces, one per purpose; data never crosses workspaces or purposes."""
    _name = 'ts.workspace'
    _description = 'پنل استعدادیاب'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char('نام پنل', required=True, tracking=True)
    code = fields.Char('کد', readonly=True, copy=False, index=True, default='/')
    purpose = fields.Selection(PURPOSES, 'هدف', required=True, tracking=True,
                               help='هدف پنل پس از فعال‌سازی قابل تغییر نیست.')
    partner_id = fields.Many2one('res.partner', 'سازمان', required=True, tracking=True, index=True,
                                 domain=[('is_company', '=', True)])
    state = fields.Selection([
        ('draft', 'پیش‌نویس'),
        ('active', 'فعال'),
        ('suspended', 'متوقف'),
        ('closed', 'بسته'),
    ], 'وضعیت', default='draft', required=True, tracking=True)
    self_service = fields.Boolean('ساخته‌شده از سلف‌سرویس', readonly=True, copy=False,
                                  help='پنلی که مشتری خودش در /panel ساخته است؛ در هفتهٔ اول سقف روزانهٔ دعوت دارد.')
    suspend_note = fields.Char('دلیل توقف (داخلی)', copy=False,
                               help='فقط برای تیم استعدادیاب؛ به مالک پنل نشان داده نمی‌شود.')
    suspended_on = fields.Datetime('تاریخ توقف', readonly=True, copy=False)
    terms_version = fields.Char('نسخهٔ شرایط پذیرفته‌شده', readonly=True, copy=False)
    terms_accepted_on = fields.Datetime('تاریخ پذیرش شرایط', readonly=True, copy=False)
    terms_accepted_by_id = fields.Many2one('res.users', 'پذیرنده‌ی شرایط', readonly=True, copy=False)
    owner_user_id = fields.Many2one('res.users', 'مالک پنل', compute='_compute_owner_user')
    member_ids = fields.One2many('ts.workspace.member', 'workspace_id', 'اعضا')
    member_count = fields.Integer(compute='_compute_member_count')
    data_contact_id = fields.Many2one('res.partner', 'مسئول داده', tracking=True)
    escalation_contact_id = fields.Many2one('res.partner', 'مسئول پیگیری فوری', tracking=True,
                                            help='برای پنل مرکز مشاوره، پیش از نخستین دعوت مراجع الزامی است؛ '
                                                 'یک بار در صفحهٔ نخستین دعوت پرسیده می‌شود.')
    note = fields.Html('یادداشت داخلی')
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)

    _code_unique = models.Constraint('unique(code)', 'کد پنل باید یکتا باشد.')

    def ts_public_name(self):
        """The panel's name as participants see it (invite, consent, sharing, notifications). ts_brand overrides it with the
        report name a counseling center chose (public_name), falling back to this."""
        self.ensure_one()
        return (self.name or '').strip()

    @api.depends('member_ids.role', 'member_ids.active', 'member_ids.user_id')
    def _compute_owner_user(self):
        for ws in self:
            ws.owner_user_id = ws.member_ids.filtered(lambda m: m.active and m.role == 'owner')[:1].user_id

    def _check_manager(self):
        if not self.env.user.has_group('ts_core.group_ts_manager'):
            raise UserError('فقط مدیر پلتفرم می‌تواند این کار را انجام دهد.')

    def action_suspend(self):
        """Super admin stops a panel after misuse (owner decision 2026-10-12 replaces approval with this): members see
        a «stopped» page, no invitation or new attempt can start; participants keep their own results."""
        self._check_manager()
        for ws in self:
            if ws.state != 'active':
                raise UserError('فقط پنل فعال متوقف می‌شود.')
            ws.write({'state': 'suspended', 'suspended_on': fields.Datetime.now()})
            self.env['ts.audit.event'].log('workspace.suspend', ws, workspace=ws, has_note=bool(ws.suspend_note))

    def action_resume(self):
        self._check_manager()
        for ws in self:
            if ws.state != 'suspended':
                raise UserError('این پنل متوقف نیست.')
            ws.write({'state': 'active', 'suspended_on': False})
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
                raise UserError('هدف پنل پس از خروج از پیش‌نویس قابل تغییر نیست.')
        res = super().write(vals)
        if 'state' in vals:
            for ws in self:
                self.env['ts.audit.event'].log('workspace.state', ws, workspace=ws, state=vals['state'])
        return res

    # onb3 (2026-10-13): the escalation contact of a counseling-center panel is no longer asked when the panel is made.
    # It is asked once, inside the first client invitation, and every client invitation of a clinical panel requires it
    # (ts_org TsAssignment._check_escalation): no client of a clinical panel is ever invited while it is empty.

    def action_view_audit(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'رویدادهای ممیزی', 'res_model': 'ts.audit.event',
            'view_mode': 'list,form', 'domain': [('workspace_id', '=', self.id)],
        }


class TsWorkspaceMember(models.Model):
    _name = 'ts.workspace.member'
    _description = 'عضو پنل استعدادیاب'
    _order = 'workspace_id, role'

    workspace_id = fields.Many2one('ts.workspace', required=True, ondelete='cascade', index=True)
    purpose = fields.Selection(related='workspace_id.purpose', store=True)
    user_id = fields.Many2one('res.users', 'کاربر', required=True, index=True, ondelete='restrict')
    role = fields.Selection(ROLES, 'نقش', required=True)
    active = fields.Boolean(default=True)
    # Licence = a BADGE (owner decision 2026-10-12, onb1): the member enters it on his own profile; the super admin's
    # check adds «پروانهٔ تأییدشده» on the profile and reports. It never gates access. Editing the number resets the badge.
    license_number = fields.Char('شمارهٔ پروانه یا نظام روان‌شناسی و مشاوره')
    verification_state = fields.Selection([
        ('not_required', 'بدون شمارهٔ پروانه'),
        ('pending', 'ثبت‌شده، هنوز تأیید نشده'),
        ('verified', 'پروانهٔ تأییدشده'),
        ('rejected', 'تأیید نشد'),
    ], 'نشان پروانه', default='not_required', required=True, readonly=True)
    verified_by_id = fields.Many2one('res.users', 'تأییدکننده', readonly=True)
    verified_on = fields.Datetime('تاریخ تأیید', readonly=True)
    owner_practices = fields.Boolean(
        'مالک خودش هم کارشناس است', help='مالکی که خودش شرکت‌کنندگان را می‌بیند (مشاور یا روان‌شناس مستقل). '
        'مالک مرکز مشاوره که خودش مشاوره نمی‌دهد، برای حفظ حریم مراجعان فقط وضعیت دعوت‌ها را می‌بیند.')
    # onb1 risk review: when an owner of a counseling center started to counsel (and so sees full reports); the back
    # office reviews these after the fact in «مالک مشاور شد (بررسی پروانه)»
    practising_since = fields.Datetime('مشاوره از', readonly=True)
    deactivated_on = fields.Datetime('تاریخ غیرفعال‌سازی', readonly=True)
    deactivated_by_id = fields.Many2one('res.users', 'غیرفعال‌کننده', readonly=True)

    # one active membership per person per panel (the same person may hold roles in other panels)
    _one_active_member = models.UniqueIndex('(workspace_id, user_id) WHERE active IS TRUE')

    @api.constrains('role', 'workspace_id')
    def _check_role_matches_purpose(self):
        for m in self:
            if m.role not in ROLES_BY_PURPOSE.get(m.purpose, set()):
                raise ValidationError('نقش «%s» با هدف این پنل سازگار نیست.' % dict(ROLES)[m.role])

    @api.constrains('user_id')
    def _check_portal_user(self):
        for m in self:
            if not m.user_id.share:
                raise ValidationError('اعضای سازمان مشتری باید کاربر پرتال باشند، نه کاربر داخلی.')

    def action_verify(self):
        """Super admin checked the licence number: the member gets the «پروانهٔ تأییدشده» badge (no access changes)."""
        if not self.env.user.has_group('ts_core.group_ts_manager'):
            raise UserError('فقط مدیر پلتفرم می‌تواند پروانه را تأیید کند.')
        for m in self:
            if not m.license_number:
                raise UserError('شماره پروانه ثبت نشده است.')
            m.with_context(ts_licence_badge=True).write({
                'verification_state': 'verified', 'verified_by_id': self.env.uid, 'verified_on': fields.Datetime.now()})
            self.env['ts.audit.event'].log('member.verify', m, workspace=m.workspace_id,
                                           user=m.user_id.id, role=m.role)

    def action_unverify(self):
        """Super admin could not confirm the number: the badge is not shown (access unchanged)."""
        if not self.env.user.has_group('ts_core.group_ts_manager'):
            raise UserError('فقط مدیر پلتفرم می‌تواند نشان پروانه را تغییر دهد.')
        for m in self:
            m.with_context(ts_licence_badge=True).write({
                'verification_state': 'rejected' if m.license_number else 'not_required',
                'verified_by_id': self.env.uid, 'verified_on': fields.Datetime.now()})
            self.env['ts.audit.event'].log('member.unverify', m, workspace=m.workspace_id, user=m.user_id.id, role=m.role)

    @staticmethod
    def _ts_licence_vals(vals):
        """A new or edited licence number starts unverified; an empty one carries no badge."""
        if 'license_number' in vals:
            lic = (vals.get('license_number') or '').strip()[:60]
            vals = dict(vals, license_number=lic or False)
            if 'verification_state' not in vals:
                vals.update(verification_state='pending' if lic else 'not_required', verified_by_id=False, verified_on=False)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._ts_licence_vals(v) for v in vals_list]
        # a member is seen by colleagues by name: an account made by mobile code gives its name first (onb1)
        Users = self.env['res.users'].sudo()
        for v in vals_list:
            if v.get('user_id') and Users.browse(v['user_id']).partner_id.ts_name_unknown:
                raise UserError('پیش از پیوستن به پنل، نام و نام خانوادگی خود را بنویسید؛ همکاران شما را با این نام می‌بینند.')
        records = super().create(vals_list)
        for m in records:
            self.env['ts.audit.event'].log('member.add', m, workspace=m.workspace_id, user=m.user_id.id, role=m.role)
        return records

    def unlink(self):
        for m in self.filtered(lambda m: m.active and m.role == 'owner'):
            others = m.workspace_id.member_ids.filtered(lambda x: x.active and x.role == 'owner' and x not in self)
            if not others:
                raise UserError('هر پنل باید دست‌کم یک مالک فعال داشته باشد؛ ابتدا مالک دیگری اضافه کنید.')
        return super().unlink()

    def write(self, vals):
        if 'license_number' in vals and not self.env.context.get('ts_licence_badge'):
            new = (vals.get('license_number') or '').strip()[:60] or False
            changed = self.filtered(lambda m: (m.license_number or False) != new)
            if changed and changed != self:
                (self - changed).write({k: v for k, v in vals.items() if k != 'license_number'})
                return changed.write(vals)
            vals = self._ts_licence_vals(vals) if changed else {k: v for k, v in vals.items() if k != 'license_number'}
            if not vals:
                return True
        if vals.get('active') is False and 'deactivated_on' not in vals:
            vals = dict(vals, deactivated_on=fields.Datetime.now(), deactivated_by_id=self.env.uid)
        elif vals.get('active') is True:
            vals = dict(vals, deactivated_on=False, deactivated_by_id=False)
        if vals.get('active') is False or ('role' in vals and vals['role'] != 'owner'):
            for m in self.filtered(lambda m: m.active and m.role == 'owner'):
                others = m.workspace_id.member_ids.filtered(lambda x: x.active and x.role == 'owner' and x not in self)
                if not others:
                    raise UserError('هر پنل باید دست‌کم یک مالک فعال داشته باشد؛ ابتدا مالک دیگری اضافه کنید.')
        res = super().write(vals)
        if {'role', 'active', 'user_id'} & set(vals):
            for m in self:
                self.env['ts.audit.event'].log('member.change', m, workspace=m.workspace_id,
                                               **{k: vals[k] for k in ('role', 'active', 'user_id') if k in vals})
        return res
