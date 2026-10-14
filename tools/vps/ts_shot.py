#!/root/eot-browser/venv/bin/python
"""Headless layout audit of Talent Search pages on a served CLONE (never live accounts).
    ts_shot.py DB PORT [--as LOGIN] PATH...
    ts_shot.py DB PORT --matrix FILE.json        FILE = {"login": ["/path", ...], ...}   (Panel v2, 08_design_system.md section 5)
Matrix entries: "/path[#anchor]" (loaded without the anchor, then scrolled to it, so every theme pass reloads the page);
"POST /path body" (a form post that sets up the next page, no screenshot); "POSTSHOT /path body" (the page a form post
answers with, captured like a page: one post per width / theme). A path with print=1, /my/assessments/ or /a/ also gets a
print-media check and a _print.png.
TS_SHOT_FOLD=1 (`ts shots DB take`): for every width <= 430 also <stem>_fold.png, the viewport only (not full page) at a
phone's height: what a phone shows before scrolling.
Tunnels VPS:18071 -> prod:PORT, maps talentsearch.ir to it, signs in with the clone-only test user
(password read from prod's root-only file, never printed) and reports per page and width:
status, horizontal overflow, elements wider than the viewport, small tap targets, images without alt,
English UI words (body and <title>), missing/duplicate h1, inputs without a label, text contrast
below 4.5:1 (3:1 for large text), console errors, and for report pages the print layout.
Exit code 1 if any page has a problem. Screenshots stay in /root/ts-jobs/shots/."""
import json, os, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

args = sys.argv[1:]
DB, PORT = args[0], args[1]; args = args[2:]
assert DB.startswith('eot_ts'), 'clones only'
LOGIN, MATRIX = None, None
if args and args[0] == '--as':
    LOGIN, args = args[1], args[2:]
elif args and args[0] == '--matrix':
    MATRIX, args = json.load(open(args[1])), []
PATHS = args or ['/']
WIDTHS = tuple(int(x) for x in os.environ.get('TS_SHOT_WIDTHS', '1280,375').split(','))   # portal v3: 320,390,430,768,1280
DARK = tuple(int(x) for x in os.environ.get('TS_SHOT_DARK', '').split(',') if x)   # extra dark-theme pass (contrast + png)
FOLD = os.environ.get('TS_SHOT_FOLD') == '1'       # extra viewport-only png per phone width (what shows before scrolling)
FOLD_H = {320: 568, 360: 740, 375: 667, 390: 844, 393: 852, 412: 915, 414: 896, 430: 932}   # CSS px of common phones
CHROME = '/snap/chromium/current/usr/lib/chromium-browser/chrome'
LOCAL = 10000 + int(PORT)          # one tunnel per clone port: a stale 18071 tunnel once pointed the shots at another slot's clone


def _drop_stale_tunnels():
    """An ssh tunnel already listening on LOCAL but forwarding to another prod port is killed (2026-10-12: an Oct-1 tunnel
    18071 -> prod:8073 made a whole slot-0 matrix photograph slot 1's clone; every sign-in failed and every token was 404)."""
    out = subprocess.run(['ps', '-eo', 'pid=,args='], capture_output=True, text=True).stdout
    for line in out.splitlines():
        pid, _sp, cmd = line.strip().partition(' ')
        m = re.search(r'\bssh\b.*-L\s*(?:127\.0\.0\.1:)?%d:([^:\s]+):(\d+)' % LOCAL, cmd)
        if m and m.group(2) != str(PORT):
            print('stale tunnel %s -> %s:%s killed (pid %s)' % (LOCAL, m.group(1), m.group(2), pid), flush=True)
            subprocess.run(['kill', pid])
            time.sleep(1)


_drop_stale_tunnels()
subprocess.run('ssh -fN -o ExitOnForwardFailure=yes -L %s:127.0.0.1:%s eot-odoo-prod 2>/dev/null || true' % (LOCAL, PORT), shell=True)
os.makedirs('/root/ts-jobs/shots', exist_ok=True)
EN = re.compile(r'\b(Loading|Search|Submit|Login|Log in|Sign in|Logout|My Account|Home|Next|Previous|Back|Save|Cancel|Delete|Edit|Error|Page Not Found|Powered by|Skip to Content|Enter your|Passkey|Password|Email|or|OdooBot)\b')

JS = r"""() => {
  const vw = window.innerWidth, out = {};
  out.scroll = document.documentElement.scrollWidth - vw;
  const wide = [];
  for (const el of document.querySelectorAll('#wrapwrap *')) {
    const r = el.getBoundingClientRect();
    let fixed = false; for (let a = el; a && a !== document.body; a = a.parentElement) { if (getComputedStyle(a).position === 'fixed') { fixed = true; break; } }
    if (r.width && (r.right > vw + 1 || r.left < -1) && !fixed) {
      const p = el.closest('.ts-table-wrap, .o_offcanvas, [aria-hidden=true], .tsp-chips, .tsp-subnav, .tsp-steps');
      if (!p) wide.push(el.tagName.toLowerCase() + '.' + [...el.classList].slice(0,2).join('.'));
    }
  }
  out.wide = [...new Set(wide)].slice(0, 6);
  const small = [];
  for (const el of document.querySelectorAll('main a.ts-btn, main button, main input, main select, #wrap a.ts-btn, #wrap button, #wrap select, #wrap input:not([type=hidden])')) {
    const r = el.getBoundingClientRect();
    if (r.width && r.height && r.height < 40 && el.type !== 'radio' && el.type !== 'checkbox') small.push((el.innerText || el.name || el.tagName).trim().slice(0, 30));
  }
  out.small = small.slice(0, 6);
  out.noalt = [...document.images].filter(i => !i.hasAttribute('alt')).length;
  out.h1 = document.querySelectorAll('h1').length;
  out.title = document.title;
  out.text = document.body.innerText;
  let ascii = 0; for (const el of document.querySelectorAll('#wrap *:not(bdi):not(code):not(script):not(style):not(textarea)')) { for (const n of el.childNodes) { if (n.nodeType === 3 && !n.parentElement.closest('bdi, code')) { ascii += (n.textContent.match(/[0-9]/g) || []).length; } } }
  out.ascii = ascii;
  out.dir = document.documentElement.dir || getComputedStyle(document.body).direction;
  // inputs without a visible or aria label (checklist 2)
  const nolabel = [];
  for (const el of document.querySelectorAll('#wrap input:not([type=hidden]):not([type=submit]):not([type=button]), #wrap select, #wrap textarea')) {
    const id = el.id, has = (id && document.querySelector('label[for="' + CSS.escape(id) + '"]')) || el.closest('label')
      || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby');
    if (!has) nolabel.push(el.name || el.tagName.toLowerCase());
  }
  out.nolabel = nolabel.slice(0, 6);
  // contrast (checklist 3): sample visible text elements
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const parse = s => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(parseFloat); return {c: p.slice(0, 3), a: p.length > 3 ? p[3] : 1}; };
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.backgroundImage && cs.backgroundImage !== 'none') return null; const p = parse(cs.backgroundColor); if (p && p.a > 0.95) return p.c; } return [255, 255, 255]; };
  const low = []; let seen = 0;
  for (const el of document.querySelectorAll('#wrap p, #wrap li, #wrap td, #wrap th, #wrap label, #wrap a, #wrap button, #wrap h1, #wrap h2, #wrap h3, #wrap small, #wrap dd, #wrap dt, #wrap span')) {
    if (seen > 250) break;
    const t = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim()).length;
    const r = el.getBoundingClientRect();
    if (!t || !r.width || !r.height) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.opacity === '0') continue;
    if (el.closest('.ts-sr, .tsp-sr, .sr-only, .visually-hidden') || (r.width <= 1 && r.height <= 1)) continue;   // screen-reader-only text
    seen++;
    const fg = parse(cs.color); if (!fg) continue;
    const bg = bgOf(el); if (!bg) continue;   // gradient or image behind the text: cannot be computed, skip
    const L1 = lum(fg.c), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700, large = size >= 24 || (size >= 18.66 && bold);
    if (ratio < (large ? 3 : 4.5)) low.push(el.tagName.toLowerCase() + '.' + [...el.classList].slice(0, 2).join('.') + ' ' + ratio.toFixed(1));
  }
  out.lowcontrast = [...new Set(low)].slice(0, 5);
  // UX audit additions (2026-10-11): heading order, unnamed controls, landmarks, duplicate ids, lang
  const hs = [...document.querySelectorAll('#wrapwrap h1, #wrapwrap h2, #wrapwrap h3, #wrapwrap h4, #wrapwrap h5, #wrapwrap h6')].filter(h => h.getBoundingClientRect().height).map(h => +h.tagName[1]);
  const skips = []; for (let i = 1; i < hs.length; i++) if (hs[i] > hs[i - 1] + 1) skips.push('h' + hs[i - 1] + '>h' + hs[i]);
  out.hskip = [...new Set(skips)].slice(0, 3);
  const unnamed = [];
  for (const el of document.querySelectorAll('#wrapwrap a[href], #wrapwrap button, #wrapwrap [role=button]')) {
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    if (el.closest('details:not([open])') && !el.closest('summary')) continue;   // a closed <details> still reports a box
    const name = (el.innerText || '').trim() || el.getAttribute('aria-label') || el.getAttribute('title') || (el.getAttribute('aria-labelledby') && 'x') || [...el.querySelectorAll('img[alt]')].map(i => i.alt).join('');
    if (!name) unnamed.push(el.tagName.toLowerCase() + '.' + [...el.classList].slice(0, 2).join('.'));
  }
  out.unnamed = [...new Set(unnamed)].slice(0, 4);
  out.main = document.querySelectorAll('main, [role=main]').length;
  const ids = {}; for (const el of document.querySelectorAll('[id]')) ids[el.id] = (ids[el.id] || 0) + 1;
  out.dupid = Object.keys(ids).filter(k => ids[k] > 1).slice(0, 4);
  out.lang = document.documentElement.lang || '';
  // clin9: empty vertical space between consecutive blocks of the panel (TS_SHOT_GAPS=1 prints it): the spacing audit
  const gaps = [], vis = e => { const c = getComputedStyle(e), r = e.getBoundingClientRect();
    return c.display !== 'none' && c.visibility !== 'hidden' && r.height > 0 && c.position !== 'fixed' && c.position !== 'absolute'; };
  const lab = e => e.id ? '#' + e.id : (e.tagName.toLowerCase() + ([...e.classList].slice(0, 1).map(c => '.' + c).join('')));
  for (const root of document.querySelectorAll('.tsp-shell__main, .tsp-shell__nav, .tsp-shell__main > section, .tsp-shell__main > form, .ts-card')) {
    const kids = [...root.children].filter(vis).sort((x, y) => x.getBoundingClientRect().top - y.getBoundingClientRect().top);   // visual order (CSS order:)
    for (let i = 1; i < kids.length; i++) {
      const a = kids[i - 1].getBoundingClientRect(), b = kids[i].getBoundingClientRect(), g = Math.round(b.top - a.bottom);
      if (g > 24 && b.top > a.top) gaps.push(g + 'px ' + lab(root) + ':' + lab(kids[i - 1]) + '>' + lab(kids[i]));
    }
  }
  out.gaps = [...new Set(gaps)].slice(0, 10);
  out.height = document.documentElement.scrollHeight;
  return out;
}"""


FOCUS_JS = r"""() => {
  // tab through the first focusable controls of the content and report the ones without a visible focus indicator
  const els = [...document.querySelectorAll('#wrap a[href], #wrap button, #wrap input:not([type=hidden]), #wrap select, #wrap textarea')].filter(e => e.getBoundingClientRect().height).slice(0, 8);
  const bad = [];
  for (const el of els) {
    const before = getComputedStyle(el); const b = [before.outlineStyle, before.outlineWidth, before.boxShadow, before.backgroundColor, before.borderColor].join('|');
    el.focus({focusVisible: true});
    if (document.activeElement !== el) continue;
    const a = getComputedStyle(el); const f = [a.outlineStyle, a.outlineWidth, a.boxShadow, a.backgroundColor, a.borderColor].join('|');
    const ring = (a.outlineStyle !== 'none' && parseFloat(a.outlineWidth) > 0) || f !== b;
    if (!ring) bad.push((el.innerText || el.name || el.tagName).trim().slice(0, 20));
    el.blur();
  }
  return bad.slice(0, 3);
}"""


BASE = 'http://talentsearch.ir'
POST_JS = """async ([u, d]) => {
  const b = new URLSearchParams(d), t = document.querySelector('input[name=csrf_token]');
  b.set('csrf_token', t ? t.value : ((window.odoo && odoo.csrf_token) || ''));
  const r = await fetch(u, {method: 'POST', body: b, credentials: 'same-origin', redirect: 'manual'});
  return r.type === 'opaqueredirect' ? 303 : r.status; }"""
FORM_JS = """([u, d]) => {
  const f = document.createElement('form'), b = new URLSearchParams(d), t = document.querySelector('input[name=csrf_token]');
  b.set('csrf_token', t ? t.value : ((window.odoo && odoo.csrf_token) || ''));
  f.method = 'post'; f.action = u;
  for (const [k, v] of b) { const i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = v; f.appendChild(i); }
  document.body.appendChild(f); f.submit(); }"""


def shot_name(path):
    if path.startswith('POSTSHOT '):
        path = path.split(' ', 2)[1] + '_post'
    return re.sub(r'[^a-z0-9]+', '_', path.lower()).strip('_') or 'home'


def _nav(page, path):
    """Open one matrix entry. An #anchor is not part of the navigation (a fragment-only change does not reload the page, so
    the dark pass used to capture the light page, G8-P5-3): load the page, then scroll the anchor into view."""
    if path.startswith('POSTSHOT '):
        _p, url, data = (path.split(' ', 2) + [''])[:3]
        with page.expect_navigation(timeout=90000, wait_until='networkidle') as nv:
            page.evaluate(FORM_JS, [url, data])
        return nv.value
    url, _sep, frag = path.partition('#')
    r = page.goto(BASE + url, timeout=90000, wait_until='networkidle')
    if frag:
        page.evaluate("f => { const e = document.getElementById(f); if (e) { e.scrollIntoView({block: 'start'}); } }", frag)
    return r


def tunnel():
    subprocess.run('ssh -fN -o ExitOnForwardFailure=yes -L %s:127.0.0.1:%s eot-odoo-prod 2>/dev/null || true' % (LOCAL, PORT), shell=True)


def nav(page, path, tries=3):
    """_nav with retries: a reset ssh tunnel (ERR_CONNECTION_RESET / SOCKET_NOT_CONNECTED) is re-opened and the page loaded
    again; after the last try the error is printed and None returned, so one bad page never ends the whole matrix."""
    for i in range(1, tries + 1):
        try:
            return _nav(page, path)
        except Exception as e:
            if i == tries:
                print('!! navigation failed %-40s %s' % (path[:40], str(e).splitlines()[0][:120]), flush=True)
                return None
            time.sleep(3 * i)
            tunnel()


def audit(p, login, paths):
    bad = 0
    pw_file = '/root/.ts_flow_%s_%s' % (DB, (login or '').split('@')[0])
    password = subprocess.run(['ssh', 'eot-odoo-prod', 'cat', pw_file], capture_output=True, text=True).stdout.strip() if login else None
    b = p.chromium.launch(executable_path=CHROME, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                                                        '--host-resolver-rules=MAP talentsearch.ir:80 127.0.0.1:%s' % LOCAL])
    ctx = b.new_context(locale='fa-IR')
    ctx.add_init_script('window.print = function () {};')   # ?print=1 pages open the print dialog; headless must not wait on it
    page = ctx.new_page()
    errors = []
    page.on('console', lambda m: errors.append(m.text[:160]) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)[:160]))
    if login:
        ok = False
        for _try in (1, 2):                  # a reset tunnel during the sign-in once left a whole user on the login page
            try:
                nav(page, '/web/login?email=1')      # onb1: plain /web/login on talentsearch.ir is the mobile sign-in
                page.fill('input[name=login]', login); page.fill('input[name=password]', password)
                # wait for the POST navigation itself: networkidle alone could return before it started, and the next goto
                # then aborted the sign-in (flaky «sign-in failed» for a random login, 2026-10-11)
                with page.expect_navigation(timeout=90000):
                    page.click('form[action="/web/login"] button[type=submit]')
                page.wait_for_load_state('networkidle', timeout=90000)
                ok = '/web/login' not in page.url
            except Exception:
                ok = False
            if ok:
                break
            time.sleep(3)
            tunnel()
        print(('signed in as %s' % login.split('@')[0]) if ok else '!! sign-in failed for %s' % login.split('@')[0], flush=True)
        bad += 0 if ok else 1
    for path in paths:
        if path.startswith('COOKIE '):
            # «COOKIE name value» (onb2): a browser cookie for the pages after it (the guest attempt of this browser)
            _c, cname, cvalue = (path.split(' ', 2) + ['', ''])[:3]
            ctx.add_cookies([{'name': cname, 'value': cvalue, 'domain': 'talentsearch.ir', 'path': '/', 'httpOnly': True,
                              'sameSite': 'Lax'}])
            print('cookie %s set' % cname, flush=True)
            continue
        if path.startswith('POST '):
            # «POST path urlencoded-body»: a form post that sets up the next page (wizard draft), no screenshot
            _p, url, data = (path.split(' ', 2) + [''])[:3]
            st = page.evaluate(POST_JS, [url, data])
            print('post %-4s %-40s %s' % (st, url[:40], 'ok' if st in (200, 303) else 'FAILED'), flush=True)
            bad += 0 if st in (200, 303) else 1
            continue
        for w in WIDTHS:
            errors.clear()
            page.set_viewport_size({'width': w, 'height': 900})
            r = None
            for attempt in (1, 2):           # one retry: a transient socket error must not end the whole matrix
                try:
                    r = nav(page, path)
                    break
                except Exception as e:
                    if attempt == 2:
                        print('!! %-4s %-40s navigation failed: %s' % (w, path[:40], str(e).splitlines()[0][:120]), flush=True)
                    else:
                        time.sleep(3)
            else:
                bad += 1
                continue
            m = page.evaluate(JS)
            body = m.pop('text')
            en = sorted(set(EN.findall(body)))
            en_title = sorted(set(EN.findall(m['title'])))
            probs = []
            if r and r.status != 200: probs.append('status %d' % r.status)
            if m['scroll'] > 0: probs.append('h-scroll %dpx' % m['scroll'])
            if m['wide']: probs.append('wide ' + ','.join(m['wide']))
            if m['small']: probs.append('small-tap ' + '|'.join(m['small']))
            if m['noalt']: probs.append('img-no-alt %d' % m['noalt'])
            if m['h1'] != 1: probs.append('h1=%d' % m['h1'])
            if en: probs.append('EN ' + ','.join(en))
            if en_title: probs.append('EN-title ' + ','.join(en_title))
            if m['nolabel']: probs.append('no-label ' + ','.join(m['nolabel']))
            if m['lowcontrast']: probs.append('contrast ' + '|'.join(m['lowcontrast']))
            if errors: probs.append('console ' + ' | '.join(errors[:2]))
            if m['dir'] != 'rtl': probs.append('dir=' + m['dir'])
            if m['hskip']: probs.append('heading-skip ' + ','.join(m['hskip']))
            if m['unnamed']: probs.append('unnamed ' + ','.join(m['unnamed']))
            if m['main'] != 1: probs.append('main=%d' % m['main'])
            if m['dupid']: probs.append('dup-id ' + ','.join(m['dupid']))
            if not m['lang'].startswith('fa'): probs.append('lang=' + (m['lang'] or '-'))
            info = (' [ascii-digits %d]' % m['ascii']) if m.get('ascii') else ''
            bad += 1 if probs else 0
            name = shot_name(path)
            stem = '/root/ts-jobs/shots/%s%s_%d' % ((login.split('@')[0] + '_') if MATRIX else '', name, w)
            if w == max(WIDTHS):
                open(stem + '.txt', 'w').write('URL %s\nTITLE %s\nFINAL %s\n\n%s' % (path, m['title'], page.url.replace(BASE, ''), body))
                page.keyboard.press('Tab')   # keyboard modality, so :focus-visible styles apply to programmatic focus
                nofocus = page.evaluate(FOCUS_JS)
                if nofocus: probs.append('no-focus-ring ' + '|'.join(nofocus))
            # the shot shows the page at rest: the Tab above lands on the skip link, which is drawn only while focused
            page.evaluate("() => { const a = document.activeElement; if (a && a !== document.body && a.blur) { a.blur(); } }")
            skip = page.evaluate("""() => { const s = document.querySelector('.o_skip_to_content');
              if (!s) { return 0; } const r = s.getBoundingClientRect(), c = getComputedStyle(s);
              return (c.display !== 'none' && c.visibility !== 'hidden' && r.width > 2 && r.height > 2
                      && !/inset\\(50%\\)/.test(c.clipPath) && c.clip.indexOf('rect(0') !== 0) ? Math.round(r.width) : 0; }""")
            if skip:
                bad += 0 if probs else 1
                probs.append('skip-link-visible %dpx' % skip)
            page.screenshot(path=stem + '.png', full_page=True)
            if FOLD and w <= 430:
                page.set_viewport_size({'width': w, 'height': FOLD_H.get(w, int(w * 2.16))})
                page.screenshot(path=stem + '_fold.png', full_page=False)
                page.set_viewport_size({'width': w, 'height': 900})
            print('%s %-4s %-40s %s%s' % (r.status if r else '-', w, path[:40], '; '.join(probs) or 'ok', info), flush=True)
            if os.environ.get('TS_SHOT_GAPS') == '1':
                print('   gaps %-4s h=%d %s' % (w, m.get('height', 0), ' | '.join(m.get('gaps') or []) or '-'), flush=True)
        for w in DARK:
            page.set_viewport_size({'width': w, 'height': 900})
            page.evaluate("() => localStorage.setItem('ts-site-theme', 'dark')")
            nav(page, path)
            m = page.evaluate(JS); m.pop('text')
            name = shot_name(path)
            page.screenshot(path='/root/ts-jobs/shots/%s%s_%d_dark.png' % ((login.split('@')[0] + '_') if MATRIX else '', name, w), full_page=True)
            print('dark %-4s %-40s %s' % (w, path[:40], ('contrast ' + '|'.join(m['lowcontrast'])) if m['lowcontrast'] else 'ok'), flush=True)
            page.evaluate("() => localStorage.setItem('ts-site-theme', 'light')")
        if '/my/assessments/' in path or '/a/' in path or 'print=1' in path:
            if 'print=1' in path:
                nav(page, path)          # the print mode page itself (G8-P10-7), not the last theme pass
            page.emulate_media(media='print'); page.set_viewport_size({'width': 794, 'height': 1123})
            hidden = page.evaluate("() => [...document.querySelectorAll('.ts-noprint, header#top, footer')].filter(e => getComputedStyle(e).display !== 'none').length")
            over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            print('print     %-40s %s' % (path[:40], 'ok' if not hidden and over <= 0 else 'visible-chrome=%d overflow=%d' % (hidden, over)), flush=True)
            page.screenshot(path='/root/ts-jobs/shots/%s%s_print.png' % ((login.split('@')[0] + '_') if MATRIX else '', shot_name(path)), full_page=True)
            page.emulate_media(media='screen')
    b.close()
    return bad


with sync_playwright() as p:
    total = 0
    if MATRIX:
        for login, paths in MATRIX.items():
            total += audit(p, login, paths)
    else:
        total = audit(p, LOGIN, PATHS)
print('SHOT %s' % ('OK' if not total else 'PROBLEMS %d' % total))
sys.exit(1 if total else 0)
