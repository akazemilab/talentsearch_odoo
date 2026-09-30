#!/usr/bin/env python3
"""Responsible-specialist UI over HTTP against a served CLONE:  ts_http_resp.py DB PORT
Run after ts_http_edu.py (uses its institute workspace and imported result)."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell
TS = 'talentsearch.ir'
OWN, CA, CB = ('ts.resp.%s.http@example.invalid' % n for n in ('owner', 'ca', 'cb'))
pw = {u: ensure_user(u) for u in (OWN, CA, CB)}
out = shell(r'''
ws = env['ts.workspace'].search([('name', '=', 'مؤسسهٔ آزمون HTTP')], limit=1)
assert ws and ws.state in ('pilot', 'active'), 'run ts_http_edu.py first'
M = env['ts.workspace.member']
def mem(login, role):
    u = env['res.users'].search([('login', '=', login)])
    return M.search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or M.create({'workspace_id': ws.id, 'user_id': u.id, 'role': role})
mo, ma, mb = mem(%r, 'owner'), mem(%r, 'counselor'), mem(%r, 'counselor')
at = env['ts.attempt'].search([('source_ref', '=', 'edu:http:1')], limit=1)
at.write({'responsible_id': False})
env.cr.commit()
print('IDS', ws.id, at.id, mb.id, ma.id)
''' % (OWN, CA, CB))
ws_id, at_id, mb_id, ma_id = re.search(r'IDS (\d+) (\d+) (\d+) (\d+)', out).groups()
NAME = 'کاندیدای آزمون HTTP'
n0 = int(re.search(r'EV (\d+)', shell("print('EV', env['ts.audit.event'].search_count([('event_type', '=', 'attempt.responsible_change'), ('res_id', '=', %s)]))" % at_id)).group(1))

o = Client(TS); assert o.login(OWN, pw[OWN])
st, _, page = o.req('/my/workspaces/%s' % ws_id)
check('owner sees the responsible dropdown on imported rows', st == 200 and 'name="responsible_id"' in page and 'تخصیص‌نشده' in page)
check('owner sees the unassigned filter tab', '?resp=none' in page)
st, _, page = o.req('/my/workspaces/%s?resp=none' % ws_id)
check('unassigned filter lists the import', st == 200 and NAME in page)
st, loc, _ = o.req('/my/workspaces/%s/p/%s/responsible' % (ws_id, at_id), {'csrf_token': o.csrf(page), 'responsible_id': mb_id})
check('owner assigns the import to counselor B', st in (302, 303) and 'error' not in (loc or ''), '%s %s' % (st, loc))
st, _, page = o.req('/my/workspaces/%s?resp=none' % ws_id)
check('assigned import leaves the unassigned filter', NAME not in page)

b = Client(TS); assert b.login(CB, pw[CB])
st, _, page = b.req('/my/workspaces/%s' % ws_id)
check('responsible counselor sees it, without an assign control', st == 200 and NAME in page and 'name="responsible_id"' not in page)
st, _, _ = b.req('/my/workspaces/%s/p/%s' % (ws_id, at_id))
check('responsible counselor opens the report', st == 200, str(st))
a = Client(TS); assert a.login(CA, pw[CA])
st, _, page = a.req('/my/workspaces/%s' % ws_id)
check('other counselor does not see it in the list', st == 200 and NAME not in page)
st, _, _ = a.req('/my/workspaces/%s/p/%s' % (ws_id, at_id))
check('other counselor gets 404 on the report', st == 404, str(st))
st, _, _ = a.req('/my/workspaces/%s/p/%s/responsible' % (ws_id, at_id), {'csrf_token': a.csrf(page), 'responsible_id': ma_id})
check('counselor cannot assign (404)', st == 404, str(st))
st, _, page = o.req('/my/workspaces/%s' % ws_id)
st, loc, _ = o.req('/my/workspaces/%s/p/%s/responsible' % (ws_id, at_id), {'csrf_token': o.csrf(page), 'responsible_id': ''})
st, _, page = a.req('/my/workspaces/%s' % ws_id)
check('owner clears it: back to the unassigned queue, counselor sees it again', NAME in page)
ev = shell("print('EV', env['ts.audit.event'].search_count([('event_type', '=', 'attempt.responsible_change'), ('res_id', '=', %s)]))" % at_id)
n1 = int(re.search(r'EV (\d+)', ev).group(1))
check('both changes audited', n1 - n0 == 2, '%d -> %d' % (n0, n1))
summary()
