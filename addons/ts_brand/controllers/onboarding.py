"""What stays of the clinic phase 6 set-up guide after onb3 (models/onboarding.py): «بدون سقف بماند» (credits:manage, like the
cap editor of ts_billing) and the counselor's first-run card. Website 4 only (member_or_404 and the help route answer 404
elsewhere). No access rule changes."""
from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_panel.controllers.base import flash_error, flash_ok, forbidden, member_or_404
from odoo.addons.ts_panel.controllers.help_center import TsPanelHelp

HELP_CHECKED = '۲۱ مهر ۱۴۰۵'      # the help page date (onb3: «شروع کار» per kind and «استخدام» were added)


class TsBrandOnboarding(http.Controller):

    def _home(self, ws_id, anchor=''):
        return request.redirect('/my/workspaces/%s%s' % (ws_id, anchor))

    @http.route('/my/workspaces/<int:ws_id>/onboarding/nocap', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def onboarding_nocap(self, ws_id, **post):
        me = member_or_404(ws_id)
        if not me.has_perm('credits:manage') or not me.can_act():
            return forbidden(me, 'credits:manage', 'home')
        try:
            me.workspace_id.ts_onb_mark_nocap(me)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('ثبت شد: مشاوران بدون سقف ماهانه کار می‌کنند. هر وقت بخواهید، در «اعتبار و مصرف» سقف بگذارید.')
        return self._home(ws_id, '#tso-more')

    @http.route('/my/workspaces/<int:ws_id>/onboarding/card-hide', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def onboarding_card_hide(self, ws_id, **post):
        me = member_or_404(ws_id)
        if me.ts_onb_card():
            me.ts_onb_card_hide(me)
        return self._home(ws_id)


class TsBrandHelp(TsPanelHelp):

    @http.route()
    def panel_help(self, **kw):
        """+ the date and, for a member of exactly one running counseling-center panel, links into that panel."""
        res = super().panel_help(**kw)
        qc = getattr(res, 'qcontext', None)
        if qc is None:
            return res
        qc['checked'] = HELP_CHECKED
        ws_one = None
        public = request.env.user._is_public()
        if not public:
            mine = request.env['ts.workspace.member'].sudo().search(  # the caller's own memberships, found by user
                [('user_id', '=', request.env.user.id), ('active', '=', True)])
            centers = mine.filtered(lambda m: m.workspace_id.purpose == 'clinical' and m.workspace_id.state == 'active')
            if len(centers.workspace_id) == 1:
                ws_one = centers.workspace_id      # place names in #center-setup become links into this panel
        qc['tsob_ws'] = ws_one
        qc['tsob_public'] = public
        return res
