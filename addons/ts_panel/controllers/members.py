from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_core.models.workspace import ROLES_BY_PURPOSE
from odoo.addons.ts_org.models.panel import ROLE_LABELS

from ..perm_labels import LIVE, PERM_LABELS, ROLE_BLURBS, ROLE_ORDER
from .base import (flash_error, flash_ok, forbidden, member_or_404, need_reauth, render_in_shell, require)

MEMBER_STATE = {
    'active': ('فعال', 'ts-pill--ok'),
    'awaiting': ('در انتظار احراز صلاحیت', 'ts-pill--warn'),
    'inactive': ('غیرفعال', 'ts-pill--neutral'),
}


def _roles_for(ws, me):
    """Roles that can be handed out in this panel, in a fixed order, with their one-line description."""
    allowed = ROLES_BY_PURPOSE.get(ws.purpose, set())
    out = []
    for r in ROLE_ORDER:
        if r in allowed and (r != 'owner' or me.has_perm('members:add_owner')):
            out.append({'key': r, 'label': ROLE_LABELS.get(r, r), 'blurb': ROLE_BLURBS.get(r, '')})
    return out


def _other_member(me, mid):
    m = request.env['ts.workspace.member'].sudo().with_context(active_test=False).search(
        [('id', '=', int(mid)), ('workspace_id', '=', me.workspace_id.id)])
    if not m:
        raise request.not_found()
    return m


def _pending(ws_id, kind):
    p = request.session.pop('ts_pv2_pending', None) or {}
    return p if p.get('ws') == ws_id and p.get('kind') == kind else {}


class TsPanelMembers(http.Controller):

    # ------------------------------------------------------------------ list + invitations
    @http.route('/my/workspaces/<int:ws_id>/members', type='http', auth='user', website=True, sitemap=False)
    def members(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'members:read', 'members')
        if denied:
            return denied
        ws = me.workspace_id
        rows = []
        everyone = request.env['ts.workspace.member'].sudo().with_context(active_test=False).search(
            [('workspace_id', '=', ws.id)])
        for m in everyone.sorted(lambda x: (not x.active, ROLE_ORDER.index(x.role) if x.role in ROLE_ORDER else 99, x.id)):
            key = m.ts_state_key()
            rows.append({'m': m, 'name': m.user_id.name, 'role': ROLE_LABELS.get(m.role, m.role),
                         'state': MEMBER_STATE[key][0], 'pill': MEMBER_STATE[key][1],
                         'clients': m.ts_client_count() if m.active else 0,
                         'last': jalali_or_dash(m.ts_last_activity()), 'self': m == me})
        can_invite = me.has_perm('members:invite')
        invites = request.env['ts.member.invite'].sudo().search(
            [('workspace_id', '=', ws.id), ('state', '=', 'pending')]) if can_invite else request.env['ts.member.invite']
        new_inv = request.env['ts.member.invite'].sudo().search(
            [('id', '=', int(kw['minv'])), ('workspace_id', '=', ws.id)], limit=1) \
            if can_invite and (kw.get('minv') or '').isdigit() else None
        pend = _pending(ws_id, 'invite') if can_invite else {}
        return render_in_shell(
            'ts_panel.members', me, 'members', 'اعضا و نقش‌ها', rows=rows, can_invite=can_invite,
            can_manage=me.has_perm('members:manage'), invites=invites, new_inv=new_inv, roles=_roles_for(ws, me),
            vals=pend, resumed=bool(pend), solo=len([r for r in rows if r['m'].active]) == 1 and not invites,
            role_label=ROLE_LABELS.get(me.role, me.role), expires=lambda i: jalali_or_dash(i.expires_at),
            invite_role_label=lambda i: ROLE_LABELS.get(i.role, i.role))

    @http.route('/my/workspaces/<int:ws_id>/members/add', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def member_add(self, ws_id, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'members:invite', 'members')
        if denied:
            return denied
        role = post.get('role')
        if role == 'owner':
            denied = require(me, 'members:add_owner', 'members')
            if denied:
                return denied
            back = need_reauth('اضافه‌کردن مالک', '/my/workspaces/%s/members' % ws_id,
                               {'ws': ws_id, 'kind': 'invite', 'role': role, 'phone': post.get('phone', '')[:40],
                                'email': post.get('email', '')[:200]})
            if back:
                return back
        try:
            inv = request.env['ts.member.invite'].ts_create(me, role, phone_raw=post.get('phone'), email_raw=post.get('email'))
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect('/my/workspaces/%s/members' % ws_id)
        return request.redirect('/my/workspaces/%s/members?minv=%s' % (ws_id, inv.id))

    @http.route('/my/workspaces/<int:ws_id>/members/invites/<int:inv_id>/<string:action>', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def invite_action(self, ws_id, inv_id, action, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'members:invite', 'members')
        if denied:
            return denied
        inv = request.env['ts.member.invite'].sudo().search([('id', '=', inv_id), ('workspace_id', '=', ws_id)])
        if not inv or action not in ('resend', 'revoke'):
            raise request.not_found()
        try:
            if action == 'revoke':
                inv.action_revoke()
                flash_ok('دعوت لغو شد؛ پیوند آن دیگر کار نمی‌کند.')
            else:
                new = inv.ts_resend(me)
                return request.redirect('/my/workspaces/%s/members?minv=%s' % (ws_id, new.id))
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        return request.redirect('/my/workspaces/%s/members' % ws_id)

    # ------------------------------------------------------------------ one member
    @http.route('/my/workspaces/<int:ws_id>/members/<int:mid>', type='http', auth='user', website=True, sitemap=False)
    def member_page(self, ws_id, mid, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'members:read', 'members')
        if denied:
            return denied
        m = _other_member(me, mid)
        ws = me.workspace_id
        pend = _pending(ws_id, 'role')
        key = m.ts_state_key()
        return render_in_shell(
            'ts_panel.member', me, 'members', m.user_id.name, m=m, state=MEMBER_STATE[key][0], pill=MEMBER_STATE[key][1],
            m_role=ROLE_LABELS.get(m.role, m.role), clients=m.ts_client_count() if m.active else 0,
            last=jalali_or_dash(m.ts_last_activity()), can_manage=me.has_perm('members:manage'), is_self=m == me,
            roles=_roles_for(ws, me), chosen=pend.get('role') or m.role, resumed=bool(pend),
            clinical=ws.purpose == 'clinical')

    @http.route('/my/workspaces/<int:ws_id>/members/<int:mid>/role', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def member_role(self, ws_id, mid, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'members:manage', 'members')
        if denied:
            return denied
        m = _other_member(me, mid)
        back = '/my/workspaces/%s/members/%s' % (ws_id, mid)
        role = post.get('role')
        if role == 'owner' and m.role != 'owner':
            back_reauth = need_reauth('اضافه‌کردن مالک', back, {'ws': ws_id, 'kind': 'role', 'role': role})
            if back_reauth:
                return back_reauth
        try:
            changed = m.ts_change_role(me, role)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('نقش تغییر کرد.' if changed else 'نقش تغییری نکرد.')
        return request.redirect(back)

    @http.route('/my/workspaces/<int:ws_id>/members/<int:mid>/deactivate', type='http', auth='user', website=True,
                methods=['GET', 'POST'], sitemap=False)
    def member_deactivate(self, ws_id, mid, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'members:manage', 'members')
        if denied:
            return denied
        m = _other_member(me, mid)
        if request.httprequest.method == 'POST':
            try:
                n = m.ts_deactivate(me)
            except (UserError, ValidationError) as e:
                flash_error(str(e.args[0] if e.args else e))
                return request.redirect('/my/workspaces/%s/members/%s' % (ws_id, mid))
            flash_ok('«%s» غیرفعال شد.%s' % (m.user_id.name, (' %s شرکت‌کننده به صف «تخصیص‌نشده» رفت.' % _fa(n)) if n else ''))
            return request.redirect('/my/workspaces/%s/members' % ws_id)
        if not m.active:
            return request.redirect('/my/workspaces/%s/members/%s' % (ws_id, mid))
        return render_in_shell('ts_panel.member_deactivate', me, 'members', 'غیرفعال‌کردن عضو', m=m,
                               clients=m.ts_client_count(), is_self=m == me)

    @http.route('/my/workspaces/<int:ws_id>/members/<int:mid>/reactivate', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def member_reactivate(self, ws_id, mid, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'members:manage', 'members')
        if denied:
            return denied
        m = _other_member(me, mid)
        try:
            m.ts_reactivate(me)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('«%s» دوباره فعال شد.' % m.user_id.name)
        return request.redirect('/my/workspaces/%s/members/%s' % (ws_id, mid))

    @http.route('/my/workspaces/<int:ws_id>/members/<int:mid>/practice', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def member_practice(self, ws_id, mid, **post):
        me = member_or_404(ws_id)
        m = _other_member(me, mid)
        if m != me:
            return forbidden(me, 'members:practice_self', 'members')
        try:
            me.ts_set_practising(me, bool(post.get('practises')), post.get('license_number'))
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('ذخیره شد.')
        return request.redirect('/my/workspaces/%s/members/%s' % (ws_id, mid))

    # ------------------------------------------------------------------ role help
    @http.route('/help/roles', type='http', auth='user', website=True, sitemap=False)
    def help_roles(self, **kw):
        from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
        _ts_site_or_404()
        from odoo.addons.ts_org.models.perms import ROLE_PERMS
        purpose = request.env['ts.workspace.member'].sudo().search(  # ts-scope-ok: the caller's own membership, found by user
            [('user_id', '=', request.env.user.id), ('active', '=', True)], limit=1).workspace_id.purpose or 'education'
        roles = [r for r in ROLE_ORDER if r in ROLES_BY_PURPOSE.get(purpose, set())]
        perms = [p for p in PERM_LABELS if p in LIVE]
        table = [{'perm': p, 'label': PERM_LABELS[p],
                  'cells': [p in ROLE_PERMS[(r, purpose)] for r in roles]} for p in perms]
        return request.render('ts_panel.help_roles', {
            'roles': [{'key': r, 'label': ROLE_LABELS.get(r, r), 'blurb': ROLE_BLURBS.get(r, '')} for r in roles],
            'table': table, 'purpose_label': dict(request.env['ts.workspace']._fields['purpose'].selection).get(purpose),
            'page_name': 'ts_panel_help'})


def jalali_or_dash(dt):
    from odoo.addons.ts_assessment.models.attempt import jalali
    return jalali(dt, with_time=False) if dt else '—'


def _fa(n):
    from odoo.addons.ts_assessment.models.attempt import fa_digits
    return fa_digits(n)
