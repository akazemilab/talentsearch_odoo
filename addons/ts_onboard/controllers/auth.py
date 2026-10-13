"""The sign-in (S-AUTH, ts_sms) in the onb2 flows.

* A session scoped to one invitation that reaches another page lands here (ir_http): the page shows the invited number
  masked and «دریافت کد»; after the code the session is an ordinary full session (the scope ends).
* A number is never linked to or written onto an account from a scoped session (risk review HIGH 2), with one exception:
  the account the one-tap flow made moments ago for that invitation (an e-mail link to an address that had no account)
  and that holds nothing else. Otherwise the code for number P signs into P's own account, or makes a phone-only one; the
  invitation stays where it is, and one calm page says so (/my/invitation-elsewhere).
* After a successful code at the result gate: the guest attempt of this browser is claimed (O3) only when this session
  was shown the gate of that attempt and the code was asked for from the gate (next == /start/result). A sign-in
  anywhere else never claims it (a shared computer: the next person's account must not receive someone else's answers);
  the gate then offers one explicit button. An invitation waiting in this session (new browser, or a link without the
  message's secret) is accepted or continued (O2).
* An e-mail/password sign-in ends any scope too."""
from odoo import fields, http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_sms.controllers.signup import KNOWN_KEY, TsAuthSiteHome, TsSignup, mask_mobile, safe_next

from ..models.common import GUEST_COOKIE, digest, drop_cookie, mask_email, read_token
from ..models.ir_http import OTHER_KEY, SCOPE_KEY
from . import flow

LOGGED_KEY = 'ts_onb_logged'         # set by _login for the rest of this request only (popped in verify)
GATE_KEY = 'ts_onb_gate'             # the guest attempt whose result gate this session showed
GATE_PATH = '/start/result'
ELSEWHERE_KEY = 'ts_onb_elsewhere'   # what /my/invitation-elsewhere tells once


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


def _elsewhere(scope):
    """What the calm page says about the invitation of an ended scope: where its message went (masked)."""
    a = request.env['ts.assignment'].sudo().browse(int(scope.get('aid') or 0)).exists()
    if not a:
        return None
    via, value = a.ts_proof()
    if via == 'email':
        return {'kind': 'email', 'masked': mask_email(value)}
    phone = a.ts_invite_phone()
    return {'kind': 'phone', 'masked': mask_mobile(phone)} if phone else {'kind': 'link', 'masked': ''}


class TsOnbSignup(TsSignup):

    @http.route()
    def signup(self, step=None, msg=None, **kw):
        if kw.get('other') == '1':
            # «شمارهٔ دیگری دارم»: the ordinary sign-in with any number. Nothing is accepted for it: an invitation still
            # checks who may accept it (another number sees the mismatch notice).
            _ts_site_or_404()
            for key in (KNOWN_KEY, 'ts_signup_phone'):
                request.session.pop(key, None)
            request.session[OTHER_KEY] = True
        if request.session.get(SCOPE_KEY) and not request.env.user._is_public():
            # signed in for one invitation only: the sign-in page itself (the number masked), not a redirect loop
            _ts_site_or_404()
            phone = request.session[SCOPE_KEY].get('phone')
            if phone and not request.session.get(OTHER_KEY):
                request.session[KNOWN_KEY] = phone
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
            a = request.env['ts.assignment'].sudo().browse(int(scope.get('aid') or 0)).exists()
            # the only exception: the account made moments ago for this invitation, holding nothing else
            if u and a and u.share and u.active and not u.partner_id.ts_phone \
                    and flow.made_here(u, a, minutes=flow.FRESH_MINUTES) \
                    and not request.env['res.users'].ts_phone_owner(phone):
                u.partner_id.sudo().write({'ts_phone': phone, 'ts_phone_verified_at': fields.Datetime.now()})
                request.env['ts.audit.event'].sudo().log('account.phone_linked', u, via='invite_email')
                return u
        return super()._create_user(phone)

    @http.route()
    def verify(self, code=None, **post):
        prev = dict(request.session.get(SCOPE_KEY) or {})
        gate_aid = request.session.get(GATE_KEY)
        res = super().verify(code=code, **post)
        uid = request.session.pop(LOGGED_KEY, None)
        if not uid:
            return res
        request.session.pop(SCOPE_KEY, None)          # an ordinary full session from now on
        request.session.pop(KNOWN_KEY, None)
        request.session.pop(OTHER_KEY, None)
        request.session.pop(GATE_KEY, None)
        request.update_env(user=uid)
        user = request.env.user
        nxt = safe_next(post.get('next'))
        url, drop = None, False
        at = guest_attempt()
        if at and nxt == GATE_PATH and gate_aid and gate_aid == at.id:
            if at.ts_guest_claim(user):
                request.env['ts.funnel.event'].ts_log(request, 'gate_signed_in', instrument=at.instrument_id,
                                                      entry='guest')
            drop = True
            url = claim_url(at)
        inv_url, bound, personal = flow.after_code(user)
        url = inv_url or url
        if not url and prev.get('uid') and prev['uid'] != uid:
            # the code was for another account than the one of the invitation: nothing moves; say so once, calmly
            note = _elsewhere(prev)
            if note:
                request.session[ELSEWHERE_KEY] = note
                url = '/my/invitation-elsewhere'
        if not (url or drop):
            return res
        out = self._reply(True, 'done', None, url or nxt, url=url or nxt)
        if drop:
            drop_cookie(out, request, GUEST_COOKIE)
        if bound:
            flow.bind_device(bound, out, personal=personal)
        return out

    @http.route('/my/invitation-elsewhere', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def invitation_elsewhere(self, **kw):
        _ts_site_or_404()
        note = request.session.pop(ELSEWHERE_KEY, None)
        if not note:
            return request.redirect('/my')
        return request.render('ts_onboard.elsewhere', {
            'note': note, 'me': mask_mobile(request.env.user.partner_id.ts_phone or ''), 'page_name': 'ts_signup'})


class TsOnbAuthSiteHome(TsAuthSiteHome):

    @http.route()
    def web_login(self, redirect=None, **kw):
        if request.httprequest.method == 'POST':
            request.session.pop(SCOPE_KEY, None)
            request.session.pop(KNOWN_KEY, None)
        return super().web_login(redirect=redirect, **kw)
