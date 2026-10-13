#!/usr/bin/env python3
"""Panel v2 S0 over HTTP against a served CLONE:  ts_http_pv2_0.py DB PORT
G30 revoke button on the TALENT-INV-15 report, G31 share-form wording, institute view has no revoke form."""
import importlib.util, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, summary, shell = lib.Client, lib.check, lib.ensure_user, lib.summary, lib.shell
TS = 'talentsearch.ir'
CNS, STU, SOLO = ('ts.pv2s0.%s.http@example.invalid' % n for n in ('counselor', 'student', 'solo'))
pw = {u: ensure_user(u) for u in (CNS, STU, SOLO)}
out = shell(r'''
inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')])
v = inst.current_version_id
org = env['res.partner'].search([('name', '=', 'مؤسسهٔ S0 HTTP')], limit=1) or env['res.partner'].create({'name': 'مؤسسهٔ S0 HTTP', 'is_company': True})
ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create({'name': 'مؤسسهٔ S0 HTTP', 'purpose': 'education', 'partner_id': org.id})
ws.state = 'active'
cu = env['res.users'].search([('login', '=', %r)])
stu = env['res.users'].search([('login', '=', %r)])
solo = env['res.users'].search([('login', '=', %r)])
env['ts.workspace.member'].search([('workspace_id', '=', ws.id), ('user_id', '=', cu.id)]) or env['ts.workspace.member'].create({'workspace_id': ws.id, 'user_id': cu.id, 'role': 'counselor'})
def fill(att):
    att.give_consent()
    for n, label in enumerate(['ریاضی', 'هنر', 'ورزش']):
        f = att.ts_add_field(label)
        for i, it in enumerate(att.active_items()):
            att.ts_save_cell(f, it.id, (i * (n %% 3 + 1) + 2 * n + i // 5) %% 5 + 1)
        att.ts_finish_field(f)
    assert att.action_submit()
    return att
Asg = env['ts.assignment']
a = Asg.search([('workspace_id', '=', ws.id), ('invitee_name', '=', 'دانش‌آموز S0 HTTP'), ('withdrawn', '=', False), ('declined', '=', False)], limit=1)
if a and a.share_level == 'none':
    a.withdrawn = True; a = Asg
if not a:
    a = Asg.sudo().create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'دانش‌آموز S0 HTTP', 'invited_by_id': cu.id})
    fill(a.action_accept(stu, share=True))
solo_att = env['ts.attempt'].search([('user_id', '=', solo.id), ('state', '=', 'done'), ('instrument_id', '=', inst.id)], limit=1)
if not solo_att:
    solo_att = fill(env['ts.attempt'].create({'user_id': solo.id, 'instrument_id': inst.id, 'version_id': v.id}))
env.cr.commit()
print('IDS', ws.id, a.attempt_id.id, solo_att.id)
''' % (CNS, STU, SOLO))
mm = re.search(r'IDS (\d+) (\d+) (\d+)', out)
assert mm, out[-1500:]
ws_id, att_id, solo_id = mm.groups()

s = Client(TS)
check('student login', s.login(STU, pw[STU]))
st, _, page = s.req('/my/assessments/%s' % att_id)
check('G30: shared TALENT-INV-15 report shows the status block and «قطع اشتراک‌گذاری»',
      st == 200 and 'id="ts-who-sees"' in page and 'قطع اشتراک‌گذاری' in page, str(st))   # UX audit G2 P3-9: one merged block
check('the block is outside the printed report (ts-noprint)', re.search(r'class="ts-doc__sec ts-noprint"\s+id="ts-who-sees"', page) is not None)
check('wording says profile report without raw answers', 'گزارش نیمرخ شما، بدون پاسخ‌های خام' in page and ('پاسخ‌های خام شما را هیچ پنلی نمی‌بیند' in page or 'پاسخ‌های خام تو را هیچ پنلی نمی‌بیند' in page))   # T7: «تو» for students
check('no duplicate «ارسال برای مشاورم» while shared', 'id="ts-share-counselor"' not in page)

c = Client(TS)
check('counselor login', c.login(CNS, pw[CNS]))
st, _, cpage = c.req('/my/workspaces/%s/p/%s' % (ws_id, att_id))
check('counselor opens the shared report', st == 200 and 'tt-cobrand' in cpage, str(st))
check('G30: the institute view never contains the revoke form or the share block',
      'قطع اشتراک‌گذاری' not in cpage and 'ts-who-sees' not in cpage and 'ts-share-counselor' not in cpage)

# UX audit G2 P5-2: «قطع اشتراک‌گذاری» on the report opens the confirmation page; its form posts the (unchanged) revoke
rv = re.search(r'href="(/my/sharing/\d+/revoke\?back=report)"', page)
st, _, cf = s.req(rv.group(1)) if rv else (0, '', '')
fm = re.search(r'<form[^>]*action="(/my/sharing/\d+/revoke)"[^>]*>(.*?)</form>', cf, re.S)
fields = {}
for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', fm.group(2) if fm else ''):
    nm, vl = re.search(r'name="([^"]+)"', tag), re.search(r'value="([^"]*)"', tag)
    if nm:
        fields[nm.group(1)] = vl.group(1) if vl else ''
st, loc, _ = s.req(fm.group(1), fields) if fm else (st, '', '')
check('student revokes from the report', bool(rv and fm) and st in (302, 303)
      and loc.endswith('/my/assessments/%s' % att_id), '%s %s' % (st, loc))
st, _, page2 = s.req('/my/assessments/%s' % att_id)
check('after revoking the report says it is not shared', st == 200 and 'هیچ پنلی این نتیجه را نمی‌بیند' in page2 and 'قطع اشتراک‌گذاری' not in page2)
st, _, pg = c.req('/my/workspaces/%s/p/%s' % (ws_id, att_id))
check('counselor view turns to not shared (404, or since S13 the status page without scores)', st == 404 or (st == 200 and 'tt-cobrand' not in pg and 'ts-factor__score' not in pg), str(st))

# self-taken result: offer to send it, correct wording on the share page
o = Client(TS)
check('solo login', o.login(SOLO, pw[SOLO]))
st, _, page = o.req('/my/assessments/%s' % solo_id)
check('G30: self-taken TALENT-INV-15 report offers «ارسال برای مشاورم» (in «قدم بعدی», UX audit G2 P3-5)',
      st == 200 and 'tt-next__cta' in page and ('/my/assessments/%s/share' % solo_id) in page and 'ارسال برای مشاورم' in page, str(st))
check('self-taken report has no revoke form', 'قطع اشتراک‌گذاری' not in page)
st, _, sp = o.req('/my/assessments/%s/share' % solo_id)
check('G31: share page tells the truth for the talent inventory', st == 200 and 'گزارش نیمرخ شما (نمرهٔ هر زمینه و توانایی‌ها)' in sp and 'فقط بازهٔ هر زمینه' not in sp, str(st))
check('another user cannot open my share page', Client(TS).req('/my/assessments/%s/share' % solo_id)[0] in (302, 303, 404))
e = Client('www.eot.ir'); e.login(SOLO, pw[SOLO])
check('eot.ir has no share page', e.req('/my/assessments/%s/share' % solo_id)[0] == 404)
summary()
