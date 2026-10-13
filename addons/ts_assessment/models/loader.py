import copy
import hashlib
import json
import logging

from odoo import api, fields, models
from odoo.tools.misc import file_path

from .attempt import DEF_HEADING, fa_digits, split_interpretation
from .engine import contract_fingerprint, contract_from_version

_logger = logging.getLogger(__name__)

APPROVAL_NOTE = (
    'تأیید مالک پلتفرم، ۱۴۰۵/۰۷/۰۷ (2026-09-29): مالکیت و حق استفاده، شواهد و کاربرد مجاز سنجه، '
    'قرارداد نمره‌گذاری نسخه‌دار و متون تفسیر شرکت‌کننده و مشاور برای انتشار در استعدادیاب تأیید شد. '
    'منبع داده: سامانهٔ پیشین sepehrtherapy.ir (مدل‌های x_psy_*)، هم‌خوان با خروجی‌های بارگذاری‌شده توسط مالک.'
)
APPROVAL_VERSION = 'TS-OWNER-APPROVED-1405-07-07'
# Owner rule (TS-OWNER-APPROVED-1405-07-07): categories an employment workspace may
# use - adult talent, self-knowledge and work instruments. Every mental-health
# category (and every child/adolescent instrument) stays out of hiring.
EMPLOYMENT_CATEGORIES = ('استعدادیابی', 'خودشناسی', 'مسائل شغلی')
RIGHTS_NOTE = 'مجموعهٔ سنجه‌های EOT. استفاده در استعدادیاب با تأیید مالک پلتفرم (۱۴۰۵/۰۷/۰۷).'
EVIDENCE_NOTE = (
    'قرارداد نمره‌گذاری S09-V1.2 (میانگین، نمره‌گذاری معکوس ۶−x، سه بازهٔ تفسیر) و متون تفسیر نسخهٔ '
    'CLINICAL-APPROVED-V1.0 از سامانهٔ منبع منتقل و با تأیید مالک پلتفرم منتشر شد. ضرایب پایایی، روایی '
    'و گروه هنجار در سامانهٔ منبع ثبت نشده و در گزارش‌ها ادعا نمی‌شود.'
)
LIMITATIONS = (
    'نتیجه توصیف پاسخ‌های شما در همین پرسشنامه است، نه تشخیص، برچسب شخصیتی یا مبنای تصمیم استخدامی. '
    'بازه‌های «کم»، «متوسط» و «زیاد» بر پایهٔ قرارداد نمره‌گذاری سنجه تعیین می‌شوند و گروه هنجار ندارند. '
    'برای تصمیم‌های مهم با متخصص مشورت کنید.'
)
# Content v2 (owner decision 2026-10-13): data/content_v2/<code>.json, schema ts-content/2, replaces the report texts
# (never items, bands or scoring) when status == approved and ir.config_parameter ts_assessment.content_v2 != '0'.
CONTENT_SCHEMA = 'ts-content/2'
CONTENT_PARAM = 'ts_assessment.content_v2'
CATEGORY_ORDER = ['خودشناسی', 'نارضایتی از زندگی', 'بیتابی روانی', 'استعدادیابی', 'مسائل شغلی',
                  'مشاوره ازدواج', 'مشکلات زناشویی', 'مسائل نوجوان', 'استعدادیابی کودک', 'مشکلات رفتاری کودک']


def _m2o(v):
    return v[0] if isinstance(v, (list, tuple)) and v else (v or False)


def _nonempty(v):
    return isinstance(v, str) and bool(v.strip())


def _talk_list(v):
    if isinstance(v, str):
        v = v.splitlines()
    return [x.strip() for x in (v or []) if isinstance(x, str) and x.strip()]


def _payload_hash(contract, f_payload, overlay_fp=None):
    """The version fingerprint. overlay_fp is appended only when a content v2 overlay is applied, so the hash of a
    book-text (v1) version is byte-identical to the one stored before content v2 existed."""
    basis = [(f['code'], [(b['band'], b['min'], b['max'],
                           hashlib.md5(b['client'].encode()).hexdigest(),
                           hashlib.md5(b['therapist'].encode()).hexdigest()) for b in f['bands']],
              [(i['qid'], i['seq'], i['text'], i['rev'], i['dis']) for i in f['items']])
             for f in f_payload]
    parts = [contract and contract['x_version'], basis]
    if overlay_fp:
        parts.append(overlay_fp)
    return hashlib.md5(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def scoring_fingerprint(version):
    """Engine contract of a version with item ids replaced by the source question id (qid): equal for two versions
    that score every answer set identically, whatever their texts."""
    c = contract_from_version(version)
    qid = {i.id: i.source_question_id for i in version.item_ids}
    c['items'] = sorted(({**it, 'id': qid[it['id']]} for it in c['items']), key=lambda it: it['id'])
    c['factors'] = sorted(({'code': f['code'], 'bands': sorted(f['bands'], key=lambda b: (b['min'], b['band']))}
                           for f in c['factors']), key=lambda f: f['code'])
    return contract_fingerprint(c)


class TsInstrumentLoader(models.Model):
    _inherit = 'ts.instrument'

    # ------------------------------------------------------------------ content v2
    @api.model
    def _ts_content_enabled(self):
        ICP = self.env['ir.config_parameter'].sudo()
        val = ICP.get_str(CONTENT_PARAM) if hasattr(ICP, 'get_str') else ICP.get_param(CONTENT_PARAM)
        return (val or '').strip() != '0'

    @api.model
    def _ts_content_file(self, code, module='ts_assessment'):
        """The parsed content v2 file of an instrument, or None. Tests pass {code: data} in the context key
        ts_content_v2_files instead of writing files into the module."""
        override = self.env.context.get('ts_content_v2_files')
        if override is not None and code in override:
            return override[code]
        try:
            path = file_path('%s/data/content_v2/%s.json' % (module, code))
        except (FileNotFoundError, ValueError):
            return None
        try:
            with open(path, encoding='utf-8') as fh:
                return json.load(fh)
        except (OSError, ValueError) as e:
            _logger.warning('content v2 %s: unreadable file (%s); book texts kept', code, e)
            return {'status': 'approved', '_unreadable': True}

    @api.model
    def _ts_content_overlay(self, code, f_payload, stats=None):
        """-> overlay dict or None. Applies only to an approved file while ts_assessment.content_v2 != '0'. The file must
        cover exactly the payload's scored (factor code, band) pairs, each factor with a definition and each band with a
        participant and a counselor text; any mismatch keeps the instrument on the book texts (warning, content_errors)."""
        data = self._ts_content_file(code)
        if not data or data.get('status') != 'approved' or not self._ts_content_enabled():
            return None
        problems = []
        if data.get('_unreadable'):
            problems.append('unreadable JSON')
        if data.get('schema') not in (None, CONTENT_SCHEMA):
            problems.append('schema %r' % data.get('schema'))
        if data.get('instrument') not in (None, code):
            problems.append('instrument %r' % data.get('instrument'))
        if not _nonempty(data.get('content_version')):
            problems.append('no content_version')
        want = {(f['code'], b['band']) for f in f_payload for b in f['bands']}
        got, factors = set(), {}
        for f in data.get('factors') or []:
            fc = f.get('code')
            if fc in factors:
                problems.append('factor %s twice' % fc)
                continue
            factors[fc] = f
            if not _nonempty(f.get('definition')):
                problems.append('factor %s: empty definition' % fc)
            for band, b in (f.get('bands') or {}).items():
                got.add((fc, band))
                if not (isinstance(b, dict) and _nonempty(b.get('participant')) and _nonempty(b.get('counselor'))):
                    problems.append('factor %s band %s: empty participant/counselor' % (fc, band))
        if got != want:
            problems.append('scored (factor, band) pairs differ: missing %s, extra %s'
                            % (sorted(want - got)[:6], sorted(got - want)[:6]))
        if problems:
            _logger.warning('content v2 %s refused, book texts kept: %s', code, '; '.join(problems[:8]))
            if stats is not None:
                stats['content_errors'] += 1
            return None
        out = {'content_version': data['content_version'].strip(), 'summary': (data.get('summary') or '').strip(),
               'approved_by': (data.get('approved_by') or '').strip(), 'approved_at': (data.get('approved_at') or '').strip(),
               'factors': {}}
        for fc, f in factors.items():
            out['factors'][fc] = {
                'name': (f.get('name') or '').strip(), 'definition': f['definition'].strip(),
                'bands': {band: {'participant': b['participant'].strip(), 'counselor': b['counselor'].strip(),
                                 'talk_points': _talk_list(b.get('talk_points'))}
                          for band, b in f['bands'].items()}}
        # fingerprint of the new-text fields only (ref_* and approval metadata do not make a new version)
        basis = [out['content_version'], out['summary'],
                 sorted((fc, f['name'], f['definition'], sorted((band, b['participant'], b['counselor'], b['talk_points'])
                                                                for band, b in f['bands'].items()))
                        for fc, f in out['factors'].items())]
        out['fingerprint'] = hashlib.sha1(json.dumps(basis, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return out

    @api.model
    def _ts_apply_overlay(self, f_payload, overlay):
        """A deep copy of the payload with the overlay's texts: band client/therapist texts, talk points, the factor
        definition and (optional) name; fmt 'v2'. Codes, bands, ranges and items are untouched."""
        f_payload = copy.deepcopy(f_payload)
        for f in f_payload:
            o = overlay['factors'].get(f['code'])
            if not o or not f['bands']:
                continue
            f['fmt'] = 'v2'
            f['definition'] = o['definition']
            if o['name']:
                f['name'] = o['name']
            for b in f['bands']:
                ob = o['bands'][b['band']]
                b.update({'client': ob['participant'], 'therapist': ob['counselor'], 'talk_points': ob['talk_points'],
                          'cv': overlay['content_version'], 'by': overlay['approved_by'] or b['by'],
                          'at': overlay['approved_at'] or b['at']})
        return f_payload

    # ------------------------------------------------------------------ versions and open attempts
    def _ts_set_current(self, version):
        """current_version_id + superseded = (v != current) on every version of the instrument; open attempts of the
        previous current version continue on the new one. Returns _ts_move_open_attempts' counts."""
        self.ensure_one()
        prev = self.current_version_id
        for v in self.version_ids.filtered(lambda v: v.superseded != (v != version)):
            v.with_context(ts_loader=True).write({'superseded': v != version})
        if prev == version:
            return {'moved': 0, 'answers': 0, 'kept': 0}
        self.write({'current_version_id': version.id})
        return self._ts_move_open_attempts(prev, version)

    def _ts_move_open_attempts(self, old, new):
        """Attempts not yet submitted (consent / in_progress) of `old` continue on `new`: each answer's item is remapped
        through the item's source question id (qid). An attempt with an answer that has no active counterpart stays on
        `old`. Returns {'moved', 'answers', 'kept'}."""
        res = {'moved': 0, 'answers': 0, 'kept': 0}
        if not old or not new or old == new:
            return res
        Attempt = self.env['ts.attempt'].sudo()
        todo = Attempt.search([('version_id', '=', old.id), ('state', 'in', ('consent', 'in_progress'))])
        if not todo:
            return res
        by_qid = {}
        for it in new.item_ids:
            by_qid.setdefault(it.source_question_id, it)
        item_map = {it.id: by_qid.get(it.source_question_id) for it in old.item_ids}
        item_map = {k: v for k, v in item_map.items() if v and not v.disabled}
        for att in todo:
            n = att._ts_remap_items(item_map)
            if n is None:
                res['kept'] += 1
                continue
            att.write({'version_id': new.id})
            res['moved'] += 1
            res['answers'] += n
        _logger.info('%s: open attempts moved from version %s to %s: %s', self.code, old.id, new.id, res)
        return res

    # ------------------------------------------------------------------ load

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

        stats = {'created': 0, 'versions': 0, 'unchanged': 0, 'published': 0, 'retired': 0, 'content_v2': 0,
                 'content_errors': 0, 'moved_attempts': 0}
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
            v1_hash = _payload_hash(contract, f_payload)
            overlay = self._ts_content_overlay(code, f_payload, stats) if contract else None
            if overlay:
                payload = self._ts_apply_overlay(f_payload, overlay)
                content_hash = _payload_hash(contract, payload, overlay['fingerprint'])
            else:
                payload, content_hash = f_payload, v1_hash
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
            prev = inst.current_version_id

            def find_or_create(h, pl, ov=None):
                v = inst.version_ids.filtered(lambda v: v.content_hash == h)[:1]
                if v:
                    return v, False
                stats['versions'] += 1
                return self._ts_create_version(inst, contract, pl, h, xml, owner, now, overlay=ov), True

            version, created = find_or_create(content_hash, payload, overlay)
            if overlay and version != prev:
                # scoring identity: the v2 version must score exactly like the version it replaces (or the book version)
                ref = prev or find_or_create(v1_hash, f_payload)[0]
                if scoring_fingerprint(version) != scoring_fingerprint(ref):
                    _logger.error('content v2 %s: scoring contract of version %s differs from version %s; '
                                  'instrument kept on the book texts', code, version.id, ref.id)
                    stats['content_errors'] += 1
                    overlay = None
                    version, created = find_or_create(v1_hash, f_payload)
            if overlay:
                stats['content_v2'] += 1
            if not created:
                stats['unchanged'] += 1
            version._validate_contract()
            scored = version.factor_ids.filtered('scored')
            names = '، '.join(scored.mapped('name'))
            aud = inst.audience
            who = ('این پرسشنامه را والد یا مراقب دربارهٔ کودک تکمیل می‌کند.' if aud == 'child' else
                   'نوجوان با اطلاع و رضایت ولی پاسخ می‌دهد.' if aud == 'adolescent' else
                   'پاسخ‌دهنده خود شرکت‌کننده است.')
            stats['moved_attempts'] += inst._ts_set_current(version)['moved']
            upd = {'rights_note': RIGHTS_NOTE, 'evidence_note': EVIDENCE_NOTE,
                   'limitations': LIMITATIONS, 'approval_note': APPROVAL_NOTE,
                   'summary': (overlay and overlay['summary']) or False}
            employment = aud == 'adult' and inst.category in EMPLOYMENT_CATEGORIES
            upd['purpose'] = 'employment' if employment else 'personal'
            if inst.category and scored and employment:
                upd['intended_use'] = ('کاربرد: خودشناسی و گفت‌وگوی مشاوره‌ای در حوزهٔ «%s»؛ در پنل استخدامی، فقط با رضایت شرکت‌کننده '
                                       'و به‌صورت سطح هر عامل، به‌عنوان یکی از ورودی‌های گفت‌وگوی شغلی. این سنجه %s عامل را توصیف می‌کند: %s. %s '
                                       'این سنجه برای تشخیص به کار نمی‌رود و به‌تنهایی مبنای تصمیم استخدامی نیست.'
                                       % (inst.category, fa_digits(len(scored)), names, who))
            elif inst.category and scored:
                upd['intended_use'] = ('کاربرد: خودشناسی و گفت‌وگوی مشاوره‌ای در حوزهٔ «%s». این سنجه %s عامل را توصیف می‌کند: %s. %s '
                                       'این سنجه برای تشخیص یا تصمیم استخدامی به کار نمی‌رود.'
                                       % (inst.category, fa_digits(len(scored)), names, who))
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
        self._ts_refresh_titles()
        _logger.info('Talent Search instruments loaded: %s', stats)
        return stats

    def _ts_create_version(self, inst, contract, f_payload, content_hash, xml, owner, now, overlay=None):
        Version = self.env['ts.instrument.version'].with_context(ts_loader=True)
        version = Version.create({
            'instrument_id': inst.id,
            'contract_version': contract['x_version'] if contract else 'NO-ACTIVE-CONTRACT',
            'content_hash': content_hash,
            'content_version': overlay['content_version'] if overlay else False,
            'source_contract_xmlid': xml.get('x_psy_scoring_contract:%s' % contract['id']) if contract else False,
            'source_contract_id': contract['id'] if contract else 0,
        })
        Factor, Band, Item = self.env['ts.instrument.factor'], self.env['ts.instrument.band'], self.env['ts.instrument.item']
        for seq, f in enumerate(f_payload):
            v2 = f.get('fmt') == 'v2'
            definition = (f.get('definition') or '') if v2 else ''
            if not v2 and f['bands']:
                for head, body in split_interpretation(f['bands'][0]['client']):
                    if head == DEF_HEADING:
                        definition = body
                        break
            fac = Factor.create({'version_id': version.id, 'code': f['code'], 'name': f['name'], 'sequence': seq,
                                 'definition': definition, 'scored': bool(f['bands']),
                                 'source_xmlid': xml.get('x_psy_factor:%s' % f['src']), 'source_rule_xmlid': f['rule_xmlid']})
            for b in f['bands']:
                Band.create({'factor_id': fac.id, 'band': b['band'], 'min_score': b['min'], 'max_score': b['max'],
                             'client_text': b['client'], 'therapist_text': b['therapist'],
                             'content_version': b['cv'] if v2 else '%s + %s' % (b['cv'], APPROVAL_VERSION),
                             'content_format': 'v2' if v2 else 'book',
                             'talk_points': '\n'.join(b.get('talk_points') or []) or False,
                             'source_approved_by': b['by'], 'source_approved_at': b['at'],
                             'approved_by_id': owner.id, 'approved_at': now,
                             'source_xmlid': xml.get('x_psy_factor_threshold_rule:%s' % b['src'])})
            Item.create([{'version_id': version.id, 'factor_id': fac.id, 'sequence': i['seq'],
                          'source_question_id': i['qid'], 'text': i['text'], 'reverse': i['rev'], 'disabled': i['dis'],
                          'source_xmlid': xml.get('x_psy_assessment_item:%s' % i['src']),
                          'source_question_xmlid': 'survey.question:%s' % i['qsrc']} for i in f['items']])
        return version
