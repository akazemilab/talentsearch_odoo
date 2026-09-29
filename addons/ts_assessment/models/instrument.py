import math
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

BANDS = [('low', 'کم'), ('medium', 'متوسط'), ('high', 'زیاد')]
AUDIENCES = [
    ('adult', 'بزرگسال (پاسخ‌دهی شخصی)'),
    ('adolescent', 'نوجوان (با اطلاع و رضایت ولی)'),
    ('child', 'کودک (پاسخ‌دهی والد یا مراقب دربارهٔ کودک)'),
]
# Scale of every source question (verified: 1,340 Odoo `scale` questions, 1-5).
# Only inventory_012 carried anchor labels in the source (min/mid/max); the
# intermediate anchors complete the same five-point wording for all instruments.
SCALE = [(1, 'بسیار کم'), (2, 'کم'), (3, 'متوسط'), (4, 'زیاد'), (5, 'بسیار زیاد')]
SECONDS_PER_ITEM = 8


class TsInstrument(models.Model):
    _name = 'ts.instrument'
    _description = 'سنجهٔ تلنت سرچ'
    _inherit = ['mail.thread']
    _order = 'sequence, code'

    name = fields.Char('نام کامل', required=True, tracking=True)
    title = fields.Char('عنوان نمایشی', compute='_compute_title', store=True)
    code = fields.Char('کد', required=True, index=True, readonly=True)
    slug = fields.Char('نشانی', compute='_compute_title', store=True, index=True)
    sequence = fields.Integer(default=10)
    category = fields.Char('دسته')
    audience = fields.Selection(AUDIENCES, 'مخاطب', required=True, default='adult')
    purpose = fields.Selection([('personal', 'خودشناسی و مشاوره'), ('employment', 'استخدام')],
                               'کاربرد', default='personal', required=True,
                               help='سنجه‌های «خودشناسی و مشاوره» در فرایند استخدام قابل انتخاب نیستند.')
    state = fields.Selection([
        ('draft', 'پیش‌نویس'),
        ('approved', 'تأییدشده'),
        ('published', 'منتشرشده'),
        ('retired', 'بازنشسته'),
    ], 'وضعیت', default='draft', required=True, tracking=True)
    version_ids = fields.One2many('ts.instrument.version', 'instrument_id', 'نسخه‌ها')
    current_version_id = fields.Many2one('ts.instrument.version', 'نسخهٔ جاری', readonly=True)
    active_item_count = fields.Integer(related='current_version_id.active_item_count', string='تعداد پرسش')
    factor_count = fields.Integer(related='current_version_id.scored_factor_count', string='تعداد بُعد')
    duration_minutes = fields.Integer('زمان تقریبی (دقیقه)', compute='_compute_duration', store=True)
    intended_use = fields.Text('کاربرد مجاز')
    limitations = fields.Text('محدودیت‌ها')
    rights_note = fields.Text('مالکیت و حق استفاده')
    evidence_note = fields.Text('شواهد')
    approved_by_id = fields.Many2one('res.users', 'تأییدکننده', readonly=True)
    approved_at = fields.Datetime('زمان تأیید', readonly=True)
    approval_note = fields.Text('سند تأیید', readonly=True)
    source_xmlid = fields.Char('شناسهٔ منبع', readonly=True)
    source_record_id = fields.Integer('ردیف منبع', readonly=True)
    attempt_count = fields.Integer(compute='_compute_attempt_count')

    _code_unique = models.Constraint('unique(code)', 'کد سنجه باید یکتا باشد.')

    @staticmethod
    def _ts_base_title(name):
        return re.sub(r'\s*-\s*\d+\s*$', '', name or '').strip()

    @api.depends('name')
    def _compute_title(self):
        # Titles drop the source's trailing item count ("... - 48"). Two source
        # instruments share a base name (inventory_003/004, 48 and 72 items):
        # those keep the count so title and URL stay unique.
        for rec in self:
            base = self._ts_base_title(rec.name)
            m = re.search(r'-\s*(\d+)\s*$', rec.name or '')
            twins = self.with_context(active_test=False).search([('name', '=like', base + '%'), ('id', '!=', rec._origin.id or 0)])
            dup = m and any(self._ts_base_title(t.name) == base for t in twins)
            n = m.group(1) if m else ''
            rec.title = '%s (%s پرسش)' % (base, n.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))) if dup else base
            rec.slug = re.sub(r'\s+', '-', base) + ('-%s' % n if dup else '')

    def _ts_refresh_titles(self):
        insts = self.with_context(active_test=False).search([])
        self.env.add_to_compute(self._fields['title'], insts)
        self.env.add_to_compute(self._fields['slug'], insts)
        insts.flush_recordset(['title', 'slug'])

    @api.depends('current_version_id.active_item_count')
    def _compute_duration(self):
        for rec in self:
            n = rec.current_version_id.active_item_count
            rec.duration_minutes = max(1, math.ceil(n * SECONDS_PER_ITEM / 60)) if n else 0

    def _compute_attempt_count(self):
        groups = self.env['ts.attempt'].sudo()._read_group([('instrument_id', 'in', self.ids)], ['instrument_id'], ['__count'])
        counts = {inst.id: n for inst, n in groups}
        for rec in self:
            rec.attempt_count = counts.get(rec.id, 0)

    def is_publishable(self):
        self.ensure_one()
        v = self.current_version_id
        return bool(v and v.locked and v.validation_ok and self.approved_at and self.intended_use and self.rights_note)

    def action_publish(self):
        for rec in self:
            if not rec.is_publishable():
                raise UserError('«%s» شرایط انتشار را ندارد (نسخهٔ قفل‌شده و معتبر، تأیید، کاربرد مجاز و حق استفاده).' % rec.name)
            rec.state = 'published'
            self.env['ts.audit.event'].log('instrument.publish', rec, version=rec.current_version_id.contract_version)

    def action_retire(self):
        for rec in self:
            rec.state = 'retired'
            self.env['ts.audit.event'].log('instrument.retire', rec)


class TsInstrumentVersion(models.Model):
    """An immutable, locked scoring contract. Attempts point at the version they
    were taken with, so historical results always re-score identically."""
    _name = 'ts.instrument.version'
    _description = 'نسخهٔ سنجه'
    _order = 'instrument_id, id desc'

    instrument_id = fields.Many2one('ts.instrument', required=True, ondelete='restrict', index=True)
    name = fields.Char(compute='_compute_name', store=True)
    contract_version = fields.Char('نسخهٔ قرارداد نمره‌گذاری', required=True)
    engine_version = fields.Char('نسخهٔ موتور نمره‌گذاری', required=True, default='S09-V3.0-multi-inventory')
    content_hash = fields.Char('اثر محتوا', required=True, index=True)
    locked = fields.Boolean('قفل', default=True)
    superseded = fields.Boolean('جایگزین‌شده')
    scale_min = fields.Integer(default=1)
    scale_max = fields.Integer(default=5)
    reverse_rule = fields.Char(default='6 - x')
    aggregation = fields.Char(default='average')
    missing_rule = fields.Char(default='every active item requires exactly one answer; otherwise no score')
    factor_ids = fields.One2many('ts.instrument.factor', 'version_id', 'ابعاد')
    item_ids = fields.One2many('ts.instrument.item', 'version_id', 'پرسش‌ها')
    active_item_count = fields.Integer(compute='_compute_counts', store=True)
    scored_factor_count = fields.Integer(compute='_compute_counts', store=True)
    validation_ok = fields.Boolean('اعتبارسنجی قرارداد', readonly=True)
    validation_report = fields.Text('گزارش اعتبارسنجی', readonly=True)
    source_contract_xmlid = fields.Char(readonly=True)
    source_contract_id = fields.Integer(readonly=True)

    @api.depends('instrument_id.code', 'contract_version')
    def _compute_name(self):
        for v in self:
            v.name = '%s / %s' % (v.instrument_id.code, v.contract_version)

    @api.depends('item_ids.disabled', 'factor_ids.scored')
    def _compute_counts(self):
        for v in self:
            v.active_item_count = len(v.item_ids.filtered(lambda i: not i.disabled))
            v.scored_factor_count = len(v.factor_ids.filtered('scored'))

    def write(self, vals):
        protected = {'contract_version', 'engine_version', 'content_hash', 'scale_min', 'scale_max',
                     'reverse_rule', 'aggregation', 'missing_rule', 'instrument_id'}
        if any(v.locked for v in self) and protected & set(vals) and not self.env.context.get('ts_loader'):
            raise UserError('نسخهٔ قفل‌شده قابل تغییر نیست؛ نسخهٔ جدید بسازید.')
        return super().write(vals)

    def _validate_contract(self):
        """Exhaustive check: for every scored factor, every achievable average
        (k / n for n active items, k in [n, 5n]) falls in exactly one band,
        and every factor with active items has a rule with three bands."""
        for v in self:
            problems = []
            active = v.item_ids.filtered(lambda i: not i.disabled)
            if not active:
                problems.append('no active items')
            for f in v.factor_ids:
                f_items = active.filtered(lambda i: i.factor_id == f)
                if f_items and not f.scored:
                    problems.append('factor %s has %d active items but no scoring rule' % (f.code, len(f_items)))
                if not f.scored:
                    continue
                if not f_items:
                    problems.append('scored factor %s has no active items' % f.code)
                    continue
                if sorted(f.band_ids.mapped('band')) != ['high', 'low', 'medium']:
                    problems.append('factor %s bands %s' % (f.code, f.band_ids.mapped('band')))
                    continue
                n = len(f_items)
                for k in range(n * v.scale_min, n * v.scale_max + 1):
                    avg = k / n
                    hits = f.band_ids.filtered(lambda b: b.min_score <= avg <= b.max_score)
                    if len(hits) != 1:
                        problems.append('factor %s average %.4f matches %d bands' % (f.code, avg, len(hits)))
                        break
            v.sudo().with_context(ts_loader=True).write({
                'validation_ok': not problems,
                'validation_report': '\n'.join(problems) or 'OK: every achievable factor average maps to exactly one band.',
            })


class TsInstrumentFactor(models.Model):
    _name = 'ts.instrument.factor'
    _description = 'بُعد سنجه'
    _order = 'version_id, sequence, id'

    version_id = fields.Many2one('ts.instrument.version', required=True, ondelete='cascade', index=True)
    instrument_id = fields.Many2one(related='version_id.instrument_id', store=True)
    code = fields.Char('کد', required=True)
    name = fields.Char('نام', required=True)
    sequence = fields.Integer(default=10)
    definition = fields.Text('تعریف')
    scored = fields.Boolean('نمره‌گذاری می‌شود')
    band_ids = fields.One2many('ts.instrument.band', 'factor_id', 'بازه‌ها')
    item_ids = fields.One2many('ts.instrument.item', 'factor_id', 'پرسش‌ها')
    source_xmlid = fields.Char(readonly=True)
    source_rule_xmlid = fields.Char(readonly=True)


class TsInstrumentBand(models.Model):
    _name = 'ts.instrument.band'
    _description = 'بازهٔ تفسیر'
    _order = 'factor_id, min_score'

    factor_id = fields.Many2one('ts.instrument.factor', required=True, ondelete='cascade', index=True)
    band = fields.Selection(BANDS, required=True)
    min_score = fields.Float('کمینه', digits=(6, 4), required=True)
    max_score = fields.Float('بیشینه', digits=(6, 4), required=True)
    client_text = fields.Text('تفسیر برای شرکت‌کننده')
    therapist_text = fields.Text('راهنمای متخصص')
    content_version = fields.Char('نسخهٔ محتوای بالینی')
    source_approved_by = fields.Char('تأییدکنندهٔ منبع', readonly=True)
    source_approved_at = fields.Char('زمان تأیید منبع', readonly=True)
    approved_by_id = fields.Many2one('res.users', 'تأییدکنندهٔ تلنت سرچ', readonly=True)
    approved_at = fields.Datetime('زمان تأیید تلنت سرچ', readonly=True)
    source_xmlid = fields.Char(readonly=True)


class TsInstrumentItem(models.Model):
    _name = 'ts.instrument.item'
    _description = 'پرسش سنجه'
    _order = 'version_id, sequence, source_question_id, id'

    version_id = fields.Many2one('ts.instrument.version', required=True, ondelete='cascade', index=True)
    factor_id = fields.Many2one('ts.instrument.factor', ondelete='restrict', index=True)
    sequence = fields.Integer(required=True)
    source_question_id = fields.Integer('شناسهٔ پرسش منبع', required=True)
    text = fields.Char('متن پرسش', required=True)
    reverse = fields.Boolean('نمره‌گذاری معکوس')
    disabled = fields.Boolean('غیرفعال')
    source_xmlid = fields.Char(readonly=True)
    source_question_xmlid = fields.Char(readonly=True)
