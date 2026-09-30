#!/usr/bin/env python3
"""Institute (education) view over HTTP against a served CLONE:  ts_http_edu.py DB PORT
counselor sees imported results (no answers), audit is written, others get 404."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, path_of, summary, shell = lib.Client, lib.check, lib.ensure_user, lib.path_of, lib.summary, lib.shell
TS = 'talentsearch.ir'
CNS, OTHER = 'ts.edu.counselor.http@example.invalid', 'ts.edu.other.http@example.invalid'
cns_pw, other_pw = ensure_user(CNS), ensure_user(OTHER)
out = shell(r'''
inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')])
v = inst.current_version_id
org = env['res.partner'].search([('name', '=', 'مؤسسهٔ آزمون HTTP')], limit=1) or env['res.partner'].create({'name': 'مؤسسهٔ آزمون HTTP', 'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'مؤسسهٔ آزمون HTTP', 'purpose': 'education', 'partner_id': org.id})
ws.write({'approved_on': '2026-01-01 00:00:00'}); ws.state = 'pilot'
u = env['res.users'].search([('login', '=', %r)])
env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)]) or env['ts.workspace.member'].create({'workspace_id': ws.id, 'user_id': u.id, 'role': 'counselor'})
org2 = env['res.partner'].search([('name', '=', 'مؤسسهٔ دیگر')], limit=1) or env['res.partner'].create({'name': 'مؤسسهٔ دیگر', 'is_company': True})
ws2 = env['ts.workspace'].search([('partner_id', '=', org2.id)], limit=1) or env['ts.workspace'].create({'name': 'مؤسسهٔ دیگر HTTP', 'purpose': 'education', 'partner_id': org2.id})
ws2.write({'approved_on': '2026-01-01 00:00:00'}); ws2.state = 'pilot'
def mk(name, ref, wsid):
    ex = env['ts.attempt'].search([('source_ref', '=', ref)])
    if ex:
        return ex.id
    person = env['res.partner'].create({'name': name})
    tmp = env['res.users'].with_context(no_reset_password=True).create({'name': name, 'login': ref + '@example.invalid', 'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
    att = env['ts.attempt'].create({'user_id': tmp.id, 'instrument_id': inst.id, 'version_id': v.id}); att.give_consent()
    items = att.active_items()
    for n, label in enumerate(['ریاضی', 'هنر', 'ورزش', 'زبان']):
        f = att.ts_add_field(label)
        for i, it in enumerate(items):
            att.ts_save_cell(f, it.id, (i * (n %% 3 + 1) + 2 * n + i // 5) %% 5 + 1)
        att.ts_finish_field(f)
    assert att.action_submit()
    att.write({'source': 'import', 'source_ref': ref, 'user_id': False, 'person_id': person.id, 'released': False, 'workspace_id': wsid})
    return att.id
a1 = mk('کاندیدای آزمون HTTP', 'edu:http:1', ws.id)
a2 = mk('کاندیدای مؤسسهٔ دیگر', 'edu:http:2', ws2.id)
env.cr.commit()
print('IDS', ws.id, a1, a2)
''' % CNS)
mm = re.search(r'IDS (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
ws_id, a1, a2 = mm.groups()

c = Client(TS)
check('counselor login', c.login(CNS, cns_pw))
st, _, page = c.req('/my/workspaces/%s' % ws_id)
check('workspace page lists the imported result', st == 200 and 'کاندیدای آزمون HTTP' in page and 'id="ts-imports"' in page, str(st))
check('imported list says not published to participant', 'منتشر نشده' in page)
check('education workspace states the answers-never rule', 'پاسخ‌های خام هرگز' in page)
check('counselor sees the invite form with only the talent inventory', 'ساخت پیوند دعوت' in page and len(re.findall(r'<option value="(\d+)">', page)) == 1)
st, _, page = c.req('/my/workspaces/%s?src=invite' % ws_id)
check('web-invites filter hides imports', st == 200 and 'کاندیدای آزمون HTTP' not in page)
st, _, page = c.req('/my/workspaces/%s/p/%s' % (ws_id, a1))
check('counselor opens the imported report', st == 200 and 'tt-cobrand' in page and 'مؤسسهٔ آزمون HTTP' in page and 'tt-compare' in page, str(st))
check('org view: fields side by side with 4 fields', page.count('tt-cmp__row') == 6 and all(x in page for x in ('ریاضی', 'هنر', 'ورزش', 'زبان')))
art = page[page.index('<article'):page.index('</article>')]
check('org view: no raw answers, no personal-area links in the report', 'tt-raw' not in art and 'پاسخ‌های من' not in art and '/my/assessments' not in art)
check('org view: print button kept', 'ts-js-print' in page)
check('other institute attempt is 404', c.req('/my/workspaces/%s/p/%s' % (ws_id, a2))[0] == 404)
check('unknown attempt is 404', c.req('/my/workspaces/%s/p/99999999' % ws_id)[0] == 404)
o = Client(TS)
o.login(OTHER, other_pw)
check('non-member gets 404 on the workspace and on the report',
      o.req('/my/workspaces/%s' % ws_id)[0] == 404 and o.req('/my/workspaces/%s/p/%s' % (ws_id, a1))[0] == 404)
check('anonymous is sent to login', Client(TS).req('/my/workspaces/%s/p/%s' % (ws_id, a1))[0] in (302, 303))
check('participant-side release is not offered to the institute', c.req('/my/workspaces/%s/p/%s/release' % (ws_id, a1))[0] in (404, 405))
n = shell("print('AUD', env['ts.audit.event'].search_count([('event_type','=','attempt.result_view'),('res_id','=',%s)]))" % a1)
check('result views are audited', re.search(r'AUD (\d+)', n) and int(re.search(r'AUD (\d+)', n).group(1)) >= 1, n.strip()[-40:])
e = Client('www.eot.ir')
e.login(CNS, cns_pw)
check('eot.ir has no institute route', e.req('/my/workspaces/%s/p/%s' % (ws_id, a1))[0] == 404)
summary()
