"""Clinic phase 6: the set-up guide of a counseling-center panel (models/onboarding.py). Website 4 only (member_or_404 and the
help route answer 404 elsewhere). Every POST acts on the caller's own membership, except «بدون سقف بماند», which needs
credits:manage exactly like the cap editor of ts_billing. No access rule changes."""
from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_panel.controllers.base import flash_error, flash_ok, forbidden, member_or_404
from odoo.addons.ts_panel.controllers.help_center import TsPanelHelp

HELP_CHECKED = '۲۰ مهر ۱۴۰۵'      # the help page date once the section «راهنمای راه‌اندازی مرکز مشاوره» was added


class TsBrandOnboarding(http.Controller):

    def _home(self, ws_id, anchor=''):
        return request.redirect('/my/workspaces/%s%s' % (ws_id, anchor))

    @http.route('/my/workspaces/<int:ws_id>/onboarding/hide', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def onboarding_hide(self, ws_id, **post):
        me = member_or_404(ws_id)
        if me.ts_onb_applies(ignore_hidden=True):
            me.ts_onb_set_hidden(me, True)
            flash_ok('فهرست راه‌اندازی پنهان شد. از «راهنمای پنل»، بخش راه‌اندازی مرکز مشاوره، دوباره نمایانش کنید.')
        return self._home(ws_id)

    @http.route('/my/workspaces/<int:ws_id>/onboarding/show', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def onboarding_show(self, ws_id, **post):
        me = member_or_404(ws_id)
        if me.ts_onb_applies(ignore_hidden=True):
            me.ts_onb_set_hidden(me, False)
            flash_ok('فهرست راه‌اندازی دوباره در «پیشخوان» دیده می‌شود.')
        return self._home(ws_id, '#tsob')

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
        return self._home(ws_id, '#tsob')

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
        """+ the caller's counseling-center panels whose set-up checklist they hid (the «نمایش دوباره» buttons)."""
        res = super().panel_help(**kw)
        qc = getattr(res, 'qcontext', None)
        if qc is None:
            return res
        qc['checked'] = HELP_CHECKED
        hidden, ws_one = [], None
        public = request.env.user._is_public()
        if not public:
            mine = request.env['ts.workspace.member'].sudo().search(  # the caller's own memberships, found by user
                [('user_id', '=', request.env.user.id), ('active', '=', True)])
            hidden = [m for m in mine if m.ts_onb_hidden_on and m.ts_onb_applies(ignore_hidden=True)]
            centers = mine.filtered(lambda m: m.workspace_id.purpose == 'clinical' and m.workspace_id.state == 'active')
            if len(centers.workspace_id) == 1:
                ws_one = centers.workspace_id      # place names in #center-setup become links into this panel
        qc['tsob_hidden'] = hidden
        qc['tsob_ws'] = ws_one
        qc['tsob_public'] = public
        return res
