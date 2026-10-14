#!/usr/bin/env python3
"""clin7 over HTTP against a served CLONE: the clinic office (role admin) and its therapist (clinician).
The office sees «دفتر مرکز», a short menu («مراجعان», no groups/import/exports/campaigns), one visible «چه بفرستید»
list and «مشاور: …» on «دعوت تازه»; its invitation lands with the therapist, who finds the client in «مراجعان»; the
dashboard has no funnel or workload tables. No SMS leaves the clone (clone guard).
    ts_http_clin7.py DB PORT"""
import importlib.util, os, re, sys

DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, summary, shell, ensure_user = lib.Client, lib.check, lib.summary, lib.shell, lib.ensure_user
TS = 'talentsearch.ir'
L = {n: 'ts.clin7.%s.http@example.invalid' % n for n in ('own', 'off', 'doc')}
pw = {u: ensure_user(u) for u in L.values()}

out = shell(r"""
L = %r
assert env.cr.dbname.startswith('eot_ts')
U, W, M = env['res.users'].sudo(), env['ts.workspace'].sudo(), env['ts.workspace.member'].sudo()
u = {k: U.search([('login', '=', v)], limit=1) for k, v in L.items()}
for m in M.search([('user_id', 'in', [u['off'].id, u['doc'].id])]):   # a re-run: earlier fixtures leave these two out
    m.with_context(ts_skip_last_owner=True).write({'active': False})
ws = W.ts_panel_create(u['own'], 'مرکز جریان clin7', 'clinic', terms=True)
owner = ws.member_ids.filtered(lambda m: m.role == 'owner')[:1]
off = M.create({'workspace_id': ws.id, 'user_id': u['off'].id, 'role': 'admin'})
doc = M.create({'workspace_id': ws.id, 'user_id': u['doc'].id, 'role': 'clinician'})
u['doc'].name = 'دکتر جریان clin7'
ws.ts_set_escalation(owner)
env.cr.commit()
print('WS', ws.id, 'DOC', doc.id)
""" % (L,))
m = re.search(r'WS (\d+) DOC (\d+)', out)
check('H00 fixture', m, out[-400:] if not m else '')
if m:
    ws_id, doc_id = int(m.group(1)), int(m.group(2))
    base = '/my/workspaces/%d' % ws_id
    off = Client(TS)
    check('H01 office signs in', off.login(L['off'], pw[L['off']]))
    st, _, page = off.req(base)
    check('H02 office dashboard 200', st == 200, st)
    check('H03 office label «دفتر مرکز»', 'دفتر مرکز' in page)
    check('H04 menu says «مراجعان»', 'مراجعان' in page)
    check('H05 no groups/import/exports in the clinic menu',
          not any(('%s/%s"' % (base, k)) in page for k in ('groups', 'import', 'exports', 'campaigns')))
    check('H06 no funnel or workload tables', 'tsp-d-fun' not in page and 'tsp-d-wl' not in page)
    st, _, page = off.req(base + '/invites/new')
    check('H07 invite page 200', st == 200, st)
    check('H08 visible «چه بفرستید» list', 'id="tso-pick"' in page and 'name="pick"' in page)
    check('H09 one therapist shown as a line', 'id="tso-therapist"' in page and 'دکتر جریان clin7' in page)
    opt = re.search(r'<option value="([bi]\d+)"', page)
    check('H10 the list has items', opt)
    st, loc, body = off.req(base + '/invites/new', {
        'csrf_token': off.csrf(page), 'one': '1', 'attest': '1', 'new_name': 'مراجع جریان clin7',
        'new_phone': '09126657001', 'pick': opt.group(1) if opt else '', 'therapist_id': str(doc_id)})
    check('H11 «فرستادن» creates the invitation', st in (302, 303) and '/invites/' in loc, '%s %s %s' % (st, loc, body[:300]))
    res = shell(r"""
c = env['ts.panel.client'].sudo().search([('workspace_id', '=', %d), ('name', '=', 'مراجع جریان clin7')], limit=1)
print('RESP', c.responsible_id.id or 0)
""" % ws_id)
    check('H12 the client belongs to the therapist', ('RESP %d' % doc_id) in res, res[-200:])
    doc = Client(TS)
    check('H13 therapist signs in', doc.login(L['doc'], pw[L['doc']]))
    st, _, page = doc.req(base + '/clients')
    check('H14 therapist sees the client', st == 200 and 'مراجع جریان clin7' in page, st)
    st, _, page = doc.req(base + '/invites/new')
    check('H15 therapist sending: no therapist picker', st == 200 and 'id="tso-therapist"' not in page, st)
summary()
