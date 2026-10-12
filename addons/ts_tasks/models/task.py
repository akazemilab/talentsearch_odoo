"""Timed task instruments inside the normal attempt (docs/hr/01_architecture.md section 4).

* A task instrument is a ts.instrument whose current version has mode 'task'; its blocks come from scoring.INSTRUMENTS.
* Items are generated per attempt from a server-side seed; answer keys never leave the server. Each block's deadline is
  kept on the server (a reload continues the same block with the remaining time and is recorded as a signal).
* Results are ts.attempt.result rows (one per O*NET ability, score = percentile 0-100, band low/medium/high), so the
  battery, report, billing and SMS machinery work unchanged. Integrity signals are stored for HR, never decide anything.
"""
import hashlib
import json
import logging
import time
import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import generators as G
from . import scoring as S

_logger = logging.getLogger(__name__)
GRACE_S = 5
AB_DEF = {
    'Inductive Reasoning': 'یافتن قاعده و الگو در اطلاعات تازه.',
    'Information Ordering': 'چیدن اطلاعات به ترتیبی که قاعده‌ای مشخص می‌خواهد.',
    'Deductive Reasoning': 'رسیدن به نتیجهٔ درست از قاعده‌ها و جمله‌های داده‌شده.',
    'Visualization': 'تصور شکل اشیا پس از چرخاندن یا جابه‌جا کردن آن‌ها.',
    'Spatial Orientation': 'تشخیص جهت و موقعیت شکل‌ها نسبت به یکدیگر.',
    'Mathematical Reasoning': 'انتخاب روش درست برای حل مسئله‌های عددی.',
    'Number Facility': 'انجام محاسبه‌های ساده با سرعت و دقت.',
    'Perceptual Speed': 'مقایسهٔ سریع و دقیق نشانه‌ها و جزئیات.',
    'Memorization': 'به خاطر سپردن کوتاه‌مدت اطلاعات، مانند رشته‌ای از عددها.',
    'Selective Attention': 'تمرکز بر آنچه مهم است و نادیده گرفتن عوامل حواس‌پرتی.',
    'Reaction Time': 'سرعت واکنش به یک نشانه.',
    'Response Orientation': 'انتخاب سریع پاسخ درست میان چند پاسخ ممکن.',
}
BAND_TEXT = {
    'high': 'در این بخش از بیشتر شرکت‌کنندگان دقیق‌تر یا سریع‌تر بودید.',
    'medium': 'در این بخش در محدودهٔ میانهٔ شرکت‌کنندگان بودید.',
    'low': 'در این بخش کمتر از بیشتر شرکت‌کنندگان امتیاز گرفتید. یک آزمون کوتاه همهٔ توانایی شما را نشان نمی‌دهد.',
}


def _now():
    return time.time()


class TsInstrumentVersionTask(models.Model):
    _inherit = 'ts.instrument.version'

    mode = fields.Selection(selection_add=[('task', 'آزمون زمان‌دار')], ondelete={'task': 'set default'})
    task_code = fields.Char('کد آزمون زمان‌دار', readonly=True)

    def _validate_contract(self):
        task = self.filtered(lambda v: v.mode == 'task')
        super(TsInstrumentVersionTask, self - task)._validate_contract()
        for v in task:
            problems = []
            spec = S.INSTRUMENTS.get(v.task_code or '')
            if not spec:
                problems.append('unknown task code %s' % v.task_code)
            else:
                codes = set(v.factor_ids.filtered('scored').mapped('code'))
                if codes != set(spec['factors']):
                    problems.append('task factors %s != spec %s' % (sorted(codes), sorted(spec['factors'])))
                for f in v.factor_ids.filtered('scored'):
                    b = sorted(f.band_ids, key=lambda x: x.min_score)
                    if [x.band for x in b] != ['low', 'medium', 'high'] or b[0].min_score > 0 or b[-1].max_score < 100:
                        problems.append('factor %s bands do not cover 0-100' % f.code)
            v.sudo().with_context(ts_loader=True).write({
                'validation_ok': not problems,
                'validation_report': '\n'.join(problems) or 'OK: task version, percentile bands cover 0-100.'})


class TsInstrumentTask(models.Model):
    _inherit = 'ts.instrument'

    invite_only = fields.Boolean('فقط با دعوت', help='در فهرست عمومی سنجه‌ها نمایش داده نمی‌شود و فقط از راه دعوت '
                                                     'پنل (معمولاً در یک مجموعهٔ استخدامی) اجرا می‌شود.')

    def ts_is_task_inst(self):
        self.ensure_one()
        return self.current_version_id.mode == 'task'

    def ts_task_spec(self):
        self.ensure_one()
        return S.INSTRUMENTS.get(self.current_version_id.task_code or '')

    @api.depends('current_version_id.active_item_count', 'current_version_id.mode', 'current_version_id.task_code')
    def _compute_duration(self):
        super()._compute_duration()
        for rec in self:
            spec = S.INSTRUMENTS.get(rec.current_version_id.task_code or '') if rec.current_version_id.mode == 'task' else None
            if spec:
                rec.duration_minutes = spec['minutes']

    def ts_effort_label(self):
        self.ensure_one()
        spec = self.ts_task_spec() if self.current_version_id.mode == 'task' else None
        if spec:
            return '%s بخش زمان‌دار' % G.fa(len(spec['blocks']))
        return super().ts_effort_label()

    def ts_duration_label(self):
        self.ensure_one()
        if self.current_version_id.mode == 'task':
            return 'حدود %s دقیقه' % G.fa(self.duration_minutes)
        return super().ts_duration_label()

    # ------------------------------------------------------------ loader (idempotent, by code)
    @api.model
    def _ts_load_tasks(self):
        Inst = self.sudo().with_context(active_test=False, ts_loader=True)
        stats = {'created': 0, 'existing': 0}
        for n, (code, spec) in enumerate(sorted(S.INSTRUMENTS.items())):
            if Inst.search_count([('code', '=', code)]):
                stats['existing'] += 1
                continue
            inst = Inst.create({
                'name': spec['name'], 'code': code, 'sequence': 900 + n, 'category': 'آزمون‌های زمان‌دار استخدامی',
                'audience': 'adult', 'purpose': 'employment', 'invite_only': True,
                'intended_use': 'سنجش توانایی‌های شناختی بزرگسالان برای کمک به تصمیم استخدامی، همراه با مصاحبه و سوابق؛ '
                                'هرگز تنها مبنای تصمیم و بدون نمرهٔ برش.',
                'limitations': 'هنجار ایرانی هنوز ساخته نشده است: تا رسیدن به ۱۰۰ شرکت‌کننده برای هر بخش، صدک‌ها برآورد '
                               'موقت‌اند. آزمون بدون ناظر است؛ برای نامزدهای نهایی آزمون تأیید حضوری پیشنهاد می‌شود.',
                'rights_note': 'پرسش‌ها را استعدادیاب برای هر شرکت‌کننده می‌سازد (ماتریس، دنباله، قیاس، چرخش، مسئلهٔ عددی) '
                               'یا از الگوهای آزاد و کلاسیک روان‌شناسی پیروی می‌کند (مقایسه، فراخنای عدد، پیکان، واکنش).',
                'evidence_note': 'نسخهٔ نخست (%s)؛ شواهد پایایی و هنجار از داده‌های واقعی گردآوری می‌شود.' % S.SCORING_VERSION,
            })
            content = json.dumps({'code': code, 'spec': spec, 'v': S.SCORING_VERSION}, sort_keys=True, ensure_ascii=False)
            V = self.env['ts.instrument.version'].sudo().with_context(ts_loader=True)
            ver = V.create({
                'instrument_id': inst.id, 'contract_version': S.SCORING_VERSION, 'engine_version': S.SCORING_VERSION,
                'content_hash': hashlib.sha256(content.encode()).hexdigest(), 'mode': 'task', 'task_code': code,
                'scale_min': 0, 'scale_max': 100, 'reverse_rule': '-', 'aggregation': 'percentile of block raw scores',
                'missing_rule': 'items not reached count as wrong; untimed blocks need every trial', 'locked': True,
                'factor_ids': [fields.Command.create({
                    'code': fac, 'name': G_AB_FA(fac), 'sequence': 10 * (i + 1), 'scored': True,
                    'definition': AB_DEF.get(fac, ''),
                    'band_ids': [fields.Command.create({'band': 'low', 'min_score': 0, 'max_score': 33.3333,
                                                        'client_text': BAND_TEXT['low'], 'content_version': 'TASKS-v1'}),
                                 fields.Command.create({'band': 'medium', 'min_score': 33.3334, 'max_score': 66.6666,
                                                        'client_text': BAND_TEXT['medium'], 'content_version': 'TASKS-v1'}),
                                 fields.Command.create({'band': 'high', 'min_score': 66.6667, 'max_score': 100,
                                                        'client_text': BAND_TEXT['high'], 'content_version': 'TASKS-v1'})],
                }) for i, fac in enumerate(spec['factors'])],
            })
            ver._validate_contract()
            inst.write({'current_version_id': ver.id, 'approved_at': fields.Datetime.now(),
                        'approved_by_id': self.env.ref('base.user_root').id,
                        'approval_note': 'Owner decision 2026-10-12: HR hiring mode = personality + timed tasks.'})
            try:
                with self.env.cr.savepoint():
                    inst.action_publish()
            except (UserError, ValidationError) as e:
                _logger.warning('ts_tasks: %s left unpublished: %s', code, e)
            stats['created'] += 1
        _logger.info('ts_tasks instruments: %s', stats)
        return stats


def G_AB_FA(name):
    from odoo.addons.ts_onet.models.jobfit import AB_FA
    return AB_FA.get(name, name)


class TsTaskNorm(models.Model):
    """Empirical norm of one task block (EMP-n): sorted raw scores of real completions."""
    _name = 'ts.task.norm'
    _description = 'هنجار آزمون زمان‌دار'

    block = fields.Char(required=True, index=True)
    n = fields.Integer()
    values_json = fields.Text()
    built_at = fields.Datetime()

    _block_unique = models.Constraint('unique(block)', 'one norm per block')

    @api.model
    def ts_values(self, block):
        rec = self.sudo().search([('block', '=', block)], limit=1)
        if not rec or rec.n < S.NORM_MIN:
            return None
        return json.loads(rec.values_json or '[]')

    @api.model
    def _ts_rebuild(self):
        """Weekly cron: rebuild every block's norm from finished, non-void task attempts (one value per attempt)."""
        At = self.env['ts.attempt'].sudo()
        vals = {}
        for at in At.search([('state', '=', 'done'), ('task_result_json', '!=', False)]):
            res = json.loads(at.task_result_json or '{}')
            for b, r in (res.get('blocks') or {}).items():
                if r.get('raw') is not None and not r.get('practice_only'):
                    vals.setdefault(b, []).append(r['raw'])
        for b, v in vals.items():
            rec = self.sudo().search([('block', '=', b)], limit=1) or self.sudo().create({'block': b})
            rec.write({'n': len(v), 'values_json': json.dumps(sorted(v)), 'built_at': fields.Datetime.now()})
        return {b: len(v) for b, v in vals.items()}


class TsAttemptTask(models.Model):
    _inherit = 'ts.attempt'

    task_json = fields.Text('وضعیت آزمون زمان‌دار', readonly=True, copy=False)
    task_result_json = fields.Text('جزئیات نتیجهٔ آزمون زمان‌دار', readonly=True, copy=False)
    task_flags = fields.Char('نشانه‌های اجرای آزمون', readonly=True, copy=False)

    def ts_is_task(self):
        self.ensure_one()
        return self.version_id.mode == 'task'

    def ts_task_spec(self):
        self.ensure_one()
        return S.INSTRUMENTS[self.version_id.task_code]

    def _ts_extra_time(self):
        a = self.sudo().assignment_id if 'assignment_id' in self._fields else False
        x = getattr(a, 'ts_extra_time', 0) if a else 0
        try:
            return max(1.0, min(2.0, float(x or 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def _ts_state(self):
        self.ensure_one()
        st = json.loads(self.task_json) if self.task_json else None
        if not st:
            spec = self.ts_task_spec()
            st = {'seed': uuid.uuid4().hex, 'v': S.SCORING_VERSION, 'accom': self._ts_extra_time(),
                  'blocks': [{'key': b['key'], 'started': None, 'deadline': None, 'done': False, 'resp': None,
                              'meta': {'focus_lost': 0, 'resumed': 0}} for b in spec['blocks']]}
            self.sudo().write({'task_json': json.dumps(st)})
        return st

    def _ts_save(self, st):
        self.sudo().write({'task_json': json.dumps(st, separators=(',', ':'))})

    def _ts_items(self, st, i, practice=False):
        b = self.ts_task_spec()['blocks'][i]
        gen = G.GENERATORS[b['key']]
        seed = ('%s-practice' % st['seed']) if practice else ('%s-%d' % (st['seed'], i))
        if practice:
            return gen(seed, n=2 if b['key'] in S.POWER else 3, practice=True)
        return gen(seed, n=b['n'], practice=False) if b['n'] else gen(seed)

    def _ts_limit(self, st, i):
        lim = self.ts_task_spec()['blocks'][i]['limit']
        return int(round(lim * st.get('accom', 1.0))) if lim else None

    # ------------------------------------------------------------ player API (owner checked by the controller)
    def ts_task_config(self):
        """What the player page needs before any block starts (no live items, practice items with their keys)."""
        self.ensure_one()
        st = self._ts_state()
        spec = self.ts_task_spec()
        blocks = []
        now = _now()
        for i, b in enumerate(spec['blocks']):
            sb = st['blocks'][i]
            p_items, p_keys = self._ts_items(st, i, practice=True)
            blocks.append({
                'i': i, 'key': b['key'], 'title': b['title'], 'help': b['help'], 'n': b['n'],
                'limit': self._ts_limit(st, i), 'speed': bool(b.get('speed')), 'done': sb['done'],
                'started': bool(sb['started']),
                'remaining': max(0, int(sb['deadline'] - now)) if sb['deadline'] and not sb['done'] else None,
                'practice': {'items': p_items, 'keys': p_keys},
            })
        return {'code': self.version_id.task_code, 'title': spec['title'], 'intro': spec['intro'],
                'desktop': spec['desktop'], 'accom': st.get('accom', 1.0), 'blocks': blocks,
                'current': next((b['i'] for b in blocks if not b['done']), None)}

    def ts_task_start(self, i):
        """Start (or resume) block i: returns its items (no keys), previous answers and the seconds left."""
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError('این آزمون در حال اجرا نیست.')
        st = self._ts_state()
        if i < 0 or i >= len(st['blocks']):
            raise UserError('بخش نامعتبر است.')
        if any(not b['done'] for b in st['blocks'][:i]):
            raise UserError('بخش‌ها به ترتیب اجرا می‌شوند.')
        sb = st['blocks'][i]
        if sb['done']:
            raise UserError('این بخش پیش‌تر تمام شده است.')
        items, keys = self._ts_items(st, i)
        now = _now()
        if sb['started']:
            sb['meta']['resumed'] = sb['meta'].get('resumed', 0) + 1
        else:
            sb['started'] = now
            lim = self._ts_limit(st, i)
            sb['deadline'] = now + lim if lim else None
            sb['resp'] = [None] * len(keys)
        self._ts_save(st)
        return {'items': items, 'answers': [r and r.get('c') for r in (sb['resp'] or [])],
                'remaining': max(0, int(sb['deadline'] - now)) if sb['deadline'] else None}

    def ts_task_answer(self, i, idx, choice, rt):
        """One answer of a timed power block; refused after the deadline (plus a short grace for the network)."""
        self.ensure_one()
        st = self._ts_state()
        sb = st['blocks'][i] if 0 <= i < len(st['blocks']) else None
        if not sb or not sb['started'] or sb['done']:
            return {'ok': False, 'reason': 'closed'}
        if sb['deadline'] and _now() > sb['deadline'] + GRACE_S:
            return {'ok': False, 'reason': 'time'}
        if not (0 <= idx < len(sb['resp'])):
            return {'ok': False, 'reason': 'item'}
        sb['resp'][idx] = {'c': int(choice), 'rt': max(0, min(600000, int(rt or 0)))}
        self._ts_save(st)
        return {'ok': True, 'remaining': max(0, int(sb['deadline'] - _now())) if sb['deadline'] else None}

    def ts_task_finish(self, i, responses=None, focus_lost=0):
        """Close block i. Speed blocks send all trials here; power blocks were saved one by one."""
        self.ensure_one()
        st = self._ts_state()
        sb = st['blocks'][i] if 0 <= i < len(st['blocks']) else None
        if not sb or not sb['started']:
            raise UserError('این بخش شروع نشده است.')
        if sb['done']:
            return {'done': True, 'next': self._ts_next(st)}
        spec_b = self.ts_task_spec()['blocks'][i]
        b_items, b_keys = self._ts_items(st, i)
        n_keys = len(b_keys)
        if spec_b.get('speed'):
            lim = self._ts_limit(st, i)
            late = lim and _now() > sb['started'] + lim + 20
            clean = []
            for idx, r in enumerate((responses or [])[:n_keys]):
                if not isinstance(r, dict):
                    clean.append(None)
                    continue
                t = int(r.get('t') or 0)
                if lim and t > lim * 1000 + 500:
                    clean.append(None)          # after the block's time: not counted
                    continue
                clean.append({'c': r.get('c') if r.get('c') in (0, 1, 2, 3) else None,
                              'v': str(r.get('v', ''))[:12], 'rt': max(0, min(10000, int(r.get('rt') or 0))),
                              'inc': not b_items[idx].get('congruent', True)})   # from our items, not the client
            clean += [None] * (n_keys - len(clean))
            sb['resp'] = clean
            elapsed = _now() - sb['started']
            claimed = max([int(r.get('t') or 0) for r in (responses or []) if isinstance(r, dict)] or [0]) / 1000.0
            answered = sum(1 for r in clean if r)
            if late:
                sb['meta']['late'] = 1
            if claimed > elapsed + 5 or (answered and elapsed < answered * 0.15):
                sb['meta']['timing'] = 1       # the browser reports more time than passed, or impossibly fast trials
        sb['meta']['focus_lost'] = sb['meta'].get('focus_lost', 0) + max(0, min(50, int(focus_lost or 0)))
        sb['done'] = True
        sb['finished'] = _now()
        self._ts_save(st)
        nxt = self._ts_next(st)
        if nxt is None:
            self.action_submit()
        return {'done': True, 'next': nxt}

    @staticmethod
    def _ts_next(st):
        return next((n for n, b in enumerate(st['blocks']) if not b['done']), None)

    # ------------------------------------------------------------ scoring
    def _ts_score_task(self):
        st = self._ts_state()
        spec = self.ts_task_spec()
        Norm = self.env['ts.task.norm']
        blocks, pcts, flags = {}, {}, []
        for i, b in enumerate(spec['blocks']):
            sb = st['blocks'][i]
            items, keys = self._ts_items(st, i)
            resp = sb['resp'] or [None] * len(keys)
            raw = S.raw_score(b['key'], keys, resp, self._ts_limit(st, i))
            pct, norm = S.percentile(b['key'], raw, Norm.ts_values(b['key']))
            fl = S.block_flags(b['key'], keys, resp, sb['meta'])
            blocks[b['key']] = {'raw': round(raw, 4), 'pct': round(pct, 2), 'norm': norm, 'flags': fl,
                                'answered': sum(1 for r in resp if r), 'n': len(keys)}
            pcts[b['key']] = pct
            flags += fl
        factors = S.factor_scores(spec, pcts)
        return blocks, factors, sorted(set(flags))

    def action_submit(self, submission_key=None):
        if not self.filtered(lambda a: a.version_id.mode == 'task'):
            return super().action_submit(submission_key=submission_key)
        self.ensure_one()
        if self.state == 'done':
            return True
        if self.state != 'in_progress':
            raise UserError('این آزمون آمادهٔ ارسال نیست.')
        self.env.cr.execute('SELECT id FROM ts_attempt WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['state'])
        if self.state == 'done':
            return True
        st = self._ts_state()
        if any(not b['done'] for b in st['blocks']):
            raise UserError('همهٔ بخش‌های آزمون هنوز تمام نشده است.')
        blocks, factors, flags = self._ts_score_task()
        Result = self.env['ts.attempt.result'].sudo()
        for f in self.version_id.factor_ids.filtered('scored'):
            if f.code not in factors:
                continue
            p = factors[f.code]
            band = S.band_of(p)
            b = f.band_ids.filtered(lambda x: x.band == band)[:1]
            Result.create({'attempt_id': self.id, 'factor_id': f.id, 'score': round(p, 4), 'band': band,
                           'band_id': b.id, 'item_count': 0, 'answered_count': 0, 'raw_total': 0,
                           'client_text': b.client_text, 'content_version': b.content_version})
        detail = {'v': S.SCORING_VERSION, 'blocks': blocks, 'factors': {k: round(v, 2) for k, v in factors.items()},
                  'flags': flags, 'accom': st.get('accom', 1.0)}
        inp = hashlib.md5(json.dumps([st['seed'], [b['resp'] for b in st['blocks']]], sort_keys=True).encode()).hexdigest()
        out = hashlib.md5((inp + json.dumps(detail, sort_keys=True)).encode()).hexdigest()
        now = fields.Datetime.now()
        self.sudo().write({'state': 'done', 'submitted_at': now, 'submission_key': submission_key or uuid.uuid4().hex,
                           'engine_version': S.SCORING_VERSION, 'input_hash': inp, 'output_hash': out,
                           'task_result_json': json.dumps(detail, ensure_ascii=False), 'task_flags': ','.join(flags),
                           'released': True, 'released_at': now})
        self.env['ts.audit.event'].sudo().log('attempt.submit', self, instrument=self.instrument_id.code,
                                              version=self.version_id.contract_version, output_hash=out)
        # the lower modules' submit hooks (usage event -> billing, notifications, result SMS) are not reached by this
        # branch; call them the way ts_talent's matrix branch does.
        for hook in ('_ts_panel_record_usage', '_ts_notify_done', '_ts_notify_result_ready'):
            if hasattr(self, hook):
                try:
                    with self.env.cr.savepoint():
                        getattr(self, hook)()
                except Exception:
                    _logger.exception('task submit hook %s failed for attempt %s', hook, self.id)
        return True

    def ts_task_result(self):
        self.ensure_one()
        return json.loads(self.task_result_json or '{}')

    def ts_abilities(self):
        """{O*NET ability: percentile} of a finished task attempt (for JOBFIT)."""
        self.ensure_one()
        if self.state != 'done' or self.version_id.mode != 'task':
            return {}
        return {r.factor_id.code: r.score for r in self.result_ids}


class TsInstrumentBandTask(models.Model):
    _inherit = 'ts.instrument.band'

    def ts_seg_pct(self):
        """Width of this band on the result meter: 1-5 scale for questionnaires, 0-100 for task percentiles."""
        b = self
        v = b.factor_id.version_id
        if v.mode == 'task':
            return round(min(b.max_score, 100) - max(b.min_score, 0) + (0.0001 if b.band != 'high' else 0), 2)
        return round(100.0 * (min(b.max_score, 5) - max(b.min_score, 1) + (0.01 if b.band != 'high' else 0)) / 4, 2)


class TsAttemptResultTask(models.Model):
    _inherit = 'ts.attempt.result'

    def score_fa(self):
        if self.attempt_id.version_id.mode == 'task':
            return G.fa(int(round(self.score)))
        return super().score_fa()

    def ts_meter_label(self):
        if self.attempt_id.version_id.mode == 'task':
            return 'صدک %s از ۱۰۰، بازهٔ %s' % (G.fa(int(round(self.score))), self.band_fa())
        return 'نمره ' + self.score_fa() + ' از ۵، بازهٔ ' + self.band_fa()


class TsWorkspaceMemberTask(models.Model):
    _inherit = 'ts.workspace.member'

    def allowed_instruments(self):
        """The HR instruments (timed tasks and the HR questionnaire, `invite_only`) belong to employment panels only."""
        res = super().allowed_instruments()
        if self.workspace_id.purpose != 'employment':
            res = res.filtered(lambda i: not i.invite_only)
        return res
