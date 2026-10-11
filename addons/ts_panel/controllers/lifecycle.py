"""Ownership transfer and closing a panel (S18, ORG-7, ORG-8). Owner only, after re-authentication.

UX audit 2026-10-11 (G4 P11, P12, PT2): the choices made before the re-authentication are kept (`pending`) and given back
to the form with a status line, so the owner only presses the button again; nothing happens without that second press.
"""
from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from ..models.text import people_word
from ..perm_labels import PICK_ORDER, ROLE_BLURBS
from .base import ROLE_LABELS, flash_error, flash_ok, member_or_404, need_reauth, reauth_fresh, render_in_shell, require


def _pending(ws_id, kind):
    """The form values kept across the re-authentication, only when it really happened just now."""
    p = request.session.get('ts_pv2_pending') or {}
    if p.get('ws') != ws_id or p.get('kind') != kind:
        return {}
    request.session.pop('ts_pv2_pending', None)
    return p if reauth_fresh() else {}


class TsPanelLifecycle(http.Controller):

    def _owner(self, ws_id, perm):
        me = member_or_404(ws_id)
        return me, require(me, perm, 'settings')

    @http.route('/my/workspaces/<int:ws_id>/settings/transfer', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def transfer_page(self, ws_id, **kw):
        me, denied = self._owner(ws_id, 'panel:transfer')
        if denied:
            return denied
        ws = me.workspace_id
        others = request.env['ts.workspace.member'].sudo().search([
            ('workspace_id', '=', ws.id), ('active', '=', True), ('id', '!=', me.id), ('role', '!=', 'owner')])
        others = others.sorted(lambda o: (o.user_id.name or '').lower())
        pend = _pending(ws_id, 'transfer')
        # What the current owner may keep: the real role names and what each one means (no preselection: the owner chooses).
        from odoo.addons.ts_core.models.workspace import ROLES_BY_PURPOSE
        stay_opts = [{'key': 'owner', 'label': 'مالک پنل (هر دو نفر مالک می‌مانید)', 'blurb': ROLE_BLURBS['owner']}]
        if 'admin' in ROLES_BY_PURPOSE.get(ws.purpose, set()):
            stay_opts.insert(0, {'key': 'admin', 'label': ROLE_LABELS.get('admin', 'admin'),
                                 'blurb': 'دیگر هیچ نتیجه‌ای نمی‌بینید و اعضا را اداره نمی‌کنید؛ کارهای اجرایی و وضعیت دعوت‌ها می‌ماند.'})
        return render_in_shell('ts_panel.transfer', me, 'settings', 'انتقال مالکیت', others=others, role_labels=ROLE_LABELS,
                               stay_opts=stay_opts, chosen_owner=str(pend.get('new_owner') or ''), chosen_stay=pend.get('stay') or '',
                               resumed=bool(pend), pick_order=PICK_ORDER)

    @http.route('/my/workspaces/<int:ws_id>/settings/transfer', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def transfer(self, ws_id, **post):
        me, denied = self._owner(ws_id, 'panel:transfer')
        if denied:
            return denied
        back = '/my/workspaces/%s/settings/transfer' % ws_id
        mid = post.get('new_owner') or ''
        redo = need_reauth('انتقال مالکیت پنل «%s»' % me.workspace_id.name, back,
                           {'ws': ws_id, 'kind': 'transfer', 'new_owner': mid[:12] if mid.isdigit() else '',
                            'stay': post.get('stay') if post.get('stay') in ('owner', 'admin') else ''})
        if redo:
            return redo
        target = request.env['ts.workspace.member'].sudo().search([
            ('id', '=', int(mid) if mid.isdigit() else 0), ('workspace_id', '=', me.workspace_id.id)])
        try:
            me.workspace_id.sudo().ts_transfer(me, target, stay=post.get('stay') or 'admin')
        except UserError as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back)
        flash_ok('مالکیت پنل به «%s» منتقل شد. هر دو نفر خبردار شدند و این کار در دفتر ممیزی ثبت شد.' % target.user_id.name)
        return request.redirect('/my/workspaces/%s/settings' % ws_id)

    @http.route('/my/workspaces/<int:ws_id>/settings/close', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def close_page(self, ws_id, **kw):
        me, denied = self._owner(ws_id, 'panel:close')
        if denied:
            return denied
        pend = _pending(ws_id, 'close')
        return render_in_shell('ts_panel.close_panel', me, 'settings', 'بستن پنل', resumed=bool(pend),
                               confirmed=pend.get('confirm') == '1', people=people_word(me.workspace_id.purpose),
                               can_export=me.has_perm('clients:export'))

    @http.route('/my/workspaces/<int:ws_id>/settings/close', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def close(self, ws_id, **post):
        me, denied = self._owner(ws_id, 'panel:close')
        if denied:
            return denied
        back = '/my/workspaces/%s/settings/close' % ws_id
        if post.get('confirm') != '1':
            flash_error('برای بستن پنل، جملهٔ تأیید را علامت بزنید.')
            return request.redirect(back)
        redo = need_reauth('بستن پنل «%s»' % me.workspace_id.name, back, {'ws': ws_id, 'kind': 'close', 'confirm': '1'})
        if redo:
            return redo
        try:
            me.workspace_id.sudo().ts_close(me)
        except UserError as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back)
        flash_ok('پنل بسته شد. تا ۹۰ روز می‌توانید از فهرست %s خروجی بگیرید.' % people_word(me.workspace_id.purpose))
        return request.redirect('/my/workspaces/%s' % ws_id)
