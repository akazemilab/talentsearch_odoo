"""Notification center and preferences (S10, NOT-1, NOT-2, ACC-7). Every route is for the signed-in person's own rows only."""
from odoo import http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits, jalali

from ..models.notify_texts import PREF_LABELS, SMS_STAFF_TYPES, TITLES, TYPES

PARTICIPANT_TYPES = ('invite', 'reminder', 'result_ready_participant', 'data_request_update')
PAGE = 50


def _safe_internal(url):
    return url if url and url.startswith('/') and not url.startswith('//') else '/my/notifications'


class TsPanelNotifications(http.Controller):

    @http.route('/my/notifications', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def center(self, **kw):
        _ts_site_or_404()
        user = request.env.user
        N = request.env['ts.notification'].sudo()
        only_unread = kw.get('unread') == '1'
        dom = [('user_id', '=', user.id)] + ([('read_at', '=', False)] if only_unread else [])
        rows = N.search(dom, limit=PAGE)
        return request.render('ts_panel.notifications', {
            'jalali': jalali, 'fa': fa_digits, 'rows': rows, 'unread': N._unread_count(user), 'only_unread': only_unread, 'flash': request.session.pop('ts_flash', None),
            'page_name': 'ts_panel_notifications'})

    @http.route('/my/notifications/read_all', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def read_all(self, **post):
        _ts_site_or_404()
        user = request.env.user
        request.env['ts.notification'].sudo().search([('user_id', '=', user.id), ('read_at', '=', False)])._mark_read(user)  # ts-scope-ok: own rows only
        return request.redirect('/my/notifications')

    @http.route('/my/notifications/<int:nid>', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def open(self, nid, **kw):
        _ts_site_or_404()
        user = request.env.user
        row = request.env['ts.notification'].sudo().search([('id', '=', nid), ('user_id', '=', user.id)])  # ts-scope-ok: own rows only
        if not row:
            raise request.not_found()
        row._mark_read(user)
        return request.redirect(_safe_internal(row.url))

    @http.route('/my/notifications/prefs', type='http', auth='user', website=True, methods=['GET', 'POST'], sitemap=False)
    def prefs(self, **post):
        _ts_site_or_404()
        env, user = request.env, request.env.user
        N = env['ts.notification'].sudo()
        is_member = bool(env['ts.workspace.member'].sudo().search_count([('user_id', '=', user.id), ('active', '=', True)]))  # ts-scope-ok: own memberships
        shown = [t for t, _l in TYPES if t in PARTICIPANT_TYPES or is_member]
        phone = N._phone_of(user)
        company = user.company_id.sudo()
        sms_live = bool(company.kv_enabled and company.ts_sms_staff)
        if request.httprequest.method == 'POST':
            for t in shown:
                env['ts.notify.pref'].ts_save(user, t, post.get('app_' + t) == '1', bool(phone) and post.get('sms_' + t) == '1')
            request.session['ts_flash'] = 'ترجیح‌های اعلان ذخیره شد.'
            return request.redirect('/my/notifications/prefs')
        prefs = {t: N._pref(user, t) for t in shown}
        return request.render('ts_panel.notification_prefs', {
            'types': [(t, PREF_LABELS[t], t in SMS_STAFF_TYPES) for t in shown], 'prefs': prefs, 'has_phone': bool(phone),
            'sms_live': sms_live, 'flash': request.session.pop('ts_flash', None), 'page_name': 'ts_panel_notification_prefs'})
