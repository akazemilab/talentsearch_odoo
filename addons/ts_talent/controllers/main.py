import json
import math
import os

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.modules import get_module_path

from odoo.addons.ts_assessment.controllers.main import TsAssessment, _my_attempt, _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION, fa_digits
from odoo.addons.ts_assessment.models.instrument import SCALE

from odoo.addons.ts_org.controllers.main import _membership as _org_membership

from ..models import engine_matrix as EM
from ..models import report as R
from ..models.loader import LIMITATIONS, LIMITATIONS_TU
from ..models.text import item_segments, norm_label

PAGE = 5
# Optional suggestions under the field-name input (UX audit G1-P13-3); hidden when already used.
SUGGESTIONS = ['ریاضی', 'نقاشی', 'فوتبال', 'برنامه‌نویسی', 'موسیقی']
ORDINALS = ['اوّل', 'دوّم', 'سوّم', 'چهارم', 'پنجم', 'ششم', 'هفتم', 'هشتم']
_TEXTS = {}


def ordinal(n):
    return ORDINALS[n - 1] if 1 <= n <= len(ORDINALS) else fa_digits(n)


def texts():
    if not _TEXTS:
        path = os.path.join(get_module_path('ts_talent'), 'data', 'talent_texts.json')
        with open(path, encoding='utf-8') as fh:
            _TEXTS.update(json.load(fh))
    return _TEXTS


def _n_pages(items):
    return max(1, math.ceil(len(items) / PAGE))


def _share_info(attempt):
    """Who else reads this report (presentation only; access is decided elsewhere)."""
    asg = attempt.ts_org_assignment() if hasattr(attempt, 'ts_org_assignment') else None
    shared = bool(asg and asg.share_level != 'none')
    return {
        'asg': asg, 'shared': shared,
        'shared_edu': shared and asg.workspace_id.purpose == 'education',
        'shared_name': asg.workspace_id.ts_public_name() if shared else '',
        'can_share': not asg and not attempt.workspace_id and attempt.source != 'import',
    }


def report_ctx(attempt, org_view=False, ws=None, submitted=None, panel_actions=None):
    """Template context of the matrix report; org_view drops raw answers (institute side).

    voice: 'org' (third person, panel member), 'tu' (student), 'shoma' (adult) - copy only.
    Participant views round to whole numbers (differences under +-8 are not meaningful)."""
    profile = attempt.ts_profile()
    interp = profile['interpretation']
    gap = interp.get('gap', 10)
    fields = profile['fields']
    t = texts()
    voice = 'org' if org_view else ('tu' if attempt.ts_informal() else 'shoma')
    digits = 0   # whole numbers in every view (the panel showed ۶۰٫۰ next to the participant's ۶۰)
    raw = []
    if not org_view:
        items = attempt.active_items()
        cells = {}
        for c in attempt.cell_ids:
            cells.setdefault(c.field_id.label, {})[c.item_id.id] = c.value
        labels = dict(SCALE)
        raw = [{'label': f['label'],
                'rows': [(item_segments(it.text, f['label']), labels.get(cells.get(f['label'], {}).get(it.id), '—'))
                         for it in items]} for f in fields]
    defs = [(EM.NAMES[c], t['scales'][c]['definition']) for c in EM.SCALES]
    defs += [(EM.NAMES[c], t['composites'][c]['definition']) for c in ('INT', 'CRE', 'SCH', 'CRT', 'CRP') if c in t['composites']]
    defs = [(name, R.norm_text(text)) for name, text in R.split_pair_definition(defs)]
    single = R.single_field_lines(interp, voice) if interp['n_fields'] < 2 else None
    multi = interp['n_fields'] >= 2
    flagged = interp.get('flagged') or [f['label'] for f in fields if f['flags'].get('straight') or f['flags'].get('fast')]

    def fmt(v, d=None):
        return R.fmt(v, digits if d is None else d)
    limitations = attempt.instrument_id.limitations or ''
    if voice == 'tu' and limitations == LIMITATIONS:          # our own text: one pronoun per page (UX audit T7 P10-2)
        limitations = LIMITATIONS_TU
    ctx = {
        'attempt': attempt, 'inst': attempt.instrument_id, 'version': attempt.version_id, 'limitations': limitations,
        'tiles': R.tiles(interp, profile, voice, digits), 'fields': fields,
        'charts': {f['label']: R.field_chart(f, digits) for f in fields},
        'legend': [EM.NAMES[c] for c in EM.SCALES], 'single': single,
        'lv': R.levels(interp, profile, voice, digits) if not single else [], 'interp': interp,
        'programs': R.programs_view(interp, voice), 'rows': R.table_rows(profile, gap), 'raw': raw,
        'cmp_rows': R.compare_rows(profile, gap) if multi else [],
        'cmp_cards': R.field_cards(profile, gap) if multi else [],
        'cmp_lines': R.compare_lines(interp, voice, digits) if multi else [],
        'summary': R.summary(interp, profile, voice, digits),
        'flagged': flagged, 'all_flagged': bool(fields) and len(flagged) >= len(fields),
        'fields_tied': R.fields_all_tied(interp),
        'gap': int(gap), 'org_view': org_view, 'ws': ws, 'who': attempt.person_id.name or attempt.partner_id.ts_known_name() or '',
        'voice': voice, 'tu': voice == 'tu',
        'quote': R.norm_text(t['quotes']['purpose']['text']),
        'texts': t, 'defs': defs, 'submitted': submitted, 'panel_actions': panel_actions or [],
        'fa': fa_digits, 'fmt': fmt, 'joinfa': R.joinfa, 'page_name': 'ts_workspaces' if org_view else 'ts_assessments'}
    if not org_view:
        ctx.update(_share_info(attempt))
    return ctx


class TsTalent(TsAssessment):

    def _tt_url(self, token, **q):
        qs = '&'.join('%s=%s' % (k, v) for k, v in q.items() if v is not None)
        return '/take/%s%s' % (token, ('?' + qs) if qs else '')

    def _name_error(self, kw):
        return request.session.pop('tt_error', None) if kw.get('error') == 'name' else None

    def _name_ctx(self, attempt, done, guidance, kw, rename=None):
        v = attempt.version_id
        used = {f.label_norm for f in attempt.field_ids}
        return {
            'attempt': attempt, 'n': len(done) + 1, 'ordinal': ordinal(len(done) + 1), 'guidance': guidance,
            'rename': rename, 'label': None, 'error': self._name_error(kw), 'done': bool(done), 'n_done': len(done),
            'field_min': v.field_min, 'field_max': v.field_max, 'fa': fa_digits, 'tu': attempt.ts_informal(),
            'suggestions': [x for x in SUGGESTIONS if norm_label(x) not in used] if not rename else [],
        }

    # ------------------------------------------------------------ player
    @http.route('/take/<string:token>/reopen', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def reopen(self, token, **post):
        """Open a completed field again before the final submit (UX audit G1-P15-2)."""
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if not attempt.ts_is_matrix() or attempt.state != 'in_progress':
            return request.redirect('/take/%s' % token)
        try:
            field = attempt.field_ids.filtered(lambda f: f.id == int(post.get('field_id') or 0))
            if not field:
                raise request.not_found()
            attempt.ts_reopen_field(field)
        except (UserError, ValueError):
            return request.redirect(self._tt_url(token, error='reopen'))
        return request.redirect(self._tt_url(token, p=1))

    @http.route()
    def review(self, token, **kw):
        # the generic Likert review page means nothing for a matrix attempt (UX audit 2026-10-11, P16-1):
        # the matrix player is its own review step
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if attempt.ts_is_matrix():
            return request.redirect('/take/%s' % token)
        return super().review(token, **kw)

    @http.route()
    def take(self, token, page=None, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if not attempt.ts_is_matrix():
            return super().take(token, page=page, **kw)
        if attempt.state == 'done':
            return request.redirect('/my/assessments/%s' % attempt.id)
        if attempt.state == 'error':
            return request.render('ts_assessment.error', {'attempt': attempt})
        if attempt.state == 'consent':
            return request.render('ts_talent.consent', {
                'attempt': attempt, 'consent_version': CONSENT_VERSION, 'error': kw.get('error'),
                'tu': attempt.ts_informal(), 'fa': fa_digits, 'v': attempt.version_id})
        v = attempt.version_id
        cur = attempt.ts_current_field()
        done = attempt.ts_done_fields()
        view = kw.get('v')
        guidance = v.field_guidance or ''
        if cur and view == 'rename' and not cur.cell_ids:
            return request.render('ts_talent.name', self._name_ctx(attempt, done, guidance, kw, rename=cur))
        if cur and view == 'straight':
            return request.render('ts_talent.straight', {
                'attempt': attempt, 'field': cur, 'tu': attempt.ts_informal(), 'fa': fa_digits,
                'field_no': len(done.filtered(lambda f: f.sequence < cur.sequence)) + 1})
        if cur:
            items = attempt.active_items()
            n_pages = _n_pages(items)
            cells = {c.item_id.id: c.value for c in cur.cell_ids}
            p = kw.get('p')
            if p is None:
                first_open = next((i for i, it in enumerate(items) if it.id not in cells), len(items) - 1)
                p = first_open // PAGE + 1
            p = min(max(int(p), 1), n_pages)
            chunk = items[(p - 1) * PAGE: p * PAGE]
            missing = {it.id for it in chunk if it.id not in cells} if kw.get('error') == 'missing' else set()
            # numbers of the unanswered statements, linked from the error summary (UX audit T7 P5-1)
            missing_nos = [(it.id, (p - 1) * PAGE + n + 1) for n, it in enumerate(chunk) if it.id in missing]
            return request.render('ts_talent.statements', {
                'attempt': attempt, 'field': cur, 'page': p, 'n_pages': n_pages, 'items': chunk,
                'first': (p - 1) * PAGE, 'scale': SCALE, 'cells': cells, 'missing': missing, 'missing_nos': missing_nos,
                'field_no': len(done.filtered(lambda f: f.sequence < cur.sequence)) + 1, 'n_done': len(done),
                'error': kw.get('error'), 'segments': item_segments, 'fa': fa_digits, 'tu': attempt.ts_informal()})
        if not done or view == 'name':
            return request.render('ts_talent.name', self._name_ctx(attempt, done, guidance, kw))
        tu = attempt.ts_informal()
        # the final submit failed: say the real reason (carried in the session like the name errors), never a
        # sentence that contradicts the fields shown on the page (UX audit T7 P8-1)
        reason = request.session.pop('tt_finish_error', None) if kw.get('error') == 'finish' else None
        enough = len(done) >= v.field_min
        if enough:
            finish_err = 'پایان ثبت نشد%s. دوباره «پایان و دیدن نتیجه» را %s؛ اگر باز هم نشد، با پشتیبانی تماس %s.' % (
                (': ' + reason.rstrip('.')) if reason else '', 'بزن' if tu else 'بزنید', 'بگیر' if tu else 'بگیرید')
        else:
            finish_err = 'هنوز نمی‌شود پایان را زد: برای مقایسه دست‌کم %s زمینهٔ کامل لازم است.' % fa_digits(v.field_min)
        errors = {
            'finish': finish_err,
            'reopen': 'این زمینه باز نشد؛ اول زمینهٔ در حال پاسخ را کامل کن.' if tu else 'این زمینه باز نشد؛ اول زمینهٔ در حال پاسخ را کامل کنید.',
        }
        last = done.sorted(lambda f: f.finished_at or f.create_date)[-1:] or done[-1:]
        return request.render('ts_talent.between', {
            'attempt': attempt, 'done': done, 'last': last, 'field_min': v.field_min, 'field_max': v.field_max,
            'n_items': len(attempt.active_items()), 'ordinal_min': ordinal(v.field_min),
            'ordinal_next': ordinal(len(done) + 1), 'error': errors.get(kw.get('error')),
            'error_support': kw.get('error') == 'finish' and enough, 'fa': fa_digits, 'tu': tu})

    @http.route('/take/<string:token>/field', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def field_post(self, token, **post):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        try:
            if post.get('field_id'):
                field = attempt.field_ids.filtered(lambda f: f.id == int(post['field_id']))
                if not field:
                    raise request.not_found()
                attempt.ts_rename_field(field, post.get('label'))
            else:
                attempt.ts_add_field(post.get('label'))
        except UserError as e:
            request.session['tt_error'] = str(e.args[0])
            return request.redirect(self._tt_url(token, v='name', error='name'))
        return request.redirect('/take/%s' % token)

    @http.route('/take/<string:token>/mpage', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def mpage(self, token, **post):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        field = attempt.ts_current_field()
        if attempt.state != 'in_progress' or not field:
            return request.redirect('/take/%s' % token)
        try:
            for key, value in post.items():
                if key.startswith('c_') and value:
                    attempt.ts_save_cell(field, int(key[2:]), int(value))
            p = int(post.get('p') or 1)
            go = post.get('go')
            items = attempt.active_items()
            have = {c.item_id.id for c in field.cell_ids}
            if go == 'prev':
                return request.redirect(self._tt_url(token, p=max(1, p - 1)))
            if go == 'next':
                chunk = items[(p - 1) * PAGE: p * PAGE]
                if any(it.id not in have for it in chunk):
                    return request.redirect(self._tt_url(token, p=p, error='missing'))
                return request.redirect(self._tt_url(token, p=p + 1))
            if go == 'done':
                gone = [it for it in items if it.id not in have]
                if gone:
                    idx = items.ids.index(gone[0].id)
                    return request.redirect(self._tt_url(token, p=idx // PAGE + 1, error='missing'))
                res = attempt.ts_finish_field(field, confirm_straight=post.get('confirm') == '1')
                if res == 'straight':
                    return request.redirect(self._tt_url(token, v='straight'))
        except UserError:
            return request.redirect(self._tt_url(token, p=1, error='missing'))
        return request.redirect('/take/%s' % token)

    @http.route()
    def autosave(self, token, item=None, value=None, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if not attempt.ts_is_matrix():
            return super().autosave(token, item=item, value=value, **kw)
        try:
            field = attempt.ts_current_field()
            if not field or (kw.get('field') and int(kw['field']) != field.id):
                raise UserError('زمینهٔ جاری نامعتبر است.')
            attempt.ts_save_cell(field, int(item), int(value))
        except (UserError, ValueError, TypeError) as e:
            return request.make_json_response({'ok': False, 'error': str(e)}, status=400)
        return request.make_json_response({'ok': True, 'answered': len(field.cell_ids), 'total': attempt.version_id.active_item_count})

    @http.route('/take/<string:token>/finish', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def finish(self, token, **post):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if not attempt.ts_is_matrix():
            return request.redirect('/take/%s' % token)
        if attempt.state == 'done':
            return request.redirect('/my/assessments/%s' % attempt.id)
        try:
            ok = attempt.action_submit(submission_key=post.get('submission_key'))
        except UserError as e:
            request.session['tt_finish_error'] = str(e.args[0])
            return request.redirect(self._tt_url(token, error='finish'))
        if not ok:
            return request.redirect('/take/%s' % token)
        return request.redirect('/my/assessments/%s?submitted=1' % attempt.id)

    # ------------------------------------------------------------ report
    @http.route()
    def my_report(self, attempt_id, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(attempt_id=attempt_id)
        if not attempt.ts_is_matrix():
            return super().my_report(attempt_id, **kw)
        if attempt.state != 'done' or not attempt.released:
            return request.redirect('/take/%s' % attempt.access_token)
        request.env['ts.audit.event'].sudo().log('report.view', attempt)
        return request.render('ts_talent.report', report_ctx(attempt, submitted=kw.get('submitted')))


class TsTalentOrg(http.Controller):
    """Institute (education workspace) side: a counselor reads a participant report."""

    @http.route('/my/workspaces/<int:ws_id>/p/<int:attempt_id>', type='http', auth='user', website=True, sitemap=False)
    def org_person(self, ws_id, attempt_id, **kw):
        _ts_site_or_404()
        member = _org_membership(ws_id)
        attempt = request.env['ts.attempt'].sudo().browse(attempt_id).exists()
        if not attempt or not attempt.ts_is_matrix() or not attempt.ts_org_visible_to(member):
            raise request.not_found()
        request.env['ts.audit.event'].sudo().log('attempt.result_view', attempt, workspace=member.workspace_id,
                                                 viewer=request.env.user.id)
        return request.render('ts_talent.report', report_ctx(attempt, org_view=True, ws=member.workspace_id))  # legacy alias


_SAMPLE = [  # fully fictional profile; never derived from a real person
    ('علوم زیستی', dict(ANA=80, EXP=73.33, ACA=86.67, NOV=60, DUT=73.33), False),
    ('طراحی گرافیک', dict(ANA=66.67, EXP=86.67, ACA=60, NOV=93.33, DUT=66.67), False),
    ('فوتسال', dict(ANA=53.33, EXP=80, ACA=46.67, NOV=60, DUT=86.67), False),
    ('برنامه‌نویسی', dict(ANA=86.67, EXP=66.67, ACA=80, NOV=73.33, DUT=53.33), True),
]


def sample_profile():
    fields = []
    for label, sc, fast in _SAMPLE:
        fields.append({'label': label, 'scales': dict(sc), 'composites': {'TOT': sum(sc.values()) / 5.0},
                       'flags': {'straight': False, 'fast': fast}})
    return {'fields': fields}


class TsEntekhab(http.Controller):

    @http.route('/entekhab-reshteh/sample', type='http', auth='public', website=True, sitemap=False)
    def er_sample(self, **kw):
        """Retired with the 2026-10 redesign: the sample report now lives on /assessments#sample."""
        _ts_site_or_404()
        return request.redirect('/assessments#sample', code=301, local=True)
