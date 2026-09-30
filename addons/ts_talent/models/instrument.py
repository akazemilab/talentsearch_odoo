import math

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_assessment.models.instrument import SECONDS_PER_ITEM
from .engine_matrix import ITEM_COUNT, SCALES


class TsInstrument(models.Model):
    _inherit = 'ts.instrument'

    @api.depends('current_version_id.active_item_count', 'current_version_id.mode', 'current_version_id.field_default')
    def _compute_duration(self):
        for rec in self:
            v = rec.current_version_id
            n = v.active_item_count
            if n and v.mode == 'matrix':
                n *= v.field_default or 1
            rec.duration_minutes = max(1, math.ceil(n * SECONDS_PER_ITEM / 60)) if n else 0


class TsInstrumentVersion(models.Model):
    _inherit = 'ts.instrument.version'

    mode = fields.Selection([('single', 'یک‌بار پاسخ'), ('matrix', 'تکرار به ازای هر زمینه')],
                            'شیوهٔ پاسخ‌دهی', default='single', required=True)
    field_min = fields.Integer('کمترین تعداد زمینه', default=2)
    field_default = fields.Integer('تعداد پیش‌فرض زمینه', default=4)
    field_max = fields.Integer('بیشترین تعداد زمینه', default=8)
    field_guidance = fields.Text('راهنمای نوشتن زمینه')
    noise_gap = fields.Float('فاصلهٔ «تقریباً برابر» (نمره)', default=10.0)

    def write(self, vals):
        protected = {'mode', 'field_min', 'field_max', 'noise_gap'}
        if any(v.locked for v in self) and protected & set(vals) and not self.env.context.get('ts_loader'):
            raise UserError('نسخهٔ قفل‌شده قابل تغییر نیست؛ نسخهٔ جدید بسازید.')
        return super().write(vals)

    def _validate_contract(self):
        matrix = self.filtered(lambda v: v.mode == 'matrix')
        super(TsInstrumentVersion, self - matrix)._validate_contract()
        for v in matrix:
            problems = []
            active = v.item_ids.filtered(lambda i: not i.disabled).sorted('sequence')
            if len(active) != ITEM_COUNT:
                problems.append('matrix version needs %d active items, has %d' % (ITEM_COUNT, len(active)))
            scale_f = {f.code: f for f in v.factor_ids if f.kind == 'scale'}
            if set(scale_f) != set(SCALES):
                problems.append('scale factors %s' % sorted(scale_f))
            for pos, item in enumerate(active):
                if item.factor_id.code != SCALES[pos % 5]:
                    problems.append('item %d belongs to %s, expected %s' % (pos + 1, item.factor_id.code, SCALES[pos % 5]))
                    break
            for f in v.factor_ids.filtered(lambda f: f.kind == 'composite'):
                members = (f.composite_of or '').split(',')
                if not members or any(m not in scale_f for m in members):
                    problems.append('composite %s members %s' % (f.code, members))
            if not (1 <= v.field_min <= v.field_default <= v.field_max <= 8):
                problems.append('field limits %s/%s/%s' % (v.field_min, v.field_default, v.field_max))
            v.sudo().with_context(ts_loader=True).write({
                'validation_ok': not problems,
                'validation_report': '\n'.join(problems) or 'OK: 15 items, 5 scales x 3 items, composites reference known scales.',
            })


class TsInstrumentFactor(models.Model):
    _inherit = 'ts.instrument.factor'

    kind = fields.Selection([('scale', 'مقیاس'), ('composite', 'ترکیب')], 'نوع', default='scale', required=True)
    group = fields.Selection([('intelligence', 'هوش'), ('action', 'کنش'), ('none', 'ـ')], 'گروه', default='none')
    composite_of = fields.Char('اجزای ترکیب (کدها با کاما)')
    program_text = fields.Text('برنامهٔ پیشنهادی (عیناً از کتاب)')
