#!/usr/bin/env python3
"""End-to-end organization flow over HTTP against a served CLONE.
    ts_http_org.py DB PORT
Sets up (on the clone only) an active employment workspace with an HR portal
user, then: HR dashboard -> invite -> participant opens the link anonymously
-> signs in -> accepts with sharing -> consent -> answers -> submit -> own
report shows the sharing note -> HR sees bands only -> participant revokes ->
HR sees nothing. Plus eot.ir isolation checks."""
import html, os, re, subprocess, sys, urllib.parse
sys.argv += [] if len(sys.argv) > 2 else []
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB, PORT = sys.argv[1], sys.argv[2]
assert DB.startswith('eot_ts'), 'clones only'
import importlib.util
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
Client, check, ensure_user, path_of, shell = lib.Client, lib.check, lib.ensure_user, lib.path_of, lib.shell

TS = 'talentsearch.ir'
HR, PART = 'ts.org.hr.http@example.invalid', 'ts.org.part.http@example.invalid'
hr_pw, part_pw = ensure_user(HR), ensure_user(PART)
out = shell(
    "u=env['res.users'].search([('login','=','%s')])\n"
    "ws=env['ts.workspace'].search([('name','=','فضای آزمون HTTP')],limit=1)\n"
    "org=env['res.partner'].search([('name','=','سازمان آزمون HTTP')],limit=1) or env['res.partner'].create({'name':'سازمان آزمون HTTP','is_company':True})\n"
    "ws=ws or env['ts.workspace'].create({'approved_on':'2026-01-01 00:00:00','name':'فضای آزمون HTTP','purpose':'employment','partner_id':org.id})\n"
    "ws.state='active'\n"
    "env['ts.workspace.member'].search([('workspace_id','=',ws.id),('user_id','=',u.id)]) or env['ts.workspace.member'].create({'workspace_id':ws.id,'user_id':u.id,'role':'hr_admin'})\n"
    "env.cr.commit()\nprint('WS', ws.id)\n" % HR)
ws_id = re.search(r'WS (\d+)', out).group(1)

hr = Client(TS)
check('hr login', hr.login(HR, hr_pw))
st, _, page = hr.req('/my')
check('portal home shows workspace card', st == 200 and '/my/workspaces' in page)
st, _, page = hr.req('/my/workspaces')
check('workspace list 200', st == 200 and 'فضای آزمون HTTP' in page, str(st))
st, _, page = hr.req('/my/workspaces/%s/legacy' % ws_id)
check('dashboard 200 with invite form', st == 200 and 'ساخت پیوند دعوت' in page, str(st))
opts = re.findall(r'<option value="(\d+)">', page)
check('invite form lists employment instruments only', len(opts) > 0, str(len(opts)))
st, loc, _ = hr.req('/my/workspaces/%s/invite' % ws_id, {'csrf_token': hr.csrf(page), 'invitee_name': 'شرکت‌کنندهٔ HTTP', 'instrument_id': opts[0]})
check('invite -> dashboard with created', st in (302, 303) and 'created=' in loc, loc)
st, _, page = lib.follow(hr, loc)
m = re.search(r'value="https://talentsearch\.ir/invite/([0-9a-f]{32})"', page)
check('invite link shown for copying', bool(m))
tok = m.group(1)
st, loc, _ = hr.req('/my/workspaces/%s/invite' % ws_id, {'csrf_token': hr.csrf(page), 'invitee_name': 'x', 'instrument_id': '999999'})
check('invite with a foreign instrument id refused', 'error=form' in loc, loc)

anon = Client(TS)
st, _, page = anon.req('/invite/' + tok)
check('anonymous invite page offers sign-up and login', st == 200 and '/web/signup?redirect=' in page and '/web/login?redirect=' in page)
check('invite page explains what is shared', 'بازهٔ هر بُعد' in page)

p = Client(TS)
check('participant login', p.login(PART, part_pw))
st, _, page = p.req('/invite/' + tok)
check('signed-in invite page has accept form', st == 200 and '/accept' in page)
st, loc, _ = p.req('/invite/%s/accept' % tok, {'csrf_token': p.csrf(page), 'share': '1'})
token = path_of(loc).split('/take/')[-1]
check('accept -> player', st in (302, 303) and len(token) == 32, loc)
st, _, page = p.req('/take/' + token)
st, loc, _ = p.req('/take/%s/consent' % token, {'csrf_token': p.csrf(page), 'consent_service': '1'})
st, _, page = p.req('/take/' + token)
csrf = p.csrf(page)
pages = int(re.search(r'صفحهٔ [۰-۹]+ از ([۰-۹]+)', page).group(1).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')))
for n in range(1, pages + 1):
    _, _, pg = p.req('/take/%s?page=%d' % (token, n))
    for iid in re.findall(r'class="ts-q" data-item="(\d+)"', pg):
        p.req('/take/%s/answer' % token, {'csrf_token': csrf, 'item': iid, 'value': str(1 + int(iid) % 5)})
st, _, page = p.req('/take/%s/review' % token)
st, loc, _ = p.req('/take/%s/submit' % token, {'csrf_token': p.csrf(page), 'submission_key': token})
report = path_of(loc).split('?')[0]
check('participant submit -> own report', report.startswith('/my/assessments/'), loc)
st, _, page = p.req(report)
check('own report shows sharing note + revoke', st == 200 and 'اشتراک با سازمان' in page and '/unshare' in page)
st, loc, _ = p.req('/invite/' + tok)
check('invite link after completion -> own report', path_of(loc).startswith('/my/assessments/'), loc)

st, _, page = hr.req('/my/workspaces/%s/legacy?state=done' % ws_id)
aid = re.search(r'/my/workspaces/%s/a/(\d+)' % ws_id, page)
check('dashboard lists the completed assignment', bool(aid))
st, _, page = hr.req('/my/workspaces/%s/a/%s' % (ws_id, aid.group(1)))
text = html.unescape(re.sub(r'<[^>]+>', ' ', page))
check('HR sees band summary', st == 200 and 'ts-band' in page and 'خلاصهٔ نتایج' in page)
check('HR sees no scores and no interpretation texts', 'نمره (۱ تا ۵)' not in text and 'راهنمای متخصص' not in text and 'تفسیر نتیجهٔ شما' not in text)
check('HR cannot open the participant attempt or report', hr.req('/take/' + token)[0] == 404 and hr.req(report)[0] == 404)

st, _, page = p.req(report)
p.req(report + '/unshare', {'csrf_token': p.csrf(page)})
st, _, page = hr.req('/my/workspaces/%s/a/%s' % (ws_id, aid.group(1)))
check('after revoke HR sees no result', st == 200 and 'ts-band' not in page and 'به اشتراک نگذاشته' in page)

o = Client(TS)
o.login('ts.flow.b@example.invalid', ensure_user('ts.flow.b@example.invalid'))
check('non-member gets 404 on the workspace', o.req('/my/workspaces/%s/legacy' % ws_id)[0] == 404)
check('non-member gets 404 on the assignment', o.req('/my/workspaces/%s/a/%s' % (ws_id, aid.group(1)))[0] == 404)
check('other account cannot use a taken invite', o.req('/invite/' + tok)[0] == 404)
e = Client('www.eot.ir')
e.login(HR, hr_pw)
check('eot.ir /my/workspaces is 404', e.req('/my/workspaces')[0] == 404)
check('eot.ir /invite is 404', e.req('/invite/' + tok)[0] == 404)
st, _, page = e.req('/my')
check('eot.ir /my shows no workspace card', st == 200 and '/my/workspaces' not in page)
lib.summary()
