"""Group invitations and the open link, staff side (S7, INV-5, INV-6, INV-9).
The form keeps its draft in the session; the review step shows who will be invited and who is skipped, and nothing is
created before the last step."""
import io
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .base import STATE_LABELS, flash_error, flash_ok, forbidden, member_or_404, render_in_shell, require
from .clients import visible_domain
from .invites import PILL, STATE_ORDER, _fa, assignment_domain, sms_available

DRAFT = 'ts_campaign_draft_%s'
PAGE = 25
MAX_LIST = 200          # one campaign; larger batches wait for the background jobs of S8
KIND_LABELS = {'list': 'دعوت گروهی', 'open_link': 'پیوند باز'}
STATE_C = {'open': 'باز', 'closed': 'بسته', 'draft': 'پیش‌نویس'}
SKIP_LABELS = {'busy': 'دعوت باز برای همین سنجه دارند', 'locked': 'اطلاعات تماسشان قفل است', 'archived': 'بایگانی شده‌اند'}


def _campaign_domain(me):
    dom = [('workspace_id', '=', me.workspace_id.id)]
    if not me.has_perm('clients:read_all'):
        dom.append(('created_by_id', '=', me.id))
    return dom


class TsPanelCampaigns(http.Controller):

    # ------------------------------------------------------------------ guard
    def _guard(self, ws_id):
        me = member_or_404(ws_id)
        if me.can_act() and me.can_invite() and not me.can_invite_participants():
            return me, render_in_shell('ts_panel.state_page', me, 'campaigns', 'دعوت گروهی هنوز ممکن نیست',
                                       state_title='دعوت گروهی پس از تأیید پنل ممکن می‌شود',
                                       state_text='پنل شما در انتظار تأیید مالک پلتفرم است. تا آن زمان می‌توانید شرکت‌کنندگان را ثبت و گروه‌بندی کنید.')
        denied = require(me, 'invites:bulk', 'campaigns')
        if denied:
            return me, denied
        if not me.can_act():
            return me, forbidden(me, 'invites:bulk', 'campaigns')
        return me, None

    def _campaign_or_404(self, me, cid):
        c = request.env['ts.campaign'].sudo().search([('id', '=', int(cid)), ('workspace_id', '=', me.workspace_id.id)])
        if not c:
            raise request.not_found()
        return c

    def _can_open(self, me, c):
        return me.has_perm('clients:read_all') or c.created_by_id == me

    # ------------------------------------------------------------------ list
    @http.route('/my/workspaces/<int:ws_id>/campaigns', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def campaigns(self, ws_id, **kw):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        C = request.env['ts.campaign'].sudo()
        dom = _campaign_domain(me)
        total = C.search_count(dom)
        pages = max(1, -(-total // PAGE))
        page = min(max(int(kw['page']) if (kw.get('page') or '').isdigit() else 1, 1), pages)
        rows = C.search(dom, limit=PAGE, offset=(page - 1) * PAGE)
        vis = assignment_domain(me)
        joined = {c.id: request.env['ts.assignment'].sudo().search_count(vis + [('campaign_id', '=', c.id)]) for c in rows}  # ts-scope-ok: vis is the workspace-scoped assignment domain
        return render_in_shell('ts_panel.campaigns', me, 'campaigns', 'دعوت گروهی', rows=rows, joined=joined, kind_labels=KIND_LABELS,
                               state_c=STATE_C, total=total, page=page, pages=pages, ws_id=ws_id)

    # ------------------------------------------------------------------ form and review
    def _groups(self, me):
        return request.env['ts.panel.group'].sudo().search([('workspace_id', '=', me.workspace_id.id), ('active', '=', True)])

    def _form_ctx(self, me, d, **extra):
        vals = dict(draft=d, instruments=me.allowed_instruments(), groups=self._groups(me), sms_ok=sms_available(me.workspace_id),
                    open_default=request.env['ir.config_parameter'].sudo().get_int('ts_panel.open_link_max', 60) or 60,
                    max_list=MAX_LIST)
        vals.update(extra)
        return vals

    @http.route('/my/workspaces/<int:ws_id>/campaigns/new', type='http', auth='user', website=True,
                methods=['GET', 'POST'], sitemap=False)
    def new(self, ws_id, **post):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        back = '/my/workspaces/%s/campaigns/new' % ws_id
        if request.httprequest.method == 'GET':
            d = {}
            if (post.get('group') or '').isdigit():
                g = self._groups(me).filtered(lambda x: x.id == int(post['group']))
                if g:
                    d = {'kind': 'list', 'group_ids': [g.id], 'name': g.name}
            elif post.get('keep') and request.session.get(DRAFT % ws_id):
                d = request.session[DRAFT % ws_id]
            return render_in_shell('ts_panel.campaign_form', me, 'campaigns', 'دعوت گروهی تازه', **self._form_ctx(me, d))
        step = post.get('step')
        if step == 'create':
            return self._create(me, ws_id)
        d, err = self._read_form(me, post)
        request.session[DRAFT % ws_id] = d
        if err:
            flash_error(err)
            return request.redirect(back + '?keep=1')
        extra = {}
        if d['kind'] == 'list':
            clients = self._clients_of(me, d['group_ids'])
            to_invite, skipped = request.env['ts.campaign'].sudo().ts_targets(clients, ws_id, d['instrument_id'])
            if not clients:
                flash_error('در گروه‌های انتخاب‌شده کسی نیست که بتوانید برایش دعوت بسازید.')
                return request.redirect(back + '?keep=1')
            extra = dict(clients=clients, to_invite=to_invite, skipped=skipped, skip_labels=SKIP_LABELS)
        inst = request.env['ts.instrument'].sudo().browse(d['instrument_id'])  # ts-scope-ok: instrument is global, not workspace data
        return render_in_shell('ts_panel.campaign_review', me, 'campaigns', 'مرور دعوت گروهی', draft=d, inst=inst,
                               groups=self._groups(me).filtered(lambda g: g.id in d.get('group_ids', [])),
                               kind_labels=KIND_LABELS, **extra)

    def _clients_of(self, me, group_ids):
        C = request.env['ts.panel.client'].sudo()
        return C.search(visible_domain(me) + [('group_ids', 'in', group_ids)], order='name_norm, id')   # ts-scope-ok: visible_domain() starts with the panel

    def _read_form(self, me, post):
        d = {'kind': post.get('kind') if post.get('kind') in KIND_LABELS else 'list'}
        d['name'] = (post.get('name') or '').strip()
        err = None
        if not 2 <= len(d['name']) <= 80:
            err = 'عنوان را بین ۲ تا ۸۰ نویسه بنویسید.'
        iid = post.get('instrument_id') or ''
        if not iid.isdigit() or int(iid) not in me.allowed_instruments().ids:
            err = err or 'سنجهٔ انتخاب‌شده برای این پنل مجاز نیست.'
        d['instrument_id'] = int(iid) if iid.isdigit() else 0
        dl = (post.get('deadline') or '').strip()
        if dl:
            try:
                dd = fields.Date.to_date(dl)
            except Exception:
                dd = None
            if not dd or dd < fields.Date.today():
                err = err or 'مهلت باید تاریخی از امروز به بعد باشد.'
            else:
                d['deadline'] = str(dd)
        d['note'] = (post.get('note') or '').strip()[:300]
        if d['kind'] == 'list':
            gids = request.httprequest.form.getlist('group_ids')
            ok = set(self._groups(me).ids)
            d['group_ids'] = sorted({int(g) for g in gids if g.isdigit() and int(g) in ok})
            if not d['group_ids']:
                err = err or 'دست‌کم یک گروه را انتخاب کنید.'
            d['sms'] = bool(post.get('sms')) and sms_available(me.workspace_id)
            if post.get('sms') and not post.get('attest'):
                err = err or 'برای ارسال پیامک، تأیید رضایت شرکت‌کنندگان را تیک بزنید.'
                d['sms'] = False
            d['remind'] = bool(post.get('remind'))
        else:
            mx = post.get('open_max') or ''
            d['open_max'] = int(mx) if mx.isdigit() and 1 <= int(mx) <= 500 else 0
            if not d['open_max']:
                err = err or 'سقف پیوستن را بین ۱ تا ۵۰۰ بنویسید.'
            days = post.get('open_days') or ''
            d['open_days'] = int(days) if days in ('7', '14', '30') else 14
        return d, err

    def _create(self, me, ws_id):
        back = '/my/workspaces/%s/campaigns/new' % ws_id
        d = request.session.get(DRAFT % ws_id)
        if not d or not d.get('instrument_id') or d['instrument_id'] not in me.allowed_instruments().ids:
            flash_error('فرم را دوباره پر کنید.')
            return request.redirect(back)
        Campaign = request.env['ts.campaign'].sudo()
        vals = {'workspace_id': ws_id, 'name': d['name'], 'instrument_id': d['instrument_id'], 'kind': d['kind'],
                'deadline': d.get('deadline') or False, 'note': d.get('note') or False, 'created_by_id': me.id}
        A = request.env['ts.assignment'].sudo()
        limit = request.env['ir.config_parameter'].sudo().get_int('ts_panel.invites_per_hour', 200) or 200
        try:
            if d['kind'] == 'list':
                clients = self._clients_of(me, d['group_ids'])
                to_invite, _skipped = Campaign.ts_targets(clients, ws_id, d['instrument_id'])
                since = fields.Datetime.now() - timedelta(hours=1)
                recent = A.search_count([('workspace_id', '=', ws_id), ('invited_by_id', '=', request.env.user.id), ('create_date', '>=', since)])
                if len(to_invite) > MAX_LIST or recent + len(to_invite) > limit:
                    flash_error('در یک ساعت بیش از %s دعوت نمی‌توان ساخت؛ گروه کوچک‌تری انتخاب کنید یا کمی بعد دوباره امتحان کنید.' % _fa(limit))
                    return request.redirect(back + '?keep=1')
                vals.update(group_ids=[(6, 0, d['group_ids'])], send_sms=bool(d.get('sms')), remind=bool(d.get('remind')))
                c = Campaign.create(vals)
                created, skipped = c.ts_launch(clients)
                request.env['ts.audit.event'].log('campaign.create', c, workspace=c.workspace_id, member=me, kind='list',
                                                  invited=len(created), skipped=sum(len(v) for v in skipped.values()))
                parts = ['%s دعوت ساخته شد' % _fa(len(created))]
                skip_txt = '، '.join('%s نفر %s' % (_fa(len(v)), SKIP_LABELS[k]) for k, v in skipped.items() if v)
                flash_ok('. '.join(parts + (['کنار گذاشته شدند: ' + skip_txt] if skip_txt else [])) + '.')
            else:
                vals.update(open_max=d['open_max'], open_expires_at=fields.Datetime.now() + timedelta(days=d.get('open_days', 14)))
                c = Campaign.create(vals)
                request.env['ts.audit.event'].log('campaign.create', c, workspace=c.workspace_id, member=me, kind='open_link',
                                                  open_max=c.open_max)
                flash_ok('پیوند باز ساخته شد. آن را با گروه به اشتراک بگذارید یا برگهٔ چاپی را بگیرید.')
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back + '?keep=1')
        request.session.pop(DRAFT % ws_id, None)
        return request.redirect('/my/workspaces/%s/campaigns/%s' % (ws_id, c.id))

    # ------------------------------------------------------------------ one campaign (INV-9)
    @http.route('/my/workspaces/<int:ws_id>/campaigns/<int:cid>', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def campaign(self, ws_id, cid, **kw):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        c = self._campaign_or_404(me, cid)
        if not self._can_open(me, c):
            return forbidden(me, 'invites:bulk', 'campaigns')
        vis = assignment_domain(me)
        counts = c.counts(vis)
        A = request.env['ts.assignment'].sudo()
        rows = A.search(vis + [('campaign_id', '=', c.id)], order='create_date desc, id desc', limit=100)
        total = A.search_count(vis + [('campaign_id', '=', c.id)])
        return render_in_shell('ts_panel.campaign', me, 'campaigns', c.name, c=c, counts=counts, rows=rows, total=total,
                               state_order=STATE_ORDER, state_labels=STATE_LABELS, pill=PILL, kind_labels=KIND_LABELS,
                               state_c=STATE_C, open_state=c.open_state() if c.kind == 'open_link' else None,
                               url=c.invite_url() if c.kind == 'open_link' else None, joined=c.joined_count() if c.kind == 'open_link' else 0,
                               can_close=c.state == 'open', is_new=bool(kw.get('new')))

    @http.route('/my/workspaces/<int:ws_id>/campaigns/<int:cid>/close', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def close(self, ws_id, cid, **post):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        c = self._campaign_or_404(me, cid)
        if not self._can_open(me, c):
            return forbidden(me, 'invites:bulk', 'campaigns')
        if not post.get('confirm'):
            flash_error('برای بستن، تأیید را تیک بزنید.')
        else:
            c.ts_close(me)
            flash_ok('بسته شد؛ از این پس کسی نمی‌پیوندد. دعوت‌های ساخته‌شده سر جایشان هستند.')
        return request.redirect('/my/workspaces/%s/campaigns/%s' % (ws_id, c.id))

    @http.route('/my/workspaces/<int:ws_id>/campaigns/<int:cid>/qr.png', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def qr(self, ws_id, cid, **kw):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        c = self._campaign_or_404(me, cid)
        if not self._can_open(me, c) or c.kind != 'open_link' or c.open_state() != 'ok':
            raise request.not_found()
        import qrcode
        buf = io.BytesIO()
        qrcode.make(c.invite_url(), box_size=8, border=2).save(buf, format='PNG')
        return request.make_response(buf.getvalue(), headers=[('Content-Type', 'image/png'), ('Cache-Control', 'private, no-store')])

    @http.route('/my/workspaces/<int:ws_id>/campaigns/<int:cid>/sheet', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def sheet(self, ws_id, cid, **kw):
        me, denied = self._guard(ws_id)
        if denied:
            return denied
        c = self._campaign_or_404(me, cid)
        if not self._can_open(me, c):
            return forbidden(me, 'invites:bulk', 'campaigns')
        invs = request.env['ts.assignment'].sudo().browse()  # ts-scope-ok: empty recordset
        if c.kind == 'list':
            invs = request.env['ts.assignment'].sudo().search(  # ts-scope-ok: domain is campaign-scoped, campaign checked against workspace above
                assignment_domain(me) + [('campaign_id', '=', c.id), ('state', 'in', ('invited', 'opened'))], limit=60)
        return render_in_shell('ts_panel.campaign_sheet', me, 'campaigns', 'برگهٔ چاپی ' + c.name, c=c, invs=invs,
                               url=c.invite_url() if c.kind == 'open_link' else None,
                               open_ok=c.kind == 'open_link' and c.open_state() == 'ok')
