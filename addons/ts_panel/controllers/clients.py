from urllib.parse import urlencode

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_org.models.assignment import RESPONSIBLE_ROLES
from odoo.addons.ts_org.models.panel import ROLE_LABELS

from ..models.text import norm_text
from .base import STATE_LABELS, flash_error, flash_ok, forbidden, member_or_404, render_in_shell, require

PAGE = 25
SORTS = {'name': 'name_norm', 'activity': 'last_activity_at', 'open': 'open_count', 'done': 'done_count'}
FILTERS = [('all', 'همه'), ('mine', 'مراجعان من'), ('unassigned', 'بدون کارشناس'), ('imported', 'واردشده'),
           ('archived', 'بایگانی‌شده')]
SOURCE_LABELS = {'manual': 'ثبت دستی', 'csv': 'فایل', 'invite': 'دعوت', 'open_link': 'پیوند عمومی',
                 'self_share': 'ارسال با کد پنل', 'import': 'واردشده'}
Q_KEY = 'ts_clients_q'


def visible_domain(me):
    """Relationship rules R0-R3 as a domain, the same answer as ts_org's member.can_see(client)."""
    dom = [('workspace_id', '=', me.workspace_id.id)]
    if me.has_perm('clients:read_all'):
        return dom
    if not me.has_perm('clients:read_own'):
        return dom + [('id', '=', 0)]
    if me.has_perm('clients:read_unassigned'):
        return dom + ['|', ('responsible_id', '=', me.id), ('responsible_id', '=', False)]
    return dom + [('responsible_id', '=', me.id)]


def _client_or_404(me, cid):
    c = request.env['ts.panel.client'].sudo().search([('id', '=', int(cid)), ('workspace_id', '=', me.workspace_id.id)])
    if not c:
        raise request.not_found()
    return c


class TsPanelClients(http.Controller):

    @http.route('/my/workspaces/<int:ws_id>/clients', type='http', auth='user', website=True,
                methods=['GET', 'POST'], sitemap=False)
    def clients(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'clients:read_own', 'clients')
        if denied:
            return denied
        if not me.can_act():
            return forbidden(me, 'clients:read_own', 'clients')
        key = '%s_%s' % (Q_KEY, ws_id)
        flt = kw.get('filter') if kw.get('filter') in dict(FILTERS) else 'all'
        if request.httprequest.method == 'POST':
            # the search text stays out of the URL (names are personal data): keep it in the session, redirect
            request.session[key] = (kw.get('q') or '').strip()[:100]
            qs = urlencode({'filter': flt}) if flt != 'all' else ''
            return request.redirect('/my/workspaces/%s/clients%s' % (ws_id, '?' + qs if qs else ''))
        q = request.session.get(key) or ''
        sort = kw.get('sort') if kw.get('sort') in SORTS else 'activity'
        direction = kw.get('dir') if kw.get('dir') in ('asc', 'desc') else ('asc' if sort == 'name' else 'desc')
        desc = direction == 'desc'
        dom = visible_domain(me)
        dom += [('state', '=', 'archived')] if flt == 'archived' else [('state', '=', 'active')]
        if flt == 'mine':
            dom.append(('responsible_id', '=', me.id))
        elif flt == 'unassigned':
            dom.append(('responsible_id', '=', False))
        elif flt == 'imported':
            dom.append(('source', '=', 'import'))
        if q:
            qn = norm_text(q)
            dom += ['|', '|', '|', ('name_norm', 'ilike', qn), ('code', 'ilike', q), ('phone', 'ilike', qn),
                    ('email', 'ilike', q.lower())]
        C = request.env['ts.panel.client'].sudo()
        total = C.search_count(dom)
        pages = max(1, -(-total // PAGE))
        page = min(max(int(kw['page']) if (kw.get('page') or '').isdigit() else 1, 1), pages)
        rows = C.search(dom, order='%s %s, id desc' % (SORTS[sort], 'desc' if desc else 'asc'),
                        limit=PAGE, offset=(page - 1) * PAGE)
        base = {'filter': flt, 'sort': sort, 'dir': direction}

        def url(**over):
            d = dict(base, **over)
            if d['filter'] == 'all':
                d.pop('filter')
            return '/my/workspaces/%s/clients?%s' % (ws_id, urlencode(d))

        return render_in_shell(
            'ts_panel.clients', me, 'clients', 'شرکت‌کنندگان', rows=rows, total=total, page=page, pages=pages,
            filters=FILTERS, flt=flt, q=q, sort=sort, desc=desc, url=url, source_labels=SOURCE_LABELS,
            n_all=C.search_count(visible_domain(me) + [('state', '=', 'active')]))

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>', type='http', auth='user', website=True, sitemap=False)
    def client_page(self, ws_id, cid, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'clients:read_own', 'clients')
        if denied:
            return denied
        c = _client_or_404(me, cid)
        if not me.can_act() or not me.can_see(c):
            return forbidden(me, 'clients:read_own', 'clients')
        can_assign = me.has_perm('clients:assign')
        cands = request.env['ts.workspace.member'].sudo().search(
            [('workspace_id', '=', me.workspace_id.id), ('active', '=', True), ('role', 'in', list(RESPONSIBLE_ROLES))]
        ).filtered(lambda m: m.can_act() and m.user_id != c.user_id) if can_assign else []
        assignments = c.assignment_ids.sorted(lambda a: (a.create_date, a.id), reverse=True)
        imports = c.attempt_ids.filtered(lambda t: t.source == 'import').sorted(lambda t: (t.create_date, t.id), reverse=True)
        return render_in_shell(
            'ts_panel.client', me, 'clients', c.name, c=c, assignments=assignments, imports=imports,
            can_assign=can_assign, cands=cands, state_labels=STATE_LABELS, source_label=SOURCE_LABELS.get(c.source, c.source),
            role_labels=ROLE_LABELS,
            level=lambda a: a.result_level(me), level_t=lambda t: t.ts_result_level(me))

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/responsible', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def client_responsible(self, ws_id, cid, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'clients:assign', 'clients')
        if denied:
            return denied
        c = _client_or_404(me, cid)
        back = '/my/workspaces/%s/clients/%s' % (ws_id, cid)
        if not me.can_act() or not me.can_see(c):
            return forbidden(me, 'clients:assign', 'clients')
        rid = (post.get('responsible_id') or '').strip()
        target = request.env['ts.workspace.member'].sudo().browse()  # ts-scope-ok: empty set
        if rid:
            target = request.env['ts.workspace.member'].sudo().search(
                [('id', '=', int(rid) if rid.isdigit() else 0), ('workspace_id', '=', me.workspace_id.id), ('active', '=', True)])
            if not target:
                raise request.not_found()
        try:
            c.write({'responsible_id': target.id or False})
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('کارشناس مسئول ذخیره شد.' if target else 'کارشناس مسئول برداشته شد.')
        return request.redirect(back)
