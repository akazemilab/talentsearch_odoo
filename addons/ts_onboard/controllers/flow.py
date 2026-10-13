"""Shared steps of the onb2 invitation flow (used by the welcome screen and by the sign-in code page).

Who may be signed in without typing anything (risk review HIGH 1): only with the delivery secret of the system's own
message (models/assignment.py), and only into an account that did not exist (made now) or a Talent Search phone-only
portal account whose login is exactly the invited number, with no activity on eot.ir. Any other account (an e-mail
account, one with eot.ir activity, anything our phone flow did not make) gets a code to the invited number, or the
ordinary sign-in when the invitation has no number."""
import time
from datetime import timedelta
from urllib.parse import quote

from odoo import fields
from odoo.exceptions import UserError
from odoo.http import request
from odoo.http.session import authenticate

from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION
from odoo.addons.ts_sms.controllers.signup import KNOWN_KEY, RESENDS_KEY, create_phone_user

from ..models.common import (DEVICE_COOKIE, DEVICE_COOKIE_AGE, DEVICE_DAYS, DEVICE_SHARED_HOURS, digest, new_token,
                             read_token, same, set_cookie)
from ..models.ir_http import OTHER_KEY, SCOPE_KEY

PENDING_KEY = 'ts_invite_pending'
PENDING_TTL_S = 30 * 60
MINOR_VERSION = 'TS-MINOR-1405-07-22-v3'     # onb2: the guardian tick and the child's own button on one screen
FRESH_MINUTES = 60                           # «made moments ago» (risk review HIGH 2)
# activity on eot.ir (website 1) by the account's partner: an account with any of these is never signed in without a code
EOT_ACTIVITY = (('sale.order', 'partner_id'), ('account.move', 'partner_id'), ('payment.transaction', 'partner_id'),
                ('event.registration', 'partner_id'), ('slide.channel.partner', 'partner_id'),
                ('website.visitor', 'partner_id'))


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
    """The consent the welcome POST carries, or an error key. `personal`: «این دستگاه شخصی من است» (device binding)."""
    need = minor_needs(a)
    if need['guardian'] and post.get('guardian_confirm') != '1':
        return 'guardian'
    return {'share': post.get('share') == '1', 'research': post.get('consent_research') == '1',
            'minor': need['minor'], 'assent': need['assent'], 'role': need['role'],
            'personal': post.get('personal') == '1'}


def first_open(a):
    rows = a.sudo().ts_battery_attempts()
    return rows.filtered(lambda t: t.state != 'done')[:1] or rows[:1]


# ---------------------------------------------------------------------- whose account may be signed in without a code
def eot_activity(user):
    """Any trace of the account on eot.ir (website 1): orders, invoices, payments, events, courses, visits, or an account
    bound to another website. Fails closed: a check that cannot run counts as activity."""
    env = user.env
    u = user.sudo()
    site = env.ref('ts_website.website_ts', raise_if_not_found=False)
    try:
        if 'website_id' in u._fields and u.website_id and (not site or u.website_id != site):
            return True
        p = u.partner_id.commercial_partner_id
        for model, field in EOT_ACTIVITY:
            if model not in env:
                continue
            M = env[model].sudo().with_context(active_test=False)
            if field not in M._fields:
                continue
            dom = [(field, 'child_of', p.id)]
            if model == 'website.visitor' and site:
                dom.append(('website_id', '!=', site.id))
            if M.search_count(dom, limit=1):
                return True
    except Exception:            # noqa: BLE001 - cannot tell: treat as an account with activity
        return True
    return False


def phone_only(user, phone):
    """A Talent Search phone-only portal account: its login is exactly `phone`, the number verified here, no internal
    access, no eot.ir activity."""
    u = user.sudo() if user else user
    if not (u and len(u) == 1 and phone and u.active and u.share and u.login == phone):
        return False
    p = u.partner_id
    if p.ts_phone != phone or not p.ts_phone_verified_at:
        return False
    return not eot_activity(u)


def only_this_invitation(user, a):
    """The account holds nothing but invitation `a`: no other invitation or attempt, no membership, client record,
    message or partner link, no eot.ir activity."""
    env = user.env
    u, a = user.sudo(), a.sudo()
    if env['ts.assignment'].sudo().with_context(active_test=False).search_count(
            [('user_id', '=', u.id), ('id', '!=', a.id)], limit=1):
        return False
    mine = a.ts_battery_attempts() | a.attempt_id
    if env['ts.attempt'].sudo().search_count([('user_id', '=', u.id), ('id', 'not in', mine.ids)], limit=1):
        return False
    p = u.partner_id
    if p.parent_id or p.child_ids or len(p.with_context(active_test=False).user_ids) > 1:
        return False
    client = a.client_id if 'client_id' in a._fields else env['res.partner']
    own = {('ts.assignment', a.id)} | {('ts.attempt', i) for i in mine.ids} | {('ts.panel.client', i) for i in client.ids}
    # messages the person wrote or was sent (not the system's tracking notes of what the flow itself did)
    msgs = env['mail.message'].sudo().search([('author_id', '=', p.id),
                                              ('message_type', 'in', ('comment', 'email', 'email_outgoing'))], limit=50)
    if any((m.model, m.res_id) not in own for m in msgs):
        # a message written anywhere else than on this invitation and its attempts
        return False
    if 'ts.workspace.member' in env and env['ts.workspace.member'].sudo().with_context(active_test=False).search_count(
            [('user_id', '=', u.id)], limit=1):
        return False
    if 'ts.panel.client' in env:
        C = env['ts.panel.client'].sudo().with_context(active_test=False)
        for f in ('user_id', 'partner_id'):
            if f in C._fields and C.search_count([(f, '=', u.id if f == 'user_id' else p.id), ('id', 'not in', client.ids)], limit=1):
                return False
    return not eot_activity(u)


def made_here(user, a, minutes=None):
    """`user` was made by the one-tap flow for invitation `a` (and, with `minutes`, that recently) and holds nothing
    else."""
    s = a.sudo()
    if not (user and s.ts_account_made and s.user_id == user):
        return False
    if minutes and user.sudo().create_date < fields.Datetime.now() - timedelta(minutes=minutes):
        return False
    return only_this_invitation(user, s)


def no_typing_ok(user, a):
    """May the holder of invitation `a` be signed in again without a code (its bound browser, or its message's secret)?"""
    return phone_only(user, a.sudo().ts_invite_phone()) or made_here(user, a)


def link_user(env, via, value):
    """The account the message's secret may sign in without a code -> (user, made) or (None, False).
    sms: no account holds the number -> a new phone account; exactly one holds it and it is phone-only -> that one.
    email: no account has this address (exact, letter case aside; `%` and `_` are not wildcards) -> a new portal account.
    Anything else -> None: a code to the invited number, or the ordinary sign-in."""
    Users = env['res.users'].sudo().with_context(active_test=False)
    if via == 'sms':
        owners = Users.ts_phone_owner(value)
        if not owners:
            return create_phone_user(env, value), True
        if len(owners) == 1 and phone_only(owners, value):
            return owners, False
        return None, False
    if via == 'email':
        email = (value or '').strip().lower()
        if not email or '@' not in email:
            return None, False
        esc = email.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        found = Users.search(['|', ('login', '=ilike', esc), ('email', '=ilike', esc)])
        found = found.filtered(lambda u: email in ((u.login or '').strip().lower(), (u.email or '').strip().lower()))
        if found:
            return None, False
        user = Users.with_context(no_reset_password=True, ts_name_placeholder=True).create({
            'name': email, 'login': email, 'email': email,
            'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
        user.partner_id.sudo().with_context(ts_name_placeholder=True).write({'ts_name_unknown': True})
        env['ts.audit.event'].sudo().log('account.signup_invite_email', user)
        return user, True
    return None, False


def scoped_login(user, a, phone=''):
    """Sign in as `user` for this one invitation only (ir_http enforces the scope). Browser-session cookie."""
    token = request.env['ts.login.token'].sudo().issue(user)
    authenticate(request.session, request.env, {'type': 'ts_phone_login', 'login': user.login, 'token': token})
    request.session['ts_session_mode'] = 'browser'
    request.session[SCOPE_KEY] = {'aid': a.id, 'uid': user.id, 'phone': phone or ''}
    request.update_env(user=user.id)
    request.env['ts.audit.event'].sudo().log('account.login_invite', user, assignment=a.id, via=a.sudo().delivered_via)


# ---------------------------------------------------------------------- device binding
def device_matches(a):
    """This browser is the one bound to invitation `a`, the binding has not ended (30 days, or 12 hours when the device
    is not personal) and the invitation is not finished."""
    raw = read_token(request.env, 'device', request.httprequest.cookies.get(DEVICE_COOKIE))
    s = a.sudo()
    if not same(raw, s.device_hash):
        return False
    if not s.device_until or s.device_until < fields.Datetime.now():
        return False
    parts = s.ts_battery_attempts()
    return not (s.state == 'done' or (parts and not parts.filtered(lambda t: t.state != 'done')))


def bind_device(a, response, personal=True):
    """The first accept binds the invitation to this browser (the same browser token serves every invitation): with
    «این دستگاه شخصی من است» for 30 days, without it a browser-session cookie and 12 hours on the server."""
    s = a.sudo()
    if s.device_hash:
        return response
    value = request.httprequest.cookies.get(DEVICE_COOKIE)
    raw = read_token(request.env, 'device', value)
    if not raw:
        raw, value = new_token(request.env, 'device')
    until = fields.Datetime.now() + (timedelta(days=DEVICE_DAYS) if personal else timedelta(hours=DEVICE_SHARED_HOURS))
    s.write({'device_hash': digest(raw), 'device_until': until})
    return set_cookie(response, request, DEVICE_COOKIE, value, DEVICE_COOKIE_AGE if personal else None)


# ---------------------------------------------------------------------- consent and acceptance
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
    """After a sign-in code: what an invitation waiting in this session asks for.
    -> (url or None, assignment to bind or None, personal)."""
    pend = request.session.pop(PENDING_KEY, None)
    if not pend or pend.get('exp', 0) < time.time():
        return None, None, False
    a = request.env['ts.assignment'].sudo().browse(int(pend.get('aid') or 0)).exists()
    if not a or a.workspace_id.state != 'active':
        return None, None, False
    if pend.get('do') == 'accept' and not a.user_id and a.invite_state() == 'ok' and a.ts_contact_matches(user) is not False:
        url = accept_now(a, user, pend)
        return (url, a, bool(pend.get('personal'))) if url else ('/invite/%s?error=rule' % a.token, None, False)
    return '/invite/%s' % a.token, None, False
