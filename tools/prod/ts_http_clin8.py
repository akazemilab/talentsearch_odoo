#!/usr/bin/env python3
"""clin8 over HTTP against a served CLONE: the clinic's short flat menus per role, the fixed «فرستادن آزمون», «خدمات»
(batteries, then tests by category; prices for the office and owner only; «فرستادن به مراجع» preselects the item),
«مراجعان» with the latest test of each client, settings links, and the talent inventory sent from a clinic and read
by the therapist. Other panel kinds keep their menus. No SMS leaves the clone (clone guard).
    ts_http_clin8.py DB PORT"""
import importlib.util, json, os, re, sys

DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, summary, shell, ensure_user = lib.Client, lib.check, lib.summary, lib.shell, lib.ensure_user
TS = 'talentsearch.ir'
L = {n: 'ts.clin8.%s.http@example.invalid' % n for n in ('own', 'off', 'doc', 'cli', 'sch')}
pw = {u: ensure_user(u) for u in L.values()}

out = shell(r"""
import json
L = %r
assert env.cr.dbname.startswith('eot_ts')
U, W, M = env['res.users'].sudo(), env['ts.workspace'].sudo(), env['ts.workspace.member'].sudo()
Inst, Bat = env['ts.instrument'].sudo(), env['ts.battery'].sudo()
u = {k: U.search([('login', '=', v)], limit=1) for k, v in L.items()}
for m in M.search([('user_id', 'in', [u['off'].id, u['doc'].id])]):
    m.write({'active': False})
# a re-run on the same clone (screenshot rounds): earlier fixture panels of these users count against the 24-hour panel
# limit (counted on owner memberships), so those are aged by two days first (clone only, asserted above)
env.cr.execute("UPDATE ts_workspace_member SET create_date = create_date - interval '2 days' WHERE user_id IN %%s",
               [tuple(x.id for x in u.values())])
env.invalidate_all()
ws = W.ts_panel_create(u['own'], 'مرکز جریان clin8', 'clinic', terms=True)
owner = ws.member_ids.filtered(lambda m: m.role == 'owner')[:1]
off = M.create({'workspace_id': ws.id, 'user_id': u['off'].id, 'role': 'admin'})
doc = M.create({'workspace_id': ws.id, 'user_id': u['doc'].id, 'role': 'clinician'})
talent = Inst.search([('code', '=', 'TALENT-INV-15')], limit=1)
adult = Inst.search([('state', '=', 'published'), ('code', 'like', 'inventory_0'), ('audience', '=', 'adult')], limit=1)
intake = Bat.search([('code', '=', 'BAT-INTAKE-1')], limit=1)
ws.write({'catalog_mode': 'granted', 'catalog_instrument_ids': [(6, 0, (talent | adult).ids)],
          'catalog_battery_ids': [(6, 0, intake.ids)]})
ws.ts_set_escalation(owner)
A = env['ts.assignment'].sudo()
a = A.with_user(u['off']).sudo().create({'workspace_id': ws.id, 'instrument_id': talent.id, 'invitee_name': 'مراجع جریان clin8'})
at = a.action_accept(u['cli'], share=True).sudo()
at.give_consent(research=False, role='self')
items = at.active_items()
for n, label in enumerate(['ریاضی', 'هنر']):
    f = at.ts_add_field(label)
    for i, it in enumerate(items):
        at.ts_save_cell(f, it.id, (i * (n %% 3 + 1) + 2 * n + i // 5) %% 5 + 1)
    at.ts_finish_field(f)
ok = at.action_submit()
a.invalidate_recordset()
sch = W.ts_panel_create(u['sch'], 'مدرسه جریان clin8', 'school', terms=True)
env.cr.commit()
print('FIX ' + json.dumps({'ws': ws.id, 'sch': sch.id, 'talent': talent.id, 'title': talent.ts_title(), 'cat': talent.category,
      'client': a.client_id.id, 'resp': a.client_id.responsible_id.id, 'doc': doc.id, 'at': at.id, 'state': a.state, 'ok': bool(ok)}))
""" % (L,))
m = re.search(r'FIX (\{.*\})', out)
check('H00 fixture (clinic panel, office, therapist, talent inventory sent by the office and finished)', m, out[-600:] if not m else '')
if m:
    F = json.loads(m.group(1))
    W = '/my/workspaces/%d' % F['ws']

    def menu(page):
        return re.findall(r'class="tsp-nav__item"[^>]*aria-label="([^"]+)"', page)

    check('H01 the talent inventory went to the therapist and is done', F['resp'] == F['doc'] and F['state'] == 'done', F)
    off, doc, own = Client(TS), Client(TS), Client(TS)
    check('H02 sign-ins', off.login(L['off'], pw[L['off']]) and doc.login(L['doc'], pw[L['doc']]) and own.login(L['own'], pw[L['own']]))
    st, _, page = off.req(W)
    check('H03 office menu: پیشخوان، خدمات، مراجعان، اعتبار (clin9: «خدمات» right after «پیشخوان»)', menu(page) == ['پیشخوان', 'خدمات', 'مراجعان', 'اعتبار'], menu(page))
    check('H04 fixed «فرستادن آزمون» for the office, no group headings', 'id="tsp-send"' in page and 'tsp-nav__group' not in page)
    st, _, page = doc.req(W)
    check('H05 therapist menu: پیشخوان، خدمات، مراجعان، گزارش‌ها', menu(page) == ['پیشخوان', 'خدمات', 'مراجعان', 'گزارش‌ها'], menu(page))
    st, _, page = own.req(W)
    check('H06 owner menu ends with تنظیمات, no members/audit/help items',
          menu(page)[-1:] == ['تنظیمات'] and not {'اعضا و نقش‌ها', 'دفتر ممیزی', 'راهنما'} & set(menu(page)), menu(page))
    st, _, page = own.req(W + '/settings')
    check('H07 settings links to members and audit', 'id="tsp-setlinks"' in page and W + '/members' in page and W + '/audit' in page)
    st, _, page = off.req(W + '/services')
    check('H08 «خدمات» 200 for the office', st == 200, st)
    check('H09 batteries first, then the talent inventory under its category', 'id="tss-bats"' in page
          and F['cat'] in page and F['title'] in page and page.index('tss-bats') < page.index('tss-i%d' % F['talent']))
    check('H10 the office sees prices', 'تومان' in page)
    check('H11 «فرستادن به مراجع» preselects the item', '/invites/new?pick=i%d' % F['talent'] in page)
    st, _, page = doc.req(W + '/services')
    check('H12 the therapist sees the catalog without prices', st == 200 and F['title'] in page and 'تومان' not in page, st)
    st, _, page = off.req(W + '/invites/new?pick=i%d' % F['talent'])
    check('H13 the invitation opens with that item chosen', st == 200 and re.search(
        r'<option value="i%d" selected' % F['talent'], page), st)
    st, _, page = off.req(W + '/clients')
    check('H14 «مراجعان» shows the latest test and its status, with «همهٔ دعوت‌ها»', st == 200 and 'آخرین آزمون' in page
          and F['title'] in page and 'id="tsp-all-invites"' in page and 'نماهای ذخیره' not in page, st)
    st, _, page = off.req(W + '/invites')
    check('H15 the invitation list still opens (from «مراجعان»), lighting «مراجعان»', st == 200
          and re.search(r'aria-current="page" data-key="clients"', page), st)
    st, _, page = doc.req(W + '/clients/%d/r/%d' % (F['client'], F['at']))
    check('H16 the therapist reads the talent-inventory report at the counselor level', st == 200
          and 'دسترسی ندارید' not in page and 'فقط وضعیت' not in page and ('گزارش ویژهٔ مشاور' in page or 'گزارش در سطح مشاور' in page), st)
    st, _, page = off.req(W + '/clients/%d/r/%d' % (F['client'], F['at']))
    check('H17 the office sees the status only, never the report', st in (403, 404) or 'دسترسی ندارید' in page
          or ('فقط وضعیت' in page and 'گزارش ویژهٔ مشاور' not in page), st)
    sch = Client(TS)
    sch.login(L['sch'], pw[L['sch']])
    st, _, page = sch.req('/my/workspaces/%d' % F['sch'])
    check('H18 a school panel keeps its menu (no «خدمات», headings stay)', st == 200 and 'خدمات' not in menu(page)
          and 'tsp-nav__group' in page, menu(page))
    check('H19 «خدمات» is a clinic page only', sch.req('/my/workspaces/%d/services' % F['sch'])[0] == 404)
summary()
