"""Free career match pages: /career (start), /career/go (one-tap start), /career/start, /career/r (background + results),
/career/job/<code>, /career/more/<kind> (optional personality / ability modules), /career/remind (SMS reminders on/off),
/career/c/<code> (the link of a reminder SMS). Every finished module comes back to /career/r.

Completion (docs/career/01_completion.md):
* B - the interests start before any account: /career/go is the one-tap consent of an adult («۱۸ سال یا بیشتر دارم؛ شروع
  آزمون»), a visitor answers as a guest (ts_onboard's guest player, cookie only) and gives the mobile number when the 60
  answers are in («نتیجه‌تان آماده است»); the claim makes the run (models/career.py).
* C - one item at a time (ts_player.js card mode), 30 items a page: a page end is a pause. The last page ends straight in
  the result when nothing is missing (no review screen); «بعداً ادامه می‌دهم» saves and goes back to the career page.
* A - reminders (models/nudge.py) and the funnel steps career_view, career_start, bg_done, result_view, nudge_back."""
from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _my_attempt, _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_brand.models.short import CODE_RE
from odoo.addons.ts_onboard.controllers.auth import guest_attempt
from odoo.addons.ts_onboard.controllers.guest import GUEST_PER_HOUR, TsOnbCatalog, TsOnbGuest, _ip, _slow
from odoo.addons.ts_onboard.models.common import GUEST_COOKIE, GUEST_COOKIE_AGE, digest, new_token, set_cookie

from ..models.career import (EDU, EXP, HEX_CODE, IP_CODE, ONET_NOTICE, RIASEC_FA, RIASEC_GLOSS, E)

PAGE = 20
SMS_KEY = 'tsc_sms'          # this session came in through a reminder SMS: the pages offer «خاموش کردن یادآوری»
CODE_LOOKUPS_PER_MINUTE = 20


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


def _funnel(step, inst=None):
    request.env['ts.funnel.event'].ts_log(request, step, instrument=inst)


def _ip_inst():
    return request.env['ts.instrument'].sudo().search([('code', '=', IP_CODE), ('state', '=', 'published')], limit=1)


def _guest_ip():
    """This browser's guest interests (any state), or an empty recordset."""
    at = guest_attempt()
    return at if (at and at.instrument_id.code == IP_CODE) else request.env['ts.attempt']


class TsCareer(TsOnbCatalog):

    @http.route('/career', type='http', auth='public', website=True, sitemap=_sitemap_career)
    def career_home(self, **kw):
        _ts_site_or_404()
        public = request.env.user._is_public()
        run = None if public else _run()
        guest = _guest_ip() if public else request.env['ts.attempt']
        full = request.env['ts.career.run'].ts_cap_reached() and not run and not guest
        inst = _ip_inst()
        _funnel('career_view', inst)
        st = run.ts_state() if run else None
        return request.render('ts_career.home', {
            'run': run, 'st': st, 'guest': guest, 'full': full, 'public': public, 'fa': fa_digits, 'notice': ONET_NOTICE,
            'inst': inst, 'minutes': run.ts_minutes_left(IP_CODE) if run else (inst.duration_minutes if inst else 8),
            'sms': bool(request.session.get(SMS_KEY))})

    @http.route('/career/go', type='http', auth='public', website=True, sitemap=False, methods=['POST'])
    def career_go(self, **post):
        """«۱۸ سال یا بیشتر دارم؛ شروع آزمون»: adult, service consent (research only when ticked), reminders as the box
        says (ticked by default). A visitor answers as a guest; a signed-in person in the ordinary player."""
        _ts_site_or_404()
        research = post.get('consent_research') == '1'
        remind = post.get('remind') == '1'
        inst = _ip_inst()
        if not inst:
            return request.redirect('/career')
        user = request.env.user
        Att = request.env['ts.attempt'].sudo()
        if not user._is_public():
            run = _run()
            if not run:
                if request.env['ts.career.run'].ts_cap_reached():
                    return request.redirect('/career')
                run = _run(create=True)
            run.ts_set_remind(remind)
            if run.ts_state()['ip_done']:
                return request.redirect('/career/r')
            at = run.ts_ensure_attempt(IP_CODE)
            if at.state == 'consent':
                at.give_consent(research=research, role='self')
            _funnel('career_start', inst)
            return request.redirect('/take/%s' % at.access_token)
        guest = _guest_ip()
        if guest and guest.state in ('consent', 'in_progress'):
            return request.redirect('/start/q')                 # one open guest attempt per browser
        if guest and guest.state == 'done':
            return request.redirect('/start/result')
        if request.env['ts.career.run'].ts_cap_reached():
            return request.redirect('/career')
        limit = request.env['ir.config_parameter'].sudo().get_int('ts_onboard.guest_per_hour', GUEST_PER_HOUR) or GUEST_PER_HOUR
        if not request.env['ts.rate.hit'].ts_hit('guest:%s' % _ip(), limit, 3600):
            return _slow(guest_limit=True)
        raw, cookie = new_token(request.env, 'guest')
        at = Att.create({'user_id': user.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id,
                         'ts_guest': True, 'ts_guest_hash': digest(raw), 'ts_guest_seen': fields.Datetime.now(),
                         'ts_career_remind': remind})
        at.ts_guest_consent(research=research)
        _funnel('career_start', inst)
        return set_cookie(request.redirect('/start/q'), request, GUEST_COOKIE, cookie, GUEST_COOKIE_AGE)

    @http.route('/career/start', type='http', auth='public', website=True, sitemap=False, methods=['GET', 'POST'])
    def career_start(self, **kw):
        """Older links: a visitor starts on /career (one tap, no sign-in first); a signed-in person continues."""
        _ts_site_or_404()
        if request.env.user._is_public():
            return request.redirect('/career')
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
            first = not (run.edu and run.exp)
            run.sudo().write({'edu': kw['edu'], 'exp': kw['exp']})
            if first:
                _funnel('bg_done', _ip_inst())
            return request.redirect('/career/r')
        if not st['bg_done'] or kw.get('edit'):
            return request.render('ts_career.background', {'run': run, 'edu': EDU, 'exp': EXP, 'fa': fa_digits,
                                                           'error': request.httprequest.method == 'POST',
                                                           'sms': bool(request.session.get(SMS_KEY))})
        res = run.ts_result()
        if not run.first_result_at:
            run.sudo().write({'first_result_at': fields.Datetime.now()})
        _funnel('result_view', _ip_inst())
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
            'n_all': len(res['rows']), 'paused': kw.get('paused') == '1',
            'hex_left': run.ts_minutes_left(HEX_CODE), 'sms': bool(request.session.get(SMS_KEY))})

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

    # ------------------------------------------------------------------ reminders: on/off and the SMS link
    @http.route('/career/remind', type='http', auth='user', website=True, sitemap=False, methods=['POST'])
    def career_remind(self, **post):
        _ts_site_or_404()
        run = _run()
        if run:
            on = post.get('on') == '1'
            run.ts_set_remind(on)
            if not on:
                _funnel('remind_off', _ip_inst())
        request.session.pop(SMS_KEY, None)
        back = post.get('back') or ''
        return request.redirect(back if back.startswith('/career') or back.startswith('/take/') else '/career/r')

    @http.route('/career/c/<string:code>', type='http', auth='public', website=True, sitemap=False, methods=['GET'])
    def career_link(self, code, **kw):
        """The link of a reminder SMS: back to the step where this person stopped (sign-in first when needed). Lookups
        are rate-limited per network address; an unknown code just opens /career."""
        _ts_site_or_404()
        if not CODE_RE.match(code or '') or not request.env['ts.rate.hit'].ts_hit('career_code:%s' % _ip(),
                                                                                 CODE_LOOKUPS_PER_MINUTE, 60):
            return request.redirect('/career')
        run = request.env['ts.career.run'].sudo().search([('short_code', '=', code)], limit=1)
        if not run:
            return request.redirect('/career')
        user = request.env.user
        if user._is_public():
            return request.redirect('/signup?next=/career/c/%s' % code)
        if run.user_id != user:
            return request.redirect('/career')
        last = run.nudge_ids.filtered(lambda n: n.state == 'sent').sorted('sent_at', reverse=True)[:1]
        if last and not last.came_back_at:
            last.sudo().write({'came_back_at': fields.Datetime.now()})
            request.env['ts.funnel.event'].ts_log_career('nudge_back', run)
        request.session[SMS_KEY] = run.id
        return request.redirect(run.ts_resume_url())

    # ------------------------------------------------------------------ the player of the career questionnaires
    @http.route()
    def save_page(self, token, **post):
        """«بعداً ادامه می‌دهم» goes back to the career page; the last page goes straight to the result when nothing is
        missing (the end card said the answers are locked by «دیدن نتیجه»)."""
        _ts_site_or_404()
        attempt = _my_attempt(token)
        go = post.get('go')
        if not (attempt.sudo().career_run_id and attempt.state == 'in_progress' and go in ('exit', 'review')):
            return super().save_page(token, **post)
        self._save_posted(attempt, post)
        if go == 'exit':
            return request.redirect('/career/r?paused=1' if attempt.sudo().career_run_id.ts_state()['ip_done'] else '/career')
        if len(attempt.sudo().answer_ids) < attempt.version_id.active_item_count:
            return request.redirect('/take/%s/review' % token)
        try:
            ok = attempt.action_submit(submission_key=attempt.access_token)
        except UserError:
            return request.redirect('/take/%s/review?error=missing' % token)
        if not ok:
            return request.redirect('/take/%s' % token)
        return request.redirect('/my/assessments/%s?submitted=1' % attempt.id)

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


class TsCareerGuest(TsOnbGuest):
    """The guest player for the interests: «بعداً ادامه می‌دهم» goes back to /career (the answers wait 48 hours in this
    browser), and the last page goes straight to «نتیجه‌تان آماده است» when nothing is missing."""

    @http.route()
    def guest_page(self, **post):
        _ts_site_or_404()
        at = self._mine()
        go = post.get('go')
        if not (at and at.state == 'in_progress' and at.instrument_id.code == IP_CODE and go in ('exit', 'review')):
            return super().guest_page(**post)
        for key, value in post.items():
            if key.startswith('q_') and value:
                try:
                    at.save_answer(int(key[2:]), int(value))
                except (UserError, ValueError):
                    pass
        at.ts_guest_touch()
        if go == 'exit':
            return request.redirect('/career')
        if len(at.answer_ids) < at.version_id.active_item_count:
            return request.redirect('/start/q/review')
        try:
            ok = at.action_submit()
        except UserError:
            return request.redirect('/start/q/review?error=missing')
        if not ok:
            return request.redirect('/start/q')
        at.ts_guest_touch()
        return request.redirect('/start/result')
