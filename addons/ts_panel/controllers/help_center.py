"""Panel help center (S19, HLP-2 .. HLP-4; 02_feature_catalog.md).

`/help/panel` is one page of short task sections with anchors. The contextual "what is this?" links on the pages point to
these anchors. Every section names the date it was checked against behaviour (G27). Open to everyone on the Talent Search
website (no personal data); the support link carries the panel number of the caller's own panel when there is one.
"""
from odoo import http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404

CHECKED = '۱۰ مهر ۱۴۰۵'          # keep in step with the text of web_help.xml, update when a section changes
SECTIONS = ('invite', 'import', 'report', 'roles', 'sharing', 'minors', 'export', 'support', 'credits')


class TsPanelHelp(http.Controller):

    @http.route('/help/panel', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def panel_help(self, **kw):
        _ts_site_or_404()
        contact = '/contact?topic=panel'
        if not request.env.user._is_public():
            member = request.env['ts.workspace.member'].sudo().search(  # ts-scope-ok: the caller's own membership, found by user
                [('user_id', '=', request.env.user.id), ('active', '=', True)], limit=1)
            if member:
                contact += '&panel=%s' % member.workspace_id.id
        return request.render('ts_panel.help_panel', {'checked': CHECKED, 'contact_url': contact,
                                                      'page_name': 'ts_panel_help'})
