from urllib.parse import quote

from odoo import fields, http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits

from ..models.phone_otp import iran_mobile
from .main import MESSAGES

MESSAGES = dict(MESSAGES, **{
    'sent': ('ok', 'کد تأیید پیامک شد و تا ۵ دقیقه معتبر است.'),
    'noname': ('warn', 'نام خود را وارد کنید.'),
    'expired_session': ('warn', 'مهلت ثبت‌نام تمام شد؛ دوباره با شمارهٔ موبایل شروع کنید.'),
})
VERIFIED_TTL_S = 600


def safe_next(value):
    """Only a local path; anything else (other hosts, protocol-relative, backslashes) falls back to /my."""
    v = (value or '').strip()
    if v.startswith('/') and not v.startswith('//') and '\\' not in v and '\n' not in v and '\r' not in v:
        return v[:300]
    return '/my'


def _enabled():
    c = request.env.company.sudo()
    return bool(c.kv_enabled and c.ts_sms_otp)


class TsSignup(http.Controller):

    def _page(self, step, msg=None, nxt='/my'):
        phone = request.session.get('ts_signup_phone') or ''
        return request.render('ts_sms.signup', {
            'enabled': _enabled(), 'step': step, 'msg': MESSAGES.get(msg), 'next': nxt,
            'masked': fa_digits(phone[:4] + '***' + phone[-4:]) if phone else '', 'page_name': 'ts_signup',
        })

    def _login(self, user):
        token = request.env['ts.login.token'].sudo().issue(user)
        request.session.authenticate(request.env, {'type': 'ts_phone_login', 'login': user.login, 'token': token})

    @http.route('/signup', type='http', auth='public', website=True, sitemap=False)
    def signup(self, step=None, msg=None, **kw):
        _ts_site_or_404()
        nxt = safe_next(kw.get('next'))
        if not request.env.user._is_public():
            return request.redirect(nxt)
        if step == 'code' and request.session.get('ts_signup_phone'):
            return self._page('code', msg, nxt)
        if step == 'name' and self._verified_phone():
            return self._page('name', msg, nxt)
        return self._page('phone', msg, nxt)

    def _verified_phone(self):
        data = request.session.get('ts_signup_ok')
        if not data:
            return None
        phone, ts = data
        if ts < fields.Datetime.now().timestamp() - VERIFIED_TTL_S:
            request.session.pop('ts_signup_ok', None)
            return None
        return phone

    @http.route('/signup/send', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def send(self, phone=None, **post):
        _ts_site_or_404()
        nxt = safe_next(post.get('next'))
        ok, reason, norm = request.env['ts.signup.otp'].request_code(phone, request.httprequest.remote_addr)
        if ok:
            request.session['ts_signup_phone'] = norm
            return request.redirect('/signup?step=code&msg=sent&next=%s' % quote(nxt, safe='/'))
        if reason in ('cooldown', 'limit') and norm:
            request.session['ts_signup_phone'] = norm
            return request.redirect('/signup?step=code&msg=%s&next=%s' % (reason, quote(nxt, safe='/')))
        return request.redirect('/signup?msg=%s&next=%s' % (reason, quote(nxt, safe='/')))

    @http.route('/signup/verify', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def verify(self, code=None, **post):
        _ts_site_or_404()
        nxt = safe_next(post.get('next'))
        q = quote(nxt, safe='/')
        phone = request.session.get('ts_signup_phone')
        if not phone:
            return request.redirect('/signup?msg=none&next=%s' % q)
        ok, reason = request.env['ts.signup.otp'].verify_code(phone, code)
        if not ok:
            return request.redirect('/signup?step=code&msg=%s&next=%s' % (reason, q))
        user = request.env['res.partner'].sudo().search([('ts_phone', '=', phone)], limit=1).user_ids[:1] \
            or request.env['res.users'].sudo().search([('login', '=', phone)], limit=1)
        request.session.pop('ts_signup_phone', None)
        if user and user.active and user.share:
            request.env['ts.audit.event'].sudo().log('account.login_phone', user)
            self._login(user)
            return request.redirect(nxt)
        request.session['ts_signup_ok'] = (phone, fields.Datetime.now().timestamp())
        return request.redirect('/signup?step=name&next=%s' % q)

    @http.route('/signup/name', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def name(self, **post):
        _ts_site_or_404()
        nxt = safe_next(post.get('next'))
        q = quote(nxt, safe='/')
        phone = self._verified_phone()
        if not phone:
            return request.redirect('/signup?msg=expired_session&next=%s' % q)
        name = ' '.join((post.get('name') or '').split())[:100]
        if len(name) < 2:
            return request.redirect('/signup?step=name&msg=noname&next=%s' % q)
        request.session.pop('ts_signup_ok', None)
        user = request.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': name, 'login': phone,
            'group_ids': [(6, 0, [request.env.ref('base.group_portal').id])],
        })
        user.partner_id.sudo().write({'mobile': phone, 'ts_phone': phone,
                                      'ts_phone_verified_at': fields.Datetime.now()})
        request.env['ts.audit.event'].sudo().log('account.signup_phone', user)
        self._login(user)
        return request.redirect(nxt)
