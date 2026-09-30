from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits


def _memberships():
    return request.env['ts.workspace.member'].sudo().search([
        ('user_id', '=', request.env.user.id), ('active', '=', True)])


def _membership(ws_id):
    """The current user's usable membership in workspace ws_id, else 404."""
    members = _memberships().filtered(lambda m: m.workspace_id.id == int(ws_id))
    member = members.filtered(lambda m: m.can_act())[:1]
    if not member:
        raise request.not_found()
    return member


def _assignment(member, assignment_id):
    a = request.env['ts.assignment'].sudo().search([
        ('id', '=', int(assignment_id)), ('workspace_id', '=', member.workspace_id.id)], limit=1)
    if not a:
        raise request.not_found()
    return a


def _counts(assignments):
    keys = ('invited', 'accepted', 'in_progress', 'done', 'declined', 'withdrawn')
    return {k: len(assignments.filtered(lambda a, k=k: a.state == k)) for k in keys}


class TsOrg(http.Controller):

    # ------------------------------------------------------- organization side
    @http.route('/my/workspaces', type='http', auth='user', website=True, sitemap=False)
    def workspaces(self, **kw):
        _ts_site_or_404()
        rows = []
        for m in _memberships():
            ws = m.workspace_id
            rows.append({'member': m, 'ws': ws, 'usable': m.can_act(),
                         'counts': _counts(request.env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id)]))})
        return request.render('ts_org.workspaces', {'rows': rows, 'fa': fa_digits, 'page_name': 'ts_workspaces'})

    @http.route('/my/workspaces/<int:ws_id>', type='http', auth='user', website=True, sitemap=False)
    def workspace(self, ws_id, state=None, **kw):
        _ts_site_or_404()
        member = _membership(ws_id)
        ws = member.workspace_id
        allx = request.env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id)])
        shown = allx.filtered(lambda a: a.state == state) if state else allx
        imports = request.env['ts.attempt']
        src = kw.get('src')
        if ws.purpose == 'education':
            imports = request.env['ts.attempt'].sudo().search([
                ('workspace_id', '=', ws.id), ('source', '=', 'import'), ('state', '=', 'done')],
                order='submitted_at desc, id desc')
            if src == 'invite':
                imports = imports.browse()
            if src == 'import':
                shown = shown.browse()
        return request.render('ts_org.workspace', {
            'imports': imports, 'src_filter': src,
            'member': member, 'ws': ws, 'assignments': shown, 'counts': _counts(allx), 'total': len(allx),
            'state_filter': state, 'instruments': member.allowed_instruments() if member.can_invite() else [],
            'created': request.env['ts.assignment'].sudo().browse(int(kw['created'])).exists()
            if kw.get('created', '').isdigit() else None,
            'error': kw.get('error'), 'fa': fa_digits, 'page_name': 'ts_workspaces',
        })

    @http.route('/my/workspaces/<int:ws_id>/invite', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def invite(self, ws_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        if not member.can_invite():
            raise request.not_found()
        name = (post.get('invitee_name') or '').strip()
        inst_id = post.get('instrument_id') or ''
        allowed = member.allowed_instruments()
        if not name or not inst_id.isdigit() or int(inst_id) not in allowed.ids:
            return request.redirect('/my/workspaces/%s?error=form' % ws_id)
        try:
            a = request.env['ts.assignment'].sudo().create({
                'workspace_id': member.workspace_id.id, 'instrument_id': int(inst_id),
                'invitee_name': name[:120], 'invitee_email': (post.get('invitee_email') or '').strip()[:200] or False,
                'note': (post.get('note') or '').strip()[:300] or False,
                'invited_by_id': request.env.user.id,
            })
        except (UserError, ValidationError):
            return request.redirect('/my/workspaces/%s?error=rule' % ws_id)
        return request.redirect('/my/workspaces/%s?created=%s' % (ws_id, a.id))

    @http.route('/my/workspaces/<int:ws_id>/a/<int:assignment_id>', type='http', auth='user',
                website=True, sitemap=False)
    def assignment(self, ws_id, assignment_id, **kw):
        _ts_site_or_404()
        member = _membership(ws_id)
        a = _assignment(member, assignment_id)
        level, results = a.visible_results(member)
        if level == 'education' and a.attempt_id:
            return request.redirect('/my/workspaces/%s/p/%s' % (ws_id, a.attempt_id.id))
        if level != 'none':
            request.env['ts.audit.event'].sudo().log('assignment.result_view', a, workspace=a.workspace_id,
                                                     level=level, viewer=request.env.user.id)
        return request.render('ts_org.assignment', {
            'member': member, 'ws': member.workspace_id, 'a': a, 'level': level, 'results': results,
            'attempt': a.attempt_id, 'inst': a.instrument_id, 'fa': fa_digits, 'page_name': 'ts_workspaces',
        })

    @http.route('/my/workspaces/<int:ws_id>/a/<int:assignment_id>/withdraw', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def withdraw(self, ws_id, assignment_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        if not member.can_invite():
            raise request.not_found()
        a = _assignment(member, assignment_id)
        try:
            a.action_withdraw()
        except UserError:
            pass
        return request.redirect('/my/workspaces/%s/a/%s' % (ws_id, a.id))

    # -------------------------------------------------------- participant side
    def _invite(self, token):
        a = request.env['ts.assignment'].sudo().search([('token', '=', token)], limit=1)
        if not a or a.workspace_id.state not in ('pilot', 'active'):
            raise request.not_found()
        return a

    @http.route('/invite/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def invite_page(self, token, **kw):
        _ts_site_or_404()
        a = self._invite(token)
        user = request.env.user
        if a.user_id and not user._is_public() and a.user_id != user:
            raise request.not_found()
        if a.attempt_id and a.user_id == user and a.state in ('accepted', 'in_progress'):
            return request.redirect('/take/%s' % a.attempt_id.access_token)
        if a.state == 'done' and a.user_id == user:
            return request.redirect('/my/assessments/%s' % a.attempt_id.id)
        redirect = quote('/invite/%s' % token)
        return request.render('ts_org.invite', {
            'a': a, 'inst': a.instrument_id, 'ws': a.workspace_id, 'public': user._is_public(),
            'login_url': '/web/login?redirect=%s' % redirect, 'signup_url': '/web/signup?redirect=%s' % redirect,
            'fa': fa_digits,
        })

    @http.route('/invite/<string:token>/accept', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def invite_accept(self, token, **post):
        _ts_site_or_404()
        a = self._invite(token)
        try:
            attempt = a.action_accept(request.env.user, share=post.get('share') == '1')
        except UserError:
            raise request.not_found()
        return request.redirect('/take/%s' % attempt.access_token)

    @http.route('/invite/<string:token>/decline', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def invite_decline(self, token, **post):
        _ts_site_or_404()
        a = self._invite(token)
        try:
            a.action_decline(request.env.user)
        except UserError:
            raise request.not_found()
        return request.redirect('/my/assessments')

    @http.route('/my/assessments/<int:attempt_id>/unshare', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def unshare(self, attempt_id, **post):
        _ts_site_or_404()
        a = request.env['ts.assignment'].sudo().search([
            ('attempt_id', '=', attempt_id), ('user_id', '=', request.env.user.id)], limit=1)
        if not a:
            raise request.not_found()
        a.action_revoke_share(request.env.user)
        return request.redirect('/my/assessments/%s' % attempt_id)
