"""Panel audit page and its export (S14, AUD-3, EXP-4). Owner only (`audit:read`, `audit:export`); only the events of the
panel in the URL; the export asks for a fresh re-authentication and is itself an audit event."""
from datetime import datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from odoo import http
from odoo.http import request

from ..models.audit_view import EXPORT_MAX, OTHER, PAGE, clean_filters, families_for
from ..models.exporter import date_cols, to_csv
from .base import member_or_404, need_reauth, render_in_shell, require

EXPORT_HEADERS = ['تاریخ (شمسی)', 'تاریخ (میلادی)', 'خانواده', 'رویداد', 'شرح', 'کاربر', 'نقش', 'نتیجه', 'جزئیات (پاک‌سازی‌شده)']
# Period presets of the filter (UX audit G4 P9-2): days back from today, Tehran time.
PERIODS = [('1', 'امروز'), ('7', '۷ روز اخیر'), ('30', '۳۰ روز اخیر'), ('', 'همه')]

try:
    from odoo.addons.ts_website.tools import parse_jdate
except ImportError:                                   # the shared component ships with ts_website; ISO still works without it
    def parse_jdate(value_iso, value_jalali):
        from ..models.audit_view import parse_day
        return parse_day(value_iso)


def _dates(kw):
    """The Solar Hijri fields (ts_website.jdate: hidden ISO + visible «۱۴۰۵/۰۷/۱۹») or a period preset -> ISO from/to."""
    out = dict(kw)
    period = kw.get('period') if kw.get('period') in ('1', '7', '30') else ''
    if period:
        today = datetime.now(ZoneInfo('Asia/Tehran')).date()
        out['from'] = (today - timedelta(days=int(period) - 1)).isoformat()
        out['to'] = today.isoformat()
        return out, period
    for key in ('from', 'to'):
        if key in kw or (key + '_jalali') in kw:
            d = parse_jdate(kw.get(key), kw.get(key + '_jalali'))
            out[key] = d.isoformat() if d else ''
    return out, ''


class TsPanelAudit(http.Controller):

    def _filters(self, me, kw):
        members = request.env['ts.workspace.member'].sudo().search([('workspace_id', '=', me.workspace_id.id)])
        kw2, period = _dates(kw)
        f = clean_filters(kw2, members)
        if period:
            f.pop('from', None)
            f.pop('to', None)
            f['period'] = period
        return f, members

    @staticmethod
    def _domain_filters(f):
        """The filters as the audit model reads them (a period becomes its dates again)."""
        if not f.get('period'):
            return f
        kw2, _p = _dates({'period': f['period']})
        g = {k: v for k, v in f.items() if k != 'period'}
        g.update({'from': kw2['from'], 'to': kw2['to']})
        return g

    @http.route('/my/workspaces/<int:ws_id>/audit', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def page(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'audit:read', 'audit')
        if denied:
            return denied
        f, members = self._filters(me, kw)
        page = int(kw['page']) if (kw.get('page') or '').isdigit() else 0
        View = request.env['ts.audit.view']
        rows, total = View.rows(me.workspace_id, self._domain_filters(f), page=page)
        rows = View.collapse(rows)
        days = []
        for r in rows:                              # grouped under a date heading (UX audit G4 P9-5)
            if not days or days[-1]['day'] != r['day']:
                days.append({'day': r['day'], 'rows': []})
            days[-1]['rows'].append(r)
        qs = urlencode(f)
        return render_in_shell(
            'ts_panel.audit', me, 'audit', 'دفتر ممیزی', rows=rows, days=days, total=total, f=f, members=members,
            families=families_for(me.workspace_id.purpose) + [OTHER], periods=PERIODS, filtered=bool(f),
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
        redo = need_reauth('خروجی گرفتن از دفتر ممیزی پنل «%s»' % me.workspace_id.name, back)
        if redo:
            return redo
        rows, total = request.env['ts.audit.view'].rows(me.workspace_id, self._domain_filters(f), page=0, limit=EXPORT_MAX)
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
