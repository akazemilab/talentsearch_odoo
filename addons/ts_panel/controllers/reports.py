"""Results and reports (S13, REP-1 .. REP-5, G29; 05_permissions_matrix.md section 5).

One result page per attempt: `W/clients/<cid>/r/<attempt_id>`. What it shows follows `ts_result_level`: none -> 404 and a deny
event, status -> a short page without any score, summary and education -> bands per factor (TALENT-INV-15 at education: the
profile report without raw answers), clinical -> scores and therapist texts. Opening and printing are audited. The group report
counts people with small-cell suppression (see models/group_report.py).
"""
from odoo import http
from odoo.http import request

from odoo.addons.ts_talent.controllers.main import TsTalentOrg, report_ctx
from odoo.addons.ts_talent.models import engine_matrix as EM

from .base import RESULT_PERMS, deny, forbidden, member_or_404, render_in_shell, require
from .clients import _client_or_404, visible_domain

LEVEL_KIND = {'status': 'وضعیت', 'summary': 'خلاصهٔ نتیجه', 'education': 'نتیجهٔ آموزشی', 'clinical': 'گزارش بالینی'}


def result_url(ws_id, client_id, attempt_id):
    return '/my/workspaces/%s/clients/%s/r/%s' % (ws_id, client_id, attempt_id)


class TsPanelReports(http.Controller):

    # ------------------------------------------------------------------ one result
    def _result_context(self, ws_id, cid, aid):
        me = member_or_404(ws_id)
        client = _client_or_404(me, cid)
        at = request.env['ts.attempt'].sudo().search(
            [('id', '=', int(aid)), ('workspace_id', '=', me.workspace_id.id), ('client_id', '=', client.id)])
        if not at or not me.can_see(client):
            deny(me, 'no_result', attempt=int(aid))
            raise request.not_found()
        level = at.ts_result_level(me)
        if level == 'none':
            deny(me, 'result_level_none', attempt=at.id)
            raise request.not_found()
        return me, client, at, level

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/r/<int:aid>', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def result(self, ws_id, cid, aid, print=None, **kw):
        me, client, at, level = self._result_context(ws_id, cid, aid)
        url = result_url(me.workspace_id.id, client.id, at.id)
        back = '/my/workspaces/%s/clients/%s' % (me.workspace_id.id, client.id)
        request.env['ts.audit.event'].sudo().log('result.view', at, workspace=me.workspace_id, member=me, level=level)
        if level == 'education' and at.ts_is_matrix():
            ctx = report_ctx(at, org_view=True, ws=me.workspace_id)
            ctx.update(back_url=back, print_url=url + '/print', autoprint=bool(print))
            return request.render('ts_talent.report', ctx)
        results = at.result_rows() if level != 'status' else request.env['ts.attempt.result']
        return render_in_shell(
            'ts_panel.result_bands', me, 'clients', 'نتیجه', client=client, attempt=at, inst=at.instrument_id, level=level,
            results=results, kind=LEVEL_KIND[level], back_url=back, print_url=url + '/print', autoprint=bool(print),
            when=at.submitted_at)

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/r/<int:aid>/print', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def result_print(self, ws_id, cid, aid, **kw):
        me, client, at, level = self._result_context(ws_id, cid, aid)
        request.env['ts.audit.event'].sudo().log('result.print', at, workspace=me.workspace_id, member=me, level=level)
        return request.redirect(result_url(me.workspace_id.id, client.id, at.id) + '?print=1')

    # ------------------------------------------------------------------ entry page
    @http.route('/my/workspaces/<int:ws_id>/reports', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def entry(self, ws_id, **kw):
        me = member_or_404(ws_id)
        if not any(me.has_perm(p) for p in RESULT_PERMS):
            return forbidden(me, 'results', 'reports')
        T = request.env['ts.attempt'].sudo()
        clients = request.env['ts.panel.client'].sudo().search(visible_domain(me) + [('state', '=', 'active')])
        rows = []
        for at in T.search([('workspace_id', '=', me.workspace_id.id), ('client_id', 'in', clients.ids), ('state', '=', 'done'),
                            ('voided', '=', False)], order='submitted_at desc, id desc', limit=80):
            level = at.ts_result_level(me)
            if level in ('summary', 'education', 'clinical'):
                rows.append((at, level))
            if len(rows) >= 20:
                break
        return render_in_shell('ts_panel.reports', me, 'reports', 'گزارش‌ها', rows=rows, kinds=LEVEL_KIND,
                               can_group=me.has_perm('reports:group'), url=result_url)

    # ------------------------------------------------------------------ group report
    @http.route('/my/workspaces/<int:ws_id>/reports/group', type='http', auth='user', website=True, methods=['GET'],
                sitemap=False)
    def group(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'reports:group', 'reports')
        if denied:
            return denied
        params = {k: kw[k] for k in ('group_id', 'campaign_id', 'instrument_id', 'period') if str(kw.get(k) or '').isdigit()}
        rep = request.env['ts.group.report'].build(me, params)
        request.env['ts.audit.event'].sudo().log('report.group_view', me.workspace_id, workspace=me.workspace_id, member=me)
        ws = me.workspace_id
        groups = request.env['ts.panel.group'].sudo().search([('workspace_id', '=', ws.id)])
        camps = request.env['ts.campaign'].sudo().search([('workspace_id', '=', ws.id)])
        return render_in_shell(
            'ts_panel.group_report', me, 'reports', 'گزارش گروهی', rep=rep, params=params, groups=groups, campaigns=camps,
            instruments=me.allowed_instruments(), names=EM.NAMES,
            periods=((0, 'همهٔ زمان‌ها'), (30, '۳۰ روز گذشته'), (90, '۹۰ روز گذشته'), (365, 'یک سال گذشته')))


class TsPanelTalentOrg(TsTalentOrg):
    """The old institute route W/p/<attempt> lands on the new result page of the same participant (S13)."""

    @http.route()
    def org_person(self, ws_id, attempt_id, **kw):
        me = member_or_404(ws_id)
        at = request.env['ts.attempt'].sudo().search([('id', '=', int(attempt_id)), ('workspace_id', '=', me.workspace_id.id)])
        if at and at.client_id:
            return request.redirect(result_url(me.workspace_id.id, at.client_id.id, at.id))
        return super().org_person(ws_id, attempt_id, **kw)
