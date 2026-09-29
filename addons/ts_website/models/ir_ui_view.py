import logging

from odoo import models

_logger = logging.getLogger(__name__)


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    def _create_all_specific_views(self, processed_modules):
        """Odoo copies newly installed inheriting views onto every website that
        has its own copy of the parent - at the END of module loading, after
        all data files (so ts_website's own setup runs too early to see them).
        Re-run Talent Search containment right after, on every install/upgrade
        of any module, so stock apps never alter eot.ir (e.g. website_crm's
        contactus_form copy that breaks eot.ir's /contactus)."""
        res = super()._create_all_specific_views(processed_modules)
        site = self.env.ref('ts_website.website_ts', raise_if_not_found=False)
        if site:
            self.env['website']._ts_contain_stock_apps(site)
        return res
