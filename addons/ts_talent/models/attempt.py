import json
import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_assessment.models.attempt import fa_digits
from . import engine_matrix as EM
from .text import clean_label, norm_label


class TsAttempt(models.Model):
    _inherit = 'ts.attempt'

    # imported historical participants have no user account (owner decision 2026-09-29)
    user_id = fields.Many2one(required=False)
    person_id = fields.Many2one('res.partner', 'شخص (ورود دادهٔ تاریخی)', index=True, ondelete='restrict')
    mode = fields.Selection(related='version_id.mode')
    source = fields.Selection([('web', 'وب'), ('import', 'ورود دادهٔ تاریخی')], default='web', required=True, index=True)
    source_ref = fields.Char('شناسهٔ منبع', index=True, copy=False)
    import_batch = fields.Char('دستهٔ ورود')
    profile_json = fields.Text('نیمرخ (JSON)', readonly=True)
    field_ids = fields.One2many('ts.attempt.field', 'attempt_id', 'زمینه‌ها')
    cell_ids = fields.One2many('ts.attempt.cell', 'attempt_id', 'پاسخ‌های ماتریسی')

    _source_ref_unique = models.Constraint('unique(source_ref)', 'این ردیف منبع قبلاً وارد شده است.')

    # ------------------------------------------------------------ helpers
    def ts_is_matrix(self):
        self.ensure_one()
        return self.version_id.mode == 'matrix'

    def ts_profile(self):
        self.ensure_one()
        return json.loads(self.profile_json) if self.profile_json else {}

    @api.depends('answer_ids', 'cell_ids', 'field_ids.state', 'version_id')
    def _compute_progress(self):
        matrix = self.filtered(lambda a: a.version_id.mode == 'matrix')
        super(TsAttempt, self - matrix)._compute_progress()
        for a in matrix:
            n = len(a.cell_ids)
            per = a.version_id.active_item_count or EM.ITEM_COUNT
            fields_n = max(len(a.field_ids), a.version_id.field_default or 4)
            a.answered_count = n
            a.progress = 100 if a.state == 'done' else min(99, int(round(100.0 * n / (per * fields_n))))

    def ts_fields_sorted(self):
        return self.field_ids.sorted('sequence')

    def ts_current_field(self):
        self.ensure_one()
        return self.field_ids.filtered(lambda f: f.state == 'draft').sorted('sequence')[:1]

    def ts_done_fields(self):
        return self.field_ids.filtered(lambda f: f.state == 'done').sorted('sequence')

    def _ts_check_open(self):
        self.ensure_one()
        if not self.ts_is_matrix():
            raise UserError('این اجرا از نوع فهرست تعاملی نیست.')
        if self.state != 'in_progress':
            raise UserError('این سنجه دیگر قابل ویرایش نیست.')

    # ------------------------------------------------------------ fields
    def ts_add_field(self, raw_label):
        self._ts_check_open()
        v = self.version_id
        if self.ts_current_field():
            raise UserError('ابتدا زمینهٔ در حال پاسخ را کامل کنید.')
        if len(self.field_ids) >= v.field_max:
            raise UserError('حداکثر %s زمینه می‌توانید بنویسید.' % fa_digits(v.field_max))
        label = clean_label(raw_label)
        if len(label) < 2:
            raise UserError('نام زمینه را بنویسید (دست‌کم دو حرف).')
        if any(f.label_norm == norm_label(label) for f in self.field_ids):
            raise UserError('این زمینه را قبلاً نوشته‌اید؛ زمینهٔ دیگری بنویسید.')
        seq = max(self.field_ids.mapped('sequence') or [0]) + 1
        return self.env['ts.attempt.field'].create({
            'attempt_id': self.id, 'sequence': seq, 'label': label, 'label_norm': norm_label(label),
            'started_at': fields.Datetime.now()})

    def ts_rename_field(self, field, raw_label):
        self._ts_check_open()
        if field.attempt_id != self or field.state != 'draft':
            raise UserError('نام این زمینه دیگر قابل تغییر نیست.')
        label = clean_label(raw_label)
        if len(label) < 2:
            raise UserError('نام زمینه را بنویسید (دست‌کم دو حرف).')
        if any(f.label_norm == norm_label(label) for f in self.field_ids - field):
            raise UserError('این زمینه را قبلاً نوشته‌اید؛ زمینهٔ دیگری بنویسید.')
        field.write({'label': label, 'label_norm': norm_label(label)})

    def ts_drop_empty_draft(self):
        """A draft field the person never answered is removed (going back from the naming step)."""
        self.ensure_one()
        self.field_ids.filtered(lambda f: f.state == 'draft' and not f.cell_ids).unlink()

    def ts_save_cell(self, field, item_id, value):
        self._ts_check_open()
        if field.attempt_id != self or field.state != 'draft':
            raise UserError('این زمینه دیگر قابل ویرایش نیست.')
        item = self.env['ts.instrument.item'].browse(int(item_id))
        if not item.exists() or item.version_id != self.version_id or item.disabled:
            raise UserError('پرسش نامعتبر است.')
        value = int(value)
        if not self.version_id.scale_min <= value <= self.version_id.scale_max:
            raise UserError('پاسخ نامعتبر است.')
        now = fields.Datetime.now()
        cell = self.env['ts.attempt.cell'].search([('field_id', '=', field.id), ('item_id', '=', item.id)], limit=1)
        if cell:
            if cell.value != value:
                cell.write({'value': value, 'answered_at': now})
        else:
            self.env['ts.attempt.cell'].create({'field_id': field.id, 'attempt_id': self.id, 'item_id': item.id,
                                                'value': value, 'answered_at': now})

    def ts_finish_field(self, field, confirm_straight=False):
        """Returns 'ok', or 'straight' when all 15 answers are equal and the person has not confirmed."""
        self._ts_check_open()
        if field.attempt_id != self or field.state != 'draft':
            raise UserError('این زمینه قبلاً کامل شده است.')
        items = self.active_items()
        by_item = {c.item_id.id: c for c in field.cell_ids}
        if any(i.id not in by_item for i in items):
            raise UserError('هنوز به همهٔ جمله‌های این زمینه پاسخ نداده‌اید.')
        values = [by_item[i.id].value for i in items]
        straight = len(set(values)) == 1
        if straight and not confirm_straight:
            return 'straight'
        times = [c.answered_at for c in field.cell_ids if c.answered_at]
        seconds = int((max(times) - min(times)).total_seconds()) if len(times) > 1 else 0
        field.write({'state': 'done', 'finished_at': fields.Datetime.now(), 'seconds': seconds,
                     'flag_straight': straight, 'flag_fast': seconds < EM.FAST_SECONDS})
        return 'ok'

    # ------------------------------------------------------------ scoring
    def ts_engine_input(self):
        self.ensure_one()
        items = self.active_items()
        out = []
        for f in self.ts_done_fields():
            by_item = {c.item_id.id: c.value for c in f.cell_ids}
            out.append({'label': f.label, 'answers': [by_item[i.id] for i in items],
                        'seconds': f.seconds if self.source == 'web' else None})
        return out

    def action_submit(self, submission_key=None):
        if not self.filtered(lambda a: a.version_id.mode == 'matrix'):
            return super().action_submit(submission_key=submission_key)
        self.ensure_one()
        if self.state == 'done':
            return True
        if self.state != 'in_progress':
            raise UserError('این سنجه آمادهٔ ارسال نیست.')
        self.env.cr.execute('SELECT id FROM ts_attempt WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['state'])
        if self.state == 'done':
            return True
        self.ts_drop_empty_draft()
        if self.ts_current_field():
            raise UserError('زمینهٔ در حال پاسخ کامل نشده است.')
        v = self.version_id
        done = self.ts_done_fields()
        if len(done) < v.field_min:
            raise UserError('دست‌کم %s زمینه لازم است.' % fa_digits(v.field_min))
        try:
            result = EM.score_matrix(self.ts_engine_input())
        except EM.ScoringError as e:
            self.write({'state': 'error', 'error_message': str(e)[:250]})
            self.env['ts.audit.event'].log('attempt.score_error', self, error=str(e)[:250])
            return False
        profile = dict(result, interpretation=EM.interpret(result, gap=v.noise_gap))
        now = fields.Datetime.now()
        self.write({'state': 'done', 'submitted_at': now, 'submission_key': submission_key or uuid.uuid4().hex,
                    'engine_version': result['engine'], 'input_hash': result['input_hash'],
                    'output_hash': result['output_hash'], 'profile_json': json.dumps(profile, ensure_ascii=False),
                    'released': True, 'released_at': now})
        self.env['ts.audit.event'].log('attempt.submit', self, instrument=self.instrument_id.code,
                                       version=v.contract_version, output_hash=result['output_hash'],
                                       fields=len(done))
        if hasattr(self, '_ts_notify_result_ready'):
            self._ts_notify_result_ready()
        return True

    def rescore_matches(self):
        self.ensure_one()
        if not self.ts_is_matrix():
            return super().rescore_matches()
        return EM.score_matrix(self.ts_engine_input())['output_hash'] == self.output_hash


class TsAttemptField(models.Model):
    _name = 'ts.attempt.field'
    _description = 'زمینهٔ نام‌گذاری‌شده در فهرست تعاملی'
    _order = 'attempt_id, sequence'

    attempt_id = fields.Many2one('ts.attempt', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True)
    label = fields.Char('نام زمینه', required=True)
    label_norm = fields.Char(index=True)
    state = fields.Selection([('draft', 'در حال پاسخ'), ('done', 'کامل')], default='draft', required=True)
    started_at = fields.Datetime()
    finished_at = fields.Datetime()
    seconds = fields.Integer()
    flag_straight = fields.Boolean('همهٔ پاسخ‌ها یکسان')
    flag_fast = fields.Boolean('بسیار سریع')
    source_ref = fields.Char('شناسهٔ منبع (ورود تاریخی)')
    cell_ids = fields.One2many('ts.attempt.cell', 'field_id')

    _seq_unique = models.Constraint('unique(attempt_id, sequence)', 'شمارهٔ زمینه تکراری است.')
    _label_unique = models.Constraint('unique(attempt_id, label_norm)', 'نام زمینه تکراری است.')


class TsAttemptCell(models.Model):
    _name = 'ts.attempt.cell'
    _description = 'پاسخ به یک جمله در یک زمینه'
    _order = 'field_id, id'

    field_id = fields.Many2one('ts.attempt.field', required=True, ondelete='cascade', index=True)
    attempt_id = fields.Many2one('ts.attempt', required=True, ondelete='cascade', index=True)
    item_id = fields.Many2one('ts.instrument.item', required=True, ondelete='restrict')
    value = fields.Integer(required=True)
    answered_at = fields.Datetime()

    _one_answer = models.Constraint('unique(field_id, item_id)', 'یک پاسخ برای هر جمله در هر زمینه')
