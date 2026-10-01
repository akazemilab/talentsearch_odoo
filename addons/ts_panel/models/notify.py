"""Notification center, preferences and reminders (S10: NOT-1..NOT-5b, ACC-7, INV-8, PLT-6; 04_data_model.md 3.6).

`ts.notification._notify(user, type, url, workspace)` is the one place that decides what a person is told and how:
an in-app row if their preference allows it (default yes), and an SMS only for the staff types, only when the platform
switch `ts_sms_staff` is on (ships OFF), the person opted in, holds a verified mobile, and the hour is outside the quiet
hours (otherwise the SMS waits for the hourly flush) and the daily limit is not used up. The reminder cron adds the
participant side (INV-8) under the switch `ts_sms_reminder` (ships OFF). Historical people (`contact_locked`) are never
reached, and no text carries a name or a result. Email is not a channel (decision D8).
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError

from .notify_texts import SMS_BODIES, SMS_STAFF_TYPES, TITLES, TYPES

_logger = logging.getLogger(__name__)
TEHRAN = ZoneInfo('Asia/Tehran')
UTC = ZoneInfo('UTC')
OPEN_STATES = ('invited', 'opened', 'accepted', 'in_progress')
MAX_REMINDERS = 3


def _cfg(env, key, default):
    return env['ir.config_parameter'].sudo().get_int('ts_panel.' + key, default) or default


class TsNotification(models.Model):
    _name = 'ts.notification'
    _description = 'Talent Search notification'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    workspace_id = fields.Many2one('ts.workspace', index=True, ondelete='cascade')
    type = fields.Selection(TYPES, required=True)
    title = fields.Char(required=True)
    url = fields.Char()
    read_at = fields.Datetime()
    sms_state = fields.Selection([('queued', 'در صف'), ('sent', 'ارسال شد'), ('failed', 'نرسید'), ('skipped', 'ارسال نشد')])
    sms_at = fields.Datetime()

    _user_read_idx = models.Index('(user_id, read_at)')

    # ------------------------------------------------------------------ time rules
    @api.model
    def _tehran_now(self):
        return datetime.now(TEHRAN)

    @api.model
    def _quiet_now(self, now=None):
        now = now or self._tehran_now()
        start, end = _cfg(self.env, 'quiet_start', 21), _cfg(self.env, 'quiet_end', 8)
        return now.hour >= start or now.hour < end

    @api.model
    def _today_start_utc(self):
        local = self._tehran_now().replace(hour=0, minute=0, second=0, microsecond=0)
        return local.astimezone(UTC).replace(tzinfo=None)

    # ------------------------------------------------------------------ preferences
    @api.model
    def _pref(self, user, type_):
        """-> (in_app, sms). Defaults: in-app on, SMS off."""
        p = self.env['ts.notify.pref'].sudo().search([('user_id', '=', user.id), ('type', '=', type_)], limit=1)
        return (p.in_app, p.sms) if p else (True, False)

    @api.model
    def _phone_of(self, user):
        """The mobile this person proved by code, or False."""
        phones = user.sudo()._ts_verified_phones()
        return phones[0] if phones else False

    # ------------------------------------------------------------------ the dispatcher
    @api.model
    def _notify(self, user, type_, url, workspace=None):
        """Tell `user` about an event. Returns the in-app row (possibly empty). Never raises into the caller's flow."""
        if not user or not user.active or type_ not in TITLES:
            return self.browse()
        try:
            with self.env.cr.savepoint():
                in_app, sms = self._pref(user, type_)
                row = self.browse()
                if in_app or (sms and type_ in SMS_STAFF_TYPES):
                    row = self.sudo().create({'user_id': user.id, 'workspace_id': workspace.id if workspace else False, 'type': type_,
                                              'title': TITLES[type_], 'url': url or False})
                    if not in_app:
                        row.read_at = fields.Datetime.now()      # kept only as the carrier of the SMS state
                if row and sms and type_ in SMS_STAFF_TYPES:
                    row._sms_leg()
                return row
        except Exception:
            _logger.exception('notification %s failed', type_)
            return self.browse()

    def _sms_leg(self):
        """Send, queue or skip the SMS of one row (staff types only)."""
        for row in self:
            user = row.user_id
            company = (row.workspace_id.company_id or user.company_id).sudo()
            phone = self._phone_of(user)
            if not (company.kv_enabled and company.ts_sms_staff and phone and row.type in SMS_STAFF_TYPES):
                continue
            if self._quiet_now():
                row.sms_state = 'queued'
                continue
            sent_today = self.sudo().search_count([('user_id', '=', user.id), ('sms_state', '=', 'sent'),
                                                   ('sms_at', '>=', self._today_start_utc())])
            if sent_today >= _cfg(self.env, 'sms_per_day', 5):
                row.sms_state = 'skipped'
                continue
            ok = self._send_sms(company, phone, SMS_BODIES[row.type] % {'url': row._abs_url()}, user.partner_id.id)
            row.write({'sms_state': 'sent' if ok else 'failed', 'sms_at': fields.Datetime.now()})
            self.env['ts.audit.event'].sudo().log('notify.send', row, workspace=row.workspace_id, channel='sms', type=row.type,
                                                  outcome='ok' if ok else 'error')

    def _abs_url(self):
        self.ensure_one()
        base = (self.env.ref('ts_website.website_ts').sudo().domain or '').rstrip('/')
        return base + (self.url or '/my/notifications')

    @api.model
    def _send_sms(self, company, number, body, partner_id=False):
        """One alert SMS through the existing gateway; the row is removed once the gateway has taken it."""
        try:
            with self.env.cr.savepoint():
                sms = self.env['sms.sms'].sudo().with_company(company).create(
                    {'number': number, 'body': body, 'sms_type': 'alert', 'partner_id': partner_id or False})
                sms.send(unlink_sent=False, raise_exception=False)
                ok = sms.state in ('process', 'pending', 'sent')
                sms.unlink()
                return ok
        except Exception:
            _logger.exception('notification SMS failed')
            return False

    # ------------------------------------------------------------------ reading
    @api.model
    def _unread_count(self, user):
        return self.sudo().search_count([('user_id', '=', user.id), ('read_at', '=', False)])

    def _mark_read(self, user):
        self.sudo().filtered(lambda r: r.user_id == user and not r.read_at).write({'read_at': fields.Datetime.now()})

    # ------------------------------------------------------------------ crons
    @api.model
    def _cron_flush_sms(self):
        """Hourly: SMS that waited for the end of the quiet hours go out now (limits are checked again)."""
        if self._quiet_now():
            return 0
        rows = self.sudo().search([('sms_state', '=', 'queued')], order='id', limit=200)
        for row in rows:
            in_app, sms = self._pref(row.user_id, row.type)
            if not sms:
                row.sms_state = 'skipped'
                continue
            row.sms_state = False
            row._sms_leg()
            if row.sms_state is False:
                row.sms_state = 'skipped'
        return len(rows)

    @api.model
    def _cron_vacuum(self):
        """Read notifications older than 180 days go away."""
        self.sudo().search([('read_at', '!=', False), ('read_at', '<', fields.Datetime.now() - timedelta(days=180))]).unlink()


class TsNotifyPref(models.Model):
    _name = 'ts.notify.pref'
    _description = 'Talent Search notification preference'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    type = fields.Selection(TYPES, required=True)
    in_app = fields.Boolean(default=True)
    sms = fields.Boolean(default=False)
    email = fields.Boolean(default=False)     # reserved; no email channel exists (decision D8)

    _uniq = models.Constraint('unique(user_id, type)', 'یک ترجیح برای هر نوع اعلان.')

    @api.model
    def ts_save(self, user, type_, in_app, sms):
        rec = self.sudo().search([('user_id', '=', user.id), ('type', '=', type_)], limit=1)
        vals = {'in_app': bool(in_app), 'sms': bool(sms) and type_ in SMS_STAFF_TYPES}
        if rec:
            rec.write(vals)
        else:
            self.sudo().create(dict(vals, user_id=user.id, type=type_))


class ResUsersNotify(models.Model):
    _inherit = 'res.users'

    def _ts_unread_count(self):
        self.ensure_one()
        return self.env['ts.notification']._unread_count(self)

    def _ts_unread_label(self):
        """Persian-digit count for the header bell, empty when nothing is unread."""
        from odoo.addons.ts_assessment.models.attempt import fa_digits
        n = 0 if self._is_public() else self._ts_unread_count()
        return fa_digits(min(n, 99)) + ('+' if n > 99 else '') if n else ''


# ---------------------------------------------------------------------- hooks
def _staff_users(workspace, responsible=None):
    """Who is told about a client: the responsible specialist, else the members who assign clients."""
    if responsible and responsible.active:
        return responsible.user_id
    members = workspace.sudo().member_ids.filtered(lambda m: m.active and m.can_act() and m.has_perm('clients:assign'))
    return members.mapped('user_id')


class TsAssignmentNotify(models.Model):
    _inherit = 'ts.assignment'

    reminder_count = fields.Integer(default=0, copy=False)
    last_reminder_at = fields.Datetime(copy=False)

    def _ts_account(self):
        """The participant's account, unless the person is a locked historical client (NOT-5)."""
        self.ensure_one()
        c = self.client_id
        if c and c.contact_locked:
            return self.env['res.users']
        return self.user_id or c.user_id

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        N = self.env['ts.notification']
        for a in recs:
            user = a._ts_account()
            if user:
                N._notify(user, 'invite', '/invite/%s' % a.token, a.workspace_id)
        return recs

    def ts_share_attempt(self, attempt, code, user):
        a = super().ts_share_attempt(attempt, code, user)
        if a:
            for u in _staff_users(a.workspace_id, a.client_id.responsible_id):
                self.env['ts.notification']._notify(u, 'shared_with_panel', '/my/workspaces/%s/clients/%s' % (a.workspace_id.id, a.client_id.id), a.workspace_id)
        return a

    def action_revoke_share(self, user):
        res = super().action_revoke_share(user)
        for a in self:
            for u in _staff_users(a.workspace_id, a.client_id.responsible_id):
                self.env['ts.notification']._notify(u, 'share_revoked', '/my/workspaces/%s/clients/%s' % (a.workspace_id.id, a.client_id.id), a.workspace_id)
        return res

    # ------------------------------------------------------------------ reminders (INV-8)
    def _ts_reminder_due(self, today):
        """Is this invitation due for its one automatic reminder on `today` (a date in Tehran)?"""
        self.ensure_one()
        if self.state not in OPEN_STATES or self.reminder_count or self.withdrawn or self.declined:
            return False
        if self.client_id.contact_locked:
            return False
        if self.campaign_id and (self.campaign_id.state == 'closed' or not self.campaign_id.remind):
            return False
        if self.deadline:
            before = _cfg(self.env, 'reminder_before_days', 3)
            return self.deadline - timedelta(days=before) <= today <= self.deadline
        after = _cfg(self.env, 'reminder_after_days', 7)
        created = self.create_date.replace(tzinfo=UTC).astimezone(TEHRAN).date()
        return created + timedelta(days=after) <= today

    def _ts_sms_reminder_ok(self):
        """The SMS leg of a reminder: every condition of INV-8 (except the clock, checked by the caller)."""
        self.ensure_one()
        company = (self.company_id or self.env.company).sudo()
        c = self.client_id
        return bool(company.kv_enabled and company.ts_sms_reminder and self.invitee_phone and self.sms_consent and self.remind_ok
                    and not (c and (c.contact_locked or c.source == 'import')))

    def _ts_do_reminder(self):
        """Send the reminder of one invitation by every allowed channel. -> set of channels used."""
        self.ensure_one()
        used = set()
        c = self.client_id
        if c and c.contact_locked:
            return used
        user = self._ts_account()
        if user:
            row = self.env['ts.notification']._notify(user, 'reminder', '/invite/%s' % self.token, self.workspace_id)
            if row:
                used.add('app')
        if self._ts_sms_reminder_ok():
            N = self.env['ts.notification']
            phone = self.invitee_phone
            from odoo.addons.ts_sms.models.phone_otp import iran_mobile            # same normaliser as the invitation SMS
            number = iran_mobile(phone)
            day = N._today_start_utc()
            same_day = self.sudo().search_count([('invitee_phone', '=', phone), ('last_reminder_at', '>=', day)])
            if number and same_day < _cfg(self.env, 'sms_per_day', 5):
                company = (self.company_id or self.env.company).sudo()
                body = SMS_BODIES['reminder'] % {'url': self.invite_url()}
                if N._send_sms(company, number, body):
                    used.add('sms')
        self.write({'reminder_count': self.reminder_count + 1, 'last_reminder_at': fields.Datetime.now()})
        self.env['ts.audit.event'].sudo().log('notify.reminder', self, workspace=self.workspace_id, channels=sorted(used))
        return used

    @api.model
    def _cron_reminders(self):
        """Daily at 10:00 Tehran: the one automatic reminder of every open invitation that is due."""
        N = self.env['ts.notification']
        if N._quiet_now():
            return 0
        today = N._tehran_now().date()
        cand = self.sudo().search([('reminder_count', '=', 0), ('state', 'in', list(OPEN_STATES))], limit=500)
        n = 0
        for a in cand:
            if a._ts_reminder_due(today):
                a._ts_do_reminder()
                n += 1
        return n

    def ts_manual_reminder(self, member):
        """The «یادآوری» button: at most one per 24 hours and three in all, and not in the quiet hours.
        -> (ok, message)"""
        self.ensure_one()
        N = self.env['ts.notification']
        if self.state not in OPEN_STATES:
            return False, 'این دعوت دیگر باز نیست.'
        if self.reminder_count >= MAX_REMINDERS:
            return False, 'برای هر دعوت حداکثر ۳ یادآوری فرستاده می‌شود.'
        if self.last_reminder_at and self.last_reminder_at > fields.Datetime.now() - timedelta(hours=24):
            return False, 'در هر ۲۴ ساعت فقط یک یادآوری ممکن است.'
        if N._quiet_now():
            return False, 'در ساعت‌های آرام (۲۱ تا ۸) یادآوری نمی‌فرستیم؛ بعد از ساعت ۸ صبح دوباره امتحان کنید.'
        if self.campaign_id and self.campaign_id.state == 'closed':
            return False, 'این دعوت گروهی بسته شده است.'
        used = self._ts_do_reminder()
        if not used:
            return False, 'این شرکت‌کننده حساب کاربری یا موافقت پیامکی ندارد؛ پیوند دعوت را خودتان برایش بفرستید.'
        return True, 'یادآوری فرستاده شد.'


class TsAttemptNotify(models.Model):
    _inherit = 'ts.attempt'

    def action_submit(self, submission_key=None):
        was_done = self.state == 'done'
        res = super().action_submit(submission_key=submission_key)
        if res and not was_done and self.state == 'done':
            self._ts_notify_done()
        return res

    def _ts_notify_done(self):
        self.ensure_one()
        N = self.env['ts.notification']
        if self.user_id:
            N._notify(self.user_id, 'result_ready_participant', '/my/assessments/%s' % self.id, self.workspace_id)
        a = self.env['ts.assignment'].sudo().search([('attempt_id', '=', self.id)], limit=1)
        if a and a.share_level != 'none':
            for u in _staff_users(a.workspace_id, a.client_id.responsible_id):
                N._notify(u, 'result_ready_staff', '/my/workspaces/%s/clients/%s' % (a.workspace_id.id, a.client_id.id), a.workspace_id)


class TsWorkspaceNotify(models.Model):
    _inherit = 'ts.workspace'

    def _ts_tell_owners(self, type_):
        N = self.env['ts.notification']
        for ws in self:
            for m in ws.sudo().member_ids.filtered(lambda m: m.active and m.role == 'owner'):
                N._notify(m.user_id, type_, '/my/workspaces/%s' % ws.id, ws)

    def action_approve(self):
        pending = self.filtered(lambda w: not w.approved_on)
        res = super().action_approve()
        pending.filtered('approved_on')._ts_tell_owners('panel_approved')
        return res

    def action_reject(self):
        res = super().action_reject()
        self._ts_tell_owners('panel_rejected')
        return res

    def action_suspend(self):
        res = super().action_suspend()
        self._ts_tell_owners('panel_suspended')
        return res


class TsMemberInviteNotify(models.Model):
    _inherit = 'ts.member.invite'

    def action_accept(self, user, license_number=None):
        member = super().action_accept(user, license_number=license_number)
        if self.invited_by_id and self.invited_by_id != user:
            self.env['ts.notification']._notify(self.invited_by_id, 'member_joined', '/my/workspaces/%s/members' % self.workspace_id.id, self.workspace_id)
        return member


class TsClientNotify(models.Model):
    _inherit = 'ts.panel.client'

    def ts_request_handover(self, me, target):
        res = super().ts_request_handover(me, target)
        for c in self.filtered('handover_to_id'):          # only a request that waits for a decision
            for u in _staff_users(c.workspace_id):
                if u != me.user_id:
                    self.env['ts.notification']._notify(u, 'client_handover_request', '/my/workspaces/%s/clients/%s' % (c.workspace_id.id, c.id), c.workspace_id)
        return res


class TsJobNotify(models.Model):
    _inherit = 'ts.job'

    def ts_run(self, commit=True):
        res = super().ts_run(commit=commit)
        if commit:       # a job that ran in the background: the person is not waiting on the page
            for j in self:
                if j.state == 'done' and j.user_id:
                    self.env['ts.notification']._notify(
                        j.user_id, 'import_done' if j.kind == 'import_clients' else 'export_ready',
                        '/my/workspaces/%s/jobs/%s' % (j.workspace_id.id, j.id), j.workspace_id)
        return res
