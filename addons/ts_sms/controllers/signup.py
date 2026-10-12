"""S-AUTH (onb1): one sign-in for talentsearch.ir, by mobile number and a 6-digit code.

Two states on one page (number, then code). Without JavaScript every step is a normal form POST and a redirect, as before;
with JavaScript the same endpoints answer JSON (header X-TS-Auth: 1) and the page switches state without a reload.
New people get an account straight after the code (no name step): the name stays unknown until they give one where it
is needed (panel, colleague invite, account page). Internal (staff) accounts are never signed in or duplicated by a
code. «این دستگاه شخصی من است» (default on) keeps a portal session for 30 days; off = a browser-session cookie
(models/ir_http.py). Website 4 only: stock /web/login (email) stays reachable as the quiet second way.
"""
from urllib.parse import quote

from odoo import fields, http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.http import request
from odoo.http.session import authenticate

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits

from ..models.res_partner import fmt_mobile
from .main import MESSAGES

MESSAGES = dict(MESSAGES, **{
    'sent': ('ok', 'کد ۶ رقمی را فرستادیم.'),
    'resent': ('ok', 'کد تازه را فرستادیم.'),
    'short': ('warn', 'کد ۶ رقمی است.'),
    'wrong': ('warn', 'این کد درست نیست. دوباره امتحان کنید.'),
    'expired': ('warn', 'این کد منقضی شده؛ کد تازه بگیرید.'),
    'attempts': ('warn', 'این کد چند بار نادرست وارد شد؛ کد تازه بگیرید.'),
    'locked': ('warn', 'چند بار کد نادرست وارد شد. برای امنیت حساب، ۱۵ دقیقهٔ دیگر دوباره امتحان کنید.'),
    'none': ('warn', 'اول شمارهٔ موبایل را بنویسید و کد بگیرید.'),
    'staff': ('warn', 'این شماره به حساب کارکنان وصل است؛ از ورود با ایمیل استفاده کنید.'),
    'inactive': ('warn', 'حساب این شماره غیرفعال است. برای فعال‌شدن دوباره با پشتیبانی تماس بگیرید.'),
    'expired_session': ('warn', 'مهلت ورود تمام شد؛ دوباره با شمارهٔ موبایل شروع کنید.'),
})
PERSONAL_KEY = 'ts_auth_personal'       # the «این دستگاه شخصی من است» choice, until the code is verified
RESENDS_KEY = 'ts_auth_resends'         # how many times a code was asked again for the current number
HELP_AFTER_RESENDS = 2


def safe_next(value):
    """Only a local path; anything else (other hosts, protocol-relative, backslashes) falls back to /my."""
    v = (value or '').strip()
    if v.startswith('/') and not v.startswith('//') and '\\' not in v and '\n' not in v and '\r' not in v:
        return v[:300]
    return '/my'


def signin_url(nxt):
    """The one sign-in address of talentsearch.ir (S-AUTH) with a return path."""
    nxt = safe_next(nxt)
    return '/signup' if nxt == '/my' else '/signup?next=%s' % quote(nxt, safe='/')


# Why the person is asked to sign in, keyed on where they came from (UX audit G1-P8-1, PT-4).
WHY = [
    ('/my/workspaces/new', 'برای ساخت پنل، اول وارد شوید؛ بعد به فرم ساخت پنل برمی‌گردید.'),
    ('/invite/', 'برای پاسخ‌دادن به دعوت، اول وارد شوید؛ بعد به همان دعوت برمی‌گردید.'),
    ('/c/', 'برای پاسخ‌دادن به دعوت، اول وارد شوید؛ بعد به همان دعوت برمی‌گردید.'),
    ('/join/', 'برای پیوستن به پنل، اول وارد شوید؛ بعد به همان دعوت برمی‌گردید.'),
    ('/assessments/', 'پاسخ‌ها و نتیجه در حساب شما ذخیره می‌شود؛ بعد از ورود به همان سنجه برمی‌گردید.'),
    ('/take/', 'پاسخ‌ها و نتیجه در حساب شما ذخیره می‌شود؛ بعد از ورود به همان سنجه برمی‌گردید.'),
]


def why_for(nxt):
    for prefix, text in WHY:
        if (nxt or '').startswith(prefix):
            return text
    if nxt and nxt not in ('/my', '/'):
        return 'بعد از ورود به همان صفحه‌ای برمی‌گردید که در آن بودید.'
    return None


def _enabled():
    c = request.env.company.sudo()
    return bool(c.kv_enabled and c.ts_sms_otp)


def _ts_site():
    website = request.env.website
    return bool(website and website._ts_is_current())


def _ajax():
    return request.httprequest.headers.get('X-TS-Auth') == '1'


def signin_values(step, msg=None, nxt='/my', edit=False):
    """Render values of ts_sms.signup (also used by /web/login on talentsearch.ir)."""
    phone = request.session.get('ts_signup_phone') or ''
    Otp = request.env['ts.signup.otp']
    return {
        'enabled': _enabled(), 'step': step, 'msg': MESSAGES.get(msg), 'msg_key': msg or '', 'next': nxt,
        'next_q': quote(nxt, safe='/'), 'why': why_for(nxt),
        'phone': phone, 'phone_fa': fmt_mobile(phone) if phone else '',
        'phone_prefill': fa_digits(phone) if (phone and edit) else '',
        'personal': request.session.get(PERSONAL_KEY, True),
        'wait': Otp.seconds_to_resend(phone) if (phone and step == 'code') else 0,
        'resends': request.session.get(RESENDS_KEY, 0),
        'help_after': HELP_AFTER_RESENDS,
        'email_url': ('/web/login?redirect=%s&email=1' % quote(nxt, safe='/')) if nxt != '/my' else '/web/login?email=1',
        'page_name': 'ts_signup',
    }


class TsSignup(http.Controller):

    def _page(self, step, msg=None, nxt='/my', edit=False):
        return request.render('ts_sms.signup', signin_values(step, msg, nxt, edit))

    def _login(self, user, personal=True):
        token = request.env['ts.login.token'].sudo().issue(user)
        authenticate(request.session, request.env, {'type': 'ts_phone_login', 'login': user.login, 'token': token})
        # read by ir.http._post_dispatch: 30-day cookie on a personal device, a browser-session cookie otherwise
        request.session['ts_session_mode'] = 'long' if personal else 'browser'

    def _reply(self, ok, state, msg, nxt, url=None, **extra):
        """JSON for the script, a redirect without it."""
        if _ajax():
            phone = request.session.get('ts_signup_phone') or ''
            m = MESSAGES.get(msg)
            data = {'ok': ok, 'state': state, 'msg': m[1] if m else '', 'tone': m[0] if m else '', 'key': msg or '',
                    'redirect': url, 'phone_fa': fmt_mobile(phone) if phone else '',
                    'wait': request.env['ts.signup.otp'].seconds_to_resend(phone) if phone else 0,
                    'resends': request.session.get(RESENDS_KEY, 0), 'help_after': HELP_AFTER_RESENDS}
            data.update(extra)
            return request.make_json_response(data)
        if url:
            return request.redirect(url)
        q = quote(nxt, safe='/')
        return request.redirect('/signup?%smsg=%s&next=%s' % ('step=code&' if state == 'code' else '', msg or '', q))

    @http.route(['/signup', '/login'], type='http', auth='public', website=True, sitemap=False)
    def signup(self, step=None, msg=None, **kw):
        _ts_site_or_404()
        nxt = safe_next(kw.get('next'))
        if not request.env.user._is_public():
            return request.redirect(nxt)
        if step == 'code' and request.session.get('ts_signup_phone'):
            return self._page('code', msg, nxt)
        return self._page('phone', msg, nxt, edit=bool(kw.get('edit')))

    @http.route('/signup/send', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def send(self, phone=None, **post):
        _ts_site_or_404()
        nxt = safe_next(post.get('next'))
        if 'personal' in post or 'personal_shown' in post:
            request.session[PERSONAL_KEY] = post.get('personal') == '1'
        resend = post.get('resend') == '1'
        if resend and not phone:
            phone = request.session.get('ts_signup_phone')
        before = request.session.get('ts_signup_phone')
        ok, reason, norm = request.env['ts.signup.otp'].request_code(phone, request.httprequest.remote_addr)
        if norm and norm != before:
            request.session[RESENDS_KEY] = 0
        if ok:
            request.session['ts_signup_phone'] = norm
            if resend:
                request.session[RESENDS_KEY] = request.session.get(RESENDS_KEY, 0) + 1
            return self._reply(True, 'code', 'resent' if resend else 'sent', nxt)
        if reason in ('cooldown', 'limit', 'locked') and norm:
            request.session['ts_signup_phone'] = norm
            return self._reply(False, 'code', reason, nxt)
        return self._reply(False, 'phone', reason, nxt)

    @http.route('/signup/verify', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def verify(self, code=None, **post):
        _ts_site_or_404()
        nxt = safe_next(post.get('next'))
        phone = request.session.get('ts_signup_phone')
        if not phone:
            return self._reply(False, 'phone', 'none', nxt)
        ok, reason = request.env['ts.signup.otp'].verify_code(phone, code)
        if not ok:
            return self._reply(False, 'code', reason, nxt)
        owners = request.env['res.users'].ts_phone_owner(phone)
        personal = request.session.get(PERSONAL_KEY, True)
        for key in ('ts_signup_phone', RESENDS_KEY, PERSONAL_KEY, 'ts_signup_ok'):
            request.session.pop(key, None)
        if owners.filtered(lambda u: not u.share):
            # a staff (internal) account holds this number: never signed in by code, never duplicated
            request.env['ts.audit.event'].sudo().log('account.login_phone_refused', None, why='internal')
            return self._reply(False, 'phone', 'staff', nxt)
        active = owners.filtered(lambda u: u.active)
        if not active and owners:
            return self._reply(False, 'phone', 'inactive', nxt)
        if active:
            # a number linked to an email account (ts_phone) or a mobile account (login): the most recently verified
            user = active.sorted(lambda u: (u.partner_id.ts_phone == phone, u.partner_id.ts_phone_verified_at or fields.Datetime.from_string('2000-01-01')),
                                 reverse=True)[0]
            request.env['ts.audit.event'].sudo().log('account.login_phone', user)
        else:
            user = self._create_user(phone)
            request.env['ts.audit.event'].sudo().log('account.signup_phone', user)
        self._login(user, personal=personal)
        return self._reply(True, 'done', None, nxt, url=nxt)

    def _create_user(self, phone):
        """A portal account from the verified mobile alone. The name is unknown: `name` holds the formatted number for
        the back office, and the site asks for a real name only where others will see it."""
        Users = request.env['res.users'].sudo().with_context(no_reset_password=True, ts_name_placeholder=True)
        user = Users.create({
            'name': fmt_mobile(phone, persian=False), 'login': phone,
            'group_ids': [(6, 0, [request.env.ref('base.group_portal').id])],
        })
        user.partner_id.sudo().with_context(ts_name_placeholder=True).write({
            'phone': phone, 'ts_phone': phone, 'ts_phone_verified_at': fields.Datetime.now(), 'ts_name_unknown': True})
        return user


class TsAuthSiteHome(AuthSignupHome):
    """talentsearch.ir only: the stock pages lead to S-AUTH. eot.ir (website 1) and the back office are untouched."""

    @http.route()
    def web_login(self, redirect=None, **kw):
        # only while mobile codes can be sent: with SMS switched off the stock e-mail sign-in stays the way in
        if (request.httprequest.method == 'GET' and not request.session.uid and _ts_site() and _enabled()
                and not kw.get('email') and not kw.get('login') and not kw.get('error')):
            # shown in place (not redirected) so a returning visitor, a link from an e-mail or a stock "please sign in"
            # redirect all land on the one sign-in; «با ایمیل ثبت‌نام کرده بودید؟» leads back here with email=1
            nxt = safe_next(redirect)
            values = signin_values('phone', None, nxt)
            response = request.render('ts_sms.signup', values)
            response.headers['Cache-Control'] = 'no-cache'
            return response
        return super().web_login(redirect=redirect, **kw)

    @http.route()
    def web_auth_signup(self, *args, **kw):
        # e-mail sign-up stays only for a colleague invitation bound to an e-mail address (/join/...) and for Odoo's
        # own signup tokens; everyone else signs up with the mobile code
        if request.httprequest.method == 'GET' and _ts_site() and _enabled() and not kw.get('token') \
                and not (kw.get('redirect') or '').startswith('/join/'):
            return request.redirect(signin_url(kw.get('redirect')))
        return super().web_auth_signup(*args, **kw)
