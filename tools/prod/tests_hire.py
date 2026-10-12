# HR hiring (ts_onet, ts_tasks, ts_hire): loaders, positions, battery run with the personality questionnaire and a timed
# task, job fit, validity, decisions, fairness, verification, email. Run ONLY on an eot_ts* clone via odoo-bin shell.
# Never commits; never sends (clones have their mail servers switched off by ts_db.sh).
import json

from odoo.exceptions import UserError, ValidationError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=Exception):
    try:
        with env.cr.savepoint():
            fn()
    except exc:
        return True
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment']
Inst, B, P, Occ = env['ts.instrument'], env['ts.battery'], env['ts.hire.position'], env['ts.onet.occupation']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.hire.%d@example.invalid' % _n[0]
    return U.create({'name': 'داوطلب %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id,
                   **({'escalation_contact_id': org.id} if purpose == 'clinical' else {})})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role):
    return M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role})


# ---------------------------------------------------------------- loaders
hx = Inst.search([('code', '=', 'HR-HEXACO-1')])
check('H01 personality questionnaire published, 123 items, valid contract',
      hx.state == 'published' and hx.active_item_count == 123 and hx.current_version_id.validation_ok,
      (hx.state, hx.active_item_count, hx.current_version_id.validation_report))
tasks = Inst.search([('code', 'in', ['TASK-REASON', 'TASK-SPATIAL', 'TASK-NUMERIC', 'TASK-SPEED', 'TASK-VERIFY'])])
check('H02 five task instruments published, invite-only, employment',
      len(tasks) == 5 and all(t.state == 'published' and t.invite_only and t.purpose == 'employment' for t in tasks),
      [(t.code, t.state) for t in tasks])
bs = B.search([('code', 'in', ['BAT-HR-SHORT', 'BAT-HR-FULL'])])
check('H03 two HR batteries published, employment only',
      len(bs) == 2 and all(b.state == 'published' and b.for_employment and not b.for_clinical for b in bs))
full = bs.filtered(lambda b: b.code == 'BAT-HR-FULL')
check('H04 full battery minutes include the timed tasks', full.est_minutes >= 45, full.est_minutes)
check('H05 hidden attention factor', hx.current_version_id.factor_ids.filtered(lambda f: f.code == 'ATTN').report_hidden)
check('H06 catalogue loaded (923) and Persian search works',
      Occ.search_count([]) == 923 and Occ.ts_search('حسابدار') and Occ.ts_search('software developer'))

# ---------------------------------------------------------------- positions
emp = panel('employment', 'شرکت آزمون استخدام')
hr = member(emp, 'hr_admin')
rev = member(emp, 'reviewer')
dev = Occ.search([('code', '=', '15-1252.00')])
pos = P.create({'name': 'برنامه‌نویس پشتیبان', 'workspace_id': emp.id, 'occupation_id': dev.id, 'battery_choice': 'short'})
check('H07 position gets the short HR battery', pos.battery_id.code == 'BAT-HR-SHORT')
edu = panel('education', 'مدرسهٔ آزمون')
check('H08 a position is refused outside employment panels',
      raises(lambda: P.create({'name': 'x', 'workspace_id': edu.id, 'occupation_id': dev.id}), ValidationError))
names = [r['name'] for r in dev.ts_requirements()]
check('H09 more than three critical requirements refused', raises(lambda: pos.ts_set_profile(names[:4], [], hr), UserError))
pos.ts_set_profile(['Attention to Detail'], ['Social Orientation'], hr)
check('H10 profile saved and position opened', pos.state == 'open' and pos.ts_overrides()['critical'] == ['Attention to Detail'])

# ---------------------------------------------------------------- one candidate through the battery
cand = puser()
a = A.with_user(hr.user_id).sudo().create({
    'workspace_id': emp.id, 'battery_id': pos.battery_id.id, 'instrument_id': pos.battery_id.ts_first_instrument().id,
    'invitee_name': cand.name, 'position_id': pos.id, 'ts_extra_time': '1.5', 'invitee_email': 'cand@example.invalid'})
first = a.action_accept(cand, share=True)
ats = a.ts_battery_attempts()
check('H11 accepting creates the questionnaire and the reasoning task', len(ats) == 2 and ats[0].instrument_id == hx, ats.mapped('instrument_id.code'))
q = ats[0]
q.give_consent()
STRONG = {'Perfectionism': 5, 'Organization': 5, 'Diligence': 5, 'Inquisitiveness': 5, 'Social Boldness': 2, 'Anxiety': 2}
for it in q.active_items():
    f = it.factor_id.code
    if f == 'ATTN':
        v = {0: 1, 1: 4, 2: 3}[list(q.active_items().filtered(lambda i: i.factor_id.code == 'ATTN').ids).index(it.id)]
    else:
        t = STRONG.get(f, 3)
        v = (6 - t) if it.reverse else t
    q.save_answer(it.id, v)
q.action_submit()
check('H12 questionnaire scored; attention factor hidden from the report',
      q.state == 'done' and len(q.result_rows()) == 24 and 'ATTN' not in q.result_rows().mapped('factor_id.code'))
check('H13 facets for the job fit', abs(q.ts_facets()['Perfectionism'] - 5.0) < 1e-6)
t = ats[1]
if t.state == 'consent':
    t.ts_battery_copy_consent() if hasattr(t, 'ts_battery_copy_consent') else t.give_consent()
check('H14 task attempt in progress after the battery consent', t.state == 'in_progress', t.state)
cfg = t.ts_task_config()
check('H15 extra time 1.5 scales every limit', cfg['blocks'][0]['limit'] == 360 and cfg['accom'] == 1.5, cfg['blocks'][0]['limit'])
st = t.ts_task_start(0)
check('H16 live items carry no answers', st['items'] and all('key' not in i for i in st['items']) and 'keys' not in st)
check('H17 blocks run in order', raises(lambda: t.ts_task_start(2), UserError))
state = json.loads(t.task_json)
for i in range(3):
    if i:
        t.ts_task_start(i)
    items, keys = t._ts_items(json.loads(t.task_json), i)
    for idx, k in enumerate(keys):
        out = t.ts_task_answer(i, idx, k, 4000)
    t.ts_task_finish(i, focus_lost=0)
check('H18 all blocks closed -> scored with three abilities', t.state == 'done' and len(t.result_ids) == 3, t.state)
check('H19 all correct -> high percentiles', all(r.score > 85 and r.band == 'high' for r in t.result_ids), t.result_ids.mapped('score'))
a.invalidate_recordset()
check('H20 candidate complete with a job fit', a.ts_hire_complete and a.jobfit_band, (a.ts_hire_complete, a.jobfit_band))
res = a.ts_jobfit()
check('H21 job fit uses personality and abilities, overrides applied',
      res['ws'] and res['ab']['rows'] and res['overrides']['critical'] == ['Attention to Detail']
      and not any(x['name'] == 'Social Orientation' for x in res['ws']['rows']))
check('H22 HR and reviewer see the summary level', a.result_level(hr) == 'summary' and a.result_level(rev) == 'summary')
check('H23 a careful answer pattern raises no attention/straight/inconsistency flag (a script is always fast)',
      not ({'attention', 'straight', 'inconsistent'} & set((a.validity_flags or '').split(','))), a.validity_flags)

# ---------------------------------------------------------------- deadline and validity
c2 = puser()
a2 = A.with_user(hr.user_id).sudo().create({'workspace_id': emp.id, 'battery_id': pos.battery_id.id,
                                            'instrument_id': pos.battery_id.ts_first_instrument().id,
                                            'invitee_name': c2.name, 'position_id': pos.id})
a2.action_accept(c2, share=True)
q2, t2 = a2.ts_battery_attempts()[0], a2.ts_battery_attempts()[1]
q2.give_consent()
for it in q2.active_items():
    q2.save_answer(it.id, 4)
q2.action_submit()
a2.invalidate_recordset()
check('H24 straight-lining and failed attention items are flagged', {'straight', 'attention'} <= set((a2.validity_flags or '').split(',')), a2.validity_flags)
if t2.state == 'consent':
    t2.ts_battery_copy_consent() if hasattr(t2, 'ts_battery_copy_consent') else t2.give_consent()
t2.ts_task_start(0)
s2 = json.loads(t2.task_json)
s2['blocks'][0]['deadline'] = s2['blocks'][0]['started'] - 100
t2.sudo().write({'task_json': json.dumps(s2)})
check('H25 an answer after the deadline is refused', t2.ts_task_answer(0, 0, 0, 1000) == {'ok': False, 'reason': 'time'})
check('H26 partial result: personality-only fit while tasks are open', a2.jobfit_band and not a2.ts_hire_complete
      and a2.ts_jobfit()['personality_only'])

# ---------------------------------------------------------------- decisions, fairness, verification
a.ts_set_decision('shortlist', 'خوب', hr.user_id)
check('H27 decision stored with who and when', a.hire_decision == 'shortlist' and a.decision_by_id == hr.user_id and a.decision_at)
check('H28 invalid decision refused', raises(lambda: a.ts_set_decision('maybe', '', hr.user_id), UserError))
fair = pos.ts_fairness()
check('H29 fairness hides small groups', fair['ts_gender']['rows'] == [])
for i in range(20):
    u = puser()
    x = A.sudo().create({'workspace_id': emp.id, 'battery_id': pos.battery_id.id,
                         'instrument_id': pos.battery_id.ts_first_instrument().id, 'invitee_name': u.name, 'position_id': pos.id})
    x.write({'ts_gender': 'female' if i < 10 else 'male', 'hire_decision': ('shortlist' if i < 2 else 'reject') if i < 10 else 'shortlist'})
fair = pos.ts_fairness()
rows = {r['label']: r for r in fair['ts_gender']['rows']}
check('H30 four-fifths rule flags the lower group, never shows group sizes',
      rows and rows['زن']['flag'] and not rows['مرد']['flag'] and all('n' not in r for r in rows.values()), rows)
v = a.ts_invite_verification(hr)
check('H31 verification test invitation', v.instrument_id.code == 'TASK-VERIFY' and v.verify_of_id == a)
check('H32 a second click reuses it', a.ts_invite_verification(hr) == v)

# ---------------------------------------------------------------- email (rendered, never sent on a clone)
tpl = env.ref('ts_hire.mail_invite')
body = tpl._render_field('body_html', a.ids)[a.id]
subj = tpl._render_field('subject', a.ids)[a.id]
check('H33 invitation email renders with the link and the position', a.invite_url() in str(body) and pos.name in str(body) and subj, subj)
check('H34 no active mail server on the clone -> nothing sent, error recorded',
      not a._ts_send_invite_email() and a.email_error, a.email_error)
check('H35 HR batteries have products for billing', all(b.product_id for b in bs) if 'product_id' in B._fields else True)

# ---------------------------------------------------------------- review fixes (2026-10-12)
stranger = puser()
check('H36 a verification test can only be accepted by the same candidate', raises(lambda: v.action_accept(stranger, share=True), UserError))
c3 = puser()
a3 = A.with_user(hr.user_id).sudo().create({'workspace_id': emp.id, 'battery_id': pos.battery_id.id,
                                            'instrument_id': pos.battery_id.ts_first_instrument().id,
                                            'invitee_name': c3.name, 'position_id': pos.id})
a3.action_accept(c3, share=False)
check('H37 a candidate who did not share is status-only for HR', a3.result_level(hr) in ('status', 'none'))
env.cr.execute("UPDATE ts_assignment SET create_date = now() - interval '400 days' WHERE id = %s", [a.id])
a.invalidate_recordset()
n = A._cron_hire_retention()
a.invalidate_recordset()
check('H38 retention: after 12 months the employer loses the result and HR data is cleared',
      n >= 1 and a.share_level == 'none' and not a.jobfit_json and a.hire_purged_at and a.result_level(hr) != 'summary')
t4 = Inst.search([('code', '=', 'TASK-SPEED')])
c4 = puser()
a4 = A.sudo().create({'workspace_id': emp.id, 'instrument_id': t4.id, 'invitee_name': c4.name})
at4 = a4.action_accept(c4, share=True)
at4.give_consent()
at4.ts_task_start(0)
items4, keys4 = at4._ts_items(json.loads(at4.task_json), 0)
at4.ts_task_finish(0, responses=[{'c': k, 'rt': 400, 't': 85000} for k in keys4[:30]])
check('H39 a speed block claiming more time than passed is flagged', json.loads(at4.task_json)['blocks'][0]['meta'].get('timing') == 1)
check('H40 the mail server is chosen by the sender domain only', A._ts_mail_server().from_filter in (False, 'sepehrtherapy.ir'))
clin = panel('clinical', 'مرکز آزمون بالینی HR')
cm = M.create({'workspace_id': clin.id, 'user_id': puser().id, 'role': 'owner'})
check('H41 HR instruments are not offered outside employment panels',
      not cm.allowed_instruments().filtered('invite_only') and hr.allowed_instruments().filtered('invite_only'))

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
