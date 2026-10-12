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

RESULT_PERMS = ('results:summary', 'results:education', 'results:clinical')

# seq, key, group (sidebar heading, redesign 2026-10), label, path suffix below /my/workspaces/<id>, permission, needs_act, absolute url;
# optional: 'when' (callable(member) -> bool, checked after the permission) and 'active_key' (the page key that marks it current)
MENU = [
    {'seq': 10, 'key': 'home', 'group': 'نمای کلی', 'label': 'پیشخوان', 'suffix': '', 'perm': 'panel:view'},
    {'seq': 20, 'key': 'clients', 'group': 'افراد و دعوت', 'label': 'شرکت‌کنندگان', 'suffix': '/clients', 'perm': 'clients:read_own',
     'needs_act': True},
    {'seq': 25, 'key': 'groups', 'group': 'افراد و دعوت', 'label': 'گروه‌ها', 'suffix': '/groups', 'perm': 'groups:manage',
     'needs_act': True},
    {'seq': 30, 'key': 'invites', 'group': 'افراد و دعوت', 'label': 'دعوت‌ها', 'suffix': '/invites', 'perm': 'invites:manage',
     'needs_act': True},
    {'seq': 35, 'key': 'campaigns', 'group': 'افراد و دعوت', 'label': 'دعوت گروهی', 'suffix': '/campaigns', 'perm': 'invites:bulk',
     'needs_act': True},
    {'seq': 38, 'key': 'import', 'group': 'افراد و دعوت', 'label': 'ورود از فایل', 'suffix': '/import', 'perm': 'clients:import',
     'needs_act': True},
    {'seq': 45, 'key': 'exports', 'group': 'گزارش و داده', 'label': 'خروجی‌ها', 'suffix': '/exports', 'perm': 'clients:export',
     'needs_act': True},
    {'seq': 42, 'key': 'reports', 'group': 'گزارش و داده', 'label': 'گزارش‌ها', 'suffix': '/reports', 'perm_any': RESULT_PERMS, 'needs_act': True},
    {'seq': 50, 'key': 'credits', 'group': 'گزارش و داده', 'label': 'اعتبار و مصرف', 'suffix': '/credits', 'perm': 'credits:read'},
    {'seq': 85, 'key': 'members', 'group': 'پنل', 'label': 'اعضا و نقش‌ها', 'suffix': '/members', 'perm': 'members:read'},
    {'seq': 80, 'key': 'audit', 'group': 'گزارش و داده', 'label': 'دفتر ممیزی', 'suffix': '/audit', 'perm': 'audit:read'},
    {'seq': 90, 'key': 'settings', 'group': 'پنل', 'label': 'تنظیمات', 'suffix': '/settings', 'perm': 'panel:profile'},
    {'seq': 999, 'key': 'help', 'group': 'پنل', 'label': 'راهنما', 'url': '/help/panel', 'perm': None},   # always last, for every state (WCAG 3.2.6)
]

STATE_LABELS = {'invited': 'دعوت‌شده', 'opened': 'بازشده', 'expired': 'منقضی', 'accepted': 'پذیرفته', 'in_progress': 'در حال پاسخ',
                'done': 'تکمیل‌شده', 'declined': 'ردشده', 'withdrawn': 'لغوشده'}
GATED_LABEL = 'در انتظار تأیید'      # a pilot panel that is still gated (glossary §9-6); an approved pilot panel is «فعال»
PANEL_STATE_LABELS = {'draft': 'پیش‌نویس', 'pilot': GATED_LABEL, 'active': 'فعال', 'suspended': 'معلق', 'closed': 'بسته'}

# One sentence per role (and purpose where it differs): what this member can see and do. Shown in the shell next to
# the role, which links to /help/roles#role-<key> (audit G5 PT-2). Presentation only: access is decided elsewhere.
ROLE_SCOPE = {
    'owner': 'اعضا، شرکت‌کنندگان و تنظیمات پنل را اداره می‌کنید.',
    'admin': 'کارهای اجرایی پنل را پیش می‌برید؛ نتیجه‌ها را نمی‌بینید، فقط وضعیت دعوت‌ها را.',
    ('counselor', 'education'): 'دانش‌آموزانی را که کارشناس مسئول آن‌ها هستید و فهرست «بدون کارشناس» را می‌بینید؛ نتیجه را در سطح مشاور می‌خوانید.',
    'counselor': 'شرکت‌کنندگانی را که کارشناس مسئول آن‌ها هستید می‌بینید؛ نتیجه را در سطح مشاور می‌خوانید.',
    'clinic_director': 'همهٔ شرکت‌کنندگان پنل را می‌بینید و اعضا و دعوت‌ها را اداره می‌کنید؛ گزارش کامل ویژهٔ مشاور پس از احراز صلاحیت باز می‌شود.',
    'clinician': 'فقط شرکت‌کنندگانی را که کارشناس مسئول آن‌ها هستید می‌بینید؛ گزارش کامل ویژهٔ مشاور پس از احراز صلاحیت باز می‌شود.',
    'hr_admin': 'همهٔ شرکت‌کنندگان را می‌بینید و اعضا و دعوت‌ها را اداره می‌کنید؛ از نتیجه فقط خلاصه (سطح هر عامل) دیده می‌شود.',
    'hiring_manager': 'شرکت‌کنندگانی را که کارشناس مسئول آن‌ها هستید می‌بینید؛ از نتیجه فقط خلاصه (سطح هر عامل، بدون نمره و پاسخ).',
    'reviewer': 'از نتیجهٔ شرکت‌کنندگان فقط سطح هر عامل را می‌بینید؛ نمره و پاسخ‌ها نمایش داده نمی‌شود و دعوت نمی‌فرستید.',
}


def role_scope(role, purpose):
    return ROLE_SCOPE.get((role, purpose)) or ROLE_SCOPE.get(role, '')


def panel_state_label(ws):
    if ws.state == 'pilot' and not ws.gated:
        return PANEL_STATE_LABELS['active']     # approved pilot panel
    return PANEL_STATE_LABELS.get(ws.state, ws.state)


def gated_note(member):
    """The one-line notice of a gated panel, worded for what this member can do (None when the panel is not gated)."""
    ws = member.workspace_id
    if not ws.gated:
        return None
    if member.has_perm('invites:create') or member.has_perm('members:invite'):
        return ('این پنل در انتظار تأیید تیم استعدادیاب است. تا آن زمان می‌توانید پنل را کامل کنید و همکاران را دعوت کنید؛ '
                'دعوت شرکت‌کننده و دیدن نتیجه پس از تأیید باز می‌شود.')
    return 'این پنل در انتظار تأیید تیم استعدادیاب است؛ کار با شرکت‌کنندگان پس از تأیید شروع می‌شود.'


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
        if it.get('perm_any') and not any(p in perms for p in it['perm_any']):
            continue
        if it.get('needs_act') and not member.can_act():
            continue
        # an item added by a later module may decide itself who sees it (e.g. ts_billing's own-cost page for capped roles)
        if it.get('when') and not it['when'](member):
            continue
        url = it.get('url') or '/my/workspaces/%s%s' % (member.workspace_id.id, it['suffix'])
        out.append({'key': it['key'], 'label': it['label'], 'url': url, 'current': it.get('active_key', it['key']) == active,
                    'group': it.get('group', '')})
    # A group heading over a single item says nothing (non-owners saw «پنل» above «راهنما» only, audit G5 PT-9):
    # such an item loses its heading and is set apart by a line instead.
    for i, it in enumerate(out):
        g = it['group']
        if i and g and sum(1 for o in out if o['group'] == g) == 1:
            it['group'] = ''
            it['solo'] = True
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
        role_scope=role_scope(member.role, ws.purpose), role_help_url='/help/roles#role-%s' % member.role,
        panel_state=panel_state_label(ws), panel_gated=bool(ws.gated), gated_note=gated_note(member),
        back_url=None, back_label=None,
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
