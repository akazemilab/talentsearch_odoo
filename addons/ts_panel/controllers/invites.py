"""Invitations of the panel (S6, INV-1..INV-4): list with funnel, wizard, invitation page, extend, withdraw.
The wizard keeps its draft in the session: names, phone numbers and notes never travel in a URL."""
from datetime import datetime, time, timedelta

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_org.models.panel import norm_email, norm_phone

from .base import STATE_LABELS, flash_error, flash_ok, forbidden, member_or_404, render_in_shell, require
from ..models.dashboard import invite_filters
from .clients import visible_domain

PAGE = 25
FILTER_TEXT = {'unseen': 'نتیجه‌هایی که هنوز باز نکرده‌اید', 'overdue': 'دعوت‌های گذشته از مهلت',
               'expiring': 'دعوت‌هایی که تا ۳ روز دیگر منقضی می‌شوند', 'sent': 'دعوت‌های فرستاده‌شده در این دوره',
               'accepted': 'دعوت‌های پذیرفته‌شده در این دوره', 'done': 'تکمیل‌شده‌ها در این دوره',
               'noshare': 'تکمیل‌شده‌های بدون اشتراک نتیجه', 'created': 'دعوت‌های ساخته‌شده در این دوره',
               'active': 'دعوت‌های این دوره (بدون لغوشده)'}
STATE_ORDER = ['invited', 'opened', 'accepted', 'in_progress', 'done', 'expired', 'declined', 'withdrawn']
DRAFT = 'ts_invite_draft_%s'
PILL = {'done': 'ts-pill--ok', 'accepted': 'ts-pill--info', 'in_progress': 'ts-pill--info', 'expired': 'ts-pill--warn',
        'declined': 'ts-pill--neutral', 'withdrawn': 'ts-pill--neutral'}


def invite_count_by_state(member):
    """Counts per state over the invitations the caller may see (same rules as the client list)."""
    A = request.env['ts.assignment'].sudo()
    out = {k: 0 for k in STATE_ORDER}
    for st, n in A._read_group(assignment_domain(member), groupby=['state'], aggregates=['__count']):
        out[st] = n
    return out


def assignment_domain(me):
    """visible_domain() of the clients, written for ts.assignment through its client."""
    out = []
    for t in visible_domain(me):
        out.append(('client_id.' + t[0], t[1], t[2]) if isinstance(t, tuple) else t)
    return [('workspace_id', '=', me.workspace_id.id)] + [x for x in out if not (isinstance(x, tuple) and x[0] == 'client_id.workspace_id')]


def _assignment_or_404(me, aid):
    a = request.env['ts.assignment'].sudo().search([('id', '=', int(aid)), ('workspace_id', '=', me.workspace_id.id)])
    if not a or not a.client_id:
        raise request.not_found()
    return a


def _fa(n):
    from odoo.addons.ts_assessment.models.attempt import fa_digits
    return fa_digits(n)


def sms_available(ws):
    company = (ws.company_id or request.env.company).sudo()
    return bool(company.kv_enabled and company.ts_sms_invite)


class TsPanelInvites(http.Controller):

    # ------------------------------------------------------------------ list
    @http.route('/my/workspaces/<int:ws_id>/invites', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def invites(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'invites:manage', 'invites')
        if denied:
            return denied
        if not me.can_act():
            return forbidden(me, 'invites:manage', 'invites')
        A = request.env['ts.assignment'].sudo()
        state = kw.get('state') if kw.get('state') in STATE_LABELS else 'all'
        base_dom = assignment_domain(me)
        extra, fparams = invite_filters(request.env, me, base_dom, kw)
        dom = base_dom + extra + ([('state', '=', state)] if state != 'all' else [])
        total = A.search_count(dom)
        pages = max(1, -(-total // PAGE))
        page = min(max(int(kw['page']) if (kw.get('page') or '').isdigit() else 1, 1), pages)
        rows = A.search(dom, order='create_date desc, id desc', limit=PAGE, offset=(page - 1) * PAGE)
        counts = invite_count_by_state(me) if not fparams else {k: 0 for k in STATE_ORDER}
        if fparams:
            for st, n in A._read_group(base_dom + extra, groupby=['state'], aggregates=['__count']):
                counts[st] = n

        def url(**over):
            q = {'state': state, 'page': page}
            q.update(fparams)
            q.update(over)
            parts = ['%s=%s' % (k, v) for k, v in q.items() if not ((k == 'state' and v == 'all') or (k == 'page' and int(v) == 1))]
            return '/my/workspaces/%s/invites%s' % (ws_id, ('?' + '&'.join(parts)) if parts else '')

        return render_in_shell('ts_panel.invites', me, 'invites', 'دعوت‌ها', rows=rows, counts=counts, state=state,
                               state_order=STATE_ORDER, state_labels=STATE_LABELS, pill=PILL, total=total, page=page, pages=pages,
                               url=url, can_create=me.has_perm('invites:create'), all_total=sum(counts.values()),
                               filtered=FILTER_TEXT.get(next((k for k in ('unseen', 'overdue', 'expiring') if k in fparams), fparams.get('kind')), '') if fparams else '',
                               clear_url='/my/workspaces/%s/invites%s' % (ws_id, ('?state=' + state) if state != 'all' else ''))

    # ------------------------------------------------------------------ wizard
    def _draft(self, ws_id):
        return request.session.get(DRAFT % ws_id) or {}

    def _save_draft(self, ws_id, d):
        request.session[DRAFT % ws_id] = d

    def _wizard_guard(self, ws_id):
        me = member_or_404(ws_id)
        if me.can_act() and me.can_invite() and not me.can_invite_participants():
            return me, render_in_shell('ts_panel.state_page', me, 'invites', 'دعوت هنوز ممکن نیست',
                                       state_title='دعوت شرکت‌کنندگان پس از تأیید پنل ممکن می‌شود',
                                       state_text='پنل شما در انتظار تأیید مالک پلتفرم است. تا آن زمان می‌توانید ردیف شرکت‌کنندگان را بسازید و سنجه‌ها را ببینید.')
        denied = require(me, 'invites:create', 'invites')
        if denied:
            return me, denied
        if not me.can_act():
            return me, forbidden(me, 'invites:create', 'invites')
        return me, None

    def _eligible_clients(self, me, q=None):
        C = request.env['ts.panel.client'].sudo()
        dom = visible_domain(me) + [('state', '=', 'active')]
        if q:
            from ..models.text import norm_text
            dom += ['|', '|', ('name_norm', 'ilike', norm_text(q)), ('code', 'ilike', q), ('phone', 'ilike', norm_phone(q) or q)]
        return C.search(dom, order='name_norm, id', limit=20).filtered(lambda c: not c.contact_locked)

    def _wizard_ctx(self, me, ws_id, step, **extra):
        d = self._draft(ws_id)
        client = request.env['ts.panel.client'].sudo().browse(d.get('client_id') or 0).exists()   # ts-scope-ok: workspace checked on the next line
        if client and client.workspace_id.id != ws_id:
            client = client.browse()
        inst = request.env['ts.instrument'].sudo().browse(d.get('instrument_id') or 0).exists()   # ts-scope-ok: instruments are platform-wide; allowed_instruments() gates the id
        vals = dict(step=step, draft=d, client=client, inst=inst, instruments=me.allowed_instruments(),
                    sms_ok=sms_available(me.workspace_id), steps=[('1', 'چه کسی'), ('2', 'کدام سنجه'), ('3', 'تنظیمات'), ('4', 'مرور')])
        vals.update(extra)
        return vals

    @http.route('/my/workspaces/<int:ws_id>/invites/new', type='http', auth='user', website=True,
                methods=['GET', 'POST'], sitemap=False)
    def wizard(self, ws_id, **post):
        me, denied = self._wizard_guard(ws_id)
        if denied:
            return denied
        step = post.get('step') if post.get('step') in ('1', '2', '3', '4') else '1'
        if request.httprequest.method == 'POST':
            return self._wizard_post(me, ws_id, step, post)
        d = self._draft(ws_id)
        if post.get('client') and (post['client'] or '').isdigit() and not d.get('client_id'):
            c = request.env['ts.panel.client'].sudo().search(visible_domain(me) + [('id', '=', int(post['client']))])   # ts-scope-ok: visible_domain() starts with the panel
            if c and not c.contact_locked and c.state == 'active':
                d = {'client_id': c.id}
                self._save_draft(ws_id, d)
        if post.get('fresh'):
            d = {}
            self._save_draft(ws_id, d)
        if step != '1' and not (d.get('client_id') or d.get('new_name')):
            step = '1'
        if step in ('3', '4') and not d.get('instrument_id'):
            step = '2'
        extra = {}
        if step == '4':
            extra = self._review_extra(me, ws_id, d)
        return render_in_shell('ts_panel.invite_wizard', me, 'invites', 'دعوت تازه', **self._wizard_ctx(me, ws_id, step, **extra))

    def _review_extra(self, me, ws_id, d):
        C = request.env['ts.panel.client'].sudo()
        dups = C.browse()
        if not d.get('client_id'):
            dups = C.ts_duplicates(ws_id, phone=d.get('new_phone'), email=d.get('new_email')).filtered(lambda c: me.can_see(c) and not c.contact_locked)
        from odoo.addons.ts_assessment.models.attempt import jalali
        dl = jalali(datetime.combine(fields.Date.to_date(d['deadline']), time(12)), with_time=False) if d.get('deadline') else ''
        return {'dups': dups, 'deadline_fa': dl}

    def _wizard_post(self, me, ws_id, step, post):
        d = dict(self._draft(ws_id))
        back = '/my/workspaces/%s/invites/new' % ws_id
        C = request.env['ts.panel.client'].sudo()
        if step == '1':
            if post.get('search') is not None and not post.get('choose') and not post.get('new_name'):
                found = self._eligible_clients(me, (post.get('q') or '').strip())
                return render_in_shell('ts_panel.invite_wizard', me, 'invites', 'دعوت تازه',
                                       **self._wizard_ctx(me, ws_id, '1', found=found, q=(post.get('q') or '').strip(), searched=True))
            cid = post.get('choose') or ''
            if cid.isdigit():
                c = C.search(visible_domain(me) + [('id', '=', int(cid)), ('state', '=', 'active')])
                if not c or c.contact_locked:
                    flash_error('این شرکت‌کننده را نمی‌توان دعوت کرد.')
                    return request.redirect(back)
                d = {'client_id': c.id}
            else:
                name = (post.get('new_name') or '').strip()
                phone, email = (post.get('new_phone') or '').strip(), (post.get('new_email') or '').strip()
                err = None
                if not 2 <= len(name) <= 120:
                    err = 'نام را بین ۲ تا ۱۲۰ نویسه بنویسید.'
                elif phone and not norm_phone(phone):
                    err = 'شمارهٔ موبایل معتبر نیست. مثال: ۰۹۱۲۳۴۵۶۷۸۹'
                elif email and not norm_email(email):
                    err = 'ایمیل معتبر نیست.'
                if err:
                    flash_error(err)
                    return request.redirect(back)
                d = {'new_name': name, 'new_phone': norm_phone(phone) or '', 'new_email': norm_email(email) or ''}
            d.pop('instrument_id', None)
            self._save_draft(ws_id, d)
            return request.redirect(back + '?step=2')
        if not (d.get('client_id') or d.get('new_name')):
            return request.redirect(back)
        if step == '2':
            iid = post.get('instrument_id') or ''
            if not iid.isdigit() or int(iid) not in me.allowed_instruments().ids:
                flash_error('سنجهٔ انتخاب‌شده برای این پنل مجاز نیست.')
                return request.redirect(back + '?step=2')
            d['instrument_id'] = int(iid)
            self._save_draft(ws_id, d)
            return request.redirect(back + '?step=3')
        if step == '3':
            deadline = (post.get('deadline') or '').strip()
            if deadline:
                try:
                    dd = fields.Date.to_date(deadline)
                except Exception:
                    dd = None
                if not dd or dd < fields.Date.today():
                    flash_error('مهلت باید تاریخی از امروز به بعد باشد.')
                    return request.redirect(back + '?step=3')
                d['deadline'] = str(dd)
            else:
                d.pop('deadline', None)
            d['note'] = (post.get('note') or '').strip()[:300]
            d['sms'] = bool(post.get('sms')) and bool(post.get('attest')) and sms_available(me.workspace_id)
            if post.get('sms') and not post.get('attest'):
                flash_error('برای ارسال پیامک، تأیید رضایت شرکت‌کننده را تیک بزنید.')
                return request.redirect(back + '?step=3')
            self._save_draft(ws_id, d)
            return request.redirect(back + '?step=4')
        if step == '4':
            return self._create(me, ws_id, d)
        return request.redirect(back)

    def _create(self, me, ws_id, d):
        back = '/my/workspaces/%s/invites/new' % ws_id
        A = request.env['ts.assignment'].sudo()
        if not d.get('instrument_id') or d['instrument_id'] not in me.allowed_instruments().ids:
            flash_error('سنجهٔ انتخاب‌شده برای این پنل مجاز نیست.')
            return request.redirect(back + '?step=2')
        limit = request.env['ir.config_parameter'].sudo().get_int('ts_panel.invites_per_hour', 200) or 200
        since = fields.Datetime.now() - timedelta(hours=1)
        if A.search_count([('workspace_id', '=', ws_id), ('invited_by_id', '=', request.env.user.id), ('create_date', '>=', since)]) >= limit:
            flash_error('در یک ساعت بیش از %s دعوت نمی‌توان ساخت. کمی بعد دوباره امتحان کنید.' % _fa(limit))
            return request.redirect('/my/workspaces/%s/invites' % ws_id)
        C = request.env['ts.panel.client'].sudo()
        vals = {'workspace_id': ws_id, 'instrument_id': d['instrument_id'], 'invited_by_id': request.env.user.id,
                'note': d.get('note') or False, 'deadline': d.get('deadline') or False}
        if d.get('client_id'):
            c = C.search(visible_domain(me) + [('id', '=', d['client_id']), ('state', '=', 'active')])
            if not c or c.contact_locked:
                flash_error('این شرکت‌کننده را نمی‌توان دعوت کرد.')
                return request.redirect(back + '?fresh=1')
            vals.update(client_id=c.id, invitee_name=c.name, invitee_email=c.email or False, invitee_phone=c.phone or False)
        else:
            vals.update(invitee_name=d['new_name'], invitee_email=d.get('new_email') or False, invitee_phone=d.get('new_phone') or False)
        if d.get('sms') and vals.get('invitee_phone') and sms_available(me.workspace_id):
            vals.update(sms_consent=True, remind_ok=True)
        try:
            a = A.create(vals)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back + '?step=4')
        request.session.pop(DRAFT % ws_id, None)
        return request.redirect('/my/workspaces/%s/invites/%s?new=1' % (ws_id, a.id))

    # ------------------------------------------------------------------ one invitation
    @http.route('/my/workspaces/<int:ws_id>/invites/<int:aid>', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def invite(self, ws_id, aid, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'invites:manage', 'invites')
        if denied:
            return denied
        a = _assignment_or_404(me, aid)
        if not me.can_act() or not me.can_see(a.client_id):
            return forbidden(me, 'invites:manage', 'invites')
        level, _results = a.visible_results(me)
        open_link = a.state in ('invited', 'opened', 'expired')
        from odoo.addons.ts_assessment.models.attempt import jalali
        deadline_fa = jalali(datetime.combine(a.deadline, time(12)), with_time=False) if a.deadline else ''
        return render_in_shell('ts_panel.invite', me, 'invites', 'دعوت %s' % a.invitee_name, a=a, c=a.client_id, deadline_fa=deadline_fa,
                               url=a.invite_url() if open_link else None, open_link=open_link,
                               is_new=bool(kw.get('new')) and open_link, level=level,
                               can_manage=me.can_invite() and not a.user_id and a.state not in ('done', 'withdrawn', 'declined'),
                               can_withdraw=me.can_invite() and a.state not in ('done', 'withdrawn', 'declined'),
                               state_labels=STATE_LABELS, pill=PILL, channel_label=dict(a._fields['channel'].selection).get(a.channel, ''),
                               days_options=(7, 14, 30))

    @http.route('/my/workspaces/<int:ws_id>/invites/<int:aid>/qr.png', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def qr(self, ws_id, aid, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'invites:manage', 'invites')
        if denied:
            return denied
        a = _assignment_or_404(me, aid)
        if not me.can_act() or not me.can_see(a.client_id) or a.state not in ('invited', 'opened', 'expired'):
            raise request.not_found()
        import io
        import qrcode   # in the Odoo virtualenv with Pillow; reportlab's PNG backend is not installed
        buf = io.BytesIO()
        qrcode.make(a.invite_url(), box_size=8, border=2).save(buf, format='PNG')
        png = buf.getvalue()
        return request.make_response(png, headers=[('Content-Type', 'image/png'), ('Cache-Control', 'private, no-store')])

    @http.route('/my/workspaces/<int:ws_id>/invites/<int:aid>/<string:action>', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def invite_action(self, ws_id, aid, action, **post):
        me = member_or_404(ws_id)
        if action not in ('extend', 'withdraw', 'remind'):
            raise request.not_found()
        denied = require(me, 'invites:manage', 'invites')
        if denied:
            return denied
        a = _assignment_or_404(me, aid)
        if not me.can_act() or not me.can_see(a.client_id) or not me.can_invite():
            return forbidden(me, 'invites:manage', 'invites')
        back = '/my/workspaces/%s/invites/%s' % (ws_id, a.id)
        try:
            if action == 'extend':
                days = int(post['days']) if (post.get('days') or '').isdigit() else 0
                if days not in (7, 14, 30):
                    raise UserError('مدت تمدید را از فهرست برگزینید.')
                a.action_extend(days, me)
                flash_ok('دعوت تمدید شد.')
            elif action == 'remind':
                ok, msg = a.ts_manual_reminder(me)
                (flash_ok if ok else flash_error)(msg)
            else:
                if not post.get('confirm'):
                    raise UserError('برای لغو دعوت، تأیید را تیک بزنید.')
                a.action_withdraw()
                flash_ok('دعوت لغو شد؛ پیوند دیگر کار نمی‌کند.')
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        return request.redirect(back)
