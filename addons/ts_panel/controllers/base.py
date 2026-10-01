"""Shared helpers of the Panel v2 controllers (05_permissions_matrix.md section 9).

Every page of the panel: find the caller's membership in the panel of the URL (404 and a deny event when there is
none), check one permission (403 page inside the shell and a deny event), render inside the shell with the menu
that the caller's permissions allow. Later stages add menu items by appending to MENU.
"""
import time
from urllib.parse import quote

from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits, jalali
from odoo.addons.ts_org.controllers.main import _memberships
from odoo.addons.ts_org.models.panel import ROLE_LABELS

# seq, key, label, path suffix below /my/workspaces/<id>, permission, needs_act, absolute url
MENU = [
    {'seq': 10, 'key': 'home', 'label': 'داشبورد', 'suffix': '', 'perm': 'panel:view'},
    {'seq': 20, 'key': 'clients', 'label': 'شرکت‌کنندگان', 'suffix': '/clients', 'perm': 'clients:read_own',
     'needs_act': True},
    {'seq': 25, 'key': 'groups', 'label': 'گروه‌ها', 'suffix': '/groups', 'perm': 'groups:manage',
     'needs_act': True},
    {'seq': 30, 'key': 'invites', 'label': 'دعوت‌ها', 'suffix': '/invites', 'perm': 'invites:manage',
     'needs_act': True},
    {'seq': 35, 'key': 'campaigns', 'label': 'دعوت گروهی', 'suffix': '/campaigns', 'perm': 'invites:bulk',
     'needs_act': True},
    {'seq': 38, 'key': 'import', 'label': 'ورود از فایل', 'suffix': '/import', 'perm': 'clients:import',
     'needs_act': True},
    {'seq': 40, 'key': 'members', 'label': 'اعضا و نقش‌ها', 'suffix': '/members', 'perm': 'members:read'},
    {'seq': 90, 'key': 'settings', 'label': 'تنظیمات', 'suffix': '/settings', 'perm': 'panel:profile'},
    {'seq': 999, 'key': 'help', 'label': 'راهنما', 'url': '/help', 'perm': None},   # always last, for every state (WCAG 3.2.6)
]

STATE_LABELS = {'invited': 'دعوت‌شده', 'opened': 'بازشده', 'expired': 'منقضی', 'accepted': 'پذیرفته', 'in_progress': 'در حال پاسخ',
                'done': 'تکمیل‌شده', 'declined': 'ردشده', 'withdrawn': 'لغوشده'}
PANEL_STATE_LABELS = {'draft': 'پیش‌نویس', 'pilot': 'فعال', 'active': 'فعال', 'suspended': 'معلق', 'closed': 'بسته'}


def deny(member, why, **detail):
    request.env['ts.audit.event'].sudo().log_denied(
        'authz.deny', route=request.httprequest.path, workspace_id=member.workspace_id.id if member else None,
        member_id=member.id if member else None, why=why, **detail)


def member_or_404(ws_id):
    """The caller's active membership in panel ws_id; none -> deny event and 404."""
    _ts_site_or_404()
    ms = _memberships().filtered(lambda m: m.workspace_id.id == int(ws_id))
    if not ms:
        request.env['ts.audit.event'].sudo().log_denied(
            'authz.deny', route=request.httprequest.path, workspace_id=int(ws_id), why='not_a_member')
        raise request.not_found()
    return ms[:1]


def build_menu(member, active):
    perms = member.perms()
    out = []
    for it in sorted(MENU, key=lambda i: i['seq']):
        if it.get('perm') and it['perm'] not in perms:
            continue
        if it.get('needs_act') and not member.can_act():
            continue
        url = it.get('url') or '/my/workspaces/%s%s' % (member.workspace_id.id, it['suffix'])
        out.append({'key': it['key'], 'label': it['label'], 'url': url, 'current': it['key'] == active})
    return out


def pop_flash():
    return request.session.pop('ts_flash_ok', None), request.session.pop('ts_flash', None)


def flash_ok(msg):
    request.session['ts_flash_ok'] = msg


def flash_error(msg):
    request.session['ts_flash'] = msg


def render_in_shell(template, member, active, title, status=None, **vals):
    ws = member.workspace_id
    ok, err = pop_flash()
    ctx = dict(
        member=member, ws=ws, active=active, menu=build_menu(member, active), fa=fa_digits, jalali=jalali,
        role_label=ROLE_LABELS.get(member.role, member.role),
        panel_state=PANEL_STATE_LABELS.get(ws.state, ws.state),
        flash_ok=ok, flash_err=err,
        title='%s · %s' % (title, ws.name), page_title=title, page_name='ts_panel_shell')
    ctx.update(vals)
    resp = request.render(template, ctx)
    if status:
        resp.status_code = status
    return resp


def forbidden(member, perm, active=None):
    """403 page inside the shell, with a deny event (state 3 of the page conventions)."""
    deny(member, 'permission', perm=perm)
    return render_in_shell('ts_panel.forbidden', member, active or 'home', 'دسترسی ندارید', status=403)


def require(member, perm, active=None):
    """None when the caller holds `perm`; else the 403 response to return."""
    return None if member.has_perm(perm) else forbidden(member, perm, active)


# ------------------------------------------------------------------ re-authentication (05 section 6)
def reauth_minutes():
    return request.env['ir.config_parameter'].sudo().get_int('ts_panel.reauth_minutes', 10) or 10


def reauth_fresh():
    at = request.session.get('ts_reauth_at')
    return bool(at and request.session.get('ts_reauth_uid') == request.env.user.id
                and time.time() - at <= reauth_minutes() * 60)


def need_reauth(why, next_url, pending=None):
    """None when the caller authenticated recently; else a redirect to /my/reauth. `pending` (form values that are
    not secrets) is kept in the session and given back to the page so nothing is typed twice (WCAG 3.3.7)."""
    if reauth_fresh():
        return None
    request.session['ts_pv2_pending'] = pending or {}
    request.session['ts_reauth_why'] = why
    return request.redirect('/my/reauth?next=%s' % quote(next_url, safe='/'))
