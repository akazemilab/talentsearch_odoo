import logging

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

HOMEPAGE_ARCH = '<t name="Homepage" t-name="website.homepage"><t t-call="ts_website.home"/></t>'

# (label, url, sequence). Rebuilt on every upgrade; website 2 only.
TS_MENU = [
    ('سنجه‌ها', '/assessments', 5),
    ('برای سازمان‌ها', '/employers', 10),
    ('برای مراکز بالینی', '/clinics', 20),
    ('روند کار', '/how-it-works', 30),
    ('شواهد و محدودیت‌ها', '/evidence', 40),
    ('درباره ما', '/about', 50),
    ('تماس', '/contact', 60),
]
class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _ts_site(self):
        return self.env.ref('ts_website.website_ts', raise_if_not_found=False)

    def _ts_is_current(self):
        site = self._ts_site()
        return bool(site) and self.id == site.id

    @api.model
    def _ts_setup_site(self):
        site = self._ts_site()
        if not site:
            raise UserError('Talent Search website record is missing.')
        if site.id == 1:
            raise UserError('Refusing to configure website 1 as Talent Search.')
        self._ts_setup_homepage(site)
        self._ts_setup_menu(site)
        if site.auth_signup_uninvited != 'b2c':
            site.auth_signup_uninvited = 'b2c'  # website-2 setting: visitors may create an account
        self._ts_isolate_crm_stages()
        self._ts_contain_stock_apps(site)
        _logger.info('Talent Search site %s configured (website id %s)', site.name, site.id)

    def _ts_setup_homepage(self, site):
        View = self.env['ir.ui.view'].with_context(active_test=False)
        home = View.search([('key', '=', 'website.homepage'), ('website_id', '=', site.id)], limit=1)
        if not home:
            std = self.env.ref('website.homepage')
            std.with_context(website_id=site.id).arch_db = HOMEPAGE_ARCH
            home = View.search([('key', '=', 'website.homepage'), ('website_id', '=', site.id)], limit=1)
        if not home or home.website_id != site:
            raise UserError('Could not find the website-2 homepage view.')
        if 'ts_website.home' not in (home.arch_db or ''):
            home.arch_db = HOMEPAGE_ARCH
        page = self.env['website.page'].search([('website_id', '=', site.id), ('url', '=', '/')], limit=1)
        if page:
            page.write({'view_id': home.id, 'website_indexed': True, 'website_published': True})

    def _ts_setup_menu(self, site):
        Menu = self.env['website.menu']
        # website.menu_id is computed and may be stale right after website
        # creation in the same transaction: look the top menu up directly.
        top = Menu.search([('website_id', '=', site.id), ('parent_id', '=', False)], limit=1)
        if not top:
            site.copy_menu_hierarchy(self.env.ref('website.main_menu'))
            top = Menu.search([('website_id', '=', site.id), ('parent_id', '=', False)], limit=1)
        if not top:
            raise UserError('Website 2 has no own top menu.')
        Menu.search([('parent_id', '=', top.id), ('website_id', '=', site.id)]).unlink()
        Menu.create([{'name': n, 'url': u, 'sequence': s, 'parent_id': top.id, 'website_id': site.id}
                     for n, u, s in TS_MENU])

    # Stock apps installed for Talent Search that publish website content on
    # the company's default website (website 1 = eot.ir) or on every website.
    STOCK_APP_PAGE_MODULES = ('website_helpdesk', 'website_crm', 'survey', 'website_payment', 'helpdesk')
    STOCK_APP_PORTAL_MODULES = ('account', 'payment', 'account_payment', 'helpdesk', 'website_helpdesk', 'sale', 'survey')

    def _ts_contain_stock_apps(self, site):
        """Move what stock app installs put on eot.ir onto website 2.

        Found by ts_guard on the rehearsal clone: website_helpdesk publishes its
        demo team 'Customer Care' on website 1 (adds a 'Help' menu to every
        eot.ir page) and ships a generic page /your-ticket-has-been-submitted.
        Only records created by those apps are touched, never eot.ir's own."""
        if 'helpdesk.team' in self.env:
            teams = self.env['helpdesk.team'].with_context(active_test=False).search([('website_id', '!=', site.id)])
            if teams:
                teams.filtered('is_published').write({'is_published': False})
                stray_menus = teams.mapped('website_menu_id').filtered(lambda m: m.website_id != site)
                teams.write({'website_id': site.id, 'website_menu_id': False})
                stray_menus.unlink()
            # Menus left behind by an earlier publish (e.g. 'Help' -> /helpdesk).
            self.env['website.menu'].search([('website_id', '!=', site.id), ('url', '=like', '/helpdesk%')]).unlink()
        # website_crm (and friends) create website-specific copies of their
        # views for every website that has its own copy of the parent. eot.ir
        # had none of these modules before, so every such website-1 copy is
        # install-generated; website_crm.contactus_form's copy breaks eot.ir's
        # redesigned /contactus (its xpath target no longer exists) -> 500.
        stray_views = self.env['ir.ui.view'].with_context(active_test=False).search([
            ('website_id', '!=', False), ('website_id', '!=', site.id), ('active', '=', True),
            '|', '|', '|', '|', ('key', '=like', 'website_crm.%'), ('key', '=like', 'website_helpdesk.%'),
            ('key', '=like', 'survey.%'), ('key', '=like', 'website_payment.%'), ('key', '=like', 'helpdesk.%')])
        # Portal home cards of those apps: Talent Search only (not eot.ir).
        entry_ids = IMD.search([('model', '=', 'portal.entry'), ('module', 'in', self.STOCK_APP_PORTAL_MODULES)]).mapped('res_id')
        entries = self.env['portal.entry'].with_context(ts_all_websites=True).browse(entry_ids).exists().filtered(lambda e: not e.website_id)
        if entries:
            entries.write({'website_id': site.id, 'show_in_portal': False})
        if stray_views:
            _logger.info('Talent Search: deactivating install-generated views on other websites: %s', stray_views.mapped('key'))
            stray_views.write({'active': False})
        IMD = self.env['ir.model.data']
        page_ids = IMD.search([('model', '=', 'website.page'), ('module', 'in', self.STOCK_APP_PAGE_MODULES)]).mapped('res_id')
        pages = self.env['website.page'].browse(page_ids).exists().filtered(lambda p: not p.website_id)
        if pages:
            pages.write({'website_id': site.id})
        # Menus those apps created on website 1 (e.g. the helpdesk 'Help' item).
        menu_ids = IMD.search([('model', '=', 'website.menu'), ('module', 'in', self.STOCK_APP_PAGE_MODULES)]).mapped('res_id')
        menus = self.env['website.menu'].browse(menu_ids).exists().filtered(lambda m: m.website_id.id != site.id)
        if menus:
            menus.unlink()

    def _ts_isolate_crm_stages(self):
        """Stock CRM stages have no team, so they would appear in the Talent
        Search pipeline too. Bind team-less stock stages to the default sales
        team (CRM was installed for Talent Search; eot.ir does not use it)."""
        default_team = self.env.ref('sales_team.team_sales_department', raise_if_not_found=False)
        if not default_team:
            return
        stock = self.env['crm.stage'].search([('team_ids', '=', False)])
        stock = stock.filtered(lambda s: not s.get_external_id().get(s.id, '').startswith('ts_website.'))
        if stock:
            stock.write({'team_ids': [(6, 0, default_team.ids)]})


class PortalEntry(models.Model):
    """Portal home cards are not website-aware in Odoo 20. Stock apps installed
    for Talent Search (account, payment, account_payment, helpdesk) add cards
    ('Invoices to pay', 'Manage your payment methods', 'Tickets', ...) to every
    signed-in user's /my - including eot.ir's. A card with a website only
    shows on that website."""
    _inherit = 'portal.entry'

    website_id = fields.Many2one('website', index=True, ondelete='cascade',
                                 help='Empty: every website. Set: only that website.')

    @api.model
    def _search(self, domain, *args, **kwargs):
        from odoo.http import request
        website = request and getattr(request, 'env', None) and request.env.website
        if website and not self.env.context.get('ts_all_websites'):
            domain = Domain(domain) & (Domain('website_id', '=', False) | Domain('website_id', '=', website.id))
        return super()._search(domain, *args, **kwargs)
