"""Small helpers of onb2: signed browser tokens (cookies), their server-side digests, masks.

A browser token is `raw.signature`: `raw` is 24 random bytes (url-safe), the signature an HMAC of raw with the database
secret and a purpose ('guest', 'device'). Only sha256(raw) is ever stored on the server; the raw token lives only in the
HttpOnly cookie and never appears in an address, a redirect or a log line."""
import hashlib
import hmac
import secrets

GUEST_COOKIE = 'ts_guest'          # the guest attempt of this browser (O3)
DEVICE_COOKIE = 'ts_dev'           # this browser, for invitation device binding (O2)
GUEST_COOKIE_AGE = 3 * 24 * 3600   # the attempt itself is deleted 48 h after its last activity
DEVICE_COOKIE_AGE = 90 * 24 * 3600


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


def https(request):
    req = request.httprequest
    return req.scheme == 'https' or req.headers.get('X-Forwarded-Proto') == 'https'


def set_cookie(response, request, name, value, max_age):
    response.set_cookie(name, value, max_age=max_age, path='/', secure=https(request), httponly=True, samesite='Lax')
    return response


def drop_cookie(response, request, name):
    response.set_cookie(name, '', max_age=0, path='/', secure=https(request), httponly=True, samesite='Lax')
    return response


_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def mask_email(email):
    """«ma•••@example.com»: enough for the person to recognise the address, not to read it."""
    email = (email or '').strip()
    if '@' not in email:
        return ''
    local, _at, dom = email.partition('@')
    return '%s•••@%s' % (local[:2], dom)


def first_name(full):
    """The first word of the name a panel wrote on the invitation («سلام مریم»); '' when there is none."""
    words = (full or '').split()          # a half-space (ZWNJ) belongs to the word: «محمد‌رضا» stays one name
    return words[0] if words else ''
