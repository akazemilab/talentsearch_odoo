import functools
import hashlib
import json
import logging
import os

from odoo import api, fields, models

from . import jobfit as J

_logger = logging.getLogger(__name__)
DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'onet_hr.json')
CREDIT = ('اطلاعات شغلی از پایگاه دادهٔ O*NET نسخهٔ ۳۱٫۰ وزارت کار آمریکا (USDOL/ETA) با مجوز CC BY ۴٫۰؛ '
          'عنوان‌ها و شرح‌های فارسی و قواعد تناسب از استعدادیاب است و USDOL/ETA آن‌ها را تأیید یا آزمون نکرده است.')

_FA_FIX = str.maketrans({'ي': 'ی', 'ك': 'ک', '‌': ' ', 'ۀ': 'ه', 'ة': 'ه', 'أ': 'ا', 'إ': 'ا'})


def norm_fa(s):
    """Search key: Arabic/Persian letter variants unified, ZWNJ as space, lower-cased Latin."""
    return ' '.join((s or '').translate(_FA_FIX).lower().split())


@functools.lru_cache(maxsize=1)
def _data():
    with open(DATA, encoding='utf-8') as fh:
        return json.load(fh)


def reference():
    return J.Reference(_data()['lv_sorted'])


class TsOnetOccupation(models.Model):
    _name = 'ts.onet.occupation'
    _description = 'شغل O*NET'
    _order = 'title_fa, code'
    _rec_name = 'title_fa'

    code = fields.Char('کد O*NET-SOC', required=True, index=True)
    title_en = fields.Char('عنوان انگلیسی', required=True)
    title_fa = fields.Char('عنوان فارسی', required=True)
    desc_fa = fields.Text('شرح کوتاه')
    job_zone = fields.Integer('سطح آمادگی (Job Zone)')
    profile_json = fields.Text('نیازهای شغل (JSON)', readonly=True)
    has_styles = fields.Boolean('دادهٔ سبک کاری', readonly=True)
    has_abilities = fields.Boolean('دادهٔ توانایی', readonly=True)
    search_text = fields.Char(compute='_compute_search_text', store=True, index=True)
    shipped_title_fa = fields.Char(readonly=True, help='Persian title as last shipped (a different current title = edited by hand)')
    shipped_desc_fa = fields.Text(readonly=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('unique(code)', 'کد شغل باید یکتا باشد.')

    @api.depends('title_fa', 'title_en', 'code')
    def _compute_search_text(self):
        for o in self:
            o.search_text = norm_fa(' '.join(filter(None, [o.title_fa, o.title_en, o.code])))

    # ------------------------------------------------------------------ data
    def ts_profile(self):
        """The O*NET side for JOBFIT: {'code', 'styles', 'ab', 'clinic', 'jz'}."""
        self.ensure_one()
        p = json.loads(self.profile_json or '{}')
        p['code'] = self.code
        p['jz'] = self.job_zone
        return p

    def ts_requirements(self, overrides=None):
        self.ensure_one()
        return J.requirements(self.ts_profile(), reference(), overrides)

    def ts_jobfit(self, facets=None, abilities=None, overrides=None):
        self.ensure_one()
        return J.jobfit(self.ts_profile(), reference(), facets=facets, abilities=abilities, overrides=overrides)

    @api.model
    def ts_search(self, q, limit=12):
        """Persian/English title or code search; every word must match (order free)."""
        words = norm_fa(q).split()
        if not words:
            return self.browse()
        domain = [('search_text', 'ilike', w) for w in words[:6]]
        return self.search(domain, limit=limit, order='title_fa')

    @api.model
    def _ts_load(self):
        """Upsert the catalogue from data/onet_hr.json. A title/description edited by hand (differs from the shipped
        text of the previous load) is kept; requirements always follow the data file."""
        with open(DATA, 'rb') as fh:
            raw = fh.read()
        digest = hashlib.sha256(raw).hexdigest()
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_str('ts_onet.data_hash') == digest and self.with_context(active_test=False).search_count([]):
            return {'skipped': True}
        data = json.loads(raw.decode('utf-8'))
        _data.cache_clear()
        existing = {o.code: o for o in self.with_context(active_test=False).search([])}
        stats = {'created': 0, 'updated': 0, 'kept_manual': 0}
        for o in data['occupations']:
            prof = json.dumps({'styles': o['styles'], 'ab': o['ab'], 'clinic': o['clinic']}, ensure_ascii=False,
                              sort_keys=True, separators=(',', ':'))
            vals = {'title_en': o['en'], 'job_zone': o['jz'] or 0, 'profile_json': prof,
                    'has_styles': bool(o['styles']), 'has_abilities': bool(o['ab'])}
            vals.update({'shipped_title_fa': o['fa'], 'shipped_desc_fa': o['desc']})
            rec = existing.get(o['code'])
            if not rec:
                vals.update({'code': o['code'], 'title_fa': o['fa'], 'desc_fa': o['desc']})
                self.create(vals)
                stats['created'] += 1
                continue
            if not rec.shipped_title_fa or (rec.title_fa == rec.shipped_title_fa and (rec.desc_fa or '') == (rec.shipped_desc_fa or '')):
                vals.update({'title_fa': o['fa'], 'desc_fa': o['desc']})
            else:
                stats['kept_manual'] += 1
            rec.write(vals)
            stats['updated'] += 1
        ICP.set_str('ts_onet.data_hash', digest)
        _logger.info('ts_onet catalogue load: %s', stats)
        return stats
