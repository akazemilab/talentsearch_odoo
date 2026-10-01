from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_org.controllers.main import _counts, _scope
from odoo.addons.ts_org.models.panel import TERMS_VERSION

from .base import STATE_LABELS, flash_error, flash_ok, member_or_404, render_in_shell, require

# What a member sees instead of the dashboard when the panel or their own account cannot work yet.
STATE_PAGES = {
    'draft': ('پنل هنوز فعال نشده است', 'پنل در حال راه‌اندازی است. پس از فعال‌شدن می‌توانید از آن استفاده کنید.'),
    'suspended': ('این پنل موقتاً معلق است',
                  'تا رفع تعلیق، کار با شرکت‌کنندگان و نتایج ممکن نیست. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.'),
    'closed': ('این پنل بسته شده است',
               'پنل بسته شده و دعوت یا مشاهدهٔ نتیجهٔ تازه ممکن نیست. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.'),
    'verify': ('احراز صلاحیت حرفه‌ای شما در حال بررسی است',
               'تا پایان بررسی شمارهٔ پروانه یا نظام حرفه‌ای، به شرکت‌کنندگان و نتایج دسترسی ندارید. '
               'پس از تأیید، همین صفحه کامل می‌شود.'),
}


def _page_state(member):
    ws = member.workspace_id
    if ws.state in ('draft', 'suspended', 'closed'):
        return ws.state
    if member._ts_unverified_pro():
        return 'verify'
    return None


class TsPanelShell(http.Controller):

    @http.route('/my/workspaces/<int:ws_id>/home', type='http', auth='user', website=True, sitemap=False)
    def home(self, ws_id, **kw):
        member = member_or_404(ws_id)
        if not member.has_perm('panel:view'):
            return require(member, 'panel:view', 'home')
        ws = member.workspace_id
        state = _page_state(member)
        if state:
            title, text = STATE_PAGES[state]
            return render_in_shell('ts_panel.state_page', member, 'home', title, state_title=title, state_text=text)
        counts = _counts(_scope(member, request.env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id)])))
        tiles = [{'key': k, 'label': STATE_LABELS[k], 'n': counts[k],
                  'url': '/my/workspaces/%s?state=%s' % (ws.id, k)} for k in STATE_LABELS]
        return render_in_shell('ts_panel.dashboard', member, 'home', 'داشبورد', tiles=tiles,
                               total=sum(counts.values()), gated=ws.gated,
                               rejected=ws.rejected_on, rejection_note=ws.rejection_note)

    # ------------------------------------------------------------------ settings
    @http.route('/my/workspaces/<int:ws_id>/settings', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def settings(self, ws_id, **kw):
        member = member_or_404(ws_id)
        denied = require(member, 'panel:profile', 'settings')
        if denied:
            return denied
        ws = member.workspace_id
        return render_in_shell(
            'ts_panel.settings', member, 'settings', 'تنظیمات',
            can_terms=member.has_perm('panel:settings'),
            terms_current=ws.terms_version == TERMS_VERSION, terms_version=ws.terms_version,
            terms_on=ws.terms_accepted_on, contact=ws.data_contact_id.name,
            escalation=ws.escalation_contact_id.name if ws.purpose == 'clinical' else None,
            purpose_label=dict(ws._fields['purpose'].selection).get(ws.purpose),
            has_logo=bool(ws.partner_id.image_1920))

    @http.route('/my/workspaces/<int:ws_id>/settings/save', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def settings_save(self, ws_id, **post):
        member = member_or_404(ws_id)
        denied = require(member, 'panel:profile', 'settings')
        if denied:
            return denied
        logo = request.httprequest.files.get('logo')
        try:
            member.workspace_id.ts_update_profile(
                name=post.get('name'), logo_bytes=logo.read(600 * 1024) if logo and logo.filename else None)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('تغییرها ذخیره شد.')
        return request.redirect('/my/workspaces/%s/settings' % ws_id)
