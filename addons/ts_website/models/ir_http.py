from odoo import models
from odoo.fields import Domain
from odoo.http import request
from odoo.addons.http_routing.models import ir_http


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def _generate_routing_rules(self, modules, converters):
        """Website 2 gets no routes from theme_* modules.

        Theme controllers are not website-scoped: theme_eot_custom's retired-URL
        redirects (/privacy, /courses, /your-ticket-has-been-submitted, ...)
        would otherwise send Talent Search visitors to eot.ir paths. Odoo keeps
        one routing map per website, so eot.ir's map is built exactly as before."""
        website = self.env.website
        if website and website._ts_is_current():
            modules = [m for m in modules if not m.startswith('theme_')]
        return super()._generate_routing_rules(modules, converters)

    @classmethod
    def _serve_redirect(cls):
        """On the Talent Search website, honour only its own redirects.

        eot_main holds global (website_id NULL) 301s created for eot.ir course
        short links; without this they would fire on website 2 too. Behaviour
        on every other website is exactly Odoo's (super)."""
        website = request.env.website
        if not (website and website._ts_is_current()):
            return super()._serve_redirect()
        req_page = request.httprequest.path
        req_page_noslug = ir_http._UNSLUG_RE.sub(r'\2', req_page)
        req_page_with_qs = request.httprequest.environ['REQUEST_URI']
        domain = (
            Domain('redirect_type', 'in', ('301', '302'))
            & Domain('url_from', 'in', [req_page_with_qs, req_page.rstrip('/'), req_page + '/', req_page_noslug])
            & Domain('website_id', '=', website.id)
        )
        return request.env['website.rewrite'].sudo().search(domain, order='url_from DESC', limit=1)
