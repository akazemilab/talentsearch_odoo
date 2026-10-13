"""O2: one-tap invitations (design §5 P2, P3, minors; docs/onboarding/02_invites_and_guest.md).

GET /invite/<token> is the welcome screen and never consumes, accepts or binds anything (messenger previews open links):
it may only mark the invitation as opened, as before. The POST of «موافقم و شروع می‌کنم» is the consent (recorded with
the consent text version) and the acceptance:
  * signed in as the invited person (or the invitation names no number): accept at once;
  * not signed in, the link came by SMS to P (or e-mail to E): signed in as the account of P / E for this invitation only
    (ir_http), the invitation bound to this browser;
  * not signed in, no proof but a number on the invitation: a code to that number, shown masked; then accept;
  * nothing known: the ordinary sign-in first, as before.
A later open from another browser (no matching ts_dev cookie) sends a code to the invited number (masked) instead.
A signed-in account that is not the invited number or address sees one clear notice and one action (sign out and go on).
Short links /i/, /j/ and the open link /c/ are rate-limited per hashed address (30 a minute, then a polite 429 page)."""
from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import CONSENT_VERSION, fa_digits
from odoo.addons.ts_battery.controllers.main import battery_url
from odoo.addons.ts_brand.controllers.main import TsBrandLinks
from odoo.addons.ts_org.controllers.main import INVITE_MSG, TsOrg
from odoo.addons.ts_panel.controllers.campaigns_public import TsPanelCampaignJoin
from odoo.addons.ts_sms.controllers.signup import mask_mobile, signin_url

from ..models.common import first_name, mask_email
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


def short_limited():
    """30 short-link lookups a minute per hashed address (ts_onboard.short_per_minute); then a polite 429 page."""
    limit = request.env['ir.config_parameter'].sudo().get_int('ts_onboard.short_per_minute', 30) or 30
    ip = request.env['ts.audit.event'].sudo()._hash_ip(request.httprequest.remote_addr)
    if request.env['ts.rate.hit'].ts_hit('short:%s' % ip, limit, 60):
        return None
    resp = request.render('ts_onboard.slow', {'page_name': 'ts_slow'}, status=429)
    resp.headers['Retry-After'] = '60'
    return resp


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
        matrix = (inst.current_version_id.mode == 'matrix') if not bat else False
        values = {
            'a': a, 'ws': ws, 'inst': inst, 'bat': bat, 'pos': pos, 'mode': mode, 'tu': tu, 'fa': fa_digits,
            'hello': first_name(a.invitee_name), 'org': ws.ts_public_name(), 'counselor': counselor,
            'minutes': (bat.est_minutes if bat else inst.duration_minutes) or 0, 'parts': len(insts),
            'items': (bat.item_count if bat else inst.active_item_count) or 0, 'matrix': matrix,
            'item_names': [i.ts_title() for i in insts] if bat else [],
            'timed': any(i.ts_is_task_inst() for i in insts if hasattr(i, 'ts_is_task_inst')),
            'need': need, 'guardian_text': GUARDIAN_TEXT.get(need['text']), 'consent_version': CONSENT_VERSION,
            'inv_msg': INVITE_MSG, 'error': None, 'page_name': 'ts_invite',
            'logout_url': '/web/session/logout?redirect=%s' % quote('/invite/%s' % a.token),
        }
        values.update(extra)
        return values

    @http.route()
    def invite_page(self, token, **kw):
        _ts_site_or_404()
        a = self._invite(token, paused_ok=True)
        user = request.env.user
        public = user._is_public()
        if not public and a.user_id == user:
            if a.state == 'done' or (a.attempt_id and a.attempt_id.state == 'done' and not a.battery_id):
                return request.redirect(battery_url(a) if a.battery_id else '/my/assessments/%s' % a.attempt_id.id)
            nxt = flow.first_open(a)
            if nxt:
                return request.redirect('/take/%s' % nxt.access_token)
        inv_state = 'paused' if a.workspace_id.state == 'suspended' else a.invite_state()
        if inv_state not in ('ok', 'used'):
            return request.render('ts_onboard.welcome', self._ts_values(a, 'state', inv_state=inv_state))
        if a.user_id:                                # accepted earlier, by this person on another browser or by someone else
            if public:
                return request.render('ts_onboard.welcome', self._ts_values(a, 'continue', done=a.state == 'done'))
            return request.render('ts_onboard.welcome', self._ts_values(a, 'other', contact=self._ts_contact(a)))
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
            a, 'welcome', error=error, public=public, name_mismatch=name_mismatch,
            ask_decline=kw.get('decline') == '1'))

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
                return request.redirect('/invite/%s' % token)       # the welcome screen answers (player or notice)
            return self._ts_continue(a)
        if a.invite_state() != 'ok':
            return request.redirect('/invite/%s' % token)
        consent = flow.consent_from(post, a)
        if isinstance(consent, str):
            return request.redirect('/invite/%s?error=%s#tso-form' % (token, consent))
        if not public:
            if a.ts_contact_matches(user) is False:
                return request.redirect('/invite/%s' % token)
            return self._ts_accept(a, user, consent)
        via, value = a.ts_proof()
        if via:
            u = flow.link_user(via, value)
            if u:
                flow.scoped_login(u, a, phone=value if via == 'sms' else (u.partner_id.ts_phone or ''))
                return self._ts_accept(a, request.env.user, consent)
        phone = a.ts_invite_phone()
        if phone:
            return flow.otp_then(a, phone, dict(consent, do='accept'))
        return request.redirect(signin_url('/invite/%s' % token))

    def _ts_accept(self, a, user, consent):
        url = flow.accept_now(a, user, consent)
        if not url:
            return request.redirect('/invite/%s?error=rule#tso-form' % a.token)
        return flow.bind_device(a, request.redirect(url))

    def _ts_continue(self, a):
        """An accepted invitation opened by a visitor who is not signed in: this browser goes on; another one gets a code
        to the invited number (masked); without a number, the ordinary sign-in."""
        owner = a.sudo().user_id
        if flow.device_matches(a) and owner.active and owner.share:
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
        return short_limited() or super().short_invite(code, **kw)

    @http.route()
    def short_join(self, code, **kw):
        _ts_site_or_404()
        return short_limited() or super().short_join(code, **kw)


class TsOnbCampaignJoin(TsPanelCampaignJoin):

    @http.route()
    def campaign_page(self, token, **kw):
        _ts_site_or_404()
        return short_limited() or super().campaign_page(token, **kw)
