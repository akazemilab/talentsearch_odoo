import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ts_org.models.assignment import RESPONSIBLE_ROLES
from odoo.addons.ts_org.models.panel import norm_email, norm_phone

from .text import norm_text

_logger = logging.getLogger(__name__)

LOCKED_FIELDS = {'phone', 'email', 'guardian_name', 'guardian_phone', 'guardian_relation'}
SOURCES = [('manual', 'ثبت دستی'), ('csv', 'فایل'), ('invite', 'دعوت'), ('open_link', 'پیوند عمومی'),
           ('self_share', 'ارسال با کد پنل'), ('import', 'واردشده')]


class TsPanelClient(models.Model):
    """The person as one panel knows them (04_data_model.md 3.1). The single place where responsibility is set:
    invitations and imported results read it through a stored related field."""
    _name = 'ts.panel.client'
    _description = 'Talent Search panel client'
    _order = 'last_activity_at desc, id desc'

    workspace_id = fields.Many2one('ts.workspace', required=True, index=True, ondelete='restrict')
    name = fields.Char('نام', required=True)
    name_norm = fields.Char(compute='_compute_name_norm', store=True, index=True)
    code = fields.Char('شناسهٔ پنل')
    phone = fields.Char('موبایل')
    email = fields.Char('ایمیل')
    responsible_id = fields.Many2one(
        'ts.workspace.member', 'کارشناس مسئول', index=True, ondelete='set null',
        domain="[('workspace_id', '=', workspace_id), ('active', '=', True)]")
    age_group = fields.Selection([('adult', 'بزرگسال'), ('minor', 'زیر ۱۸ سال'), ('unknown', 'نامشخص')],
                                 'گروه سنی', default='unknown', required=True)
    guardian_name = fields.Char('نام سرپرست')
    guardian_phone = fields.Char('موبایل سرپرست')
    guardian_relation = fields.Selection([('father', 'پدر'), ('mother', 'مادر'), ('guardian', 'سرپرست قانونی'),
                                          ('other', 'سایر')], 'نسبت')
    group_ids = fields.Many2many('ts.panel.group', 'ts_panel_client_group_rel', 'client_id', 'group_id', 'گروه‌ها')
    handover_to_id = fields.Many2one('ts.workspace.member', 'واگذاری به', ondelete='set null')
    handover_by_id = fields.Many2one('ts.workspace.member', 'درخواست‌کننده', ondelete='set null')
    handover_on = fields.Datetime('زمان درخواست واگذاری')
    user_id = fields.Many2one('res.users', 'حساب کاربری', index=True, ondelete='set null')
    account_is_guardian = fields.Boolean('حساب متعلق به سرپرست است')
    partner_id = fields.Many2one('res.partner', 'شخص (دادهٔ تاریخی)', ondelete='restrict')
    source = fields.Selection(SOURCES, 'منبع', default='manual', required=True)
    contact_locked = fields.Boolean(compute='_compute_contact_locked')
    merged_into_id = fields.Many2one('ts.panel.client', ondelete='set null')
    state = fields.Selection([('active', 'فعال'), ('archived', 'بایگانی')], default='active', required=True, index=True)
    archived_on = fields.Datetime()
    anonymised_on = fields.Datetime()
    last_activity_at = fields.Datetime('آخرین فعالیت', index=True, default=fields.Datetime.now)
    assignment_ids = fields.One2many('ts.assignment', 'client_id')
    attempt_ids = fields.One2many('ts.attempt', 'client_id')
    open_count = fields.Integer(compute='_compute_counts', store=True)
    done_count = fields.Integer(compute='_compute_counts', store=True)

    _code_uniq = models.UniqueIndex('(workspace_id, code) WHERE code IS NOT NULL')
    _user_uniq = models.UniqueIndex('(workspace_id, user_id) WHERE user_id IS NOT NULL')

    # ------------------------------------------------------------------ computed
    @api.depends('name')
    def _compute_name_norm(self):
        for c in self:
            c.name_norm = norm_text(c.name)

    @api.depends('assignment_ids.state', 'attempt_ids.state', 'attempt_ids.source')
    def _compute_counts(self):
        for c in self:
            st = c.assignment_ids.mapped('state')
            imported = c.attempt_ids.filtered(lambda a: a.source == 'import' and a.state == 'done')
            c.open_count = sum(1 for s in st if s in ('invited', 'opened', 'accepted', 'in_progress'))
            c.done_count = sum(1 for s in st if s == 'done') + len(imported)

    @api.model
    def _import_unlocked(self):
        return self.env['ir.config_parameter'].sudo().get_str('ts_panel.import_contact_unlocked') in ('1', 'true', 'True')

    @api.depends('source')
    def _compute_contact_locked(self):
        unlocked = self._import_unlocked()
        for c in self:
            c.contact_locked = c.source == 'import' and not unlocked

    # ------------------------------------------------------------------ constraints
    @api.constrains('responsible_id', 'workspace_id', 'user_id')
    def _check_responsible(self):
        for c in self:
            r = c.responsible_id
            if not r:
                continue
            if r.workspace_id != c.workspace_id or not r.active or r.role not in RESPONSIBLE_ROLES:
                raise ValidationError('کارشناس مسئول باید عضو فعال همین فضای کاری با نقش کارشناس باشد.')
            if c.user_id and r.user_id == c.user_id:
                raise ValidationError('شرکت‌کننده نمی‌تواند کارشناس مسئولِ خودش باشد.')

    @api.constrains('name')
    def _check_name(self):
        for c in self:
            if not (c.name or '').strip() or len(c.name) > 120:
                raise ValidationError('نام باید بین ۱ تا ۱۲۰ نویسه باشد.')

    # ------------------------------------------------------------------ create / write
    @staticmethod
    def _norm_vals(vals):
        vals = dict(vals)
        if 'name' in vals:
            vals['name'] = (vals['name'] or '').strip()[:120]
        for k in ('phone', 'guardian_phone'):
            if vals.get(k):
                vals[k] = norm_phone(vals[k]) or False
        if vals.get('email'):
            vals['email'] = norm_email(vals['email']) or False
        if 'code' in vals:
            vals['code'] = (vals['code'] or '').strip()[:40] or False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._norm_vals(v) for v in vals_list]
        recs = super().create(vals_list)
        for c in recs:
            if c.responsible_id:
                self.env['ts.audit.event'].log('client.responsible_change', c, workspace=c.workspace_id,
                                               old=False, new=c.responsible_id.id)
        return recs

    def write(self, vals):
        vals = self._norm_vals(vals)
        if LOCKED_FIELDS & set(vals) and any(c.contact_locked for c in self):
            raise UserError('اطلاعات تماس این فرد از دادهٔ تاریخی است و فعلاً قفل است.')
        old = {c.id: c.responsible_id.id for c in self} if 'responsible_id' in vals else {}
        res = super().write(vals)
        for c in self:
            if c.id in old and old[c.id] != c.responsible_id.id:
                self.env['ts.audit.event'].log('client.responsible_change', c, workspace=c.workspace_id,
                                               old=old[c.id] or False, new=c.responsible_id.id or False)
        return res

    def ts_touch(self):
        now = fields.Datetime.now()
        self.sudo().filtered(lambda c: c.last_activity_at != now).write({'last_activity_at': now})

    # ------------------------------------------------------------------ S5: archive, merge, handover
    def _check_actor(self, by, perm):
        for c in self:
            if by.workspace_id != c.workspace_id or not by.has_perm(perm) or not by.can_act() or not by.can_see(c):
                raise UserError('دسترسی ندارید.')

    def ts_archive(self, by):
        self._check_actor(by, 'clients:archive')
        now = fields.Datetime.now()
        for c in self.filtered(lambda c: c.state == 'active'):
            c.write({'state': 'archived', 'archived_on': now, 'handover_to_id': False, 'handover_by_id': False,
                     'handover_on': False})
            self.env['ts.audit.event'].log('client.archive', c, workspace=c.workspace_id)

    def ts_restore(self, by):
        self._check_actor(by, 'clients:archive')
        for c in self.filtered(lambda c: c.state == 'archived' and not c.merged_into_id):
            c.write({'state': 'active', 'archived_on': False})
            self.env['ts.audit.event'].log('client.restore', c, workspace=c.workspace_id)

    def ts_merge_check(self, other, by):
        """Raise unless `other` can be folded into self (04_data_model.md linking rule 5)."""
        self.ensure_one()
        other.ensure_one()
        (self | other)._check_actor(by, 'clients:merge')
        if self == other or self.workspace_id != other.workspace_id:
            raise UserError('دو ردیف متفاوت از همین پنل را انتخاب کنید.')
        if self.contact_locked or other.contact_locked:
            raise UserError('افراد واردشده از دادهٔ تاریخی ادغام نمی‌شوند.')
        if self.state != 'active' or other.state != 'active':
            raise UserError('فقط ردیف‌های فعال ادغام می‌شوند.')
        if self.user_id and other.user_id and self.user_id != other.user_id:
            raise UserError('این دو ردیف حساب کاربری متفاوتی دارند و ادغام نمی‌شوند.')

    def ts_merge_preview(self, other):
        self.ensure_one()
        return {'assignments': len(other.assignment_ids), 'attempts': len(other.attempt_ids - other.assignment_ids.attempt_id),
                'groups': len(other.group_ids - self.group_ids)}

    def ts_merge(self, other, by):
        """`other` is folded into self: invitations, results and groups move, empty fields are filled, `other`
        stays as an archived row pointing here. Nothing is deleted."""
        self.ensure_one()
        self.ts_merge_check(other, by)
        moved_a, moved_t = len(other.assignment_ids), len(other.attempt_ids)
        other.assignment_ids.sudo().write({'client_id': self.id})
        other.attempt_ids.sudo().write({'client_id': self.id})
        fill = {}
        for f in ('phone', 'email', 'guardian_name', 'guardian_phone', 'guardian_relation'):
            if not self[f] and other[f]:
                fill[f] = other[f]
        if not self.code and other.code:
            fill['code'] = other.code
        user = other.user_id if not self.user_id else self.env['res.users']
        resp = other.responsible_id if not self.responsible_id else self.env['ts.workspace.member']
        groups = other.group_ids
        other.write({'code': False, 'user_id': False, 'responsible_id': False, 'group_ids': [(5, 0, 0)],
                     'state': 'archived', 'archived_on': fields.Datetime.now(), 'merged_into_id': self.id,
                     'handover_to_id': False, 'handover_by_id': False, 'handover_on': False})
        self.env.flush_all()   # the freed code and account must reach the database before the survivor takes them
        if user:
            fill['user_id'] = user.id
        if resp and resp.can_act():
            fill['responsible_id'] = resp.id
        if groups:
            fill['group_ids'] = [(4, g.id) for g in groups]
        if fill:
            self.write(fill)
        self.ts_touch()
        self.env['ts.audit.event'].log('client.merge', self, workspace=self.workspace_id,
                                       merged=other.id, assignments=moved_a, attempts=moved_t)

    def ts_request_handover(self, by, target):
        """CLI-5: the responsible specialist asks to hand the client to a colleague. A member who can assign does
        it at once; otherwise it waits for one of them to confirm."""
        self.ensure_one()
        if by.workspace_id != self.workspace_id or not by.can_act() or self.responsible_id != by \
                or not by.has_perm('clients:be_responsible'):
            raise UserError('فقط کارشناس مسئول می‌تواند واگذاری را درخواست کند.')
        if self.state != 'active':
            raise UserError('شرکت‌کنندهٔ بایگانی‌شده واگذار نمی‌شود.')
        self._check_handover_target(target, by)
        if by.has_perm('clients:assign'):
            self.write({'responsible_id': target.id, 'handover_to_id': False, 'handover_by_id': False, 'handover_on': False})
            return 'done'
        self.write({'handover_to_id': target.id, 'handover_by_id': by.id, 'handover_on': fields.Datetime.now()})
        self.env['ts.audit.event'].log('client.handover_request', self, workspace=self.workspace_id,
                                       by=by.id, to=target.id)
        return 'requested'

    def _check_handover_target(self, target, by):
        if not target or target.workspace_id != self.workspace_id or not target.active or not target.can_act() \
                or target.role not in RESPONSIBLE_ROLES or target == by or (self.user_id and target.user_id == self.user_id):
            raise UserError('همکار انتخاب‌شده نمی‌تواند کارشناس مسئول این فرد شود.')

    def ts_decide_handover(self, by, accept):
        self.ensure_one()
        self._check_actor(by, 'clients:assign')
        if not self.handover_to_id:
            raise UserError('درخواست واگذاری بازی وجود ندارد.')
        target, requester = self.handover_to_id, self.handover_by_id
        vals = {'handover_to_id': False, 'handover_by_id': False, 'handover_on': False}
        if accept:
            self._check_handover_target(target, requester)
            vals['responsible_id'] = target.id
        self.write(vals)
        self.env['ts.audit.event'].log('client.handover_decide', self, workspace=self.workspace_id,
                                       accepted=bool(accept), to=target.id)

    # ------------------------------------------------------------------ duplicates (a warning, never a block)
    @api.model
    def ts_duplicates(self, ws_id, name=None, phone=None, email=None, exclude=None):
        dom = [('workspace_id', '=', int(ws_id)), ('state', '=', 'active')]
        if exclude:
            dom.append(('id', '!=', exclude))
        conds = []
        if (name or '').strip():
            conds.append(('name_norm', '=', norm_text(name)))
        if norm_phone(phone):
            conds.append(('phone', '=', norm_phone(phone)))
        if norm_email(email):
            conds.append(('email', '=', norm_email(email)))
        if not conds:
            return self.browse()
        return self.sudo().search(dom + ['|'] * (len(conds) - 1) + conds)

    # ------------------------------------------------------------------ finding or making a client
    @api.model
    def _active_in(self, ws_id):
        return [('workspace_id', '=', int(ws_id)), ('state', '=', 'active')]

    @api.model
    def ts_for_invitation(self, vals):
        """Linking rules 1-4 for a new invitation (04_data_model.md 3.1): the account is the only automatic key,
        then an exact phone, then an exact email; never the name."""
        C = self.sudo()
        ws_id = int(vals['workspace_id'])
        user_id = vals.get('user_id')
        phone = norm_phone(vals.get('invitee_phone')) or False
        email = norm_email(vals.get('invitee_email')) or False
        found = C.browse()
        if user_id:
            found = C.search(self._active_in(ws_id) + [('user_id', '=', user_id)], limit=1)
        if not found and phone:
            found = C.search(self._active_in(ws_id) + [('phone', '=', phone)], limit=1)
        if not found and email:
            found = C.search(self._active_in(ws_id) + [('email', '=', email)], limit=1)
        if found:
            if phone and not found.phone and not found.contact_locked:
                found.phone = phone
            return found
        by = vals.get('invited_by_id') or self.env.uid
        resp = self.env['ts.workspace.member'].ts_panel_default_responsible(ws_id, by)
        return C.create({
            'workspace_id': ws_id, 'name': (vals.get('invitee_name') or '—'), 'phone': phone, 'email': email,
            'user_id': user_id or False, 'responsible_id': resp.id or False,
            'source': 'self_share' if user_id and by == user_id else 'invite',
        })

    @api.model
    def ts_for_import(self, ws_id, partner, responsible=None):
        """One client per (panel, historical person). Contact data is never copied (decision D5)."""
        C = self.sudo()
        found = C.search([('workspace_id', '=', int(ws_id)), ('partner_id', '=', partner.id)], limit=1)
        if found:
            return found
        return C.create({'workspace_id': int(ws_id), 'name': partner.name or '—', 'partner_id': partner.id,
                         'source': 'import', 'responsible_id': responsible.id if responsible else False})

    # ------------------------------------------------------------------ migration M3-M5 (idempotent)
    @api.model
    def ts_migrate_s4(self):
        """Backfill clients for existing invitations (M3), imported results (M4) and web attempts (M5).
        Sends nothing, links no account, releases no result. Prints counts only."""
        env = self.sudo().with_context(tracking_disable=True, mail_notrack=True).env
        cr = env.cr
        cr.execute("SELECT to_regclass('ts_panel_resp_snap')")
        snap = {}
        if cr.fetchone()[0]:
            cr.execute("SELECT kind, id, responsible_id FROM ts_panel_resp_snap")
            snap = {(k, i): r for k, i, r in cr.fetchall()}
        Member = env['ts.workspace.member'].with_context(active_test=False)

        def valid(member_id, ws, user=None):
            m = Member.browse(member_id) if member_id else Member
            ok = m and m.exists() and m.workspace_id == ws and m.active and m.role in RESPONSIBLE_ROLES \
                and not (user and m.user_id == user)
            return m.id if ok else False

        Client = env['ts.panel.client']
        A = env['ts.assignment'].with_context(active_test=False)
        T = env['ts.attempt'].with_context(active_test=False)
        made = linked = 0
        for a in A.search([('client_id', '=', False)], order='create_date, id'):
            resp = snap.get(('a', a.id)) or a.responsible_id.id
            before = Client.search_count([])
            c = self._migrate_find_or_make(a)
            made += Client.search_count([]) - before
            if valid(resp, a.workspace_id, c.user_id) and resp != c.responsible_id.id:
                c.responsible_id = resp
            a.client_id = c.id
            c.last_activity_at = max(a.write_date or a.create_date, c.last_activity_at or a.create_date)
            linked += 1
        # M4
        imported = 0
        before = Client.search_count([('source', '=', 'import')])
        groups = {}
        for t in T.search([('source', '=', 'import'), ('workspace_id', '!=', False), ('client_id', '=', False),
                           ('person_id', '!=', False)], order='create_date, id'):
            groups.setdefault((t.workspace_id.id, t.person_id.id), []).append(t)
        for (ws_id, pid), ts_ in groups.items():
            ws = env['ts.workspace'].browse(ws_id)
            resp = 0
            for t in ts_:                                    # newest wins
                resp = valid(snap.get(('t', t.id)) or t.responsible_id.id, ws) or resp
            c = Client.ts_for_import(ws_id, env['res.partner'].browse(pid), Member.browse(resp) if resp else None)
            for t in ts_:
                t.client_id = c.id
                imported += 1
            c.last_activity_at = max(t.write_date or t.create_date for t in ts_)
        clients_import = Client.search_count([('source', '=', 'import')]) - before
        # M5
        web = 0
        for a in A.search([('attempt_id', '!=', False), ('client_id', '!=', False)]):
            if not a.attempt_id.client_id:
                a.attempt_id.client_id = a.client_id.id
                web += 1
        env.flush_all()
        if snap:
            cr.execute("DROP TABLE IF EXISTS ts_panel_resp_snap")
        _logger.info('ts_panel S4 migration: clients created for invitations %s (assignments linked %s), '
                     'import clients %s (attempts linked %s), web attempts linked %s',
                     made, linked, clients_import, imported, web)
        return {'invitation_clients': made, 'assignments': linked, 'import_clients': clients_import,
                'import_attempts': imported, 'web_attempts': web}

    @api.model
    def _migrate_find_or_make(self, a):
        """Same matching order as ts_for_invitation, with the invitation's own creator for the default rule."""
        vals = {'workspace_id': a.workspace_id.id, 'user_id': a.user_id.id or False,
                'invitee_phone': getattr(a, 'invitee_phone', False), 'invitee_email': a.invitee_email,
                'invitee_name': a.invitee_name, 'invited_by_id': a.invited_by_id.id or self.env.uid}
        C = self.sudo()
        ws_id = vals['workspace_id']
        phone = norm_phone(vals['invitee_phone']) or False
        email = norm_email(vals['invitee_email']) or False
        found = C.browse()
        if vals['user_id']:
            found = C.search(self._active_in(ws_id) + [('user_id', '=', vals['user_id'])], limit=1)
        if not found and phone:
            found = C.search(self._active_in(ws_id) + [('phone', '=', phone)], limit=1)
        if not found and email:
            found = C.search(self._active_in(ws_id) + [('email', '=', email)], limit=1)
        if found:
            return found
        return C.create({'workspace_id': ws_id, 'name': vals['invitee_name'] or '—', 'phone': phone, 'email': email,
                         'user_id': vals['user_id'], 'source': 'self_share' if vals['user_id'] and a.invited_by_id == a.user_id else 'invite',
                         'last_activity_at': a.create_date})
