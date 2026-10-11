#!/root/eot-browser/venv/bin/python
"""Headless layout audit of Talent Search pages on a served CLONE (never live accounts).
    ts_shot.py DB PORT [--as LOGIN] PATH...
    ts_shot.py DB PORT --matrix FILE.json        FILE = {"login": ["/path", ...], ...}   (Panel v2, 08_design_system.md section 5)
Tunnels VPS:18071 -> prod:PORT, maps talentsearch.ir to it, signs in with the clone-only test user
(password read from prod's root-only file, never printed) and reports per page and width:
status, horizontal overflow, elements wider than the viewport, small tap targets, images without alt,
English UI words (body and <title>), missing/duplicate h1, inputs without a label, text contrast
below 4.5:1 (3:1 for large text), console errors, and for report pages the print layout.
Exit code 1 if any page has a problem. Screenshots stay in /root/ts-jobs/shots/."""
import json, os, re, subprocess, sys
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
CHROME = '/snap/chromium/current/usr/lib/chromium-browser/chrome'
LOCAL = 10000 + int(PORT)          # one tunnel per clone port: a stale 18071 tunnel once pointed the shots at another slot's clone
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
  let ascii = 0; for (const el of document.querySelectorAll('#wrap *:not(bdi):not(code):not(script):not(style)')) { for (const n of el.childNodes) { if (n.nodeType === 3 && !n.parentElement.closest('bdi, code')) { ascii += (n.textContent.match(/[0-9]/g) || []).length; } } }
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
    const name = (el.innerText || '').trim() || el.getAttribute('aria-label') || el.getAttribute('title') || (el.getAttribute('aria-labelledby') && 'x') || [...el.querySelectorAll('img[alt]')].map(i => i.alt).join('');
    if (!name) unnamed.push(el.tagName.toLowerCase() + '.' + [...el.classList].slice(0, 2).join('.'));
  }
  out.unnamed = [...new Set(unnamed)].slice(0, 4);
  out.main = document.querySelectorAll('main, [role=main]').length;
  const ids = {}; for (const el of document.querySelectorAll('[id]')) ids[el.id] = (ids[el.id] || 0) + 1;
  out.dupid = Object.keys(ids).filter(k => ids[k] > 1).slice(0, 4);
  out.lang = document.documentElement.lang || '';
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


def audit(p, login, paths):
    bad = 0
    pw_file = '/root/.ts_flow_%s_%s' % (DB, (login or '').split('@')[0])
    password = subprocess.run(['ssh', 'eot-odoo-prod', 'cat', pw_file], capture_output=True, text=True).stdout.strip() if login else None
    b = p.chromium.launch(executable_path=CHROME, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                                                        '--host-resolver-rules=MAP talentsearch.ir:80 127.0.0.1:%s' % LOCAL])
    ctx = b.new_context(locale='fa-IR')
    page = ctx.new_page()
    errors = []
    page.on('console', lambda m: errors.append(m.text[:160]) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)[:160]))
    BASE = 'http://talentsearch.ir'
    if login:
        page.goto(BASE + '/web/login', timeout=90000)
        page.fill('input[name=login]', login); page.fill('input[name=password]', password)
        page.click('form[action="/web/login"] button[type=submit]'); page.wait_for_load_state('networkidle', timeout=90000)
        ok = '/web/login' not in page.url
        print(('signed in as %s' % login.split('@')[0]) if ok else '!! sign-in failed for %s' % login.split('@')[0], flush=True)
        bad += 0 if ok else 1
    for path in paths:
        for w in WIDTHS:
            errors.clear()
            page.set_viewport_size({'width': w, 'height': 900})
            r = page.goto(BASE + path, timeout=90000, wait_until='networkidle')
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
            name = re.sub(r'[^a-z0-9]+', '_', path.lower()).strip('_') or 'home'
            stem = '/root/ts-jobs/shots/%s%s_%d' % ((login.split('@')[0] + '_') if MATRIX else '', name, w)
            if w == max(WIDTHS):
                open(stem + '.txt', 'w').write('URL %s\nTITLE %s\nFINAL %s\n\n%s' % (path, m['title'], page.url.replace(BASE, ''), body))
                page.keyboard.press('Tab')   # keyboard modality, so :focus-visible styles apply to programmatic focus
                nofocus = page.evaluate(FOCUS_JS)
                if nofocus: probs.append('no-focus-ring ' + '|'.join(nofocus))
            page.screenshot(path=stem + '.png', full_page=True)
            print('%s %-4s %-40s %s%s' % (r.status if r else '-', w, path[:40], '; '.join(probs) or 'ok', info), flush=True)
        for w in DARK:
            page.set_viewport_size({'width': w, 'height': 900})
            page.evaluate("() => localStorage.setItem('ts-site-theme', 'dark')")
            page.goto(BASE + path, timeout=90000, wait_until='networkidle')
            m = page.evaluate(JS); m.pop('text')
            name = re.sub(r'[^a-z0-9]+', '_', path.lower()).strip('_') or 'home'
            page.screenshot(path='/root/ts-jobs/shots/%s%s_%d_dark.png' % ((login.split('@')[0] + '_') if MATRIX else '', name, w), full_page=True)
            print('dark %-4s %-40s %s' % (w, path[:40], ('contrast ' + '|'.join(m['lowcontrast'])) if m['lowcontrast'] else 'ok'), flush=True)
            page.evaluate("() => localStorage.setItem('ts-site-theme', 'light')")
        if '/my/assessments/' in path or '/a/' in path:
            page.emulate_media(media='print'); page.set_viewport_size({'width': 794, 'height': 1123})
            hidden = page.evaluate("() => [...document.querySelectorAll('.ts-noprint, header#top, footer')].filter(e => getComputedStyle(e).display !== 'none').length")
            over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            print('print     %-40s %s' % (path[:40], 'ok' if not hidden and over <= 0 else 'visible-chrome=%d overflow=%d' % (hidden, over)), flush=True)
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
