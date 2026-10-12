"""Clinic phase 5, website side (website 4 only; every route answers 404 elsewhere, like the other ts routes).

* /i/<code>, /j/<code>: SMS short links -> 302 to /invite/<token>, /join/<token>; /n/<id>: a staff notice -> its own page
  (/my/notifications/<id> checks that the reader owns it).
* PDF downloads, generated on demand and never stored: participant (own attempt / battery only) and panel (through
  `result_level()` exactly like the screen pages; level 'status' or 'none' -> 404 with a deny event). Audited
  `result.print` with kind 'pdf'.
* Settings «هویت مرکز در گزارش‌ها» (panel:profile + owner/clinic director of a counseling-center or education panel) and the
  member page «هویت شما در گزارش‌ها» (the member, or owner/admin/clinic director for title and «show on report»). A member
  without members:read (a counselor) may open their own member page for this section.
"""
import logging
import re

from odoo import http
from odoo.exceptions import UserError, ValidationError
from urllib.parse import quote

from odoo.http import request


def content_disposition(filename):
    """RFC 6266 attachment header with an ASCII fallback and the UTF-8 name (odoo.http no longer exports it in Odoo 20)."""
    ascii_name = ''.join(c if c.isascii() and c not in '"\\' else '_' for c in filename) or 'report.pdf'
    return 'attachment; filename="%s"; filename*=UTF-8\'\'%s' % (ascii_name, quote(filename))

from odoo.addons.ts_assessment.controllers.main import _my_attempt, _ts_site_or_404
from odoo.addons.ts_battery.controllers.main import TsBatteryMembers, TsBatteryPanelReport
from odoo.addons.ts_org.models.panel import ROLE_LABELS
from odoo.addons.ts_panel.controllers.base import (deny, flash_error, flash_ok, forbidden, member_or_404, render_in_shell,
                                                   require)
from odoo.addons.ts_panel.controllers.members import MEMBER_STATE, _other_member, jalali_or_dash
from odoo.addons.ts_panel.controllers.reports import TsPanelReports

from ..models.short import CODE_RE

_logger = logging.getLogger(__name__)
PDF_ERROR = 'ساختن فایل PDF الان ممکن نشد. چند دقیقه بعد دوباره امتحان کنید یا از دکمهٔ «چاپ» صفحهٔ گزارش استفاده کنید.'


def _pdf(report_xmlid, res_id, data, filename, fallback_url=None):
    """Render one PDF and answer it as a download (no attachment is created: the reports have no `attachment` expression).
    When the server has no PDF engine (wkhtmltopdf is not installed on eot-odoo-prod) or rendering fails, the reader is sent
    to the report page in print mode (`?print=1`: the browser's print dialog, where «ذخیره به‌صورت PDF» is one choice)."""
    try:
        pdf, _kind = request.env['ir.actions.report'].sudo()._render_qweb_pdf(report_xmlid, [res_id], data=data)
    except Exception as e:      # noqa: BLE001
        if 'pdf engine' in str(e).lower():
            _logger.info('ts_brand: no PDF engine on this server; %s falls back to print mode', report_xmlid)
        else:
            _logger.exception('ts_brand: PDF %s for %s failed', report_xmlid, res_id)
        if fallback_url:
            return request.redirect(fallback_url + ('&' if '?' in fallback_url else '?') + 'print=1', code=303, local=True)
        return request.make_response(PDF_ERROR, headers=[('Content-Type', 'text/plain; charset=utf-8')], status=503)
    return request.make_response(pdf, headers=[
        ('Content-Type', 'application/pdf'), ('Content-Length', str(len(pdf))),
        ('Content-Disposition', content_disposition(filename)),
        ('Cache-Control', 'no-store, private'), ('X-Robots-Tag', 'noindex')])


def _safe_name(ref):
    return re.sub(r'[^A-Za-z0-9_-]+', '-', ref or 'report').strip('-') or 'report'


class TsBrandLinks(http.Controller):

    @http.route('/i/<string:code>', type='http', auth='public', website=True, sitemap=False)
    def short_invite(self, code, **kw):
        _ts_site_or_404()
        if not CODE_RE.match(code or ''):
            raise request.not_found()
        a = request.env['ts.assignment'].sudo().search([('short_code', '=', code)], limit=1)  # the code is the key of a public link
        if not a:
            raise request.not_found()
        return request.redirect('/invite/%s' % a.token, code=302)

    @http.route('/j/<string:code>', type='http', auth='public', website=True, sitemap=False)
    def short_join(self, code, **kw):
        _ts_site_or_404()
        if not CODE_RE.match(code or ''):
            raise request.not_found()
        inv = request.env['ts.member.invite'].sudo().search([('short_code', '=', code)], limit=1)
        if not inv:
            raise request.not_found()
        return request.redirect('/join/%s' % inv.token, code=302)

    @http.route('/n/<int:nid>', type='http', auth='public', website=True, sitemap=False)
    def short_notice(self, nid, **kw):
        _ts_site_or_404()
        return request.redirect('/my/notifications/%d' % nid, code=302)

    # ------------------------------------------------------------------ participant PDFs (own only)
    @http.route('/my/assessments/<int:attempt_id>/pdf', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def my_pdf(self, attempt_id, **kw):
        _ts_site_or_404()
        at = _my_attempt(attempt_id=attempt_id)
        if at.state != 'done' or not at.released:
            raise request.not_found()
        resp = _pdf('ts_brand.action_attempt_pdf', at.id, {'mode': 'self'}, 'estedadyab-%s.pdf' % _safe_name(at.name),
                    fallback_url='/my/assessments/%d' % at.id)
        if resp.status_code in (200, 303):
            request.env['ts.audit.event'].sudo().log('result.print', at, kind='pdf' if resp.status_code == 200 else 'print')
        return resp

    @http.route('/my/assessments/battery/<int:assignment_id>/pdf', type='http', auth='user', website=True, methods=['GET'],
                sitemap=False)
    def my_battery_pdf(self, assignment_id, **kw):
        _ts_site_or_404()
        a = request.env['ts.assignment'].sudo().search([
            ('id', '=', int(assignment_id)), ('user_id', '=', request.env.user.id), ('battery_id', '!=', False)], limit=1)
        if not a or not a.ts_battery_attempts().filtered(lambda t: t.state == 'done' and t.released):
            raise request.not_found()
        resp = _pdf('ts_brand.action_battery_pdf', a.id, {'mode': 'self'}, 'estedadyab-%s.pdf' % _safe_name(a.name),
                    fallback_url='/my/assessments/battery/%d' % a.id)
        if resp.status_code in (200, 303):
            request.env['ts.audit.event'].sudo().log('result.print', a, workspace=a.workspace_id,
                                                     kind='pdf' if resp.status_code == 200 else 'print', battery=a.battery_id.code)
        return resp

    # ------------------------------------------------------------------ panel PDFs (result_level, like the screen)
    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/r/<int:aid>/pdf', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def panel_pdf(self, ws_id, cid, aid, **kw):
        me, client, at, level = TsPanelReports._result_context(self, ws_id, cid, aid)
        if level not in ('summary', 'education', 'clinical'):
            deny(me, 'result_level_status', attempt=at.id)
            raise request.not_found()
        resp = _pdf('ts_brand.action_attempt_pdf', at.id, {'mode': 'panel', 'level': level},
                    'estedadyab-%s.pdf' % _safe_name(at.name),
                    fallback_url='/my/workspaces/%d/clients/%d/r/%d' % (me.workspace_id.id, client.id, at.id))
        if resp.status_code in (200, 303):
            request.env['ts.audit.event'].sudo().log('result.print', at, workspace=me.workspace_id, member=me, level=level,
                                                     kind='pdf' if resp.status_code == 200 else 'print')
        return resp

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/b/<int:aid>/pdf', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def panel_battery_pdf(self, ws_id, cid, aid, **kw):
        me, client, a, level = TsBatteryPanelReport._context(self, ws_id, cid, aid)
        if level not in ('summary', 'education', 'clinical'):
            deny(me, 'result_level_status', assignment=a.id)
            raise request.not_found()
        resp = _pdf('ts_brand.action_battery_pdf', a.id, {'mode': 'panel', 'level': level},
                    'estedadyab-%s.pdf' % _safe_name(a.name),
                    fallback_url='/my/workspaces/%d/clients/%d/b/%d' % (me.workspace_id.id, client.id, a.id))
        if resp.status_code in (200, 303):
            request.env['ts.audit.event'].sudo().log('result.print', a, workspace=me.workspace_id, member=me, level=level,
                                                     kind='pdf' if resp.status_code == 200 else 'print', battery=a.battery_id.code)
        return resp

    # ------------------------------------------------------------------ settings: the panel's identity on reports
    @http.route('/my/workspaces/<int:ws_id>/settings/brand', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def settings_brand(self, ws_id, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'panel:profile', 'settings')
        if denied:
            return denied
        if not me.ts_brand_manager():
            return forbidden(me, 'brand:panel', 'settings')
        try:
            changed = me.workspace_id.ts_brand_save(me, post)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('هویت مرکز ذخیره شد.' if changed else 'تغییری نبود.')
        return request.redirect('/my/workspaces/%s/settings#tsbr-org' % ws_id)


class TsBrandMembers(TsBatteryMembers):

    @http.route()
    def member_page(self, ws_id, mid, **kw):
        me = member_or_404(ws_id)
        if int(mid) == me.id and not me.has_perm('members:read'):
            # a counselor has no members list; their own page carries only «هویت شما در گزارش‌ها»
            key = me.ts_state_key()
            return render_in_shell(
                'ts_panel.member', me, 'members', me.user_id.name, m=me, state=MEMBER_STATE[key][0], pill=MEMBER_STATE[key][1],
                m_role=ROLE_LABELS.get(me.role, me.role), clients=me.ts_client_count() if me.active else 0,
                last=jalali_or_dash(me.ts_last_activity()), can_manage=False, is_self=True, roles=[], chosen=me.role,
                resumed=False, clinical=me.workspace_id.purpose == 'clinical', can_catalog=False, own_only=True)
        return super().member_page(ws_id, mid, **kw)

    @http.route('/my/workspaces/<int:ws_id>/members/<int:mid>/brand', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def member_brand(self, ws_id, mid, **post):
        me = member_or_404(ws_id)
        own = int(mid) == me.id
        if not own and not me.has_perm('members:read'):
            return forbidden(me, 'members:read', 'members')
        m = me if own else _other_member(me, mid)
        files = request.httprequest.files
        photo, sig = files.get('photo'), files.get('signature')
        vals = {'title': post.get('title', ''), 'show_on_report': bool(post.get('show_on_report'))}
        if own and 'report_bio' in post:
            vals['report_bio'] = post.get('report_bio', '')
        try:
            changed = m.ts_brand_save(
                me, vals,
                photo=photo.read(600 * 1024) if own and photo and photo.filename else None,
                signature=sig.read(400 * 1024) if own and sig and sig.filename else None,
                remove_photo=own and bool(post.get('remove_photo')), remove_signature=own and bool(post.get('remove_signature')))
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('ذخیره شد.' if changed else 'تغییری نبود.')
        return request.redirect('/my/workspaces/%s/members/%s#tsbr-member' % (ws_id, m.id))
