"""Free personal career match (ts.career.run): one run per user ties the interest attempt (CAREER-IP-60), the two
background answers (job zone), the optional personality (CAREER-HEXACO-1) and ability tasks (TASK-*) to the
CAREER-MATCH engine. Results are cached in result_json, keyed by a hash of the inputs."""
import functools
import hashlib
import json
import logging
import os
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_hire.models import hexaco as H
from odoo.addons.ts_onet.models import jobfit as JF

from . import engine as E

_logger = logging.getLogger(__name__)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data', 'career_onet.json')
IP_DATA = os.path.join(HERE, '..', 'data', 'ip60_fa.json')
IP_CODE = 'CAREER-IP-60'
HEX_CODE = 'CAREER-HEXACO-1'
TASK_CODES = ['TASK-REASON', 'TASK-SPATIAL', 'TASK-NUMERIC']
CAP_PARAM = 'ts_career.daily_cap'
CAP_DEFAULT = 100
RIASEC_CODE = dict(zip('RIASEC', E.RIASEC))
RIASEC_FA = {'Realistic': 'واقع‌گرا', 'Investigative': 'جست‌وجوگر', 'Artistic': 'هنری', 'Social': 'اجتماعی',
             'Enterprising': 'متهور', 'Conventional': 'قراردادی'}
RIASEC_GLOSS = {'Realistic': 'کار با ابزار، دستگاه، مواد و طبیعت؛ کارهای عملی',
                'Investigative': 'پژوهش، تحلیل و فهمیدن چرایی چیزها',
                'Artistic': 'آفریدن، طراحی، بیان و اجرا',
                'Social': 'کمک، آموزش و مراقبت از دیگران',
                'Enterprising': 'رهبری، متقاعد کردن، فروش و کسب‌وکار',
                'Conventional': 'نظم، داده، عدد و رویه‌های روشن'}
EDU = [('1', 'کمتر از دیپلم'), ('2', 'دیپلم'), ('3', 'کاردانی یا مدرک فنی‌وحرفه‌ای'), ('4', 'کارشناسی'),
       ('5', 'کارشناسی ارشد یا دکتری')]
EXP = [('0', 'سابقهٔ کار ندارم'), ('1_2', 'کمتر از ۳ سال'), ('3_5', '۳ تا ۵ سال'), ('5plus', 'بیشتر از ۵ سال')]
JZ_FA = {1: 'آمادگی کم: چند روز تا چند ماه آموزش در محل کار',
         2: 'آمادگی متوسط رو به پایین: معمولاً دیپلم و کمی سابقه',
         3: 'آمادگی متوسط: آموزش فنی‌وحرفه‌ای یا کاردانی و سابقهٔ مرتبط',
         4: 'آمادگی زیاد: معمولاً کارشناسی و چند سال سابقه',
         5: 'آمادگی بسیار زیاد: معمولاً کارشناسی ارشد یا بالاتر و سابقهٔ طولانی'}
READY_FA = {'READY': 'آماده', 'NEAR': 'یک پله فاصله', 'FAR': 'دو پله یا بیشتر فاصله', 'UNKNOWN': 'نامشخص'}
LEVEL_FA = {'high': 'هم‌خوانی زیاد', 'medium': 'هم‌خوانی متوسط', 'low': 'هم‌خوانی کم', 'none': 'نامشخص'}
ONET_NOTICE = ('بخش علایق ترجمه و اقتباسی از O*NET Interest Profiler است. وزارت کار آمریکا (USDOL/ETA) این تغییرات را '
               'تأیید یا آزمایش نکرده است. داده‌های شغلی از O*NET 31.0 (مجوز CC BY 4.0).')
IP_BANDS = [('low', 1.0, 2.5), ('medium', 2.6, 3.4), ('high', 3.5, 5.0)]
# phase C (docs/career/01_completion.md): the two questionnaires of the career match, one item at a time, a pause every
# 30 items (interests: half-way; work styles: four sittings)
CARD_CODES = (IP_CODE, HEX_CODE)
CARD_PAGE = 30


@functools.lru_cache(maxsize=1)
def career_data():
    with open(DATA, encoding='utf-8') as fh:
        data = json.load(fh)
    return data, E.Ref(data)


class TsAttemptCareer(models.Model):
    _inherit = 'ts.attempt'

    career_run_id = fields.Many2one('ts.career.run', 'مسیر شغلی', index=True, ondelete='set null')
    ts_career_remind = fields.Boolean('یادآوری پیامکی (آزمون شغلی مهمان)', copy=False, readonly=True)

    def _ts_notify_result_ready(self):
        # the career list is one page the person is already on: no result-ready SMS per module
        if self.sudo().career_run_id:
            return False
        return super()._ts_notify_result_ready()

    def ts_erase_content(self):
        # an erase request removes the whole career profile (result cache, education, experience) with the answers
        run = self.sudo().career_run_id
        res = super().ts_erase_content()
        if run:
            run.unlink()
        return res

    # ------------------------------------------------------------------ phase B: a guest's interests join the account
    def ts_guest_claim(self, user):
        """The interests answered before sign-in become the run of the account that claims them (newest counts)."""
        ok = super().ts_guest_claim(user)
        at = self.sudo()
        if ok and at.instrument_id.code == IP_CODE and not at.career_run_id:
            run = self.env['ts.career.run'].ts_for_user(at.user_id, create=True)
            at.write({'career_run_id': run.id})
            run.write({'remind': bool(at.ts_career_remind)})
        return ok

    # ------------------------------------------------------------------ funnel: every career module is counted
    def _ts_career_counted(self):
        s = self.sudo()
        return bool(s.career_run_id or (s.ts_guest and s.instrument_id.code == IP_CODE))

    def _ts_funnel_target(self):
        if self._ts_career_counted():
            return True, None
        return super()._ts_funnel_target()

    def _ts_funnel_first(self):
        s = self.sudo()
        if s.career_run_id and request and s.state == 'in_progress':
            self.env.cr.execute('SELECT 1 FROM ts_attempt_answer WHERE attempt_id = %s LIMIT 1', [self.id])
            return not self.env.cr.fetchone()
        return super()._ts_funnel_first()

    def save_answer(self, item_id, value):
        """Half-way of a career questionnaire is a funnel step (where people stop is what phase A measures)."""
        before = None
        if request and self._ts_career_counted() and self.state == 'in_progress':
            self.env['ts.attempt.answer'].flush_model()
            self.env.cr.execute('SELECT count(*) FROM ts_attempt_answer WHERE attempt_id = %s', [self.id])
            before = self.env.cr.fetchone()[0]
        res = super().save_answer(item_id, value)
        if before is not None:
            try:
                total = self.sudo().version_id.active_item_count or 0
                if total and before < (total + 1) // 2 <= before + 1:
                    self.env['ts.funnel.event'].ts_log(request, 'half', instrument=self.sudo().instrument_id)
            except Exception:       # noqa: BLE001 - measuring never breaks answering
                _logger.exception('ts_career: half-way not counted')
        return res


class TsInstrumentCareer(models.Model):
    _inherit = 'ts.instrument'

    def ts_page_size(self):
        return CARD_PAGE if self.code in CARD_CODES else super().ts_page_size()

    def ts_card_mode(self):
        return self.code in CARD_CODES or super().ts_card_mode()


class TsTaskNormCareer(models.Model):
    _inherit = 'ts.task.norm'

    @api.model
    def _ts_rebuild(self):
        """Hiring norms stay built from hiring and panel takes only: free career task attempts, a member's own try-out
        and sample reports (ts_preview, onb3) and voided attempts are all left out."""
        At = self.env['ts.attempt'].sudo()
        vals = {}
        for at in At.search([('state', '=', 'done'), ('task_result_json', '!=', False), ('career_run_id', '=', False),
                             ('ts_preview', '=', False), ('voided', '=', False)]):
            res = json.loads(at.task_result_json or '{}')
            for b, r in (res.get('blocks') or {}).items():
                if r.get('raw') is not None and not r.get('practice_only'):
                    vals.setdefault(b, []).append(r['raw'])
        for b, v in vals.items():
            rec = self.sudo().search([('block', '=', b)], limit=1) or self.sudo().create({'block': b})
            rec.write({'n': len(v), 'values_json': json.dumps(sorted(v)), 'built_at': fields.Datetime.now()})
        return {b: len(v) for b, v in vals.items()}


class TsCareerRun(models.Model):
    _name = 'ts.career.run'
    _inherit = ['ts.brand.short.mixin']
    _description = 'مسیر شغلی (نسخهٔ رایگان)'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    edu = fields.Selection(EDU, 'تحصیلات')
    exp = fields.Selection(EXP, 'سابقهٔ کار')
    attempt_ids = fields.One2many('ts.attempt', 'career_run_id')
    result_json = fields.Text()
    result_key = fields.Char()
    computed_at = fields.Datetime()
    model_version = fields.Char()
    # phase A (docs/career/01_completion.md): reminders on by default (owner 2026-10-15), one tap turns them off
    remind = fields.Boolean('یادآوری پیامکی', default=True)
    remind_off_at = fields.Datetime('یادآوری خاموش شد', readonly=True)
    first_result_at = fields.Datetime('نخستین دیدن فهرست', readonly=True)
    nudge_ids = fields.One2many('ts.career.nudge', 'run_id', 'یادآوری‌ها')

    _user_uniq = models.Constraint('unique(user_id)', 'هر حساب یک مسیر شغلی دارد.')
    _short_code_unique = models.Constraint('unique(short_code)', 'کد پیوند کوتاه باید یکتا باشد.')

    # ---------------------------------------------------------------- reminders and the SMS link
    def ts_short_url(self):
        """/career/c/<code>: the link of a reminder SMS (opens the step where this person stopped)."""
        self.ensure_one()
        from odoo.addons.ts_brand.models.short import site_base
        return '%s/career/c/%s' % (site_base(self.env), self.ts_short_code())

    def ts_resume_url(self):
        """Where this person continues: the open questionnaire, the two questions, or the list."""
        self.ensure_one()
        st = self.ts_state()
        if not st['ip_done']:
            return '/take/%s' % self.ts_ensure_attempt(IP_CODE).access_token
        if not st['bg_done']:
            return '/career/r'
        if st['hex'] and not st['hex_done']:
            return '/take/%s' % st['hex'].access_token
        return '/career/r'

    def ts_set_remind(self, on):
        self.ensure_one()
        self.sudo().write({'remind': bool(on), 'remind_off_at': False if on else fields.Datetime.now()})
        if not on:
            self.sudo().nudge_ids.filtered(lambda n: n.state == 'queued').write({'state': 'skipped', 'reason': 'opted_out'})

    def ts_minutes_left(self, code):
        """Honest minutes left of one questionnaire (from the items left and the instrument's minutes)."""
        self.ensure_one()
        at = self.ts_attempt(code, done=False)
        inst = at.instrument_id if at else self._inst(code)
        total = (inst.active_item_count or 0) if inst else 0
        left = total - (len(at.answer_ids) if at else 0)
        mins = (inst.duration_minutes or 0) if inst else 0
        return max(1, -(-left * mins // total)) if (total and mins and left > 0) else 0

    # ---------------------------------------------------------------- access helpers
    @api.model
    def ts_cap_reached(self):
        """New free starts in the last 24 hours (runs of accounts and interests started as a guest) reached the cap."""
        try:
            cap = int(self.env['ir.config_parameter'].sudo().get_str(CAP_PARAM) or CAP_DEFAULT)
        except (TypeError, ValueError):
            cap = CAP_DEFAULT
        since = fields.Datetime.now() - timedelta(hours=24)
        runs = self.sudo().search_count([('create_date', '>=', since)])
        guests = self.env['ts.attempt'].sudo().search_count([('create_date', '>=', since), ('ts_guest', '=', True),
                                                             ('instrument_id.code', '=', IP_CODE)])
        return runs + guests >= cap

    @api.model
    def ts_for_user(self, user, create=False):
        run = self.sudo().search([('user_id', '=', user.id)], limit=1)
        if not run and create:
            try:
                with self.env.cr.savepoint():
                    run = self.sudo().create({'user_id': user.id})
            except Exception:           # a parallel request created it first (unique user)
                run = self.sudo().search([('user_id', '=', user.id)], limit=1)
        return run

    def _inst(self, code):
        return self.env['ts.instrument'].sudo().search([('code', '=', code), ('state', '=', 'published')], limit=1)

    def ts_attempt(self, code, done=None):
        self.ensure_one()
        ats = self.sudo().attempt_ids.filtered(lambda a: a.instrument_id.code == code and a.state != 'void')
        if done is True:
            ats = ats.filtered(lambda a: a.state == 'done')
        elif done is False:
            ats = ats.filtered(lambda a: a.state != 'done')
        return ats.sorted('id', reverse=True)[:1]

    def ts_ensure_attempt(self, code):
        """The open (or new) attempt of one module. Later modules reuse the consent given on the interest module."""
        self.ensure_one()
        at = self.ts_attempt(code, done=False)
        if at:
            return at
        inst = self._inst(code)
        if not inst:
            raise UserError('این بخش هنوز در دسترس نیست.')
        at = self.env['ts.attempt'].sudo().create({'user_id': self.user_id.id, 'instrument_id': inst.id,
                                                    'version_id': inst.current_version_id.id, 'career_run_id': self.id})
        first = self.ts_attempt(IP_CODE)
        if code != IP_CODE and first and first.consent_service and at.state == 'consent':
            # the start button of every later module says the first consent is recorded for it too (service only)
            at.give_consent(research=False)
            if 'ts.consent.record' in self.env:
                Rec = self.env['ts.consent.record'].sudo()
                if Rec.search_count([('attempt_id', '=', first.id), ('kind', '=', 'guardian')], limit=1):
                    from odoo.addons.ts_panel.controllers.consent import TEXT_VERSION
                    Rec._log('guardian', self.user_id, attempt=at, workspace=at.workspace_id, version=TEXT_VERSION,
                             given_as='guardian', client=at.client_id)
        return at

    def ts_next_task(self):
        self.ensure_one()
        for code in TASK_CODES:
            if not self.ts_attempt(code, done=True):
                return code
        return None

    def ts_state(self):
        self.ensure_one()
        ip = self.ts_attempt(IP_CODE)
        hx = self.ts_attempt(HEX_CODE)
        tasks_done = [c for c in TASK_CODES if self.ts_attempt(c, done=True)]
        return {'ip': ip, 'ip_done': bool(ip and ip.state == 'done'), 'bg_done': bool(self.edu and self.exp),
                'hex': hx, 'hex_done': bool(hx and hx.state == 'done'),
                'tasks_done': len(tasks_done), 'tasks_total': len(TASK_CODES)}

    # ---------------------------------------------------------------- person and result
    def ts_person(self):
        self.ensure_one()
        p = {'riasec': None, 'styles': None, 'abilities': None, 'values': None, 'jz': E.jz_from(self.edu, self.exp)}
        ip = self.ts_attempt(IP_CODE, done=True)
        if ip:
            sc = {r.factor_id.code: r.score for r in ip.sudo().result_ids}
            if all(k in sc for k in RIASEC_CODE):
                p['riasec'] = {RIASEC_CODE[k]: sc[k] for k in RIASEC_CODE}
        hx = self.ts_attempt(HEX_CODE, done=True)
        if hx:
            fac = {r.factor_id.code: r.score for r in hx.sudo().result_ids if r.factor_id.code in JF.FACETS}
            if len(fac) == len(JF.FACETS):
                p['styles'] = JF.style_scores(JF.center_facets(fac))
        ab = {}
        for code in TASK_CODES:
            t = self.ts_attempt(code, done=True)
            if t and hasattr(t, 'ts_abilities'):
                ab.update(t.sudo().ts_abilities() or {})
        p['abilities'] = ab or None
        return p

    def ts_result(self):
        """The engine result for the current inputs (recomputed only when an input changed)."""
        self.ensure_one()
        person = self.ts_person()
        if not person['riasec']:
            return None
        data, ref = career_data()
        key = hashlib.sha256(json.dumps([E.MODEL, data.get('version'), person], sort_keys=True).encode()).hexdigest()
        if self.result_key == key and self.result_json:
            return json.loads(self.result_json)
        res = E.match(person, data, ref)
        res['rows'] = res['rows'][:120]
        res['person'] = person
        self.sudo().write({'result_json': json.dumps(res, ensure_ascii=False), 'result_key': key,
                           'computed_at': fields.Datetime.now(), 'model_version': E.MODEL})
        return res

    @api.model
    def ts_view_row(self, row, person):
        """Display dict for one occupation row (titles, Persian levels, reasons)."""
        data, ref = career_data()
        occ = data['occ'].get(row['code']) or {}
        why, watch = E.explain_fa(row, person, {'riasec': RIASEC_FA, 'ws': JF.WS_FA, 'ab': JF.AB_FA})
        return {'code': row['code'], 'fa': occ.get('fa') or occ.get('en'), 'en': occ.get('en'), 'desc': occ.get('desc'),
                'level': row['level'], 'level_fa': LEVEL_FA.get(row['level'], ''), 'ready': row['ready'],
                'ready_fa': READY_FA.get(row['ready'], ''), 'jz': row.get('jz'), 'jz_fa': JZ_FA.get(row.get('jz') or 0, ''),
                'why': why, 'watch': watch, 'clinic_fa': [JF.AB_FA.get(a, a) for a in row.get('clinic') or []],
                'types_fa': ' و '.join(RIASEC_FA[k] for k in (row.get('I') or {}).get('job_top', [])),
                'area': row.get('area') or row['code'][:2], 'area_fa': E.AREA_FA.get(row.get('area') or row['code'][:2], ''),
                'rank': row['rank']}

    # ---------------------------------------------------------------- instruments
    @api.model
    def _ts_load_career(self):
        return {'ip': self._ts_load_ip(), 'hexaco': self._ts_load_hexaco()}

    def _publish(self, inst, ver, note):
        ver._validate_contract()
        inst.write({'current_version_id': ver.id, 'approved_at': fields.Datetime.now(),
                    'approved_by_id': self.env.ref('base.user_root').id, 'approval_note': note})
        try:
            with self.env.cr.savepoint():
                inst.action_publish()
        except (UserError, ValidationError) as e:
            _logger.warning('ts_career: %s left unpublished: %s (%s)', inst.code, e, ver.validation_report)

    @api.model
    def _ts_load_ip(self):
        Inst = self.env['ts.instrument'].sudo().with_context(active_test=False, ts_loader=True)
        if Inst.search_count([('code', '=', IP_CODE)]):
            return {'existing': 1}
        with open(IP_DATA, encoding='utf-8') as fh:
            items = json.load(fh)['items']
        by_t = {}
        for it in items:
            by_t.setdefault(it['type'], []).append(it)
        order = [by_t[t][k] for k in range(10) for t in 'RIASEC']        # interleaved: no two neighbours share a type
        inst = Inst.create({
            'name': 'علایق شغلی', 'code': IP_CODE, 'sequence': 880, 'audience': 'adult', 'purpose': 'personal',
            'invite_only': True, 'category': 'مسیر شغلی',
            'summary': 'به ۶۰ کار کوتاه بگویید چقدر دوست دارید انجامشان دهید.',
            'intended_use': 'شناخت علایق شغلی (شش تیپ هالند) برای پیدا کردن شغل‌های هم‌خوان در فهرست O*NET؛ برای خودشناسی، '
                            'نه برای تصمیم استخدام.',
            'limitations': 'نسخهٔ آزمایشی: هنجار ایرانی هنوز ساخته نشده است و هم‌خوانی شغل‌ها بر پایهٔ داده‌های شغلی آمریکا است.',
            'rights_note': ONET_NOTICE,
            'evidence_note': 'نسخهٔ اصلی انگلیسی (۶۰ جمله) پایایی و اعتبار گزارش‌شده دارد؛ نسخهٔ فارسی با دو ترجمهٔ مستقل، '
                             'تلفیق و ترجمهٔ برگردان ساخته شده و اعتبارسنجی آن با داده‌های همین نسخه انجام می‌شود.',
        })
        content = json.dumps([(it['n'], it['type'], it['fa']) for it in order], ensure_ascii=False)
        factor_cmds = []
        for i, t in enumerate('RIASEC'):
            name = E.RIASEC['RIASEC'.index(t)]
            factor_cmds.append(fields.Command.create({
                'code': t, 'name': RIASEC_FA[name], 'sequence': 10 * (i + 1), 'scored': True, 'definition': RIASEC_GLOSS[name],
                'band_ids': [fields.Command.create({'band': b, 'min_score': lo, 'max_score': hi, 'client_text': '',
                                                    'content_version': IP_CODE}) for b, lo, hi in IP_BANDS]}))
        ver = self.env['ts.instrument.version'].sudo().with_context(ts_loader=True).create({
            'instrument_id': inst.id, 'contract_version': IP_CODE, 'locked': True, 'factor_ids': factor_cmds,
            'content_hash': hashlib.sha256(content.encode()).hexdigest()})
        fid = {f.code: f.id for f in ver.factor_ids}
        self.env['ts.instrument.item'].sudo().with_context(ts_loader=True).create([
            {'version_id': ver.id, 'factor_id': fid[it['type']], 'sequence': 10 * (k + 1), 'source_question_id': it['n'],
             'text': it['fa'], 'reverse': False, 'source_xmlid': 'onet_ipsf_%d' % it['n']} for k, it in enumerate(order)])
        self._publish(inst, ver, 'Owner decision 2026-10-13: free career match, automatic adaptation (beta).')
        return {'created': 1, 'items': len(order)}

    @api.model
    def _ts_load_hexaco(self):
        """Personal copy of the HR personality questionnaire (same items and scoring, personal purpose)."""
        Inst = self.env['ts.instrument'].sudo().with_context(active_test=False, ts_loader=True)
        if Inst.search_count([('code', '=', HEX_CODE)]):
            return {'existing': 1}
        src = Inst.search([('code', '=', H.HEXACO_CODE)], limit=1)
        if not src or not src.current_version_id:
            return {'missing_source': 1}
        sv = src.current_version_id
        inst = Inst.create({
            'name': 'سبک‌های کاری', 'code': HEX_CODE, 'sequence': 881, 'audience': 'adult', 'purpose': 'personal',
            'invite_only': True, 'category': 'مسیر شغلی',
            'summary': '۱۲۰ جملهٔ کوتاه دربارهٔ شیوهٔ کار و رفتار شما.',
            'intended_use': 'شناخت سبک‌های کاری (۲۴ ویژگی شخصیت در مدل هگزاکو) برای دقیق‌تر کردن فهرست شغل‌های هم‌خوان؛ '
                            'برای خودشناسی، نه برای تصمیم استخدام.',
            'limitations': src.limitations, 'rights_note': src.rights_note, 'evidence_note': src.evidence_note,
        })
        factor_cmds = [fields.Command.create({
            'code': f.code, 'name': f.name, 'sequence': f.sequence, 'scored': f.scored, 'definition': f.definition,
            'report_hidden': f.report_hidden,
            'band_ids': [fields.Command.create({'band': b.band, 'min_score': b.min_score, 'max_score': b.max_score,
                                                'client_text': b.client_text, 'content_version': HEX_CODE})
                         for b in f.band_ids]}) for f in sv.factor_ids]
        ver = self.env['ts.instrument.version'].sudo().with_context(ts_loader=True).create({
            'instrument_id': inst.id, 'contract_version': HEX_CODE, 'locked': True, 'factor_ids': factor_cmds,
            'content_hash': sv.content_hash})
        fid = {f.code: f.id for f in ver.factor_ids}
        self.env['ts.instrument.item'].sudo().with_context(ts_loader=True).create([
            {'version_id': ver.id, 'factor_id': fid[i.factor_id.code], 'sequence': i.sequence,
             'source_question_id': i.source_question_id, 'text': i.text, 'reverse': i.reverse, 'disabled': i.disabled,
             'source_xmlid': i.source_xmlid} for i in sv.item_ids])
        self._publish(inst, ver, 'Owner decision 2026-10-13: personal copy of HR-HEXACO-1 for the free career match.')
        return {'created': 1, 'items': len(sv.item_ids)}
