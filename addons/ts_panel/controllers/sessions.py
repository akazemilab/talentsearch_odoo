"""My sessions (S18, ACC-3, ACC-4): the person's own devices from Odoo's `res.session`, and sign-out of the others.

Only the signed-in person's rows are read. Revoking goes through the private `_revoke()` of the stock model, after our own
re-authentication (a person who signs in by SMS has no password for the stock identity check).
"""
from odoo import http
from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.http import request

from odoo.addons.ts_assessment.models.attempt import jalali

from .base import flash_ok, need_reauth, pop_flash, reauth_fresh


def _sessions(user):
    return request.env['res.session'].sudo().search([('user_id', '=', user.id), ('revoked', '=', False)], order='last_activity desc')  # ts-scope-ok: the user's own sessions


class TsPanelSessions(http.Controller):

    @http.route('/my/sessions', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def page(self, **kw):
        _ts_site_or_404()
        rows = _sessions(request.env.user)
        ok, err = pop_flash()
        p = request.session.get('ts_pv2_pending') or {}
        pend = {}
        if p.get('kind') == 'my_sessions':
            request.session.pop('ts_pv2_pending', None)
            pend = p if reauth_fresh() else {}
        return request.render('ts_panel.my_sessions', {'sessions': rows, 'ok': ok, 'error': err, 'jalali': jalali,
                                                       'resumed': bool(pend), 'resumed_sid': pend.get('sid') or '',
                                                       'page_name': 'ts_my_sessions'})

    @http.route('/my/sessions/revoke', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def revoke(self, **post):
        _ts_site_or_404()
        user = request.env.user
        sid_in = (post.get('sid') or '')[:20]
        redo = need_reauth('خروج از دستگاه‌های دیگر' if sid_in == 'others' else 'خروج از یک دستگاه دیگر', '/my/sessions',
                           {'kind': 'my_sessions', 'sid': sid_in})
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
        flash_ok('از %s دستگاه دیگر خارج شدید.' % str(n).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')) if n else 'دستگاه دیگری برای خروج نبود.')
        return request.redirect('/my/sessions')
