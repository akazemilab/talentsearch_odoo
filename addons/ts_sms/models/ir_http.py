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
import time
from contextlib import suppress

from werkzeug.http import dump_cookie

from odoo import api, models
from odoo.http import request
from odoo.http.session import get_session_max_inactivity, session_store

LONG_SESSION_S = 30 * 24 * 3600


def _is_long_session(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    return data.get('ts_session_mode') == 'long' and bool(data.get('uid'))


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        try:
            sess = request.session
            mode = sess.get('ts_session_mode') if sess.uid else None
            headers = getattr(response, 'headers', None)
            if mode not in ('long', 'browser') or headers is None:
                return
            cookies = headers.getlist('Set-Cookie')
            if not any(c.startswith('session_id=') for c in cookies):
                return
            keep = [c for c in cookies if not c.startswith('session_id=')]
            headers.remove('Set-Cookie')
            for c in keep:
                headers.add('Set-Cookie', c)
            headers.add('Set-Cookie', dump_cookie('session_id', sess.sid, path='/', httponly=True,
                                                  max_age=LONG_SESSION_S if mode == 'long' else None))
        except Exception:     # never break a response over the cookie length
            return

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
