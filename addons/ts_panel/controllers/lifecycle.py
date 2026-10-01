"""Ownership transfer and closing a panel (S18, ORG-7, ORG-8). Owner only, after re-authentication."""
from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from .base import ROLE_LABELS, flash_error, flash_ok, member_or_404, need_reauth, render_in_shell, require


class TsPanelLifecycle(http.Controller):

    def _owner(self, ws_id, perm):
        me = member_or_404(ws_id)
        return me, require(me, perm, 'settings')

    @http.route('/my/workspaces/<int:ws_id>/settings/transfer', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def transfer_page(self, ws_id, **kw):
        me, denied = self._owner(ws_id, 'panel:transfer')
        if denied:
            return denied
        others = request.env['ts.workspace.member'].sudo().search([
            ('workspace_id', '=', me.workspace_id.id), ('active', '=', True), ('id', '!=', me.id), ('role', '!=', 'owner')])
        return render_in_shell('ts_panel.transfer', me, 'settings', 'انتقال مالکیت', others=others, role_labels=ROLE_LABELS)

    @http.route('/my/workspaces/<int:ws_id>/settings/transfer', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def transfer(self, ws_id, **post):
        me, denied = self._owner(ws_id, 'panel:transfer')
        if denied:
            return denied
        back = '/my/workspaces/%s/settings/transfer' % ws_id
        redo = need_reauth('برای انتقال مالکیت پنل', back)
        if redo:
            return redo
        mid = post.get('new_owner') or ''
        target = request.env['ts.workspace.member'].sudo().search([
            ('id', '=', int(mid) if mid.isdigit() else 0), ('workspace_id', '=', me.workspace_id.id)])
        try:
            me.workspace_id.sudo().ts_transfer(me, target, stay=post.get('stay') or 'admin')
        except UserError as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back)
        flash_ok('مالکیت منتقل شد. هر دو نفر خبردار شدند.')
        return request.redirect('/my/workspaces/%s/settings' % ws_id)

    @http.route('/my/workspaces/<int:ws_id>/settings/close', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def close_page(self, ws_id, **kw):
        me, denied = self._owner(ws_id, 'panel:close')
        if denied:
            return denied
        return render_in_shell('ts_panel.close_panel', me, 'settings', 'بستن پنل')

    @http.route('/my/workspaces/<int:ws_id>/settings/close', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def close(self, ws_id, **post):
        me, denied = self._owner(ws_id, 'panel:close')
        if denied:
            return denied
        back = '/my/workspaces/%s/settings/close' % ws_id
        if post.get('confirm') != '1':
            flash_error('برای بستن پنل باید تأیید کنید.')
            return request.redirect(back)
        redo = need_reauth('برای بستن پنل', back)
        if redo:
            return redo
        try:
            me.workspace_id.sudo().ts_close(me)
        except UserError as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back)
        flash_ok('پنل بسته شد. تا ۹۰ روز می‌توانید فهرست مراجعان را بیرون بکشید.')
        return request.redirect('/my/workspaces/%s' % ws_id)
