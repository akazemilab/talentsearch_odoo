import uuid
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .perms import roles_with

# Who may do what inside a workspace now lives in perms.py (05_permissions_matrix.md). The sets below are kept,
# derived from that table, for old callers; `admin` (new in Panel v2) is not in them on purpose.
INVITE_TTL_DAYS = 30
INVITE_ROLES = roles_with('invites:create') - {'admin', 'benefit_admin'}
VIEW_ROLES = roles_with('results:summary') | {'reviewer'}
VERIFIED_ROLES = {'clinician', 'clinic_director'}
EDU_ROLES = roles_with('results:education')
SEE_ALL_ROLES = roles_with('clients:read_all') - {'admin', 'benefit_admin'}
RESPONSIBLE_ROLES = roles_with('clients:be_responsible')

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
            if a.workspace_id.gated:
                raise ValidationError('این پنل در انتظار تأیید مالک پلتفرم است؛ دعوت شرکت‌کنندهٔ واقعی پس از تأیید ممکن می‌شود.')

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

    def invite_state(self):
        """ok | expired | used | declined | withdrawn: what a participant opening the link should be told."""
        self.ensure_one()
        if self.withdrawn:
            return 'withdrawn'
        if self.declined:
            return 'declined'
        if self.user_id:
            return 'used'
        if (self.create_date and self.create_date < fields.Datetime.now() - timedelta(days=INVITE_TTL_DAYS)) \
                or (self.deadline and self.deadline < fields.Date.today()):
            return 'expired'
        return 'ok'

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
        if not self.user_id and self.invite_state() == 'expired':
            raise UserError('مهلت این دعوت تمام شده است.')
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

    @api.model
    def ts_share_attempt(self, attempt, code, user):
        """A participant sends an already finished, self-taken result to ONE education panel (by its code).
        Uses the normal assignment machinery, so revoking, visibility and the responsible-counselor rules
        are identical to an invited result. Only the band summary is shared; answers never are."""
        attempt = attempt.sudo()
        code = (code or '').strip().upper().translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
        ws = self.env['ts.workspace'].sudo().search([('code', '=', code), ('purpose', '=', 'education'),
                                                      ('state', 'in', ('pilot', 'active'))], limit=1) if code else False
        if not ws or ws.gated:
            raise UserError('پنلی با این کد پیدا نشد. کد را از مشاور خود بپرسید.')
        if attempt.user_id != user or attempt.state != 'done' or attempt.workspace_id or attempt.source == 'import':
            raise UserError('این نتیجه قابل ارسال برای مشاور نیست.')
        existing = self.sudo().search([('attempt_id', '=', attempt.id)])
        active = existing.filtered(lambda x: x.share_level != 'none')
        if active.filtered(lambda x: x.workspace_id == ws):
            raise UserError('این نتیجه پیش‌تر با همین پنل به اشتراک گذاشته شده است.')
        limit = self.env['ir.config_parameter'].sudo().get_int('ts_panel.share_max_panels', 3) or 3     # owner decision D3
        if len(active) >= limit:
            raise UserError('این نتیجه همین حالا با %s پنل به اشتراک گذاشته شده است؛ ابتدا یکی از اشتراک‌ها را لغو کنید.' % limit)
        again = existing.filtered(lambda x: x.workspace_id == ws and x.invited_by_id == user)
        if again:                                  # re-sharing with a panel the person revoked earlier: the same record
            again[0].write({'share_level': 'summary'})
            self.env['ts.audit.event'].sudo().log('assignment.self_share', again[0], workspace=ws, instrument=attempt.instrument_id.code)
            return again[0]
        a = self.sudo().create({
            'workspace_id': ws.id, 'instrument_id': attempt.instrument_id.id, 'invitee_name': user.name or 'شرکت‌کننده',
            'invited_by_id': user.id, 'user_id': user.id, 'attempt_id': attempt.id, 'share_level': 'summary',
            'accepted_at': fields.Datetime.now()})
        self.env['ts.audit.event'].sudo().log('assignment.self_share', a, workspace=ws, instrument=attempt.instrument_id.code)
        return a

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

    def result_level(self, member):
        """How much of this invitation's result `member` may see (05_permissions_matrix.md section 5):
        'none' | 'status' | 'summary' | 'education' | 'clinical'. First match wins."""
        self.ensure_one()
        if member.workspace_id != self.workspace_id or not member.can_act() or not member.can_see(self):  # step 1
            return 'none'
        at = self.attempt_id
        if not at or at.state != 'done':                                                                   # 2, 3
            return 'status'
        if not at.released or self.share_level == 'none':                                                  # 5, 6
            return 'status'
        if self._ts_guardian_blocks():                                                                     # 7
            return 'status'
        purpose = self.purpose
        if purpose == 'employment' and self.share_level == 'summary' and member.has_perm('results:summary'):  # 8
            return 'summary'
        if purpose == 'education' and self.share_level == 'summary' and member.has_perm('results:education'):  # 9
            return 'education'
        if purpose == 'clinical' and self.share_level == 'clinical' and member.has_perm('results:clinical'):  # 10
            return 'clinical'
        return 'status'

    def _ts_guardian_blocks(self):
        """Hook for S16: a minor's result is withheld while no guardian consent is recorded."""
        return False

    def visible_results(self, member):
        """Old interface: (level, results) with level 'none' | 'summary' | 'education' | 'clinical'.
        The levels 'none' and 'status' both give an empty result set and the old answer 'none'."""
        self.ensure_one()
        level = self.result_level(member)
        if level in ('none', 'status'):
            return 'none', self.env['ts.attempt.result']
        return level, self.attempt_id.result_rows()


class TsWorkspaceMember(models.Model):
    _inherit = 'ts.workspace.member'

    def can_act(self):
        """May this member work in the panel at all: active, panel running, and (clinicians, clinic directors)
        professionally verified. A suspended or draft panel gives False (A2, A3)."""
        self.ensure_one()
        if not self.active or self.workspace_id.state not in ('pilot', 'active'):
            return False
        return not self._ts_unverified_pro()

    # ------------------------------------------------ a specialist leaves or changes role
    def _ts_release_clients(self):
        """Everything this member was responsible for goes back to the unassigned queue (owner/manager
        still see it, the leaver no longer can). Each change is audit-logged by the record's own write."""
        A = self.env['ts.assignment'].sudo()
        T = self.env['ts.attempt'].sudo()
        for m in self:
            A.search([('responsible_id', '=', m.id)]).write({'responsible_id': False})
            T.search([('responsible_id', '=', m.id)]).write({'responsible_id': False})

    def write(self, vals):
        leaving = self.env['ts.workspace.member']
        if vals.get('active') is False or ('role' in vals and vals['role'] not in RESPONSIBLE_ROLES):
            leaving = self.filtered(lambda m: m.role in RESPONSIBLE_ROLES or vals.get('active') is False)
        res = super().write(vals)
        leaving._ts_release_clients()
        return res

    def unlink(self):
        self._ts_release_clients()
        return super().unlink()

    def can_invite(self):
        """Role may create invitations (a gated panel is handled by can_invite_participants, as before;
        admin is not added: the coordinator does not invite in this stage)."""
        return self.role in INVITE_ROLES

    def can_invite_participants(self):
        """Real participants can be invited only once the platform owner approved gated panels."""
        self.ensure_one()
        return self.can_invite() and not self.workspace_id.gated

    # ------------------------------------------------ responsible specialist
    def sees_all(self):
        self.ensure_one()
        return self.has_perm('clients:read_all')

    def sees_unassigned(self):
        """Owners, coordinators and managers always; counselors only in education panels."""
        self.ensure_one()
        return self.has_perm('clients:read_unassigned')

    def can_assign(self):
        """Who may hand a participant to a specialist."""
        self.ensure_one()
        return self.has_perm('clients:assign')

    def can_see(self, rec):
        """rec is a ts.assignment or an imported ts.attempt with a responsible_id (relationship rules R0-R3)."""
        self.ensure_one()
        if rec.workspace_id != self.workspace_id:
            return False
        if self.has_perm('clients:read_all'):
            return True
        if rec.responsible_id:
            return rec.responsible_id == self and self.has_perm('clients:read_own')
        return self.has_perm('clients:read_unassigned')

    @api.model
    def ts_default_responsible(self, workspace_id, user_id):
        """The creator is responsible if their role can be; an owner only when working alone or practising."""
        m = self.sudo().search([('workspace_id', '=', int(workspace_id)), ('user_id', '=', user_id),
                                ('active', '=', True)], limit=1)
        if not m or m.role not in RESPONSIBLE_ROLES or not m.can_act():
            return self.browse()
        if m.role == 'owner' and not m.owner_practices and self.sudo().search_count(
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
