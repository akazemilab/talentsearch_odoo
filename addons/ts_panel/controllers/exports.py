"""Exports (S9, EXP-1..EXP-3): one page with the three exports, one POST that starts a job. Every export needs a fresh
re-authentication (A7) at the moment it is requested and again when the file is downloaded; the file is private to the
requester and lives 24 hours (see imports.py for the job page and the download route).
"""
from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from ..models.job import KIND_PERM
from .base import flash_error, forbidden, member_or_404, need_reauth, render_in_shell, require

KINDS = {'clients': 'export_clients', 'status': 'export_status', 'results': 'export_results'}


class TsPanelExports(http.Controller):

    def _guard(self, ws_id):
        me = member_or_404(ws_id)
        denied = require(me, 'clients:export', 'exports')
        if denied:
            return me, denied
        if not me.can_act():
            return me, forbidden(me, 'clients:export', 'exports')
        return me, None

    @http.route('/my/workspaces/<int:ws_id>/exports', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def page(self, ws_id, **kw):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        ws = me.workspace_id
        env = request.env
        jobs = env['ts.job'].sudo().search([('workspace_id', '=', ws.id), ('member_id', '=', me.id),
                                             ('kind', 'in', list(KINDS.values()))], limit=8)
        can_results = me.has_perm('results:export') and ws.purpose in ('education', 'employment')
        return render_in_shell(
            'ts_panel.exports', me, 'exports', 'خروجی‌ها', jobs=jobs, can_results=can_results,
            groups=env['ts.panel.group'].sudo().search([('workspace_id', '=', ws.id), ('active', '=', True)]),
            instruments=me.allowed_instruments(), ttl=env['ts.job']._ttl_hours())

    @http.route('/my/workspaces/<int:ws_id>/exports/create', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def create(self, ws_id, **post):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        kind = KINDS.get(post.get('what'))
        back = '/my/workspaces/%s/exports' % ws_id
        if not kind or not me.has_perm(KIND_PERM[kind]):
            return forbidden(me, KIND_PERM.get(kind, 'clients:export'), 'exports')
        redo = need_reauth('خروجی گرفتن از اطلاعات', back)
        if redo:
            return redo
        try:
            job = request.env['ts.job'].ts_export_create(me, kind, post.get('format'), {
                'group_id': post.get('group_id') if (post.get('group_id') or '').isdigit() else '',
                'instrument_id': post.get('instrument_id') if (post.get('instrument_id') or '').isdigit() else '',
                'state': post.get('state') if post.get('state') in ('active', 'archived', 'all') else ''})
        except UserError as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back)
        return request.redirect('/my/workspaces/%s/jobs/%s' % (ws_id, job.id))
