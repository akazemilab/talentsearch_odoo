from urllib.parse import parse_qsl, urlencode

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_org.models.assignment import RESPONSIBLE_ROLES
from odoo.addons.ts_org.models.panel import ROLE_LABELS, norm_email, norm_phone

from ..models.text import norm_text
from .base import STATE_LABELS, flash_error, flash_ok, forbidden, member_or_404, render_in_shell, require

PAGE = 25
SORTS = {'name': 'name_norm', 'activity': 'last_activity_at', 'open': 'open_count', 'done': 'done_count'}
FILTERS = [('all', 'همه'), ('mine', 'شرکت‌کنندگان من'), ('unassigned', 'بدون کارشناس'), ('imported', 'واردشده'),
           ('archived', 'بایگانی‌شده'), ('handover', 'درخواست سپردن'), ('mine_open', 'شرکت‌کنندگان من با دعوت باز'),
           ('done', 'تکمیل‌شده')]


def role_filters(me):
    """The chips this member can use (G5-P2-3, G5-P14-2): responsibility chips only for roles that hold participants,
    the handover chip only for those who decide on it, «من» first for members who see only their own."""
    labels = dict(FILTERS)
    resp = me.has_perm('clients:be_responsible')
    if not resp and me.has_perm('clients:read_all') and not me.has_perm('clients:assign'):
        keys = ['all', 'done', 'archived']                       # e.g. an employment reviewer: sees everyone, holds no one
    elif resp and not me.has_perm('clients:read_all'):
        keys = ['mine', 'mine_open', 'all', 'done', 'imported', 'archived']
        if me.has_perm('clients:read_unassigned'):
            keys.insert(2, 'unassigned')
    else:
        keys = ['all', 'mine', 'unassigned', 'done', 'imported', 'archived', 'handover', 'mine_open']
        if not resp:
            keys = [k for k in keys if k not in ('mine', 'mine_open')]
    if not me.has_perm('clients:assign'):
        keys = [k for k in keys if k != 'handover']
    return [(k, labels[k]) for k in keys]


def default_filter(me):
    """Members who see only their own participants start on «شرکت‌کنندگان من»."""
    return 'mine' if me.has_perm('clients:be_responsible') and not me.has_perm('clients:read_all') else 'all'
SOURCE_LABELS = {'manual': 'ثبت دستی', 'csv': 'فایل', 'invite': 'دعوت', 'open_link': 'پیوند عمومی',
                 'self_share': 'ارسال با کد پنل', 'import': 'واردشده'}
Q_KEY = 'ts_clients_q'
COLUMNS = [('source', 'منبع'), ('responsible', 'کارشناس مسئول'), ('open', 'در جریان'), ('done', 'تکمیل‌شده'),
           ('activity', 'آخرین فعالیت')]
AGE = [('unknown', 'نامشخص'), ('adult', 'بزرگسال'), ('minor', 'زیر ۱۸ سال')]
RELATIONS = [('', '—'), ('father', 'پدر'), ('mother', 'مادر'), ('guardian', 'سرپرست قانونی'), ('other', 'سایر')]
BULK = {'assign': 'clients:assign', 'group_add': 'groups:manage', 'group_remove': 'groups:manage',
        'archive': 'clients:archive', 'restore': 'clients:archive', 'merge': 'clients:merge'}


def _ids(name):
    return [int(x) for x in request.httprequest.form.getlist(name) if x.isdigit()][:200]


def _clean_query(q):
    """Only whitelisted list parameters survive; the search text is never among them."""
    out = {}
    for k, v in parse_qsl(q or ''):
        if k == 'filter' and v in dict(FILTERS):
            out[k] = v
        elif k == 'sort' and v in SORTS:
            out[k] = v
        elif k == 'dir' and v in ('asc', 'desc'):
            out[k] = v
        elif k == 'group' and v.isdigit():
            out[k] = v
    return out


def _cols(raw):
    keys = [c for c in (raw or '').split(',') if c in dict(COLUMNS)]
    return keys or [c for c, _ in COLUMNS]


def visible_domain(me):
    """Relationship rules R0-R3 as a domain, the same answer as ts_org's member.can_see(client). A member's own try-out
    (source «preview», onb3) is in no list or count of the panel: the dashboard's «شروع کار» card and, in hiring, the
    sample position show it, labelled «پیش‌نمایش»."""
    dom = [('workspace_id', '=', me.workspace_id.id), ('source', '!=', 'preview')]
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

    # ------------------------------------------------------------------ the list
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
        if request.httprequest.method == 'POST':
            # the search text stays out of the URL (names are personal data): keep it in the session, redirect
            request.session[key] = (kw.get('q') or '').strip()[:100]
            back = _clean_query(urlencode({k: kw.get(k) for k in ('filter', 'group', 'sort', 'dir') if kw.get(k)}))
            return request.redirect('/my/workspaces/%s/clients%s' % (ws_id, '?' + urlencode(back) if back else ''))
        SV = request.env['ts.saved.view'].sudo()
        views = SV.search([('member_id', '=', me.id), ('page', '=', 'clients')])
        view = views.filtered(lambda v: str(v.id) == kw.get('view'))[:1]
        if not view and not any(kw.get(k) for k in ('filter', 'group', 'sort', 'dir', 'page', 'cols', 'view')):
            view = views.filtered('is_default')[:1]
        params = _clean_query(view.query) if view else {}
        params.update(_clean_query(urlencode({k: kw[k] for k in ('filter', 'group', 'sort', 'dir') if kw.get(k)})))
        cols = _cols(kw['cols'] if 'cols' in kw else (view.columns if view else ''))
        q = request.session.get(key) or ''
        dflt = default_filter(me)
        flt = params.get('filter', dflt)
        sort = params.get('sort', 'activity')
        direction = params.get('dir') or ('asc' if sort == 'name' else 'desc')
        desc = direction == 'desc'
        dom = visible_domain(me)
        dom += [('state', '=', 'archived')] if flt == 'archived' else [('state', '=', 'active')]
        if flt == 'mine':
            dom.append(('responsible_id', '=', me.id))
        elif flt == 'unassigned':
            dom.append(('responsible_id', '=', False))
        elif flt == 'imported':
            dom.append(('source', '=', 'import'))
        elif flt == 'handover':
            dom.append(('handover_to_id', '!=', False))
        elif flt == 'mine_open':
            dom += [('responsible_id', '=', me.id), ('open_count', '>', 0)]
        elif flt == 'done':
            dom.append(('done_count', '>', 0))
        G = request.env['ts.panel.group'].sudo()
        groups = G.search([('workspace_id', '=', ws_id)])
        group = groups.filtered(lambda g: str(g.id) == params.get('group'))[:1]
        if group:
            dom.append(('group_ids', 'in', group.ids))
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
        base = {'sort': sort, 'dir': direction}
        if flt != dflt:
            base['filter'] = flt
        if group:
            base['group'] = group.id
        if 'cols' in kw or (view and view.columns):
            base['cols'] = ','.join(cols)

        def url(**over):
            d = dict(base, **over)
            return '/my/workspaces/%s/clients?%s' % (ws_id, urlencode(d))

        def filter_url(f):
            d = {k: v for k, v in base.items() if k != 'filter'}
            if f != dflt:
                d['filter'] = f
            return '/my/workspaces/%s/clients%s' % (ws_id, '?' + urlencode(d) if d else '')

        can_bulk = {a: me.has_perm(p) for a, p in BULK.items()}
        # the counselor's loop in one row: latest result to open, and «دعوت به سنجه» (G3-P3-3)
        results = {}
        for c in rows.filtered(lambda r: r.done_count):
            done = c.assignment_ids.filtered(lambda a: a.state == 'done' and a.attempt_id).sorted(
                lambda a: (a.attempt_id.submitted_at or a.create_date, a.id), reverse=True)
            for a in done:
                if a.result_level(me) != 'none':
                    results[c.id] = '/my/workspaces/%s/clients/%s/r/%s' % (ws_id, c.id, a.attempt_id.id)
                    break
        can_invite = me.can_invite() and me.has_perm('invites:create') and me.can_invite_participants()
        assignable = request.env['ts.workspace.member'].sudo().search(
            [('workspace_id', '=', ws_id), ('active', '=', True), ('role', 'in', list(RESPONSIBLE_ROLES))]
        ).filtered(lambda m: m.can_act()) if can_bulk['assign'] else []
        return render_in_shell(
            'ts_panel.clients', me, 'clients', 'شرکت‌کنندگان', rows=rows, total=total, page=page, pages=pages,
            filters=role_filters(me), flt=flt, dflt=dflt, q=q, sort=sort, desc=desc, direction=direction, url=url, filter_url=filter_url,
            results=results, can_invite=can_invite, purpose=me.workspace_id.purpose,
            source_labels=SOURCE_LABELS, cols=cols, all_cols=COLUMNS, groups=groups.filtered('active'), group=group,
            views=views, view=view, can_bulk=can_bulk, any_bulk=any(can_bulk.values()), assignable=assignable,
            can_write=me.has_perm('clients:write'), role_labels=ROLE_LABELS,
            n_all=C.search_count(visible_domain(me) + [('state', '=', 'active')]))

    # ------------------------------------------------------------------ saved views
    @http.route('/my/workspaces/<int:ws_id>/clients/views/save', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def view_save(self, ws_id, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'clients:read_own', 'clients')
        if denied:
            return denied
        query = urlencode(_clean_query(urlencode({k: post[k] for k in ('filter', 'group', 'sort', 'dir') if post.get(k)})))
        cols = [c for c in request.httprequest.form.getlist('col') if c in dict(COLUMNS)]
        name = (post.get('name') or '').strip()[:40]
        back = '/my/workspaces/%s/clients' % ws_id
        if not name:
            flash_error('برای نما یک نام بنویسید.')
            return request.redirect(back)
        SV = request.env['ts.saved.view'].sudo()
        try:
            v = SV.search([('member_id', '=', me.id), ('page', '=', 'clients'), ('name', '=', name)])
            vals = {'query': query, 'columns': ','.join(cols or [c for c, _ in COLUMNS]),
                    'is_default': bool(post.get('is_default'))}
            if v:
                v.write(vals)
            else:
                v = SV.create(dict(vals, member_id=me.id, page='clients', name=name))
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back)
        flash_ok('نما ذخیره شد.')
        return request.redirect('%s?view=%s' % (back, v.id))

    @http.route('/my/workspaces/<int:ws_id>/clients/views/<int:vid>/<string:action>', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def view_action(self, ws_id, vid, action, **post):
        me = member_or_404(ws_id)
        v = request.env['ts.saved.view'].sudo().search([('id', '=', vid), ('member_id', '=', me.id), ('member_id.workspace_id', '=', ws_id), ('page', '=', 'clients')])
        if not v or action not in ('delete', 'default'):
            raise request.not_found()
        if action == 'delete':
            v.unlink()
            flash_ok('نما حذف شد.')
        else:
            v.write({'is_default': not v.is_default})
            flash_ok('نمای پیش‌فرض ذخیره شد.' if v.is_default else 'نمای پیش‌فرض برداشته شد.')
        return request.redirect('/my/workspaces/%s/clients' % ws_id)

    # ------------------------------------------------------------------ bulk actions (work as a plain form post)
    @http.route('/my/workspaces/<int:ws_id>/clients/bulk', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def bulk(self, ws_id, **post):
        me = member_or_404(ws_id)
        action = post.get('bulk')
        back = '/my/workspaces/%s/clients' % ws_id
        if action not in BULK:
            flash_error('یک کار را برای افراد انتخاب‌شده برگزینید.')
            return request.redirect(back)
        denied = require(me, BULK[action], 'clients')
        if denied:
            return denied
        if not me.can_act():
            return forbidden(me, BULK[action], 'clients')
        C = request.env['ts.panel.client'].sudo()
        chosen = C.search([('id', 'in', _ids('sel')), ('workspace_id', '=', ws_id)]).filtered(lambda c: me.can_see(c))
        if not chosen:
            flash_error('هیچ شرکت‌کننده‌ای انتخاب نشده است.')
            return request.redirect(back)
        ok = 0
        try:
            if action == 'assign':
                rid = (post.get('target') or '').strip()
                target = request.env['ts.workspace.member'].sudo().search(
                    [('id', '=', int(rid) if rid.isdigit() else 0), ('workspace_id', '=', ws_id), ('active', '=', True)])
                if rid and not target:
                    raise request.not_found()
                for c in chosen:
                    try:
                        with request.env.cr.savepoint():
                            c.write({'responsible_id': target.id or False})
                        ok += 1
                    except (UserError, ValidationError):
                        pass
            elif action in ('group_add', 'group_remove'):
                g = request.env['ts.panel.group'].sudo().search(
                    [('id', '=', int(post['group']) if (post.get('group') or '').isdigit() else 0),
                     ('workspace_id', '=', ws_id), ('active', '=', True)])
                if not g:
                    flash_error('گروه را انتخاب کنید.')
                    return request.redirect(back)
                g.write({'client_ids': [((4 if action == 'group_add' else 3), c.id) for c in chosen]})
                ok = len(chosen)
            elif action in ('archive', 'restore'):
                todo = chosen.filtered(lambda c: (c.state == 'active') == (action == 'archive'))
                (todo.ts_archive(me) if action == 'archive' else todo.ts_restore(me))
                ok = len(todo)
            elif action == 'merge':
                if len(chosen) != 2:
                    flash_error('برای ادغام دقیقاً دو شرکت‌کننده را انتخاب کنید.')
                    return request.redirect(back)
                a, b = chosen.sorted('id')
                a.ts_merge_check(b, me)
                return render_in_shell('ts_panel.client_merge', me, 'clients', 'ادغام دو شرکت‌کننده', a=a, b=b,
                                       prev_a=a.ts_merge_preview(b), prev_b=b.ts_merge_preview(a))
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect(back)
        skipped = len(chosen) - ok
        flash_ok('%s مورد انجام شد%s.' % (_fa(ok), ('؛ %s مورد نادیده گرفته شد' % _fa(skipped)) if skipped else ''))
        return request.redirect(back)

    @http.route('/my/workspaces/<int:ws_id>/clients/merge', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def merge(self, ws_id, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'clients:merge', 'clients')
        if denied:
            return denied
        C = request.env['ts.panel.client'].sudo()
        keep = C.search([('id', '=', int(post['keep']) if (post.get('keep') or '').isdigit() else 0), ('workspace_id', '=', ws_id)])
        pair = [int(x) for x in (post.get('ids') or '').split(',') if x.strip().isdigit()]
        rest = [i for i in pair if i != keep.id]
        other = C.search([('id', '=', rest[0] if len(pair) == 2 and keep.id in pair and rest else 0),
                          ('workspace_id', '=', ws_id)])
        if not keep or not other:
            raise request.not_found()
        try:
            keep.ts_merge(other, me)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
            return request.redirect('/my/workspaces/%s/clients' % ws_id)
        flash_ok('دو شرکت‌کننده ادغام شد.')
        return request.redirect('/my/workspaces/%s/clients/%s' % (ws_id, keep.id))

    # ------------------------------------------------------------------ create / edit
    def _form(self, me, c, vals, errors=None, dups=None, status=None):
        ws = me.workspace_id
        can_assign = me.has_perm('clients:assign')
        cands = request.env['ts.workspace.member'].sudo().search(
            [('workspace_id', '=', ws.id), ('active', '=', True), ('role', 'in', list(RESPONSIBLE_ROLES))]
        ).filtered(lambda m: m.can_act()) if can_assign and not c else []
        # the creating member holds participants: preselect them instead of «بدون کارشناس» (G3-P4-5)
        default_resp = vals.get('responsible_id') or (me.id if me in cands else '')
        return render_in_shell('ts_panel.client_form', me, 'clients', ('ویرایش «%s»' % c.name) if c else 'شرکت‌کنندهٔ جدید',
                               status=status, c=c, vals=vals, errors=errors or {}, dups=dups or [], age=AGE,
                               relations=RELATIONS, can_assign=can_assign, cands=cands, role_labels=ROLE_LABELS,
                               locked=bool(c and c.contact_locked), default_resp=str(default_resp),
                               can_invite=me.can_invite() and me.has_perm('invites:create') and me.can_invite_participants())

    @staticmethod
    def _post_vals(post, locked=False):
        v = {'name': (post.get('name') or '').strip(), 'code': (post.get('code') or '').strip(),
             'age_group': post.get('age_group') if post.get('age_group') in dict(AGE) else 'unknown'}
        if not locked:
            v.update(phone=(post.get('phone') or '').strip(), email=(post.get('email') or '').strip(),
                     guardian_name=(post.get('guardian_name') or '').strip(),
                     guardian_phone=(post.get('guardian_phone') or '').strip(),
                     guardian_relation=post.get('guardian_relation') if post.get('guardian_relation') in dict(RELATIONS) else '')
        return v

    @staticmethod
    def _errors(me, vals, exclude=None):
        err = {}
        if not (2 <= len(vals['name']) <= 120):
            err['name'] = 'نام را بین ۲ تا ۱۲۰ نویسه بنویسید.'
        if vals.get('phone') and not norm_phone(vals['phone']):
            err['phone'] = 'شمارهٔ موبایل معتبر نیست. مثال: ۰۹۱۲۳۴۵۶۷۸۹'
        if vals.get('email') and not norm_email(vals['email']):
            err['email'] = 'ایمیل معتبر نیست.'
        if vals.get('guardian_phone') and not norm_phone(vals['guardian_phone']):
            err['guardian_phone'] = 'شمارهٔ موبایل ولی معتبر نیست.'
        if vals['code']:
            if len(vals['code']) > 40:
                err['code'] = 'شناسه حداکثر ۴۰ نویسه است.'
            elif request.env['ts.panel.client'].sudo().search_count(
                    [('workspace_id', '=', me.workspace_id.id), ('code', '=', vals['code'])] + ([('id', '!=', exclude)] if exclude else [])):
                err['code'] = 'این شناسه برای فرد دیگری در همین پنل ثبت شده است.'
        return err

    def _dups(self, me, vals, exclude=None):
        found = request.env['ts.panel.client'].ts_duplicates(
            me.workspace_id.id, vals.get('name'), vals.get('phone'), vals.get('email'), exclude)
        return found.filtered(lambda x: me.can_see(x))

    @http.route('/my/workspaces/<int:ws_id>/clients/new', type='http', auth='user', website=True,
                methods=['GET', 'POST'], sitemap=False)
    def client_new(self, ws_id, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'clients:write', 'clients')
        if denied:
            return denied
        if not me.can_act() or me.workspace_id.state != 'active':
            return forbidden(me, 'clients:write', 'clients')
        if request.httprequest.method == 'GET':
            return self._form(me, None, {'age_group': 'minor' if me.workspace_id.purpose == 'education' else 'unknown'})
        vals = self._post_vals(post)
        errors = self._errors(me, vals)
        dups = self._dups(me, vals) if not errors else []
        if errors or (dups and not post.get('confirm_dup')):
            return self._form(me, None, dict(vals, responsible_id=post.get('responsible_id') or ''), errors, dups,
                              status=400 if errors else None)
        C = request.env['ts.panel.client'].sudo()
        create = {k: (v or False) for k, v in vals.items()}
        create.update(workspace_id=ws_id, source='manual')
        resp = request.env['ts.workspace.member'].sudo().browse()   # ts-scope-ok: empty set
        rid = (post.get('responsible_id') or '').strip()
        if me.has_perm('clients:assign') and rid.isdigit():
            resp = request.env['ts.workspace.member'].sudo().search(
                [('id', '=', int(rid)), ('workspace_id', '=', ws_id), ('active', '=', True)])
        elif not me.has_perm('clients:assign'):
            resp = request.env['ts.workspace.member'].ts_panel_default_responsible(ws_id, me.user_id.id)
        create['responsible_id'] = resp.id or False
        try:
            c = C.create(create)
        except (UserError, ValidationError) as e:
            return self._form(me, None, vals, {'name': str(e.args[0] if e.args else e)}, status=400)
        request.env['ts.audit.event'].log('client.create', c, workspace=c.workspace_id, via='form')
        flash_ok('شرکت‌کننده ثبت شد.')
        if post.get('then') == 'invite':        # «ثبت و دعوت به سنجه»: straight to step 2 of the wizard (G3-P4-4)
            return request.redirect('/my/workspaces/%s/invites/new?fresh=1&client=%s' % (ws_id, c.id))
        return request.redirect('/my/workspaces/%s/clients/%s' % (ws_id, c.id))

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/edit', type='http', auth='user', website=True,
                methods=['GET', 'POST'], sitemap=False)
    def client_edit(self, ws_id, cid, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'clients:write', 'clients')
        if denied:
            return denied
        c = _client_or_404(me, cid)
        if not me.can_act() or not me.can_see(c):
            return forbidden(me, 'clients:write', 'clients')
        if request.httprequest.method == 'GET':
            vals = {k: (c[k] or '') for k in ('name', 'code', 'phone', 'email', 'age_group', 'guardian_name',
                                                'guardian_phone', 'guardian_relation')}
            return self._form(me, c, vals)
        vals = self._post_vals(post, locked=c.contact_locked)
        errors = self._errors(me, vals, exclude=c.id)
        dups = self._dups(me, vals, exclude=c.id) if not errors else []
        if errors or (dups and not post.get('confirm_dup')):
            return self._form(me, c, vals, errors, dups, status=400 if errors else None)
        try:
            c.write({k: (v or False) for k, v in vals.items()})
        except (UserError, ValidationError) as e:
            return self._form(me, c, vals, {'name': str(e.args[0] if e.args else e)}, status=400)
        request.env['ts.audit.event'].log('client.edit', c, workspace=c.workspace_id, fields=sorted(vals))
        flash_ok('تغییرها ذخیره شد.')
        return request.redirect('/my/workspaces/%s/clients/%s' % (ws_id, c.id))

    # ------------------------------------------------------------------ one client
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
        Mem = request.env['ts.workspace.member'].sudo()
        eligible = Mem.search([('workspace_id', '=', me.workspace_id.id), ('active', '=', True),
                               ('role', 'in', list(RESPONSIBLE_ROLES))]).filtered(
            lambda m: m.can_act() and m.user_id != c.user_id)
        cands = eligible if can_assign else []
        colleagues = eligible.filtered(lambda m: m != me) if c.responsible_id == me and not can_assign else []
        assignments = c.assignment_ids.sorted(lambda a: (a.create_date, a.id), reverse=True)
        imports = c.attempt_ids.filtered(lambda t: t.source == 'import').sorted(lambda t: (t.create_date, t.id), reverse=True)
        can_groups = me.has_perm('groups:manage')
        all_groups = request.env['ts.panel.group'].sudo().search(
            [('workspace_id', '=', me.workspace_id.id), ('active', '=', True)]) if can_groups else []
        can_invite = (me.can_invite() and me.has_perm('invites:create') and me.can_invite_participants()
                      and c.state == 'active' and not c.contact_locked)
        return render_in_shell(
            'ts_panel.client', me, 'clients', c.name, c=c, assignments=assignments, imports=imports,
            can_assign=can_assign, cands=cands, colleagues=colleagues, state_labels=STATE_LABELS,
            source_label=SOURCE_LABELS.get(c.source, c.source), role_labels=ROLE_LABELS,
            can_write=me.has_perm('clients:write'), can_archive=me.has_perm('clients:archive'),
            can_groups=can_groups, all_groups=all_groups, is_resp=c.responsible_id == me, can_invite=can_invite,
            can_manage_inv=me.has_perm('invites:manage'),
            age_labels=dict(AGE), level=lambda a: a.result_level(me), level_t=lambda t: t.ts_result_level(me))

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
        target = request.env['ts.workspace.member'].sudo().search([('id', '=', 0)])   # ts-scope-ok: empty set
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

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/<string:action>', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def client_action(self, ws_id, cid, action, **post):
        me = member_or_404(ws_id)
        perm = {'archive': 'clients:archive', 'restore': 'clients:archive', 'groups': 'groups:manage'}.get(action)
        if action in ('handover', 'decide'):
            perm = 'clients:be_responsible' if action == 'handover' else 'clients:assign'
        if not perm:
            raise request.not_found()
        denied = require(me, perm, 'clients')
        if denied:
            return denied
        c = _client_or_404(me, cid)
        back = '/my/workspaces/%s/clients/%s' % (ws_id, cid)
        if not me.can_act() or not me.can_see(c):
            return forbidden(me, perm, 'clients')
        try:
            if action == 'archive':
                if not post.get('confirm'):
                    raise UserError('برای بایگانی، تأیید را تیک بزنید.')
                c.ts_archive(me)
                flash_ok('شرکت‌کننده بایگانی شد؛ از فهرست پیش‌فرض بیرون رفت و دعوت تازه نمی‌گیرد. از پالایش «بایگانی‌شده» برمی‌گردد.')
            elif action == 'restore':
                c.ts_restore(me)
                flash_ok('شرکت‌کننده بازیابی شد.')
            elif action == 'groups':
                g = request.env['ts.panel.group'].sudo().search(
                    [('id', '=', int(post.get('group')) if (post.get('group') or '').isdigit() else 0),
                     ('workspace_id', '=', ws_id), ('active', '=', True)])
                if not g:
                    raise request.not_found()
                g.write({'client_ids': [(3 if post.get('remove') else 4, c.id)]})
                flash_ok('گروه‌ها به‌روز شد.')
            elif action == 'handover':
                tid = (post.get('target') or '')
                target = request.env['ts.workspace.member'].sudo().search(
                    [('id', '=', int(tid) if tid.isdigit() else 0), ('workspace_id', '=', ws_id)])
                res = c.ts_request_handover(me, target)
                flash_ok('کارشناس مسئول عوض شد.' if res == 'done' else 'درخواست سپردن ثبت شد؛ پس از تأیید مالک یا هماهنگ‌کننده اعمال می‌شود.')
            elif action == 'decide':
                c.ts_decide_handover(me, accept=post.get('accept') == '1')
                flash_ok('تصمیم ثبت شد.')
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        return request.redirect(back)


def _fa(n):
    from odoo.addons.ts_assessment.models.attempt import fa_digits
    return fa_digits(n)
