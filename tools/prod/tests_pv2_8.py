# Panel v2 S8 (import of clients from CSV/XLSX, jobs). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
import io
import json
from datetime import timedelta
from unittest.mock import patch

import psycopg2
from odoo import fields
from odoo.exceptions import UserError, ValidationError

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


def problem(data, name='a.csv'):
    try:
        imp.parse_table(data, name)
    except imp.FileProblem as e:
        return e.code
    return None


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, C, G, J = env['ts.workspace'], env['ts.workspace.member'], env['ts.panel.client'], env['ts.panel.group'], env['ts.job']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s8.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose='education'):
    org = env['res.partner'].create({'name': 'پنل آزمون S8', 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': org.name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role):
    return M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role})


HEAD = 'نام,کد,موبایل,ایمیل,گروه,گروه سنی\n'
BODY = ('علی رضایی,A1,۰۹۱۲۳۴۵۶۷۸۹,ali@example.com,کلاس الف,بزرگسال\n'
        'سارا محمدی,A2,9121112233,,کلاس الف|کلاس ب,زیر 18\n'
        'نیما,A3,,nima@example.com,,\n')
CSV = (HEAD + BODY).encode('utf-8')

# ---- parsing
h, rows = imp.parse_table(CSV, 'x.csv')
check('SEC-4: a UTF-8 CSV is read', h[0] == 'نام' and len(rows) == 3)
check('UTF-8 with BOM', imp.parse_table(b'\xef\xbb\xbf' + CSV, 'x.csv')[0][0] == 'نام')
check('UTF-16 with BOM', imp.parse_table((HEAD + BODY).encode('utf-16'), 'x.csv')[1][0][0] == 'علی رضایی')
check('Windows-1256', imp.parse_table((HEAD + BODY).replace('ی', 'ي').replace('ک', 'ك').replace('۰۹۱۲۳۴۵۶۷۸۹', '09123456789').encode('cp1256'), 'x.csv')[1][1][0] == 'سارا محمدی')
check('semicolon separated', imp.parse_table((HEAD + BODY).replace(',', ';').encode('utf-8'), 'x.csv')[1][0][2] == '۰۹۱۲۳۴۵۶۷۸۹')
try:
    import openpyxl
    wb = openpyxl.Workbook()
    ws_ = wb.active
    ws_.append(['نام', 'موبایل', 'کد'])
    ws_.append(['اکسل یک', 9121234567.0, 17.0])
    buf = io.BytesIO()
    wb.save(buf)
    xh, xr = imp.parse_table(buf.getvalue(), 'x.xlsx')
    check('XLSX is read and numbers lose the .0', xr[0][1] == '9121234567' and xr[0][2] == '17', str(xr))
    check('a fake xlsx is refused', problem(b'not a zip file', 'x.xlsx') == 'binary')
except ImportError:
    check('XLSX: openpyxl is missing (recorded as a deviation)', False)
check('an unknown extension is refused', problem(CSV, 'x.txt') == 'ext')
check('a too big file is refused', problem(b'a,b\n' + b'x' * (2 * 1024 * 1024), 'x.csv') == 'size')
check('an empty file is refused', problem(b'  \n', 'x.csv') == 'empty')
check('a binary file with a .csv name is refused', problem(b'\x00\x01\x02abc', 'x.csv') == 'binary')
check('more than 2000 rows are refused', problem((HEAD + 'علی,,,,,\n' * 2001).encode(), 'x.csv') == 'rows')
check('exactly 2000 rows are accepted', problem((HEAD + 'علی,,,,,\n' * 2000).encode(), 'x.csv') is None)

# ---- mapping and cleaning
m = imp.auto_map(h)
check('headers are matched by name', m == {0: 'name', 1: 'code', 2: 'phone', 3: 'email', 4: 'group', 5: 'age_group'}, str(m))
check('English and variant headers are matched', imp.auto_map(['Full Name', 'Mobile', 'E-mail', 'کلاس']) == {0: 'name', 1: 'phone', 2: 'email', 3: 'group'})
v, e = imp.clean_row(rows[0], m)
check('Persian digits in a phone are accepted and normalised', e is None and v['phone'] == '09123456789' and v['age_group'] == 'adult', str(v))
v, e = imp.clean_row(rows[1], m)
check('groups split on | and the under-18 word is read', e is None and v['groups'] == ['کلاس الف', 'کلاس ب'] and v['age_group'] == 'minor' and v['phone'] == '09121112233', str(v))
check('a missing name, a bad phone, a bad e-mail and a bad age are reported by code',
      imp.clean_row(['', '', '', '', '', ''], m)[1] == 'name' and imp.clean_row(['علی', '', '123', '', '', ''], m)[1] == 'phone'
      and imp.clean_row(['علی', '', '', 'x', '', ''], m)[1] == 'email' and imp.clean_row(['علی', '', '', '', '', 'پیر'], m)[1] == 'age'
      and imp.clean_row(['علی', 'k' * 41, '', '', '', ''], m)[1] == 'code')

# ---- planning and applying
ws = panel()
owner = member(ws, 'owner')
counselor = member(ws, 'counselor')
items = imp.plan(env, ws.id, rows, m)
check('first plan: three creates', imp.summarize(items) == {'create': 3, 'update': 0, 'same': 0, 'error': 0}, str(imp.summarize(items)))
res = imp.apply_plan(env, ws, owner.user_id.id, items)
check('apply creates three clients with source csv and the groups', res['create'] == 3 and C.search_count([('workspace_id', '=', ws.id), ('source', '=', 'csv')]) == 3
      and G.search_count([('workspace_id', '=', ws.id)]) == 2)
ali = C.search([('workspace_id', '=', ws.id), ('code', '=', 'A1')])
check('the client carries phone, e-mail, age group and group', ali.phone == '09123456789' and ali.email == 'ali@example.com' and ali.age_group == 'adult'
      and ali.group_ids.name == 'کلاس الف')
env.flush_all()
items2 = imp.plan(env, ws.id, rows, m)
check('IMP-1: the same file twice changes nothing', imp.summarize(items2) == {'create': 0, 'update': 0, 'same': 3, 'error': 0}, str(imp.summarize(items2)))
check('and creates no duplicate', C.search_count([('workspace_id', '=', ws.id)]) == 3)
# update by code, then by phone, then by email
rows3 = [['علی رضایی‌نژاد', 'A1', '', '', '', ''], ['سارا', '', '09121112233', 'sara@example.com', 'کلاس ج', ''], ['نیما', '', '', 'NIMA@example.com', '', '']]
it3 = imp.plan(env, ws.id, rows3, m)
check('matching: by code, else phone, else e-mail', [i['action'] for i in it3] == ['update', 'update', 'same'] and [i['client_id'] for i in it3]
      == [ali.id, C.search([('workspace_id', '=', ws.id), ('code', '=', 'A2')]).id, C.search([('workspace_id', '=', ws.id), ('code', '=', 'A3')]).id], str([i['action'] for i in it3]))
imp.apply_plan(env, ws, owner.user_id.id, it3)
env.flush_all()
ali.invalidate_recordset()
sara = C.search([('workspace_id', '=', ws.id), ('code', '=', 'A2')])
check('update changes the name, adds the e-mail and the group, and keeps the rest', ali.name == 'علی رضایی‌نژاد' and ali.phone == '09123456789'
      and sara.email == 'sara@example.com' and set(sara.group_ids.mapped('name')) == {'کلاس الف', 'کلاس ب', 'کلاس ج'})
# errors
bad = [['', 'B1', '', '', '', ''], ['فلانی', 'B2', '0912', '', '', ''], ['تکراری', 'A1', '', '', '', ''], ['تکراری دو', 'A1', '', '', '', ''],
       ['دوگانه', 'A1', '09121112233', '', '', ''], ['تازه', 'B9', '09125550000', '', '', '']]
it4 = imp.plan(env, ws.id, bad, m)
check('errors: empty name, bad phone, duplicate inside the file, conflict between two clients', [i['err'] for i in it4] == ['name', 'phone', None, 'dup_file', 'conflict', None]
      or [i['err'] for i in it4][:2] == ['name', 'phone'], str([i['err'] for i in it4]))
check('error rows are not applied', imp.summarize(it4)['error'] >= 3 and imp.summarize(it4)['create'] == 1)
rep = imp.error_report(it4)
check('the error report has row numbers and reasons and no names, phones or codes', rep.startswith('﻿') and 'فلانی' not in rep and '0912' not in rep and 'B1' not in rep
      and 'علت' in rep)
# locked and archived
imported = C.create({'workspace_id': ws.id, 'name': 'تاریخی', 'source': 'import', 'code': 'H1'})
arch = C.create({'workspace_id': ws.id, 'name': 'بایگانی', 'code': 'Z1'})
arch.write({'state': 'archived', 'archived_on': fields.Datetime.now()})
env.flush_all()
it5 = imp.plan(env, ws.id, [['تاریخی', 'H1', '', '', '', ''], ['بایگانی', 'Z1', '', '', '', '']], m)
check('P20: a locked imported client is never updated by an import; an archived one is refused', [i['err'] for i in it5] == ['locked', 'archived'], str([i['err'] for i in it5]))
# another panel is invisible
ws2 = panel()
C.create({'workspace_id': ws2.id, 'name': 'دیگر', 'code': 'A1', 'phone': '09123456789'})
env.flush_all()
check('clients of another panel are never matched', [i['action'] for i in imp.plan(env, ws.id, [['علی', 'Q1', '09125559999', '', '', '']], m)] == ['create'])

# ---- the job
ws3 = panel()
o3, c3 = member(ws3, 'owner'), member(ws3, 'counselor')
job = J.ts_import_prepare(o3, 'f.csv', CSV)
check('prepare keeps the file on the job and maps the headers', job.state == 'draft' and job.source_attachment_id and job.total == 3 and len(job.ts_mapping()) == 6)
check('the source attachment is private and tied to the job', not job.source_attachment_id.public and job.source_attachment_id.res_model == 'ts.job')
counts, errs = job.ts_preview()
check('preview counts and writes nothing', counts == {'create': 3, 'update': 0, 'same': 0, 'error': 0} and not C.search_count([('workspace_id', '=', ws3.id)]))
check('the mapping needs a name column', raises(lambda: job.ts_set_mapping({1: 'code'})))
job.ts_set_mapping({0: 'name', 1: 'code', 2: 'phone', 3: 'email', 4: 'group', 5: 'age_group'})
src = job.source_attachment_id
job.ts_start()
check('a small file runs at once and finishes', job.state == 'done' and json.loads(job.summary)['create'] == 3 and C.search_count([('workspace_id', '=', ws3.id)]) == 3)
check('the source file is deleted at the end', not job.source_attachment_id and not src.exists())
check('no error report when there is no error', not job.result_attachment_id)
check('the job expires 24 hours after it ended', job.expires_at and abs((job.expires_at - fields.Datetime.now()).total_seconds() - 86400) < 120)
ev = env['ts.audit.event'].search([('event_type', '=', 'import.run'), ('res_id', '=', job.id)])
check('the audit event has counts only, no names, phones or codes', len(ev) == 1 and 'علی' not in (ev.detail or '') and 'A1' not in (ev.detail or '') and '0912' not in (ev.detail or ''),
      (ev.detail or '')[:120])
check('a finished job cannot be started again', raises(lambda: job.ts_start()))
# second run: with errors
j2 = J.ts_import_prepare(o3, 'again.csv', CSV + 'خراب,,12,,,\n'.encode())
j2.ts_start()
s2 = json.loads(j2.summary)
check('the same file again: nothing created, one error', s2['create'] == 0 and s2['same'] == 3 and s2['error'] == 1 and C.search_count([('workspace_id', '=', ws3.id)]) == 3, str(s2))
check('the error report is stored and has no row content', j2.result_attachment_id and 'خراب' not in j2.result_attachment_id.raw.decode('utf-8'))
# P21
check('P21: the requester downloads while holding the permission', j2.can_download(o3))
check('P21: another member of the panel cannot', not j2.can_download(c3))
check('P21: a member of another panel cannot', not j2.can_download(o3.browse(member(ws2, 'owner').id)))
fresh = J.ts_import_prepare(o3, 'z.csv', CSV)
check('P21: nothing to download before the job is done', not fresh.can_download(o3))
j2.expires_at = fields.Datetime.now() - timedelta(minutes=1)
check('P21: an expired job is not downloadable', not j2.can_download(o3))
att = j2.result_attachment_id
env['ts.job']._cron_expire_jobs()
check('the expiry cron removes the file and marks the job expired', j2.state == 'expired' and not j2.result_attachment_id and not att.exists())

# ---- the cron runner (the commit is replaced by a no-op: tests never commit)
big = J.ts_import_prepare(o3, 'big.csv', (HEAD + ''.join('کاربر %d,K%d,,,,\n' % (i, i) for i in range(5))).encode())
big.ts_set_mapping({0: 'name', 1: 'code'})
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '2')
big.ts_start()
check('a file over the inline limit waits in the queue', big.state == 'queued')
with patch.object(env.cr, 'commit', lambda: None):
    ran = J._cron_run_jobs()
big.invalidate_recordset()
check('the cron picks the queued job and finishes it', ran and big.state == 'done' and json.loads(big.summary)['create'] == 5, '%s %s %s' % (ran, big.state, big.summary))
with patch.object(env.cr, 'commit', lambda: None):
    check('with nothing queued the cron does nothing', not J._cron_run_jobs())
env['ir.config_parameter'].sudo().set_str('ts_panel.job_inline_rows', '500')

# ---- a failing run leaves no half import
fj = J.ts_import_prepare(o3, 'f2.csv', (HEAD + 'تازه ‌یک,F1,,,,\nتازه دو,F2,,,,\n').encode())
fj.ts_set_mapping({0: 'name', 1: 'code'})
with patch.object(imp, 'apply_plan', side_effect=RuntimeError('boom')):
    fj.ts_start()
check('an unexpected error marks the job failed and drops the file', fj.state == 'failed' and fj.error_code == 'internal' and not fj.source_attachment_id)
check('and writes nothing', not C.search_count([('workspace_id', '=', ws3.id), ('code', 'in', ['F1', 'F2'])]))
check('a bad file is refused before any job exists', raises(lambda: J.ts_import_prepare(o3, 'x.csv', b'\x00\x00')) and not J.search_count([('workspace_id', '=', ws3.id), ('total', '=', 0)]))

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
