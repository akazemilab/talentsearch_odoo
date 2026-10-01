"""Import of clients from a CSV or XLSX file, and the job pages (S8, IMP-1, INV-7, SEC-4).
Steps: template -> upload -> column mapping -> review -> start -> job page. The uploaded file lives only on the job and is
deleted when the job ends; the error report holds row numbers and reasons, never row content."""
import json

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_org.models.perms import ROLE_PERMS

from ..models import importer
from ..models.job import KINDS, STATES, att_bytes
from .base import flash_error, flash_ok, forbidden, member_or_404, render_in_shell, require

KIND_LABEL = dict(KINDS)
STATE_LABEL = dict(STATES)
JOB_PILL = {'done': 'ts-pill--ok', 'failed': 'ts-pill--warn', 'expired': 'ts-pill--neutral', 'queued': 'ts-pill--info',
            'running': 'ts-pill--info', 'draft': 'ts-pill--neutral'}


class TsPanelImports(http.Controller):

    def _guard(self, ws_id):
        me = member_or_404(ws_id)
        ws = me.workspace_id
        if me.can_act() and ws.gated and 'clients:import' in ROLE_PERMS.get((me.role, ws.purpose), ()):
            return me, render_in_shell('ts_panel.state_page', me, 'import', 'ورود از فایل هنوز ممکن نیست',
                                       state_title='ورود از فایل پس از تأیید پنل ممکن می‌شود',
                                       state_text='پنل شما در انتظار تأیید مالک پلتفرم است. تا آن زمان می‌توانید شرکت‌کنندگان را یکی‌یکی ثبت کنید.')
        denied = require(me, 'clients:import', 'import')
        if denied:
            return me, denied
        if not me.can_act():
            return me, forbidden(me, 'clients:import', 'import')
        return me, None

    def _job_or_404(self, me, jid, kinds=('import_clients',), states=None):
        job = request.env['ts.job'].sudo().search([('id', '=', int(jid)), ('workspace_id', '=', me.workspace_id.id)])
        if not job or job.user_id != request.env.user or job.member_id != me or (kinds and job.kind not in kinds):
            raise request.not_found()
        if states and job.state not in states:
            return None
        return job

    # ------------------------------------------------------------------ step 1
    @http.route('/my/workspaces/<int:ws_id>/import', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def start(self, ws_id, **kw):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        return render_in_shell('ts_panel.import_start', me, 'import', 'ورود از فایل', max_rows=importer.MAX_ROWS,
                               max_mb=importer.MAX_BYTES // (1024 * 1024), headers=importer.TEMPLATE_HEADERS)

    @http.route('/my/workspaces/<int:ws_id>/import/template.csv', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def template(self, ws_id, **kw):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        return request.make_response(importer.template_csv().encode('utf-8'), headers=[
            ('Content-Type', 'text/csv; charset=utf-8'), ('Content-Disposition', 'attachment; filename="clients-template.csv"'),
            ('Cache-Control', 'private, no-store')])

    @http.route('/my/workspaces/<int:ws_id>/import/upload', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def upload(self, ws_id, **post):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        f = request.httprequest.files.get('file')
        back = '/my/workspaces/%s/import' % ws_id
        if not f or not f.filename:
            flash_error('فایلی انتخاب نشده است.')
            return request.redirect(back)
        data = f.read(importer.MAX_BYTES + 1)
        try:
            job = request.env['ts.job'].ts_import_prepare(me, f.filename, data)
        except importer.FileProblem as e:
            flash_error(importer.FILE_ERRORS.get(e.code, 'فایل پذیرفته نشد.'))
            return request.redirect(back)
        return request.redirect('/my/workspaces/%s/import/%s/map' % (ws_id, job.id))

    # ------------------------------------------------------------------ step 2: map columns
    @http.route('/my/workspaces/<int:ws_id>/import/<int:jid>/map', type='http', auth='user', website=True, methods=['GET', 'POST'], sitemap=False)
    def mapping(self, ws_id, jid, **post):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        job = self._job_or_404(me, jid, states=('draft',))
        if not job:
            return request.redirect('/my/workspaces/%s/jobs/%s' % (ws_id, jid))
        headers = job._p().get('headers', [])
        if request.httprequest.method == 'POST':
            pairs = {i: (post.get('col_%d' % i) or '') for i in range(len(headers))}
            try:
                job.ts_set_mapping(pairs)
            except importer.FileProblem as e:
                flash_error(importer.FILE_ERRORS.get(e.code, 'تطبیق ستون‌ها درست نیست.'))
                return request.redirect('/my/workspaces/%s/import/%s/map' % (ws_id, job.id))
            return request.redirect('/my/workspaces/%s/import/%s/review' % (ws_id, job.id))
        return render_in_shell('ts_panel.import_map', me, 'import', 'تطبیق ستون‌ها', job=job, headers=headers, mapping=job.ts_mapping(),
                               fields=importer.FIELDS)

    # ------------------------------------------------------------------ step 3: review
    @http.route('/my/workspaces/<int:ws_id>/import/<int:jid>/review', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def review(self, ws_id, jid, **kw):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        job = self._job_or_404(me, jid, states=('draft',))
        if not job:
            return request.redirect('/my/workspaces/%s/jobs/%s' % (ws_id, jid))
        if 'name' not in job.ts_mapping().values():
            return request.redirect('/my/workspaces/%s/import/%s/map' % (ws_id, jid))
        try:
            counts, errs = job.ts_preview()
        except importer.FileProblem as e:
            flash_error(importer.FILE_ERRORS.get(e.code, 'فایل خوانده نشد.'))
            return request.redirect('/my/workspaces/%s/import' % ws_id)
        return render_in_shell('ts_panel.import_review', me, 'import', 'مرور پیش از ورود', job=job, counts=counts, errs=errs,
                               errors_text=importer.ERRORS, total=job.total)

    @http.route('/my/workspaces/<int:ws_id>/import/<int:jid>/start', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def run(self, ws_id, jid, **post):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        job = self._job_or_404(me, jid, states=('draft',))
        if job:
            try:
                job.ts_start()
            except (UserError, importer.FileProblem) as e:
                flash_error(importer.FILE_ERRORS.get(getattr(e, 'code', ''), str(e.args[0] if e.args else e)))
                return request.redirect('/my/workspaces/%s/import/%s/map' % (ws_id, jid))
        return request.redirect('/my/workspaces/%s/jobs/%s' % (ws_id, jid))

    # ------------------------------------------------------------------ the job page and its file
    @http.route('/my/workspaces/<int:ws_id>/jobs/<int:jid>', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def job(self, ws_id, jid, **kw):
        me = member_or_404(ws_id)
        job = self._job_or_404(me, jid, kinds=None)
        s = job._s()
        groups = request.env['ts.panel.group'].sudo().search_count([('workspace_id', '=', me.workspace_id.id), ('active', '=', True)])
        return render_in_shell('ts_panel.job', me, 'import' if job.kind == 'import_clients' else 'home', 'کار ' + KIND_LABEL.get(job.kind, ''),
                               job=job, s=s, kind_label=KIND_LABEL, state_label=STATE_LABEL, pill=JOB_PILL,
                               refresh=job.state in ('queued', 'running'), can_download=job.can_download(me), groups=groups,
                               err_text=importer.FILE_ERRORS.get(job.error_code or '', 'خطای داخلی؛ دوباره امتحان کنید یا با پشتیبانی تماس بگیرید.'),
                               can_campaign=me.has_perm('invites:bulk') and me.can_act())

    @http.route('/my/workspaces/<int:ws_id>/jobs/<int:jid>/download', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def download(self, ws_id, jid, **kw):
        me = member_or_404(ws_id)
        job = self._job_or_404(me, jid, kinds=None)
        if not job.can_download(me):
            raise request.not_found()
        att = job.result_attachment_id
        request.env['ts.audit.event'].sudo().log('job.download', job, workspace=job.workspace_id, member=me, kind=job.kind)
        return request.make_response(att_bytes(att), headers=[('Content-Type', att.mimetype or 'application/octet-stream'),
                                                       ('Content-Disposition', 'attachment; filename="%s"' % att.name),
                                                       ('Cache-Control', 'private, no-store')])
