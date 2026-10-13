"""Shared steps of the onb2 invitation flow (used by the welcome screen and by the sign-in code page)."""
import time
from urllib.parse import quote

from odoo import fields
from odoo.exceptions import UserError
from odoo.http import request
from odoo.http.session import authenticate

from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION
from odoo.addons.ts_sms.controllers.signup import KNOWN_KEY, RESENDS_KEY, create_phone_user, pick_phone_user

from ..models.common import DEVICE_COOKIE, DEVICE_COOKIE_AGE, digest, new_token, read_token, set_cookie
from ..models.ir_http import OTHER_KEY, SCOPE_KEY

PENDING_KEY = 'ts_invite_pending'
PENDING_TTL_S = 30 * 60
MINOR_VERSION = 'TS-MINOR-1405-07-22-v3'     # onb2: the guardian tick and the child's own button on one screen


def minor_needs(a):
    """What the one consent screen asks for a minor or a child instrument.
    guardian: a required tick; text: which sentence; assent: the button is the child's own «من هم موافقم»;
    minor: the respondent is a minor client (ledger rows guardian + assent)."""
    a = a.sudo()
    insts = a.battery_id.ts_lines().mapped('instrument_id') if a.battery_id else a.instrument_id
    first = insts[:1] or a.instrument_id
    child_report = any(i.audience == 'child' for i in insts)
    role_guardian = first.audience in ('child', 'adolescent')
    client = a.client_id if 'client_id' in a._fields else False
    minor_client = bool(client and client.age_group == 'minor')
    if child_report:
        text = 'child'
    elif minor_client:
        text = 'minor'
    elif role_guardian:
        text = 'teen'
    else:
        text = None
    return {'guardian': bool(text), 'text': text, 'assent': minor_client and not child_report,
            'minor': minor_client and not child_report, 'role': 'guardian' if role_guardian else 'self'}


def consent_from(post, a):
    """The consent the welcome POST carries, or an error key."""
    need = minor_needs(a)
    if need['guardian'] and post.get('guardian_confirm') != '1':
        return 'guardian'
    return {'share': post.get('share') == '1', 'research': post.get('consent_research') == '1',
            'minor': need['minor'], 'assent': need['assent'], 'role': need['role']}


def first_open(a):
    rows = a.sudo().ts_battery_attempts()
    return rows.filtered(lambda t: t.state != 'done')[:1] or rows[:1]


def link_user(via, value):
    """The account of the number / address the invitation message reached: found, or made (portal, name unknown). None
    for a staff account or an archived one (they sign in the ordinary way)."""
    Users = request.env['res.users'].sudo()
    if via == 'sms':
        owners = Users.ts_phone_owner(value)
        if owners.filtered(lambda u: not u.share):
            return None
        active = owners.filtered(lambda u: u.active)
        if owners and not active:
            return None
        return pick_phone_user(active, value) if active else create_phone_user(request.env, value)
    if via == 'email':
        U = Users.with_context(active_test=False)
        users = U.search([('login', '=ilike', value)]) or U.search([('email', '=ilike', value)])
        if users.filtered(lambda u: not u.share):
            return None
        active = users.filtered(lambda u: u.active)
        if users and not active:
            return None
        if active:
            return active.sorted(lambda u: ((u.login or '').lower() == value, u.id), reverse=True)[:1]
        user = Users.with_context(no_reset_password=True, ts_name_placeholder=True).create({
            'name': value, 'login': value, 'email': value,
            'group_ids': [(6, 0, [request.env.ref('base.group_portal').id])]})
        user.partner_id.sudo().with_context(ts_name_placeholder=True).write({'ts_name_unknown': True})
        request.env['ts.audit.event'].sudo().log('account.signup_invite_email', user)
        return user
    return None


def scoped_login(user, a, phone=''):
    """Sign in as `user` for this one invitation only (ir_http enforces the scope). Browser-session cookie."""
    token = request.env['ts.login.token'].sudo().issue(user)
    authenticate(request.session, request.env, {'type': 'ts_phone_login', 'login': user.login, 'token': token})
    request.session['ts_session_mode'] = 'browser'
    request.session[SCOPE_KEY] = {'aid': a.id, 'uid': user.id, 'phone': phone or ''}
    request.update_env(user=user.id)
    request.env['ts.audit.event'].sudo().log('account.login_invite', user, assignment=a.id, via=a.sudo().delivered_via)


def device_matches(a):
    raw = read_token(request.env, 'device', request.httprequest.cookies.get(DEVICE_COOKIE))
    h = a.sudo().device_hash
    return bool(raw and h and digest(raw) == h)


def bind_device(a, response):
    """The first accept binds the invitation to this browser (the same browser token serves every invitation)."""
    s = a.sudo()
    if s.device_hash:
        return response
    raw = read_token(request.env, 'device', request.httprequest.cookies.get(DEVICE_COOKIE))
    value = request.httprequest.cookies.get(DEVICE_COOKIE) if raw else None
    if not raw:
        raw, value = new_token(request.env, 'device')
    s.write({'device_hash': digest(raw)})
    return set_cookie(response, request, DEVICE_COOKIE, value, DEVICE_COOKIE_AGE)


def give_consent(a, user, consent):
    """The welcome POST is the consent: recorded on the first attempt (a battery copies it to every instrument), with the
    consent text version; minors get the guardian and assent rows of the ledger."""
    a = request.env['ts.assignment'].sudo().browse(a.id)
    first = a.ts_battery_attempts()[:1] or a.attempt_id
    if not first:
        return False
    if first.state == 'consent':
        first.give_consent(research=consent['research'], role=consent['role'])
    if consent.get('minor') and 'ts.consent.record' in request.env:
        Rec = request.env['ts.consent.record']
        Rec._log('guardian', user, attempt=first, workspace=a.workspace_id, version=MINOR_VERSION, given_as='guardian',
                 client=a.client_id)
        if consent.get('assent'):
            Rec._log('assent', user, attempt=first, workspace=a.workspace_id, version=MINOR_VERSION, given_as='self',
                     client=a.client_id)
    a.write({'welcome_version': CONSENT_VERSION, 'welcome_at': fields.Datetime.now()})
    request.env['ts.audit.event'].sudo().log('assignment.welcome_consent', a, workspace=a.workspace_id,
                                             version=CONSENT_VERSION, research=bool(consent['research']),
                                             share=bool(consent['share']), minor=bool(consent.get('minor')))
    return True


def accept_now(a, user, consent):
    """Accept for `user`, record the consent, return the address of the first instrument (or None on a refusal)."""
    a = request.env['ts.assignment'].sudo().browse(a.id)
    try:
        a.action_accept(user, share=consent['share'])
    except UserError:
        return None
    try:
        give_consent(a, user, consent)
    except UserError:
        pass                     # the ordinary consent page of the instrument follows (nothing is lost)
    request.env['ts.funnel.event'].ts_log(request, 'invite_accept', assignment=a, instrument=a.instrument_id)
    nxt = first_open(a)
    return '/take/%s' % nxt.access_token if nxt else '/invite/%s' % a.token


def otp_then(a, phone, pending):
    """Send a sign-in code to the invitation's number (shown masked) and keep what to do after the code."""
    sess = request.session
    sess[PENDING_KEY] = dict(pending, aid=a.id, exp=time.time() + PENDING_TTL_S)
    sess[KNOWN_KEY] = phone
    sess.pop(OTHER_KEY, None)
    nxt = '/invite/%s' % a.token
    ok, reason, norm = request.env['ts.signup.otp'].request_code(phone, request.httprequest.remote_addr)
    if ok or (reason in ('cooldown', 'limit', 'locked') and norm):
        sess['ts_signup_phone'] = norm
        sess[RESENDS_KEY] = 0
        msg = '' if (ok or reason == 'cooldown') else reason       # a code sent a moment ago is still the code to type
        return request.redirect('/signup?step=code&msg=%s&next=%s' % (msg, quote(nxt, safe='/')))
    return request.redirect('/signup?msg=%s&next=%s' % (reason or 'send', quote(nxt, safe='/')))


def after_code(user):
    """After a sign-in code: what an invitation waiting in this session asks for. -> (url or None, assignment or None)."""
    pend = request.session.pop(PENDING_KEY, None)
    if not pend or pend.get('exp', 0) < time.time():
        return None, None
    a = request.env['ts.assignment'].sudo().browse(int(pend.get('aid') or 0)).exists()
    if not a or a.workspace_id.state != 'active':
        return None, None
    if pend.get('do') == 'accept' and not a.user_id and a.invite_state() == 'ok' and a.ts_contact_matches(user) is not False:
        url = accept_now(a, user, pend)
        return (url, a) if url else ('/invite/%s?error=rule' % a.token, None)
    return '/invite/%s' % a.token, None
