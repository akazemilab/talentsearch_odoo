"""onb3 pages: the member's try-out («پیش‌نمایش»), the sample report per kind (panel and public), the one-screen
invitation with the panel's permanent link and QR, the dashboard cards' «بعداً», the per-member guide-SMS switch and the
end of a try-out. Every panel route starts with member_or_404 and checks its own permission; nothing here reads a result
the existing checks would not show (a try-out is the member's own data)."""
import io
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_billing.controllers.main import TsBillingInvites
from odoo.addons.ts_battery.controllers.main import _picker_ctx
from odoo.addons.ts_org.models.panel import norm_email, norm_phone
from odoo.addons.ts_panel.controllers.base import flash_error, flash_ok, forbidden, member_or_404, render_in_shell, require
from odoo.addons.ts_panel.controllers.clients import AGE, visible_domain
from odoo.addons.ts_panel.controllers.invites import sms_available
from odoo.addons.ts_tasks.controllers.main import TsTaskPlayer
from odoo.addons.ts_website.tools import parse_jdate

SAMPLE_KINDS = ('clinic', 'solo', 'school', 'hr')
KIND_TITLES = {'clinic': 'گزارش نمونهٔ مرکز مشاوره', 'solo': 'گزارش نمونهٔ مشاور مستقل', 'school': 'گزارش نمونهٔ مدرسه',
               'hr': 'گزارش نمونهٔ استخدام'}


def _sample_ctx(kind, ws=None):
    """Template values of the sample report of `kind` (None when its instruments are not published). `ws`: the panel the
    talent report names inside a panel; the public page names the synthetic «مدرسهٔ نمونه»."""
    d = request.env['ts.onb.sample'].sudo().ts_kind_sample(kind)
    if not d:
        return None
    ctx = {'sample': d, 'sample_kind': d['kind'], 'fa': fa_digits}
    if d['kind'] == 'school':
        from odoo.addons.ts_talent.controllers.main import report_ctx
        rc = report_ctx(d['attempt'], org_view=True, ws=ws or d['ws'])
        for k in ('title', 'page_name'):
            rc.pop(k, None)
        rc['who'] = d['who']
        ctx['talent'] = rc
    if d['kind'] == 'hr':
        from odoo.addons.ts_hire.controllers.positions import STATUS
        ctx.update(r=d['r'], res=d['res'], st_labels=STATUS, a=None)
    return ctx


class TsOnb3Panel(http.Controller):

    # ------------------------------------------------------------------ the try-out
    @http.route('/my/workspaces/<int:ws_id>/try', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def onb_try(self, ws_id, **post):
        me = member_or_404(ws_id)
        if not me.ts_onb_can_try():
            return forbidden(me, 'invites:create', 'home')
        try:
            a = me.ts_onb_try()
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect('/my/workspaces/%s' % ws_id)
        if a.state == 'done':
            return request.redirect(me.ts_onb_preview_url(a))
        return request.redirect(me.ts_onb_take_url(a))

    @http.route('/my/workspaces/<int:ws_id>/try/end', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def onb_try_end(self, ws_id, **kw):
        me = member_or_404(ws_id)
        a = me.ts_onb_preview()
        if a and a.state == 'done':
            return request.redirect(me.ts_onb_preview_url(a))
        if a:
            return request.redirect(me.ts_onb_take_url(a))
        return request.redirect('/my/workspaces/%s' % ws_id)

    # ------------------------------------------------------------------ the sample report inside the panel
    @http.route('/my/workspaces/<int:ws_id>/sample', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def onb_sample(self, ws_id, **kw):
        me = member_or_404(ws_id)
        ws = me.workspace_id
        kind = ws.ts_onb_kind() or 'clinic'
        ctx = _sample_ctx(kind, ws=ws)
        if not ctx:
            raise request.not_found()
        pv = me.ts_onb_preview()
        extra = dict(title_kind=KIND_TITLES.get(kind), words=ws.ts_onb_words(), invite_url=me.ts_onb_invite_url(),
                     invite_cta=me.ts_onb_invite_cta(), can_try=me.ts_onb_can_try() and not (pv and pv.state == 'done'),
                     try_url='/my/workspaces/%s/try' % ws.id)
        if ctx['sample_kind'] == 'school':
            talent = dict(ctx.pop('talent'))
            talent.pop('ws', None)                 # the shell's own panel
            vals = dict(talent)
            vals.update(ctx)
            vals.update(extra)
            vals.update(report_frame='ts_onboard.sample_shell_frame', autoprint=False, viewers=None, print_url=None)
            return render_in_shell('ts_talent.report', me, 'home', 'نمونهٔ گزارش', **vals)
        vals = dict(ctx)
        vals.update(extra)
        return render_in_shell('ts_onboard.sample_panel', me, 'home', 'نمونهٔ گزارش', **vals)

    # ------------------------------------------------------------------ cards: «بعداً»
    @http.route('/my/workspaces/<int:ws_id>/start/hide', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def onb_start_hide(self, ws_id, **post):
        me = member_or_404(ws_id)
        me.ts_onb_hide('start')
        flash_ok('«شروع کار» برای شما پنهان شد. راهنمای همین گام‌ها در «راهنما» هست.')
        return request.redirect('/my/workspaces/%s' % ws_id)

    @http.route('/my/workspaces/<int:ws_id>/more/hide', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def onb_more_hide(self, ws_id, **post):
        me = member_or_404(ws_id)
        me.ts_onb_hide('more')
        return request.redirect('/my/workspaces/%s' % ws_id)

    # ------------------------------------------------------------------ guide SMS opt-out (own membership only)
    @http.route('/my/workspaces/<int:ws_id>/members/<int:mid>/guide-sms', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def onb_guide_sms(self, ws_id, mid, **post):
        me = member_or_404(ws_id)
        if me.id != int(mid):
            return forbidden(me, 'members:self', 'members')
        on = post.get('on') == '1'
        me.sudo().ts_guide_sms = on
        request.env['ts.audit.event'].sudo().log('member.guide_sms', me, workspace=me.workspace_id, member=me, on=on)
        flash_ok('پیامک‌های راهنما روشن شد.' if on else 'پیامک‌های راهنما خاموش شد.')
        return request.redirect('/my/workspaces/%s/members/%s#tso-guide' % (ws_id, mid))

    # ------------------------------------------------------------------ the permanent link: QR (view or download)
    @http.route('/my/workspaces/<int:ws_id>/link/qr.png', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def onb_link_qr(self, ws_id, download=None, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'invites:create', 'invites')
        if denied:
            return denied
        c = me.workspace_id.ts_onb_permanent_link(me, create=False)
        if not c or c.open_state() != 'ok':
            raise request.not_found()
        import qrcode
        buf = io.BytesIO()
        qrcode.make(c.invite_url(), box_size=10, border=2).save(buf, format='PNG')
        headers = [('Content-Type', 'image/png'), ('Cache-Control', 'private, no-store')]
        if download:
            headers.append(('Content-Disposition', 'attachment; filename="talentsearch-link-%s.png"' % me.workspace_id.code))
        return request.make_response(buf.getvalue(), headers=headers)


class TsOnb3Invites(TsBillingInvites):
    """«دعوت تازه» is one screen (onb3): two equal choices, a personal invitation (name, mobile, the starter preselected, the
    SMS read-only, «فرستادن») or the panel's permanent link with its QR. Deadline, note, another instrument or battery,
    e-mail and the age group are under «تنظیمات بیشتر». The four-step wizard stays reachable for one case only: picking an
    existing participant by search (`?wizard=1`, and every POST that carries a `step`)."""

    def _one_values(self, me, kw=None, vals=None, error=None):
        kw = kw or {}
        ws = me.workspace_id
        kind = ws.ts_onb_kind()
        words = ws.ts_onb_words()
        bat, inst = ws.ts_onb_starter(me)
        d = {}
        if bat:
            d['battery_id'] = bat.id
        if inst:
            d['instrument_id'] = inst.id
        pick = _picker_ctx(me, d) if hasattr(me, 'allowed_batteries') else {}
        instruments = me.allowed_instruments()
        client = request.env['ts.panel.client'].sudo()
        cid = (kw.get('client') or (vals or {}).get('client') or '')
        if str(cid).isdigit():
            c = client.search(visible_domain(me) + [('id', '=', int(cid)), ('state', '=', 'active')], limit=1)
            if c and not c.contact_locked:
                client = c
        link = ws.ts_onb_permanent_link(me, create=False) if kind != 'hr' else None
        sms_ok = sms_available(ws)
        return dict(
            pick, words=words, kind=kind, starter_bat=bat, starter_inst=inst, instruments=instruments, client=client,
            pick_inst_id=(inst.id if (inst and not bat) else 0), sms_ok=sms_ok, preview_sms=self._sms_preview(me, bat, inst),
            need_escalation=ws.purpose == 'clinical' and not ws.escalation_contact_id,
            mode='link' if (kw.get('mode') == 'link' or (vals or {}).get('mode') == 'link') and kind != 'hr' else 'one',
            link=link if (link and link.open_state() == 'ok') else None, link_url=link.invite_url() if (link and link.open_state() == 'ok') else '',
            quota_note=ws.ts_invite_quota_note() if me.can_act() else None, age=AGE,
            age_default='minor' if ws.purpose == 'education' else 'unknown', vals=vals or {}, error=error,
            wizard_url='/my/workspaces/%s/invites/new?wizard=1&step=1' % ws.id,
            positions_url='/my/workspaces/%s/positions' % ws.id if ws.purpose == 'employment' else None,
            extra_time=ws.purpose == 'employment', fa=fa_digits)

    def _sms_preview(self, me, bat, inst):
        """The invitation SMS as it will read, from the real template (short link shown as a placeholder)."""
        ws = me.workspace_id.sudo()
        if not inst:
            return ''
        try:
            a = request.env['ts.assignment'].sudo().with_context(ts_sms_link='https://talentsearch.ir/i/…').new(
                {'workspace_id': ws.id, 'instrument_id': inst.id, 'battery_id': bat.id if bat else False,
                 'invitee_name': 'نمونه', 'invited_by_id': me.user_id.id})
            body = a._ts_invite_sms_body()
            if body:
                return body
        except Exception:       # noqa: BLE001 - the preview never breaks the page
            pass
        head = ws.ts_sms_sender() if hasattr(ws, 'ts_sms_sender') else ws.name
        return '%s\n%s\nhttps://talentsearch.ir/i/…' % (fa_digits(head), 'یک سنجه برای شما')

    @http.route()
    def wizard(self, ws_id, **post):
        method = request.httprequest.method
        if method == 'GET' and not post.get('step') and not post.get('wizard'):
            me, denied = self._wizard_guard(ws_id)
            if denied:
                return denied
            self._save_draft(ws_id, {})           # «دعوت تازه» starts clean, like ?fresh=1
            return render_in_shell('ts_onboard.invite_one', me, 'invites', 'دعوت تازه', **self._one_values(me, post))
        if method == 'POST' and post.get('one') == '1':
            return self._one_post(ws_id, post)
        if method == 'POST' and post.get('one') == 'link':
            return self._link_post(ws_id, post)
        return super().wizard(ws_id, **post)

    # ------------------------------------------------------------------ escalation, once
    def _escalation(self, me, post):
        ws = me.workspace_id
        if ws.purpose != 'clinical' or ws.sudo().escalation_contact_id:
            return None
        if not post.get('escalation_ok'):
            return 'پیش از نخستین دعوت مراجع، «پیگیری فوری نشانه‌های خطر با من است» را تیک بزنید.'
        ws.ts_set_escalation(me)
        return None

    def _link_post(self, ws_id, post):
        me, denied = self._wizard_guard(ws_id)
        if denied:
            return denied
        err = self._escalation(me, post)
        if not err:
            try:
                me.workspace_id.ts_onb_permanent_link(me)
            except (UserError, ValidationError) as e:
                err = str(e.args[0] if e.args else e)
        if err:
            return render_in_shell('ts_onboard.invite_one', me, 'invites', 'دعوت تازه',
                                   **self._one_values(me, vals=dict(post, mode='link'), error=err))
        flash_ok('پیوند همیشگی پنل آماده است.')
        return request.redirect('/my/workspaces/%s/invites/new?mode=link#tso-link' % ws_id)

    def _one_post(self, ws_id, post):
        me, denied = self._wizard_guard(ws_id)
        if denied:
            return denied

        def again(msg):
            return render_in_shell('ts_onboard.invite_one', me, 'invites', 'دعوت تازه',
                                   **self._one_values(me, vals=post, error=msg))

        err = self._escalation(me, post)
        if err:
            return again(err)
        ws = me.workspace_id
        C = request.env['ts.panel.client'].sudo()
        A = request.env['ts.assignment'].sudo()
        d = {}
        client = C.browse()
        if (post.get('client') or '').isdigit():
            client = C.search(visible_domain(me) + [('id', '=', int(post['client'])), ('state', '=', 'active')], limit=1)
            if not client or client.contact_locked:
                return again('این شرکت‌کننده را نمی‌توان دعوت کرد.')
        else:
            name = ' '.join((post.get('new_name') or '').split())
            phone_raw, email_raw = (post.get('new_phone') or '').strip(), (post.get('new_email') or '').strip()
            if not 2 <= len(name) <= 120:
                return again('نام را بین ۲ تا ۱۲۰ نویسه بنویسید.')
            if phone_raw and not norm_phone(phone_raw):
                return again('شمارهٔ موبایل معتبر نیست. مثال: ۰۹۱۲۳۴۵۶۷۸۹')
            if email_raw and not norm_email(email_raw):
                return again('ایمیل معتبر نیست.')
            if not (phone_raw or email_raw):
                return again('شمارهٔ موبایل را بنویسید تا پیوند دعوت با پیامک برسد (یا در «تنظیمات بیشتر» ایمیل بدهید).')
            d.update(new_name=name, new_phone=norm_phone(phone_raw) or '', new_email=norm_email(email_raw) or '',
                     new_age=post.get('new_age') if post.get('new_age') in dict(AGE) else
                     ('minor' if ws.purpose == 'education' else 'unknown'))
        # the item: the starter unless «تنظیمات بیشتر» chose another (the billing check of ts_billing applies here)
        if not (post.get('instrument_id') or post.get('battery_id')):
            bat, inst = ws.ts_onb_starter(me)
            if bat:
                post = dict(post, item_kind='battery', battery_id=str(bat.id))
            elif inst:
                post = dict(post, item_kind='single', instrument_id=str(inst.id))
        err = self._read_item(me, post, d)
        if err:
            return again(err)
        typed = (post.get('deadline') or '').strip() or (post.get('deadline_jalali') or '').strip()
        if typed:
            dd = parse_jdate(post.get('deadline'), post.get('deadline_jalali'))
            if not dd or dd < fields.Date.today():
                return again('مهلت را به شکل ۱۴۰۵/۰۸/۱۵ و از امروز به بعد بنویسید.')
            d['deadline'] = str(dd)
        d['note'] = (post.get('note') or '').strip()[:300]
        limit = request.env['ir.config_parameter'].sudo().get_int('ts_panel.invites_per_hour', 200) or 200
        since = fields.Datetime.now() - timedelta(hours=1)
        if A.search_count([('workspace_id', '=', ws_id), ('invited_by_id', '=', request.env.user.id), ('create_date', '>=', since)]) >= limit:
            return again('در یک ساعت بیش از %s دعوت نمی‌توان ساخت. کمی بعد دوباره امتحان کنید.' % fa_digits(limit))
        vals = {'workspace_id': ws_id, 'instrument_id': d['instrument_id'], 'invited_by_id': request.env.user.id,
                'note': d.get('note') or False, 'deadline': d.get('deadline') or False}
        vals.update(self._item_vals(me, d))
        guardian = bool(post.get('guardian_ok'))
        if client:
            if client.ts_needs_guardian() and not guardian:
                return again('برای %s زیر ۱۸ سال تأیید کنید که رضایت ولی یا سرپرست قانونی را گرفته‌اید.' % ws.ts_onb_words()['one'])
            vals.update(client_id=client.id, invitee_name=client.name, invitee_email=client.email or False,
                        invitee_phone=client.phone or False)
        else:
            if d['new_age'] == 'minor' and not guardian:
                dups = C.ts_duplicates(ws_id, phone=d.get('new_phone'), email=d.get('new_email')).filtered(lambda c: me.can_see(c))
                if not dups or any(x.ts_needs_guardian() for x in dups):
                    return again('برای %s زیر ۱۸ سال تأیید کنید که رضایت ولی یا سرپرست قانونی را گرفته‌اید.' % ws.ts_onb_words()['one'])
            vals.update(invitee_name=d['new_name'], invitee_email=d.get('new_email') or False,
                        invitee_phone=d.get('new_phone') or False)
        # «فرستادن» with the line under it is the attestation that the person agrees to the SMS (same rule as the wizard)
        if vals.get('invitee_phone') and sms_available(ws) and post.get('attest') == '1':
            vals.update(sms_consent=True, remind_ok=True)
        if ws.purpose == 'employment' and post.get('extra_time') in ('1.25', '1.5'):
            vals['ts_extra_time'] = post['extra_time']
        try:
            with request.env.cr.savepoint():
                if client and client.ts_needs_guardian():
                    client.ts_attest_guardian(me)
                a = A.create(vals)
                if not client and a.client_id and d.get('new_age') in ('minor', 'adult') and a.client_id.age_group == 'unknown':
                    a.client_id.sudo().age_group = d['new_age']
                    if d['new_age'] == 'minor' and guardian:
                        a.client_id.ts_attest_guardian(me)
        except (UserError, ValidationError) as e:
            return again(str(e.args[0] if e.args else e))
        # the invitation SMS goes out from ts_sms's create hook (sms_consent); the next page says whether it reached
        return request.redirect('/my/workspaces/%s/invites/%s?new=1' % (ws_id, a.id))


class TsOnb3Player(TsTaskPlayer):
    """The end of a try-out: the member lands on the report as his panel sees a client's (with the coach line)."""

    def _ts_preview_end(self, a):
        if a and a.ts_preview and a.user_id == request.env.user and a.state == 'done' and a.workspace_id:
            return request.redirect('/my/workspaces/%s/try/end' % a.workspace_id.id)
        return None

    @http.route()
    def my_report(self, attempt_id, **kw):
        if kw.get('submitted'):
            at = request.env['ts.attempt'].sudo().search([('id', '=', int(attempt_id)), ('user_id', '=', request.env.user.id),
                                                           ('ts_preview', '=', True), ('state', '=', 'done')], limit=1)
            a = (at.assignment_id if at and 'assignment_id' in at._fields and at.assignment_id else
                 request.env['ts.assignment'].sudo().search([('attempt_id', '=', at.id)], limit=1)) if at else None
            res = self._ts_preview_end(a)
            if res:
                return res
        return super().my_report(attempt_id, **kw)

    @http.route()
    def my_battery(self, assignment_id, **kw):
        if kw.get('submitted'):
            a = request.env['ts.assignment'].sudo().search([('id', '=', int(assignment_id)),
                                                             ('user_id', '=', request.env.user.id), ('ts_preview', '=', True)], limit=1)
            res = self._ts_preview_end(a)
            if res:
                return res
        return super().my_battery(assignment_id, **kw)

    @http.route()
    def my_list(self, **kw):
        """A try-out in the member's own list says «پیش‌نمایش» next to the panel it was taken for."""
        res = super().my_list(**kw)
        qc = getattr(res, 'qcontext', None)
        if qc is None:
            return res
        att = qc.get('attempts')
        if att is not None and isinstance(qc.get('shares'), dict):
            for t in att.filtered(lambda x: x.sudo().ts_preview and x.id in qc['shares']):
                qc['shares'][t.id] = '%s (پیش‌نمایش)' % qc['shares'][t.id]
        for key in ('batteries_done', 'batteries_going'):
            for row in qc.get(key) or []:
                if row.get('a') is not None and row['a'].ts_preview:
                    row['org'] = '%s (پیش‌نمایش)' % (row.get('org') or '')
        return res


class TsOnb3Public(http.Controller):

    @http.route('/sample/<string:kind>', type='http', auth='public', website=True, methods=['GET'], sitemap=False)
    def public_sample(self, kind, **kw):
        """The public sample report of a kind (audience pages): synthetic data, real templates, labelled «نمونه»."""
        _ts_site_or_404()
        if kind not in SAMPLE_KINDS:
            raise request.not_found()
        ctx = _sample_ctx(kind)
        if not ctx:
            raise request.not_found()
        back = {'clinic': '/clinics', 'solo': '/clinics', 'school': '/schools', 'hr': '/hiring'}[kind]
        extra = dict(title_kind=KIND_TITLES[kind], back_url=back, build_url='/panel?kind=%s' % {'hr': 'org'}.get(kind, kind),
                     page_name='ts_sample', additional_title=KIND_TITLES[kind])
        if ctx['sample_kind'] == 'school':
            talent = ctx.pop('talent')
            vals = dict(talent)
            vals.update(ctx)
            vals.update(extra)
            vals.update(report_frame='ts_onboard.sample_public_frame', autoprint=False, viewers=None, print_url=None)
            return request.render('ts_talent.report', vals)
        return request.render('ts_onboard.sample_public', dict(ctx, **extra))
