import math
from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION, fa_digits
from odoo.addons.ts_assessment.models.instrument import SCALE

PAGE_SIZE = 10


def _ts_site_or_404():
    website = request.env.website
    if not (website and website._ts_is_current()):
        raise request.not_found()
    return website


def _instrument_by_slug(slug):
    inst = request.env['ts.instrument'].sudo().search([('slug', '=', slug), ('state', '=', 'published')], limit=1)
    if not inst:
        raise request.not_found()
    return inst


def _my_attempt(token=None, attempt_id=None):
    Attempt = request.env['ts.attempt'].sudo()
    domain = [('user_id', '=', request.env.user.id)]
    domain.append(('access_token', '=', token) if token else ('id', '=', int(attempt_id)))
    attempt = Attempt.search(domain, limit=1)
    if not attempt:
        raise request.not_found()
    return attempt


def _pages(attempt):
    items = attempt.active_items()
    n = max(1, math.ceil(len(items) / PAGE_SIZE))
    return items, n


class TsAssessment(http.Controller):

    # ------------------------------------------------------------- catalog
    @http.route('/assessments', type='http', auth='public', website=True, sitemap=True)
    def catalog(self, **kw):
        _ts_site_or_404()
        insts = request.env['ts.instrument'].sudo().search([('state', '=', 'published')])
        groups = {}
        for inst in insts:
            groups.setdefault(inst.category or 'سایر', []).append(inst)
        return request.render('ts_assessment.catalog', {
            'groups': list(groups.items()), 'count': len(insts), 'fa': fa_digits,
        })

    @http.route('/assessments/<string:slug>', type='http', auth='public', website=True, sitemap=False)
    def detail(self, slug, **kw):
        _ts_site_or_404()
        inst = _instrument_by_slug(slug)
        mine = request.env['ts.attempt'].sudo().search([
            ('user_id', '=', request.env.user.id), ('instrument_id', '=', inst.id)], limit=5) \
            if not request.env.user._is_public() else request.env['ts.attempt']
        return request.render('ts_assessment.detail', {
            'inst': inst, 'version': inst.current_version_id, 'mine': mine, 'fa': fa_digits,
            'start_url': '/assessments/%s/start' % quote(inst.slug),
        })

    @http.route('/assessments/<string:slug>/start', type='http', auth='user', website=True, methods=['GET', 'POST'], sitemap=False)
    def start(self, slug, **kw):
        _ts_site_or_404()
        inst = _instrument_by_slug(slug)
        user = request.env.user
        Attempt = request.env['ts.attempt'].sudo()
        open_attempt = Attempt.search([('user_id', '=', user.id), ('instrument_id', '=', inst.id),
                                       ('state', 'in', ('consent', 'in_progress')),
                                       ('version_id', '=', inst.current_version_id.id)], limit=1)
        if request.httprequest.method == 'GET' and not open_attempt:
            # Starting creates a record: only via the POST form on the detail page.
            return request.redirect('/assessments/%s' % quote(inst.slug))
        attempt = open_attempt or Attempt.create({
            'user_id': user.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id,
        })
        return request.redirect('/take/%s' % attempt.access_token)

    # ------------------------------------------------------------- player
    @http.route('/take/<string:token>', type='http', auth='user', website=True, sitemap=False)
    def take(self, token, page=None, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if attempt.state == 'done':
            return request.redirect('/my/assessments/%s' % attempt.id)
        if attempt.state == 'consent':
            return request.render('ts_assessment.consent', {'attempt': attempt, 'inst': attempt.instrument_id,
                                                              'consent_version': CONSENT_VERSION, 'fa': fa_digits,
                                                              'error': kw.get('error')})
        if attempt.state == 'error':
            return request.render('ts_assessment.error', {'attempt': attempt})
        items, n_pages = _pages(attempt)
        answers = attempt.answers_map()
        if page is None:
            first_open = next((idx for idx, it in enumerate(items) if it.id not in answers), 0)
            page = first_open // PAGE_SIZE + 1
        page = min(max(int(page), 1), n_pages)
        chunk = items[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        return request.render('ts_assessment.player', {
            'attempt': attempt, 'inst': attempt.instrument_id, 'items': chunk, 'answers': answers,
            'page': page, 'n_pages': n_pages, 'scale': SCALE, 'fa': fa_digits,
            'first_index': (page - 1) * PAGE_SIZE, 'answered': len(answers), 'total': len(items),
            'error': kw.get('error'),
        })

    @http.route('/take/<string:token>/consent', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def consent(self, token, **post):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if post.get('consent_service') != '1':
            return request.redirect('/take/%s?error=consent' % token)
        role = 'guardian' if attempt.instrument_id.audience in ('child', 'adolescent') else 'self'
        if role == 'guardian' and post.get('guardian_confirm') != '1':
            return request.redirect('/take/%s?error=guardian' % token)
        attempt.give_consent(research=post.get('consent_research') == '1', role=role, subject=post.get('subject_label'))
        return request.redirect('/take/%s' % token)

    def _save_posted(self, attempt, post):
        for key, value in post.items():
            if key.startswith('q_') and value:
                attempt.save_answer(int(key[2:]), int(value))

    @http.route('/take/<string:token>/page', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def save_page(self, token, **post):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if attempt.state != 'in_progress':
            return request.redirect('/take/%s' % token)
        self._save_posted(attempt, post)
        page = int(post.get('page') or 1)
        go = post.get('go')
        if go == 'prev':
            return request.redirect('/take/%s?page=%d' % (token, page - 1))
        if go == 'review':
            return request.redirect('/take/%s/review' % token)
        return request.redirect('/take/%s?page=%d' % (token, page + 1))

    @http.route('/take/<string:token>/answer', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def autosave(self, token, item=None, value=None, **kw):
        """Autosave of one answer (fetch from ts_player.js). CSRF-protected."""
        _ts_site_or_404()
        attempt = _my_attempt(token)
        try:
            attempt.save_answer(int(item), int(value))
        except (UserError, ValueError, TypeError) as e:
            return request.make_json_response({'ok': False, 'error': str(e)}, status=400)
        return request.make_json_response({'ok': True, 'answered': len(attempt.answer_ids),
                                           'total': attempt.version_id.active_item_count})

    @http.route('/take/<string:token>/review', type='http', auth='user', website=True, sitemap=False)
    def review(self, token, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if attempt.state != 'in_progress':
            return request.redirect('/take/%s' % token)
        items, n_pages = _pages(attempt)
        answers = attempt.answers_map()
        missing = [(idx + 1, it, idx // PAGE_SIZE + 1) for idx, it in enumerate(items) if it.id not in answers]
        return request.render('ts_assessment.review', {
            'attempt': attempt, 'inst': attempt.instrument_id, 'missing': missing, 'total': len(items),
            'answered': len(answers), 'n_pages': n_pages, 'fa': fa_digits, 'error': kw.get('error'),
        })

    @http.route('/take/<string:token>/submit', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def submit(self, token, **post):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if attempt.state == 'done':
            return request.redirect('/my/assessments/%s' % attempt.id)
        try:
            ok = attempt.action_submit(submission_key=post.get('submission_key'))
        except UserError:
            return request.redirect('/take/%s/review?error=missing' % token)
        if not ok:
            return request.redirect('/take/%s' % token)
        return request.redirect('/my/assessments/%s?submitted=1' % attempt.id)

    # ------------------------------------------------------------- account
    @http.route('/my/assessments', type='http', auth='user', website=True, sitemap=False)
    def my_list(self, **kw):
        _ts_site_or_404()
        attempts = request.env['ts.attempt'].sudo().search([('user_id', '=', request.env.user.id)], order='id desc')
        # portal v3 (P3): unfinished first, then results grouped per instrument, newest first
        going = attempts.filtered(lambda a: a.state in ('consent', 'in_progress'))
        groups = []
        for a in attempts.filtered(lambda a: a.state not in ('consent', 'in_progress')):
            for g in groups:
                if g['inst'] == a.instrument_id:
                    g['rows'].append(a)
                    break
            else:
                groups.append({'inst': a.instrument_id, 'rows': [a]})
        return request.render('ts_assessment.my_list', {'attempts': attempts, 'going': going, 'groups': groups,
                                                         'fa': fa_digits, 'page_name': 'ts_assessments'})

    @http.route('/my/assessments/<int:attempt_id>', type='http', auth='user', website=True, sitemap=False)
    def my_report(self, attempt_id, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(attempt_id=attempt_id)
        if attempt.state != 'done':
            return request.redirect('/take/%s' % attempt.access_token)
        if not attempt.released:
            # finished but not available to the participant (erased under a legal hold, or imported without release):
            # an honest page instead of the old redirect loop between /my/assessments/<id> and /take/<token>
            return request.render('ts_assessment.unavailable', {'attempt': attempt, 'inst': attempt.instrument_id,
                                                                  'page_name': 'ts_assessments'})
        request.env['ts.audit.event'].sudo().log('report.view', attempt)
        # portal v3 (P3): earlier released results of the same instrument; only the same scoring contract is comparable
        history = request.env['ts.attempt'].sudo().search([
            ('user_id', '=', request.env.user.id), ('instrument_id', '=', attempt.instrument_id.id), ('state', '=', 'done'),
            ('released', '=', True), ('id', '!=', attempt.id)], order='submitted_at desc')
        return request.render('ts_assessment.report', {
            'attempt': attempt, 'inst': attempt.instrument_id, 'version': attempt.version_id,
            'results': attempt.result_rows(), 'fa': fa_digits, 'submitted': kw.get('submitted'),
            'history': history, 'page_name': 'ts_assessments',
        })
