"""S-AUTH (onb1): one sign-in for talentsearch.ir, by mobile number and a 6-digit code.

Two states on one page (number, then code). Without JavaScript every step is a normal form POST and a redirect, as before;
with JavaScript the same endpoints answer JSON (header X-TS-Auth: 1) and the page switches state without a reload.
New people get an account straight after the code (no name step): the name stays unknown until they give one where it
is needed (panel, colleague invite, account page). Internal (staff) accounts are never signed in or duplicated by a
code. «این دستگاه شخصی من است» (default on) keeps a portal session for 30 days; off = a browser-session cookie
(models/ir_http.py). Website 4 only: stock /web/login (email) stays reachable as the quiet second way.

onb2: a number the server already knows (KNOWN_KEY: the invited number of an invitation, or the number of a session
scoped to one invitation) is shown masked, its last four digits only («*** ۴۵۶۷»; risk review: a link's holder must not
learn the operator prefix either; asterisks, because bullets read as Persian zeros in Vazirmatn) and the visitor types
nothing but the code. A number the visitor typed is shown in full (it is theirs).
"""
import re
from urllib.parse import quote

from odoo import fields, http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.website.controllers.main import WebsiteSession
from odoo.http import request
from odoo.http.session import authenticate

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_core.safe_url import local_path

from ..models.phone_otp import TTL_MIN
from ..models.res_partner import fmt_mobile
from .main import MESSAGES

MESSAGES = dict(MESSAGES, **{
    # the code line of the page already says «کد ۶ رقمی را به … فرستادیم»; the status adds the one missing fact (W40)
    'sent': ('ok', 'کد تا %s دقیقه معتبر است.' % fa_digits(TTL_MIN)),
    'resent': ('ok', 'کد تازه را فرستادیم؛ تا %s دقیقه معتبر است.' % fa_digits(TTL_MIN)),
    'short': ('warn', 'کد ۶ رقمی است.'),
    'wrong': ('warn', 'این کد درست نیست. دوباره امتحان کنید.'),
    'expired': ('warn', 'مهلت این کد تمام شده است؛ «ارسال دوباره کد» را بزنید.'),
    'attempts': ('warn', 'این کد چند بار نادرست وارد شد؛ کد تازه بگیرید.'),
    'locked': ('warn', 'چند بار کد نادرست وارد شد. برای امنیت حساب، ۱۵ دقیقهٔ دیگر دوباره امتحان کنید.'),
    'none': ('warn', 'اول شمارهٔ موبایل را بنویسید و کد بگیرید.'),
    'staff': ('warn', 'این شماره به حساب کارکنان وصل است؛ از ورود با ایمیل استفاده کنید.'),
    'inactive': ('warn', 'حساب این شماره غیرفعال است. برای فعال‌شدن دوباره با پشتیبانی تماس بگیرید.'),
    'expired_session': ('warn', 'مهلت ورود تمام شد؛ دوباره با شمارهٔ موبایل شروع کنید.'),
})
PERSONAL_KEY = 'ts_auth_personal'       # the «این دستگاه شخصی من است» choice, until the code is verified
RESENDS_KEY = 'ts_auth_resends'         # how many times a code was asked again for the current number
KNOWN_KEY = 'ts_auth_known'             # onb2: a number the server holds; shown masked, never typed
HELP_AFTER_RESENDS = 2
_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def mask_mobile(phone):
    """«*** ۴۵۶۷»: only the last four digits of a normalised mobile number, in Persian digits."""
    phone = phone or ''
    if len(phone) < 8:
        return ''
    return '*** ' + phone[-4:].translate(_FA)


def _shown(phone):
    """The number as the page shows it: masked when it is the known number, else formatted in full."""
    if not phone:
        return ''
    return mask_mobile(phone) if phone == request.session.get(KNOWN_KEY) else fmt_mobile(phone)


def safe_next(value):
    """Only a local path (the one shared validator, ts_core.safe_url); anything else falls back to /my."""
    return local_path(value, '/my')


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
    ('/start/', 'نتیجه‌تان آماده است؛ با شمارهٔ موبایل آن را می‌بینید و در حسابتان نگه می‌دارید.'),
]


_LINK_RE = re.compile(r'^/(invite|c)/([0-9A-Za-z]{16,64})$')


def invite_context(nxt):
    """Who invites to what, for the sign-in page reached from an invitation link (audit P2-1, P2-2): (text, tu) or None.
    Only what that link's own page shows a signed-out visitor: an open (not yet accepted) invitation or an open link of a
    running panel. Anything else (bound, unknown, closed) gets the general sentence, so nothing new is disclosed."""
    m = _LINK_RE.match(nxt or '')
    if not m:
        return None
    env = request.env
    title = ws = None
    if m.group(1) == 'invite':
        a = env['ts.assignment'].sudo().search([('token', '=', m.group(2))], limit=1)   # ts-scope-ok: the secret token is the key
        if not a or a.user_id or a.workspace_id.state != 'active':
            return None
        bat = a.battery_id if 'battery_id' in a._fields else None
        ws, title = a.workspace_id, ('مجموعهٔ ' + bat.ts_title()) if bat else a.instrument_id.ts_title()
    elif 'ts.campaign' in env:
        c = env['ts.campaign'].sudo().search([('open_token', '=', m.group(2)), ('kind', '=', 'open_link')], limit=1)   # ts-scope-ok: the secret token is the key
        if not c or c.workspace_id.state != 'active' or c.open_state() != 'ok':
            return None
        bat = c.battery_id if 'battery_id' in c._fields else None
        ws, title = c.workspace_id, ('مجموعهٔ ' + bat.ts_title()) if bat else c.instrument_id.ts_title()
    if not ws:
        return None
    tu = ws.purpose == 'education'
    if tu:
        text = '«%s» تو را به «%s» دعوت کرده است؛ اول با شمارهٔ موبایلت وارد شو، بعد به همان دعوت برمی‌گردی.'
    else:
        text = '«%s» شما را به «%s» دعوت کرده است؛ اول با شمارهٔ موبایل وارد شوید، بعد به همان دعوت برمی‌گردید.'
    return text % (ws.ts_public_name(), title), tu


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
    known = request.session.get(KNOWN_KEY) or ''
    Otp = request.env['ts.signup.otp']
    ctx = invite_context(nxt)
    return {
        'enabled': _enabled(), 'step': step, 'msg': MESSAGES.get(msg), 'msg_key': msg or '', 'next': nxt,
        'next_q': quote(nxt, safe='/'), 'why': ctx[0] if ctx else why_for(nxt),
        # «تو» on the sign-in page when the person comes from a school's invitation (P2-2; voice.md §2)
        'tu': bool(ctx and ctx[1]),
        'phone': phone, 'phone_fa': _shown(phone),
        'phone_prefill': fa_digits(phone) if (phone and edit and phone != known) else '',
        'known_fa': mask_mobile(known) if known else '',
        'personal': request.session.get(PERSONAL_KEY, True),
        'wait': Otp.seconds_to_resend(phone) if (phone and step == 'code') else 0,
        'resends': request.session.get(RESENDS_KEY, 0),
        'help_after': HELP_AFTER_RESENDS,
        'email_url': ('/web/login?redirect=%s&email=1' % quote(nxt, safe='/')) if nxt != '/my' else '/web/login?email=1',
        'page_name': 'ts_signup',
    }


def pick_phone_user(users, phone):
    """Of the accounts that hold a number, the most recently verified one (the verified number first, then the login)."""
    return users.sorted(lambda u: (u.partner_id.ts_phone == phone,
                                   u.partner_id.ts_phone_verified_at or fields.Datetime.from_string('2000-01-01')),
                        reverse=True)[:1]


def create_phone_user(env, phone):
    """A portal account from a mobile number alone (a verified code, or since onb2 the invitation SMS that reached this
    number). The name is unknown: `name` holds the formatted number for the back office, and the site asks for a real
    name only where others will see it. The name a panel typed on an invitation is never copied here."""
    Users = env['res.users'].sudo().with_context(no_reset_password=True, ts_name_placeholder=True)
    user = Users.create({
        'name': fmt_mobile(phone, persian=False), 'login': phone,
        'group_ids': [(6, 0, [env.ref('base.group_portal').id])],
    })
    user.partner_id.sudo().with_context(ts_name_placeholder=True).write({
        'phone': phone, 'ts_phone': phone, 'ts_phone_verified_at': fields.Datetime.now(), 'ts_name_unknown': True})
    return user


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
                    'redirect': url, 'phone_fa': _shown(phone),
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
        if post.get('known') == '1' and request.session.get(KNOWN_KEY):
            phone = request.session[KNOWN_KEY]      # the number the server holds (shown masked): nothing is typed
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
        ok, reason = request.env['ts.signup.otp'].verify_code(phone, code, request.httprequest.remote_addr)
        if not ok:
            return self._reply(False, 'code', reason, nxt)
        owners = request.env['res.users'].ts_phone_owner(phone)
        personal = request.session.get(PERSONAL_KEY, True)
        for key in ('ts_signup_phone', RESENDS_KEY, PERSONAL_KEY, 'ts_signup_ok', KNOWN_KEY):
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
            user = pick_phone_user(active, phone)
            request.env['ts.audit.event'].sudo().log('account.login_phone', user)
        else:
            user = self._create_user(phone)
            request.env['ts.audit.event'].sudo().log('account.signup_phone', user)
        self._login(user, personal=personal)
        return self._reply(True, 'done', None, nxt, url=nxt)

    def _create_user(self, phone):
        """A portal account from the verified mobile alone (see create_phone_user)."""
        return create_phone_user(request.env, phone)


class TsAuthSiteHome(AuthSignupHome):
    """talentsearch.ir only: the stock pages lead to S-AUTH. eot.ir (website 1) and the back office are untouched."""

    @http.route()
    def web_login(self, redirect=None, **kw):
        if _ts_site() and redirect:
            redirect = local_path(redirect, None)       # the one return-path validator on talentsearch.ir
        if request.httprequest.method == 'POST':
            # a password sign-in never inherits the 30-day choice of an earlier mobile sign-in in this browser
            request.session.pop('ts_session_mode', None)
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

    @staticmethod
    def _signup_allowed(kw):
        """E-mail sign-up on talentsearch.ir: only an Odoo signup token (reset / invitation) or a colleague invitation
        bound to an e-mail address (/join/...); everyone else signs up with the mobile code."""
        if kw.get('token'):
            return True
        back = local_path(kw.get('redirect'), '')
        return back.startswith('/join/')

    @http.route()
    def web_auth_signup(self, *args, **kw):
        # GET and POST alike: no e-mail account is made on talentsearch.ir outside the two cases above
        if _ts_site() and not self._signup_allowed(kw):
            return request.redirect(signin_url(kw.get('redirect')), 303)
        return super().web_auth_signup(*args, **kw)


class TsAuthSession(WebsiteSession):
    """Sign-out: Odoo clears the whole session (the 30-day choice goes with it); said here once more explicitly."""

    @http.route()
    def logout(self, *args, **kw):
        request.session.pop('ts_session_mode', None)
        return super().logout(*args, **kw)
