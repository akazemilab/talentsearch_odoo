"""Session length of a mobile sign-in on talentsearch.ir (onb1, S-AUTH).

The sign-in page stores the visitor's choice in the session as `ts_session_mode` (portal accounts only, website 4 only):
- 'long'    («این دستگاه شخصی من است», the default): the session cookie lives 30 days, renewed whenever Odoo re-issues it;
- 'browser' (box unticked): the cookie has no expiry and ends when the browser closes.
Every other session (eot.ir, the back office, email sign-in, internal users) keeps Odoo's own cookie and lifetime: this
code only rewrites the session cookie of a session that carries that key, and the server-side clean-up keeps only such
'long' sessions longer than Odoo's own limit.
"""
import glob
import json
import os
import logging
import time
from contextlib import suppress

from werkzeug.http import dump_cookie

from odoo import api, models
from odoo.http import request
from odoo.http.session import get_session_max_inactivity, session_store

_logger = logging.getLogger(__name__)
LONG_SESSION_S = 30 * 24 * 3600


def _is_long_session(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    return data.get('ts_session_mode') == 'long' and bool(data.get('uid'))


def cookie_mode(session, user, website):
    """'long' | 'browser' | None: the cookie a mobile sign-in asked for, and only for a portal account on talentsearch.ir
    (risk review: the session flag alone is not enough). None = Odoo's own cookie, untouched."""
    mode = session.get('ts_session_mode') if session.uid else None
    if mode not in ('long', 'browser'):
        return None
    if not (user and user.share and website and website._ts_is_current()):
        return None
    return mode


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        try:
            sess = request.session
            if not sess.get('ts_session_mode') or not sess.uid:
                return
            headers = getattr(response, 'headers', None)
            if headers is None:
                return
            cookies = headers.getlist('Set-Cookie')
            if not any(c.startswith('session_id=') for c in cookies):
                return          # only when Odoo (re)issues the session cookie
            # the website of this request (context website_id), else the one whose domain is this request's host
            website = cls._ts_request_website()
            mode = cookie_mode(sess, request.env['res.users'].sudo().browse(sess.uid), website)
            if not mode:
                return
            keep = [c for c in cookies if not c.startswith('session_id=')]
            headers.remove('Set-Cookie')
            for c in keep:
                headers.add('Set-Cookie', c)
            headers.add('Set-Cookie', dump_cookie('session_id', sess.sid, path='/', httponly=True,
                                                  max_age=LONG_SESSION_S if mode == 'long' else None))
        except Exception:     # never break a response over the cookie length
            _logger.exception('talentsearch session cookie not adjusted')
            return

    @classmethod
    def _ts_request_website(cls):
        from urllib.parse import urlsplit
        site = request.env.website
        if site:
            return site
        host = (request.httprequest.host or '').split(':')[0].lower()
        for w in request.env['website'].sudo().search([('domain', '!=', False)]):
            d = w.domain if '://' in w.domain else 'https://' + w.domain
            if (urlsplit(d).hostname or '').lower() == host:
                return w
        return None

    @api.autovacuum
    def _gc_sessions(self):
        """Odoo's clean-up, except that a 'long' talentsearch.ir session survives up to 30 days without activity."""
        if os.getenv('ODOO_SKIP_GC_SESSIONS'):
            return
        store = session_store()
        root = getattr(store, 'path', None)
        base = get_session_max_inactivity(self.env)
        if not root or base >= LONG_SESSION_S:
            return super()._gc_sessions()
        now = time.time()
        for path in glob.iglob(os.path.join(root, '*', '*')):
            try:
                age = now - os.path.getmtime(path)
            except OSError:
                continue
            if age < base or (age < LONG_SESSION_S and _is_long_session(path)):
                continue
            with suppress(OSError):
                os.unlink(path)
