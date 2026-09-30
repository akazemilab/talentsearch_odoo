from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_org.models.assignment import RESPONSIBLE_ROLES
from odoo.addons.ts_org.models.panel import role_choices


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
    if not a or not member.can_see(a):
        raise request.not_found()
    return a


def _scope(member, records):
    """Only what this member may see: everything for owners/managers, else their own."""
    return records.filtered(member.can_see)


def _assignable(member):
    """Members a participant can be handed to (owner/manager view only)."""
    if not member.can_assign():
        return request.env['ts.workspace.member']
    return member.workspace_id.member_ids.filtered(lambda m: m.active and m.role in RESPONSIBLE_ROLES)


def _counts(assignments):
    keys = ('invited', 'accepted', 'in_progress', 'done', 'declined', 'withdrawn')
    return {k: len(assignments.filtered(lambda a, k=k: a.state == k)) for k in keys}


INVITE_MSG = {
    'expired': ('این دعوت منقضی شده است', 'مهلت دعوت تمام شده است. از سازمان یا مؤسسهٔ دعوت‌کننده بخواهید دعوت تازه بفرستد.'),
    'used': ('این دعوت قبلاً استفاده شده است', 'این پیوند با یک حساب دیگر پذیرفته شده است. اگر اشتباهی رخ داده، از دعوت‌کننده بخواهید دعوت تازه بفرستد.'),
    'declined': ('این دعوت رد شده است', 'برای شرکت در سنجه از دعوت‌کننده بخواهید دعوت تازه بفرستد.'),
    'withdrawn': ('این دعوت دیگر فعال نیست', 'دعوت‌کننده آن را لغو کرده است. برای اطلاعات بیشتر با او تماس بگیرید.'),
}


class TsOrg(http.Controller):

    # ------------------------------------------------------- organization side
    @http.route('/my/workspaces', type='http', auth='user', website=True, sitemap=False)
    def workspaces(self, **kw):
        _ts_site_or_404()
        rows = []
        for m in _memberships():
            ws = m.workspace_id
            rows.append({'member': m, 'ws': ws, 'usable': m.can_act(),
                         'counts': _counts(_scope(m, request.env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id)])))})
        return request.render('ts_org.workspaces', {'rows': rows, 'fa': fa_digits, 'page_name': 'ts_workspaces'})

    @http.route('/my/workspaces/<int:ws_id>', type='http', auth='user', website=True, sitemap=False)
    def workspace(self, ws_id, state=None, **kw):
        _ts_site_or_404()
        member = _membership(ws_id)
        ws = member.workspace_id
        allx = _scope(member, request.env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id)]))
        resp = kw.get('resp')
        shown = allx.filtered(lambda a: a.state == state) if state else allx
        imports = request.env['ts.attempt']
        src = kw.get('src')
        if ws.purpose == 'education':
            imports = request.env['ts.attempt'].sudo().search([
                ('workspace_id', '=', ws.id), ('source', '=', 'import'), ('state', '=', 'done')],
                order='submitted_at desc, id desc')
            imports = _scope(member, imports)
            if src == 'invite':
                imports = imports.browse()
            if src == 'import':
                shown = shown.browse()
        un_a = allx.filtered(lambda r: not r.responsible_id)
        un_i = imports.filtered(lambda r: not r.responsible_id)
        mi_a = allx.filtered(lambda r: r.responsible_id == member)
        mi_i = imports.filtered(lambda r: r.responsible_id == member)
        unassigned, mine = len(un_a) + len(un_i), len(mi_a) + len(mi_i)
        if resp == 'none':
            shown, imports = shown & un_a, imports & un_i
        elif resp == 'mine':
            shown, imports = shown & mi_a, imports & mi_i
        return request.render('ts_org.workspace', {
            'resp_filter': resp, 'unassigned_count': unassigned, 'mine_count': mine,
            'can_assign': member.can_assign(), 'assignable': _assignable(member),
            'show_unassigned': member.sees_unassigned(),
            'imports': imports, 'src_filter': src,
            'member': member, 'ws': ws, 'assignments': shown, 'counts': _counts(allx), 'total': len(allx),
            'state_filter': state, 'instruments': member.allowed_instruments() if member.can_invite() else [],
            'created': request.env['ts.assignment'].sudo().browse(int(kw['created'])).exists()
            if kw.get('created', '').isdigit() else None,
            'error': kw.get('error'), 'fa': fa_digits, 'page_name': 'ts_workspaces',
            'others': [m for m in _memberships() if m.workspace_id != ws and m.can_act()],
            'is_new': bool(kw.get('new')), 'flash': request.session.pop('ts_flash', None),
            'can_invite_participants': member.can_invite_participants(),
            'checklist': self._checklist(member, ws),
            'members': ws.member_ids.filtered('active') if member.can_assign() else request.env['ts.workspace.member'],
            'pending_invites': request.env['ts.member.invite'].sudo().search(
                [('workspace_id', '=', ws.id), ('state', '=', 'pending')]) if member.can_assign() else None,
            'new_invite': request.env['ts.member.invite'].sudo().search(
                [('id', '=', int(kw['minv'])), ('workspace_id', '=', ws.id)], limit=1)
            if member.can_assign() and (kw.get('minv') or '').isdigit() else None,
            'role_choices': role_choices(ws) if member.can_assign() else [],
        })

    def _checklist(self, member, ws):
        if not member.can_assign():
            return []
        others = len(ws.member_ids.filtered(lambda m: m.active and m != member)) + \
            request.env['ts.member.invite'].sudo().search_count([('workspace_id', '=', ws.id)])
        first = request.env['ts.assignment'].sudo().search_count([('workspace_id', '=', ws.id)])
        return [
            ('پنل ساخته شد', True, None),
            ('نام و لوگوی پنل', bool(ws.partner_id.image_1920), '#ts-settings'),
            ('دعوت اولین همکار', bool(others), '#ts-members'),
            ('دعوت اولین شرکت‌کننده' + (' (پس از تأیید)' if ws.gated else ''), bool(first), '#ts-invite'),
        ]

    @http.route('/my/workspaces/<int:ws_id>/invite', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def invite(self, ws_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        if not member.can_invite():
            raise request.not_found()
        if not member.can_invite_participants():
            return request.redirect('/my/workspaces/%s?error=pending' % ws_id)
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

    def _set_responsible(self, member, rec, post):
        """Owner/manager hands a record to a specialist of the same workspace, or clears it."""
        if not member.can_assign():
            raise request.not_found()
        rid = (post.get('responsible_id') or '').strip()
        target = request.env['ts.workspace.member']
        if rid:
            target = _assignable(member).filtered(lambda m: str(m.id) == rid)
            if not target:
                return False
        try:
            rec.write({'responsible_id': target.id or False})
        except (UserError, ValidationError):
            return False
        return True

    @http.route('/my/workspaces/<int:ws_id>/a/<int:assignment_id>/responsible', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def assignment_responsible(self, ws_id, assignment_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        a = _assignment(member, assignment_id)
        ok = self._set_responsible(member, a, post)
        return request.redirect('/my/workspaces/%s%s' % (ws_id, '' if ok else '?error=rule'))

    @http.route('/my/workspaces/<int:ws_id>/p/<int:attempt_id>/responsible', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def import_responsible(self, ws_id, attempt_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        at = request.env['ts.attempt'].sudo().search([
            ('id', '=', int(attempt_id)), ('workspace_id', '=', member.workspace_id.id),
            ('source', '=', 'import')], limit=1)
        if not at or not member.can_see(at):
            raise request.not_found()
        ok = self._set_responsible(member, at, post)
        return request.redirect('/my/workspaces/%s%s' % (ws_id, '' if ok else '?error=rule'))

    # -------------------------------------------------------- participant side
    def _auth_urls(self, path):
        """Sign-in links for a public visitor; ts_sms adds mobile sign-in (phone_url)."""
        redirect = quote(path)
        return {'login_url': '/web/login?redirect=%s' % redirect, 'signup_url': '/web/signup?redirect=%s' % redirect,
                'phone_url': None}

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
        inv_state = a.invite_state()
        return request.render('ts_org.invite', {
            'a': a, 'inst': a.instrument_id, 'ws': a.workspace_id, 'public': user._is_public(),
            'fa': fa_digits, **self._auth_urls('/invite/%s' % token),
            'inv_state': inv_state if not (inv_state == 'used' and a.user_id == user) else 'ok',
            'inv_msg': INVITE_MSG,
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
