"""The HR personality questionnaire: IPIP-HEXACO (Ashton, Lee & Goldberg 2007, public domain, ipip.ori.org), 24 facets x
5 items + 3 attention items (docs/hr/01_architecture.md section 2). Played by the normal Likert player; scored by the
normal engine (facet = factor, mean 1-5). The attention items form a hidden factor used only for response validity.
The copyrighted HEXACO-PI-R / HEXACO-60 wording is not used."""
import hashlib
import json
import logging
import os

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ts_onet.models.jobfit import FACET_FA, FACETS

_logger = logging.getLogger(__name__)
HEXACO_CODE = 'HR-HEXACO-1'
ATTN = 'ATTN'
DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'hexaco_fa.json')

# (definition, high, low) - candidate-facing, «شما» register, counselling tone; medium text is generic.
FACET_TEXT = {
    'Sincerity': ('رک و بی‌پرده بودن در روابط، بدون چاپلوسی یا ظاهرسازی.',
                  'در روابط کاری رک هستید و برای پیشبرد کار از چاپلوسی یا ظاهرسازی پرهیز می‌کنید.',
                  'گاهی برای رسیدن به هدف، خود را با انتظار دیگران هماهنگ نشان می‌دهید.'),
    'Fairness': ('پایبندی به قاعده و پرهیز از سودجویی به زیان دیگران.',
                 'حتی وقتی فرصت سودجویی هست، به قاعده و حق دیگران پایبند می‌مانید.',
                 'گاهی قاعده‌ها را برای رسیدن به سود شخصی انعطاف‌پذیر می‌بینید.'),
    'Greed Avoidance': ('کم‌اهمیت دانستن ثروت، تجملات و نشانه‌های جایگاه.',
                        'ثروت و نشانه‌های جایگاه برای شما انگیزهٔ اصلی نیست.',
                        'پاداش مادی و نشانه‌های جایگاه برایتان انگیزهٔ مهمی است.'),
    'Modesty': ('خود را برتر از دیگران ندیدن.',
                'خود را برتر از دیگران نمی‌دانید و انتظار امتیاز ویژه ندارید.',
                'از توانایی‌ها و جایگاه خود با اطمینان سخن می‌گویید و انتظار احترام ویژه دارید.'),
    'Fearfulness': ('احتیاط در برابر خطرهای جسمی.',
                    'از موقعیت‌های پرخطر جسمی دوری می‌کنید.',
                    'در موقعیت‌های پرخطر جسمی کمتر احساس ترس می‌کنید.'),
    'Anxiety': ('نگران شدن در موقعیت‌های دشوار یا نامطمئن.',
                'در موقعیت‌های دشوار یا نامطمئن زودتر نگران می‌شوید.',
                'زیر فشار، آرامش خود را بیشتر حفظ می‌کنید.'),
    'Dependence': ('نیاز به حمایت عاطفی دیگران در دشواری‌ها.',
                   'در دشواری‌ها از حمایت و همدلی دیگران نیرو می‌گیرید.',
                   'مشکلات را بیشتر خودتان و بدون کمک دیگران حل می‌کنید.'),
    'Sentimentality': ('پیوند عاطفی عمیق با دیگران.',
                       'احساسات دیگران و پیوندهای عاطفی برایتان بسیار مهم است.',
                       'در تصمیم‌ها کمتر تحت تأثیر احساسات قرار می‌گیرید.'),
    'Expressiveness': ('ابراز راحت فکر و احساس در جمع.',
                       'در جمع راحت نظر و احساس خود را بیان می‌کنید.',
                       'ترجیح می‌دهید در جمع کمتر توجه را به خود جلب کنید.'),
    'Social Boldness': ('راحتی در موقعیت‌های اجتماعی و هدایت گروه.',
                        'در موقعیت‌های اجتماعی و در هدایت گروه احساس راحتی می‌کنید.',
                        'در موقعیت‌های تازهٔ اجتماعی یا در برابر جمع محتاط‌تر هستید.'),
    'Sociability': ('لذت از گفت‌وگو و همنشینی با دیگران.',
                    'از گفت‌وگو و کار در کنار دیگران لذت می‌برید.',
                    'کار مستقل و جمع‌های کوچک را ترجیح می‌دهید.'),
    'Liveliness': ('انرژی و حال‌وهوای مثبت.',
                   'معمولاً پرانرژی و امیدوار هستید.',
                   'حال‌وهوای آرام‌تر و کم‌هیجان‌تری دارید.'),
    'Forgiveness': ('آمادگی برای بخشیدن و اعتماد دوباره.',
                    'پس از دلخوری آسان‌تر می‌بخشید و دوباره اعتماد می‌کنید.',
                    'پس از دلخوری، برای اعتماد دوباره به زمان بیشتری نیاز دارید.'),
    'Gentleness': ('نرمی در قضاوت دیگران.',
                   'در قضاوت و بازخورد دادن ملایم و مهربان هستید.',
                   'در قضاوت دیگران سخت‌گیرتر و رک‌تر هستید.'),
    'Flexibility': ('کنار آمدن با نظر دیگران برای همکاری.',
                    'برای همکاری آماده‌اید از نظر خود کوتاه بیایید.',
                    'روی نظر خود محکم می‌ایستید و کمتر کوتاه می‌آیید.'),
    'Patience': ('آرام ماندن در برابر رفتار ناخوشایند.',
                 'در برابر رفتار ناخوشایند دیگران آرام می‌مانید.',
                 'از رفتار ناخوشایند دیگران زودتر برآشفته می‌شوید.'),
    'Organization': ('نظم در کار و محیط.',
                     'کارها و محیط کارتان را منظم و برنامه‌ریزی‌شده نگه می‌دارید.',
                     'با کار بی‌برنامه و انعطاف‌پذیر راحت‌تر هستید.'),
    'Diligence': ('تلاش پیوسته برای رسیدن به هدف.',
                  'برای رسیدن به هدف سخت و پیوسته کار می‌کنید.',
                  'انگیزهٔ کار سخت و طولانی برایتان کمتر است.'),
    'Perfectionism': ('دقت و توجه به جزئیات.',
                      'به جزئیات دقت می‌کنید و کار را بی‌نقص می‌خواهید.',
                      'به نتیجهٔ کلی بیشتر از جزئیات توجه می‌کنید.'),
    'Prudence': ('سنجیدن پیش از تصمیم.',
                 'پیش از تصمیم، گزینه‌ها و پیامدها را می‌سنجید.',
                 'سریع و بر پایهٔ حس لحظه تصمیم می‌گیرید.'),
    'Aesthetic Appreciation': ('لذت از هنر، طبیعت و زیبایی.',
                               'از هنر، طبیعت و زیبایی لذت عمیقی می‌برید.',
                               'هنر و زیبایی‌شناسی برایتان اولویت کمتری دارد.'),
    'Inquisitiveness': ('میل به دانستن دربارهٔ دانش و جهان.',
                        'دربارهٔ دانش، فناوری و جهان کنجکاو هستید.',
                        'کنجکاوی کمتری به موضوع‌های تازهٔ علمی و فنی دارید.'),
    'Creativity': ('میل به ساختن راه‌ها و ایده‌های تازه.',
                   'دوست دارید راه‌حل‌ها و ایده‌های تازه بسازید.',
                   'راه‌های آزموده و شناخته‌شده را ترجیح می‌دهید.'),
    'Unconventionality': ('پذیرش ایده‌ها و شیوه‌های غیرمعمول.',
                          'ایده‌ها و شیوه‌های غیرمعمول را می‌پذیرید و از آن‌ها لذت می‌برید.',
                          'شیوه‌های متعارف و پذیرفته‌شده را ترجیح می‌دهید.'),
}
MEDIUM_TEXT = 'در «%s» در میانهٔ دو سو هستید؛ بسته به موقعیت، به هر دو شیوه رفتار می‌کنید.'
BANDS5 = [('low', 1.0, 2.6), ('medium', 2.8, 3.4), ('high', 3.6, 5.0)]
BANDS3 = [('low', 1.0, 2.34), ('medium', 2.66, 3.67), ('high', 4.0, 5.0)]


class TsInstrumentFactorHidden(models.Model):
    _inherit = 'ts.instrument.factor'

    report_hidden = fields.Boolean('در گزارش نمایش داده نشود', help='برای عامل‌های کنترلی (مثل جمله‌های سنجش دقت).')


class TsAttemptHidden(models.Model):
    _inherit = 'ts.attempt'

    def result_rows(self):
        return super().result_rows().filtered(lambda r: not r.factor_id.report_hidden)

    def ts_facets(self):
        """{facet: mean 1-5} of a finished HR personality attempt (for JOBFIT)."""
        self.ensure_one()
        if self.state != 'done' or self.instrument_id.code != HEXACO_CODE:
            return {}
        return {r.factor_id.code: r.score for r in self.result_ids if r.factor_id.code in FACETS}


class TsInstrumentHexaco(models.Model):
    _inherit = 'ts.instrument'

    @api.model
    def _ts_load_hexaco(self):
        """Create and publish the HR personality questionnaire once (by code). Items are interleaved by facet so no two
        neighbours measure the same thing; the three attention items sit at about 1/4, 1/2 and 3/4 of the way."""
        Inst = self.sudo().with_context(active_test=False, ts_loader=True)
        if Inst.search_count([('code', '=', HEXACO_CODE)]):
            return {'existing': 1}
        with open(DATA, encoding='utf-8') as fh:
            data = json.load(fh)
        by_f = {}
        for it in data['items']:
            by_f.setdefault(it['facet'], []).append(it)
        if sorted(by_f) != sorted(FACETS) or any(len(v) != 5 for v in by_f.values()):
            raise UserError('hexaco_fa.json must hold 5 items for each of the 24 facets')
        order = []
        for k in range(5):
            for f in FACETS:
                order.append(by_f[f][k])
        attn_at = {30: data['attention'][0], 62: data['attention'][1], 95: data['attention'][2]}
        seq, items = 0, []
        for n, it in enumerate(order):
            if n in attn_at:
                seq += 10
                items.append((seq, ATTN, attn_at[n]['fa'], False))
            seq += 10
            items.append((seq, it['facet'], it['fa'], it['key'] < 0))
        inst = Inst.create({
            'name': 'پرسش‌نامهٔ سبک‌های کاری', 'code': HEXACO_CODE, 'sequence': 890, 'audience': 'adult',
            'purpose': 'employment', 'invite_only': True, 'category': 'سنجه‌های استخدامی',
            'intended_use': 'شناخت سبک‌های کاری بزرگسالان (۲۴ ویژگی شخصیت در مدل هگزاکو) برای کمک به تصمیم استخدامی '
                            'همراه با مصاحبه و سوابق، و برای بازخورد به خود داوطلب؛ هرگز تنها مبنای تصمیم.',
            'limitations': 'خودگزارشی است و در موقعیت استخدام ممکن است اغراق‌آمیز پاسخ داده شود؛ نشانه‌های دقت پاسخ‌دهی '
                           'به منابع انسانی گزارش می‌شود. هنجار ایرانی هنوز ساخته نشده است.',
            'rights_note': 'جمله‌ها از مقیاس‌های IPIP-HEXACO (Ashton, Lee & Goldberg, 2007) در مخزن بین‌المللی '
                           'جمله‌های شخصیت (ipip.ori.org) است که مالکیت عمومی دارد؛ ترجمهٔ فارسی از استعدادیاب.',
            'evidence_note': 'پایایی مقیاس‌های ۱۰جمله‌ای اصلی ۰٫۶۹ تا ۰٫۸۸؛ نسخهٔ ۵جمله‌ای فارسی در حال اعتبارسنجی.',
        })
        content = json.dumps([(s, f, t, r) for s, f, t, r in items], ensure_ascii=False)
        factor_cmds = []
        for i, f in enumerate(FACETS):
            d, hi, lo = FACET_TEXT[f]
            texts = {'low': lo, 'medium': MEDIUM_TEXT % FACET_FA[f], 'high': hi}
            factor_cmds.append(fields.Command.create({
                'code': f, 'name': FACET_FA[f], 'sequence': 10 * (i + 1), 'scored': True, 'definition': d,
                'band_ids': [fields.Command.create({'band': b, 'min_score': lo_, 'max_score': hi_,
                                                    'client_text': texts[b], 'content_version': 'HR-HEXACO-1'})
                             for b, lo_, hi_ in BANDS5]}))
        factor_cmds.append(fields.Command.create({
            'code': ATTN, 'name': 'دقت پاسخ‌دهی', 'sequence': 999, 'scored': True, 'report_hidden': True,
            'definition': 'جمله‌های کنترلی؛ فقط برای سنجش دقت پاسخ‌دهی.',
            'band_ids': [fields.Command.create({'band': b, 'min_score': lo_, 'max_score': hi_, 'client_text': '',
                                                'content_version': 'HR-HEXACO-1'}) for b, lo_, hi_ in BANDS3]}))
        ver = self.env['ts.instrument.version'].sudo().with_context(ts_loader=True).create({
            'instrument_id': inst.id, 'contract_version': 'HR-HEXACO-1', 'content_hash': hashlib.sha256(content.encode()).hexdigest(),
            'locked': True, 'factor_ids': factor_cmds})
        fid = {f.code: f.id for f in ver.factor_ids}
        self.env['ts.instrument.item'].sudo().with_context(ts_loader=True).create([
            {'version_id': ver.id, 'factor_id': fid[f], 'sequence': s, 'text': t, 'reverse': r} for s, f, t, r in items])
        ver._validate_contract()
        inst.write({'current_version_id': ver.id, 'approved_at': fields.Datetime.now(),
                    'approved_by_id': self.env.ref('base.user_root').id,
                    'approval_note': 'Owner decision 2026-10-12: HR hiring mode = personality + timed tasks.'})
        try:
            with self.env.cr.savepoint():
                inst.action_publish()
        except (UserError, ValidationError) as e:
            _logger.warning('ts_hire: %s left unpublished: %s (%s)', HEXACO_CODE, e, ver.validation_report)
        return {'created': 1, 'items': len(items), 'valid': ver.validation_ok}
