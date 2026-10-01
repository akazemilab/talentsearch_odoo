#!/usr/bin/env python3
"""ts_check.py [REPO] - preflight before any rehearsal (runs on the tools VPS, ~2 s, no prod access).

Catches, before a 25-minute rehearsal, the failures that cost whole cycles on 2026-09-30:
  E py       every .py under addons/ and tools/ compiles
  E xml      every addons/**/*.xml parses
  E manifest every file listed in a manifest's data exists
  E qweb     t-elif / t-else directly follows a sibling with t-if / t-elif (else the page 500s)
  E view     a NEW ir.ui.view / template in a module that does not depend on `website`
             (install fails on eot_main: website makes ir_ui_view.visibility NOT NULL)
  W phone    the same test mobile number used in two test files (fixtures collide)
  W pycache  __pycache__ files tracked by git
  Panel v2 rules (ts_panel only):
  W audit    an audit `.log(` call passes a keyword that can carry personal data (name, phone, ...); warning until S1
  E scope    `sudo().search/browse/...` in ts_panel/controllers (outside base.py) without `workspace_id` in the
             domain (browse: add a `# ts-scope-ok` comment on the line when the id was already scoped)
  E words    a forbidden claim in a ts_panel template (08_design_system.md section 6)
  `ts_check.py --selftest` proves the three rules fire on a sample bad module.
Exit 1 if any E, else 0. Reference for "new" views: the commit in /root/ts-jobs/LIVE_COMMIT
(written by `ts ship`), else origin/main.
"""
import ast, glob, os, re, subprocess, sys

from lxml import etree

SELFTEST = '--selftest' in sys.argv
argv = [a for a in sys.argv[1:] if a != '--selftest']
if SELFTEST:   # prove the Panel v2 rules fire on a sample bad module, then exit
    import tempfile
    d = tempfile.mkdtemp()
    os.makedirs(f'{d}/addons/ts_panel/controllers'); os.makedirs(f'{d}/addons/ts_panel/views')
    open(f'{d}/addons/ts_panel/__manifest__.py', 'w').write("{'name': 'x', 'depends': [], 'data': []}")
    open(f'{d}/addons/ts_panel/controllers/main.py', 'w').write(
        "def f(request, env, ws):\n    env['ts.x'].sudo().search([('id', '=', 1)])\n    env['ts.x'].sudo().browse(3)\n"
        "    env['ts.audit.event'].log('x.y', None, phone='0912')\n"
        "    env['ts.x'].sudo().search([('workspace_id', '=', ws.id)])\n")
    open(f'{d}/addons/ts_panel/views/v.xml', 'w', encoding='utf-8').write('<odoo><p>تضمین قبولی</p></odoo>')
    r = subprocess.run([sys.executable, __file__, d], capture_output=True, text=True).stdout
    want = ['E scope addons/ts_panel/controllers/main.py:2', 'E scope addons/ts_panel/controllers/main.py:3',
            'W audit addons/ts_panel/controllers/main.py:4', 'E words addons/ts_panel/views/v.xml']
    miss = [w for w in want if w not in r]
    extra = 'E scope addons/ts_panel/controllers/main.py:5' in r
    print('SELFTEST ' + ('OK' if not miss and not extra else 'FAILED missing=%s extra_flag_on_scoped_search=%s' % (miss, extra)))
    sys.exit(0 if not miss and not extra else 1)
REPO = os.path.abspath(argv[0] if argv else os.getcwd())
ADDONS = os.path.join(REPO, 'addons')
errors, warns = [], []
FA = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')


def rel(p):
    return os.path.relpath(p, REPO)


def git(*args):
    r = subprocess.run(['git', '-C', REPO] + list(args), capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


# ---------------------------------------------------------------- py
for p in glob.glob(f'{REPO}/addons/**/*.py', recursive=True) + glob.glob(f'{REPO}/tools/**/*.py', recursive=True):
    if '__pycache__' in p:
        continue
    try:
        compile(open(p, encoding='utf-8').read(), p, 'exec')
    except SyntaxError as e:
        errors.append(f'py {rel(p)}:{e.lineno} {e.msg}')

# ---------------------------------------------------------------- manifests
manifests = {}
for mf in glob.glob(f'{ADDONS}/*/__manifest__.py'):
    mod = os.path.basename(os.path.dirname(mf))
    try:
        manifests[mod] = ast.literal_eval(open(mf, encoding='utf-8').read())
    except Exception as e:
        errors.append(f'manifest {mod}: {e}')
        continue
    for f in manifests[mod].get('data', []):
        if not os.path.exists(os.path.join(ADDONS, mod, f)):
            errors.append(f'manifest {mod}: data file missing {f}')


def closure(mod, seen=None):
    seen = seen if seen is not None else set()
    for d in manifests.get(mod, {}).get('depends', []):
        if d not in seen:
            seen.add(d)
            closure(d, seen)
    return seen


# ---------------------------------------------------------------- xml + qweb
COND = ('t-if', 't-elif')


def prev_element(el):
    p = el.getprevious()
    while p is not None and not isinstance(p.tag, str):   # comments, PIs
        p = p.getprevious()
    return p


view_ids = {}   # module -> set of xml ids of views/templates
for p in glob.glob(f'{ADDONS}/**/*.xml', recursive=True):
    mod = rel(p).split(os.sep)[1]
    try:
        tree = etree.parse(p)
    except etree.XMLSyntaxError as e:
        errors.append(f'xml {rel(p)}: {e}')
        continue
    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        if 't-elif' in el.attrib or 't-else' in el.attrib:
            pr = prev_element(el)
            if pr is None or not any(a in pr.attrib for a in COND):
                errors.append(f'qweb {rel(p)}:{el.sourceline} <{el.tag} {"t-elif" if "t-elif" in el.attrib else "t-else"}> '
                              f'does not follow a t-if/t-elif sibling (got <{pr.tag if pr is not None else "nothing"}>)')
        if (el.tag == 'record' and el.get('model') == 'ir.ui.view') or el.tag == 'template':
            if el.get('id'):
                view_ids.setdefault(mod, set()).add(el.get('id'))

# ---------------------------------------------------------------- new views in non-website modules
ref = None
try:
    ref = open('/root/ts-jobs/LIVE_COMMIT').read().strip() or None
except OSError:
    pass
ref = ref or 'origin/main'
for mod, ids in view_ids.items():
    if mod not in manifests or 'website' in closure(mod) or mod == 'website':
        continue
    old = set()
    files = git('ls-tree', '-r', '--name-only', ref, f'addons/{mod}') or ''
    for f in files.split():
        if f.endswith('.xml'):
            src = git('show', f'{ref}:{f}') or ''
            old |= set(re.findall(r'<record[^>]*id="([^"]+)"[^>]*model="ir\.ui\.view"', src))
            old |= set(re.findall(r'<record[^>]*model="ir\.ui\.view"[^>]*id="([^"]+)"', src))
            old |= set(re.findall(r'<template[^>]*id="([^"]+)"', src))
    new = sorted(ids - old)
    if new:
        errors.append(f'view {mod} does not depend on website but adds views {new[:5]} (vs {ref[:12]}): move them to a module that depends on website')

# ---------------------------------------------------------------- test phone numbers
phones = {}
for p in glob.glob(f'{REPO}/tools/prod/*.py'):
    for num in set(re.findall(r'09\d{9}', open(p, encoding='utf-8').read().translate(FA))):
        phones.setdefault(num, set()).add(os.path.basename(p))
for num, files in sorted(phones.items()):
    if len(files) > 1:
        warns.append(f'phone {num[:4]}***{num[-3:]} used in {sorted(files)}')

# ---------------------------------------------------------------- tracked pycache
tracked = [l for l in (git('ls-files') or '').splitlines() if '__pycache__' in l]
if tracked:
    warns.append(f'pycache {len(tracked)} __pycache__ files tracked by git')


# ---------------------------------------------------------------- Panel v2 rules (ts_panel)
PANEL = os.path.join(ADDONS, 'ts_panel')
DENY_KW = {'name', 'phone', 'mobile', 'email', 'national_id', 'national_code', 'nid', 'query', 'search', 'q',
           'text', 'contact', 'invitee_name', 'partner_name', 'display_name'}
FORBIDDEN = ['رشتهٔ مناسب تو', 'احتمال قبولی', 'تضمین', 'رایگان برای همیشه', 'نظام روانشناسی و مشاوره']
SCOPED = ('search', 'search_count', 'search_read', 'read_group', 'browse')
if os.path.isdir(PANEL):
    for p in glob.glob(f'{PANEL}/**/*.py', recursive=True):
        try:
            src = open(p, encoding='utf-8').read()
            tree = ast.parse(src)
        except SyntaxError:
            continue
        is_ctrl = os.sep + 'controllers' + os.sep in p and os.path.basename(p) != 'base.py'
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == 'log':
                bad = sorted({k.arg for k in node.keywords if k.arg in DENY_KW})
                if bad:
                    warns.append(f'audit {rel(p)}:{node.lineno} .log() passes {bad}: no names, phones, emails or search text in audit detail')
            if is_ctrl and node.func.attr in SCOPED and isinstance(node.func.value, ast.Call) \
                    and isinstance(node.func.value.func, ast.Attribute) and node.func.value.func.attr == 'sudo':
                seg = ast.get_source_segment(src, node) or ''
                line = src.splitlines()[node.lineno - 1]
                if 'ts-scope-ok' in line:
                    continue
                if node.func.attr == 'browse' or 'workspace_id' not in seg:
                    errors.append(f'scope {rel(p)}:{node.lineno} sudo().{node.func.attr}() without workspace_id in the domain')
    for p in glob.glob(f'{PANEL}/**/*.xml', recursive=True):
        txt = open(p, encoding='utf-8').read()
        for w in FORBIDDEN:
            if w in txt:
                errors.append(f'words {rel(p)}: forbidden claim «{w}»')

for e in errors:
    print('E ' + e)
for w in warns:
    print('W ' + w)
print(f'CHECK {"FAILED" if errors else "OK"}: {len(errors)} error(s), {len(warns)} warning(s)')
sys.exit(1 if errors else 0)
