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
Exit 1 if any E, else 0. Reference for "new" views: the commit in /root/ts-jobs/LIVE_COMMIT
(written by `ts ship`), else origin/main.
"""
import ast, glob, os, re, subprocess, sys

from lxml import etree

REPO = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
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

for e in errors:
    print('E ' + e)
for w in warns:
    print('W ' + w)
print(f'CHECK {"FAILED" if errors else "OK"}: {len(errors)} error(s), {len(warns)} warning(s)')
sys.exit(1 if errors else 0)
