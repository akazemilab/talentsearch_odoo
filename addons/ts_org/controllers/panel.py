from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from urllib.parse import quote

from odoo.addons.ts_org.controllers.main import _membership
from odoo.addons.ts_org.models.panel import ROLE_LABELS, TERMS_VERSION

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
        return urls.get('phone_url') or urls.get('signup_url') or urls.get('login_url')

    # --------------------------------------------------------------- landing + terms
    @http.route('/panel', type='http', auth='public', website=True, sitemap=False)
    def landing(self, **kw):
        _ts_site_or_404()
        return request.render('ts_org.panel_landing', {
            'cta_url': '/my/workspaces/new', 'page_name': 'ts_panel'})

    @http.route('/panel/terms', type='http', auth='public', website=True, sitemap=False)
    def terms(self, **kw):
        _ts_site_or_404()
        return request.render('ts_org.panel_terms', {'version': TERMS_VERSION, 'page_name': 'ts_panel'})

    # --------------------------------------------------------------- create
    @http.route('/my/workspaces/new', type='http', auth='public', website=True, sitemap=False)
    def create_form(self, **kw):
        _ts_site_or_404()
        if request.env.user._is_public():
            return request.redirect(self._login_url('/my/workspaces/new'))
        return request.render('ts_org.panel_new', {
            'error': _flash(), 'vals': {}, 'page_name': 'ts_panel'})

    @http.route('/my/workspaces/new/create', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def create(self, **post):
        _ts_site_or_404()
        vals = {k: (post.get(k) or '')[:120] for k in ('name', 'kind', 'solo_as')}
        try:
            ws = request.env['ts.workspace'].ts_panel_create(
                request.env.user, post.get('name'), post.get('kind'), solo_as=post.get('solo_as'),
                terms=bool(post.get('terms')), escalation_ok=bool(post.get('escalation_ok')))
        except (UserError, ValidationError) as e:
            return request.render('ts_org.panel_new', {
                'error': str(e.args[0] if e.args else e), 'vals': vals, 'page_name': 'ts_panel'})
        return request.redirect('/my/workspaces/%s?new=1' % ws.id)

    # --------------------------------------------------------------- settings
    @http.route('/my/workspaces/<int:ws_id>/settings', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def settings(self, ws_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        if not member.can_assign():
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
        if not inv or not member.can_assign():
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
            'fits': signed and inv.matches(user), 'role_label': ROLE_LABELS.get(inv.role, inv.role),
            'urls': self._auth_urls('/join/' + token), 'error': _flash(), 'page_name': 'ts_panel'})

    @http.route('/join/<string:token>/accept', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def join_accept(self, token, **post):
        _ts_site_or_404()
        inv = self._invite(token)
        try:
            m = inv.action_accept(request.env.user, license_number=post.get('license_number'))
        except (UserError, ValidationError) as e:
            _flash(str(e.args[0] if e.args else e))
            return request.redirect('/join/%s' % token)
        return request.redirect('/my/workspaces/%s' % m.workspace_id.id)
