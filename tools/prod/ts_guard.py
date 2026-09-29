#!/usr/bin/env python3
"""ts_guard.py - prove Talent Search work leaves eot.ir (website 1) untouched.

  ts_guard.py snapshot DB PORT LABEL   fingerprint DB rows + rendered eot.ir pages
  ts_guard.py compare  DB PORT LABEL   re-fingerprint and diff against LABEL

DB rows: every existing ir_ui_view / website_page / website_menu /
website_rewrite row with website_id 1 or NULL, website 1 itself, and all
ir_config_parameter rows, hashed without write/create metadata. Rows ADDED
by module installs are listed (grouped), CHANGED or REMOVED rows fail.
Pages: every URL in www.eot.ir's sitemap + system routes, fetched with
Host: www.eot.ir from the server on PORT; body text is normalized (scripts,
csrf tokens, asset hashes, session ids stripped) and hashed.
Exit 0 = eot.ir unchanged; 1 = differences (printed, short).
"""
import sys, json, re, hashlib, subprocess, urllib.request, urllib.error, urllib.parse, difflib, os, html

DIR = "/var/lib/ts_guard"
TABLES = {
    "ir_ui_view": "website_id = 1 OR website_id IS NULL",
    "website_page": "website_id = 1 OR website_id IS NULL",
    "website_menu": "website_id = 1 OR website_id IS NULL",
    "website_rewrite": "website_id = 1 OR website_id IS NULL",
    "website": "id = 1",
    "ir_config_parameter": "true",
}
DROP = "- 'write_date' - 'write_uid' - 'create_date' - 'create_uid'"
SYSTEM = ["/", "/web/login", "/blog", "/shop", "/contactus", "/my", "/survey", "/helpdesk",
          "/this-page-does-not-exist-ts-guard", "/robots.txt", "/sitemap.xml", "/web/reset_password"]


def psql(db, q):
    out = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", db, "-AtF", "\t", "-c", q],
                         capture_output=True, text=True)
    if out.returncode:
        raise SystemExit("psql failed: " + out.stderr[:300])
    return [l.split("\t") for l in out.stdout.splitlines() if l]


def db_rows(db):
    res = {}
    for t, where in TABLES.items():
        key = "key" if t == "ir_config_parameter" else "id"
        extra = ""
        if t == "ir_ui_view":
            extra = ", coalesce(key,''), coalesce(website_id::text,'g')"
        rows = psql(db, f"SELECT {key}::text, md5((to_jsonb(t) {DROP})::text){extra} FROM {t} t WHERE {where}")
        res[t] = {r[0]: r[1:] for r in rows}
    return res


def fetch(port, path, host="www.eot.ir"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": host, "X-Forwarded-Proto": "https", "Accept-Language": "fa-IR"})
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        r = opener.open(req, timeout=60)
        return r.status, r.headers.get("Location", ""), r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", ""), e.read().decode("utf-8", "ignore")


def norm(body):
    b = re.sub(r"(?is)<script.*?</script>", "", body)
    b = re.sub(r'csrf_token[^,}"\n]*', "", b)
    b = re.sub(r"/web/assets/[^\"' )]+", "/web/assets/X", b)
    b = re.sub(r'name="csrf_token" value="[^"]*"', "", b)
    b = re.sub(r"session_id=[^;\"']+", "", b)
    b = re.sub(r'data-oe-[a-z-]+="[^"]*"', "", b)
    b = re.sub(r'(?i)<link[^>]+(preload|modulepreload)[^>]*>', "", b)
    b = re.sub(r"\s+", " ", b)
    return b


def text_of(b):
    t = re.sub(r"(?s)<[^>]+>", "\n", b)
    return [l.strip() for l in html.unescape(t).split("\n") if l.strip()]


def pages(port):
    st, loc, sm = fetch(port, "/sitemap.xml")
    urls = []
    for u in re.findall(r"<loc>(.*?)</loc>", sm):
        p = urllib.parse.urlsplit(html.unescape(u))
        urls.append(urllib.parse.quote(urllib.parse.unquote(p.path)) + (("?" + p.query) if p.query else ""))
    out = {}
    for path in sorted(set(urls + SYSTEM)):
        st, loc, body = fetch(port, path)
        n = norm(body)
        out[path] = {"status": st, "loc": loc, "hash": hashlib.md5(n.encode()).hexdigest(), "text": text_of(n)[:4000]}
    return out


def main():
    mode, db, port, label = sys.argv[1:5]
    os.makedirs(DIR, exist_ok=True)
    path = f"{DIR}/{label}.json"
    cur = {"db": db_rows(db), "pages": pages(port)}
    if mode == "snapshot":
        json.dump(cur, open(path, "w"))
        print(f"snapshot {label}: " + ", ".join(f"{t}={len(v)}" for t, v in cur["db"].items()) + f", pages={len(cur['pages'])}")
        return 0
    base = json.load(open(path))
    bad = 0
    for t, rows in base["db"].items():
        now = cur["db"][t]
        changed = [k for k in rows if k in now and now[k][0] != rows[k][0]]
        removed = [k for k in rows if k not in now]
        added = [k for k in now if k not in rows]
        if changed or removed:
            bad += 1
            print(f"!! {t}: changed={len(changed)} removed={len(removed)} e.g. {[(k, rows[k][1:] if len(rows[k]) > 1 else '') for k in (changed + removed)[:6]]}")
        if added:
            if t == "ir_ui_view":
                site1 = [k for k in added if now[k][2] == "1"]
                if site1:
                    bad += 1
                    print(f"!! ir_ui_view: {len(site1)} NEW website-1 views: {[now[k][1] for k in site1[:8]]}")
                mods = {}
                for k in added:
                    if now[k][2] == "g":
                        m = now[k][1].split(".")[0] or "(no key)"
                        mods[m] = mods.get(m, 0) + 1
                ts = {m: n for m, n in mods.items() if m.startswith("ts_")}
                if ts:
                    bad += 1
                    print(f"!! ir_ui_view: generic views from ts_* modules (must be website-2 scoped): {ts}")
                print(f"   ir_ui_view: {len(added)} new generic views from installed apps: " + ", ".join(f"{m}:{n}" for m, n in sorted(mods.items(), key=lambda x: -x[1])[:15]))
            elif t in ("website_page", "website_menu", "website_rewrite"):
                bad += 1
                print(f"!! {t}: {len(added)} new rows with website 1 or no website: {added[:8]}")
            else:
                print(f"   {t}: {len(added)} new rows")
    for p, b in base["pages"].items():
        c = cur["pages"].get(p)
        if not c:
            continue
        if (c["status"], c["loc"], c["hash"]) != (b["status"], b["loc"], b["hash"]):
            d = [l for l in difflib.unified_diff(b["text"], c["text"], lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("---", "+++")]
            if b["status"] == c["status"] and b["loc"] == c["loc"] and not d:
                continue  # markup-only noise with identical visible text
            bad += 1
            print(f"!! page {urllib.parse.unquote(p)}: {b['status']}->{c['status']} {b['loc']}->{c['loc']} text diff: {d[:6]}")
    print(f"pages compared: {len(base['pages'])}; verdict: {'eot.ir UNCHANGED' if not bad else str(bad) + ' difference group(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
