"""Small helpers of onb2: signed browser tokens (cookies), their server-side digests, masks.

A browser token is `raw.signature`: `raw` is 24 random bytes (url-safe), the signature an HMAC of raw with the database
secret and a purpose ('guest', 'device'). Only sha256(raw) is ever stored on the server; the raw token lives only in the
HttpOnly cookie and never appears in an address, a redirect or a log line.

The delivery secret of an invitation message (models/assignment.py) is kept the same way: only its digest is stored, and
every comparison is constant-time."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

GUEST_COOKIE = 'ts_guest'          # the guest attempt of this browser (O3)
DEVICE_COOKIE = 'ts_dev'           # this browser, for invitation device binding (O2)
GUEST_COOKIE_AGE = 3 * 24 * 3600   # the attempt itself is deleted 48 h after its last activity
DEVICE_DAYS = 30                   # «این دستگاه شخصی من است» ticked: the binding lasts 30 days at most
DEVICE_COOKIE_AGE = DEVICE_DAYS * 24 * 3600
DEVICE_SHARED_HOURS = 12           # unticked: a browser-session cookie, and the server side ends after 12 hours
DLV_BYTES = 16                     # the delivery secret of a message: 16 random bytes = 22 url-safe characters
DLV_RE = re.compile(r'^[A-Za-z0-9_-]{22,64}$')


def _secret(env):
    return env['ir.config_parameter'].sudo().get_str('database.secret') or env.cr.dbname


def sign(env, purpose, raw):
    return hmac.new(_secret(env).encode(), ('ts-onb2:%s:%s' % (purpose, raw)).encode(), hashlib.sha256).hexdigest()[:32]


def new_token(env, purpose):
    """-> (raw, cookie value)."""
    raw = secrets.token_urlsafe(24)
    return raw, '%s.%s' % (raw, sign(env, purpose, raw))


def read_token(env, purpose, value):
    """The raw token of a cookie value whose signature is right, else None."""
    if not value or not isinstance(value, str) or len(value) > 200 or '.' not in value:
        return None
    raw, _dot, sig = value.rpartition('.')
    if not raw or not hmac.compare_digest(sig, sign(env, purpose, raw)):
        return None
    return raw


def digest(raw):
    """What the server stores of a browser token."""
    return hashlib.sha256(('ts-onb2-token:' + (raw or '')).encode()).hexdigest()


def same(raw, stored):
    """Is `stored` the digest of `raw`? Constant-time; False when either is missing."""
    return bool(raw and stored) and hmac.compare_digest(digest(raw), stored)


def dlv_digest(raw):
    """What the server stores of a delivery secret (never the secret itself)."""
    return digest('dlv:' + (raw or ''))


def https(request):
    req = request.httprequest
    return req.scheme == 'https' or req.headers.get('X-Forwarded-Proto') == 'https'


def set_cookie(response, request, name, value, max_age):
    """max_age None: a browser-session cookie (gone when the browser closes). Odoo's Response.set_cookie would add a
    one-year Expires by default: the expiry is always given explicitly."""
    expires = None if max_age is None else datetime.now(timezone.utc) + timedelta(seconds=max_age)
    response.set_cookie(name, value, max_age=max_age, expires=expires, path='/', secure=https(request), httponly=True,
                        samesite='Lax')
    return response


def drop_cookie(response, request, name):
    response.set_cookie(name, '', max_age=0, path='/', secure=https(request), httponly=True, samesite='Lax')
    return response


_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def mask_email(email):
    """«ma***@example.com»: enough for the person to recognise the address, not to read it."""
    email = (email or '').strip()
    if '@' not in email:
        return ''
    local, _at, dom = email.partition('@')
    return '%s***@%s' % (local[:2], dom)


def first_name(full):
    """The first word of the name a panel wrote on the invitation («سلام مریم»); '' when there is none."""
    words = (full or '').split()          # a half-space (ZWNJ) belongs to the word: «محمد‌رضا» stays one name
    return words[0] if words else ''
