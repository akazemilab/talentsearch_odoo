"""Groups of the panel (S5, GRP-1..3): classes, teams and tags. A group never widens what anyone may see:
the member list of a group page is filtered by the same relationship rules as the client list."""
from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from ..models.group import KINDS
from ..models.text import norm_text
from .base import flash_error, flash_ok, member_or_404, render_in_shell, require
from .clients import visible_domain


def _group_or_404(me, gid):
    g = request.env['ts.panel.group'].sudo().search(
        [('id', '=', int(gid)), ('workspace_id', '=', me.workspace_id.id)])
    if not g:
        raise request.not_found()
    return g


class TsPanelGroups(http.Controller):

    @http.route('/my/workspaces/<int:ws_id>/groups', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def groups(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'groups:manage', 'groups')
        if denied:
            return denied
        gs = request.env['ts.panel.group'].sudo().search([('workspace_id', '=', ws_id), ('active', '=', True)])
        return render_in_shell('ts_panel.groups', me, 'groups', 'گروه‌ها', groups=gs, kinds=KINDS,
                               kind_label=dict(KINDS))

    @http.route('/my/workspaces/<int:ws_id>/groups/new', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def group_new(self, ws_id, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'groups:manage', 'groups')
        if denied:
            return denied
        back = '/my/workspaces/%s/groups' % ws_id
        name = (post.get('name') or '').strip()
        kind = post.get('kind') if post.get('kind') in dict(KINDS) else 'class'
        G = request.env['ts.panel.group'].sudo()
        if G.search_count([('workspace_id', '=', ws_id), ('active', '=', True), ('name_norm', '=', norm_text(name))]):
            flash_error('گروهی با این نام از پیش هست.')
            return request.redirect(back)
        try:
            g = G.create({'workspace_id': ws_id, 'name': name, 'kind': kind})
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back)
        flash_ok('گروه ساخته شد.')
        return request.redirect('%s/%s' % (back, g.id))

    @http.route('/my/workspaces/<int:ws_id>/groups/<int:gid>', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def group(self, ws_id, gid, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'groups:manage', 'groups')
        if denied:
            return denied
        g = _group_or_404(me, gid)
        C = request.env['ts.panel.client'].sudo()
        people = C.search(visible_domain(me) + [('id', 'in', g.client_ids.ids)], order='name_norm, id')
        return render_in_shell('ts_panel.group', me, 'groups', g.name, g=g, people=people, can_campaign=me.has_perm('invites:bulk') and me.can_act(),
                               kind_label=dict(KINDS), hidden=len(g.client_ids) - len(people))

    @http.route('/my/workspaces/<int:ws_id>/groups/<int:gid>/<string:action>', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def group_action(self, ws_id, gid, action, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'groups:manage', 'groups')
        if denied:
            return denied
        g = _group_or_404(me, gid)
        back = '/my/workspaces/%s/groups/%s' % (ws_id, gid)
        try:
            if action == 'rename':
                name = (post.get('name') or '').strip()
                if request.env['ts.panel.group'].sudo().search_count(
                        [('workspace_id', '=', ws_id), ('active', '=', True), ('id', '!=', g.id),
                         ('name_norm', '=', norm_text(name))]):
                    flash_error('گروهی با این نام از پیش هست.')
                else:
                    g.write({'name': name})
                    flash_ok('نام گروه ذخیره شد.')
            elif action == 'archive':
                g.write({'active': False})
                flash_ok('گروه بایگانی شد؛ ردیف‌ها دست‌نخورده ماندند.')
                return request.redirect('/my/workspaces/%s/groups' % ws_id)
            elif action == 'remove':
                cid = post.get('client') or ''
                c = request.env['ts.panel.client'].sudo().search(
                    visible_domain(me) + [('workspace_id', '=', ws_id), ('id', '=', int(cid) if cid.isdigit() else 0)])
                if not c:
                    raise request.not_found()
                g.write({'client_ids': [(3, c.id)]})
                flash_ok('از گروه برداشته شد.')
            else:
                raise request.not_found()
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        return request.redirect(back)
