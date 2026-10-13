"""O2: a session scoped to ONE invitation, enforced centrally and failing closed.

When an invitation's own message (SMS or e-mail, with its delivery secret) is opened and «موافقم و شروع می‌کنم» tapped
without being signed in, the person is signed in as the account of that number (or address) — but only for that
invitation: the session carries `ts_scope = {aid, uid, phone}`. Before every request (`_pre_dispatch`, after
authentication) and before a website page or attachment is served (`_serve_fallback`), a scoped session:
  * seen on any other website than talentsearch.ir (eot.ir), or where the website cannot be told, is signed out at once
    (the session is destroyed): a GET is sent to the same address as a visitor, anything else answers 403;
  * on talentsearch.ir may only reach
      - this invitation (/invite/<its token>[/...], its short links /i/<its code>[/<secret>]);
      - the player of its attempts (/take/<token>[/...], the ts_tasks endpoints live under it);
      - the participant's own result of those attempts (/my/assessments/<id>[/pdf|/unshare],
        /my/assessments/battery/<id>[/...]);
      - static assets (never /web/image or /websocket), sign-out, and the sign-in (/signup, /login).
    Any other GET page answers 303 to the sign-in with the number by its last four digits («*** ۴۵۶۷»); after the code
    the session is an ordinary full session. Anything else (JSON-RPC, /json, /mail, /web/dataset, /web/session/*, a POST)
    answers 403.
A session whose user no longer matches the scope drops it.

Every response of the invitation, player, guest and short-link families carries `Referrer-Policy: no-referrer` (the token
or code in the address must not leak to another site) and `Cache-Control: no-store` (no shared cache or browser history
copy of a personal page).

The access log never keeps a delivery secret: the werkzeug request line is redacted (/i/<code>/*** and d=***)."""
import logging
import re
from urllib.parse import quote

import werkzeug.exceptions

from odoo import api, models
from odoo.http import request
from odoo.http.session import logout as session_logout

from odoo.addons.ts_core.safe_url import local_path
from odoo.addons.ts_panel.models.security import on_ts_site

_logger = logging.getLogger(__name__)
SCOPE_KEY = 'ts_scope'
KNOWN_KEY = 'ts_auth_known'        # ts_sms.controllers.signup.KNOWN_KEY
OTHER_KEY = 'ts_auth_other'        # «شمارهٔ دیگری دارم» chosen: the known number is no longer offered in this session
STATIC = ('/web/assets/', '/web/static/', '/website/static/', '/web/webclient/translations',
          '/website/translations', '/web/manifest.webmanifest', '/favicon.ico', '/robots.txt')
OPEN = {'/signup', '/signup/send', '/signup/verify', '/login', '/web/session/logout'}
NO_REFERRER = ('/invite/', '/take/', '/i/', '/j/', '/c/', '/start')
_SECRET_RE = re.compile(r'(/i/[a-z0-9]{8,12}/)[A-Za-z0-9_-]{22,64}|([?&]d=)[A-Za-z0-9_-]{22,64}')


class _RedactSecrets(logging.Filter):
    """Request lines of the access log: the delivery secret of an invitation link becomes ***."""

    def filter(self, record):
        try:
            msg = record.getMessage()
            if '/i/' in msg or 'd=' in msg:
                red = _SECRET_RE.sub(lambda m: (m.group(1) or m.group(2)) + '***', msg)
                if red != msg:
                    record.msg, record.args = red, ()
        except Exception:        # noqa: BLE001 - a log line must never break a request
            pass
        return True


_wz = logging.getLogger('werkzeug')
if not any(isinstance(f, _RedactSecrets) for f in _wz.filters):
    _wz.addFilter(_RedactSecrets())


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
    if len(parts) in (2, 3) and parts[0] == 'i':
        return bool(a.short_code) and parts[1] == a.short_code
    attempts = a.ts_battery_attempts() if hasattr(a, 'ts_battery_attempts') else a.attempt_id
    if len(parts) >= 2 and parts[0] == 'take':
        return parts[1] in set(attempts.mapped('access_token'))
    if len(parts) >= 3 and parts[0] == 'my' and parts[1] == 'assessments':
        if parts[2] == 'battery':
            return len(parts) >= 4 and parts[3] == str(a.id)
        return parts[2].isdigit() and int(parts[2]) in attempts.ids and (len(parts) == 3 or parts[3] in ('pdf', 'unshare'))
    return False


def _forbidden():
    werkzeug.exceptions.abort(request.make_response('403 Forbidden', headers=[('Content-Type', 'text/plain')], status=403))


class IrHttpScope(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        kind = (getattr(getattr(rule, 'endpoint', None), 'routing', None) or {}).get('type', 'http')
        cls._ts_scope_guard(kind)

    @classmethod
    def _serve_fallback(cls):
        # website pages, redirects and attachments have no route: the same rule as every route (risk review LOW)
        cls._ts_scope_guard('http')
        return super()._serve_fallback()

    @classmethod
    def _ts_scope_guard(cls, kind='http'):
        sess = request.session
        scope = sess.get(SCOPE_KEY)
        if not scope:
            return
        if not sess.uid or sess.uid != scope.get('uid'):
            sess.pop(SCOPE_KEY, None)        # signed out, or signed in as someone else: the scope is over
            return
        hr = request.httprequest
        page = kind == 'http' and hr.method in ('GET', 'HEAD')
        if not on_ts_site():
            # eot.ir (or a website that cannot be told): a session for one invitation never works here — destroyed
            session_logout(sess, keep_db=True)
            _logger.info('ts_onboard: a session scoped to one invitation reached another website; signed out')
            if page:
                werkzeug.exceptions.abort(request.redirect(local_path(hr.full_path.rstrip('?'), '/'), code=303, local=True))
            _forbidden()
        try:
            allowed = scope_allows(request.env, scope, hr.path)
        except Exception:        # noqa: BLE001 - a scope that cannot be checked allows nothing
            _logger.exception('ts_onboard: scope check failed')
            allowed = False
        if allowed:
            return
        if not page:
            _forbidden()
        if scope.get('phone') and not sess.get(OTHER_KEY):
            sess[KNOWN_KEY] = scope['phone']
        nxt = local_path(hr.full_path.rstrip('?'), '/my')
        werkzeug.exceptions.abort(request.redirect('/signup?next=%s' % quote(nxt, safe='/'), code=303, local=True))

    @api.model
    def get_frontend_session_info(self):
        """A page of a session scoped to one invitation never starts the website bus: without `bus_info` the bus
        service does not open /websocket at all (no connection attempt, no reconnect loop, no 303 on /websocket)."""
        info = super().get_frontend_session_info()
        try:
            if request and request.session.get(SCOPE_KEY):
                info.pop('bus_info', None)
                info.pop('websocket_worker_version', None)
        except Exception:        # noqa: BLE001 - the page renders either way
            _logger.exception('ts_onboard: bus info not removed')
        return info

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        cls._ts_private_headers(response)

    @classmethod
    def _handle_error(cls, exception):
        # the link 404 of an unknown or foreign token (ts_website.page_404) carries the token in its address too
        response = super()._handle_error(exception)
        cls._ts_private_headers(response)
        return response

    @classmethod
    def _ts_private_headers(cls, response):
        try:
            if not request:
                return
            path = request.httprequest.path
            headers = getattr(response, 'headers', None)
            if headers is not None and path.startswith(NO_REFERRER) and on_ts_site():
                headers['Referrer-Policy'] = 'no-referrer'
                headers['Cache-Control'] = 'no-store'
        except Exception:        # noqa: BLE001 - a header must never break a response
            _logger.exception('ts_onboard: referrer header not set')
