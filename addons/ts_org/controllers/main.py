import re
from datetime import datetime, time as dtime
from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits, jalali
from odoo.addons.ts_org.models.assignment import RESPONSIBLE_ROLES
from odoo.addons.ts_org.models.panel import PURPOSE_LABELS, role_choices


def _memberships():
    return request.env['ts.workspace.member'].sudo().search([
        ('user_id', '=', request.env.user.id), ('active', '=', True)])


def _membership(ws_id):
    """The current user's usable membership in workspace ws_id, else 404."""
    members = _memberships().filtered(lambda m: m.workspace_id.id == int(ws_id))
    member = members.filtered(lambda m: m.can_act())[:1]
    if not member:
        request.env['ts.audit.event'].sudo().log_denied(
            'authz.deny', route=request.httprequest.path, workspace_id=int(ws_id),
            member_id=members[:1].id or None, why='no_usable_membership')
        raise request.not_found()
    return member


def _assignment(member, assignment_id):
    a = request.env['ts.assignment'].sudo().search([
        ('id', '=', int(assignment_id)), ('workspace_id', '=', member.workspace_id.id)], limit=1)
    if not a or not member.can_see(a):
        raise request.not_found()
    return a


def _scope(member, records):
    """Only what this member may see: everything for owners/managers, else their own."""
    return records.filtered(member.can_see)


def _assignable(member):
    """Members a participant can be handed to (owner/manager view only)."""
    if not member.can_assign():
        return request.env['ts.workspace.member']
    return member.workspace_id.member_ids.filtered(lambda m: m.active and m.role in RESPONSIBLE_ROLES)


def _counts(assignments):
    # every state, so the panel list, the dashboard and the invitation list count the same set (G3-P20-3, G5-P6-2)
    keys = ('invited', 'opened', 'accepted', 'in_progress', 'done', 'expired', 'declined', 'withdrawn')
    return {k: len(assignments.filtered(lambda a, k=k: a.state == k)) for k in keys}


# State pill of a panel card (glossary §2). No approval state since onb1: a panel is active from the start.
PANEL_PILL = {'active': ('فعال', 'ts-pill--ok'), 'draft': ('پیش‌نویس', 'ts-pill--neutral'),
              'suspended': ('متوقف', 'ts-pill--warn'), 'closed': ('بسته', 'ts-pill--neutral')}


def _panel_pill(ws):
    return PANEL_PILL.get(ws.state, (ws.state, 'ts-pill--neutral'))


def _unseen(member):
    """Finished results this member may open and has not opened yet (same rule as the dashboard)."""
    if not (member.can_act() and member.has_perm('invites:manage')):
        return 0
    try:
        from odoo.addons.ts_panel.models.dashboard import unseen_ids
    except ImportError:
        return 0
    base = [('workspace_id', '=', member.workspace_id.id)]
    return len([i for i in unseen_ids(request.env, member, base)
                if member.can_see(request.env['ts.assignment'].sudo().browse(i))])


# Dead-end states of an invitation link (UX T7 X1, copy W10-W13): (title, text «شما», text «تو»). The text says what to
# do next; ts_website.state_card adds the route («سنجه‌ها و نتیجه‌ها» or sign-in). {org} = the panel's public name.
INVITE_MSG = {
    'expired': ('مهلت این دعوت تمام شده است',
                'از کسی که پیوند را فرستاده بخواهید دعوت تازه بفرستد.',
                'از کسی که پیوند را فرستاده بخواه دعوت تازه بفرستد.'),
    'used': ('این دعوت را حساب دیگری پذیرفته است',
             'اگر این دعوت مال شماست، با همان شماره‌ای وارد شوید که دعوت را با آن پذیرفتید. اگر نه، از «{org}» دعوت تازه بخواهید.',
             'اگر این دعوت مال توست، با همان شماره‌ای وارد شو که دعوت را با آن پذیرفتی. اگر نه، از مشاورت دعوت تازه بخواه.'),
    'declined': ('این دعوت را نپذیرفته‌اید',
                 'اگر نظرتان عوض شده، از «{org}» دعوت تازه بخواهید.',
                 'اگر نظرت عوض شده، از مشاورت دعوت تازه بخواه.'),
    'withdrawn': ('این دعوت دیگر فعال نیست',
                  '«{org}» این دعوت را پس گرفته است. اگر فکر می‌کنید اشتباهی شده، از همان‌جا بپرسید.',
                  'فرستنده این دعوت را پس گرفته است. اگر فکر می‌کنی اشتباهی شده، از مشاورت بپرس.'),
    'paused': ('این دعوت فعلاً در دسترس نیست',
               '«{org}» موقتاً متوقف شده است و پاسخ‌دهی تازه شروع نمی‌شود. نتیجهٔ سنجه‌هایی که پیش‌تر تمام کرده‌اید در «سنجه‌ها و نتیجه‌ها» می‌ماند.',
               '«{org}» موقتاً متوقف شده است و پاسخ‌دهی تازه شروع نمی‌شود. نتیجهٔ سنجه‌هایی که پیش‌تر تمام کرده‌ای در «سنجه‌ها و نتیجه‌ها» می‌ماند.'),
}
INVITE_DECLINED_TU_TITLE = 'این دعوت را نپذیرفته‌ای'


def invite_card(state, org, student, when=None):
    """Title, text and note of a dead-end invitation state for ts_website.state_card (one pronoun per page)."""
    title, shoma, tu = INVITE_MSG[state]
    if student and state == 'declined':
        title = INVITE_DECLINED_TU_TITLE
    note = None
    if state == 'expired' and when:
        note = ('مهلت این دعوت %s تمام شد.' % when)
    return {'title': title, 'text': (tu if student else shoma).format(org=org), 'note': note}


def _is_task(inst):
    return inst.current_version_id.mode == 'task'


def _strip_minutes(text):
    """A battery description may still name minutes («…؛ حدود ۳۰ دقیقه.»); the page states time once, from data."""
    text = re.sub(r'؛\s*حدود\s+[0-9۰-۹]+\s+دقیقه\.', '.', text or '')
    return re.sub(r'؛\s*حدود\s+[0-9۰-۹]+\s+دقیقه،\s*', '؛ ', text).strip()


def effort_facts(inst, battery=None, purpose=None):
    """One source for the size and time a participant is told before starting (UX T7 X5, copy P3/W15/W20/W21):
    {'size', 'time', 'lines', 'description'}. Instruments use their own labels (ts_effort_label / ts_duration_label: a
    timed task says «۳ بخش زمان‌دار», never «۰ پرسش»); the matrix inventory adds a total range; a battery sums its
    questionnaire items, its timed sections and its stored estimate (est_minutes)."""
    if battery:
        b = battery.sudo()
        insts = b.ts_lines().mapped('instrument_id') if hasattr(b, 'ts_lines') else b.line_ids.mapped('instrument_id')
        items = sum(i.active_item_count for i in insts if not _is_task(i))
        blocks = 0
        for i in insts.filtered(_is_task):
            spec = i.ts_task_spec() if hasattr(i, 'ts_task_spec') else None
            blocks += len(spec['blocks']) if spec else 1
        parts = []
        if items:
            parts.append('%s پرسش' % fa_digits(items))
        if blocks:
            parts.append('%s بخش زمان‌دار' % fa_digits(blocks))
        size = '%s سنجه: %s' % (fa_digits(len(insts)), ' و '.join(parts)) if parts else '%s سنجه' % fa_digits(len(insts))
        desc = _strip_minutes(b.ts_card()['description'] if hasattr(b, 'ts_card') else b.description)
        if purpose != 'employment':
            # a counseling or school client never reads the hiring clause of a shared starter battery (audit P25-2)
            desc = desc.replace(' و در پنل استخدامی فقط یکی از ورودی‌های گفت‌وگوی شغلی است', '')
        return {'size': size, 'time': 'حدود %s دقیقه' % fa_digits(b.est_minutes),
                'lines': [{'name': i.ts_title(), 'size': i.ts_effort_label(), 'time': i.ts_duration_label()} for i in insts],
                'description': desc}
    inst = inst.sudo()
    size, time = inst.ts_effort_label(), inst.ts_duration_label()
    v = inst.current_version_id
    per_field = getattr(type(inst), 'MATRIX_SECONDS_PER_FIELD', 0)
    if v.mode == 'matrix' and per_field and v.field_min and v.field_max:
        # the usual 3 to 5 fields (the field-name page and the talent consent say the same; copy W15), clamped to the version
        f_lo, f_hi = max(v.field_min, 3), min(v.field_max, 5)
        if f_lo > f_hi:
            f_lo, f_hi = v.field_min, v.field_max
        lo, hi = f_lo * per_field // 60, f_hi * per_field // 60
        time = '%s؛ معمولاً %s تا %s زمینه، یعنی %s تا %s دقیقه' % (time, fa_digits(f_lo), fa_digits(f_hi), fa_digits(lo), fa_digits(hi))
    return {'size': size, 'time': time, 'lines': [], 'description': ''}


class TsOrg(http.Controller):

    # ------------------------------------------------------- organization side
    @http.route('/my/workspaces', type='http', auth='user', website=True, sitemap=False)
    def workspaces(self, **kw):
        _ts_site_or_404()
        rows = []
        for m in _memberships():
            ws = m.workspace_id
            counts = _counts(_scope(m, request.env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id)])))
            rows.append({'member': m, 'ws': ws, 'usable': m.can_act(), 'counts': counts, 'total': sum(counts.values()),
                         'pill': _panel_pill(ws), 'purpose': PURPOSE_LABELS.get(ws.purpose, ws.purpose),
                         'unseen': _unseen(m) if m.can_act() else 0})
        return request.render('ts_org.workspaces', {'rows': rows, 'fa': fa_digits, 'page_name': 'ts_workspaces'})

    @http.route('/my/workspaces/<int:ws_id>', type='http', auth='user', website=True, sitemap=False)
    def workspace(self, ws_id, state=None, **kw):
        _ts_site_or_404()
        member = _membership(ws_id)
        ws = member.workspace_id
        allx = _scope(member, request.env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id)]))
        resp = kw.get('resp')
        shown = allx.filtered(lambda a: a.state == state) if state else allx
        imports = request.env['ts.attempt']
        src = kw.get('src')
        if ws.purpose == 'education':
            imports = request.env['ts.attempt'].sudo().search([
                ('workspace_id', '=', ws.id), ('source', '=', 'import'), ('state', '=', 'done')],
                order='submitted_at desc, id desc')
            imports = _scope(member, imports)
            if src == 'invite':
                imports = imports.browse()
            if src == 'import':
                shown = shown.browse()
        un_a = allx.filtered(lambda r: not r.responsible_id)
        un_i = imports.filtered(lambda r: not r.responsible_id)
        mi_a = allx.filtered(lambda r: r.responsible_id == member)
        mi_i = imports.filtered(lambda r: r.responsible_id == member)
        unassigned, mine = len(un_a) + len(un_i), len(mi_a) + len(mi_i)
        if resp == 'none':
            shown, imports = shown & un_a, imports & un_i
        elif resp == 'mine':
            shown, imports = shown & mi_a, imports & mi_i
        return request.render('ts_org.workspace', {
            'resp_filter': resp, 'unassigned_count': unassigned, 'mine_count': mine,
            'can_assign': member.can_assign(), 'assignable': _assignable(member),
            'show_unassigned': member.sees_unassigned(),
            'imports': imports, 'src_filter': src,
            'member': member, 'ws': ws, 'assignments': shown, 'counts': _counts(allx), 'total': len(allx),
            'state_filter': state, 'instruments': member.allowed_instruments() if member.can_invite() else [],
            'created': request.env['ts.assignment'].sudo().browse(int(kw['created'])).exists()
            if kw.get('created', '').isdigit() else None,
            'error': kw.get('error'), 'fa': fa_digits, 'page_name': 'ts_workspaces',
            'others': [m for m in _memberships() if m.workspace_id != ws and m.can_act()],
            'is_new': bool(kw.get('new')), 'flash': request.session.pop('ts_flash', None),
            'can_invite_participants': member.can_invite_participants(),
            'checklist': self._checklist(member, ws),
            'members': ws.member_ids.filtered('active') if member.has_perm('members:invite') else request.env['ts.workspace.member'],
            'pending_invites': request.env['ts.member.invite'].sudo().search(
                [('workspace_id', '=', ws.id), ('state', '=', 'pending')]) if member.has_perm('members:invite') else None,
            'new_invite': request.env['ts.member.invite'].sudo().search(
                [('id', '=', int(kw['minv'])), ('workspace_id', '=', ws.id)], limit=1)
            if member.has_perm('members:invite') and (kw.get('minv') or '').isdigit() else None,
            'role_choices': role_choices(ws) if member.has_perm('members:invite') else [],
        })

    def _checklist(self, member, ws):
        if not member.has_perm('members:invite'):
            return []
        others = len(ws.member_ids.filtered(lambda m: m.active and m != member)) + \
            request.env['ts.member.invite'].sudo().search_count([('workspace_id', '=', ws.id)])
        first = request.env['ts.assignment'].sudo().search_count([('workspace_id', '=', ws.id)])
        return [
            ('پنل ساخته شد', True, None),
            ('نام و لوگوی پنل', bool(ws.partner_id.image_1920), '#ts-settings'),
            ('دعوت اولین همکار', bool(others), '#ts-members'),
            ('دعوت اولین شرکت‌کننده', bool(first), '#ts-invite'),
        ]

    @http.route('/my/workspaces/<int:ws_id>/invite', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def invite(self, ws_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        if not member.can_invite():
            raise request.not_found()
        if not member.can_invite_participants():
            raise request.not_found()
        name = (post.get('invitee_name') or '').strip()
        inst_id = post.get('instrument_id') or ''
        allowed = member.allowed_instruments()
        if not name or not inst_id.isdigit() or int(inst_id) not in allowed.ids:
            return request.redirect('/my/workspaces/%s?error=form' % ws_id)
        try:
            a = request.env['ts.assignment'].sudo().create({
                'workspace_id': member.workspace_id.id, 'instrument_id': int(inst_id),
                'invitee_name': name[:120], 'invitee_email': (post.get('invitee_email') or '').strip()[:200] or False,
                'note': (post.get('note') or '').strip()[:300] or False,
                'invited_by_id': request.env.user.id,
            })
        except (UserError, ValidationError):
            return request.redirect('/my/workspaces/%s?error=rule' % ws_id)
        return request.redirect('/my/workspaces/%s?created=%s' % (ws_id, a.id))

    @http.route('/my/workspaces/<int:ws_id>/a/<int:assignment_id>', type='http', auth='user',
                website=True, sitemap=False)
    def assignment(self, ws_id, assignment_id, **kw):
        _ts_site_or_404()
        member = _membership(ws_id)
        a = _assignment(member, assignment_id)
        level, results = a.visible_results(member)
        if level == 'education' and a.attempt_id:
            return request.redirect('/my/workspaces/%s/p/%s' % (ws_id, a.attempt_id.id))
        if a.client_id and member.has_perm('invites:manage'):
            # one page per invitation: invite managers land on the panel's invitation page (link, QR, actions; G3-P14-1)
            return request.redirect('/my/workspaces/%s/invites/%s' % (ws_id, a.id))
        if level != 'none':
            request.env['ts.audit.event'].sudo().log('assignment.result_view', a, workspace=a.workspace_id,
                                                     level=level, viewer=request.env.user.id)
        return request.render('ts_org.assignment', {
            'member': member, 'ws': member.workspace_id, 'a': a, 'level': level, 'results': results,
            'attempt': a.attempt_id, 'inst': a.instrument_id, 'fa': fa_digits, 'page_name': 'ts_workspaces',
        })

    @http.route('/my/workspaces/<int:ws_id>/a/<int:assignment_id>/withdraw', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def withdraw(self, ws_id, assignment_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        if not member.can_invite():
            raise request.not_found()
        a = _assignment(member, assignment_id)
        try:
            a.action_withdraw()
        except UserError:
            pass
        return request.redirect('/my/workspaces/%s/a/%s' % (ws_id, a.id))

    def _set_responsible(self, member, rec, post):
        """Owner/manager hands a record to a specialist of the same workspace, or clears it."""
        if not member.can_assign():
            raise request.not_found()
        rid = (post.get('responsible_id') or '').strip()
        target = request.env['ts.workspace.member']
        if rid:
            target = _assignable(member).filtered(lambda m: str(m.id) == rid)
            if not target:
                return False
        try:
            rec.write({'responsible_id': target.id or False})
        except (UserError, ValidationError):
            return False
        return True

    @http.route('/my/workspaces/<int:ws_id>/a/<int:assignment_id>/responsible', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def assignment_responsible(self, ws_id, assignment_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        a = _assignment(member, assignment_id)
        ok = self._set_responsible(member, a, post)
        return request.redirect('/my/workspaces/%s%s' % (ws_id, '' if ok else '?error=rule'))

    @http.route('/my/workspaces/<int:ws_id>/p/<int:attempt_id>/responsible', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def import_responsible(self, ws_id, attempt_id, **post):
        _ts_site_or_404()
        member = _membership(ws_id)
        at = request.env['ts.attempt'].sudo().search([
            ('id', '=', int(attempt_id)), ('workspace_id', '=', member.workspace_id.id),
            ('source', '=', 'import')], limit=1)
        if not at or not member.can_see(at):
            raise request.not_found()
        ok = self._set_responsible(member, at, post)
        return request.redirect('/my/workspaces/%s%s' % (ws_id, '' if ok else '?error=rule'))

    # -------------------------------------------------------- participant side
    def _auth_urls(self, path):
        """Sign-in links for a public visitor; ts_sms adds mobile sign-in (phone_url)."""
        redirect = quote(path)
        return {'login_url': '/web/login?redirect=%s' % redirect, 'signup_url': '/web/signup?redirect=%s' % redirect,
                'phone_url': None}

    def _invite(self, token, paused_ok=False):
        """The invitation of a running panel. With paused_ok the invitation of a suspended panel is returned too, so
        its page can say so (accepting stays impossible)."""
        a = request.env['ts.assignment'].sudo().search([('token', '=', token)], limit=1)
        if not a or a.workspace_id.state not in (('active', 'suspended') if paused_ok else ('active',)):
            raise request.not_found()
        return a

    @http.route('/invite/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def invite_page(self, token, **kw):
        _ts_site_or_404()
        a = self._invite(token, paused_ok=True)
        user = request.env.user
        if a.user_id and a.user_id != user:
            # bound to another account, or opened signed out: the same 404 as an unknown token, so nobody learns whether
            # the link exists or who holds it; ts_website.page_404 explains and offers sign-in or the person's own list
            # (UX T7 X1). The owner signs in and lands back here.
            raise request.not_found()
        if a.attempt_id and a.user_id == user and a.state in ('accepted', 'in_progress'):
            return request.redirect('/take/%s' % a.attempt_id.access_token)
        if a.state == 'done' and a.user_id == user:
            return request.redirect('/my/assessments/%s' % a.attempt_id.id)
        inv_state = 'paused' if a.workspace_id.state == 'suspended' else a.invite_state()
        if inv_state == 'used' and a.user_id == user:
            inv_state = 'ok'
        public = user._is_public()
        student = a.workspace_id.purpose == 'education'
        mismatch = False
        account = user.ts_account_label()
        known = account['label'] if account['kind'] == 'name' else ''
        if known and not a.user_id:
            # signed in with an account whose name differs from the invitee: say so before accepting (G2-P12-1)
            def norm(x):
                return ' '.join((x or '').replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ').split()).lower()
            mismatch = norm(a.invitee_name) != norm(user.name)
        card = None
        if inv_state != 'ok':
            ends = a.expires_at if 'expires_at' in a._fields and a.expires_at else a.deadline
            if ends and not isinstance(ends, datetime):
                ends = datetime.combine(ends, dtime(12, 0))
            card = invite_card(inv_state, a.workspace_id.ts_public_name(), student,
                               jalali(ends, with_time=False) if ends else None)
        battery = a.battery_id if 'battery_id' in a._fields else None
        return request.render('ts_org.invite', {
            'a': a, 'inst': a.instrument_id, 'ws': a.workspace_id, 'public': public,
            'fa': fa_digits, **self._auth_urls('/invite/%s' % token),
            'inv_state': inv_state, 'inv_msg': INVITE_MSG, 'inv_card': card,
            'facts': effort_facts(a.instrument_id, battery, a.workspace_id.purpose),
            'user_name': known, 'account': account, 'mismatch': mismatch,
            'logout_url': '/web/session/logout?redirect=%s' % quote('/invite/%s' % token),
            'ask_decline': kw.get('decline') == '1' and not public,
            'student': student,
        })

    @http.route('/invite/<string:token>/accept', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def invite_accept(self, token, **post):
        _ts_site_or_404()
        a = self._invite(token)
        try:
            attempt = a.action_accept(request.env.user, share=post.get('share') == '1')
        except UserError:
            raise request.not_found()
        # onb1: the name the panel typed stays on this invitation (invitee_name) for the panel's eyes only; it is never
        # copied into the account, whose own name is given by the person on «/my/account» or where others see it
        return request.redirect('/take/%s' % attempt.access_token)

    @http.route('/invite/<string:token>/decline', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def invite_decline(self, token, **post):
        _ts_site_or_404()
        a = self._invite(token)
        try:
            a.action_decline(request.env.user)
        except UserError:
            raise request.not_found()
        # UX T7 P22-1: /my says, as a status message, that it worked
        return request.redirect('/my?msg=declined')

    @http.route('/my/assessments/<int:attempt_id>/unshare', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def unshare(self, attempt_id, **post):
        _ts_site_or_404()
        a = request.env['ts.assignment'].sudo().search([
            ('attempt_id', '=', attempt_id), ('user_id', '=', request.env.user.id)], limit=1)
        if not a:
            raise request.not_found()
        a.action_revoke_share(request.env.user)
        return request.redirect('/my/assessments/%s' % attempt_id)
