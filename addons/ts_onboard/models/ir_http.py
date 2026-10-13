"""O2: a session scoped to ONE invitation, enforced centrally (talentsearch.ir only; eot.ir never sees such a session).

When an invitation reached the person by SMS (or e-mail) and they tap «موافقم و شروع می‌کنم» without being signed in, they
are signed in as the account of that number (or address) — but only for that invitation: the session carries
`ts_scope = {aid, uid, phone}`. Before every request (`_pre_dispatch`, after authentication) a scoped session may only
reach:
  * this invitation (/invite/<its token>[/...], its short link /i/<its code>);
  * the player of its attempts (/take/<token>[/...], the ts_tasks endpoints live under it);
  * the participant's own result of those attempts (/my/assessments/<id>[/pdf|/unshare], /my/assessments/battery/<id>[/...]);
  * static assets, sign-out, and the sign-in (/signup, /login).
Anything else answers 303 to the sign-in with the number shown masked («۰۹۱۲***۴۵۶۷»); after the code the session is an
ordinary full session. A session whose user no longer matches the scope drops it.

Every response of the invitation, player, guest and short-link families carries `Referrer-Policy: no-referrer` (the token
or code in the address must not leak to another site) and `Cache-Control: no-store` (no shared cache or browser history
copy of a personal page)."""
import logging
from urllib.parse import quote

import werkzeug.exceptions

from odoo import models
from odoo.http import request

from odoo.addons.ts_core.safe_url import local_path
from odoo.addons.ts_panel.models.security import on_ts_site

_logger = logging.getLogger(__name__)
SCOPE_KEY = 'ts_scope'
KNOWN_KEY = 'ts_auth_known'        # ts_sms.controllers.signup.KNOWN_KEY
OTHER_KEY = 'ts_auth_other'        # «شمارهٔ دیگری دارم» chosen: the known number is no longer offered in this session
STATIC = ('/web/assets/', '/web/image/', '/web/static/', '/website/static/', '/web/webclient/translations',
          '/website/translations', '/web/manifest.webmanifest', '/favicon.ico', '/robots.txt', '/websocket')
OPEN = {'/signup', '/signup/send', '/signup/verify', '/login', '/web/session/logout'}
NO_REFERRER = ('/invite/', '/take/', '/i/', '/j/', '/c/', '/start')


def scope_allows(env, scope, path):
    """May a session scoped to `scope` reach `path`?"""
    if path in OPEN or path.startswith(STATIC):
        return True
    a = env['ts.assignment'].sudo().browse(int(scope.get('aid') or 0)).exists()
    if not a or (a.user_id and a.user_id.id != scope.get('uid')):
        return False
    parts = [p for p in path.split('/') if p]
    if len(parts) >= 2 and parts[0] == 'invite':
        return parts[1] == a.token
    if len(parts) == 2 and parts[0] == 'i':
        return bool(a.short_code) and parts[1] == a.short_code
    attempts = a.ts_battery_attempts() if hasattr(a, 'ts_battery_attempts') else a.attempt_id
    if len(parts) >= 2 and parts[0] == 'take':
        return parts[1] in set(attempts.mapped('access_token'))
    if len(parts) >= 3 and parts[0] == 'my' and parts[1] == 'assessments':
        if parts[2] == 'battery':
            return len(parts) >= 4 and parts[3] == str(a.id)
        return parts[2].isdigit() and int(parts[2]) in attempts.ids and (len(parts) == 3 or parts[3] in ('pdf', 'unshare'))
    return False


class IrHttpScope(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        cls._ts_scope_guard()

    @classmethod
    def _ts_scope_guard(cls):
        sess = request.session
        scope = sess.get(SCOPE_KEY)
        if not scope:
            return
        if not sess.uid or sess.uid != scope.get('uid'):
            sess.pop(SCOPE_KEY, None)        # signed out, or signed in as someone else: the scope is over
            return
        if not on_ts_site():
            return
        hr = request.httprequest
        try:
            allowed = scope_allows(request.env, scope, hr.path)
        except Exception:        # noqa: BLE001 - a scope that cannot be checked allows nothing
            _logger.exception('ts_onboard: scope check failed')
            allowed = False
        if allowed:
            return
        if scope.get('phone') and not sess.get(OTHER_KEY):
            sess[KNOWN_KEY] = scope['phone']
        target = hr.full_path if hr.method in ('GET', 'HEAD') else hr.path
        nxt = local_path(target.rstrip('?'), '/my')
        werkzeug.exceptions.abort(request.redirect('/signup?next=%s' % quote(nxt, safe='/'), code=303, local=True))

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        try:
            path = request.httprequest.path
            headers = getattr(response, 'headers', None)
            if headers is not None and path.startswith(NO_REFERRER) and on_ts_site():
                headers['Referrer-Policy'] = 'no-referrer'
                headers['Cache-Control'] = 'no-store'
        except Exception:        # noqa: BLE001 - a header must never break a response
            _logger.exception('ts_onboard: referrer header not set')
