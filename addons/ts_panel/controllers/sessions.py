"""My sessions (S18, ACC-3, ACC-4): the person's own devices from Odoo's `res.session`, and sign-out of the others.

Only the signed-in person's rows are read. Revoking goes through the private `_revoke()` of the stock model, after our own
re-authentication (a person who signs in by SMS has no password for the stock identity check).
"""
from odoo import http
from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.http import request

from odoo.addons.ts_assessment.models.attempt import jalali

from .base import flash_ok, need_reauth, pop_flash


def _sessions(user):
    return request.env['res.session'].sudo().search([('user_id', '=', user.id), ('revoked', '=', False)], order='last_activity desc')  # ts-scope-ok: the user's own sessions


class TsPanelSessions(http.Controller):

    @http.route('/my/sessions', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def page(self, **kw):
        _ts_site_or_404()
        rows = _sessions(request.env.user)
        ok, err = pop_flash()
        return request.render('ts_panel.my_sessions', {'sessions': rows, 'ok': ok, 'error': err, 'jalali': jalali,
                                                       'page_name': 'ts_my_sessions'})

    @http.route('/my/sessions/revoke', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def revoke(self, **post):
        _ts_site_or_404()
        user = request.env.user
        redo = need_reauth('برای خروج از دستگاه‌های دیگر', '/my/sessions')
        if redo:
            return redo
        mine = _sessions(user)
        sid = post.get('sid') or ''
        if sid == 'others':
            targets = mine.filtered(lambda s: not s.is_current)
        else:
            targets = mine.filtered(lambda s: str(s.id) == sid and not s.is_current)
        n = len(targets)
        if n:
            targets._revoke()
            request.env['ts.audit.event'].sudo().log('account.sessions_revoke', user, count=n)
        flash_ok('از %s نشست خارج شدید.' % str(n).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')) if n else 'نشست دیگری برای خروج نبود.')
        return request.redirect('/my/sessions')
