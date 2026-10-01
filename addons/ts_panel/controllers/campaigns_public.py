"""The open link of a campaign, participant side (S7, INV-6): /c/<token>.
A signed-in participant types a name and joins; the invitation that results is the ordinary one, so the consent and
sharing steps of /invite/<token> follow. Joining is capped by the campaign (open_max, expiry, closed) and by an IP-hash
rate limit; the page tells nothing about the panel except its name, the instrument and the note."""
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_org.controllers.main import TsOrg

from ..models.campaign import JOIN_MSG


class TsPanelCampaignJoin(TsOrg):

    def _campaign(self, token):
        _ts_site_or_404()
        c = request.env['ts.campaign'].sudo().search([('open_token', '=', token), ('kind', '=', 'open_link')], limit=1)   # ts-scope-ok: the secret token is the key of a public link
        if not c or c.workspace_id.state not in ('pilot', 'active'):
            raise request.not_found()
        return c

    @http.route('/c/<string:token>', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def campaign_page(self, token, **kw):
        c = self._campaign(token)
        user = request.env.user
        st = c.open_state()
        mine = None
        if not user._is_public():
            mine = request.env['ts.assignment'].sudo().search(  # ts-scope-ok: campaign_id is scoped to the campaign workspace
                [('campaign_id', '=', c.id), ('client_id.user_id', '=', user.id)], limit=1)   # ts-scope-ok: campaign_id is the panel's own
        return request.render('ts_panel.campaign_join', {
            'c': c, 'ws': c.workspace_id, 'inst': c.instrument_id, 'public': user._is_public(), 'fa': fa_digits,
            'flash': request.session.pop('ts_flash', None), 'state': st, 'msg': JOIN_MSG.get(st), 'mine': mine, 'user_name': (user.name or '') if not user._is_public() else '',
            **self._auth_urls('/c/%s' % token)})

    @http.route('/c/<string:token>/join', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def campaign_join(self, token, **post):
        c = self._campaign(token)
        Audit = request.env['ts.audit.event'].sudo()
        ip = Audit._hash_ip(request.httprequest.remote_addr)
        limit = request.env['ir.config_parameter'].sudo().get_int('ts_panel.join_per_hour_ip', 30) or 30
        since = fields.Datetime.now() - timedelta(hours=1)
        tries = Audit.search_count([('event_type', '=', 'campaign.join_try'), ('ip_hash', '=', ip), ('create_date', '>=', since)])
        if tries >= limit:
            request.session['ts_flash'] = 'تلاش‌های پیاپی بود. یک ساعت دیگر دوباره امتحان کنید.'
            return request.redirect('/c/%s' % token)
        Audit.log('campaign.join_try', c, workspace=c.workspace_id)
        try:
            a = c.ts_join(request.env.user, post.get('name'))
        except UserError as e:
            request.session['ts_flash'] = str(e.args[0] if e.args else e)
            return request.redirect('/c/%s' % token)
        Audit.log('campaign.join', a, workspace=c.workspace_id, campaign_id=c.id)
        return request.redirect('/invite/%s' % a.token)
