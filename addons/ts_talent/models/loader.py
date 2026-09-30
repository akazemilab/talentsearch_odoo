import hashlib
import json
import logging

from odoo import api, fields, models
from odoo.tools import file_path

from .engine_matrix import COMPOSITES, INTEL, ITEM_COUNT, NAMES, SCALES

_logger = logging.getLogger(__name__)

CODE = 'TALENT-INV-15'
CONTRACT_VERSION = '1.0'
APPROVAL_NOTE = 'طرح و گزارش این سنجه با تأیید مالک تلنت سرچ (۱۴۰۵/۰۷/۰۷) ساخته شد.'
INTENDED_USE = ('کاربرد: خودشناسی. شما زمینه‌هایی را که خودتان می‌نویسید (مثلاً یک درس، هنر، ورزش، مهارت یا شغل) با ۱۵ جمله می‌سنجید؛ '
                'گزارش، برداشت شما از پنج توانایی بنیادین (سه هوش و دو کنش) را در هر زمینه و مقایسهٔ زمینه‌های خودتان با هم نشان می‌دهد. '
                'پاسخ‌دهنده خود شرکت‌کننده است. این سنجه برای تشخیص بالینی، تصمیم استخدامی یا برچسب «تیزهوش» به کار نمی‌رود.')
LIMITATIONS = ('نمره‌ها برداشت شما از خودتان هستند و فقط زمینه‌ها و توانایی‌های خودِ شما را با هم مقایسه می‌کنند؛ با دیگران مقایسه نمی‌شوند. '
               'برای این فهرست، هنجار، نقطهٔ برش یا پایایی گزارش‌شده‌ای در دست نیست و هر توانایی با سه جمله سنجیده می‌شود. '
               'کتاب پنج بُعد را برای استعداد لازم می‌داند و این فهرست فقط دو بُعد را می‌سنجد: توانایی‌های شناختی (سه هوش) و رفتاری (دو کنش).')
RIGHTS_NOTE = ('شیوهٔ نمره‌گذاری و تفسیر از کتاب «آموزش و پرورش برای استعداد و تیزهوشی» (دکتر ناصرالدّین کاظمی حقیقی) است و متن ۱۵ جمله عیناً از فرم منتشرشدهٔ '
               'فهرست تعاملی استعداد آمده است. استفاده در تلنت سرچ به دستور مالک این سامانه (۱۴۰۵/۰۷/۰۷) انجام شده است.')
EVIDENCE_NOTE = ('نمره‌گذاری: میانگین سه جمله برای هر توانایی در مقیاس ۲۰ تا ۱۰۰؛ ترکیب‌ها میانگین توانایی‌های سازندهٔ خود هستند و تفسیر در هفت سطح، '
                 'طبق فصل «تلفیق در مکتب تعاملی» کتاب است. برای این ۱۵ جمله در کتاب هنجار یا پایایی گزارش نشده است.')
FIELD_GUIDANCE = ('زمینه یعنی موضوعی که به آن علاقه یا استعداد دارید: یک درس، هنر، ورزش، مهارت یا شغل. '
                  'هر بار یک زمینه را با کلمات خودتان بنویسید.')


def _read(name):
    with open(file_path('ts_talent/data/%s' % name), encoding='utf-8') as fh:
        return json.load(fh)


class TsInstrumentTalent(models.Model):
    _inherit = 'ts.instrument'

    @api.model
    def _ts_load_talent(self):
        items = _read('talent_items.json')
        texts = _read('talent_texts.json')
        assert len(items) == ITEM_COUNT, 'talent_items.json must hold %d statements' % ITEM_COUNT
        content = {'items': items, 'scales': texts['scales'], 'composites': COMPOSITES, 'names': NAMES,
                   'limits': [2, 3, 8], 'gap': 10}
        content_hash = hashlib.md5(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        owner = self.env.ref('base.user_admin')
        now = fields.Datetime.now()
        inst = self.search([('code', '=', CODE)], limit=1)
        vals = {'name': 'فهرست تعاملی استعداد', 'code': CODE, 'category': 'استعدادیابی', 'audience': 'adult',
                'purpose': 'personal', 'sequence': 1}
        if inst:
            inst.write(vals)
        else:
            inst = self.create(vals)
        version = inst.version_ids.filtered(lambda v: v.content_hash == content_hash)[:1]
        created = False
        if not version:
            n = len(inst.version_ids)
            version = self._ts_create_talent_version(inst, content, texts, content_hash,
                                                     CONTRACT_VERSION if not n else '1.%d' % n)
            (inst.version_ids - version).with_context(ts_loader=True).write({'superseded': True})
            created = True
        if version.field_default != 4:  # entekhab-1405: suggest 4 fields (data: median 4, 18% used 8)
            version.with_context(ts_loader=True).write({'field_default': 4})
        version._validate_contract()
        upd = {'current_version_id': version.id, 'intended_use': INTENDED_USE, 'limitations': LIMITATIONS,
               'rights_note': RIGHTS_NOTE, 'evidence_note': EVIDENCE_NOTE, 'approval_note': APPROVAL_NOTE}
        if not inst.approved_at:
            upd.update({'approved_by_id': owner.id, 'approved_at': now})
        inst.write(upd)
        if version.validation_ok and inst.state in ('draft', 'approved'):
            inst.action_publish()
        self._ts_refresh_titles()
        _logger.info('Talent inventory loaded: version=%s created=%s valid=%s state=%s',
                     version.contract_version, created, version.validation_ok, inst.state)
        return inst

    def _ts_create_talent_version(self, inst, content, texts, content_hash, contract_version):
        Version = self.env['ts.instrument.version'].with_context(ts_loader=True)
        version = Version.create({
            'instrument_id': inst.id, 'contract_version': contract_version, 'content_hash': content_hash,
            'engine_version': 'TS-MATRIX-1.0', 'mode': 'matrix', 'scale_min': 1, 'scale_max': 5,
            'reverse_rule': 'none', 'aggregation': 'scale = sum of 3 items / 15 x 100; composite = mean of its scales',
            'missing_rule': 'every named field needs exactly 15 answers; 2 to 8 fields',
            'field_min': 2, 'field_default': 4, 'field_max': 8, 'noise_gap': 10.0, 'field_guidance': FIELD_GUIDANCE,
        })
        Factor, Item = self.env['ts.instrument.factor'], self.env['ts.instrument.item']
        factors = {}
        for seq, code in enumerate(SCALES):
            factors[code] = Factor.create({
                'version_id': version.id, 'code': code, 'name': NAMES[code], 'sequence': (seq + 1) * 10,
                'definition': texts['scales'][code]['definition'], 'scored': False, 'kind': 'scale',
                'group': 'intelligence' if code in INTEL else 'action'})
        for seq, (code, members) in enumerate(COMPOSITES.items()):
            Factor.create({
                'version_id': version.id, 'code': code, 'name': NAMES[code], 'sequence': 100 + seq * 10,
                'definition': (texts['composites'].get(code) or {}).get('definition') or False,
                'scored': False, 'kind': 'composite', 'group': 'none', 'composite_of': ','.join(members)})
        Item.create([{'version_id': version.id, 'factor_id': factors[SCALES[i % 5]].id, 'sequence': i + 1,
                      'source_question_id': i + 1, 'text': text, 'reverse': False, 'disabled': False}
                     for i, text in enumerate(content['items'])])
        return version
