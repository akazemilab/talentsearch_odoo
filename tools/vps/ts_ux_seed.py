# UX audit matrix (2026-10-11): every page route of website 4 in its main states, per role. Runs in `odoo shell` on a CLONE,
# after tools/prod/pv2_fixtures.py. Fictional data only; upserts. Writes /tmp/ux_matrix.json = {login: [paths]} for ts_shot.py.
import json, traceback
assert env.cr.dbname.startswith('eot_ts'), 'clones only'
portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
A, Att, M = env['ts.assignment'].sudo(), env['ts.attempt'].sudo(), env['ts.workspace.member'].sudo()
L = lambda k: 'ts.pv2.%s@example.invalid' % k
def user(k, name):
    return U.search([('login', '=', L(k))], limit=1) or U.create({'name': name, 'login': L(k), 'email': L(k), 'group_ids': [(6, 0, [portal.id])]})
def ws_of(name):
    return env['ts.workspace'].search([('name', '=', name)], limit=1)
EDU, CLIN, EMP = ws_of('پنل آزمایشی آموزشی'), ws_of('پنل آزمایشی بالینی'), ws_of('پنل آزمایشی استخدامی')
W = '/my/workspaces/%s' % EDU.id
inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1)
oth = env['ts.instrument'].search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)
own = M.search([('workspace_id', '=', EDU.id), ('role', '=', 'owner')], limit=1)
cns = M.search([('workspace_id', '=', EDU.id), ('role', '=', 'counselor')], limit=1)
stu = user('edu.student', 'دانش‌آموز آزمایشی')
R = {}
def step(name, fn):
    try:
        R[name] = fn()
        env.cr.commit()
    except Exception as e:
        env.cr.rollback()
        print('SEED-SKIP', name, type(e).__name__, str(e)[:120])

done_as = A.search([('workspace_id', '=', EDU.id), ('invitee_name', '=', 'دانش‌آموز آزمایشی'), ('withdrawn', '=', False)], limit=1)
done_at = done_as.attempt_id if 'attempt_id' in done_as._fields else Att.search([('user_id', '=', stu.id), ('state', '=', 'done')], limit=1)
client = done_as.client_id if 'client_id' in done_as._fields else env['ts.panel.client']
def mk_client():
    C = env['ts.panel.client'].sudo()
    return C.search([('workspace_id', '=', EDU.id), ('name', '=', 'نگار آزمایشی')], limit=1) or C.create(
        {'workspace_id': EDU.id, 'name': 'نگار آزمایشی', 'email': 'negar@example.invalid'})
step('client2', mk_client)
def mk_group():
    G = env['ts.panel.group'].sudo()
    return G.search([('workspace_id', '=', EDU.id), ('name', '=', 'کلاس دهم الف')], limit=1) or G.create(
        {'workspace_id': EDU.id, 'name': 'کلاس دهم الف', 'kind': 'class'})
step('group', mk_group)
def mk_camp(kind, name):
    C = env['ts.campaign'].sudo()
    return C.search([('workspace_id', '=', EDU.id), ('name', '=', name)], limit=1) or C.create(
        {'workspace_id': EDU.id, 'name': name, 'instrument_id': inst.id, 'kind': kind, 'created_by_id': own.id})
step('camp_list', lambda: mk_camp('list', 'دعوت کلاس دهم'))
step('camp_open', lambda: mk_camp('open_link', 'پیوند باز نمایشگاه'))
def mk_pending():
    return A.search([('workspace_id', '=', EDU.id), ('invitee_name', '=', 'مهمان آزمایشی')], limit=1) or A.create(
        {'workspace_id': EDU.id, 'instrument_id': inst.id, 'invitee_name': 'مهمان آزمایشی', 'invited_by_id': own.user_id.id})
step('pending', mk_pending)
def mk_minv():
    I = env['ts.member.invite'].sudo()
    return I.search([('workspace_id', '=', EDU.id), ('state', '=', 'pending')], limit=1) if 'state' in I._fields and I.search_count(
        [('workspace_id', '=', EDU.id)]) else I.ts_create(own, 'counselor', email_raw='colleague.ux@example.invalid')
step('minv', mk_minv)
step('import', lambda: env['ts.job'].sudo().ts_import_prepare(own, 'ux.csv', 'نام,موبایل\nعلی آزمایشی,09120000099\n'.encode()))
step('export', lambda: env['ts.job'].sudo().ts_export_create(own, 'export_clients', 'csv'))
# participant attempts in every player state (one user per state: one open talent attempt per user)
def talent_state(k, state):
    u = user(k, 'شرکت‌کنندهٔ آزمایشی %s' % k[-1])
    a = Att.search([('user_id', '=', u.id), ('instrument_id', '=', inst.id), ('state', '!=', 'done')], limit=1) or Att.create(
        {'user_id': u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
    if state != 'consent' and a.state == 'consent':
        a.give_consent()
    if state in ('matrix', 'review') and not a.field_ids:
        items = a.active_items()
        for n, label in enumerate(['ریاضی', 'نقاشی']):
            f = a.ts_add_field(label)
            for i, it in enumerate(items if state == 'review' or n == 0 else items[:4]):
                a.ts_save_cell(f, it.id, (i + n) % 5 + 1)
            if state == 'review' or n == 0:
                a.ts_finish_field(f)
    return a
for k, s in (('ux.p1', 'consent'), ('ux.p2', 'fields'), ('ux.p3', 'matrix'), ('ux.p4', 'review')):
    step(k, lambda k=k, s=s: talent_state(k, s))
def likert(state):
    a = Att.search([('user_id', '=', stu.id), ('instrument_id', '=', oth.id), ('state', '!=', 'done')], limit=1) or Att.create(
        {'user_id': stu.id, 'instrument_id': oth.id, 'version_id': oth.current_version_id.id})
    if state == 'progress' and a.state == 'consent':
        a.give_consent()
    return a
step('likert', lambda: likert('progress'))

tok = lambda k: R[k].access_token if k in R else None
pub = ['/panel', '/panel/terms', '/signup', '/web/login', '/web/reset_password', '/help/panel', '/assessments/%s' % inst.slug,
       '/my/workspaces/new']
if 'pending' in R: pub.append('/invite/%s' % R['pending'].token)
if 'minv' in R and R['minv']: pub.append('/join/%s' % R['minv'].token)
if 'camp_open' in R and R['camp_open'].open_token: pub.append('/c/%s' % R['camp_open'].open_token)
o = [W + x for x in ('', '/home', '/clients', '/clients/new', '/groups', '/invites', '/invites/new', '/campaigns', '/campaigns/new',
                     '/members', '/reports', '/reports/group', '/credits', '/exports', '/audit', '/settings', '/settings/transfer',
                     '/settings/close', '/import', '/legacy')]
o += ['/my/workspaces', '/my/workspaces/new', '/help/roles', '/my/notifications', '/my/notifications/prefs', '/my/reauth',
      '/my/sessions', '/my/privacy', '/my/sharing', '/my', '/my/account', '/my/phone']
if client:
    o += [W + '/clients/%s' % client.id, W + '/clients/%s/edit' % client.id]
    if done_at: o.append(W + '/clients/%s/r/%s' % (client.id, done_at.id))
if done_at: o.append(W + '/p/%s' % done_at.id)
if 'group' in R: o.append(W + '/groups/%s' % R['group'].id)
for k in ('camp_list', 'camp_open'):
    if k in R: o += [W + '/campaigns/%s' % R[k].id]
if 'camp_list' in R: o.append(W + '/campaigns/%s/sheet' % R['camp_list'].id)
if 'pending' in R: o += [W + '/invites/%s' % R['pending'].id, W + '/a/%s' % R['pending'].id]
if cns: o += [W + '/members/%s' % cns.id, W + '/members/%s/deactivate' % cns.id]
if 'import' in R: o += [W + '/import/%s/map' % R['import'].id, W + '/import/%s/review' % R['import'].id]
if 'export' in R: o.append(W + '/jobs/%s' % R['export'].id)
c = [W + x for x in ('', '/clients', '/reports', '/invites', '/groups')] + ['/my/workspaces', '/my']
if client:
    c.append(W + '/clients/%s' % client.id)
    if done_at: c.append(W + '/clients/%s/r/%s' % (client.id, done_at.id))
s = ['/my', '/my/assessments', '/my/sharing', '/my/privacy', '/my/notifications', '/my/sessions', '/my/phone', '/my/account']
if done_at: s += ['/my/assessments/%s' % done_at.id, '/my/assessments/%s/share' % done_at.id]
if 'likert' in R: s.append('/take/%s' % tok('likert'))
if 'pending' in R: s.append('/invite/%s' % R['pending'].token)
m = {'': pub, L('edu.owner'): o, L('edu.counselor'): c, L('edu.student'): s}
for k in ('ux.p1', 'ux.p2', 'ux.p3', 'ux.p4'):
    if k in R:
        m[L(k)] = ['/take/%s' % tok(k)] + (['/take/%s/review' % tok(k)] if k == 'ux.p4' else [])
for key, ws in (('clin.clinician', CLIN), ('emp.reviewer', EMP)):
    if ws: m[L(key)] = ['/my/workspaces/%s' % ws.id, '/my/workspaces/%s/clients' % ws.id, '/my/workspaces/%s/reports' % ws.id]

# ---------------------------------------------------------------- battery pages (clinic phase 3, 2026-10-11)
# On the fixtures of tools/prod/ts_http_battery.py (counseling-center panel in granted mode, battery BAT-TEST-HTTP, owner /
# counselor c1 / participant p1 with a finished battery). Adds: a battery invitation not accepted (uxb1), accepted but no
# consent yet (uxb2), instrument 1 submitted + instrument 2 half answered (uxb3), a battery campaign. Upserts; the HTTP
# suite withdraws open invitations of its panel on every run, so withdrawn ones are replaced here.
BL = lambda n: 'ts.bat.%s.http@example.invalid' % n
BU = lambda n: 'ts.bat.%s@example.invalid' % n
bat = env['ts.battery'].sudo().search([('code', '=', 'BAT-TEST-HTTP')], limit=1)
borg = env['res.partner'].search([('name', '=', 'پنل آزمون مجموعه وب')], limit=1)
BWS = env['ts.workspace'].search([('partner_id', '=', borg.id)], limit=1) if borg else env['ts.workspace']
busr = {n: U.search([('login', '=', BL(n))], limit=1) for n in ('owner', 'c1', 'p1')}
if not (bat and BWS and all(busr.values())):
    print('SEED-SKIP battery: run tools/prod/ts_http_battery.py on this clone first')
else:
    BW = '/my/workspaces/%s' % BWS.id
    bmo = M.search([('workspace_id', '=', BWS.id), ('user_id', '=', busr['owner'].id)], limit=1)
    bm1 = M.search([('workspace_id', '=', BWS.id), ('user_id', '=', busr['c1'].id)], limit=1)
    if busr['p1'].name == 'آزمون جریان':
        busr['p1'].name = 'سارا آزمایشی'
    bdone = A.search([('workspace_id', '=', BWS.id), ('battery_id', '=', bat.id), ('user_id', '=', busr['p1'].id),
                      ('state', '=', 'done')], order='id desc', limit=1)

    def bat_user(k, name):
        return U.search([('login', '=', BU(k))], limit=1) or U.create(
            {'name': name, 'login': BU(k), 'email': BU(k), 'group_ids': [(6, 0, [portal.id])]})

    def bat_inv(k, name, state):
        """state: invited | consent | going (instrument 1 done, instrument 2 half answered)."""
        u = bat_user(k, name)
        a = A.search([('workspace_id', '=', BWS.id), ('battery_id', '=', bat.id), ('invitee_name', '=', name),
                      ('withdrawn', '=', False)], limit=1) or A.create(
            {'workspace_id': BWS.id, 'instrument_id': bat.ts_first_instrument().id, 'battery_id': bat.id,
             'invited_by_id': busr['c1'].id, 'invitee_name': name})
        if state == 'invited':
            return a
        if not a.user_id:
            a.action_accept(u, True)
        rows = a.ts_battery_attempts()
        if state == 'going':
            first, second = rows[0], rows[1]
            if first.state == 'consent':
                first.give_consent()
            if first.state == 'in_progress':
                for it in first.active_items():
                    first.save_answer(it.id, 1 + it.id % 5)
                first.action_submit()
            if second.state == 'in_progress' and not second.answer_ids:
                items = second.active_items()
                for it in items[:max(1, len(items) // 2)]:
                    second.save_answer(it.id, 1 + it.id % 5)
        return a
    step('bat_inv', lambda: bat_inv('uxb1', 'مریم آزمایشی', 'invited'))
    step('bat_consent', lambda: bat_inv('uxb2', 'رضا آزمایشی', 'consent'))
    step('bat_going', lambda: bat_inv('uxb3', 'نیما آزمایشی', 'going'))

    def bat_camp():
        C = env['ts.campaign'].sudo()
        return C.search([('workspace_id', '=', BWS.id), ('name', '=', 'ارزیابی آغاز مشاوره پاییز')], limit=1) or C.create(
            {'workspace_id': BWS.id, 'name': 'ارزیابی آغاز مشاوره پاییز', 'battery_id': bat.id, 'kind': 'open_link',
             'created_by_id': bmo.id})
    step('bat_camp', bat_camp)

    bo = ([BW + '/members/%s' % bm1.id] if bm1 else []) + [BW + '/campaigns/new']
    if 'bat_camp' in R: bo.append(BW + '/campaigns/%s' % R['bat_camp'].id)
    m[BL('owner')] = bo
    b1 = [BW + '/invites/new?fresh=1']
    if bdone and bdone.client_id:
        b1 += [BW + '/invites/new?fresh=1&client=%s' % bdone.client_id.id, BW + '/clients/%s' % bdone.client_id.id,
               BW + '/clients/%s/b/%s' % (bdone.client_id.id, bdone.id)]
    if 'bat_going' in R: b1.append(BW + '/invites/%s' % R['bat_going'].id)
    m[BL('c1')] = b1
    if bdone: m[BL('p1')] = ['/my/assessments/battery/%s' % bdone.id, '/my/assessments']
    if 'bat_inv' in R: m[BU('uxb1')] = ['/invite/%s' % R['bat_inv'].token]
    if 'bat_consent' in R: m[BU('uxb2')] = ['/take/%s' % R['bat_consent'].ts_battery_attempts()[0].access_token]
    if 'bat_going' in R:
        ra = R['bat_going'].ts_battery_attempts()
        m[BU('uxb3')] = ['/take/%s' % ra[1].access_token, '/take/%s/next' % ra[0].access_token, '/my/assessments', '/my']
json.dump(m, open('/tmp/ux_matrix.json', 'w'))
print('UXMATRIX', ' '.join('%s=%d' % ((k or 'public').split('@')[0], len(v)) for k, v in m.items()), 'total', sum(len(v) for v in m.values()))
