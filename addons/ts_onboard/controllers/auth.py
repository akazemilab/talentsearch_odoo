"""The sign-in (S-AUTH, ts_sms) in the onb2 flows.

* A session scoped to one invitation that reaches another page lands here (ir_http): the page shows the invited number
  masked and «دریافت کد»; after the code the session is an ordinary full session (the scope ends).
* A session scoped to an e-mail invitation has no number yet: a verified number that nobody holds joins that account
  (one person, one account) instead of making a second one.
* After a successful code: a guest attempt of this browser is claimed (O3), and an invitation waiting in this session
  (new browser, or a link without proof) is accepted or continued (O2).
* An e-mail/password sign-in ends any scope too."""
from odoo import fields, http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_sms.controllers.signup import KNOWN_KEY, TsAuthSiteHome, TsSignup, safe_next

from ..models.common import GUEST_COOKIE, digest, drop_cookie, read_token
from ..models.ir_http import SCOPE_KEY
from . import flow

LOGGED_KEY = 'ts_onb_logged'         # set by _login for the rest of this request only (popped in verify)


def guest_attempt(any_state=True):
    """The guest attempt of this browser (signed cookie -> digest), or an empty recordset."""
    Att = request.env['ts.attempt'].sudo()
    raw = read_token(request.env, 'guest', request.httprequest.cookies.get(GUEST_COOKIE))
    if not raw:
        return Att
    return Att.search([('ts_guest', '=', True), ('ts_guest_hash', '=', digest(raw))], limit=1)


def claim_url(at):
    if at.state == 'done':
        return '/my/assessments/%s?submitted=1&claimed=1' % at.id
    return '/take/%s' % at.access_token


class TsOnbSignup(TsSignup):

    @http.route()
    def signup(self, step=None, msg=None, **kw):
        if request.session.get(SCOPE_KEY) and not request.env.user._is_public():
            # signed in for one invitation only: the sign-in page itself (the number masked), not a redirect loop
            _ts_site_or_404()
            nxt = safe_next(kw.get('next'))
            if step == 'code' and request.session.get('ts_signup_phone'):
                return self._page('code', msg, nxt)
            return self._page('phone', msg, nxt)
        return super().signup(step=step, msg=msg, **kw)

    def _login(self, user, personal=True):
        super()._login(user, personal=personal)
        request.session[LOGGED_KEY] = user.id

    def _create_user(self, phone):
        scope = request.session.get(SCOPE_KEY)
        if scope and not scope.get('phone'):
            u = request.env['res.users'].sudo().browse(int(scope.get('uid') or 0)).exists()
            if u and u.share and u.active and not u.partner_id.ts_phone \
                    and not request.env['res.users'].ts_phone_owner(phone):
                u.partner_id.sudo().write({'ts_phone': phone, 'ts_phone_verified_at': fields.Datetime.now()})
                request.env['ts.audit.event'].sudo().log('account.phone_linked', u, via='invite_email')
                return u
        return super()._create_user(phone)

    @http.route()
    def verify(self, code=None, **post):
        res = super().verify(code=code, **post)
        uid = request.session.pop(LOGGED_KEY, None)
        if not uid:
            return res
        request.session.pop(SCOPE_KEY, None)          # an ordinary full session from now on
        request.session.pop(KNOWN_KEY, None)
        request.update_env(user=uid)
        user = request.env.user
        nxt = safe_next(post.get('next'))
        url, drop, bound = None, False, None
        at = guest_attempt()
        if at:
            at.ts_guest_claim(user)
            request.env['ts.funnel.event'].ts_log(request, 'gate_signed_in', instrument=at.instrument_id)
            drop = True
            if nxt.startswith('/start'):
                url = claim_url(at)
        inv_url, bound = flow.after_code(user)
        url = inv_url or url
        if not (url or drop):
            return res
        out = self._reply(True, 'done', None, url or nxt, url=url or nxt)
        if drop:
            drop_cookie(out, request, GUEST_COOKIE)
        if bound:
            flow.bind_device(bound, out)
        return out


class TsOnbAuthSiteHome(TsAuthSiteHome):

    @http.route()
    def web_login(self, redirect=None, **kw):
        if request.httprequest.method == 'POST':
            request.session.pop(SCOPE_KEY, None)
            request.session.pop(KNOWN_KEY, None)
        return super().web_login(redirect=redirect, **kw)
