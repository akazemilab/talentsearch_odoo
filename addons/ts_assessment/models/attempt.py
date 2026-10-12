import re
import uuid

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .engine import ScoringError, contract_from_version, score as engine_score
from .instrument import BANDS

# v2 (1405-07-19, UX audit 2026-10-11): consent pages explain autosave, stop/continue, locking, withdrawal and who sees
# v3 (1405-07-19, clinic phase 3): a battery invitation is agreed to once, on the first instrument's page, which names the
# battery and lists its instruments (ts_battery adds that block); the same consent is recorded on every instrument of it
# v4 (1405-07-20, UX audit 2026-10-12 G6): «در حسابم» / «در حسابتان» (glossary §7), a battery shows one battery-level
# limitation instead of the first instrument's, «نه تشخیص» once, who-sees wording «اشتراک‌گذاری» and «عامل»
CONSENT_VERSION = 'TS-CONSENT-1405-07-20-v5'   # v5 (onb1): «مشاوران همین مرکز» (the licence no longer gates results)
BAND_FA = dict(BANDS)
BAND_WORDS = {'Low': 'کم', 'Medium': 'متوسط', 'High': 'زیاد'}
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


# Owner decision 2026-10-11: the product speaks the language of counseling. The book's band texts are stored verbatim
# (never edited); these explicit phrases are mapped only when a text is shown. Each pattern needs a non-letter on both
# sides, so درماندگی / درمانده / درمانی / بیماری / بیمارستان are never touched. Order matters (longest first).
# Persian/Arabic letters, diacritics, ZWNJ/ZWJ; NOT punctuation (، ؛ ؟) or digits, which count as boundaries.
_FA_LETTER = '\u0620-\u065F\u066E-\u06D3\u06D5\u06EE\u06EF\u06FA-\u06FC\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u200c\u200d'
_COUNSELING_TERMS = [
    (r'روان[\u200c ]?درمانگران', 'مشاوران'),
    (r'روان[\u200c ]?درمانگر', 'مشاور'),
    (r'روان[\u200c ]?درمانی', 'مشاوره'),
    (r'درمانگران', 'مشاوران'),
    (r'درمانگر', 'مشاور'),
    (r'جلسات درمان', 'جلسات مشاوره'),
    (r'جلسه(?:ٔ|\u200cی| ی)? درمان', 'جلسهٔ مشاوره'),
    (r'(فرا?یند|فرآیند) درمان', r'\1 مشاوره'),
    (r'درمان[\u200c]?جویان', 'مراجعان'),
    (r'درمان[\u200c]?جو', 'مراجع'),
    (r'بیماران', 'مراجعان'),
    (r'بیمار', 'مراجع'),
    # UX audit 2026-10-12 (G6-P7-5, owner approved): the counselor guide's «پروتکل پیشنهادی» is medical register
    (r'پروتکل پیشنهادی', 'پیشنهادهای کاربردی برای جلسه'),
]
_COUNSELING_RE = [(re.compile(r'(?<![%s])%s(?![%s])' % (_FA_LETTER, pat, _FA_LETTER)), rep)
                  for pat, rep in _COUNSELING_TERMS]


def counseling_terms(text):
    """Display-time wording map for book texts (headings and bodies); the stored text is unchanged."""
    if not text:
        return text
    for rx, rep in _COUNSELING_RE:
        text = rx.sub(rep, text)
    return text


DEF_HEADING = 'این عامل چه چیزی را توصیف می‌کند'      # «تعریف عامل» (glossary §4: عامل, never بُعد)
PARTICIPANT_HEADING = 'تفسیر نتیجهٔ شما'             # «تفسیر سطح X» and, for the participant, its «تحلیل» / «تفسیر» parts
_SUB_HEADS = ('تحلیل', 'تفسیر')
_RANGE_HEAD = re.compile(r'نمرات\s*[\d۰-۹]')          # «تحلیل و تفسیر نمرات 60-80»: a block of the source's older 5-range scheme
_GLUED_HEAD = re.compile(r'(?<=[^\s#])\s*(?=#{2,}\s)')    # «… راهکارها### تحلیل و تفسیر نمرات 80-100:» (heading glued to a line)


def _heading_of(line):
    """A short line ending with ':' is a heading; markdown marks around it (#### / **) are ignored. None otherwise."""
    core = re.sub(r'^[#\s]+', '', line.strip()).replace('**', '').strip()
    if core.endswith(':') and len(core) < 60:
        return core[:-1].strip()
    return None


def _is_band_head(h):
    return bool(h) and (h.startswith('تفسیر سطح') or h.startswith('تحلیل و تفسیر سطح'))


def split_interpretation(text, participant=False):
    """The approved source texts follow a fixed shape:
        تفسیر نتیجه برای مراجع | راهنمای تخصصی درمانگر   (title line)
        عامل: <name>                                       (dropped: the factor heading is already on the page)
        تعریف عامل:  <definition>
        تفسیر سطح Low: / تحلیل و تفسیر سطح Low:  <body>, sometimes split into «تحلیل:» / «تفسیر:» parts
        پروتکل پیشنهادی: <counselor suggestions>           (therapist text only)
    Returns [(heading, body)], headings in Persian, bodies verbatim except the counseling word map (counseling_terms)
    and markdown marks (** and leading #).

    Display-time clean-up of the book texts (UX audit 2026-10-12, G6-PT3; data facts in docs/clinic/06_data_issues.md),
    the stored text is never changed:
    * Many band texts hold TWO variants of the band text (the source system had five score ranges and merged them into
      three bands): a band body of two blank-line-separated paragraphs, or a second «تحلیل:» / «تفسیر:» pair. Only the
      first variant is shown; it is the one written for the band.
    * A stray «تحلیل و تفسیر نمرات 60-80:» block (older range scheme) is not shown.
    * participant=True (the participant's own report): the band text and its «تحلیل» / «تفسیر» parts are one section
      «تفسیر نتیجهٔ شما» (one heading, one voice for the reader)."""
    if not text:
        return []
    lines = text.replace('\r', '').split('\n')
    lines = lines[1:] if lines and ':' not in lines[0] else lines
    flat = []
    for line in lines:
        flat.extend(_GLUED_HEAD.split(line) if '##' in line else [line])
    sections, head, buf = [], None, []
    for line in flat:
        s = line.strip()
        if re.match(r'^عامل\s*:', s) or re.fullmatch(r'-{3,}', s):
            continue
        h = _heading_of(s)
        if h is not None:
            if head is not None or buf:
                sections.append((head, '\n'.join(buf).strip()))
            head, buf = h, []
        else:
            buf.append(line.replace('**', ''))
    if head is not None or buf:
        sections.append((head, '\n'.join(buf).strip()))

    kept, in_band, seen_sub, dropping = [], False, set(), False
    for h, body in sections:
        if h and _RANGE_HEAD.search(h):
            dropping = True
            continue
        if h in _SUB_HEADS:
            if dropping or not body:       # an empty «تحلیل:» line is not a variant of its own
                continue
            if in_band:
                if h in seen_sub:          # second «تحلیل» / «تفسیر»: the next variant starts here
                    dropping = True
                    continue
                seen_sub.add(h)
            kept.append((h, body, in_band))
            continue
        dropping = False
        in_band = _is_band_head(h)
        seen_sub = set()
        if in_band:
            paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
            body = paras[0] if paras else ''
        kept.append((h, body, False))

    out = []
    for h, body, band_part in kept:
        if not body:
            continue
        if h:
            for en, fa in BAND_WORDS.items():
                h = re.sub(r'\b%s\b' % en, fa, h)
            if h.startswith('تعریف عامل'):
                h = DEF_HEADING
            elif h.startswith('تفسیر سطح'):
                h = PARTICIPANT_HEADING
            elif participant and band_part:
                if out and out[-1][0] == PARTICIPANT_HEADING:
                    out[-1] = (PARTICIPANT_HEADING, out[-1][1] + '\n\n' + counseling_terms(body))
                    continue
                h = PARTICIPANT_HEADING
        out.append((counseling_terms(h), counseling_terms(body)))
    return out


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
                'content_version': band.content_version,
            })
        now = fields.Datetime.now()
        self.write({'state': 'done', 'submitted_at': now, 'submission_key': submission_key or uuid.uuid4().hex,
                    'engine_version': out['engine'], 'input_hash': out['input_hash'], 'output_hash': out['output_hash'],
                    'released': True, 'released_at': now})
        self.env['ts.audit.event'].log('attempt.submit', self, instrument=self.instrument_id.code,
                                       version=self.version_id.contract_version, output_hash=out['output_hash'])
        return True

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

    def score_fa(self):
        return fa_digits('%.2f' % self.score).replace('.', '٫')

    def position_pct(self):
        v = self.attempt_id.version_id
        return round(100.0 * (self.score - v.scale_min) / (v.scale_max - v.scale_min), 1)

    def band_fa(self):
        return BAND_FA.get(self.band, '')

    def client_sections(self, participant=True):
        """The participant text; participant=False keeps the «تحلیل» / «تفسیر» sub-headings (counselor view)."""
        return split_interpretation(self.client_text, participant=participant)

    def therapist_sections(self):
        return split_interpretation(self.therapist_text)
