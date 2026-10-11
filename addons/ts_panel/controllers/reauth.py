import time

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_sms.controllers.signup import safe_next

from odoo.addons.ts_assessment.models.attempt import fa_digits

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
        nxt = safe_next(kw.get('next'))
        return request.render('ts_panel.reauth', {
            'next': nxt, 'cancel': _cancel_url(nxt), 'why': request.session.get('ts_reauth_why') or '',
            'phone_masked': _mask(phone) if phone else None, 'sent': bool(sent and phone),
            'flash_err': request.session.pop('ts_flash', None), 'minutes': reauth_minutes(), 'fa': fa_digits,
            'title': 'تأیید هویت', 'page_name': 'ts_panel_reauth'})

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
        request.session.pop('ts_reauth_cancel', None)
        request.env['ts.audit.event'].sudo().log('auth.reauth', method='code' if request.env['ts.reauth.code'].ts_phone_of(user) else 'password')
        return request.redirect(nxt)


def _cancel_url(nxt):
    """Where «انصراف» goes: the page the person came from (kept for the whole visit, so a wrong code does not lose it),
    never a URL that would itself perform the action (a file download or an export)."""
    from urllib.parse import urlsplit
    ref = request.httprequest.referrer or ''
    parts = urlsplit(ref)
    host = request.httprequest.host
    if ref and parts.netloc == host and parts.path and not parts.path.startswith('/my/reauth'):
        request.session['ts_reauth_cancel'] = [nxt, safe_next(parts.path + ('?' + parts.query if parts.query else ''))]
    kept = request.session.get('ts_reauth_cancel') or []
    cancel = kept[1] if len(kept) == 2 and kept[0] == nxt else None
    if not cancel:
        path = nxt.split('?', 1)[0]
        for tail in ('/download', '/export', '/revoke'):
            if path.endswith(tail):
                path = path[:-len(tail)] or '/my'
        cancel = path if path.startswith('/') else '/my'
    for tail in ('/download', '/audit/export'):
        if cancel.split('?', 1)[0].endswith(tail):
            cancel = cancel.split('?', 1)[0][:-len(tail.rsplit('/', 1)[1]) - 1] or '/my'
    return cancel


def _q(path):
    from urllib.parse import quote
    return quote(path, safe='/')
