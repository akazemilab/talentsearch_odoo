import logging
import math

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ts_assessment.models.instrument import AUDIENCES, SECONDS_PER_ITEM

_logger = logging.getLogger(__name__)

# workspace purpose -> battery flag (benefits panels have no batteries)
PURPOSE_FLAG = {'clinical': 'for_clinical', 'education': 'for_education', 'employment': 'for_employment'}

_LIMIT = 'این مجموعه برای کمک به گفت‌وگوی مشاوره است، نه تشخیص.'
# Starter batteries (docs/clinic/01_architecture.md 2.1). Instruments are created by the loader, not by xmlids,
# so they are resolved by code in _ts_load_starter. Audiences checked against workbook_meta.json (all match).
# UX audit 2026-10-12 (G6-PT9): descriptions no longer end with _LIMIT; the pages say the limit once.
STARTER = [
    {'code': 'BAT-INTAKE-1', 'name': 'ارزیابی آغاز مشاوره', 'audience': 'adult', 'flags': ('for_clinical',),
     'description': 'برای جلسه‌های نخست با مراجع بزرگسال؛ تصویری کلی از آرامش روانی، بی‌تابی، رضایت از زندگی، '
                    'نیازها و تعهد فردی می‌دهد و کمک می‌کند مسیر گفت‌وگو را انتخاب کنید.',
     'instruments': ['inventory_001', 'inventory_027', 'inventory_020', 'inventory_031', 'inventory_014']},
    {'code': 'BAT-DISTRESS-1', 'name': 'آشفتگی هیجانی و تعادل روانی', 'audience': 'adult', 'flags': ('for_clinical',),
     'description': 'برای مراجع بزرگسالی که از فشار، نگرانی یا بی‌قراری می‌گوید؛ بی‌تابی، پایایی، تعادل و سرزندگی '
                    'را کنار هم نشان می‌دهد.',
     'instruments': ['inventory_027', 'inventory_008', 'inventory_010', 'inventory_023']},
    {'code': 'BAT-LIFE-1', 'name': 'رضایت از زندگی و معنا', 'audience': 'adult', 'flags': ('for_clinical',),
     'description': 'برای مراجع بزرگسالی که از نارضایتی یا کم‌رنگ شدن معنا در زندگی می‌گوید؛ رضایت از زندگی، '
                    'هدفمندی، ارجمندی و حمایت معنوی را می‌سنجد.',
     'instruments': ['inventory_020', 'inventory_033', 'inventory_002', 'inventory_016']},
    {'code': 'BAT-COUPLE-1', 'name': 'زوج و ازدواج', 'audience': 'adult', 'flags': ('for_clinical',),
     'description': 'برای مشاورهٔ پیش از ازدواج یا مشاورهٔ زوج؛ هر یک از دو نفر جداگانه دعوت می‌شود و رضایت زناشویی، '
                    'خردمندی و خودگستری را پاسخ می‌دهد.',
     'instruments': ['inventory_021', 'inventory_017', 'inventory_018']},
    {'code': 'BAT-CHILD-1', 'name': 'کودک: شخصیت و توانایی', 'audience': 'child', 'flags': ('for_clinical',),
     'description': 'برای والدی که دربارهٔ کودک خود مشورت می‌خواهد؛ والد یا مراقب دربارهٔ شخصیت و توانایی‌های کودک '
                    'پاسخ می‌دهد.',
     'instruments': ['inventory_025', 'inventory_003']},
    {'code': 'BAT-WORK-1', 'name': 'کار و مسیر شغلی', 'audience': 'adult', 'flags': ('for_clinical', 'for_employment'),
     'description': 'برای مشاورهٔ شغلی و انتخاب مسیر کاری بزرگسالان؛ رضایت شغلی، هوش موفق، تعهد فردی و وظیفه‌مندی '
                    'را کنار هم می‌گذارد و در پنل استخدامی فقط یکی از ورودی‌های گفت‌وگوی شغلی است.',
     'instruments': ['inventory_022', 'inventory_034', 'inventory_014', 'inventory_032']},
]


def ts_strip_limit(text):
    """A battery description without the trailing «… نه تشخیص» sentence (owner-edited texts may still carry it)."""
    return (text or '').replace(_LIMIT, '').strip()


# Owner decision 2026-10-11 (counseling wording): texts the starter batteries were created with before the rename.
# `_ts_refresh_starter_texts` replaces a stored name/description only while it still equals one of these, so a text the
# owner edited by hand is never overwritten and a second run changes nothing. 2026-10-12 (G6-PT9): every description that
# still ends with _LIMIT is legacy too.
STARTER_LEGACY = {
    'BAT-INTAKE-1': {'name': ['ارزیابی آغاز درمان']},
    'BAT-COUPLE-1': {'description': ['برای مشاورهٔ پیش از ازدواج یا زوج‌درمانی؛ هر یک از دو نفر جداگانه دعوت می‌شود و رضایت زناشویی، '
                                     'خردمندی و خودگستری را پاسخ می‌دهد. ' + _LIMIT]},
}
for _spec in STARTER:
    STARTER_LEGACY.setdefault(_spec['code'], {}).setdefault('description', []).append(_spec['description'] + ' ' + _LIMIT)


def est_minutes(items):
    """8 s per item, rounded up to the next 5 minutes (0 items -> 0). Stored on ts.battery for the back office; pages
    a participant reads use minutes_text() so the total equals the per-instrument list (verify T7)."""
    return int(math.ceil(items * SECONDS_PER_ITEM / 60 / 5) * 5) if items else 0


def _fa(n):
    return str(n).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


def _range_text(lo, hi):
    """(29, 29) -> «۲۹»; (6, 10) -> «۶ تا ۱۰»: used as «حدود … دقیقه»."""
    return _fa(lo) if lo == hi else '%s تا %s' % (_fa(lo), _fa(hi))


def minutes_text(insts):
    """Display only (verify T7, R5): the minutes of a set of instruments as the sum of the numbers each instrument's
    own label shows (ts_minutes_range: questionnaire = duration_minutes, timed task = its minutes, matrix inventory =
    the usual 3 to 5 fields). Every participant page (invite, consent, /my, transition) uses this one sum."""
    lo = hi = 0
    for i in insts:
        a, b = i.ts_minutes_range() if hasattr(i, 'ts_minutes_range') else (i.duration_minutes or 0,) * 2
        lo, hi = lo + a, hi + b
    return _range_text(lo, hi) if hi else ''


def rest_minutes_text(attempts):
    """Minutes left of a battery's unfinished attempts: an attempt in progress counts what is left of it with the
    player's own formula (ceil(unanswered x minutes / items)), so /my and the player say the same number."""
    lo = hi = 0
    for at in attempts:
        inst = at.instrument_id
        a, b = inst.ts_minutes_range() if hasattr(inst, 'ts_minutes_range') else (inst.duration_minutes or 0,) * 2
        mode = at.version_id.mode if 'version_id' in at._fields and at.version_id else 'questionnaire'
        if a == b and at.state == 'in_progress' and mode not in ('matrix', 'task') and at.answered_count:
            total = len(at.active_items())
            a = b = math.ceil((total - at.answered_count) * (inst.duration_minutes or 0) / total) if total else a
        lo, hi = lo + a, hi + b
    return _range_text(lo, hi) if hi else ''


class TsBattery(models.Model):
    """An ordered set of published instruments offered as one invitation (run in Phase 3)."""
    _name = 'ts.battery'
    _description = 'باتری سنجه'
    _inherit = ['mail.thread']
    _order = 'sequence, code'

    name = fields.Char('نام', required=True, tracking=True)
    code = fields.Char('کد', required=True, copy=False, index=True, tracking=True)
    sequence = fields.Integer(default=10)
    description = fields.Text('شرح', help='برای چه کسی و چه زمانی، در یک یا دو جمله. جملهٔ «… نه تشخیص» را ننویسید: صفحه‌ها آن را یک بار نشان می‌دهند.')
    audience = fields.Selection(AUDIENCES, 'مخاطب', required=True, default='adult', tracking=True)
    for_clinical = fields.Boolean('پنل مرکز مشاوره', default=True)
    for_education = fields.Boolean('پنل آموزشی')
    for_employment = fields.Boolean('پنل استخدامی')
    line_ids = fields.One2many('ts.battery.line', 'battery_id', 'سنجه‌ها', copy=True)
    state = fields.Selection([('draft', 'پیش‌نویس'), ('published', 'منتشرشده'), ('retired', 'بازنشسته')],
                             'وضعیت', default='draft', required=True, tracking=True, copy=False)
    item_count = fields.Integer('تعداد پرسش', compute='_compute_counts', store=True)
    est_minutes = fields.Integer('زمان تقریبی (دقیقه)', compute='_compute_counts', store=True)
    has_retired = fields.Boolean('سنجهٔ بازنشسته دارد', compute='_compute_has_retired', store=True,
                                 help='یکی از سنجه‌های این باتری بازنشسته شده است؛ تا آن را برندارید، باتری منتشر نمی‌شود.')
    # Filled in Phase 4 (ts_billing: one product per published battery).
    product_id = fields.Many2one('product.product', 'محصول', copy=False, readonly=True, ondelete='set null')

    _code_unique = models.Constraint('unique(code)', 'کد باتری باید یکتا باشد.')

    @api.depends('line_ids.instrument_id.current_version_id.active_item_count')
    def _compute_counts(self):
        for b in self:
            n = sum(b.line_ids.mapped('instrument_id.current_version_id.active_item_count'))
            b.item_count = n
            b.est_minutes = est_minutes(n)

    @api.depends('line_ids.instrument_id.state')
    def _compute_has_retired(self):
        for b in self:
            b.has_retired = any(s == 'retired' for s in b.line_ids.mapped('instrument_id.state'))

    def ts_minutes_text(self):
        """«۲۹» or «۶ تا ۱۰»: the battery total shown to participants = the sum of its instruments' own labels."""
        self.ensure_one()
        return minutes_text(self.sudo().line_ids.mapped('instrument_id'))

    def ts_title(self):
        """The name people see (same helper as ts.instrument.ts_title()): a battery has no separate title field."""
        self.ensure_one()
        return (self.name or '').strip()

    def ts_display_title(self):
        """Alias of ts_title() kept for older callers."""
        return self.ts_title()

    def unlink(self):
        return super(TsBattery, self.with_context(ts_battery_unlink=True)).unlink()

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for b, vals in zip(self, vals_list):
            vals.setdefault('code', '%s-COPY' % b.code)
            vals.setdefault('name', '%s (رونوشت)' % b.name)
        return vals_list

    # ------------------------------------------------------------ rules
    def _ts_publish_problems(self):
        """Persian reasons why this battery cannot be (or stay) published; empty list = publishable."""
        self.ensure_one()
        problems = []
        lines = self.line_ids
        if len(lines) < 2:
            problems.append('باتری دست‌کم دو سنجه لازم دارد.')
        insts = lines.mapped('instrument_id')
        if len(insts) != len(lines):
            problems.append('هر سنجه فقط یک بار در یک باتری می‌آید.')
        if not (self.for_clinical or self.for_education or self.for_employment):
            problems.append('دست‌کم یکی از کاربردها (مرکز مشاوره، آموزشی یا استخدامی) را انتخاب کنید.')
        for i in insts:
            if i.state == 'retired':
                problems.append('سنجهٔ «%s» بازنشسته شده است؛ پیش از انتشار آن را از باتری بردارید.' % i.name)
            elif i.state != 'published':
                problems.append('سنجهٔ «%s» منتشر نشده است.' % i.name)
            if i.audience != self.audience:
                problems.append('مخاطب سنجهٔ «%s» با مخاطب باتری یکی نیست.' % i.name)
            if self.for_employment and i.purpose != 'employment':
                problems.append('سنجهٔ «%s» برای پنل استخدامی مجاز نیست.' % i.name)
        return problems

    @api.constrains('state', 'line_ids', 'audience', 'for_clinical', 'for_education', 'for_employment')
    def _check_published(self):
        for b in self:
            if b.state == 'published':
                problems = b._ts_publish_problems()
                if problems:
                    raise ValidationError('\n'.join(problems))

    @api.constrains('audience')
    def _check_audience(self):
        for b in self:
            bad = b.line_ids.filtered(lambda l: l.instrument_id.audience != b.audience)
            if bad:
                raise ValidationError('مخاطب سنجهٔ «%s» با مخاطب باتری یکی نیست.' % bad[0].instrument_id.name)

    # ------------------------------------------------------------ lifecycle
    def action_publish(self):
        for b in self:
            problems = b._ts_publish_problems()
            if problems:
                raise UserError('باتری «%s» منتشر نشد:\n%s' % (b.name, '\n'.join(problems)))
            b.state = 'published'
            self.env['ts.audit.event'].log('battery.publish', b, lines=len(b.line_ids))

    def action_retire(self):
        for b in self.filtered(lambda r: r.state != 'retired'):
            b.state = 'retired'
            self.env['ts.audit.event'].log('battery.retire', b)

    def action_draft(self):
        for b in self.filtered(lambda r: r.state != 'draft'):
            b.state = 'draft'
            self.env['ts.audit.event'].log('battery.draft', b)

    # ------------------------------------------------------------ starter data
    @api.model
    def _ts_load_starter(self):
        """Create the six starter batteries once (by code). A battery whose instruments are missing or not
        published is skipped; one that fails a publish rule stays draft. An existing starter that still carries a
        legacy text (STARTER_LEGACY) gets the current name/description. Running it again changes nothing."""
        Inst = self.env['ts.instrument'].sudo().with_context(active_test=False)
        B = self.sudo()
        stats = {'created': 0, 'published': 0, 'existing': 0, 'skipped': 0}
        stats['renamed'] = self._ts_refresh_starter_texts()
        for spec in STARTER:
            if B.search_count([('code', '=', spec['code'])]):
                stats['existing'] += 1
                continue
            insts = [Inst.search([('code', '=', c)], limit=1) for c in spec['instruments']]
            missing = [c for c, i in zip(spec['instruments'], insts) if not i or i.state != 'published']
            if missing:
                _logger.warning('ts_battery: starter %s skipped, instruments missing or not published: %s',
                                spec['code'], missing)
                stats['skipped'] += 1
                continue
            vals = {'code': spec['code'], 'name': spec['name'], 'description': spec['description'],
                    'audience': spec['audience'], 'sequence': 10 * (STARTER.index(spec) + 1),
                    'for_clinical': 'for_clinical' in spec['flags'], 'for_education': 'for_education' in spec['flags'],
                    'for_employment': 'for_employment' in spec['flags'],
                    'line_ids': [fields.Command.create({'sequence': 10 * (n + 1), 'instrument_id': i.id})
                                 for n, i in enumerate(insts)]}
            try:
                with self.env.cr.savepoint():
                    bat = B.create(vals)
            except (UserError, ValidationError) as e:
                _logger.warning('ts_battery: starter %s not created: %s', spec['code'], e)
                stats['skipped'] += 1
                continue
            stats['created'] += 1
            try:
                with self.env.cr.savepoint():
                    bat.action_publish()
                stats['published'] += 1
            except (UserError, ValidationError) as e:
                _logger.warning('ts_battery: starter %s left as draft: %s', spec['code'], e)
        _logger.info('ts_battery starter batteries: %s', stats)
        return stats

    @api.model
    def _ts_refresh_starter_texts(self):
        """Bring existing starter batteries (matched by code) to the current STARTER name/description when the stored
        value is still a legacy one. Runs from the loader (install) and from data/batteries_texts.xml (every upgrade,
        because batteries.xml is noupdate). Returns the number of batteries written; 0 on a second run."""
        B = self.sudo().with_context(active_test=False)
        spec_by_code = {s['code']: s for s in STARTER}
        n = 0
        for code, legacy in STARTER_LEGACY.items():
            bat = B.search([('code', '=', code)], limit=1)
            if not bat:
                continue
            vals = {f: spec_by_code[code][f] for f, olds in legacy.items() if bat[f] in olds}
            if vals:
                bat.write(vals)
                n += 1
        if n:
            _logger.info('ts_battery: %d starter battery text(s) updated to the counseling wording', n)
        return n


class TsBatteryLine(models.Model):
    _name = 'ts.battery.line'
    _description = 'سنجهٔ باتری'
    _order = 'battery_id, sequence, id'

    battery_id = fields.Many2one('ts.battery', 'باتری', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer('ترتیب', default=10)
    instrument_id = fields.Many2one('ts.instrument', 'سنجه', required=True, ondelete='restrict', index=True,
                                    domain=[('state', '=', 'published')])
    required = fields.Boolean('الزامی', default=True)
    instrument_audience = fields.Selection(related='instrument_id.audience', string='مخاطب سنجه')
    instrument_state = fields.Selection(related='instrument_id.state', string='وضعیت سنجه')
    item_count = fields.Integer(related='instrument_id.active_item_count', string='تعداد پرسش')

    _battery_instrument_unique = models.Constraint('unique(battery_id, instrument_id)',
                                                   'هر سنجه فقط یک بار در یک باتری می‌آید.')

    @api.constrains('instrument_id', 'battery_id')
    def _check_instrument(self):
        for l in self:
            b = l.battery_id
            if len(b.line_ids.filtered(lambda x: x.instrument_id == l.instrument_id)) > 1:
                raise ValidationError('سنجهٔ «%s» دو بار در این باتری آمده است.' % l.instrument_id.name)
            if l.instrument_id.state != 'published':
                raise ValidationError('فقط سنجهٔ منتشرشده به باتری اضافه می‌شود («%s»).' % l.instrument_id.name)
            if l.instrument_id.audience != b.audience:
                raise ValidationError('مخاطب سنجهٔ «%s» با مخاطب باتری یکی نیست.' % l.instrument_id.name)
            if b.state == 'published':
                problems = b._ts_publish_problems()
                if problems:
                    raise ValidationError('\n'.join(problems))

    def unlink(self):
        published = self.mapped('battery_id').filtered(lambda b: b.state == 'published')
        if self.env.context.get('ts_battery_unlink'):     # the whole battery goes
            published = published.browse()
        res = super().unlink()
        for b in published.exists():
            if len(b.line_ids) < 2:
                raise ValidationError('باتری منتشرشده دست‌کم دو سنجه لازم دارد؛ ابتدا آن را به پیش‌نویس برگردانید.')
        return res
