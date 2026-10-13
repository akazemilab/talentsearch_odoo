"""One validator for every return path (next / redirect) taken from a request on talentsearch.ir (onb1 risk review).

A return path is accepted only when it is a path on this site:
- no character below 0x21 (spaces, tabs, newlines, other control characters) and no backslash, raw or percent-encoded
  as a control character;
- it starts with a single «/» — never «//» or «/\\» — and the character after it is not an encoded «/», «\\» or tab
  (%2F, %5C, %09), which some browsers and proxies decode into a protocol-relative address;
- urlsplit() finds neither a scheme nor a host.
Anything else becomes the default (the person's own page). The result is never longer than 300 characters.
"""
import re
from urllib.parse import unquote, urlsplit

MAX_LEN = 300
_ENCODED_AFTER_SLASH = re.compile(r'^/%(2f|5c|09)', re.IGNORECASE)


def _bad_chars(text):
    return any(ord(ch) < 0x21 for ch in text) or '\\' in text


def local_path(value, default='/my'):
    """`value` when it is a safe path on this site, else `default`."""
    if not isinstance(value, str):
        return default
    v = value
    if not v or len(v) > 2000 or _bad_chars(v):
        return default
    if not v.startswith('/') or v.startswith('//') or v.startswith('/\\') or _ENCODED_AFTER_SLASH.match(v):
        return default
    decoded = unquote(v)
    # decoded once more: a control character or a backslash hidden behind %-encoding, or a «//» start, is refused too
    if any(ord(ch) < 0x20 for ch in decoded) or '\\' in decoded or decoded.startswith('//'):
        return default
    parts = urlsplit(v)
    if parts.scheme or parts.netloc:
        return default
    return v[:MAX_LEN]
