"""Background jobs of the panel (S8, 04_data_model.md 3.7): a file import now, exports and reports in later stages.

A job belongs to its requester: only that account can open its page or download its file, and the permission of the job
kind is checked again at download time (P21). `params` holds column mapping and filter ids only; `summary` holds counts;
the error report holds row numbers and reasons, never row content. The uploaded source file is deleted when the job ends.
"""
import base64
import json
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from . import exporter, importer

KINDS = [('export_clients', 'برون‌بری شرکت‌کنندگان'), ('export_status', 'برون‌بری وضعیت دعوت‌ها'),
         ('export_results', 'برون‌بری نتایج'), ('export_audit', 'برون‌بری رویدادها'),
         ('import_clients', 'ورود شرکت‌کنندگان از فایل'), ('group_report', 'گزارش گروهی'), ('data_export', 'نسخهٔ داده‌های من')]
KIND_PERM = {'import_clients': 'clients:import', 'export_clients': 'clients:export', 'export_status': 'clients:export',
             'export_results': 'results:export', 'export_audit': 'audit:export', 'group_report': 'reports:group'}
EXPORT_ROWS = {'export_clients': exporter.client_rows, 'export_status': exporter.status_rows,
               'export_results': exporter.result_rows}
STATES = [('draft', 'در حال آماده‌سازی'), ('queued', 'در صف'), ('running', 'در حال اجرا'), ('done', 'انجام شد'),
          ('failed', 'ناموفق'), ('expired', 'منقضی')]


def att_bytes(att):
    """Odoo 20: `raw` is bytes or a lazy BinaryValue (filestore); always return bytes."""
    r = att.sudo().raw
    return bytes(r) if isinstance(r, (bytes, bytearray)) else r.content


class TsJob(models.Model):
    _name = 'ts.job'
    _description = 'Talent Search panel job'
    _order = 'id desc'

    workspace_id = fields.Many2one('ts.workspace', index=True, ondelete='restrict')
    member_id = fields.Many2one('ts.workspace.member', ondelete='set null')
    user_id = fields.Many2one('res.users', index=True, ondelete='set null')
    kind = fields.Selection(KINDS, required=True)
    state = fields.Selection(STATES, default='draft', required=True, index=True)
    params = fields.Text(help='JSON: column mapping and filter ids only')
    progress = fields.Integer()
    total = fields.Integer()
    result_attachment_id = fields.Many2one('ir.attachment', ondelete='set null')
    source_attachment_id = fields.Many2one('ir.attachment', ondelete='set null')
    summary = fields.Text(help='JSON: counts')
    error_code = fields.Char()
    expires_at = fields.Datetime(index=True)

    # ------------------------------------------------------------------ helpers
    def _p(self):
        self.ensure_one()
        return json.loads(self.params or '{}')

    def _set_p(self, **kw):
        p = self._p()
        p.update(kw)
        self.params = json.dumps(p)

    def _s(self):
        return json.loads(self.summary or '{}')

    @api.model
    def _ttl_hours(self):
        return self.env['ir.config_parameter'].sudo().get_int('ts_panel.export_ttl_hours', 24) or 24

    @api.model
    def _inline_rows(self):
        return self.env['ir.config_parameter'].sudo().get_int('ts_panel.job_inline_rows', 500) or 500

    def _attach(self, name, data, mimetype):
        return self.env['ir.attachment'].sudo().create({
            'name': name, 'raw': data if isinstance(data, bytes) else data.encode('utf-8'), 'res_model': 'ts.job', 'res_id': self.id,
            'mimetype': mimetype, 'public': False})

    def can_download(self, member):
        """P21: the requester only, still holding the permission of the kind, and before the expiry."""
        self.ensure_one()
        return bool(self.state == 'done' and self.result_attachment_id and self.user_id == member.user_id
                    and self.member_id == member and self.workspace_id == member.workspace_id
                    and member.can_act() and member.has_perm(KIND_PERM.get(self.kind, 'none:none'))
                    and (not self.expires_at or self.expires_at >= fields.Datetime.now()))

    # ------------------------------------------------------------------ import: prepare, map, preview, start
    @api.model
    def ts_import_prepare(self, member, filename, data):
        """Check and keep the uploaded file; returns the draft job. Raises importer.FileProblem."""
        headers, rows = importer.parse_table(data, filename)       # raises FileProblem before anything is stored
        job = self.sudo().create({'workspace_id': member.workspace_id.id, 'member_id': member.id, 'user_id': member.user_id.id,
                                  'kind': 'import_clients', 'state': 'draft', 'total': len(rows)})
        att = job._attach('import-source', data, 'application/octet-stream')
        job.source_attachment_id = att.id
        mapping = importer.auto_map(headers)
        job._set_p(headers=headers, mapping={str(k): v for k, v in mapping.items()}, ext=(filename or '').lower().rsplit('.', 1)[-1])
        return job

    def ts_mapping(self):
        self.ensure_one()
        return {int(k): v for k, v in self._p().get('mapping', {}).items()}

    def ts_set_mapping(self, pairs):
        """pairs = {column index: field or ''}; one field once; `name` required."""
        self.ensure_one()
        headers = self._p().get('headers', [])
        valid = {f for f, _l in importer.FIELDS}
        mapping, used = {}, set()
        for idx, f in pairs.items():
            if f and f in valid and 0 <= idx < len(headers) and f not in used:
                mapping[str(idx)] = f
                used.add(f)
        if 'name' not in used:
            raise importer.FileProblem('no_name')
        self._set_p(mapping=mapping)

    def _parsed_table(self):
        self.ensure_one()
        att = self.source_attachment_id
        if not att:
            raise UserError('فایل این کار دیگر نگه‌داری نمی‌شود.')
        return importer.parse_table(att_bytes(att), 'x.' + (self._p().get('ext') or 'csv'))

    def ts_preview(self):
        """Counts and the first rows with a problem; writes nothing."""
        self.ensure_one()
        _h, rows = self._parsed_table()
        items = importer.plan(self.env, self.workspace_id.id, rows, self.ts_mapping())
        errs = [{'n': it['n'], 'err': it['err']} for it in items if it['action'] == 'error'][:20]
        return importer.summarize(items), errs

    def ts_start(self):
        """Queue the import; a small file runs at once, a large one waits for the cron runner."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('این کار پیش‌تر شروع شده است.')
        if 'name' not in self.ts_mapping().values():
            raise importer.FileProblem('no_name')
        self.state = 'queued'
        if self.total <= self._inline_rows():
            self.ts_run(commit=False)

    # ------------------------------------------------------------------ run
    def ts_run(self, commit=True):
        self.ensure_one()
        if self.state not in ('queued', 'running'):
            return
        self.state = 'running'
        if commit:
            self.env.flush_all()
            self.env.cr.commit()
        try:
            if commit:
                getattr(self, '_run_' + self.kind)(True)
            else:
                with self.env.cr.savepoint():       # a failure leaves no half import behind
                    getattr(self, '_run_' + self.kind)(False)
        except importer.FileProblem as e:
            self._fail(e.code)
        except Exception:
            self._fail('internal')
        if commit:
            self.env.flush_all()
            self.env.cr.commit()

    def _fail(self, code):
        self.write({'state': 'failed', 'error_code': code})
        self._drop_source()
        self.env['ts.audit.event'].log('job.failed', self, workspace=self.workspace_id, kind=self.kind, code=code)

    def _drop_source(self):
        att = self.source_attachment_id
        self.source_attachment_id = False
        if att:
            att.sudo().unlink()

    def _run_import_clients(self, commit):
        _h, rows = self._parsed_table()
        items = importer.plan(self.env, self.workspace_id.id, rows, self.ts_mapping())
        res = importer.apply_plan(self.env, self.workspace_id, self.user_id.id, items, commit=self.env.cr.commit if commit else None)
        res['error'] = sum(1 for it in items if it['action'] == 'error')
        vals = {'state': 'done', 'summary': json.dumps(res), 'progress': len(rows), 'total': len(rows),
                'expires_at': fields.Datetime.now() + timedelta(hours=self._ttl_hours())}
        if res['error']:
            vals['result_attachment_id'] = self._attach('import-errors.csv', importer.error_report(items), 'text/csv').id
        self.write(vals)
        self._drop_source()
        self.env['ts.audit.event'].log('import.run', self, workspace=self.workspace_id, member=self.member_id,
                                       created=res['create'], updated=res['update'], unchanged=res['same'], errors=res['error'])


    # ------------------------------------------------------------------ exports (S9)
    @api.model
    def ts_export_create(self, member, kind, fmt, params=None):
        """Create and start an export job for `member`. Raises UserError when the kind is not allowed for this member or
        panel. A small export runs at once, a large one waits for the cron runner."""
        if kind not in EXPORT_ROWS or not member.can_act() or not member.has_perm(KIND_PERM[kind]):
            raise UserError('این خروجی برای شما ممکن نیست.')
        if kind == 'export_results' and member.workspace_id.purpose not in ('education', 'employment'):
            raise UserError('این نوع پنل خروجی نتایج ندارد.')
        fmt = fmt if fmt in ('csv', 'xlsx') else 'csv'
        clean = {k: str(v) for k, v in (params or {}).items() if k in ('group_id', 'instrument_id', 'state') and v}
        clean['format'] = fmt
        job = self.sudo().create({'workspace_id': member.workspace_id.id, 'member_id': member.id, 'user_id': member.user_id.id,
                                  'kind': kind, 'state': 'queued', 'params': json.dumps(clean)})
        job.total = exporter.count_rows(self.env, member, kind, clean)
        self.env['ts.audit.event'].sudo().log('export.create', job, workspace=job.workspace_id, member=member, kind=kind, format=fmt)
        if job.total <= self._inline_rows():
            job.ts_run(commit=False)
        return job

    def _run_export(self, commit):
        m = self.member_id
        if not (m.exists() and m.user_id == self.user_id and m.can_act() and m.has_perm(KIND_PERM[self.kind])
                and (self.kind != 'export_results' or self.workspace_id.purpose in ('education', 'employment'))):
            raise importer.FileProblem('forbidden')            # the permission is checked again when the job runs (P21)
        p = self._p()
        headers, rows = EXPORT_ROWS[self.kind](self.env, m, p)
        data, ext, mime = exporter.render(p.get('format'), headers, rows)
        stamp = exporter.date_cols(fields.Datetime.now())[1].replace('-', '')
        att = self._attach('%s-%s.%s' % (self.kind.replace('export_', ''), stamp, ext), data, mime)
        self.write({'state': 'done', 'summary': json.dumps({'rows': len(rows)}), 'progress': len(rows), 'total': len(rows),
                    'result_attachment_id': att.id, 'expires_at': fields.Datetime.now() + timedelta(hours=self._ttl_hours())})

    def _run_export_clients(self, commit):
        self._run_export(commit)

    def _run_export_status(self, commit):
        self._run_export(commit)

    def _run_export_results(self, commit):
        self._run_export(commit)

    # ------------------------------------------------------------------ my data (S15, ACC-5)
    def _run_data_export(self, commit):
        """The requester's own data as a ZIP (JSON + CSV); no panel, no member."""
        Req = self.env['ts.data.request']
        payload = Req.ts_payload(self.user_id)
        stamp = exporter.date_cols(fields.Datetime.now())[1].replace('-', '')
        att = self._attach('my-data-%s.zip' % stamp, Req.ts_zip(payload), 'application/zip')
        rows = sum(len(v) if isinstance(v, list) else 1 for v in payload.values())
        self.write({'state': 'done', 'summary': json.dumps({'rows': rows}), 'progress': rows, 'total': rows,
                    'result_attachment_id': att.id, 'expires_at': fields.Datetime.now() + timedelta(hours=24)})

    def can_download_own(self, user):
        """A participant's own data file: the requester only, before the 24 h expiry."""
        self.ensure_one()
        return bool(self.kind == 'data_export' and self.state == 'done' and self.result_attachment_id and self.user_id == user
                    and (not self.expires_at or self.expires_at >= fields.Datetime.now()))

    # ------------------------------------------------------------------ crons
    @api.model
    def _cron_run_jobs(self):
        """One queued job per run, locked so that two workers never take the same one."""
        self.env.flush_all()
        self.env.cr.execute("SELECT id FROM ts_job WHERE state = 'queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1")
        row = self.env.cr.fetchone()
        if row:
            self.browse(row[0]).sudo().ts_run(commit=True)
        return bool(row)

    @api.model
    def _cron_expire_jobs(self):
        late = self.sudo().search([('state', '=', 'done'), ('expires_at', '!=', False), ('expires_at', '<', fields.Datetime.now())])
        for job in late:
            att = job.result_attachment_id
            job.write({'state': 'expired', 'result_attachment_id': False})
            if att:
                att.sudo().unlink()
        stale = self.sudo().search([('state', 'in', ('draft', 'failed')), ('create_date', '<', fields.Datetime.now() - timedelta(hours=24))])
        for job in stale:
            job._drop_source()
        return len(late)
