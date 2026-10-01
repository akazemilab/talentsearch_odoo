#!/usr/bin/env python3
"""ts_pages.py PORT HOST PATH... - one line per page: status, title. A 5xx or a traceback in the
body prints a FAIL line (so rehearsal digests count it); everything else prints 'ok'."""
import html, re, sys, urllib.error, urllib.request

port, host, paths = sys.argv[1], sys.argv[2], sys.argv[3:]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


opener = urllib.request.build_opener(NoRedirect)
bad = 0
for p in paths:
    req = urllib.request.Request(f'http://127.0.0.1:{port}{p}', headers={'Host': host, 'X-Forwarded-Proto': 'https', 'Accept-Language': 'fa-IR'})
    try:
        r = opener.open(req, timeout=60)
        st, body = r.status, r.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        st, body = e.code, e.read().decode('utf-8', 'ignore')
    except Exception as e:
        st, body = 0, str(e)
    t = re.findall(r'<title>(.*?)</title>', body, re.S)
    title = html.unescape(t[0].strip())[:60] if t else '-'
    wid = re.search(r'data-website-id="(\d+)"', body)
    if st >= 500 or st == 0 or 'Traceback (most recent call last)' in body:
        bad += 1
        print(f'FAIL  page {host}{p} {st} {title}')
    else:
        print(f'ok    {st} {p} [w{wid.group(1) if wid else "-"}] {title}')
print(f'SUMMARY {len(paths) - bad}/{len(paths)} passed (pages on {host})')
