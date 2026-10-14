from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits, jalali_long
from urllib.parse import quote

from odoo.addons.ts_org.controllers.main import _membership
from odoo.addons.ts_org.models.panel import ROLE_LABELS, TERMS_LABEL, role_label, TERMS_VERSION

PANEL_KINDS = ('school', 'org', 'clinic', 'solo')


def mask_identity(phone, email):
    """Masked contact a colleague invite is bound to, e.g. ۰۹۱۲…۸۹ or a…@example.com (UX audit G1-P10-1)."""
    if phone:
        return fa_digits(phone[:4] + '\u200e…\u200e' + phone[-2:])   # LRM: Persian digits (bidi AN) would swap the parts
    if email and '@' in email:
        user, dom = email.split('@', 1)
        return user[:1] + '…@' + dom
    return ''

def _need_name():
    """An account made by mobile code alone has no name yet; forms where others will see the person ask for it."""
    return bool(request.env.user.partner_id.sudo().ts_name_unknown)


def _take_own_name(post):
    """Store «نام شما» from a form when the account has no name yet. Raises UserError on a missing or bad name."""
    if not _need_name():
        return
    name = ' '.join((post.get('own_name') or '').split())
    if not 2 <= len(name) <= 80:
        raise UserError('نام و نام خانوادگی خود را بنویسید (۲ تا ۸۰ نویسه)؛ همکاران و مراجعان این نام را می‌بینند.')
    request.env.user.sudo().write({'name': name})
    request.env['ts.audit.event'].sudo().log('account.name')


def _take_panel_name(post):
    """«نام شما» on the panel form (onb3: always on the form, filled with the account's name). An account without a name
    must give one; a known name is updated only when the person changed it (2 to 80 characters)."""
    name = ' '.join((post.get('own_name') or '').split())
    if _need_name():
        return _take_own_name(post)
    if not name or name == (request.env.user.name or '').strip():
        return
    if not 2 <= len(name) <= 80:
        raise UserError('نام و نام خانوادگی خود را بنویسید (۲ تا ۸۰ نویسه)؛ همکاران و مراجعان این نام را می‌بینند.')
    request.env.user.sudo().write({'name': name})
    request.env['ts.audit.event'].sudo().log('account.name')


def _flash(msg=None):
    if msg:
        request.session['ts_flash'] = msg
        return None
    return request.session.pop('ts_flash', None)


class TsPanel(http.Controller):

    def _auth_urls(self, path):
        """Sign-in links for a public visitor; ts_sms adds mobile sign-in (phone_url)."""
        redirect = quote(path)
        return {'login_url': '/web/login?redirect=%s' % redirect, 'signup_url': '/web/signup?redirect=%s' % redirect,
                'phone_url': None}

    def _login_url(self, path):
        urls = self._auth_urls(path)
        return urls.get('phone_url') or urls.get('login_url') or urls.get('signup_url')   # the Persian sign-in page links to sign-up

    # --------------------------------------------------------------- landing + terms
    @http.route('/panel', type='http', auth='public', website=True, sitemap=False)
    def landing(self, **kw):
        _ts_site_or_404()
        if kw.get('kind') in PANEL_KINDS:
            # an audience page's «ساخت پنل رایگان» lands in the one form with its kind chosen (sign-in first, onb3)
            return request.redirect('/my/workspaces/new?kind=%s' % kw['kind'])
        return request.render('ts_org.panel_landing', {
            'cta_url': '/my/workspaces/new', 'page_name': 'ts_panel'})

    @http.route('/panel/terms', type='http', auth='public', website=True, sitemap=False)
    def terms(self, **kw):
        _ts_site_or_404()
        return request.render('ts_org.panel_terms', {'version': TERMS_VERSION, 'version_label': TERMS_LABEL,
                                                       'page_name': 'ts_panel'})

    # --------------------------------------------------------------- create
    @http.route('/my/workspaces/new', type='http', auth='public', website=True, sitemap=False)
    def create_form(self, **kw):
        _ts_site_or_404()
        kind = kw.get('kind') if kw.get('kind') in PANEL_KINDS else ''
        if request.env.user._is_public():
            return request.redirect(self._login_url('/my/workspaces/new' + ('?kind=' + kind if kind else '')))
        user = request.env.user
        return request.render('ts_org.panel_new', {
            'error': _flash(), 'vals': {'kind': kind, 'own_name': user.partner_id.ts_known_name() or ''},
            'page_name': 'ts_panel', 'need_name': _need_name()})

    @http.route('/my/workspaces/new/create', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def create(self, **post):
        """One form (onb3): kind, panel name, «نام شما». The button is the acceptance of the panel terms (the line under it
        says so, as on the sign-in page); a form of an older page that still sends the tick works the same."""
        _ts_site_or_404()
        vals = {k: (post.get(k) or '')[:120] for k in ('name', 'kind', 'solo_as', 'own_name')}
        try:
            with request.env.cr.savepoint():
                _take_panel_name(post)
            ws = request.env['ts.workspace'].ts_panel_create(
                request.env.user, post.get('name'), post.get('kind'), solo_as=post.get('solo_as') or None,
                terms=bool(post.get('terms') or post.get('accept')), escalation_ok=bool(post.get('escalation_ok')),
                license_number=post.get('license_number'))
        except (UserError, ValidationError) as e:
            return request.render('ts_org.panel_new', {
                'error': str(e.args[0] if e.args else e), 'vals': vals, 'page_name': 'ts_panel', 'need_name': _need_name()})
        return request.redirect('/my/workspaces/%s?new=1' % ws.id)

    # --------------------------------------------------------------- settings
    @http.route('/my/workspaces/<int:ws_id>/settings', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def settings(self, ws_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        if not member.has_perm('panel:profile'):
            raise request.not_found()
        logo = request.httprequest.files.get('logo')
        try:
            member.workspace_id.ts_update_profile(
                name=post.get('name'), logo_bytes=logo.read(600 * 1024) if logo and logo.filename else None)
        except (UserError, ValidationError) as e:
            _flash(str(e.args[0] if e.args else e))
        return request.redirect('/my/workspaces/%s' % ws_id)

    # --------------------------------------------------------------- colleagues
    @http.route('/my/workspaces/<int:ws_id>/members/invite', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def member_invite(self, ws_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        try:
            inv = request.env['ts.member.invite'].ts_create(
                member, post.get('role'), phone_raw=post.get('phone'), email_raw=post.get('email'))
        except (UserError, ValidationError) as e:
            _flash(str(e.args[0] if e.args else e))
            return request.redirect('/my/workspaces/%s#ts-members' % ws_id)
        return request.redirect('/my/workspaces/%s?minv=%s#ts-members' % (ws_id, inv.id))

    @http.route('/my/workspaces/<int:ws_id>/members/revoke/<int:inv_id>', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def member_revoke(self, ws_id, inv_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        inv = request.env['ts.member.invite'].sudo().search([('id', '=', inv_id), ('workspace_id', '=', ws_id)], limit=1)
        if not inv or not member.has_perm('members:invite'):
            raise request.not_found()
        inv.action_revoke()
        return request.redirect('/my/workspaces/%s#ts-members' % ws_id)

    # --------------------------------------------------------------- join by link
    def _invite(self, token):
        inv = request.env['ts.member.invite'].sudo().search([('token', '=', token)], limit=1)
        if not inv:
            raise request.not_found()
        return inv

    @http.route('/join/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def join(self, token, **kw):
        _ts_site_or_404()
        inv = self._invite(token)
        user = request.env.user
        signed = not user._is_public()
        return request.render('ts_org.panel_join', {
            'inv': inv, 'state': inv.usable_state(), 'signed': signed,
            'fits': signed and inv.matches(user), 'role_label': role_label(inv.role, inv.workspace_id.purpose),
            'urls': self._auth_urls('/join/' + token), 'error': _flash(), 'page_name': 'ts_panel',
            'bound_to': mask_identity(inv.phone, inv.email), 'by_phone': bool(inv.phone),
            'inviter': inv.invited_by_id.sudo().name or '', 'expires_fa': jalali_long(inv.expires_at),
            'user_name': user.partner_id.ts_known_name() if signed else '', 'need_name': signed and _need_name(),
            # the signed-in account as its owner knows it: the name, else the masked mobile or e-mail (UX T7 X6, P10-1)
            'account': user.ts_account_label()})

    @http.route('/join/<string:token>/accept', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def join_accept(self, token, **post):
        _ts_site_or_404()
        inv = self._invite(token)
        try:
            _take_own_name(post)
            m = inv.action_accept(request.env.user, license_number=post.get('license_number'))
        except (UserError, ValidationError) as e:
            _flash(str(e.args[0] if e.args else e))
            return request.redirect('/join/%s' % token)
        return request.redirect('/my/workspaces/%s' % m.workspace_id.id)

    # --------------------------------------------------------------- participant -> counselor
    def _own_attempt(self, attempt_id):
        at = request.env['ts.attempt'].sudo().search([
            ('id', '=', int(attempt_id)), ('user_id', '=', request.env.user.id), ('state', '=', 'done')], limit=1)
        if not at:
            raise request.not_found()
        return at

    @http.route('/my/assessments/<int:attempt_id>/share', type='http', auth='user', website=True, sitemap=False)
    def share_form(self, attempt_id, code=None, **kw):
        _ts_site_or_404()
        at = self._own_attempt(attempt_id)
        ws, error = None, _flash()
        if at.workspace_id or at.source == 'import':
            # invited or imported results already belong to their panel; ts_share_attempt() would refuse (G2-P4-1)
            return request.render('ts_org.share_form', {
                'attempt': at, 'ws': None, 'code': '', 'error': error, 'page_name': 'ts_assessments',
                'owned_by': at.workspace_id.sudo(), 'shares': None, 'need_name': _need_name()})
        if code:
            code = code.strip().upper()[:30]
            ws = request.env['ts.workspace'].sudo().search([
                ('code', '=', code), ('purpose', '=', 'education'), ('state', '=', 'active')], limit=1)
            if not ws:
                ws, error = None, 'پنلی با این کد پیدا نشد. کد را از مشاور خود بپرسید.'
        shares = request.env['ts.assignment'].sudo().search(
            [('attempt_id', '=', at.id), ('user_id', '=', request.env.user.id), ('share_level', '!=', 'none')])
        return request.render('ts_org.share_form', {
            'attempt': at, 'ws': ws, 'code': code or '', 'error': error, 'page_name': 'ts_assessments',
            'owned_by': None, 'shares': shares, 'need_name': _need_name()})

    @http.route('/my/assessments/<int:attempt_id>/share/confirm', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def share_confirm(self, attempt_id, **post):
        _ts_site_or_404()
        at = self._own_attempt(attempt_id)
        try:
            _take_own_name(post)
            request.env['ts.assignment'].ts_share_attempt(at, post.get('code'), request.env.user)
        except (UserError, ValidationError) as e:
            _flash(str(e.args[0] if e.args else e))
            return request.redirect('/my/assessments/%s/share' % attempt_id)
        return request.redirect('/my/assessments/%s' % attempt_id)
