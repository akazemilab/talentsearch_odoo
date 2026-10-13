import hashlib
import json
import logging

from odoo import api, fields, models
from odoo.tools import file_path

from odoo.addons.ts_assessment.models.loader import CONTENT_SCHEMA, scoring_fingerprint
from .engine_matrix import COMPOSITES, INTEL, ITEM_COUNT, NAMES, SCALES
from .report import LEVEL_GLOSS, PROGRAM_PLAIN
from .text import PLACEHOLDER

_logger = logging.getLogger(__name__)

CODE = 'TALENT-INV-15'
CONTRACT_VERSION = '1.0'
APPROVAL_NOTE = 'طرح و گزارش این سنجه با تأیید مالک استعدادیاب (۱۴۰۵/۰۷/۰۷) ساخته شد.'
INTENDED_USE = ('کاربرد: خودشناسی. شما زمینه‌هایی را که خودتان می‌نویسید (مثلاً یک درس، هنر، ورزش، مهارت یا شغل) با ۱۵ جمله می‌سنجید؛ '
                'گزارش، برداشت شما از پنج توانایی بنیادین (سه هوش و دو کنش) را در هر زمینه و مقایسهٔ زمینه‌های خودتان با هم نشان می‌دهد. '
                'پاسخ‌دهنده خود شرکت‌کننده است. این سنجه برای تشخیص، تصمیم استخدامی یا برچسب «تیزهوش» به کار نمی‌رود.')
LIMITATIONS = ('نمره‌ها برداشت شما از خودتان هستند و فقط زمینه‌ها و توانایی‌های خودِ شما را با هم مقایسه می‌کنند؛ با دیگران مقایسه نمی‌شوند. '
               'برای این فهرست، هنجار، نقطهٔ برش یا پایایی گزارش‌شده‌ای در دست نیست و هر توانایی با سه جمله سنجیده می‌شود. '
               'کتاب پنج بُعد را برای استعداد لازم می‌داند و این فهرست فقط دو بُعد را می‌سنجد: توانایی‌های شناختی (سه هوش) و رفتاری (دو کنش).')
# The intended use in the student's register («تو»); shown on the detail page instead of INTENDED_USE (UX audit T7 P16-3).
INTENDED_USE_TU = ('کاربرد: خودشناسی. زمینه‌هایی را که خودت می‌نویسی (مثلاً یک درس، هنر، ورزش، مهارت یا شغل) با ۱۵ جمله می‌سنجی؛ '
                   'گزارش، برداشت خودت از پنج توانایی بنیادین (سه هوش و دو کنش) را در هر زمینه و مقایسهٔ زمینه‌های خودت با هم نشان می‌دهد. '
                   'به جمله‌ها خودت پاسخ می‌دهی. این سنجه برای تشخیص، تصمیم استخدامی یا برچسب «تیزهوش» به کار نمی‌رود.')
# The same limits in the student's register («تو»); shown instead of LIMITATIONS in a «تو» report (UX audit T7 P10-2).
LIMITATIONS_TU = ('نمره‌ها برداشت خودت از خودت هستند و فقط زمینه‌ها و توانایی‌های خودت را با هم مقایسه می‌کنند؛ با دیگران مقایسه نمی‌شوند. '
                  'برای این فهرست، هنجار، نقطهٔ برش یا پایایی گزارش‌شده‌ای در دست نیست و هر توانایی با سه جمله سنجیده می‌شود. '
                  'کتاب پنج بُعد را برای استعداد لازم می‌داند و این فهرست فقط دو بُعد را می‌سنجد: توانایی‌های شناختی (سه هوش) و رفتاری (دو کنش).')
RIGHTS_NOTE = ('شیوهٔ نمره‌گذاری و تفسیر از کتاب «آموزش و پرورش برای استعداد و تیزهوشی» (دکتر ناصرالدّین کاظمی حقیقی) است و متن ۱۵ جمله عیناً از فرم منتشرشدهٔ '
               'فهرست تعاملی استعداد آمده است. استفاده در استعدادیاب به دستور مالک این سامانه (۱۴۰۵/۰۷/۰۷) انجام شده است.')
EVIDENCE_NOTE = ('نمره‌گذاری: میانگین سه جمله برای هر توانایی در مقیاس ۲۰ تا ۱۰۰؛ ترکیب‌ها میانگین توانایی‌های سازندهٔ خود هستند و تفسیر در هفت سطح، '
                 'طبق فصل «تلفیق در مکتب تعاملی» کتاب است. برای این ۱۵ جمله در کتاب هنجار یا پایایی گزارش نشده است.')
FIELD_GUIDANCE = ('زمینه یعنی موضوعی که به آن علاقه یا استعداد دارید: یک درس، هنر، ورزش، مهارت یا شغل. '
                  'هر بار یک زمینه را با کلمات خودتان بنویسید.')


def _read(name):
    with open(file_path('ts_talent/data/%s' % name), encoding='utf-8') as fh:
        return json.load(fh)


def _hash(content):
    return hashlib.md5(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _txt(v):
    return v.strip() if isinstance(v, str) else ''


def _same_placeholders(book, new):
    """A rewritten statement keeps the field-name slots of the book statement: the same «این زمینه/قلمرو/عرصه» in the
    same order (so «این زمینه» stays wherever the book has it and the field name is still inserted)."""
    return [m.group(0) for m in PLACEHOLDER.finditer(new)] == [m.group(0) for m in PLACEHOLDER.finditer(book)]


class TsInstrumentTalent(models.Model):
    _inherit = 'ts.instrument'

    @api.model
    def _ts_talent_overlay(self, items, stats):
        """Content v2 of TALENT-INV-15 (data/content_v2/TALENT-INV-15.json, written by tools/content/ts_content_export.py
        --talent): -> None (book content) or {'items', 'v2'} where v2 holds every new text, normalised. Applies only to an
        approved file while ts_assessment.content_v2 != '0'; empty fields keep the book/default text. A statement that
        loses its field-name slot, an unknown code or a statement in the wrong place refuses the whole file."""
        data = self._ts_content_file(CODE, 'ts_talent')
        if not data or data.get('status') != 'approved' or not self._ts_content_enabled():
            return None
        problems = []
        if data.get('_unreadable'):
            problems.append('unreadable JSON')
        if data.get('schema') not in (None, CONTENT_SCHEMA) or data.get('instrument') not in (None, CODE):
            problems.append('schema/instrument %r/%r' % (data.get('schema'), data.get('instrument')))
        if not _txt(data.get('content_version')):
            problems.append('no content_version')
        new_items = list(items)
        seen = set()
        for st in data.get('statements') or []:
            text, n = _txt(st.get('text')), st.get('n')
            if not text:
                continue
            if not isinstance(n, int) or not 1 <= n <= ITEM_COUNT or n in seen or st.get('scale') not in (None, SCALES[(n - 1) % 5]):
                problems.append('statement %r (scale %r) out of place' % (n, st.get('scale')))
                continue
            seen.add(n)
            if not _same_placeholders(items[n - 1], text) or ('این زمینه' in items[n - 1] and 'این زمینه' not in text):
                problems.append('statement %d lost «این زمینه»' % n)
                continue
            new_items[n - 1] = text
        scales, comps = {}, {}
        for sc in data.get('scales') or []:
            if sc.get('code') not in SCALES or sc['code'] in scales:
                problems.append('scale %r' % sc.get('code'))
                continue
            scales[sc['code']] = {'name': _txt(sc.get('name')), 'definition': _txt(sc.get('definition')),
                                  'plain': _txt(sc.get('plain'))}
        for co in data.get('composites') or []:
            code = co.get('code')
            if code not in COMPOSITES or code in comps or (co.get('parts') and list(co['parts']) != list(COMPOSITES[code])):
                problems.append('composite %r' % code)
                continue
            comps[code] = {'name': _txt(co.get('name')), 'definition': _txt(co.get('definition'))}
        levels, titles = {}, {}
        for lv in data.get('levels') or []:
            if lv.get('key') not in LEVEL_GLOSS:
                problems.append('level %r' % lv.get('key'))
                continue
            levels[lv['key']], titles[lv['key']] = _txt(lv.get('gloss')), _txt(lv.get('title'))
        glosses = data.get('glosses') or {}
        prefixes = dict(PROGRAM_PLAIN)
        programs = {}
        for pr in glosses.get('programs') or []:
            if pr.get('prefix') not in prefixes:
                problems.append('programme prefix %r' % pr.get('prefix'))
                continue
            programs[pr['prefix']] = _txt(pr.get('text'))
        if problems:
            _logger.warning('content v2 %s refused, book content kept: %s', CODE, '; '.join(problems[:8]))
            stats['content_errors'] += 1
            return None
        v2 = {
            'content_version': _txt(data['content_version']), 'summary': _txt(data.get('summary')),
            'scales': {c: v for c, v in scales.items() if any(v.values())},
            'composites': {c: v for c, v in comps.items() if any(v.values())},
            'plain': {c: v['plain'] for c, v in scales.items() if v['plain']},
            'programs': {k: v for k, v in programs.items() if v},
            'levels': {k: v for k, v in levels.items() if v},
            'level_titles': {k: v for k, v in titles.items() if v},
            'field_guidance': _txt((glosses.get('field_guidance') or {}).get('text')),
        }
        if new_items == list(items) and not any(v for k, v in v2.items() if k != 'content_version'):
            return None     # an approved file without a single new text changes nothing
        return {'items': new_items, 'v2': v2}

    @api.model
    def _ts_load_talent(self):
        items = _read('talent_items.json')
        texts = _read('talent_texts.json')
        assert len(items) == ITEM_COUNT, 'talent_items.json must hold %d statements' % ITEM_COUNT
        stats = {'content_errors': 0}
        content = {'items': items, 'scales': texts['scales'], 'composites': COMPOSITES, 'names': NAMES,
                   'limits': [2, 3, 8], 'gap': 10}
        v1_hash = _hash(content)      # unchanged since 1.0: book content keeps its version
        overlay = self._ts_talent_overlay(items, stats)
        if overlay:
            content = dict(content, items=overlay['items'], content_v2=overlay['v2'])
        content_hash = _hash(content) if overlay else v1_hash
        owner = self.env.ref('base.user_admin')
        now = fields.Datetime.now()
        inst = self.search([('code', '=', CODE)], limit=1)
        vals = {'name': 'فهرست تعاملی استعداد', 'code': CODE, 'category': 'استعدادیابی', 'audience': 'adult',
                'purpose': 'personal', 'sequence': 1}
        if inst:
            inst.write(vals)
        else:
            inst = self.create(vals)
        prev = inst.current_version_id

        def find_or_create(h, cont):
            v = inst.version_ids.filtered(lambda v: v.content_hash == h)[:1]
            if v:
                return v, False
            n = len(inst.version_ids)
            return self._ts_create_talent_version(inst, cont, texts, h, CONTRACT_VERSION if not n else '1.%d' % n), True

        version, created = find_or_create(content_hash, content)
        if overlay and version != prev:
            ref = prev or find_or_create(v1_hash, dict(content, items=items, content_v2=None))[0]
            if scoring_fingerprint(version) != scoring_fingerprint(ref):
                _logger.error('content v2 %s: scoring contract of version %s differs from version %s; book content kept',
                              CODE, version.id, ref.id)
                stats['content_errors'] += 1
                overlay = None
                version, created = find_or_create(v1_hash, dict(content, items=items, content_v2=None))
        if version.field_default != 4:  # entekhab-1405: suggest 4 fields (data: median 4, 18% used 8)
            version.with_context(ts_loader=True).write({'field_default': 4})
        version._validate_contract()
        moved = inst._ts_set_current(version)
        upd = {'intended_use': INTENDED_USE, 'limitations': LIMITATIONS,
               'rights_note': RIGHTS_NOTE, 'evidence_note': EVIDENCE_NOTE, 'approval_note': APPROVAL_NOTE,
               'summary': (overlay and overlay['v2']['summary']) or False}
        if not inst.approved_at:
            upd.update({'approved_by_id': owner.id, 'approved_at': now})
        inst.write(upd)
        if version.validation_ok and inst.state in ('draft', 'approved'):
            inst.action_publish()
        self._ts_refresh_titles()
        _logger.info('Talent inventory loaded: version=%s created=%s valid=%s state=%s content=%s errors=%s moved=%s',
                     version.contract_version, created, version.validation_ok, inst.state,
                     version.content_version or 'book', stats['content_errors'], moved)
        return inst

    def _ts_create_talent_version(self, inst, content, texts, content_hash, contract_version):
        """content: the hashed content; with content['content_v2'] (approved content v2) the new texts override the book
        definitions, names, field guidance and statements, and the report glosses are stored in report_texts."""
        v2 = content.get('content_v2') or {}
        sc2, co2 = v2.get('scales') or {}, v2.get('composites') or {}

        def name_of(code):
            return (sc2.get(code) or co2.get(code) or {}).get('name') or NAMES[code]
        Version = self.env['ts.instrument.version'].with_context(ts_loader=True)
        version = Version.create({
            'content_version': v2.get('content_version') or False,
            'report_texts': {k: v2[k] for k in ('plain', 'programs', 'levels', 'level_titles') if v2.get(k)} or False,
            'instrument_id': inst.id, 'contract_version': contract_version, 'content_hash': content_hash,
            'engine_version': 'TS-MATRIX-1.0', 'mode': 'matrix', 'scale_min': 1, 'scale_max': 5,
            'reverse_rule': 'none', 'aggregation': 'scale = sum of 3 items / 15 x 100; composite = mean of its scales',
            'missing_rule': 'every named field needs exactly 15 answers; 2 to 8 fields',
            'field_min': 2, 'field_default': 4, 'field_max': 8, 'noise_gap': 10.0,
            'field_guidance': v2.get('field_guidance') or FIELD_GUIDANCE,
        })
        Factor, Item = self.env['ts.instrument.factor'], self.env['ts.instrument.item']
        factors = {}
        for seq, code in enumerate(SCALES):
            factors[code] = Factor.create({
                'version_id': version.id, 'code': code, 'name': name_of(code), 'sequence': (seq + 1) * 10,
                'definition': (sc2.get(code) or {}).get('definition') or texts['scales'][code]['definition'],
                'scored': False, 'kind': 'scale',
                'group': 'intelligence' if code in INTEL else 'action'})
        for seq, (code, members) in enumerate(COMPOSITES.items()):
            Factor.create({
                'version_id': version.id, 'code': code, 'name': name_of(code), 'sequence': 100 + seq * 10,
                'definition': ((co2.get(code) or {}).get('definition')
                               or (texts['composites'].get(code) or {}).get('definition') or False),
                'scored': False, 'kind': 'composite', 'group': 'none', 'composite_of': ','.join(members)})
        Item.create([{'version_id': version.id, 'factor_id': factors[SCALES[i % 5]].id, 'sequence': i + 1,
                      'source_question_id': i + 1, 'text': text, 'reverse': False, 'disabled': False}
                     for i, text in enumerate(content['items'])])
        return version
