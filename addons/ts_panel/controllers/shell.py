from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_org.controllers.main import TsOrg
from odoo.addons.ts_org.models.panel import TERMS_VERSION

from ..models.dashboard import PERIODS
from .base import STATE_LABELS, flash_error, flash_ok, member_or_404, render_in_shell, require
from .invites import STATE_ORDER, invite_count_by_state

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


OLD_ERRORS = {'pending': 'پنل در انتظار تأیید است؛ دعوت شرکت‌کنندهٔ واقعی پس از تأیید ممکن می‌شود.',
              'form': 'نام و سنجه را کامل کنید.', 'rule': 'این تغییر مجاز نیست.'}


class TsPanelWorkspace(TsOrg):
    """S6: the panel address itself is the dashboard. The old one-page panel moves to W/legacy (no menu entry; it is
    deleted in S20) and the old POST routes of ts_org land on the new pages through the query parameters they use."""

    @http.route()
    def workspace(self, ws_id, state=None, **kw):
        member = member_or_404(ws_id)
        if (kw.get('created') or '').isdigit():
            return request.redirect('/my/workspaces/%s/invites/%s?new=1' % (ws_id, kw['created']))
        if (kw.get('minv') or '').isdigit():       # the old invite form of colleagues redirects here
            return request.redirect('/my/workspaces/%s/members?minv=%s' % (ws_id, kw['minv']))
        if kw.get('error') in OLD_ERRORS:
            flash_error(OLD_ERRORS[kw['error']])
        if state in STATE_LABELS:
            return request.redirect('/my/workspaces/%s/invites?state=%s' % (ws_id, state))
        return self._dashboard(member, is_new=bool(kw.get('new')), period=kw.get('period'))

    @http.route('/my/workspaces/<int:ws_id>/legacy', type='http', auth='user', website=True, sitemap=False)
    def workspace_legacy(self, ws_id, state=None, **kw):
        return super().workspace(ws_id, state=state, **kw)

    @http.route()
    def invite_page(self, token, **kw):
        res = super().invite_page(token, **kw)
        a = request.env['ts.assignment'].sudo().search([('token', '=', token)], limit=1)   # ts-scope-ok: the secret token is the key of a public link
        if a and not a.user_id and a.invite_state() == 'ok':
            a.action_mark_opened()   # first visit of the link; a link preview may count too, so the panel says «بازشده», not «خوانده‌شده»
        return res

    def _setup_steps(self, member):
        """The first-steps list of a new panel (moved from the old page), pointing at the new pages."""
        ws = member.workspace_id
        if not member.has_perm('members:invite'):
            return []
        base = '/my/workspaces/%s' % ws.id
        others = len(ws.member_ids.filtered(lambda m: m.active and m != member))
        others += request.env['ts.member.invite'].sudo().search_count([('workspace_id', '=', ws.id)])
        first = request.env['ts.assignment'].sudo().search_count([('workspace_id', '=', ws.id)])
        return [
            ('پنل ساخته شد', True, None),
            ('نام و لوگوی پنل', bool(ws.partner_id.image_1920), base + '/settings'),
            ('دعوت اولین همکار', bool(others), base + '/members'),
            ('دعوت اولین شرکت‌کننده' + (' (پس از تأیید)' if ws.gated else ''), bool(first), base + '/invites/new?fresh=1'),
        ]

    def _dashboard(self, member, is_new=False, period=None):
        if not member.has_perm('panel:view'):
            return require(member, 'panel:view', 'home')
        ws = member.workspace_id
        page_state = _page_state(member)
        if page_state:
            title, text = STATE_PAGES[page_state]
            return render_in_shell('ts_panel.state_page', member, 'home', title, state_title=title, state_text=text)
        days = int(period) if (period or '').isdigit() and int(period) in PERIODS else 30
        counts = invite_count_by_state(member) if member.can_act() and member.has_perm('invites:manage') else {k: 0 for k in STATE_ORDER}
        return render_in_shell('ts_panel.dashboard', member, 'home', 'داشبورد',
                               attention=member.dash_attention(), tiles=member.dash_tiles(days), funnel=member.dash_funnel(days),
                               workload=member.dash_workload(), checklist=member.dash_checklist(), days=days, periods=PERIODS,
                               is_new=is_new, total=sum(counts.values()), gated=ws.gated,
                               can_invite=member.can_act() and member.has_perm('invites:create'),
                               can_dismiss=member.has_perm('members:invite'),
                               rejected=ws.rejected_on, rejection_note=ws.rejection_note)


class TsPanelShell(http.Controller):

    @http.route('/my/workspaces/<int:ws_id>/home', type='http', auth='user', website=True, sitemap=False)
    def home(self, ws_id, **kw):
        member_or_404(ws_id)
        return request.redirect('/my/workspaces/%s' % ws_id)

    @http.route('/my/workspaces/<int:ws_id>/dashboard/dismiss', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def dismiss_checklist(self, ws_id, **post):
        member = member_or_404(ws_id)
        denied = require(member, 'members:invite', 'home')
        if denied:
            return denied
        member.workspace_id.sudo().onboarding_dismissed_on = fields.Datetime.now()
        return request.redirect('/my/workspaces/%s' % ws_id)

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
