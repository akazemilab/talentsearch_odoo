"""Group invitations and the open link (S7, INV-5, INV-6, INV-9; 04_data_model.md 3.3).

A campaign is a batch of invitations that share an instrument, a deadline and a note. Kind `list` creates one
invitation per chosen client at once; kind `open_link` creates one invitation per person who joins through
`/c/<token>`, up to `open_max` and until `open_expires_at`. Closing a campaign stops new joins; it withdraws nothing.
"""
import uuid
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

OPEN_STATES = ('invited', 'opened', 'accepted', 'in_progress')     # an invitation that still counts as "open"
COUNT_STATES = ['invited', 'opened', 'accepted', 'in_progress', 'done', 'expired', 'declined', 'withdrawn']
OPEN_MAX_HARD = 500
JOIN_MSG = {'closed': 'این دعوت بسته شده است.', 'expired': 'مهلت این دعوت به پایان رسیده است.',
            'full': 'ظرفیت این دعوت تکمیل شده است.'}


class TsCampaign(models.Model):
    _name = 'ts.campaign'
    _description = 'Talent Search campaign (group invitation or open link)'
    _order = 'id desc'

    workspace_id = fields.Many2one('ts.workspace', required=True, index=True, ondelete='restrict')
    name = fields.Char('عنوان', required=True)
    instrument_id = fields.Many2one('ts.instrument', 'سنجه', required=True, ondelete='restrict')
    kind = fields.Selection([('list', 'دعوت گروهی'), ('open_link', 'پیوند باز')], 'نوع', required=True, default='list')
    state = fields.Selection([('draft', 'پیش‌نویس'), ('open', 'باز'), ('closed', 'بسته')], 'وضعیت', default='open', required=True)
    deadline = fields.Date('مهلت')
    note = fields.Char('یادداشت', size=300)
    created_by_id = fields.Many2one('ts.workspace.member', 'سازنده', ondelete='set null')
    group_ids = fields.Many2many('ts.panel.group', 'ts_campaign_group_rel', 'campaign_id', 'group_id', 'گروه‌ها')
    open_token = fields.Char('کد پیوند باز', index=True, copy=False, readonly=True)
    open_max = fields.Integer('سقف پیوستن')
    open_expires_at = fields.Datetime('انقضای پیوند باز')
    send_sms = fields.Boolean('پیامک')
    sms_consent_attested = fields.Boolean('تأیید رضایت پیامک', readonly=True)
    remind = fields.Boolean('یادآوری', default=True)
    closed_on = fields.Datetime(readonly=True)
    assignment_ids = fields.One2many('ts.assignment', 'campaign_id')

    _token_uniq = models.UniqueIndex('(open_token) WHERE open_token IS NOT NULL')

    # ------------------------------------------------------------------ constraints
    @api.constrains('name')
    def _check_name(self):
        for c in self:
            if not 2 <= len((c.name or '').strip()) <= 80:
                raise ValidationError('عنوان باید بین ۲ تا ۸۰ نویسه باشد.')

    @api.constrains('open_max', 'kind')
    def _check_open_max(self):
        for c in self:
            if c.kind == 'open_link' and not 1 <= c.open_max <= OPEN_MAX_HARD:
                raise ValidationError('سقف پیوستن باید بین ۱ تا %d باشد.' % OPEN_MAX_HARD)

    @api.constrains('send_sms', 'sms_consent_attested')
    def _check_sms(self):
        for c in self:
            if c.send_sms and not c.sms_consent_attested:
                raise ValidationError('برای ارسال پیامک، تأیید رضایت لازم است.')

    @api.constrains('instrument_id', 'workspace_id', 'created_by_id')
    def _check_instrument(self):
        for c in self:
            if c.created_by_id and c.instrument_id not in c.created_by_id.allowed_instruments():
                raise ValidationError('سنجهٔ انتخاب‌شده برای این پنل مجاز نیست.')

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            v['name'] = (v.get('name') or '').strip()
            if v.get('kind') == 'open_link':
                v.setdefault('open_token', uuid.uuid4().hex)
                if not v.get('open_max'):
                    v['open_max'] = self.env['ir.config_parameter'].sudo().get_int('ts_panel.open_link_max', 60) or 60
                v.setdefault('open_expires_at', fields.Datetime.now() + timedelta(days=14))
            if v.get('send_sms'):
                v['sms_consent_attested'] = True    # the controller only passes send_sms together with the tick
        return super().create(vals_list)

    # ------------------------------------------------------------------ state of the open link
    def open_state(self):
        """'ok' / 'closed' / 'expired' / 'full' for the public join page."""
        self.ensure_one()
        if self.kind != 'open_link' or self.state != 'open':
            return 'closed'
        if self.open_expires_at and self.open_expires_at < fields.Datetime.now():
            return 'expired'
        if self.joined_count() >= self.open_max:
            return 'full'
        return 'ok'

    def joined_count(self):
        self.ensure_one()
        return self.env['ts.assignment'].sudo().search_count([('campaign_id', '=', self.id)])

    def invite_url(self):
        self.ensure_one()
        base = self.env.ref('ts_website.website_ts').domain or ''
        return '%s/c/%s' % (base.rstrip('/'), self.open_token)

    def counts(self, domain=None):
        """{state: n} over the campaign's invitations, optionally narrowed by a visibility domain."""
        self.ensure_one()
        out = {k: 0 for k in COUNT_STATES}
        dom = [('campaign_id', '=', self.id)] + (domain or [])
        for st, n in self.env['ts.assignment'].sudo()._read_group(dom, groupby=['state'], aggregates=['__count']):
            out[st] = n
        return out

    # ------------------------------------------------------------------ list campaign (INV-5)
    @api.model
    def ts_targets(self, clients, ws_id, instrument_id):
        """Split the chosen clients into who gets an invitation and who is skipped, with the reason.
        Returns (to_invite, skipped) where skipped is {reason: recordset}."""
        A = self.env['ts.assignment'].sudo()
        busy = A.search([('workspace_id', '=', ws_id), ('instrument_id', '=', instrument_id),
                         ('client_id', 'in', clients.ids), ('state', 'in', list(OPEN_STATES))]).client_id
        skipped = {
            'locked': clients.filtered(lambda c: c.contact_locked),
            'archived': clients.filtered(lambda c: c.state != 'active'),
            'busy': clients & busy,
        }
        gone = skipped['locked'] | skipped['archived'] | skipped['busy']
        return clients - gone, skipped

    def ts_launch(self, clients):
        """Create the invitations of a list campaign. Returns (created assignments, skipped dict)."""
        self.ensure_one()
        if self.kind != 'list' or self.state != 'open':
            raise UserError('این دعوت گروهی دیگر باز نیست.')
        if self.workspace_id.gated:
            raise UserError('دعوت شرکت‌کننده پس از تأیید پنل ممکن می‌شود.')
        clients = clients.sudo().filtered(lambda c: c.workspace_id == self.workspace_id)
        # the lock on the campaign row keeps a double click from creating the batch twice
        self.env.cr.execute('SELECT id FROM ts_campaign WHERE id = %s FOR UPDATE', [self.id])
        to_invite, skipped = self.ts_targets(clients, self.workspace_id.id, self.instrument_id.id)
        A = self.env['ts.assignment'].sudo()
        by = self.created_by_id.user_id.id if self.created_by_id else self.env.uid
        created = A.browse()
        for c in to_invite:
            vals = {'workspace_id': self.workspace_id.id, 'instrument_id': self.instrument_id.id, 'client_id': c.id,
                    'campaign_id': self.id, 'invited_by_id': by, 'invitee_name': c.name, 'invitee_email': c.email or False,
                    'invitee_phone': c.phone or False, 'note': self.note or False, 'deadline': self.deadline or False}
            if self.send_sms and c.phone and self.sms_consent_attested:
                vals.update(sms_consent=True, remind_ok=bool(self.remind))
            created |= A.create(vals)
        return created, skipped

    # ------------------------------------------------------------------ open link (INV-6)
    def ts_join(self, user, name):
        """A signed-in participant joins through the open link. Returns the assignment (new or existing).
        Raises UserError with the page message when the link is closed, expired or full."""
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM ts_campaign WHERE id = %s FOR UPDATE', [self.id])
        A = self.env['ts.assignment'].sudo()
        C = self.env['ts.panel.client'].sudo()
        ws = self.workspace_id
        name = (name or '').strip()
        if ws.gated:
            raise UserError(JOIN_MSG['closed'])
        if not 2 <= len(name) <= 120:
            raise UserError('نام را بین ۲ تا ۱۲۰ نویسه بنویسید.')
        client = C.search([('workspace_id', '=', ws.id), ('user_id', '=', user.id), ('state', '=', 'active')], limit=1)
        if client and client.contact_locked:
            raise UserError('این دعوت برای حساب شما ممکن نیست.')
        mine = A.search([('campaign_id', '=', self.id), ('client_id', '=', client.id)], limit=1) if client else A.browse()
        if mine:
            return mine
        st = self.open_state()
        if st != 'ok':
            raise UserError(JOIN_MSG[st])
        if client:
            busy = A.search([('workspace_id', '=', ws.id), ('instrument_id', '=', self.instrument_id.id),
                             ('client_id', '=', client.id), ('state', 'in', list(OPEN_STATES))], limit=1)
            if busy:
                return busy        # no second open invitation for the same person and instrument
        else:
            client = C.create({'workspace_id': ws.id, 'name': name, 'user_id': user.id, 'source': 'open_link'})
        return A.create({'workspace_id': ws.id, 'instrument_id': self.instrument_id.id, 'client_id': client.id,
                         'campaign_id': self.id, 'invited_by_id': self.created_by_id.user_id.id or False,
                         'invitee_name': name, 'note': self.note or False, 'deadline': self.deadline or False,
                         'channel': 'open_link'})

    def ts_close(self, by=None):
        for c in self:
            if c.state == 'closed':
                continue
            c.write({'state': 'closed', 'closed_on': fields.Datetime.now()})
            self.env['ts.audit.event'].log('campaign.close', c, workspace=c.workspace_id, member=by)


class TsAssignmentCampaign(models.Model):
    _inherit = 'ts.assignment'

    campaign_id = fields.Many2one('ts.campaign', 'کمپین', index=True, ondelete='restrict')
