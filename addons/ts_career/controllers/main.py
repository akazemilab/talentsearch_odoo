"""Free career match pages: /career (start), /career/start, /career/r (background + results), /career/job/<code>,
/career/more/<kind> (optional personality / ability modules). Every finished module comes back to /career/r."""
from odoo import http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _my_attempt, _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_onboard.controllers.guest import TsOnbCatalog

from ..models.career import (EDU, EXP, HEX_CODE, IP_CODE, ONET_NOTICE, RIASEC_FA, RIASEC_GLOSS, E)

PAGE = 20


def _sitemap_career(env, rule, qs):
    """/career is listed in talentsearch.ir's sitemap only (routes are global: sitemap=True would add it to eot.ir's)."""
    try:
        site = getattr(env, 'website', None) or env['website'].browse(env.context.get('website_id') or [])
        ts = env.ref('ts_website.website_ts', raise_if_not_found=False)
        ok = bool(site) and bool(ts) and site.id == ts.id
    except Exception:                                   # noqa: BLE001  (never break a sitemap)
        ok = False
    if ok and (not qs or qs.lower() in '/career'):
        yield {'loc': '/career'}


def _run(create=False):
    return request.env['ts.career.run'].ts_for_user(request.env.user, create=create)


class TsCareer(TsOnbCatalog):

    @http.route('/career', type='http', auth='public', website=True, sitemap=_sitemap_career)
    def career_home(self, **kw):
        _ts_site_or_404()
        public = request.env.user._is_public()
        run = None if public else _run()
        full = request.env['ts.career.run'].ts_cap_reached() and not run
        return request.render('ts_career.home', {'run': run, 'full': full, 'public': public, 'fa': fa_digits,
                                                 'notice': ONET_NOTICE})

    @http.route('/career/start', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def career_start(self, **kw):
        _ts_site_or_404()
        if request.env.user._is_public():
            if request.env['ts.career.run'].ts_cap_reached():
                return request.redirect('/career')
            return request.redirect('/signup?next=/career/start')
        run = _run()
        if not run:
            if request.env['ts.career.run'].ts_cap_reached():
                return request.redirect('/career')
            run = _run(create=True)
        st = run.ts_state()
        if st['ip_done']:
            return request.redirect('/career/r')
        return request.redirect('/take/%s' % run.ts_ensure_attempt(IP_CODE).access_token)

    @http.route('/career/r', type='http', auth='user', website=True, sitemap=False, methods=['GET', 'POST'])
    def career_result(self, **kw):
        _ts_site_or_404()
        run = _run()
        if not run:
            return request.redirect('/career')
        st = run.ts_state()
        if not st['ip_done']:
            return request.redirect('/career/start')
        if request.httprequest.method == 'POST' and kw.get('edu') in dict(EDU) and kw.get('exp') in dict(EXP):
            run.sudo().write({'edu': kw['edu'], 'exp': kw['exp']})
            return request.redirect('/career/r')
        if not st['bg_done'] or kw.get('edit'):
            return request.render('ts_career.background', {'run': run, 'edu': EDU, 'exp': EXP, 'fa': fa_digits,
                                                           'error': request.httprequest.method == 'POST'})
        res = run.ts_result()
        person = res['person']
        full_list = kw.get('all') == '1'
        ready_only = full_list and kw.get('ready') == '1'
        rows = [r for r in res['rows'] if not ready_only or r['ready'] == 'READY']
        Run = request.env['ts.career.run']
        groups, order = {}, []
        for i, r in enumerate([r for r in res['rows'] if r.get('short')]):
            v = Run.ts_view_row(r, person)
            v['n'] = i + 1
            if v['area'] not in groups:
                order.append(v['area'])
                groups[v['area']] = {'name': v['area_fa'], 'rows': []}
            groups[v['area']]['rows'].append(v)
        try:
            n = max(PAGE, min(120, int(kw.get('n') or PAGE)))
        except ValueError:
            n = PAGE
        top = E.person_top(person['riasec'], 6)
        mx = max(float(person['riasec'][k]) for k in top) or 1
        profile = [{'name': RIASEC_FA[k], 'gloss': RIASEC_GLOSS[k], 'w': int(round(100 * float(person['riasec'][k]) / mx))}
                   for k in top[:3]]
        return request.render('ts_career.result', {
            'run': run, 'st': st, 'res': res, 'tier': res['tier'], 'profile': profile,
            'rows': [Run.ts_view_row(r, person) for r in rows[:n]] if full_list else [], 'more': full_list and len(rows) > n, 'n': n, 'ready_only': ready_only,
            'total': len(rows), 'fa': fa_digits, 'notice': ONET_NOTICE, 'full_list': full_list,
            'groups': [groups[k] for k in order], 'n_short': sum(len(groups[k]['rows']) for k in order),
            'n_all': len(res['rows'])})

    @http.route('/career/job/<string:code>', type='http', auth='user', website=True, sitemap=False)
    def career_job(self, code, **kw):
        _ts_site_or_404()
        run = _run()
        res = run and run.ts_result()
        row = res and next((r for r in res['rows'] if r['code'] == code), None)
        if not row:
            return request.redirect('/career/r')
        st = run.ts_state()
        missing = []
        if not st['hex_done']:
            missing.append('سبک‌های کاری شما هنوز سنجیده نشده است.')
        if st['tasks_done'] < st['tasks_total']:
            missing.append('توانایی‌های شما هنوز کامل سنجیده نشده است.')
        return request.render('ts_career.job', {'run': run, 'j': request.env['ts.career.run'].ts_view_row(row, res['person']),
                                                'tier': res['tier'], 'missing': missing, 'fa': fa_digits, 'st': st,
                                                'notice': ONET_NOTICE})

    @http.route('/career/more/<string:kind>', type='http', auth='user', website=True, sitemap=False, methods=['POST'])
    def career_more(self, kind, **kw):
        _ts_site_or_404()
        run = _run()
        if not run or not run.ts_state()['ip_done']:
            return request.redirect('/career')
        if kind == 'personality':
            code = HEX_CODE
        elif kind == 'abilities':
            code = run.ts_next_task()
        else:
            code = None
        if not code:
            return request.redirect('/career/r')
        return request.redirect('/take/%s' % run.ts_ensure_attempt(code).access_token)

    @http.route()
    def my_report(self, attempt_id, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(attempt_id=attempt_id)
        if attempt.career_run_id and attempt.state == 'done':
            nxt = attempt.career_run_id.ts_next_task() if attempt.instrument_id.code.startswith('TASK-') else None
            if nxt:
                return request.redirect('/take/%s' % attempt.career_run_id.ts_ensure_attempt(nxt).access_token)
            return request.redirect('/career/r')
        return super().my_report(attempt_id, **kw)
