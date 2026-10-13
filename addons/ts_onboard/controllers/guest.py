"""O3: test first for individuals (design §5 P1): the starter test answered before any account, the result kept with the
mobile number.

/start (and /start/<slug> for a guest-ok instrument) is one screen: what it measures, statements, minutes, «پاسخ‌ها فقط
برای خودتان است…», the button «۱۸ سال یا بیشتر دارم؛ موافقم و شروع می‌کنم» (adult age and service consent), an unticked
research box, and «کمتر از ۱۸ سال دارم» (no guest attempt for minors: /start/under-18 sends them to their school or
counselor). A signed-in visitor goes straight into an ordinary attempt.

The guest player /start/q* renders the ordinary player and review pages with this address; the attempt is found only
through the signed HttpOnly cookie (never a token in an address). Limits per hashed address: 5 new guest attempts an hour
(ts_onboard.guest_per_hour), 200 saved answers a minute (ts_onboard.answers_per_minute); one open guest attempt per
browser. At the end /start/result shows «نتیجه‌تان آماده است.» with the sign-in inline; the sign-in claims the attempt
(controllers/auth.py) and opens the report. The first answer and the end are counted in the funnel by the attempt model
(models/attempt.py), for every player."""
from urllib.parse import quote

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _page_of, _page_start, _pages, _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION, fa_digits
from odoo.addons.ts_assessment.models.instrument import SCALE
from odoo.addons.ts_sms.controllers.signup import signin_values
from odoo.addons.ts_tasks.controllers.main import TsTaskPlayer

from ..models.common import GUEST_COOKIE, GUEST_COOKIE_AGE, digest, drop_cookie, new_token, set_cookie
from .auth import claim_url, guest_attempt

GUEST_PER_HOUR = 5
ANSWERS_PER_MINUTE = 200


def _funnel(step, inst):
    request.env['ts.funnel.event'].ts_log(request, step, instrument=inst)


def _ip():
    return request.env['ts.audit.event'].sudo()._hash_ip(request.httprequest.remote_addr)


def _answers_ok():
    """200 saved guest answers a minute per hashed address (a person answers far slower; a script does not)."""
    limit = request.env['ir.config_parameter'].sudo().get_int('ts_onboard.answers_per_minute', ANSWERS_PER_MINUTE) \
        or ANSWERS_PER_MINUTE
    return request.env['ts.rate.hit'].ts_hit('answer:%s' % _ip(), limit, 60)


def _slow(**values):
    resp = request.render('ts_onboard.slow', dict({'page_name': 'ts_slow'}, **values), status=429)
    resp.headers['Retry-After'] = '60'
    return resp


def _instrument(slug=None):
    Inst = request.env['ts.instrument'].sudo()
    inst = Inst.search([('slug', '=', slug), ('state', '=', 'published')], limit=1) if slug else Inst.ts_starter()
    if not inst or not inst.ts_guest_ready():
        raise request.not_found()
    return inst


class TsOnbGuest(http.Controller):

    # ------------------------------------------------------------------ the start screen
    @http.route(['/start', '/start/<string:slug>'], type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def start_page(self, slug=None, **kw):
        _ts_site_or_404()
        inst = _instrument(slug)
        public = request.env.user._is_public()
        mine = request.env['ts.attempt']
        guest = guest_attempt() if public else mine
        if not public:
            mine = request.env['ts.attempt'].sudo().search([
                ('user_id', '=', request.env.user.id), ('instrument_id', '=', inst.id),
                ('state', 'in', ('consent', 'in_progress')), ('version_id', '=', inst.current_version_id.id)], limit=1)
        _funnel('start_view', inst)
        return request.render('ts_onboard.start', {
            'inst': inst, 'public': public, 'guest': guest, 'mine': mine, 'fa': fa_digits, 'error': kw.get('error'),
            'consent_version': CONSENT_VERSION, 'page_name': 'ts_start'})

    @http.route('/start/under-18', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def under18(self, **kw):
        _ts_site_or_404()
        return request.render('ts_onboard.under18', {'page_name': 'ts_start'})

    @http.route('/start/<string:slug>/go', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def start_go(self, slug, **post):
        _ts_site_or_404()
        inst = _instrument(slug)
        research = post.get('consent_research') == '1'
        user = request.env.user
        Att = request.env['ts.attempt'].sudo()
        if not user._is_public():
            # a signed-in visitor: an ordinary attempt, the same one-tap consent (adult, service, optional research)
            at = Att.search([('user_id', '=', user.id), ('instrument_id', '=', inst.id), ('state', 'in', ('consent', 'in_progress')),
                             ('version_id', '=', inst.current_version_id.id)], limit=1) or Att.create(
                {'user_id': user.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
            if at.state == 'consent':
                at.give_consent(research=research, role='self')
            _funnel('start', inst)
            return request.redirect('/take/%s' % at.access_token)
        open_guest = guest_attempt()
        if open_guest and open_guest.state in ('consent', 'in_progress'):
            return request.redirect('/start/q')           # one open guest attempt per browser
        if open_guest and open_guest.state == 'done':
            return request.redirect('/start/result')
        limit = request.env['ir.config_parameter'].sudo().get_int('ts_onboard.guest_per_hour', GUEST_PER_HOUR) or GUEST_PER_HOUR
        if not request.env['ts.rate.hit'].ts_hit('guest:%s' % _ip(), limit, 3600):
            return _slow(guest_limit=True)
        raw, cookie = new_token(request.env, 'guest')
        at = Att.create({'user_id': user.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id,
                         'ts_guest': True, 'ts_guest_hash': digest(raw), 'ts_guest_seen': fields.Datetime.now()})
        at.ts_guest_consent(research=research)
        _funnel('start', inst)
        return set_cookie(request.redirect('/start/q'), request, GUEST_COOKIE, cookie, GUEST_COOKIE_AGE)

    # ------------------------------------------------------------------ the guest player (cookie only)
    def _mine(self):
        at = guest_attempt()
        if not at or not request.env.user._is_public():
            return None
        return at

    def _values(self, at, **extra):
        values = {'attempt': at, 'inst': at.instrument_id, 'fa': fa_digits, 'take_url': '/start/q', 'guest': True,
                  'tu': False, 'page_name': 'ts_start'}
        values.update(extra)
        return values

    @http.route('/start/q', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def guest_take(self, page=None, **kw):
        _ts_site_or_404()
        at = self._mine()
        if not at:
            return request.redirect('/start')
        if at.state == 'done':
            return request.redirect('/start/result')
        if at.state != 'in_progress':
            return request.redirect('/start')
        items, n_pages = _pages(at)
        answers = at.answers_map()
        n_items = len(items)
        if page is None or not str(page).isdigit():
            first_open = next((idx for idx, it in enumerate(items) if it.id not in answers), 0)
            page = _page_of(first_open, n_items)
        page = min(max(int(page), 1), n_pages)
        # the same balanced paging as /take (5 items per page at most, take1)
        start, end = _page_start(page, n_items), _page_start(page + 1, n_items) if page < n_pages else n_items
        chunk = items[start:end]
        chunk_ids = set(chunk.ids)
        minutes = at.instrument_id.duration_minutes or 0
        return request.render('ts_assessment.player', self._values(
            at, items=chunk, answers=answers, page=page, n_pages=n_pages, scale=SCALE, first_index=start,
            answered=len(answers), total=n_items, error=kw.get('error'),
            missing_elsewhere=len([it for it in items if it.id not in answers and it.id not in chunk_ids]),
            show_missing=bool(kw.get('missing')),
            minutes_left=-(-(n_items - len(answers)) * minutes // n_items) if (n_items and minutes) else 0))

    @http.route('/start/q/answer', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def guest_answer(self, item=None, value=None, **kw):
        _ts_site_or_404()
        at = self._mine()
        if not at:
            return request.make_json_response({'ok': False, 'error': 'no attempt'}, status=404)
        if not _answers_ok():
            return request.make_json_response({'ok': False, 'error': 'slow'}, headers=[('Retry-After', '60')], status=429)
        try:
            at.save_answer(int(item), int(value))
        except (UserError, ValueError, TypeError) as e:
            return request.make_json_response({'ok': False, 'error': str(e)}, status=400)
        at.ts_guest_touch()
        return request.make_json_response({'ok': True, 'answered': len(at.answer_ids), 'total': at.version_id.active_item_count})

    @http.route('/start/q/page', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def guest_page(self, **post):
        _ts_site_or_404()
        at = self._mine()
        if not at or at.state != 'in_progress':
            return request.redirect('/start/q' if at else '/start')
        if not _answers_ok():
            return _slow()
        for key, value in post.items():
            if key.startswith('q_') and value:
                try:
                    at.save_answer(int(key[2:]), int(value))
                except (UserError, ValueError):
                    pass
        at.ts_guest_touch()
        page = int(post.get('page') or 1) if str(post.get('page') or '1').isdigit() else 1
        go = post.get('go')
        if go == 'prev':
            return request.redirect('/start/q?page=%d' % (page - 1))
        if go == 'review':
            return request.redirect('/start/q/review')
        return request.redirect('/start/q?page=%d' % (page + 1))

    @http.route('/start/q/review', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def guest_review(self, **kw):
        _ts_site_or_404()
        at = self._mine()
        if not at or at.state != 'in_progress':
            return request.redirect('/start/q' if at else '/start')
        items, n_pages = _pages(at)
        answers = at.answers_map()
        n_items = len(items)
        missing = [(idx + 1, it, _page_of(idx, n_items)) for idx, it in enumerate(items) if it.id not in answers]
        page_rows = []
        for p in range(1, n_pages + 1):
            start = _page_start(p, n_items)
            end = _page_start(p + 1, n_items) if p < n_pages else n_items
            page_rows.append({'page': p, 'first': start + 1, 'last': end, 'missing': [m for m in missing if m[2] == p]})
        return request.render('ts_assessment.review', self._values(
            at, missing=missing, total=n_items, answered=len(answers), n_pages=n_pages, page_rows=page_rows,
            error=kw.get('error')))

    @http.route('/start/q/submit', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def guest_submit(self, **post):
        _ts_site_or_404()
        at = self._mine()
        if not at:
            return request.redirect('/start')
        if at.state != 'done':
            try:
                ok = at.action_submit()
            except UserError:
                return request.redirect('/start/q/review?error=missing')
            if not ok:
                return request.redirect('/start/q')
            at.ts_guest_touch()
        return request.redirect('/start/result')

    # ------------------------------------------------------------------ the result gate
    @http.route('/start/result', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def gate(self, step=None, msg=None, **kw):
        _ts_site_or_404()
        at = guest_attempt()
        if not at:
            return request.redirect('/start')
        if at.state != 'done':
            return request.redirect('/start/q')
        _funnel('gate_view', at.instrument_id)
        if not request.env.user._is_public():
            return request.render('ts_onboard.gate_signed', {'at': at, 'inst': at.instrument_id, 'page_name': 'ts_start'})
        st = 'code' if (step == 'code' and request.session.get('ts_signup_phone')) else 'phone'
        values = signin_values(st, msg, '/start/result')
        values.update(gate=True, gate_inst=at.instrument_id, why=None)
        return request.render('ts_sms.signup', values)

    @http.route('/start/claim', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def claim(self, **post):
        """A visitor already signed in (another tab) keeps the result of this browser's guest attempt."""
        _ts_site_or_404()
        at = guest_attempt()
        if not at:
            return request.redirect('/my/assessments')
        if at.ts_guest_claim(request.env.user):
            _funnel('gate_signed_in', at.instrument_id)
        return drop_cookie(request.redirect(claim_url(at)), request, GUEST_COOKIE)


class TsOnbCatalog(TsTaskPlayer):
    """The detail page's «شروع سنجه» of a guest-ok instrument goes to its start screen (no sign-in first); the report of a
    claimed guest attempt counts one funnel step and offers the name, the next instrument and sharing."""

    @http.route()
    def detail(self, slug, **kw):
        res = super().detail(slug, **kw)
        qc = getattr(res, 'qcontext', None)
        inst = qc and qc.get('inst')
        if inst and inst.ts_guest_ready():
            qc['start_url'] = '/start/%s' % quote(inst.slug)
            qc['ts_guest_start'] = True
        return res

    @http.route()
    def my_report(self, attempt_id, **kw):
        res = super().my_report(attempt_id, **kw)
        qc = getattr(res, 'qcontext', None)
        at = qc and qc.get('attempt')
        if at and at.ts_guest_claimed_at:
            if kw.get('claimed'):
                _funnel('report_view', at.instrument_id)
            qc['ts_claimed'] = True
            qc['ts_name_unknown'] = bool(request.env.user.partner_id.ts_name_unknown)
            qc['ts_next_url'] = '/assessments'
        return res

    @http.route('/my/assessments/<int:attempt_id>/name', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def report_name(self, attempt_id, **post):
        """«نامی که روی گزارش بیاید (اختیاری)»: the person's own entry, written only while the account has no name."""
        _ts_site_or_404()
        at = request.env['ts.attempt'].sudo().search([('id', '=', int(attempt_id)), ('user_id', '=', request.env.user.id)], limit=1)
        if not at:
            raise request.not_found()
        name = ' '.join((post.get('name') or '').split())[:80]
        partner = request.env.user.partner_id.sudo()
        if name and partner.ts_name_unknown:
            partner.with_context(ts_name_placeholder=False).write({'name': name, 'ts_name_unknown': False})
            request.env['ts.audit.event'].sudo().log('account.name_set', request.env.user, where='report')
        return request.redirect('/my/assessments/%s' % at.id)
