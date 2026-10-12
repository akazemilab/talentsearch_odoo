"""Notification center and preferences (S10, NOT-1, NOT-2, ACC-7). Every route is for the signed-in person's own rows only."""
import re

from odoo import http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits, jalali

from ..models.notify_texts import PREF_LABELS, SMS_STAFF_TYPES, TITLES, TYPES

PARTICIPANT_TYPES = ('invite', 'reminder', 'result_ready_participant', 'data_request_update')
PAGE = 50
# Preference groups of the settings page (UX audit G4 P19-1) and the security events that always reach the site bell (P19-2).
PREF_GROUPS = [
    ('mine', 'سنجه‌های خودم', ('invite', 'reminder', 'result_ready_participant', 'data_request_update')),
    ('people', 'شرکت‌کنندگان پنل', ('result_ready_staff', 'shared_with_panel', 'share_revoked', 'client_handover_request')),
    ('admin', 'مدیریت پنل', ('panel_suspended', 'member_joined', 'export_ready', 'import_done',
                                 'low_balance')),
    ('security', 'امنیت', ('support_access_opened', 'panel_transferred', 'panel_closed')),
]
ALWAYS_ON = ('support_access_opened', 'panel_transferred', 'panel_closed')
_RESULT_URL = re.compile(r'^/my/assessments/(\d+)')


def _display_title(row, user):
    """The title shown in the list. Stored titles never carry a name or a score; the page adds what this reader may see anyway:
    the instrument of the reader's own result, the panel name for a member (UX audit G2 P7-3, G4 P18-3)."""
    title = row.title or TITLES.get(row.type, '')
    if row.type == 'result_ready_participant':
        m = _RESULT_URL.match(row.url or '')
        if m:
            at = request.env['ts.attempt'].sudo().search([('id', '=', int(m.group(1))), ('user_id', '=', user.id)], limit=1)  # ts-scope-ok: own attempt
            if at:
                return 'نتیجهٔ «%s» آماده است' % at.instrument_id.title
    if row.workspace_id and row.type not in PARTICIPANT_TYPES:
        return '%s: %s' % (row.workspace_id.sudo().name, title)
    return title


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
        items = [{'id': r.id, 'title': _display_title(r, user), 'new': not r.read_at, 'when': jalali(r.create_date)} for r in rows]
        return request.render('ts_panel.notifications', {
            'jalali': jalali, 'fa': fa_digits, 'rows': rows, 'items': items, 'unread': N._unread_count(user), 'only_unread': only_unread,
            'flash': request.session.pop('ts_flash', None), 'page_name': 'ts_panel_notifications'})

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
                in_app = t in ALWAYS_ON or post.get('app_' + t) == '1'      # security events always reach the bell
                env['ts.notify.pref'].ts_save(user, t, in_app, bool(phone) and post.get('sms_' + t) == '1')
            request.session['ts_flash'] = 'ترجیح‌های اعلان ذخیره شد.'
            return request.redirect('/my/notifications/prefs')
        prefs = {t: N._pref(user, t) for t in shown}
        groups = []
        for key, label, types in PREF_GROUPS:
            rows = [(t, PREF_LABELS[t], t in SMS_STAFF_TYPES, t in ALWAYS_ON) for t in types if t in shown]
            if rows:
                groups.append({'key': key, 'label': label, 'rows': rows})
        return request.render('ts_panel.notification_prefs', {
            'types': [(t, PREF_LABELS[t], t in SMS_STAFF_TYPES) for t in shown], 'groups': groups, 'prefs': prefs, 'has_phone': bool(phone),
            'any_sms': any(t in SMS_STAFF_TYPES for t in shown),
            'sms_live': sms_live, 'flash': request.session.pop('ts_flash', None), 'page_name': 'ts_panel_notification_prefs'})
