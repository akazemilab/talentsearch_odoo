import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Who may do what inside a workspace (blueprint §4, purpose-bound roles).
INVITE_ROLES = {'owner', 'hr_admin', 'hiring_manager', 'clinic_director', 'clinician', 'counselor'}
VIEW_ROLES = INVITE_ROLES | {'reviewer'}
# Roles that need a recorded professional verification before they can act.
VERIFIED_ROLES = {'clinician', 'clinic_director'}
# Education: the institute's owner and counselors read the participant report (never the answers).
EDU_ROLES = {'owner', 'counselor'}
# Owners and managers see every result of the workspace; other specialists see only
# the participants they are responsible for (plus the unassigned queue where allowed).
SEE_ALL_ROLES = {'owner', 'hr_admin', 'clinic_director', 'reviewer'}
RESPONSIBLE_ROLES = INVITE_ROLES

from odoo.addons.ts_assessment.models.loader import EMPLOYMENT_CATEGORIES  # noqa: F401 (single source)

SHARE_LEVELS = [
    ('none', 'بدون اشتراک نتیجه'),
    ('summary', 'خلاصهٔ بازه‌ها (بدون پاسخ‌ها و متن تفسیر)'),
    ('clinical', 'گزارش کامل برای متخصص بالینی تأییدشده'),
]


class TsAssignment(models.Model):
    """An invitation from a workspace to one participant for one instrument.

    Data separation (blueprint §3): the organization never reads answers.
    Employment workspaces see status and, only if the participant agrees, the
    band per dimension. Clinical workspaces show the full report, including the
    professional guidance texts, only to verified clinicians."""
    _name = 'ts.assignment'
    _description = 'Talent Search assignment'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char('شناسه', readonly=True, copy=False, default='/')
    workspace_id = fields.Many2one('ts.workspace', 'فضای کاری', required=True, index=True, ondelete='restrict')
    purpose = fields.Selection(related='workspace_id.purpose', store=True)
    instrument_id = fields.Many2one('ts.instrument', 'سنجه', required=True, ondelete='restrict',
                                    domain=[('state', '=', 'published')])
    invitee_name = fields.Char('نام شرکت‌کننده', required=True)
    invitee_email = fields.Char('ایمیل شرکت‌کننده')
    note = fields.Char('یادداشت برای شرکت‌کننده')
    token = fields.Char(required=True, copy=False, index=True, default=lambda s: uuid.uuid4().hex)
    invited_by_id = fields.Many2one('res.users', 'دعوت‌کننده', readonly=True, default=lambda s: s.env.user)
    user_id = fields.Many2one('res.users', 'حساب شرکت‌کننده', readonly=True, index=True)
    attempt_id = fields.Many2one('ts.attempt', 'اجرا', readonly=True)
    share_level = fields.Selection(SHARE_LEVELS, 'اشتراک نتیجه', readonly=True, default='none')
    accepted_at = fields.Datetime('پذیرش', readonly=True)
    deadline = fields.Date('مهلت')
    state = fields.Selection([
        ('invited', 'دعوت‌شده'),
        ('accepted', 'پذیرفته'),
        ('in_progress', 'در حال پاسخ'),
        ('done', 'تکمیل‌شده'),
        ('declined', 'ردشده'),
        ('withdrawn', 'لغوشده'),
    ], 'وضعیت', compute='_compute_state', store=True, tracking=True)
    responsible_id = fields.Many2one(
        'ts.workspace.member', 'کارشناس مسئول', index=True, ondelete='set null',
        domain="[('workspace_id', '=', workspace_id), ('active', '=', True)]",
        help='کارشناسی که نتیجهٔ این شرکت‌کننده را می‌بیند. مالک و مدیر همه را می‌بینند.')
    withdrawn = fields.Boolean(readonly=True)
    declined = fields.Boolean(readonly=True)
    company_id = fields.Many2one(related='workspace_id.company_id', store=True)

    _token_unique = models.Constraint('unique(token)', 'توکن دعوت باید یکتا باشد.')

    @api.depends('withdrawn', 'declined', 'user_id', 'attempt_id.state')
    def _compute_state(self):
        for a in self:
            if a.withdrawn:
                a.state = 'withdrawn'
            elif a.declined:
                a.state = 'declined'
            elif a.attempt_id.state == 'done':
                a.state = 'done'
            elif a.attempt_id.state == 'in_progress':
                a.state = 'in_progress'
            elif a.user_id:
                a.state = 'accepted'
            else:
                a.state = 'invited'

    @api.constrains('instrument_id', 'workspace_id')
    def _check_instrument_fits_purpose(self):
        for a in self:
            if a.instrument_id.state != 'published':
                raise ValidationError('فقط سنجهٔ منتشرشده قابل دعوت است.')
            if a.purpose == 'employment' and a.instrument_id.purpose != 'employment':
                raise ValidationError('این سنجه برای فرایند استخدام مجاز نیست.')
            if a.workspace_id.state not in ('pilot', 'active'):
                raise ValidationError('فضای کاری فعال نیست.')

    @api.constrains('responsible_id', 'workspace_id', 'user_id')
    def _check_responsible(self):
        for a in self:
            r = a.responsible_id
            if not r:
                continue
            if r.workspace_id != a.workspace_id or not r.active or r.role not in RESPONSIBLE_ROLES:
                raise ValidationError('کارشناس مسئول باید عضو فعال همین فضای کاری با نقش کارشناس باشد.')
            if a.user_id and r.user_id == a.user_id:
                raise ValidationError('شرکت‌کننده نمی‌تواند کارشناس مسئولِ خودش باشد.')

    def write(self, vals):
        old = {a.id: a.responsible_id.id for a in self} if 'responsible_id' in vals else {}
        res = super().write(vals)
        for a in self:
            if a.id in old and old[a.id] != a.responsible_id.id:
                self.env['ts.audit.event'].log('assignment.responsible_change', a, workspace=a.workspace_id,
                                               old=old[a.id] or False, new=a.responsible_id.id or False)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        Member = self.env['ts.workspace.member']
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('ts.assignment') or '/'
            if 'responsible_id' not in vals and vals.get('workspace_id'):
                default = Member.ts_default_responsible(vals['workspace_id'],
                                                        vals.get('invited_by_id') or self.env.uid)
                if default:
                    vals['responsible_id'] = default.id
        recs = super().create(vals_list)
        for a in recs:
            self.env['ts.audit.event'].log('assignment.create', a, workspace=a.workspace_id,
                                           instrument=a.instrument_id.code)
        return recs

    # --------------------------------------------------------------- helpers
    def invite_url(self):
        self.ensure_one()
        base = self.env.ref('ts_website.website_ts').domain or ''
        return '%s/invite/%s' % (base.rstrip('/'), self.token)

    def default_share_level(self):
        self.ensure_one()
        return 'clinical' if self.purpose == 'clinical' else 'summary'

    def action_accept(self, user, share):
        """Participant accepts; creates the attempt tied to the workspace."""
        self.ensure_one()
        if self.state in ('withdrawn', 'declined'):
            raise UserError('این دعوت دیگر معتبر نیست.')
        if self.user_id and self.user_id != user:
            raise UserError('این دعوت قبلاً با حساب دیگری پذیرفته شده است.')
        if not self.user_id:
            share_level = self.default_share_level() if share else 'none'
            if self.responsible_id.user_id == user:
                # nobody is their own responsible specialist: back to the unassigned queue
                self.responsible_id = False
            inst = self.instrument_id
            attempt = self.env['ts.attempt'].create({
                'user_id': user.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id,
                'workspace_id': self.workspace_id.id,
            })
            self.write({'user_id': user.id, 'attempt_id': attempt.id, 'share_level': share_level,
                        'accepted_at': fields.Datetime.now()})
            self.env['ts.audit.event'].log('assignment.accept', self, workspace=self.workspace_id,
                                           share=share_level)
        return self.attempt_id

    def action_decline(self, user):
        self.ensure_one()
        if self.user_id and self.user_id != user:
            raise UserError('این دعوت متعلق به حساب دیگری است.')
        if self.attempt_id.state == 'done':
            raise UserError('سنجهٔ تکمیل‌شده قابل رد نیست.')
        self.write({'declined': True, 'user_id': self.user_id.id or user.id})
        self.env['ts.audit.event'].log('assignment.decline', self, workspace=self.workspace_id)

    def action_withdraw(self):
        for a in self:
            if a.state == 'done':
                raise UserError('دعوتِ تکمیل‌شده قابل لغو نیست.')
            a.withdrawn = True
            self.env['ts.audit.event'].log('assignment.withdraw', a, workspace=a.workspace_id)

    def action_revoke_share(self, user):
        """The participant can stop sharing at any time."""
        self.ensure_one()
        if self.user_id != user:
            raise UserError('دسترسی ندارید.')
        self.share_level = 'none'
        self.env['ts.audit.event'].log('assignment.share_revoke', self, workspace=self.workspace_id)

    def visible_results(self, member):
        """What `member` (ts.workspace.member) may see of this assignment's result.

        Returns (level, results) with level in 'none' | 'summary' | 'clinical'."""
        self.ensure_one()
        empty = self.env['ts.attempt.result']
        if member.workspace_id != self.workspace_id or not member.can_act():
            return 'none', empty
        if not member.can_see(self):
            return 'none', empty
        if self.state != 'done' or self.share_level == 'none' or not self.attempt_id.released:
            return 'none', empty
        results = self.attempt_id.result_rows()
        if self.purpose == 'clinical':
            if self.share_level == 'clinical' and member.role in VERIFIED_ROLES:
                return 'clinical', results
            return 'none', empty
        if self.purpose == 'employment' and self.share_level == 'summary' and member.role in VIEW_ROLES:
            return 'summary', results
        if self.purpose == 'education' and self.share_level == 'summary' and member.role in EDU_ROLES:
            return 'education', results
        return 'none', empty


class TsWorkspaceMember(models.Model):
    _inherit = 'ts.workspace.member'

    def can_act(self):
        self.ensure_one()
        if not self.active or self.workspace_id.state not in ('pilot', 'active'):
            return False
        if self.role in VERIFIED_ROLES and self.verification_state != 'verified':
            return False
        return True

    def can_invite(self):
        return self.can_act() and self.role in INVITE_ROLES

    # ------------------------------------------------ responsible specialist
    def sees_all(self):
        self.ensure_one()
        return self.role in SEE_ALL_ROLES

    def sees_unassigned(self):
        """Owners and managers always; counselors only in education workspaces."""
        self.ensure_one()
        return self.sees_all() or (self.workspace_id.purpose == 'education' and self.role == 'counselor')

    def can_assign(self):
        """Who may hand a participant to a specialist: owner and managers."""
        self.ensure_one()
        return self.can_act() and self.sees_all() and self.role != 'reviewer'

    def can_see(self, rec):
        """rec is a ts.assignment or an imported ts.attempt with a responsible_id."""
        self.ensure_one()
        if rec.workspace_id != self.workspace_id:
            return False
        if self.sees_all():
            return True
        if rec.responsible_id:
            return rec.responsible_id == self
        return self.sees_unassigned()

    @api.model
    def ts_default_responsible(self, workspace_id, user_id):
        """The inviter is responsible if they are a specialist; an owner only when working alone."""
        m = self.sudo().search([('workspace_id', '=', int(workspace_id)), ('user_id', '=', user_id),
                                ('active', '=', True)], limit=1)
        if not m or m.role not in RESPONSIBLE_ROLES or not m.can_act():
            return self.browse()
        if m.role == 'owner' and self.sudo().search_count(
                [('workspace_id', '=', m.workspace_id.id), ('active', '=', True)]) > 1:
            return self.browse()
        return m

    def allowed_instruments(self):
        self.ensure_one()
        dom = [('state', '=', 'published')]
        if self.workspace_id.purpose == 'employment':
            dom.append(('purpose', '=', 'employment'))
        elif self.workspace_id.purpose == 'education':
            # institutes invite students to the interactive talent inventory only
            dom.append(('code', '=', 'TALENT-INV-15'))
        return self.env['ts.instrument'].sudo().search(dom)
