#!/root/eot-browser/venv/bin/python
"""Headless layout audit of Talent Search pages on a served CLONE (never live accounts).
    ts_shot.py DB PORT [--as LOGIN] PATH...
Tunnels VPS:18071 -> prod:PORT, maps talentsearch.ir to it, signs in with the
clone-only test user (password read from prod's root-only file, never printed) and
reports per page and width: status, horizontal overflow, elements wider than the
viewport, small tap targets, images without alt, English UI words, console errors,
and for report pages the print layout. Screenshots stay in /root/ts-jobs/shots/."""
import os, re, subprocess, sys
from playwright.sync_api import sync_playwright

args = sys.argv[1:]
DB, PORT = args[0], args[1]; args = args[2:]
assert DB.startswith('eot_ts'), 'clones only'
LOGIN = None
if args and args[0] == '--as':
    LOGIN, args = args[1], args[2:]
PATHS = args or ['/']
CHROME = '/snap/chromium/current/usr/lib/chromium-browser/chrome'
subprocess.run('ssh -fN -o ExitOnForwardFailure=yes -L 18071:127.0.0.1:%s eot-odoo-prod 2>/dev/null || true' % PORT, shell=True)
os.makedirs('/root/ts-jobs/shots', exist_ok=True)
EN = re.compile(r'\b(Loading|Search|Submit|Login|Log in|Sign in|Logout|My Account|Home|Next|Previous|Back|Save|Cancel|Delete|Edit|Error|Page Not Found|Powered by|Skip to Content)\b')

JS = r"""() => {
  const vw = window.innerWidth, out = {};
  out.scroll = document.documentElement.scrollWidth - vw;
  const wide = [];
  for (const el of document.querySelectorAll('#wrapwrap *')) {
    const r = el.getBoundingClientRect();
    if (r.width && (r.right > vw + 1 || r.left < -1) && getComputedStyle(el).position !== 'fixed') {
      const p = el.closest('.ts-table-wrap, .o_offcanvas, [aria-hidden=true]');
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
  out.dir = document.documentElement.dir || getComputedStyle(document.body).direction;
  return out;
}"""

pw_file = '/root/.ts_flow_%s_%s' % (DB, (LOGIN or '').split('@')[0])
password = subprocess.run(['ssh', 'eot-odoo-prod', 'cat', pw_file], capture_output=True, text=True).stdout.strip() if LOGIN else None
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                                                        '--host-resolver-rules=MAP talentsearch.ir:80 127.0.0.1:18071'])
    ctx = b.new_context(locale='fa-IR')
    page = ctx.new_page()
    errors = []
    page.on('console', lambda m: errors.append(m.text[:160]) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)[:160]))
    BASE = 'http://talentsearch.ir'
    if LOGIN:
        page.goto(BASE + '/web/login', timeout=90000)
        page.fill('input[name=login]', LOGIN); page.fill('input[name=password]', password)
        page.click('form[action="/web/login"] button[type=submit]'); page.wait_for_load_state('networkidle', timeout=90000)
        print('signed in' if '/web/login' not in page.url else '!! sign-in failed', flush=True)
    for path in PATHS:
        for w in (1280, 375):
            errors.clear()
            page.set_viewport_size({'width': w, 'height': 900})
            r = page.goto(BASE + path, timeout=90000, wait_until='networkidle')
            m = page.evaluate(JS)
            en = sorted(set(EN.findall(m.pop('text'))))
            probs = []
            if m['scroll'] > 0: probs.append('h-scroll %dpx' % m['scroll'])
            if m['wide']: probs.append('wide ' + ','.join(m['wide']))
            if m['small']: probs.append('small-tap ' + '|'.join(m['small']))
            if m['noalt']: probs.append('img-no-alt %d' % m['noalt'])
            if m['h1'] != 1: probs.append('h1=%d' % m['h1'])
            if en: probs.append('EN ' + ','.join(en))
            if errors: probs.append('console ' + ' | '.join(errors[:2]))
            if m['dir'] != 'rtl': probs.append('dir=' + m['dir'])
            name = re.sub(r'[^a-z0-9]+', '_', path.lower()).strip('_') or 'home'
            page.screenshot(path='/root/ts-jobs/shots/%s_%d.png' % (name, w), full_page=True)
            print('%s %-4s %-40s %s' % (r.status if r else '-', w, path[:40], '; '.join(probs) or 'ok'), flush=True)
        if '/my/assessments/' in path or '/a/' in path:
            page.emulate_media(media='print'); page.set_viewport_size({'width': 794, 'height': 1123})
            hidden = page.evaluate("() => [...document.querySelectorAll('.ts-noprint, header#top, footer')].filter(e => getComputedStyle(e).display !== 'none').length")
            over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            page.pdf(path='/root/ts-jobs/shots/%s_print.pdf' % name) if False else None
            print('print     %-40s %s' % (path[:40], 'ok' if not hidden and over <= 0 else 'visible-chrome=%d overflow=%d' % (hidden, over)), flush=True)
            page.emulate_media(media='screen')
    b.close()
