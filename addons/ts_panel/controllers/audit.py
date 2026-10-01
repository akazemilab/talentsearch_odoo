"""Panel audit page and its export (S14, AUD-3, EXP-4). Owner only (`audit:read`, `audit:export`); only the events of the
panel in the URL; the export asks for a fresh re-authentication and is itself an audit event."""
from urllib.parse import urlencode

from odoo import http
from odoo.http import request

from ..models.audit_view import EXPORT_MAX, FAMILIES, OTHER, PAGE, clean_filters
from ..models.exporter import date_cols, to_csv
from .base import member_or_404, need_reauth, render_in_shell, require

EXPORT_HEADERS = ['تاریخ (شمسی)', 'تاریخ (میلادی)', 'خانواده', 'رویداد', 'شرح', 'کاربر', 'نقش', 'نتیجه', 'جزئیات (پاک‌سازی‌شده)']


class TsPanelAudit(http.Controller):

    def _filters(self, me, kw):
        members = request.env['ts.workspace.member'].sudo().search([('workspace_id', '=', me.workspace_id.id)])
        return clean_filters(kw, members), members

    @http.route('/my/workspaces/<int:ws_id>/audit', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def page(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'audit:read', 'audit')
        if denied:
            return denied
        f, members = self._filters(me, kw)
        page = int(kw['page']) if (kw.get('page') or '').isdigit() else 0
        View = request.env['ts.audit.view']
        rows, total = View.rows(me.workspace_id, f, page=page)
        qs = urlencode(f)
        return render_in_shell(
            'ts_panel.audit', me, 'audit', 'ممیزی پنل', rows=rows, total=total, f=f, members=members, families=FAMILIES + [OTHER],
            page=page, pages=max(1, -(-total // PAGE)), qs=qs, support=View.support_rows(me.workspace_id),
            can_export=me.has_perm('audit:export'), export_max=EXPORT_MAX)

    @http.route('/my/workspaces/<int:ws_id>/audit/export', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def export(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'audit:export', 'audit')
        if denied:
            return denied
        f, _members = self._filters(me, kw)
        back = '/my/workspaces/%s/audit/export?%s' % (me.workspace_id.id, urlencode(f))
        redo = need_reauth('خروجی گرفتن از ممیزی', back)
        if redo:
            return redo
        rows, total = request.env['ts.audit.view'].rows(me.workspace_id, f, page=0, limit=EXPORT_MAX)
        request.env['ts.audit.event'].sudo().log('audit.export', me.workspace_id, workspace=me.workspace_id, member=me,
                                                 rows=len(rows), filtered=bool(f))
        data = []
        for r in rows:
            j, i = date_cols(r['iso'])
            data.append([j, i, r['family'], r['type'], r['text'], r['actor'], r['role'], r['outcome'], r['detail']])
        body = to_csv(EXPORT_HEADERS, data)
        return request.make_response(body, headers=[
            ('Content-Type', 'text/csv; charset=utf-8'),
            ('Content-Disposition', 'attachment; filename="audit-%s.csv"' % me.workspace_id.code),
            ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')])
