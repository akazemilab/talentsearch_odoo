"""onb3 nudges (docs/onboarding/03_panel_first_session.md, section «پیامک‌های راهنما»).

SMS first, each text a native sms.template rendered by ts.brand.sms_render (rules of docs/clinic/05_sms_texts.md: no test,
client or result named, Persian digits, the link last). One row per member and kind (`key`), so nothing is sent twice.

| kind          | when                                                          | to                       |
|---------------|---------------------------------------------------------------|--------------------------|
| welcome       | the panel is made                                             | the owner who made it    |
| stall_3h      | 3 h, no try-out of the owner and no real invitation          | owners                   |
| stall_24h     | 24 h, no real invitation (link to the one-screen invitation) | owners                   |
| first_result  | the first real shared result is ready                        | owners + inviting member |
| digest        | weekly (Saturday from 09:00 Tehran), active panels only       | owners                   |
| (7 days, no result: no SMS - a back-office activity «تماس شخصی با پنل …» for the EOT team)                          |

Rules: the switch `ts_onboard.nudges_enabled` (default on); at most one guide SMS a member a day (the first-result SMS is
an answer to the member's own invitation and is never held back by the cap); a stall nudge stops once its step is done;
no SMS between 22:00 and 08:00 Tehran (queued, sent by the hourly run from 08:00); a suspended or closed panel gets
nothing; each member opts out on his own profile («پیامک‌های راهنما»). Separate from the global staff-SMS switch.
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models

from odoo.addons.ts_assessment.models.attempt import fa_digits

from .onb3 import REAL, sms_allowed

_logger = logging.getLogger(__name__)
TEHRAN, UTC = ZoneInfo('Asia/Tehran'), ZoneInfo('UTC')
KINDS = [('welcome', 'خوش‌آمد'), ('stall_3h', 'سه ساعت بی‌کار'), ('stall_24h', 'یک روز بی‌دعوت'),
         ('first_result', 'نخستین نتیجه'), ('digest', 'خلاصهٔ هفتگی')]
CAPPED = ('welcome', 'stall_3h', 'stall_24h', 'digest')
OPEN = ('invited', 'opened', 'accepted', 'in_progress')
TEMPLATES = {'welcome': 'ts_onboard.sms_onb_welcome', 'stall_3h': 'ts_onboard.sms_onb_try',
             'stall_24h': 'ts_onboard.sms_onb_invite', 'first_result': 'ts_onboard.sms_onb_first_result',
             'digest': 'ts_onboard.sms_onb_digest'}
FALLBACK = {
    'welcome': 'استعدادیاب\nپنل %(panel)s ساخته شد. نخستین قدم: خودتان امتحان کنید.\n%(link)s',
    'stall_3h': 'استعدادیاب\nچند دقیقه وقت دارید؟ اول خودتان ببینید %(one)s چه می‌بیند.\n%(link)s',
    'stall_24h': 'استعدادیاب\n%(invite)s\n%(link)s',
    'first_result': 'استعدادیاب\nنخستین نتیجه در پنل %(panel)s آماده است.\n%(link)s',
    'digest': 'استعدادیاب\nاین هفته در پنل %(panel)s: %(n_inv)s دعوت، %(n_done)s نتیجه، %(n_wait)s در انتظار.\n%(link)s',
}


def _int(env, key, default):
    raw = (env['ir.config_parameter'].sudo().get_str('ts_onboard.' + key) or '').strip()
    return int(raw) if raw.isdigit() else default


class TsOnbNudge(models.Model):
    _name = 'ts.onb.nudge'
    _description = 'Talent Search onboarding guide SMS (onb3)'
    _order = 'id desc'

    workspace_id = fields.Many2one('ts.workspace', required=True, index=True, ondelete='cascade')
    member_id = fields.Many2one('ts.workspace.member', required=True, index=True, ondelete='cascade')
    kind = fields.Selection(KINDS, required=True, index=True)
    key = fields.Char(required=True)
    state = fields.Selection([('queued', 'در صف'), ('sent', 'ارسال شد'), ('failed', 'نرسید'), ('skipped', 'فرستاده نشد')],
                             default='queued', required=True, index=True)
    due_at = fields.Datetime(default=fields.Datetime.now, required=True)
    sent_at = fields.Datetime(readonly=True)
    reason = fields.Char('دلیل فرستاده‌نشدن')

    _member_key = models.UniqueIndex('(member_id, key)')

    # ------------------------------------------------------------------ rules
    @api.model
    def _enabled(self):
        return (self.env['ir.config_parameter'].sudo().get_str('ts_onboard.nudges_enabled') or '1').strip().lower() \
            not in ('0', 'off', 'false', 'no')

    @api.model
    def _tehran_now(self):
        return datetime.now(TEHRAN)

    @api.model
    def _quiet(self, now=None):
        now = now or self._tehran_now()
        start, end = _int(self.env, 'quiet_start', 22), _int(self.env, 'quiet_end', 8)
        return now.hour >= start or now.hour < end

    @api.model
    def _day_start_utc(self):
        local = self._tehran_now().replace(hour=0, minute=0, second=0, microsecond=0)
        return local.astimezone(UTC).replace(tzinfo=None)

    @api.model
    def _owners(self, ws):
        return ws.sudo().member_ids.filtered(lambda m: m.active and m.role == 'owner')

    @api.model
    def _new(self, ws, member, kind, key=None, due=None):
        """One row per member and key; an existing row is returned untouched."""
        key = key or kind
        old = self.sudo().search([('member_id', '=', member.id), ('key', '=', key)], limit=1)
        if old:
            return old, False
        with self.env.cr.savepoint():
            row = self.sudo().create({'workspace_id': ws.id, 'member_id': member.id, 'kind': kind, 'key': key,
                                      'due_at': due or fields.Datetime.now()})
        return row, True

    # ------------------------------------------------------------------ events
    @api.model
    def ts_on_panel_created(self, ws):
        for m in self._owners(ws)[:1]:
            row, new = self._new(ws, m, 'welcome')
            if new:
                row._ts_try_send()

    @api.model
    def ts_on_first_result(self, a):
        ws = a.workspace_id.sudo()
        members = self._owners(ws)
        inviter = ws.member_ids.filtered(lambda m: m.active and a.invited_by_id and m.user_id == a.invited_by_id)
        for m in (members | inviter):
            row, new = self._new(ws, m, 'first_result')
            if new:
                row._ts_try_send()

    # ------------------------------------------------------------------ sending
    def _ts_still_due(self):
        """A stall nudge stops as soon as its step is done; the others always stand."""
        self.ensure_one()
        ws = self.workspace_id.sudo()
        A = self.env['ts.assignment'].sudo()
        invited = bool(ws.ts_onb_first_invite_at) or bool(A.search_count([('workspace_id', '=', ws.id)] + REAL, limit=1))
        if self.kind == 'stall_3h':
            tried = bool(A.search_count([('workspace_id', '=', ws.id), ('ts_preview', '=', True),
                                         ('user_id', '=', self.member_id.user_id.id)], limit=1))
            return not tried and not invited
        if self.kind == 'stall_24h':
            return not invited
        return True

    def _ts_try_send(self, now=None):
        """Send one queued row now if every rule allows it; otherwise leave it queued or mark it skipped."""
        for row in self.sudo().filtered(lambda r: r.state == 'queued'):
            try:
                with self.env.cr.savepoint():
                    row._ts_send_one(now)
            except Exception:       # noqa: BLE001 - one row never stops the others
                _logger.exception('ts_onboard: nudge %s failed', row.id)

    def _ts_send_one(self, now=None):
        self.ensure_one()
        ws, m = self.workspace_id.sudo(), self.member_id.sudo()
        skip = None
        if not self._enabled():
            skip = 'switch_off'
        elif ws.state != 'active':
            skip = 'panel_inactive'
        elif not m.active or not m.ts_guide_sms:
            skip = 'opted_out' if m.active else 'member_left'
        elif not self._ts_still_due():
            skip = 'step_done'
        if skip:
            self.write({'state': 'skipped', 'reason': skip})
            return False
        if self._quiet(now):
            return False                                   # waits for 08:00 Tehran (hourly run)
        if self.kind in CAPPED and self.search_count([
                ('member_id', '=', m.id), ('state', '=', 'sent'), ('kind', 'in', list(CAPPED)),
                ('sent_at', '>=', self._day_start_utc()), ('id', '!=', self.id)], limit=1):
            return False                                   # one guide SMS a member a day: tomorrow
        company = (ws.company_id or self.env.company).sudo()
        phones = m.user_id.sudo()._ts_verified_phones()
        from odoo.addons.ts_sms.models.phone_otp import iran_mobile
        number = iran_mobile(phones[0]) if phones else False
        if not (company.kv_enabled and number):
            self.write({'state': 'skipped', 'reason': 'no_sms' if number else 'no_phone'})
            return False
        if not sms_allowed(self.env):
            self.write({'state': 'skipped', 'reason': 'not_production'})
            return False
        ok = self.env['ts.notification']._send_sms(company, number, self._ts_body(), m.user_id.partner_id.id)
        # the clock of the rules (quiet hours, one a day) is the one that stamps the row
        self.write({'state': 'sent' if ok else 'failed',
                    'sent_at': self._tehran_now().astimezone(UTC).replace(tzinfo=None)})
        self.env['ts.audit.event'].sudo().log('onboarding.nudge', self, workspace=ws, member=m, kind=self.kind,
                                              outcome='ok' if ok else 'error')
        return ok

    def _ts_values(self):
        self.ensure_one()
        from odoo.addons.ts_brand.models.short import site_base
        ws = self.workspace_id.sudo()
        base = site_base(self.env)
        w = ws.ts_onb_words()
        kind = ws.ts_onb_kind()
        vals = {'panel': fa_digits(ws.ts_sms_sender() if hasattr(ws, 'ts_sms_sender') else ws.name), 'one': w['one'],
                'link': '%s/my/workspaces/%s' % (base, ws.id)}
        if self.kind == 'stall_24h':
            if kind == 'hr':
                vals['invite'] = 'موقعیت نمونهٔ پنل %s آماده است؛ نخستین داوطلب‌ها را دعوت کنید.' % vals['panel']
                vals['link'] = '%s/my/workspaces/%s/positions' % (base, ws.id)
            else:
                vals['invite'] = 'پیوند همیشگی پنل %s آماده است؛ آن را برای نخستین %s بفرستید.' % (vals['panel'], w['one'])
                vals['link'] = '%s/my/workspaces/%s/invites/new?mode=link' % (base, ws.id)
        if self.kind == 'digest':
            vals.update(self._ts_week_counts(ws))
        return vals

    @api.model
    def _ts_week_counts(self, ws):
        A = self.env['ts.assignment'].sudo()
        since = fields.Datetime.now() - timedelta(days=7)
        dom = [('workspace_id', '=', ws.id)] + REAL
        return {'n_inv': fa_digits(A.search_count(dom + [('create_date', '>=', since)])),
                'n_done': fa_digits(A.search_count(dom + [('state', '=', 'done'), ('attempt_id.submitted_at', '>=', since)])),
                'n_wait': fa_digits(A.search_count(dom + [('state', 'in', list(OPEN))]))}

    def _ts_body(self):
        self.ensure_one()
        vals = self._ts_values()
        return self.env['ts.brand'].sms_render(TEMPLATES[self.kind], self.workspace_id.sudo(), values=vals,
                                               fallback=lambda: FALLBACK[self.kind] % vals)

    # ------------------------------------------------------------------ the hourly run
    @api.model
    def _cron_onb_nudges(self):
        """Hourly: queue the nudges that came due, send what may go now, the weekly digest, the 7-day follow-up."""
        if not self._enabled():
            return 0
        now = fields.Datetime.now()
        WS = self.env['ts.workspace'].sudo()
        # stall nudges for panels made in the last 8 days (onb3 panels only: ts_onb_start; a panel older than the release
        # has its follow-up marked by the migration and gets no stall SMS)
        young = WS.search([('state', '=', 'active'), ('ts_onb_start', '=', True), ('ts_onb_followup_at', '=', False),
                           ('create_date', '>=', now - timedelta(days=8))])
        for ws in young:
            age = now - ws.create_date
            for m in self._owners(ws):
                if age >= timedelta(hours=24):
                    self._new(ws, m, 'stall_24h')
                    # the later nudge says more (with the link): a 3-hour nudge still waiting gives way to it
                    self.sudo().search([('member_id', '=', m.id), ('kind', '=', 'stall_3h'), ('state', '=', 'queued')]).write(
                        {'state': 'skipped', 'reason': 'superseded'})
                    if not self.sudo().search_count([('member_id', '=', m.id), ('kind', '=', 'stall_3h')]):
                        row, _new = self._new(ws, m, 'stall_3h')
                        row.write({'state': 'skipped', 'reason': 'superseded'})
                elif age >= timedelta(hours=3):
                    self._new(ws, m, 'stall_3h')
        # the 7-day follow-up (no SMS): one back-office activity for the EOT team
        old = WS.search([('state', '=', 'active'), ('ts_onb_start', '=', True), ('ts_onb_result_ready_at', '=', False),
                         ('ts_onb_followup_at', '=', False), ('create_date', '<=', now - timedelta(days=7))])
        for ws in old:
            self._ts_followup(ws)
        # the weekly digest: Saturday (the first day of the Iranian week) from 09:00 Tehran, active panels only
        t = self._tehran_now()
        if t.weekday() == 5 and t.hour >= 9:
            self._ts_digest(t)
        # rows queued during this run are due too (their due_at is a little after `now`)
        rows = self.sudo().search([('state', '=', 'queued'), ('due_at', '<=', fields.Datetime.now())], order='id', limit=300)
        rows._ts_try_send()
        return len(rows)

    @api.model
    def _ts_digest(self, t):
        key = 'digest:%s' % t.strftime('%G-%V')
        A = self.env['ts.assignment'].sudo()
        since = fields.Datetime.now() - timedelta(days=7)
        ws_ids = {r['workspace_id'][0] for r in A.search_read(
            [('create_date', '>=', since)] + REAL, ['workspace_id'])} | {r['workspace_id'][0] for r in A.search_read(
            [('state', '=', 'done'), ('attempt_id.submitted_at', '>=', since)] + REAL, ['workspace_id'])}
        for ws in self.env['ts.workspace'].sudo().browse(sorted(ws_ids)).filtered(lambda w: w.state == 'active'):
            for m in self._owners(ws):
                self._new(ws, m, 'digest', key=key)

    @api.model
    def _ts_followup(self, ws):
        """«تماس شخصی با پنل …»: one activity on the panel for a platform manager (no SMS, no client data)."""
        ws = ws.sudo()
        try:
            ICP = self.env['ir.config_parameter'].sudo()
            uid = int(ICP.get_str('ts_onboard.followup_user_id') or 0)
            user = self.env['res.users'].sudo().browse(uid).exists() if uid else self.env['res.users']
            if not user or not user.active or user.share:
                group = self.env.ref('ts_core.group_ts_manager')
                user = self.env['res.users'].sudo().search([('group_ids', 'in', group.id), ('share', '=', False),
                                                            ('active', '=', True), ('id', '!=', 1)], order='id', limit=1)
            xmlid = 'mail.mail_activity_data_call' if self.env.ref('mail.mail_activity_data_call', raise_if_not_found=False) \
                else 'mail.mail_activity_data_todo'
            n_inv = self.env['ts.assignment'].sudo().search_count([('workspace_id', '=', ws.id)] + REAL)
            kind = dict(ws._fields['ts_kind'].selection).get(ws.ts_onb_kind(), '')
            with self.env.cr.savepoint():
                ws.activity_schedule(
                    act_type_xmlid=xmlid,
                    summary='تماس شخصی با پنل %s' % ws.name,
                    note='این پنل (%s) هفت روز پیش ساخته شد و هنوز نتیجه‌ای ندارد؛ %s دعوت فرستاده است. یک تماس کوتاه و '
                         'شخصی برای کمک به نخستین دعوت پیشنهاد کنید.' % (kind, fa_digits(n_inv)),
                    user_id=user.id if user else self.env.uid, date_deadline=fields.Date.today())
            ws.ts_onb_followup_at = fields.Datetime.now()
            self.env['ts.audit.event'].sudo().log('onboarding.followup', ws, workspace=ws)
        except Exception:       # noqa: BLE001 - the follow-up never stops the hourly run
            _logger.exception('ts_onboard: follow-up activity for panel %s failed', ws.id)
