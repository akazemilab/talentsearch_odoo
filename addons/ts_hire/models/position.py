"""HR positions and candidate job fit (docs/hr/01_architecture.md sections 3, 5).

A position = one job an employment panel is hiring for, tied to the closest O*NET occupation and one of the two HR
batteries. Candidates are ordinary battery invitations (ts.assignment) carrying position_id; every access rule stays
the existing one (`result_level()`): HR sees the job-fit summary only when the candidate shared the result."""
import json
import logging
import statistics

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ts_onet.models import jobfit as J
from .hexaco import ATTN, HEXACO_CODE

_logger = logging.getLogger(__name__)

BATTERIES = {
    'short': {'code': 'BAT-HR-SHORT', 'name': 'غربالگری استخدامی (کوتاه)',
              'instruments': [HEXACO_CODE, 'TASK-REASON'],
              'description': 'پرسش‌نامهٔ سبک‌های کاری و آزمون استدلال؛ حدود ۳۰ دقیقه. برای غربالگری اولیهٔ داوطلبان؛ '
                             'نتیجه فقط یکی از ورودی‌های تصمیم استخدامی است و هرگز به‌تنهایی مبنای رد یا پذیرش نیست.'},
    'full': {'code': 'BAT-HR-FULL', 'name': 'ارزیابی استخدامی (کامل)',
             'instruments': [HEXACO_CODE, 'TASK-REASON', 'TASK-NUMERIC', 'TASK-SPATIAL', 'TASK-SPEED'],
             'description': 'پرسش‌نامهٔ سبک‌های کاری و چهار آزمون زمان‌دار (استدلال، عددی، تجسم فضایی، سرعت و توجه)؛ '
                            'حدود ۵۵ دقیقه، بخش سرعت با رایانه. نتیجه فقط یکی از ورودی‌های تصمیم استخدامی است.'},
}
DECISIONS = [('none', 'بدون تصمیم'), ('shortlist', 'فهرست کوتاه'), ('interview', 'دعوت به مصاحبه'),
             ('hold', 'در انتظار'), ('reject', 'رد'), ('hire', 'استخدام')]
POSITIVE = ('shortlist', 'interview', 'hire')
GENDERS = [('female', 'زن'), ('male', 'مرد'), ('undisclosed', 'ترجیح می‌دهم نگویم')]
AGE_BANDS = [('18-24', '۱۸ تا ۲۴'), ('25-34', '۲۵ تا ۳۴'), ('35-44', '۳۵ تا ۴۴'), ('45-54', '۴۵ تا ۵۴'),
             ('55+', '۵۵ و بیشتر'), ('undisclosed', 'ترجیح می‌دهم نگویم')]
FAIR_MIN_GROUP = 5
MAX_CRITICAL = 3
VALIDITY_FA = {
    'attention': 'به جمله‌های کنترلی دقت کافی نشد',
    'straight': 'بیشتر جمله‌ها با یک گزینهٔ یکسان پاسخ داده شد',
    'inconsistent': 'پاسخ به جمله‌های هم‌معنا و وارونه ناهمخوان بود',
    'fast': 'پاسخ‌ها بسیار سریع داده شد',
}


class TsBatteryHire(models.Model):
    _inherit = 'ts.battery'

    @api.model
    def _ts_load_hr(self):
        """Create and publish the two HR batteries once (by code)."""
        Inst = self.env['ts.instrument'].sudo().with_context(active_test=False)
        out = {}
        for key, spec in BATTERIES.items():
            if self.sudo().search_count([('code', '=', spec['code'])]):
                out[key] = 'existing'
                continue
            insts = [Inst.search([('code', '=', c)], limit=1) for c in spec['instruments']]
            if not all(i and i.state == 'published' for i in insts):
                _logger.warning('ts_hire: battery %s skipped, instruments missing', spec['code'])
                out[key] = 'skipped'
                continue
            b = self.sudo().create({
                'code': spec['code'], 'name': spec['name'], 'description': spec['description'], 'audience': 'adult',
                'sequence': 200 if key == 'short' else 210, 'for_clinical': False, 'for_education': False,
                'for_employment': True,
                'line_ids': [fields.Command.create({'sequence': 10 * (n + 1), 'instrument_id': i.id})
                             for n, i in enumerate(insts)]})
            try:
                with self.env.cr.savepoint():
                    b.action_publish()
                out[key] = 'published'
            except (UserError, ValidationError) as e:
                _logger.warning('ts_hire: battery %s left draft: %s', spec['code'], e)
                out[key] = 'draft'
        return out


class TsHirePosition(models.Model):
    _name = 'ts.hire.position'
    _description = 'موقعیت شغلی'
    _inherit = ['mail.thread']
    _order = 'state, create_date desc, id desc'

    name = fields.Char('عنوان موقعیت', required=True, tracking=True)
    workspace_id = fields.Many2one('ts.workspace', 'پنل', required=True, index=True, ondelete='restrict')
    occupation_id = fields.Many2one('ts.onet.occupation', 'شغل مرجع (O*NET)', required=True, ondelete='restrict',
                                    tracking=True)
    battery_choice = fields.Selection([('short', 'غربالگری کوتاه (حدود ۳۰ دقیقه)'),
                                       ('full', 'ارزیابی کامل (حدود ۵۵ دقیقه)')],
                                      'نوع ارزیابی', required=True, default='short', tracking=True)
    battery_id = fields.Many2one('ts.battery', 'مجموعه', compute='_compute_battery', store=True)
    critical_json = fields.Char('نیازهای کلیدی', default='[]')
    dropped_json = fields.Char('نیازهای کنارگذاشته', default='[]')
    profile_reviewed = fields.Boolean('نیمرخ بررسی شد')
    state = fields.Selection([('draft', 'پیش‌نویس'), ('open', 'باز'), ('closed', 'بسته')], 'وضعیت',
                             default='draft', required=True, tracking=True)
    deadline = fields.Date('مهلت پاسخ داوطلبان')
    note = fields.Char('یادداشت داخلی')
    created_by_id = fields.Many2one('res.users', 'سازنده', default=lambda s: s.env.user, readonly=True)
    assignment_ids = fields.One2many('ts.assignment', 'position_id', 'داوطلبان')
    company_id = fields.Many2one(related='workspace_id.company_id', store=True)

    @api.depends('battery_choice')
    def _compute_battery(self):
        B = self.env['ts.battery'].sudo()
        for p in self:
            code = BATTERIES[p.battery_choice or 'short']['code']
            p.battery_id = B.search([('code', '=', code)], limit=1)

    @api.constrains('workspace_id')
    def _check_purpose(self):
        for p in self:
            if p.workspace_id.purpose != 'employment':
                raise ValidationError('موقعیت شغلی فقط در پنل استخدامی ساخته می‌شود.')

    def ts_overrides(self):
        self.ensure_one()
        return {'critical': json.loads(self.critical_json or '[]'), 'dropped': json.loads(self.dropped_json or '[]')}

    def ts_requirements(self):
        self.ensure_one()
        return self.occupation_id.ts_requirements(self.ts_overrides())

    def ts_set_profile(self, critical, dropped, member):
        """HR marks up to three requirements as critical and drops clearly irrelevant ones; logged, then results of
        existing candidates are recomputed (the data never changes, only the weights)."""
        self.ensure_one()
        names = {r['name'] for r in self.occupation_id.ts_requirements()}
        critical = sorted(set(critical) & names)
        dropped = sorted((set(dropped) & names) - set(critical))
        if len(critical) > MAX_CRITICAL:
            raise UserError('حداکثر سه نیاز را می‌توان کلیدی کرد.')
        old = self.ts_overrides()
        self.write({'critical_json': json.dumps(critical), 'dropped_json': json.dumps(dropped),
                    'profile_reviewed': True, 'state': 'open' if self.state == 'draft' else self.state})
        self.env['ts.audit.event'].sudo().log('position.profile', self, workspace=self.workspace_id,
                                              critical=critical, dropped=dropped, old=old, member=member.id)
        self.assignment_ids.sudo()._ts_hire_refresh()

    def ts_counts(self):
        self.ensure_one()
        a = self.assignment_ids.sudo().filtered(lambda x: x.state not in ('withdrawn',))
        return {'invited': len(a), 'done': len(a.filtered(lambda x: x.ts_hire_complete)),
                'going': len(a.filtered(lambda x: x.state in ('accepted', 'in_progress') and not x.ts_hire_complete)),
                'strong': len(a.filtered(lambda x: x.jobfit_band == 'strong'))}

    def ts_sorted_candidates(self):
        self.ensure_one()
        rows = self.assignment_ids.sudo().filtered(lambda x: x.state != 'withdrawn')
        return rows.sorted(lambda x: (0 if x.ts_hire_complete else 1, x.jobfit_order or 99, -(x.id)))

    # ------------------------------------------------------------ fairness (four-fifths, decisions only)
    def ts_fairness(self):
        """Selection rate (shortlist/interview/hire) by voluntary gender and age band. Groups below FAIR_MIN_GROUP are
        not shown (privacy and noise); the rule flags a group whose rate is below 4/5 of the highest group."""
        self.ensure_one()
        decided = self.assignment_ids.sudo().filtered(lambda x: x.hire_decision and x.hire_decision != 'none')
        out = {}
        for field, labels in (('ts_gender', dict(GENDERS)), ('ts_age_band', dict(AGE_BANDS))):
            groups = {}
            for a in decided:
                g = a[field]
                if not g or g == 'undisclosed':
                    continue
                n, pos = groups.get(g, (0, 0))
                groups[g] = (n + 1, pos + (1 if a.hire_decision in POSITIVE else 0))
            shown = {g: v for g, v in groups.items() if v[0] >= FAIR_MIN_GROUP}
            rows = []
            if len(shown) >= 2:
                top = max(p / n for n, p in shown.values()) or 0
                for g, (n, p) in sorted(shown.items()):
                    rate = p / n
                    rows.append({'label': labels.get(g, g), 'n': n, 'rate': rate,
                                 'ratio': (rate / top) if top else None, 'flag': bool(top and rate / top < 0.8)})
            out[field] = {'rows': rows, 'hidden': len(groups) - len(shown), 'decided': len(decided)}
        return out


class TsAssignmentHire(models.Model):
    _inherit = 'ts.assignment'

    position_id = fields.Many2one('ts.hire.position', 'موقعیت شغلی', index=True, ondelete='set null', readonly=True)
    ts_extra_time = fields.Selection([('1.0', 'عادی'), ('1.25', '۲۵٪ بیشتر'), ('1.5', '۵۰٪ بیشتر')],
                                     'زمان آزمون‌ها', default='1.0',
                                     help='برای داوطلبی که نیاز ویژه دارد (مثلاً کم‌بینایی یا ناتوانی حرکتی)؛ ثبت می‌شود.')
    hire_decision = fields.Selection(DECISIONS, 'تصمیم', default='none', tracking=True)
    decision_note = fields.Char('یادداشت تصمیم')
    decision_by_id = fields.Many2one('res.users', 'تصمیم‌گیرنده', readonly=True)
    decision_at = fields.Datetime('زمان تصمیم', readonly=True)
    ts_gender = fields.Selection(GENDERS, 'جنسیت (اختیاری)', readonly=True, groups='ts_core.group_ts_manager')
    ts_age_band = fields.Selection(AGE_BANDS, 'گروه سنی (اختیاری)', readonly=True, groups='ts_core.group_ts_manager')
    jobfit_json = fields.Text(readonly=True, copy=False)
    jobfit_band = fields.Selection([('strong', 'تناسب زیاد'), ('moderate', 'تناسب متوسط'), ('limited', 'تناسب کم')],
                                   'تناسب شغلی', readonly=True, copy=False, index=True)
    jobfit_order = fields.Float(readonly=True, copy=False)
    ts_hire_complete = fields.Boolean('همهٔ بخش‌ها تکمیل شد', readonly=True, copy=False)
    validity_flags = fields.Char('نشانه‌های دقت پاسخ‌دهی', readonly=True, copy=False)
    verify_of_id = fields.Many2one('ts.assignment', 'آزمون تأیید برای', readonly=True, index=True, ondelete='set null')
    email_sent_at = fields.Datetime('ارسال ایمیل دعوت', readonly=True, copy=False)
    email_error = fields.Char('خطای ایمیل دعوت', readonly=True, copy=False)

    # ------------------------------------------------------------ job fit
    def _ts_hire_attempts(self):
        self.ensure_one()
        return self.attempt_ids if 'attempt_ids' in self._fields and self.attempt_ids else self.attempt_id

    def _ts_hire_refresh(self):
        """Recompute the job fit and response-validity signals from the finished attempts of this candidate."""
        for a in self.sudo():
            if not a.position_id:
                continue
            ats = a._ts_hire_attempts()
            facets, abilities, flags = {}, {}, []
            for t in ats.filtered(lambda x: x.state == 'done'):
                if t.instrument_id.code == HEXACO_CODE:
                    facets = t.ts_facets()
                    flags += a._ts_validity(t)
                elif t.version_id.mode == 'task':
                    for k, v in t.ts_abilities().items():
                        abilities[k] = v
                    flags += ['task:%s' % f for f in (t.task_flags or '').split(',') if f]
            ver = a.env['ts.assignment'].sudo().search([('verify_of_id', '=', a.id), ('state', '=', 'done')], limit=1)
            if ver and abilities.get('Inductive Reasoning') is not None:
                vt = ver.attempt_id.ts_abilities().get('Inductive Reasoning')
                if vt is not None and abilities['Inductive Reasoning'] - vt > 30:
                    flags.append('task:verify_drop')
            res = a.position_id.occupation_id.ts_jobfit(facets=facets or None, abilities=abilities or None,
                                                         overrides=a.position_id.ts_overrides()) if facets or abilities else None
            complete = bool(ats) and all(t.state == 'done' for t in ats)
            newly = complete and not a.ts_hire_complete
            vals = {'ts_hire_complete': complete, 'validity_flags': ','.join(sorted(set(flags)))}
            if res:
                rank, neg = J.order_key(res)
                vals.update({'jobfit_json': json.dumps(res, ensure_ascii=False), 'jobfit_band': res['band'] or False,
                             'jobfit_order': rank + (1 + neg) / 10.0})
            a.write(vals)
            if newly and hasattr(a, '_ts_mail_candidate_done'):
                a._ts_mail_candidate_done()

    def _ts_validity(self, attempt):
        """Response-validity signals of the personality questionnaire (never a decision on their own)."""
        flags = []
        answers = attempt.answer_ids
        if not answers:
            return flags
        by_item = {x.item_id.id: x for x in answers}
        items = attempt.version_id.item_ids.filtered(lambda i: not i.disabled)
        attn = items.filtered(lambda i: i.factor_id.code == ATTN).sorted('sequence')
        expect = [1, 4, 3]
        wrong = sum(1 for it, e in zip(attn, expect) if it.id in by_item and by_item[it.id].value != e)
        if wrong >= 2:
            flags.append('attention')
        vals = [x.value for x in answers]
        top = max(vals.count(v) for v in set(vals))
        if top / len(vals) >= 0.8:
            flags.append('straight')
        incons = 0
        for f in attempt.version_id.factor_ids.filtered(lambda f: f.code != ATTN):
            fi = items.filtered(lambda i: i.factor_id == f)
            pos = [by_item[i.id].value for i in fi if not i.reverse and i.id in by_item]
            neg = [6 - by_item[i.id].value for i in fi if i.reverse and i.id in by_item]
            if pos and neg and abs(statistics.mean(pos) - statistics.mean(neg)) >= 2.0:
                incons += 1
        if incons >= 6:
            flags.append('inconsistent')
        stamps = sorted(x.answered_at for x in answers if x.answered_at)
        if len(stamps) > 20:
            span = (stamps[-1] - stamps[0]).total_seconds()
            if span / len(stamps) < 1.5:
                flags.append('fast')
        return flags

    def ts_jobfit(self):
        self.ensure_one()
        return json.loads(self.jobfit_json) if self.jobfit_json else None

    def ts_validity_labels(self):
        """Persian labels of the integrity signals for HR."""
        from odoo.addons.ts_tasks.models.scoring import FLAG_FA
        out = []
        for f in (self.validity_flags or '').split(','):
            if not f:
                continue
            if f.startswith('task:'):
                out.append(FLAG_FA.get(f[5:], f[5:]))
            else:
                out.append(VALIDITY_FA.get(f, f))
        return sorted(set(out))

    def ts_set_decision(self, decision, note, user):
        self.ensure_one()
        if decision not in dict(DECISIONS):
            raise UserError('تصمیم نامعتبر است.')
        self.sudo().write({'hire_decision': decision, 'decision_note': (note or '')[:200], 'decision_by_id': user.id,
                           'decision_at': fields.Datetime.now()})
        self.env['ts.audit.event'].sudo().log('hire.decision', self, workspace=self.workspace_id, decision=decision)

    # ------------------------------------------------------------ verification test (ITC 45.3)
    def ts_invite_verification(self, member):
        """A short supervised reasoning test with fresh items for a shortlisted candidate; a large drop is a signal."""
        self.ensure_one()
        inst = self.env['ts.instrument'].sudo().search([('code', '=', 'TASK-VERIFY'), ('state', '=', 'published')], limit=1)
        if not inst:
            raise UserError('آزمون تأیید هنوز در دسترس نیست.')
        if not self.user_id:
            raise UserError('داوطلب هنوز دعوت را نپذیرفته است.')
        old = self.sudo().search([('verify_of_id', '=', self.id), ('state', 'not in', ('withdrawn', 'declined'))], limit=1)
        if old:
            return old
        v = self.sudo().with_user(member.user_id).create({
            'workspace_id': self.workspace_id.id, 'instrument_id': inst.id, 'invitee_name': self.invitee_name,
            'invitee_email': self.invitee_email, 'verify_of_id': self.id, 'note': 'آزمون تأیید حضوری',
            'responsible_id': self.responsible_id.id, 'ts_extra_time': self.ts_extra_time})
        self.env['ts.audit.event'].sudo().log('hire.verify_invite', self, workspace=self.workspace_id)
        return v


class TsAttemptHire(models.Model):
    _inherit = 'ts.attempt'

    def action_submit(self, submission_key=None):
        was = {a.id: a.state for a in self}
        res = super().action_submit(submission_key=submission_key)
        for at in self.sudo():
            if res and was.get(at.id) != 'done' and at.state == 'done':
                a = at.assignment_id if 'assignment_id' in at._fields else False
                a = a or self.env['ts.assignment'].sudo().search([('attempt_id', '=', at.id)], limit=1)
                if a and a.position_id:
                    a._ts_hire_refresh()
                if a and a.verify_of_id:
                    a.verify_of_id._ts_hire_refresh()
        return res
