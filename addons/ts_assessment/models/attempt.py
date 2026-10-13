import uuid

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .engine import ScoringError, contract_from_version, score as engine_score
from .instrument import BANDS, CONTENT_FORMATS
from .textfmt import (BAND_WORDS, DEF_HEADING, PARTICIPANT_HEADING, counseling_terms,  # noqa: F401 (re-exported)
                      split_interpretation)

# v2 (1405-07-19, UX audit 2026-10-11): consent pages explain autosave, stop/continue, locking, withdrawal and who sees
# v3 (1405-07-19, clinic phase 3): a battery invitation is agreed to once, on the first instrument's page, which names the
# battery and lists its instruments (ts_battery adds that block); the same consent is recorded on every instrument of it
# v4 (1405-07-20, UX audit 2026-10-12 G6): «در حسابم» / «در حسابتان» (glossary §7), a battery shows one battery-level
# limitation instead of the first instrument's, «نه تشخیص» once, who-sees wording «اشتراک‌گذاری» and «عامل»
CONSENT_VERSION = 'TS-CONSENT-1405-07-21-v6'   # v6 (take2): plain-language summary on top; v5 (onb1): «مشاوران همین مرکز»
BAND_FA = dict(BANDS)
COUNSELOR_HEADING = 'راهنمای مشاور'             # content v2 counselor sections
TALK_HEADING = 'پیشنهاد برای گفت‌وگو'
PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa_digits(value):
    return str(value).translate(PERSIAN_DIGITS)


def g2j(gy, gm, gd):
    """Gregorian -> Jalali (33-year arithmetic, valid 1244-1472 AP)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def jalali(dt, env=None, with_time=True):
    """UTC datetime -> 'YYYY/MM/DD HH:MM' Jalali in Asia/Tehran, Persian digits."""
    if not dt:
        return ''
    from zoneinfo import ZoneInfo
    local = dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Tehran'))
    y, m, d = g2j(local.year, local.month, local.day)
    s = '%04d/%02d/%02d' % (y, m, d)
    if with_time:
        s += ' ساعت %02d:%02d' % (local.hour, local.minute)
    return fa_digits(s)


JALALI_MONTHS = ('فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند')


def jalali_long(dt):
    """UTC datetime -> «۲۱ مهر ۱۴۰۵» (Asia/Tehran, month name, Persian digits) for participant pages (UX audit T7, PT7)."""
    if not dt:
        return ''
    from zoneinfo import ZoneInfo
    local = dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Tehran'))
    y, m, d = g2j(local.year, local.month, local.day)
    return fa_digits('%d %s %d' % (d, JALALI_MONTHS[m - 1], y))


class TsAttempt(models.Model):
    _name = 'ts.attempt'
    _description = 'اجرای سنجه'
    _order = 'id desc'

    name = fields.Char('شناسه', readonly=True, copy=False, default='/')
    user_id = fields.Many2one('res.users', 'کاربر', required=True, index=True, ondelete='restrict')
    partner_id = fields.Many2one(related='user_id.partner_id', store=True)
    instrument_id = fields.Many2one('ts.instrument', required=True, index=True, ondelete='restrict')
    version_id = fields.Many2one('ts.instrument.version', required=True, ondelete='restrict')
    workspace_id = fields.Many2one('ts.workspace', 'پنل', index=True)
    access_token = fields.Char(required=True, copy=False, index=True, default=lambda s: uuid.uuid4().hex)
    state = fields.Selection([
        ('consent', 'در انتظار رضایت'),
        ('in_progress', 'در حال پاسخ'),
        ('done', 'تکمیل‌شده'),
        ('error', 'خطا در نمره‌گذاری'),
    ], default='consent', required=True, index=True)
    respondent_role = fields.Selection([('self', 'خود شرکت‌کننده'), ('guardian', 'والد یا مراقب')], default='self')
    subject_label = fields.Char('نام یا عنوان کودک/نوجوان')
    consent_service = fields.Boolean('رضایت برای خدمت')
    consent_research = fields.Boolean('رضایت برای پژوهش')
    consent_at = fields.Datetime('زمان رضایت')
    consent_version = fields.Char('نسخهٔ متن رضایت')
    started_at = fields.Datetime('شروع')
    submitted_at = fields.Datetime('ارسال')
    submission_key = fields.Char(copy=False)
    answer_ids = fields.One2many('ts.attempt.answer', 'attempt_id', 'پاسخ‌ها')
    result_ids = fields.One2many('ts.attempt.result', 'attempt_id', 'نتایج')
    answered_count = fields.Integer(compute='_compute_progress')
    item_total = fields.Integer(related='version_id.active_item_count')
    progress = fields.Integer('پیشرفت (%)', compute='_compute_progress')
    engine_version = fields.Char(readonly=True)
    input_hash = fields.Char(readonly=True)
    output_hash = fields.Char(readonly=True)
    error_message = fields.Char(readonly=True)
    released = fields.Boolean('منتشرشده برای شرکت‌کننده', readonly=True)
    released_at = fields.Datetime(readonly=True)

    _token_unique = models.Constraint('unique(access_token)', 'duplicate token')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('ts.attempt') or '/'
        return super().create(vals_list)

    @api.depends('answer_ids', 'version_id')
    def _compute_progress(self):
        for a in self:
            n = len(a.answer_ids)
            total = a.version_id.active_item_count or 0
            a.answered_count = n
            a.progress = int(round(100.0 * n / total)) if total else 0

    # ---------------------------------------------------------------- helpers
    def _check_owner(self, user=None):
        user = user or self.env.user
        for a in self:
            if a.user_id != user:
                raise AccessError('این سنجه متعلق به شما نیست.')

    def active_items(self):
        self.ensure_one()
        return self.version_id.item_ids.filtered(lambda i: not i.disabled).sorted(lambda i: (i.sequence, i.source_question_id, i.id))

    def answers_map(self):
        self.ensure_one()
        return {a.item_id.id: a.value for a in self.answer_ids}

    def jalali(self, dt, with_time=True):
        return jalali(dt, self.env, with_time)

    def jalali_long(self, dt):
        return jalali_long(dt)

    def ts_progress_line(self, tu=False):
        """«۶ از ۲۲ پرسش را پاسخ داده‌اید؛ حدود ۲ دقیقه مانده» for the resume rows (/my, /my/assessments; W44, PT8).
        Likert attempts only; '' for others (the talent inventory and timed tasks have their own counters)."""
        self.ensure_one()
        v = self.version_id
        if 'mode' in v._fields and v.mode not in (False, 'single'):     # matrix (ts_talent) / task (ts_tasks)
            return ''
        total = self.version_id.active_item_count or 0
        if not total:
            return ''
        n = len(self.answer_ids)
        line = '%s از %s پرسش را پاسخ %s' % (fa_digits(n), fa_digits(total), 'داده‌ای' if tu else 'داده‌اید')
        minutes = self.instrument_id.duration_minutes or 0
        left = -(-(total - n) * minutes // total) if minutes else 0
        if left and n < total:
            line += '؛ حدود %s دقیقه مانده' % fa_digits(left)
        return line

    def ts_informal(self):
        """Copy register only (voice.md §2): True -> «تو» (students), False -> «شما» (adults, parents).
        Students: a minor client, an education panel, an adolescent instrument, or a self-declared minor (guardian
        consent row). A parent answering about a child is addressed with «شما». Never used for access decisions."""
        self.ensure_one()
        if self.instrument_id.audience == 'child':
            return False
        client = self['client_id'] if 'client_id' in self._fields else False
        if client and client.age_group in ('minor', 'adult'):
            return client.age_group == 'minor'
        ws = self['workspace_id'] if 'workspace_id' in self._fields else False
        if ws:
            return ws.purpose == 'education'
        if self.instrument_id.audience == 'adolescent':
            return True
        if 'ts.consent.record' in self.env:
            return bool(self.env['ts.consent.record'].sudo().search_count(
                [('attempt_id', '=', self.id), ('kind', '=', 'guardian')], limit=1))
        return False

    # ---------------------------------------------------------------- actions
    def give_consent(self, research=False, role='self', subject=None):
        self.ensure_one()
        if self.state != 'consent':
            return
        if self.instrument_id.audience == 'child' and role != 'guardian':
            raise UserError('این سنجه را باید ولی کودک (پدر، مادر یا سرپرست قانونی) دربارهٔ او تکمیل کند.')
        now = fields.Datetime.now()
        self.write({'consent_service': True, 'consent_research': bool(research), 'consent_at': now,
                    'consent_version': CONSENT_VERSION, 'state': 'in_progress', 'started_at': now,
                    'respondent_role': role, 'subject_label': (subject or '')[:80] or False})
        self.env['ts.audit.event'].log('attempt.consent', self, research=bool(research), role=role,
                                       consent_version=CONSENT_VERSION)

    def save_answer(self, item_id, value):
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError('این سنجه دیگر قابل ویرایش نیست.')
        item = self.env['ts.instrument.item'].browse(int(item_id))
        if not item.exists() or item.version_id != self.version_id or item.disabled:
            raise UserError('پرسش نامعتبر است.')
        value = int(value)
        if not self.version_id.scale_min <= value <= self.version_id.scale_max:
            raise UserError('پاسخ نامعتبر است.')
        Answer = self.env['ts.attempt.answer']
        existing = Answer.search([('attempt_id', '=', self.id), ('item_id', '=', item.id)], limit=1)
        if existing:
            if existing.value != value:
                existing.write({'value': value, 'answered_at': fields.Datetime.now()})
        else:
            Answer.create({'attempt_id': self.id, 'item_id': item.id, 'value': value, 'answered_at': fields.Datetime.now()})

    def action_submit(self, submission_key=None):
        """Idempotent final submission: a second submit (double click, retry
        after a dropped connection) returns the same scored attempt."""
        self.ensure_one()
        if self.state == 'done':
            return True
        if self.state != 'in_progress':
            raise UserError('این سنجه آمادهٔ ارسال نیست.')
        self.env.cr.execute('SELECT id FROM ts_attempt WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['state'])
        if self.state == 'done':
            return True
        answers = self.answers_map()
        contract = contract_from_version(self.version_id)
        try:
            out = engine_score(contract, answers)
        except ScoringError as e:
            missing = len(self.active_items()) - len(answers)
            if missing > 0:
                raise UserError('هنوز به %s پرسش پاسخ نداده‌اید.' % fa_digits(missing))
            self.write({'state': 'error', 'error_message': str(e)[:250]})
            self.env['ts.audit.event'].log('attempt.score_error', self, error=str(e)[:250])
            return False
        factors = {f.code: f for f in self.version_id.factor_ids}
        Result = self.env['ts.attempt.result']
        for r in out['results']:
            f = factors[r['factor']]
            band = f.band_ids.filtered(lambda b: b.band == r['band'])
            Result.create({
                'attempt_id': self.id, 'factor_id': f.id, 'score': r['score'], 'band': r['band'], 'band_id': band.id,
                'item_count': r['item_count'], 'answered_count': r['answered'], 'raw_total': r['raw_total'],
                'client_text': band.client_text, 'therapist_text': band.therapist_text,
                'content_version': band.content_version, 'content_format': band.content_format or 'book',
                'talk_points': band.talk_points or False, 'definition': f.definition or False,
            })
        now = fields.Datetime.now()
        self.write({'state': 'done', 'submitted_at': now, 'submission_key': submission_key or uuid.uuid4().hex,
                    'engine_version': out['engine'], 'input_hash': out['input_hash'], 'output_hash': out['output_hash'],
                    'released': True, 'released_at': now})
        self.env['ts.audit.event'].log('attempt.submit', self, instrument=self.instrument_id.code,
                                       version=self.version_id.contract_version, output_hash=out['output_hash'])
        return True

    def _ts_remap_items(self, item_map):
        """Move this open attempt's answers to another version's items ({old item id: new item}); the loader calls it
        before switching version_id. Returns the number of rows remapped, or None (nothing changed) when an answer has
        no counterpart."""
        self.ensure_one()
        answers = self.sudo().answer_ids
        if any(a.item_id.id not in item_map for a in answers):
            return None
        for a in answers:
            a.write({'item_id': item_map[a.item_id.id].id})
        return len(answers)

    def rescore_matches(self):
        """Historical reproducibility: re-run the engine on stored answers."""
        self.ensure_one()
        out = engine_score(contract_from_version(self.version_id), self.answers_map())
        return out['output_hash'] == self.output_hash

    def result_rows(self):
        self.ensure_one()
        return self.result_ids.sorted(lambda r: (r.factor_id.sequence, r.factor_id.id))


class TsAttemptAnswer(models.Model):
    _name = 'ts.attempt.answer'
    _description = 'پاسخ'
    _order = 'attempt_id, id'

    attempt_id = fields.Many2one('ts.attempt', required=True, ondelete='cascade', index=True)
    item_id = fields.Many2one('ts.instrument.item', required=True, ondelete='restrict')
    value = fields.Integer(required=True)
    answered_at = fields.Datetime()

    _one_answer = models.Constraint('unique(attempt_id, item_id)', 'one answer per item')


class TsAttemptResult(models.Model):
    _name = 'ts.attempt.result'
    _description = 'نتیجهٔ بُعد'
    _order = 'attempt_id, id'

    attempt_id = fields.Many2one('ts.attempt', required=True, ondelete='cascade', index=True)
    factor_id = fields.Many2one('ts.instrument.factor', required=True, ondelete='restrict')
    score = fields.Float(digits=(6, 4))
    band = fields.Selection(BANDS)
    band_id = fields.Many2one('ts.instrument.band', ondelete='restrict')
    item_count = fields.Integer()
    answered_count = fields.Integer()
    raw_total = fields.Float()
    client_text = fields.Text()
    therapist_text = fields.Text()
    content_version = fields.Char()
    # content v2 (1405-07-21): the report format of the band at submit time, its talk points and the factor definition,
    # copied like the texts so a result reads the same after a later content version
    content_format = fields.Selection(CONTENT_FORMATS, default='book', required=True)
    talk_points = fields.Text()
    definition = fields.Text()

    def score_fa(self):
        return fa_digits('%.2f' % self.score).replace('.', '٫')

    def position_pct(self):
        v = self.attempt_id.version_id
        return round(100.0 * (self.score - v.scale_min) / (v.scale_max - v.scale_min), 1)

    def band_fa(self):
        return BAND_FA.get(self.band, '')

    def client_sections(self, participant=True):
        """The participant text; participant=False keeps the «تحلیل» / «تفسیر» sub-headings (counselor view).
        Content v2: [(DEF_HEADING, definition), (PARTICIPANT_HEADING, text)], the same for both views."""
        if self.content_format == 'v2':
            return [(h, counseling_terms(b.strip())) for h, b in ((DEF_HEADING, self.definition or ''),
                                                                  (PARTICIPANT_HEADING, self.client_text or '')) if b.strip()]
        return split_interpretation(self.client_text, participant=participant)

    def therapist_sections(self):
        """Book texts: the parsed counselor guide. Content v2: the guide and the talk points as a bulleted list."""
        if self.content_format == 'v2':
            points = '\n'.join('• ' + line.strip().lstrip('•-* ').strip()
                                for line in (self.talk_points or '').splitlines() if line.strip())
            return [(h, counseling_terms(b.strip())) for h, b in ((COUNSELOR_HEADING, self.therapist_text or ''),
                                                                  (TALK_HEADING, points)) if b.strip()]
        return split_interpretation(self.therapist_text)
