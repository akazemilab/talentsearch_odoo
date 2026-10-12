"""Timed task player routes (docs/hr/01_architecture.md section 4). The page renders once; the script talks to
/take/<token>/task/{start,answer,finish}. Ownership is checked by _my_attempt (the attempt's user only)."""
import json

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _my_attempt, _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_battery.controllers.main import TsBatteryPlayer, after_url


def _done_url(attempt):
    if attempt.ts_battery():
        return after_url(attempt, submitted=True)
    return '/my/assessments/%s?submitted=1' % attempt.id


class TsTaskPlayer(TsBatteryPlayer):

    @http.route()
    def take(self, token, page=None, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if attempt.ts_is_task() and attempt.state == 'in_progress':
            earlier = attempt.ts_battery_earlier_open() if attempt.ts_battery() else False
            if earlier:
                return request.redirect('/take/%s' % earlier.access_token)      # instruments in battery order
            cfg = attempt.ts_task_config()
            if cfg['current'] is None:                                           # every block closed, not yet scored
                try:
                    attempt.action_submit()
                except UserError:
                    pass
                return request.redirect(_done_url(attempt))
            return request.render('ts_tasks.player', {
                'attempt': attempt, 'inst': attempt.instrument_id, 'cfg': cfg, 'fa': fa_digits,
                'cfg_json': json.dumps(cfg, ensure_ascii=False), 'page_name': 'ts_assessments'})
        return super().take(token, page=page, **kw)

    @http.route()
    def battery_next(self, token, **kw):
        res = super().battery_next(token, **kw)
        qc = getattr(res, 'qcontext', None)
        if qc and qc.get('nxt') and qc['nxt'].ts_is_task():
            qc['matrix'] = True          # the transition page then shows «۳ بخش زمان‌دار · حدود ۱۲ دقیقه»
        return res

    @http.route()
    def catalog(self, **kw):
        res = super().catalog(**kw)
        qc = getattr(res, 'qcontext', None)
        if qc and qc.get('groups'):
            qc['groups'] = [(g, [i for i in insts if not i.invite_only]) for g, insts in qc['groups']]
            qc['groups'] = [(g, insts) for g, insts in qc['groups'] if insts]
            qc['count'] = sum(len(i) for _, i in qc['groups'])
        return res

    @http.route()
    def detail(self, slug, **kw):
        inst = request.env['ts.instrument'].sudo().search([('slug', '=', slug)], limit=1)
        if inst and inst.invite_only:
            raise request.not_found()
        return super().detail(slug, **kw)

    @http.route()
    def start(self, slug, **kw):
        inst = request.env['ts.instrument'].sudo().search([('slug', '=', slug)], limit=1)
        if inst and inst.invite_only:
            raise request.not_found()
        return super().start(slug, **kw)

    # ------------------------------------------------------------------ JSON-ish endpoints (form POST + CSRF)
    def _task(self, token):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if not attempt.ts_is_task():
            raise request.not_found()
        return attempt

    @http.route('/take/<string:token>/task/start', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def task_start(self, token, i=None, **kw):
        attempt = self._task(token)
        try:
            out = attempt.ts_task_start(int(i))
        except (UserError, ValueError, TypeError) as e:
            return request.make_json_response({'ok': False, 'error': str(e)}, status=400)
        out['ok'] = True
        return request.make_json_response(out)

    @http.route('/take/<string:token>/task/answer', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def task_answer(self, token, i=None, idx=None, c=None, rt=None, **kw):
        attempt = self._task(token)
        try:
            out = attempt.ts_task_answer(int(i), int(idx), int(c), int(rt or 0))
        except (UserError, ValueError, TypeError) as e:
            return request.make_json_response({'ok': False, 'error': str(e)}, status=400)
        return request.make_json_response(out, status=200 if out.get('ok') else 409)

    @http.route('/take/<string:token>/task/finish', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def task_finish(self, token, i=None, responses=None, focus_lost=0, **kw):
        attempt = self._task(token)
        try:
            resp = json.loads(responses) if responses else None
            if resp is not None and not isinstance(resp, list):
                raise ValueError('responses')
            out = attempt.ts_task_finish(int(i), responses=resp, focus_lost=int(focus_lost or 0))
        except (UserError, ValueError, TypeError) as e:
            return request.make_json_response({'ok': False, 'error': str(e)}, status=400)
        out['ok'] = True
        if out.get('next') is None:
            out['url'] = _done_url(attempt)
        return request.make_json_response(out)
