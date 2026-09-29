import hashlib
import json
import logging

from odoo import api, fields, models
from odoo.tools.misc import file_path

from .attempt import split_interpretation

_logger = logging.getLogger(__name__)

APPROVAL_NOTE = (
    'تأیید مالک پلتفرم، ۱۴۰۵/۰۷/۰۷ (2026-09-29): مالکیت و حق استفاده، شواهد و کاربرد مجاز سنجه، '
    'قرارداد نمره‌گذاری نسخه‌دار و متون تفسیر شرکت‌کننده و متخصص برای انتشار در تلنت سرچ تأیید شد. '
    'منبع داده: سامانهٔ پیشین sepehrtherapy.ir (مدل‌های x_psy_*)، هم‌خوان با خروجی‌های بارگذاری‌شده توسط مالک.'
)
APPROVAL_VERSION = 'TS-OWNER-APPROVED-1405-07-07'
RIGHTS_NOTE = 'مجموعهٔ سنجه‌های EOT. استفاده در تلنت سرچ با تأیید مالک پلتفرم (۱۴۰۵/۰۷/۰۷).'
EVIDENCE_NOTE = (
    'قرارداد نمره‌گذاری S09-V1.2 (میانگین، نمره‌گذاری معکوس ۶−x، سه بازهٔ تفسیر) و متون تفسیر نسخهٔ '
    'CLINICAL-APPROVED-V1.0 از سامانهٔ منبع منتقل و با تأیید مالک پلتفرم منتشر شد. ضرایب پایایی، روایی '
    'و گروه هنجار در سامانهٔ منبع ثبت نشده و در گزارش‌ها ادعا نمی‌شود.'
)
LIMITATIONS = (
    'نتیجه توصیف پاسخ‌های شما در همین پرسشنامه است، نه تشخیص بالینی، برچسب شخصیتی یا مبنای تصمیم استخدامی. '
    'بازه‌های «کم»، «متوسط» و «زیاد» بر پایهٔ قرارداد نمره‌گذاری سنجه تعیین می‌شوند و گروه هنجار ندارند. '
    'برای تصمیم‌های مهم با متخصص مشورت کنید.'
)
CATEGORY_ORDER = ['خودشناسی', 'نارضایتی از زندگی', 'بیتابی روانی', 'استعدادیابی', 'مسائل شغلی',
                  'مشاوره ازدواج', 'مشکلات زناشویی', 'مسائل نوجوان', 'استعدادیابی کودک', 'مشکلات رفتاری کودک']


def _m2o(v):
    return v[0] if isinstance(v, (list, tuple)) and v else (v or False)


class TsInstrumentLoader(models.Model):
    _inherit = 'ts.instrument'

    @api.model
    def _ts_load_source(self):
        src = json.load(open(file_path('ts_assessment/data/source/psy_source.json')))
        meta = json.load(open(file_path('ts_assessment/data/source/workbook_meta.json')))
        xml = src['xmlids']
        owner = self.env.ref('base.user_admin')
        now = fields.Datetime.now()
        A = {a['id']: a for a in src['x_psy_assessment']}
        Q = {q['id']: q for q in src['survey.question']}
        contracts = {}
        for c in src['x_psy_scoring_contract']:
            contracts.setdefault(_m2o(c['x_assessment_id']), []).append(c)
        rules_by_factor = {_m2o(r['x_factor_id']): r for r in src['x_psy_factor_scoring_rule']}
        bands_by_rule = {}
        for t in src['x_psy_factor_threshold_rule']:
            bands_by_rule.setdefault(_m2o(t['x_rule_id']), []).append(t)
        factors_by_asm = {}
        for f in src['x_psy_factor']:
            factors_by_asm.setdefault(_m2o(f['x_assessment_id']), []).append(f)
        items_by_factor = {}
        for it in src['x_psy_assessment_item']:
            items_by_factor.setdefault(_m2o(it['x_factor_id']), []).append(it)

        stats = {'created': 0, 'versions': 0, 'unchanged': 0, 'published': 0, 'retired': 0}
        for aid, a in sorted(A.items(), key=lambda kv: kv[1]['x_code']):
            code = a['x_code']
            m = meta.get(code, {})
            active = [c for c in contracts.get(aid, []) if c.get('x_active')]
            contract = active[0] if len(active) == 1 else None
            # --- build the version payload (plain data) and its fingerprint
            f_payload = []
            for f in sorted(factors_by_asm.get(aid, []), key=lambda x: (x['x_code'], x['id'])):
                rule = rules_by_factor.get(f['id'])
                if rule and contract and _m2o(rule['x_contract_id']) != contract['id']:
                    rule = None
                bands = sorted(bands_by_rule.get(rule['id'], []) if rule else [], key=lambda b: b['x_min_score'])
                items = sorted(items_by_factor.get(f['id'], []), key=lambda i: (i['x_sequence'], int(i['x_source_question_id']), i['id']))
                f_payload.append({
                    'code': f['x_code'], 'name': f['x_name'], 'src': f['id'],
                    'rule_xmlid': xml.get('x_psy_factor_scoring_rule:%s' % rule['id']) if rule else False,
                    'bands': [{'band': b['x_band'].lower(), 'min': b['x_min_score'], 'max': b['x_max_score'],
                               'client': b.get('x_client_text') or '', 'therapist': b.get('x_therapist_text') or '',
                               'cv': b.get('x_content_version') or '', 'src': b['id'],
                               'by': (b.get('x_approved_by_user_id') or [0, ''])[1] if b.get('x_approved_by_user_id') else '',
                               'at': b.get('x_approved_at') or ''} for b in bands],
                    'items': [{'seq': i['x_sequence'], 'qid': int(i['x_source_question_id']),
                               'text': (Q[_m2o(i['x_question_id'])]['title'] or '').strip(),
                               'rev': bool(i['x_reverse']), 'dis': bool(i['x_disabled']), 'src': i['id'],
                               'qsrc': _m2o(i['x_question_id'])} for i in items],
                })
            fingerprint_basis = [(f['code'], [(b['band'], b['min'], b['max'],
                                               hashlib.md5(b['client'].encode()).hexdigest(),
                                               hashlib.md5(b['therapist'].encode()).hexdigest()) for b in f['bands']],
                                  [(i['qid'], i['seq'], i['text'], i['rev'], i['dis']) for i in f['items']])
                                 for f in f_payload]
            content_hash = hashlib.md5(json.dumps([contract and contract['x_version'], fingerprint_basis],
                                                  ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            inst = self.search([('code', '=', code)], limit=1)
            vals = {
                'name': a['x_name'], 'code': code, 'category': m.get('category') or False,
                'audience': m.get('audience') or 'adult',
                'sequence': (CATEGORY_ORDER.index(m['category']) * 100 if m.get('category') in CATEGORY_ORDER else 9000)
                            + int(code.split('_')[1]),
                'source_xmlid': xml.get('x_psy_assessment:%s' % aid), 'source_record_id': aid,
            }
            if not inst:
                inst = self.create(vals)
                stats['created'] += 1
            else:
                inst.write(vals)
            version = inst.version_ids.filtered(lambda v: v.content_hash == content_hash)[:1]
            if not version:
                version = self._ts_create_version(inst, contract, f_payload, content_hash, xml, owner, now)
                (inst.version_ids - version).with_context(ts_loader=True).write({'superseded': True})
                stats['versions'] += 1
            else:
                stats['unchanged'] += 1
            version._validate_contract()
            scored = version.factor_ids.filtered('scored')
            names = '، '.join(scored.mapped('name'))
            aud = inst.audience
            who = ('این پرسشنامه را والد یا مراقب دربارهٔ کودک تکمیل می‌کند.' if aud == 'child' else
                   'نوجوان با اطلاع و رضایت ولی پاسخ می‌دهد.' if aud == 'adolescent' else
                   'پاسخ‌دهنده خود شرکت‌کننده است.')
            upd = {'current_version_id': version.id, 'rights_note': RIGHTS_NOTE, 'evidence_note': EVIDENCE_NOTE,
                   'limitations': LIMITATIONS, 'approval_note': APPROVAL_NOTE}
            if inst.category and scored:
                upd['intended_use'] = ('کاربرد: خودشناسی و گفت‌وگوی مشاوره‌ای در حوزهٔ «%s». این سنجه %s بُعد را توصیف می‌کند: %s. %s '
                                       'این سنجه برای تشخیص بالینی یا تصمیم استخدامی به کار نمی‌رود.'
                                       % (inst.category, len(scored), names, who))
            if not inst.approved_at:
                upd.update({'approved_by_id': owner.id, 'approved_at': now})
            inst.write(upd)
            if contract and version.validation_ok and inst.state in ('draft', 'approved', 'published'):
                if inst.state != 'published':
                    inst.action_publish()
                stats['published'] += 1
            elif not contract:
                if inst.state != 'retired':
                    inst.state = 'retired'
                stats['retired'] += 1
        _logger.info('Talent Search instruments loaded: %s', stats)
        return stats

    def _ts_create_version(self, inst, contract, f_payload, content_hash, xml, owner, now):
        Version = self.env['ts.instrument.version'].with_context(ts_loader=True)
        version = Version.create({
            'instrument_id': inst.id,
            'contract_version': contract['x_version'] if contract else 'NO-ACTIVE-CONTRACT',
            'content_hash': content_hash,
            'source_contract_xmlid': xml.get('x_psy_scoring_contract:%s' % contract['id']) if contract else False,
            'source_contract_id': contract['id'] if contract else 0,
        })
        Factor, Band, Item = self.env['ts.instrument.factor'], self.env['ts.instrument.band'], self.env['ts.instrument.item']
        for seq, f in enumerate(f_payload):
            definition = ''
            if f['bands']:
                for head, body in split_interpretation(f['bands'][0]['client']):
                    if head == 'این بُعد چه چیزی را توصیف می‌کند':
                        definition = body
                        break
            fac = Factor.create({'version_id': version.id, 'code': f['code'], 'name': f['name'], 'sequence': seq,
                                 'definition': definition, 'scored': bool(f['bands']),
                                 'source_xmlid': xml.get('x_psy_factor:%s' % f['src']), 'source_rule_xmlid': f['rule_xmlid']})
            for b in f['bands']:
                Band.create({'factor_id': fac.id, 'band': b['band'], 'min_score': b['min'], 'max_score': b['max'],
                             'client_text': b['client'], 'therapist_text': b['therapist'],
                             'content_version': '%s + %s' % (b['cv'], APPROVAL_VERSION),
                             'source_approved_by': b['by'], 'source_approved_at': b['at'],
                             'approved_by_id': owner.id, 'approved_at': now,
                             'source_xmlid': xml.get('x_psy_factor_threshold_rule:%s' % b['src'])})
            Item.create([{'version_id': version.id, 'factor_id': fac.id, 'sequence': i['seq'],
                          'source_question_id': i['qid'], 'text': i['text'], 'reverse': i['rev'], 'disabled': i['dis'],
                          'source_xmlid': xml.get('x_psy_assessment_item:%s' % i['src']),
                          'source_question_xmlid': 'survey.question:%s' % i['qsrc']} for i in f['items']])
        return version
