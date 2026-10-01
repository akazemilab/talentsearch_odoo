# Panel v2 S9 (exports). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
import csv
import io
import json
from datetime import datetime, timedelta

import psycopg2
from odoo import fields
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ts_panel.models import exporter as ex
from odoo.addons.ts_panel.models import importer as imp

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=(UserError, ValidationError, psycopg2.IntegrityError, imp.FileProblem)):
    env.flush_all()
    try:
        with env.cr.savepoint():
            fn()
            env.flush_all()
    except exc:
        return True
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, C, G, J, A = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.panel.client', 'ts.panel.group', 'ts.job', 'ts.assignment'))
Inst = env['ts.instrument']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s9.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id,
                   **({'escalation_contact_id': org.id} if purpose == 'clinical' else {})})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role, **kw):
    m = M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role, **kw})
    if role in ('clinician', 'clinic_director'):
        m.action_verify()
    return m


def finish(attempt):
    attempt.give_consent()
    for it in attempt.active_items():
        attempt.save_answer(it.id, 1 + it.id % 5)
    attempt.action_submit()


# ---- cell safety, digits, dates, files (pure helpers)
check('SEC-8: a formula start gets a quote', [ex.safe(x) for x in ('=1+1', '+98912', '-5', '@x', '\tx')] == ["'=1+1", "'+98912", "'-5", "'@x", "'\tx"])
check('plain text is untouched, None is empty, numbers stay numbers', ex.safe('علی') == 'علی' and ex.safe(None) == '' and ex.safe(7) == 7 and ex.safe(2.5) == 2.5)
check('L10N-2: Persian and Arabic digits become Latin', ex.safe('۰۹۱۲٣٤') == '091234')
j, i = ex.date_cols(datetime(2026, 3, 21, 12, 0))
check('both date forms: Jalali with Latin digits and ISO', j == '1405/01/01' and i == '2026-03-21', '%s %s' % (j, i))
check('a date near midnight UTC is read in Tehran', ex.date_cols(datetime(2026, 3, 20, 21, 0)) == ('1405/01/01', '2026-03-21'))
check('a plain date gives the same date in both forms', ex.date_cols(fields.Date.to_date('2026-03-21')) == ('1405/01/01', '2026-03-21'))
check('no value gives two empty cells', ex.date_cols(False) == ('', ''))
data = ex.to_csv(['الف', 'ب'], [['=SUM(A1)', '۱۲۳'], ['x', 5]])
check('csv: UTF-8 BOM first', data.startswith(b'\xef\xbb\xbf'))
rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
check('csv: header, formula guard and Latin digits survive a round trip', rows == [['الف', 'ب'], ["'=SUM(A1)", '123'], ['x', '5']], str(rows))
x, ext, mime = ex.render('xlsx', ['الف'], [['=A1+1'], ['-3'], ['متن']])
import openpyxl
wb = openpyxl.load_workbook(io.BytesIO(x))
wsx = wb.active
check('xlsx: opens, right to left, formula-like text stays text', wsx.sheet_view.rightToLeft and wsx['A2'].value == "'=A1+1" and wsx['A2'].data_type == 's'
      and wsx['A3'].value == "'-3" and ext == 'xlsx' and 'spreadsheetml' in mime)
check('render defaults to csv', ex.render('zzz', ['a'], [])[1:] == ('csv', 'text/csv'))

# ---- fixtures: an education panel, an employment panel, a clinical panel
edu = panel('education', 'مدرسهٔ خروجی S9')
emp = panel('employment', 'شرکت خروجی S9')
cli = panel('clinical', 'مرکز خروجی S9')
o_edu, c1_edu, c2_edu = member(edu, 'owner'), member(edu, 'counselor'), member(edu, 'counselor')
o_emp, hr_emp, rv_emp = member(emp, 'owner'), member(emp, 'hr_admin'), member(emp, 'reviewer')
o_cli, cl_cli = member(cli, 'owner'), member(cli, 'clinician', license_number='T-9')
grp = G.create({'workspace_id': edu.id, 'name': 'کلاس ۹۰۱'})

plain = Inst.search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
talent = Inst.search([('code', '=', 'TALENT-INV-15')], limit=1)
check('fixtures: instruments found (education panels invite TALENT-INV-15 only)', bool(plain and talent) and o_edu.allowed_instruments() == talent)

# employment: one done + shared result for the hr admin, one not shared
a_emp = A.create({'workspace_id': emp.id, 'instrument_id': plain.id, 'invitee_name': 'استخدام‌شونده یک'})
at_emp = a_emp.action_accept(puser(), share=True)
finish(at_emp)
a_emp2 = A.create({'workspace_id': emp.id, 'instrument_id': plain.id, 'invitee_name': 'استخدام‌شونده دو'})
a_emp2.action_accept(puser(), share=False)
a_emp3 = A.create({'workspace_id': emp.id, 'instrument_id': plain.id, 'invitee_name': '=cmd|calc'})
env.flush_all()
check('employment fixtures: one summary-level result', a_emp.result_level(hr_emp) == 'summary' and a_emp2.result_level(hr_emp) == 'status')

# education: counselor c1 is responsible for client 1; client 2 belongs to c2; client 3 is unassigned and in a group
a_e1 = A.create({'workspace_id': edu.id, 'instrument_id': talent.id, 'invitee_name': 'دانش‌آموز یک', 'invitee_phone': '09123334455'})
a_e2 = A.create({'workspace_id': edu.id, 'instrument_id': talent.id, 'invitee_name': 'دانش‌آموز دو'})
a_e3 = A.create({'workspace_id': edu.id, 'instrument_id': talent.id, 'invitee_name': 'دانش‌آموز سه'})
a_e1.client_id.responsible_id = c1_edu.id
a_e2.client_id.responsible_id = c2_edu.id
a_e3.client_id.group_ids = [(4, grp.id)]
at_e1 = a_e1.action_accept(puser(), share=True)
at_e3 = a_e3.action_accept(puser(), share=True)
SECRET = 'نام-خصوصی-زمینه-۷۷'
PROFILE = json.dumps({'fields': [
    {'seq': 1, 'label': SECRET, 'scales': {'ANA': 61.5, 'EXP': 70, 'ACA': 48, 'NOV': 80, 'DUT': 55}, 'composites': {'TOT': 62.9}},
    {'seq': 2, 'label': 'زمینهٔ دوم', 'scales': {'ANA': 20, 'EXP': 30, 'ACA': 40, 'NOV': 50, 'DUT': 60}, 'composites': {'TOT': 40}}]})
for _at in (at_e1, at_e3):
    _at.write({'state': 'done', 'released': True, 'submitted_at': fields.Datetime.now(), 'profile_json': PROFILE})
env.flush_all()
check('education fixtures: the owner sees both results at education level', a_e1.result_level(o_edu) == 'education' and a_e3.result_level(o_edu) == 'education')

# ---- EXP-1 clients
h, r = ex.client_rows(env, o_edu, {})
names = [x[0] for x in r]
check('EXP-1: headers and one row per active client for the owner', h == ex.CLIENT_HEADERS and len(r) == 3 and 'دانش‌آموز سه' in names, str(names))
check('EXP-1: the group column and the responsible column', any(x[2] == 'کلاس ۹۰۱' for x in r) and any(x[3] == c1_edu.user_id.name for x in r))
check('EXP-1: no phone, e-mail or token column', not (set(h) & {'موبایل', 'ایمیل', 'پیوند'}) and all('0912' not in str(c) for x in r for c in x))
h, r = ex.client_rows(env, c1_edu, {})
check('EXP-1: a counselor gets her own clients and the unassigned ones, not a colleague\'s', sorted(x[0] for x in r) == ['دانش‌آموز سه', 'دانش‌آموز یک'], str([x[0] for x in r]))
h, r = ex.client_rows(env, o_edu, {'group_id': str(grp.id)})
check('EXP-1: the group filter', [x[0] for x in r] == ['دانش‌آموز سه'])
h, r = ex.client_rows(env, hr_emp, {})
check('EXP-1: a formula-looking name is quoted in the file', any(x[0] == '=cmd|calc' for x in r) and b"'=cmd|calc" in ex.to_csv(h, r))
a_e2.client_id.write({'state': 'archived'})
check('EXP-1: archived clients only when asked', len(ex.client_rows(env, o_edu, {})[1]) == 2 and len(ex.client_rows(env, o_edu, {'state': 'all'})[1]) == 3
      and len(ex.client_rows(env, o_edu, {'state': 'archived'})[1]) == 1)
a_e2.client_id.write({'state': 'active'})

# ---- EXP-2 status
h, r = ex.status_rows(env, o_edu, {})
check('EXP-2: one row per invitation, both date forms, no result column', h == ex.STATUS_HEADERS and len(r) == 3
      and not any('نتیجه' in c or 'پاسخ' in c for c in h) and all(len(x) == 10 for x in r))
done = [x for x in r if x[0] == 'دانش‌آموز یک'][0]
check('EXP-2: a finished invitation has a completion date, an open one does not',
      done[3] == dict(A._fields['state'].selection)['done'] and done[8] and done[9] and not [x for x in r if x[0] == 'دانش‌آموز دو'][0][8])
check('EXP-2: a counselor sees only the invitations of her visible clients', sorted(x[0] for x in ex.status_rows(env, c1_edu, {})[1]) == ['دانش‌آموز سه', 'دانش‌آموز یک'])
check('EXP-2: the instrument filter', len(ex.status_rows(env, o_emp, {'instrument_id': str(plain.id)})[1]) == 3 and not ex.status_rows(env, o_emp, {'instrument_id': str(talent.id)})[1])

# ---- EXP-3 results
h, r = ex.result_rows(env, hr_emp, {})
check('EXP-3: the hr admin gets bands only for the shared, finished result', len(r) > 0 and all(x[0] == 'استخدام‌شونده یک' for x in r)
      and all(x[4] in ('کم', 'متوسط', 'زیاد') for x in r) and all(x[5:] == [''] * 6 for x in r), str(r[:2]))
check('EXP-3: no answers column, no scores for an ordinary instrument', not any('پاسخ' in c for c in h))
h, r = ex.result_rows(env, o_edu, {})
tal = [x for x in r if x[2] == talent.name]
check('EXP-3: the education owner gets two TALENT field rows per finished result', len(tal) == 4 and len(r) == 4, str(len(r)))
check('EXP-3: TALENT rows hold the field number, the five scales and the total, never the field name',
      tal[0][3] == 1 and tal[0][4] == '' and tal[0][5:] == [61.5, 70, 48, 80, 55, 62.9] and tal[1][3] == 2 and SECRET not in json.dumps(r, ensure_ascii=False)
      and 'زمینهٔ دوم' not in json.dumps(r, ensure_ascii=False))
data = ex.to_csv(h, r)
check('EXP-3: the file holds no field name either', SECRET.encode() not in data)
h, r = ex.result_rows(env, c1_edu, {})
check('EXP-3: row level filter: a counselor sees only visible clients in the builder', all(x[0] != 'دانش‌آموز دو' for x in r))

# ---- jobs
j1 = J.ts_export_create(o_edu, 'export_clients', 'csv', {})
check('job: a small export runs at once and finishes', j1.state == 'done' and j1.result_attachment_id and j1.result_attachment_id.name.endswith('.csv')
      and j1._s().get('rows') == 3, j1.state)
check('job: file name has no client data and the link lives 24 hours',
      all(ord(c) < 128 for c in j1.result_attachment_id.name) and timedelta(hours=23) < j1.expires_at - fields.Datetime.now() <= timedelta(hours=24))
data = ex_data = j1.result_attachment_id.sudo().raw
data = bytes(data) if isinstance(data, (bytes, bytearray)) else data.content
check('job: the stored file starts with the BOM', data.startswith(b'\xef\xbb\xbf'))
check('job: only the requester may download, and only while the permission holds',
      j1.can_download(o_edu) and not j1.can_download(c1_edu) and not j1.can_download(hr_emp))
ev = env['ts.audit.event'].search([('event_type', '=', 'export.create'), ('workspace_id', '=', edu.id)])
check('audit: export.create is written without names or counts of people', len(ev) == 1 and 'دانش‌آموز' not in (ev.detail or '') and 'export_clients' in (ev.detail or ''))
j2 = J.ts_export_create(o_edu, 'export_status', 'xlsx', {})
check('job: xlsx export', j2.state == 'done' and j2.result_attachment_id.name.endswith('.xlsx'))
j3 = J.ts_export_create(o_edu, 'export_results', 'csv', {})
check('job: results export for an education owner', j3.state == 'done' and j3._s().get('rows') == len(ex.result_rows(env, o_edu, {})[1]))
check('P21: a counselor cannot create a clients export', raises(lambda: J.ts_export_create(c1_edu, 'export_clients', 'csv', {})))
check('P21: a reviewer cannot create any export', raises(lambda: J.ts_export_create(rv_emp, 'export_status', 'csv', {})))
check('P21: a counselor cannot create a results export', raises(lambda: J.ts_export_create(c1_edu, 'export_results', 'csv', {})))
check('a clinical panel has no results export, even for its owner', raises(lambda: J.ts_export_create(o_cli, 'export_results', 'csv', {})))
check('a clinician has no clients export', raises(lambda: J.ts_export_create(cl_cli, 'export_clients', 'csv', {})))
check('the clinical owner can still export the client list', J.ts_export_create(o_cli, 'export_clients', 'csv', {}).state == 'done')
check('an unknown kind is refused', raises(lambda: J.ts_export_create(o_edu, 'export_audit', 'csv', {})))
j4 = J.ts_export_create(hr_emp, 'export_results', 'csv', {})
check('employment: the hr admin may export results', j4.state == 'done' and j4._s().get('rows') > 0)

# the permission is checked again when a queued job runs
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '1')
jq = J.ts_export_create(o_edu, 'export_status', 'csv', {})
check('a job over the inline limit waits in the queue', jq.state == 'queued')
c1_edu_user = c1_edu.user_id
o2 = member(edu, 'owner')
jq2 = J.ts_export_create(o2, 'export_status', 'csv', {})
o2.write({'role': 'counselor'})
env.flush_all()
from unittest.mock import patch
with patch.object(env.cr, 'commit', lambda: None):
    for _k in range(3):
        J._cron_run_jobs()
jq.invalidate_recordset()
jq2.invalidate_recordset()
check('the cron finishes the queued job of a member who still holds the permission', jq.state == 'done')
check('P21: a member who lost the permission before the run gets a failed job and no file', jq2.state == 'failed' and jq2.error_code == 'forbidden' and not jq2.result_attachment_id)
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '500')

# expiry
j1.write({'expires_at': fields.Datetime.now() - timedelta(minutes=1)})
check('after the expiry the file is not downloadable', not j1.can_download(o_edu))
att = j1.result_attachment_id
env['ts.job']._cron_expire_jobs()
check('the expiry cron removes the file and marks the job expired', j1.state == 'expired' and not j1.result_attachment_id and not att.exists())

passed = sum(1 for _n_, ok in results if ok)
print('SUMMARY %d/%d passed' % (passed, len(results)))
env.cr.rollback()
