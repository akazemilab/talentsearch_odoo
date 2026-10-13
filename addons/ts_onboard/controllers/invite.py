"""O2: one-tap invitations (design §5 P2, P3, minors; docs/onboarding/02_invites_and_guest.md).

GET /invite/<token> is the welcome screen and never consumes, accepts or binds anything (messenger previews open links):
it may only mark the invitation as opened, as before. The POST of «موافقم و شروع می‌کنم» is the consent (recorded with
the consent text version) and the acceptance:
  * signed in as the invited person (or the invitation names no number): accept at once;
  * not signed in, with the delivery secret of the system's own SMS or e-mail (`d`, carried as a hidden field from
    /i/<code>/<secret> or ?d=<secret>; risk review HIGH 1): signed in for this invitation only (ir_http) as the account
    of that number / address, but only when that account did not exist (made now) or is a Talent Search phone-only
    account whose login is the invited number (flow.link_user);
  * otherwise (a link the panel copied, an older message, any other existing account): a code to the invited number,
    shown masked, then accept; without a number the ordinary sign-in.
The invitation is bound to this browser when «این دستگاه شخصی من است» is ticked (30 days) or for this browser session.
A later open from another browser (no valid binding, no secret) sends a code to the invited number (masked) instead.
A signed-in account that is not the invited number or address sees one clear notice and one action (sign out, then sign
in with the invited number). An invitation another account accepted answers the site's link 404 (ts_website.page_404,
take1): the same page as an unknown token, so nobody learns whether the link exists or who holds it.
Lookups are rate-limited per hashed address and family, then a polite 429 page: the invitation page /invite/ and the
short links /i/ and /j/ 60 a minute each, the open class link /c/ 120 (a whole class opens it from one school network).
A miss (unknown token or code) is answered with the link 404 inside the request's own transaction, so the counted hit is
kept (models/rate.py: no second cursor).
Size and time come from ts_org's effort_facts and dead-end states from its invite_card (one source, take1)."""
from datetime import datetime, time as dtime
from urllib.parse import quote

import werkzeug.exceptions

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION, fa_digits, jalali_long
from odoo.addons.ts_battery.controllers.main import battery_url
from odoo.addons.ts_brand.controllers.main import TsBrandLinks
from odoo.addons.ts_brand.models.short import CODE_RE
from odoo.addons.ts_org.controllers.main import TsOrg, effort_facts, invite_card
from odoo.addons.ts_panel.controllers.campaigns_public import TsPanelCampaignJoin
from odoo.addons.ts_sms.controllers.signup import mask_mobile, signin_url

from ..models.common import DLV_RE, first_name, mask_email
from . import flow

ERRORS = {
    'guardian': 'برای ادامه، تیک تأیید ولی لازم است.',
    'rule': 'این دعوت با این حساب پذیرفته نمی‌شود. اگر فکر می‌کنید اشتباهی رخ داده است، با دعوت‌کننده تماس بگیرید.',
}
GUARDIAN_TEXT = {
    'child': 'تأیید می‌کنم ولی (پدر، مادر یا سرپرست قانونی) کودک هستم و این سنجه را دربارهٔ او پاسخ می‌دهم.',
    'teen': 'تأیید می‌کنم ولی قانونی نوجوان هستم و پاسخ‌دهی با اطلاع و رضایت من انجام می‌شود.',
    'minor': 'ولی‌ام (پدر، مادر یا سرپرست قانونی) از این سنجه خبر دارد و موافق است.',
}
PER_MINUTE = {'invite': 60, 'short': 60, 'campaign': 120}


def limited(family):
    """Lookups a minute per hashed address and family (ts_onboard.<family>_per_minute: invite and short 60, campaign
    120); then a polite 429 page. None when the lookup may go on."""
    default = PER_MINUTE.get(family, 60)
    limit = request.env['ir.config_parameter'].sudo().get_int('ts_onboard.%s_per_minute' % family, default) or default
    ip = request.env['ts.audit.event'].sudo()._hash_ip(request.httprequest.remote_addr)
    if request.env['ts.rate.hit'].ts_hit('%s:%s' % (family, ip), limit, 60):
        return None
    resp = request.render('ts_onboard.slow', {'page_name': 'ts_slow'}, status=429)
    resp.headers['Retry-After'] = '60'
    return resp


def counted(family, serve):
    """Rate-limit one lookup, then serve it; a miss (404) is rendered here, in the request's own transaction, so the hit
    just counted is committed with it (raising would roll it back)."""
    slow = limited(family)
    if slow:
        return slow
    try:
        return serve()
    except werkzeug.exceptions.NotFound as e:
        IrHttp = request.env['ir.http']
        code, values = IrHttp._get_exception_code_values(e)
        code, html = IrHttp._get_error_html(code, values)
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')], status=int(code))


def dlv_of(value):
    """A well-formed delivery secret from the address or the form, else ''."""
    return value if isinstance(value, str) and DLV_RE.match(value) else ''


class TsOnbInvite(TsOrg):

    # ------------------------------------------------------------------ the welcome screen (GET: never binds)
    def _ts_values(self, a, mode, **extra):
        a = a.sudo()
        ws, bat, pos, inst = a.workspace_id, a.battery_id, a.position_id, a.instrument_id
        insts = bat.ts_lines().mapped('instrument_id') if bat else inst
        counselor = ''
        if ws.purpose == 'clinical' and hasattr(ws, 'ts_brand_enabled') and ws.ts_brand_enabled():
            m = ws.ts_brand_member(a)
            if m and m.show_on_report:
                counselor = m.user_id.partner_id.ts_known_name() or ''
        need = flow.minor_needs(a)
        tu = ws.purpose == 'education'
        values = {
            'a': a, 'ws': ws, 'inst': inst, 'bat': bat, 'pos': pos, 'mode': mode, 'tu': tu, 'fa': fa_digits,
            'hello': first_name(a.invitee_name), 'org': ws.ts_public_name(), 'counselor': counselor,
            'facts': effort_facts(inst, bat or None, ws.purpose),
            'item_names': [i.ts_title() for i in insts] if bat else [],
            'timed': any(i.ts_is_task_inst() for i in insts if hasattr(i, 'ts_is_task_inst')),
            'need': need, 'guardian_text': GUARDIAN_TEXT.get(need['text']), 'consent_version': CONSENT_VERSION,
            'public': request.env.user._is_public(), 'inv_card': None, 'error': None, 'page_name': 'ts_invite',
            'logout_url': '/web/session/logout?redirect=%s' % quote('/invite/%s' % a.token), 'dlv': '',
        }
        values.update(extra)
        if mode == 'state':
            ends = a.expires_at if 'expires_at' in a._fields and a.expires_at else a.deadline
            if ends and not isinstance(ends, datetime):
                ends = datetime.combine(ends, dtime(12, 0))
            values['inv_card'] = invite_card(values['inv_state'], values['org'], tu, jalali_long(ends) if ends else None)
        return values

    @http.route()
    def invite_page(self, token, **kw):
        _ts_site_or_404()
        return counted('invite', lambda: self._ts_welcome(token, **kw))

    def _ts_welcome(self, token, **kw):
        a = self._invite(token, paused_ok=True)
        user = request.env.user
        public = user._is_public()
        dlv = dlv_of(kw.get('d'))
        if not public and a.user_id == user:
            if a.state == 'done' or (a.attempt_id and a.attempt_id.state == 'done' and not a.battery_id):
                return request.redirect(battery_url(a) if a.battery_id else '/my/assessments/%s' % a.attempt_id.id)
            nxt = flow.first_open(a)
            if nxt:
                return request.redirect('/take/%s' % nxt.access_token)
        if a.user_id and not public:
            # accepted by another account: the link 404 of the site (it offers sign-out and sign-in with the invited
            # number) — the same page as an unknown token, nobody learns who holds the invitation (take1)
            raise request.not_found()
        inv_state = 'paused' if a.workspace_id.state == 'suspended' else a.invite_state()
        if inv_state not in ('ok', 'used'):
            return request.render('ts_onboard.welcome', self._ts_values(a, 'state', inv_state=inv_state))
        if a.user_id:                                # accepted earlier, by this person on another browser or by someone else
            return request.render('ts_onboard.welcome', self._ts_values(a, 'continue', done=a.state == 'done', dlv=dlv))
        if a.workspace_id.state == 'active':
            a.action_mark_opened()                   # a link preview may count too: the panel says «بازشده»
        error = ERRORS.get(kw.get('error'))
        if not public and a.ts_contact_matches(user) is False:
            return request.render('ts_onboard.welcome', self._ts_values(a, 'mismatch', contact=self._ts_contact(a)))
        name_mismatch = ''
        if not public:
            known = user.partner_id.ts_known_name()
            norm = lambda x: ' '.join((x or '').replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ').split()).lower()
            if known and a.ts_contact_matches(user) is None and norm(a.invitee_name) != norm(known):
                name_mismatch = known            # the old notice for links without a number (G2-P12-1)
        request.env['ts.funnel.event'].ts_log(request, 'invite_view', assignment=a, instrument=a.instrument_id)
        return request.render('ts_onboard.welcome', self._ts_values(
            a, 'welcome', error=error, name_mismatch=name_mismatch, ask_decline=kw.get('decline') == '1', dlv=dlv))

    def _ts_contact(self, a):
        via, value = a.ts_proof()
        if via == 'email':
            return {'kind': 'email', 'masked': mask_email(value)}
        phone = a.ts_invite_phone()
        return {'kind': 'phone', 'masked': mask_mobile(phone)} if phone else None

    # ------------------------------------------------------------------ the POST is the consent
    @http.route('/invite/<string:token>/accept', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def invite_accept(self, token, **post):
        _ts_site_or_404()
        if not post.get('welcome'):
            # an older form without the welcome screen: unchanged (sign in first; the consent page follows)
            if request.env.user._is_public():
                return request.redirect(signin_url('/invite/%s' % token))
            return super().invite_accept(token, **post)
        a = self._invite(token)
        user = request.env.user
        public = user._is_public()
        if a.user_id:
            if not public:
                return request.redirect('/invite/%s' % token)       # the welcome screen answers (player or 404)
            return self._ts_continue(a, post)
        if a.invite_state() != 'ok':
            return request.redirect('/invite/%s' % token)
        consent = flow.consent_from(post, a)
        if isinstance(consent, str):
            return request.redirect('/invite/%s?error=%s#tso-form' % (token, consent))
        if not public:
            if a.ts_contact_matches(user) is False:
                return request.redirect('/invite/%s' % token)
            return self._ts_accept(a, user, consent)
        channel = a.ts_dlv_channel(dlv_of(post.get('d')))
        if channel:
            value = a.ts_dlv_value(channel)
            u, made = flow.link_user(request.env, channel, value)
            if u:
                flow.scoped_login(u, a, phone=value if channel == 'sms' else (u.partner_id.ts_phone or ''))
                return self._ts_accept(a, request.env.user, consent, made=made)
        phone = a.ts_invite_phone()
        if phone:
            return flow.otp_then(a, phone, dict(consent, do='accept'))
        return request.redirect(signin_url('/invite/%s' % token))

    def _ts_accept(self, a, user, consent, made=False):
        url = flow.accept_now(a, user, consent)
        if not url:
            return request.redirect('/invite/%s?error=rule#tso-form' % a.token)
        if made:
            a.sudo().write({'ts_account_made': True})
        return flow.bind_device(a, request.redirect(url), personal=consent.get('personal', False))

    def _ts_continue(self, a, post):
        """An accepted invitation opened by a visitor who is not signed in: its bound browser, or its message's secret,
        goes on without a code when the account may be signed in so (flow.no_typing_ok); anything else gets a code to
        the invited number (masked); without a number, the ordinary sign-in."""
        owner = a.sudo().user_id
        proven = bool(a.ts_dlv_channel(dlv_of(post.get('d'))))
        if (proven or flow.device_matches(a)) and owner.active and owner.share and flow.no_typing_ok(owner, a):
            flow.scoped_login(owner, a, phone=a.ts_invite_phone() or owner.partner_id.ts_phone or '')
            return request.redirect('/invite/%s' % a.token)
        phone = a.ts_invite_phone() or owner.partner_id.ts_phone or ''
        if phone:
            return flow.otp_then(a, phone, {'do': 'continue'})
        return request.redirect(signin_url('/invite/%s' % a.token))

    @http.route('/invite/<string:token>/decline', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def invite_decline(self, token, **post):
        _ts_site_or_404()
        if not request.env.user._is_public():
            return super().invite_decline(token, **post)
        a = self._invite(token)
        if not a.user_id and a.invite_state() == 'ok':
            try:
                a.action_decline(request.env.user)        # an anonymous «no»: models/assignment.py keeps the account empty
            except UserError:
                pass
        return request.redirect('/invite/%s' % token)


class TsOnbShortLinks(TsBrandLinks):

    @http.route()
    def short_invite(self, code, **kw):
        _ts_site_or_404()
        return counted('short', lambda: super(TsOnbShortLinks, self).short_invite(code, **kw))

    @http.route('/i/<string:code>/<string:secret>', type='http', auth='public', website=True, methods=['GET'],
                sitemap=False)
    def short_invite_proof(self, code, secret, **kw):
        """The link of the system's own SMS: the short code and the delivery secret. The secret goes on to the welcome
        screen (?d=, then a hidden field of its form); it is checked only by the POST."""
        _ts_site_or_404()

        def serve():
            if not CODE_RE.match(code or '') or not dlv_of(secret):
                raise request.not_found()
            a = request.env['ts.assignment'].sudo().search([('short_code', '=', code)], limit=1)  # the code is the key
            if not a:
                raise request.not_found()
            return request.redirect('/invite/%s?d=%s' % (a.token, secret), code=302)
        return counted('short', serve)

    @http.route()
    def short_join(self, code, **kw):
        _ts_site_or_404()
        return counted('short', lambda: super(TsOnbShortLinks, self).short_join(code, **kw))


class TsOnbCampaignJoin(TsPanelCampaignJoin):

    @http.route()
    def campaign_page(self, token, **kw):
        _ts_site_or_404()
        return counted('campaign', lambda: super(TsOnbCampaignJoin, self).campaign_page(token, **kw))
