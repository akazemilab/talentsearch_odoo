"""Career reminders (docs/career/01_completion.md, phase A): one SMS that brings a person back to the step where the free
career match stopped. Same safety rules as the onboarding guide SMS (ts_onboard/models/onb3_nudge.py):

| kind      | when (hourly run)                                                          | link opens               |
|-----------|----------------------------------------------------------------------------|--------------------------|
| ip_stall  | interests started (at least one answer), not finished, 24 h without answer | the interests, same item |
| bg_stall  | interests finished, education/experience missing, 3 h                      | the two questions        |
| l2_invite | the list was seen, work styles never started, 3 days                       | the result page          |
| l2_stall  | work styles started, not finished, 24 h without answer                     | the work styles          |

Rules: the owner switch `ts_career.nudges_enabled` (default on); only a run whose «یادآوری پیامکی» is on (owner decision
2026-10-15: on by default, one tap turns it off on every career page and on the page the SMS link opens); one row per run
and kind (never twice); at most one career SMS a day and three in all per person; nothing between 22:00 and 08:00 Tehran
(queued, sent from 08:00); a reminder whose step is done is skipped; only to the mobile the person proved by code; the text
never names the test or a result; Persian digits; the link last. At most once: the row is claimed («sending») and that
claim committed before the gateway call."""
import hashlib
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models

from odoo.addons.ts_assessment.models.attempt import fa_digits

_logger = logging.getLogger(__name__)
TEHRAN, UTC = ZoneInfo('Asia/Tehran'), ZoneInfo('UTC')
KINDS = [('ip_stall', 'علایق نیمه‌کاره'), ('bg_stall', 'دو پرسش مانده'), ('l2_invite', 'دعوت به سبک‌های کاری'),
         ('l2_stall', 'سبک‌های کاری نیمه‌کاره')]
WAIT_H = {'ip_stall': 24, 'bg_stall': 3, 'l2_invite': 72, 'l2_stall': 24}
MAX_PER_RUN = 3
LOOK_BACK_DAYS = 30
TEMPLATES = {k: 'ts_career.sms_%s' % k for k, _ in KINDS}
FALLBACK = {
    'ip_stall': 'استعدادیاب\n%(left)s سؤال تا نتیجهٔ شما مانده است؛ پاسخ‌های قبلی ذخیره شده‌اند.\n%(link)s',
    'bg_stall': 'استعدادیاب\nفقط دو سؤال کوتاه تا دیدن نتیجه‌تان مانده است.\n%(link)s',
    'l2_invite': 'استعدادیاب\nبا یک بخش ۱۵ دقیقه‌ای، نتیجهٔ شما دقیق‌تر می‌شود. هر جا خواستید مکث کنید؛ پاسخ‌ها ذخیره می‌شوند.\n%(link)s',
    'l2_stall': 'استعدادیاب\n%(left)s جمله تا کامل شدن بخش دوم نتیجه‌تان مانده است؛ از همان‌جا ادامه دهید.\n%(link)s',
}


def _int(env, key, default):
    raw = (env['ir.config_parameter'].sudo().get_str('ts_career.' + key) or '').strip()
    return int(raw) if raw.isdigit() else default


class TsCareerNudge(models.Model):
    _name = 'ts.career.nudge'
    _description = 'Talent Search career reminder SMS'
    _order = 'id desc'

    run_id = fields.Many2one('ts.career.run', required=True, index=True, ondelete='cascade')
    kind = fields.Selection(KINDS, required=True, index=True)
    state = fields.Selection([('queued', 'در صف'), ('sending', 'در حال ارسال'), ('sent', 'ارسال شد'), ('failed', 'نرسید'),
                              ('skipped', 'فرستاده نشد')], default='queued', required=True, index=True)
    due_at = fields.Datetime(default=fields.Datetime.now, required=True)
    claimed_at = fields.Datetime(readonly=True)
    sent_at = fields.Datetime(readonly=True)
    came_back_at = fields.Datetime('بازگشت با پیوند', readonly=True)
    reason = fields.Char('دلیل فرستاده‌نشدن')

    _run_kind = models.UniqueIndex('(run_id, kind)')

    # ------------------------------------------------------------------ rules
    @api.model
    def _enabled(self):
        return (self.env['ir.config_parameter'].sudo().get_str('ts_career.nudges_enabled') or '1').strip().lower() \
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
    def _idle_since(self, attempt):
        """When the person last answered in `attempt` (None: no answer yet)."""
        self.env['ts.attempt.answer'].flush_model()
        self.env.cr.execute('SELECT max(write_date) FROM ts_attempt_answer WHERE attempt_id = %s', [attempt.id])
        row = self.env.cr.fetchone()
        return row and row[0]

    @api.model
    def _due_kind(self, run, now_utc):
        """The one reminder this run is waiting for right now (time included), or None."""
        st = run.ts_state()
        if not st['ip_done']:
            ip = st['ip']
            if ip and ip.state == 'in_progress':
                last = self._idle_since(ip)
                if last and last <= now_utc - timedelta(hours=WAIT_H['ip_stall']):
                    return 'ip_stall'
            return None
        if not st['bg_done']:
            ip = run.ts_attempt('CAREER-IP-60', done=True)
            at = ip.submitted_at or ip.write_date
            return 'bg_stall' if at and at <= now_utc - timedelta(hours=WAIT_H['bg_stall']) else None
        hx = st['hex']
        if not hx:
            seen = run.computed_at
            return 'l2_invite' if seen and seen <= now_utc - timedelta(hours=WAIT_H['l2_invite']) else None
        if not st['hex_done'] and hx.state == 'in_progress':
            last = self._idle_since(hx)
            if last and last <= now_utc - timedelta(hours=WAIT_H['l2_stall']):
                return 'l2_stall'
        return None

    def _ts_still_due(self):
        """The step of this reminder is still open (the clock is not checked again)."""
        self.ensure_one()
        st = self.run_id.sudo().ts_state()
        return {'ip_stall': not st['ip_done'],
                'bg_stall': st['ip_done'] and not st['bg_done'],
                'l2_invite': st['bg_done'] and not st['hex'],
                'l2_stall': bool(st['hex']) and not st['hex_done']}.get(self.kind, False)

    # ------------------------------------------------------------------ the hourly run
    @api.model
    def _cron_career_nudges(self):
        return self._ts_run(commit=True)

    @api.model
    def _ts_run(self, now=None, commit=False):
        """Queue the reminders that came due, then send what may go now. `now` (aware Tehran time) is for the suites."""
        if not self._enabled():
            return 0
        now_utc = (now or self._tehran_now()).astimezone(UTC).replace(tzinfo=None)
        Run = self.env['ts.career.run'].sudo()
        runs = Run.search([('remind', '=', True), ('create_date', '>=', now_utc - timedelta(days=LOOK_BACK_DAYS))])
        for run in runs:
            try:
                if self.sudo().search_count([('run_id', '=', run.id), ('state', 'in', ('sent', 'sending'))]) >= MAX_PER_RUN:
                    continue
                kind = self._due_kind(run, now_utc)
                if kind and not self.sudo().search_count([('run_id', '=', run.id), ('kind', '=', kind)], limit=1):
                    with self.env.cr.savepoint():
                        self.sudo().create({'run_id': run.id, 'kind': kind})
            except Exception:       # noqa: BLE001 - one run never stops the others
                _logger.exception('ts_career: reminder for run %s not queued', run.id)
        if commit:
            self.env.cr.commit()
        queued = self.sudo().search([('state', '=', 'queued')], order='id')
        return queued._ts_send(now=now, commit=commit)

    # ------------------------------------------------------------------ sending
    def _ts_send(self, now=None, commit=False):
        if not self:
            return 0
        cr = self.env.cr
        self.env['ts.career.nudge'].flush_model()
        cr.execute("SELECT id FROM ts_career_nudge WHERE id IN %s AND state = 'queued' ORDER BY id FOR UPDATE SKIP LOCKED",
                   [tuple(self.ids)])
        rows = self.sudo().browse([r[0] for r in cr.fetchall()])
        rows.invalidate_recordset()
        plan = []
        for row in rows:
            try:
                with cr.savepoint():
                    job = row._ts_claim(now)
                if job:
                    plan.append((row, job))
            except Exception:       # noqa: BLE001
                _logger.exception('ts_career: reminder %s failed', row.id)
        if commit:
            cr.commit()             # the claims («sending») are durable before any gateway call
        sent = 0
        for row, (company, number, body, partner_id) in plan:
            ok = False
            try:
                ok = bool(self.env['ts.notification']._send_sms(company, number, body, partner_id))
            except Exception:       # noqa: BLE001
                _logger.exception('ts_career: reminder %s gateway call failed', row.id)
            try:
                with cr.savepoint():
                    row._ts_mark(ok, now)
            except Exception:       # noqa: BLE001 - the row stays «sending»: never sent twice
                _logger.exception('ts_career: reminder %s result not written', row.id)
            if commit:
                cr.commit()
            sent += ok
        return sent

    def _ts_mark(self, ok, now=None):
        self.ensure_one()
        when = (now or self._tehran_now()).astimezone(UTC).replace(tzinfo=None)
        self.write({'state': 'sent' if ok else 'failed', 'sent_at': when})
        self.env['ts.audit.event'].sudo().log('career.nudge', self.run_id, kind=self.kind, outcome='ok' if ok else 'error')
        if ok:
            self.env['ts.funnel.event'].ts_log_career('nudge_sent', self.run_id)

    def _ts_claim(self, now=None):
        """Every rule of one queued row: None (skipped, or waiting) or (company, number, body, partner) with the row
        marked «sending»."""
        self.ensure_one()
        run = self.run_id.sudo()
        user = run.user_id
        skip = None
        if not self._enabled():
            skip = 'switch_off'
        elif not run.remind:
            skip = 'opted_out'
        elif not user.active or user._is_public():
            skip = 'no_account'
        elif not self._ts_still_due():
            skip = 'step_done'
        elif self.search_count([('run_id', '=', run.id), ('state', 'in', ('sent', 'sending')), ('id', '!=', self.id)]) \
                >= MAX_PER_RUN:
            skip = 'max_reached'
        if skip:
            self.write({'state': 'skipped', 'reason': skip})
            return False
        if self._quiet(now):
            return False                                   # waits for 08:00 Tehran (hourly run)
        if self.search_count([('run_id', '=', run.id), ('state', 'in', ('sent', 'sending')), ('id', '!=', self.id),
                              '|', ('sent_at', '>=', self._day_start_utc()), ('state', '=', 'sending')], limit=1):
            return False                                   # one career SMS a day: tomorrow
        site = self.env.ref('ts_website.website_ts', raise_if_not_found=False)
        company = ((site and site.sudo().company_id) or self.env.company).sudo()
        phones = user.sudo()._ts_verified_phones()
        from odoo.addons.ts_sms.models.phone_otp import iran_mobile
        number = iran_mobile(phones[0]) if phones else False
        if not (company.kv_enabled and number):
            self.write({'state': 'skipped', 'reason': 'no_sms' if number else 'no_phone'})
            return False
        from odoo.addons.ts_kavenegar.tools.guard import sms_route_allowed
        if not sms_route_allowed(self.env):
            self.write({'state': 'skipped', 'reason': 'not_production'})
            return False
        body = self._ts_body()
        self.write({'state': 'sending', 'claimed_at': fields.Datetime.now()})
        return company, number, body, user.partner_id.id

    def _ts_values(self):
        self.ensure_one()
        run = self.run_id.sudo()
        vals = {'link': run.ts_short_url(), 'left': ''}
        code = {'ip_stall': 'CAREER-IP-60', 'l2_stall': 'CAREER-HEXACO-1'}.get(self.kind)
        if code:
            at = run.ts_attempt(code, done=False)
            if at:
                vals['left'] = fa_digits(max(0, (at.version_id.active_item_count or 0) - len(at.answer_ids)))
        return vals

    def _ts_body(self):
        self.ensure_one()
        vals = self._ts_values()
        return self.env['ts.brand'].sms_render(TEMPLATES[self.kind], self, values=vals,
                                               fallback=lambda: FALLBACK[self.kind] % vals)


class TsFunnelCareer(models.Model):
    _inherit = 'ts.funnel.event'

    step = fields.Selection(selection_add=[
        ('career_view', 'آزمون شغلی: دیدن صفحهٔ آغاز'), ('career_start', 'آزمون شغلی: شروع'),
        ('half', 'نیمهٔ سنجه'), ('bg_done', 'آزمون شغلی: دو پرسش'), ('result_view', 'آزمون شغلی: دیدن فهرست'),
        ('nudge_sent', 'آزمون شغلی: یادآوری فرستاده شد'), ('nudge_back', 'آزمون شغلی: بازگشت با یادآوری'),
        ('remind_off', 'آزمون شغلی: خاموش کردن یادآوری'),
    ], ondelete={k: 'cascade' for k in ('career_view', 'career_start', 'half', 'bg_done', 'result_view', 'nudge_sent',
                                         'nudge_back', 'remind_off')})

    @api.model
    def ts_log_career(self, step, run, instrument=None):
        """One row per run and step without a request (the hourly run): the step, the day and hour, and a salted hash of
        the run, so nothing points at a person. Never raises."""
        try:
            h = hashlib.sha256(('%s:career:%s' % (self._ts_salt(), run.id)).encode()).hexdigest()[:24]
            S = self.sudo()
            inst = instrument.id if instrument else False
            if S.search_count([('step', '=', step), ('session_hash', '=', h), ('instrument_id', '=', inst)], limit=1):
                return S.browse()
            with self.env.cr.savepoint():
                return S.create({'step': step, 'session_hash': h, 'entry': 'user', 'instrument_id': inst})
        except Exception:       # noqa: BLE001 - measuring never breaks the work
            return self.browse()
