from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class TsOrgPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'ts_workspace_count' in counters:
            website = request.env.website
            count = 0
            if website and website._ts_is_current():
                count = request.env['ts.workspace.member'].sudo().search_count([
                    ('user_id', '=', request.env.user.id), ('active', '=', True)])
            values['ts_workspace_count'] = count
        return values
