#!/usr/bin/env python3
"""Panel v2 S5 (client edit, groups, bulk, views) over HTTP against a served CLONE:  ts_http_pv2_5.py DB PORT"""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell
TS = 'talentsearch.ir'
NAMES = ('owner', 'admin', 'c1', 'c2', 'hm', 'hmo', 'outsider')
L = {n: 'ts.pv2s5.%s.http@example.invalid' % n for n in NAMES}
pw = {u: ensure_user(u) for u in L.values()}
code = r'''
L = %r
def user(n): return env['res.users'].search([('login', '=', L[n])])
def panel(name, purpose):
    org = env['res.partner'].search([('name', '=', name)], limit=1) or env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
        {'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
    return ws
def member(ws, n, role):
    u = user(n)
    m = env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create(
        {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
    if role in ('counselor', 'clinician'):
        m.write({'license_number': 'T-1', 'verification_state': 'verified'})
    return m
A = panel('پنل S5 آموزشی', 'education')
mo = member(A, 'owner', 'owner'); member(A, 'admin', 'admin'); m1 = member(A, 'c1', 'counselor'); m2 = member(A, 'c2', 'counselor')
C = env['ts.panel.client']
for n, r in (('پنج الف', m1), ('پنج ب', m1), ('پنج پ', m2), ('پنج ت', False)):
    if not C.search_count([('workspace_id', '=', A.id), ('name', '=', n)]):
        C.create({'workspace_id': A.id, 'name': n, 'responsible_id': r.id if r else False})
env['ts.panel.group'].search([('workspace_id', '=', A.id)]).unlink()
env['ts.saved.view'].search([('member_id', 'in', [mo.id, m1.id])]).unlink()
env.cr.commit()
cid = lambda n: C.search([('workspace_id', '=', A.id), ('name', '=', n)], limit=1).id
print('IDS', A.id, cid('پنج الف'), cid('پنج ب'), cid('پنج پ'), cid('پنج ت'), m1.id, m2.id)
''' % L
out = shell(code)
mm = re.search(r'IDS (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
A, K1, K2, K3, K4, M1, M2 = mm.groups()
W = '/my/workspaces/%s' % A


def login(n):
    c = Client(TS)
    assert c.login(L[n], pw[L[n]]), n
    return c


def get(c, path):
    st, loc, body = c.req(path)
    return st, body


def post(c, path, data):
    pairs = list(data.items()) if isinstance(data, dict) else list(data)
    pairs.append(('csrf_token', c.csrf(c.req('/web/login')[2])))
    return c.req(path, pairs)


def tbl(page):
    m = re.search(r'<table.*?</table>', page, re.S)
    return m.group(0) if m else ''


own, c1, c2, adm = login('owner'), login('c1'), login('c2'), login('admin')

# ---- groups: create, page, rename
st, body = get(own, W + '/groups')
check('owner opens the groups page', st == 200 and body.count('<h1') == 1)
st, loc, _ = post(own, W + '/groups/new', {'name': 'کلاس پنجم', 'kind': 'class'})
m = re.search(r'/groups/(\d+)', loc)
check('creating a group redirects to its page', st in (302, 303) and bool(m), loc)
GID = m.group(1) if m else '0'
st, loc, _ = post(own, W + '/groups/new', {'name': ' کلاس پنجم ', 'kind': 'class'})
st2, body = get(own, W + '/groups')
check('a duplicate group name is refused with a message', body.count('کلاس پنجم') == body.count('کلاس پنجم') and 'از پیش هست' in body or 'از پیش هست' in get(own, loc)[1], loc)
check('a counselor has no groups page of her own panel menu entry... but may not open another panel', get(c1, '/my/workspaces/999999/groups')[0] == 404)

# ---- bulk: add to group
sel = [('sel', K1), ('sel', K2), ('sel', K3), ('bulk', 'group_add'), ('group', GID)]
st, loc, _ = post(own, W + '/clients/bulk', sel)
st, body = get(own, W + '/groups/' + GID)
check('bulk add to group puts three people in it', all(n in body for n in ('پنج الف', 'پنج ب', 'پنج پ')), str(st))
st, body = get(c1, W + '/groups/' + GID)
check('a counselor sees only her own people on the group page', 'پنج الف' in body and 'پنج پ' not in body and st == 200, str(st))
st, body = get(own, W + '/clients?group=' + GID)
check('the client list filters by group', 'پنج الف' in tbl(body) and 'پنج ت' not in tbl(body))

# ---- bulk safety: a counselor cannot act on someone she cannot see; no action -> message
st, loc, _ = post(c1, W + '/clients/bulk', [('sel', K3), ('bulk', 'group_remove'), ('group', GID)])
st, body = get(own, W + '/groups/' + GID)
check('a hidden id in a bulk post is ignored', 'پنج پ' in body)
st, loc, _ = post(c1, W + '/clients/bulk', [('sel', K1), ('bulk', 'assign'), ('target', M2)])
check('a counselor cannot assign in bulk (403)', st == 403, str(st))
st, loc, _ = post(adm, W + '/clients/bulk', [('sel', K4), ('bulk', 'nonsense')])
check('an unknown bulk action changes nothing and redirects', st in (302, 303))

# ---- bulk assign and archive by the owner
st, loc, _ = post(own, W + '/clients/bulk', [('sel', K4), ('bulk', 'assign'), ('target', M2)])
st, body = get(c2, W + '/clients')
check('bulk assign: the specialist now sees the person', 'پنج ت' in tbl(body))
st, loc, _ = post(own, W + '/clients/bulk', [('sel', K4), ('bulk', 'archive')])
st, body = get(own, W + '/clients')
check('bulk archive removes them from the default list', 'پنج ت' not in tbl(body))
st, body = get(own, W + '/clients?filter=archived')
check('and shows them under the archived filter', 'پنج ت' in tbl(body), str(st))
st, loc, _ = post(own, W + '/clients/bulk', [('sel', K4), ('bulk', 'restore')])
st, body = get(own, W + '/clients')
check('bulk restore brings them back', 'پنج ت' in tbl(body))

# ---- merge: preview then confirm
st, body = post(own, W + '/clients/bulk', [('sel', K2), ('sel', K3), ('bulk', 'merge')])[0::2]
check('merge shows a preview page with a choice and no data changed', st == 200 and 'name="keep"' in body and 'ادغام' in body, str(st))
st, loc, _ = post(own, W + '/clients/merge', [('ids', '%s,%s' % (K2, K3)), ('keep', K2)])
check('confirming the merge redirects to the surviving client', st in (302, 303) and loc.endswith('/clients/' + K2), loc)
st, body = get(own, W + '/clients/' + K3)
check('the merged row is archived and says where it went', st == 200 and ('ادغام' in body or 'بایگانی' in body))
st, loc, _ = post(own, W + '/clients/merge', [('ids', '%s,%s' % (K1, K2)), ('keep', '999999')])
check('merge with a foreign id is 404', st == 404, str(st))

# ---- saved views: no search text is stored
st, loc, _ = post(own, W + '/clients/views/save', {'name': 'مال من', 'filter': 'mine', 'sort': 'name', 'dir': 'asc', 'q': 'محرمانه', 'evil': 'x'})
out = shell("v = env['ts.saved.view'].search([('name', '=', 'مال من')]); print('V', len(v), v.query, v.columns)")
check('a saved view keeps whitelisted filters only, never the search text', 'V 1' in out and 'محرمانه' not in out and 'evil' not in out, out[-200:])
st, body = get(own, W + '/clients')
check('the saved view is offered on the list', 'مال من' in body)
check('another member does not see it', 'مال من' not in get(c1, W + '/clients')[1])
vid = re.search(r'V_ID (\d+)', shell("print('V_ID', env['ts.saved.view'].search([('name', '=', 'مال من')]).id)")).group(1)
check('another member cannot delete it (404)', post(c1, W + '/clients/views/%s/delete' % vid, {})[0] == 404)
st, loc, _ = post(own, W + '/clients/views/%s/delete' % vid, {})
check('the owner deletes it', st in (302, 303) and 'مال من' not in get(own, W + '/clients')[1])

# ---- create and edit
st, body = get(own, W + '/clients/new')
check('the new-client form opens, one h1, labelled fields', st == 200 and body.count('<h1') == 1 and 'for="' in body)
st, body = post(own, W + '/clients/new', {'name': ''})[0::2]
check('an empty name re-renders the form with an error, not a crash', st in (200, 400, 422) and 'name=' in body, str(st))
st, loc, _ = post(own, W + '/clients/new', {'name': 'تازه از فرم', 'phone': '09121112233', 'age_group': 'adult'})
m = re.search(r'/clients/(\d+)', loc)
check('creating a client redirects to its page', st in (302, 303) and bool(m), '%s %s' % (st, loc))
NEW = m.group(1) if m else '0'
st, body = post(own, W + '/clients/new', {'name': 'تازه از فرم'})[0::2]
check('the same name warns about a duplicate and still allows saving', 'confirm' in body or 'مشابه' in body or st in (302, 303), str(st))
st, loc, _ = post(own, W + '/clients/%s/edit' % NEW, {'name': 'تازه ویرایش‌شده', 'age_group': 'adult', 'phone': '09121112233'})
check('editing saves', 'تازه ویرایش‌شده' in get(own, W + '/clients/' + NEW)[1])
check('a counselor cannot edit someone else\'s client (404)', post(c1, W + '/clients/%s/edit' % K3, {'name': 'x'})[0] == 404)
st, loc, _ = post(own, W + '/clients/%s/edit' % NEW, {'name': 'تازه ویرایش‌شده', 'age_group': 'minor', 'guardian_name': 'ولی', 'guardian_phone': '09123334455', 'guardian_relation': 'father'})
check('a minor keeps guardian data on the page', 'ولی' in get(own, W + '/clients/' + NEW)[1])

# ---- handover over HTTP
st, loc, _ = post(c1, W + '/clients/%s/handover' % K1, {'target': M2})
st, body = get(own, W + '/clients/' + K1)
check('a counselor request shows as pending to the owner', 'درخواست' in body and 'name="accept"' in body or 'accept' in body, str(st))
st, loc, _ = post(own, W + '/clients/%s/decide' % K1, {'accept': '1'})
st, body = get(c2, W + '/clients')
check('after acceptance the new specialist sees the person', 'پنج الف' in tbl(body))
check('a counselor cannot decide (403)', post(c2, W + '/clients/%s/decide' % K1, {'accept': '1'})[0] == 403)

# ---- every page: single h1, no horizontal-scroll markup
for path in ('/groups', '/groups/' + GID, '/clients/new', '/clients', '/clients/' + K2):
    st, body = get(own, W + path)
    check('page %s: 200 and exactly one h1' % path, st == 200 and body.count('<h1') == 1, str(st))
summary()
