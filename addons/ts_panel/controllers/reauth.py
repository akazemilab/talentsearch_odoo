import time

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_sms.controllers.signup import safe_next

from .base import reauth_minutes

MAX_PASSWORD_FAILS = 5
REASONS = {
    'nophone': 'برای حساب شما شمارهٔ موبایل تأییدشده‌ای ثبت نیست؛ با رمز عبور تأیید کنید.',
    'cooldown': 'کد تازه‌ای همین الان فرستاده شد. یک دقیقه صبر کنید.',
    'limit': 'تعداد درخواست کد زیاد بوده است. بعداً دوباره تلاش کنید.',
    'send': 'ارسال پیامک ممکن نشد. کمی بعد دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.',
}
VERIFY_REASONS = {
    'none': 'کدی درخواست نشده است. «ارسال کد» را بزنید.',
    'expired': 'کد منقضی شده است. کد تازه بگیرید.',
    'attempts': 'تعداد تلاش‌ها تمام شد. کد تازه بگیرید.',
    'wrong': 'کد درست نیست. دوباره وارد کنید.',
}


def _mask(phone):
    return '*' * 7 + phone[-4:]


class TsPanelReauth(http.Controller):

    @http.route('/my/reauth', type='http', auth='user', website=True, sitemap=False)
    def page(self, **kw):
        _ts_site_or_404()
        user = request.env.user
        phone = request.env['ts.reauth.code'].ts_phone_of(user)
        sent = request.session.get('ts_reauth_sent')
        return request.render('ts_panel.reauth', {
            'next': safe_next(kw.get('next')), 'why': request.session.get('ts_reauth_why') or 'این کار',
            'phone_masked': _mask(phone) if phone else None, 'sent': bool(sent and phone),
            'flash_err': request.session.pop('ts_flash', None), 'minutes': reauth_minutes(),
            'page_name': 'ts_panel_reauth'})

    @http.route('/my/reauth/send', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def send(self, **post):
        _ts_site_or_404()
        nxt = safe_next(post.get('next'))
        ok, reason = request.env['ts.reauth.code'].ts_request(request.env.user)
        if ok:
            request.session['ts_reauth_sent'] = True
        else:
            request.session['ts_flash'] = REASONS.get(reason, REASONS['send'])
        return request.redirect('/my/reauth?next=' + _q(nxt))

    @http.route('/my/reauth/verify', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def verify(self, **post):
        _ts_site_or_404()
        user = request.env.user
        nxt = safe_next(post.get('next'))
        good, reason = False, None
        if request.env['ts.reauth.code'].ts_phone_of(user):
            good, reason = request.env['ts.reauth.code'].ts_verify(user, post.get('code'))
            reason = VERIFY_REASONS.get(reason)
        else:
            now = time.time()
            fails = [t for t in request.session.get('ts_reauth_fails', []) if now - t < 600]
            if len(fails) >= MAX_PASSWORD_FAILS:
                reason = 'تعداد تلاش‌ها زیاد بود. چند دقیقه بعد دوباره تلاش کنید.'
            else:
                try:
                    user._check_credentials({'type': 'password', 'password': post.get('password') or ''},
                                            {'interactive': True})
                    good = True
                except AccessDenied:
                    fails.append(now)
                    reason = 'رمز عبور درست نیست.'
                request.session['ts_reauth_fails'] = fails
        if not good:
            request.session['ts_flash'] = reason or 'تأیید انجام نشد.'
            request.env['ts.audit.event'].sudo().log_denied('auth.reauth_fail', route=request.httprequest.path)
            return request.redirect('/my/reauth?next=' + _q(nxt))
        request.session['ts_reauth_at'] = time.time()
        request.session['ts_reauth_uid'] = user.id
        request.session.pop('ts_reauth_sent', None)
        request.session.pop('ts_reauth_why', None)
        request.env['ts.audit.event'].sudo().log('auth.reauth', method='code' if request.env['ts.reauth.code'].ts_phone_of(user) else 'password')
        return request.redirect(nxt)


def _q(path):
    from urllib.parse import quote
    return quote(path, safe='/')
