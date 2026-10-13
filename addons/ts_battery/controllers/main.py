"""Battery run, website side (docs/clinic/01_architecture.md section 3; clinic phase 3).

Player: one consent page (the first attempt), siblings never show their own; after each instrument a short transition
page, after the last one the battery result page. Lists (/my, /my/assessments, panel participant page) show a battery
as one row. Panel: the member page lets owner/admin/director choose each member's instruments and batteries
(catalog:assign); the invitation wizard and group invitations offer «یک مجموعه». Every access decision is the
existing one (`result_level()`, `member.can_see`, `allowed_batteries()`); these controllers only read with sudo after it.
"""
import re

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _my_attempt, _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits, jalali_long
from odoo.addons.ts_org.controllers.main import TsOrg
from odoo.addons.ts_panel.controllers.base import (deny, flash_error, flash_ok, forbidden, member_or_404,
                                                   render_in_shell, require)
from odoo.addons.ts_panel.controllers.campaigns import TsPanelCampaigns
from odoo.addons.ts_panel.controllers.clients import _client_or_404
from odoo.addons.ts_panel.controllers.invites import TsPanelInvites
from odoo.addons.ts_panel.controllers.members import TsPanelMembers, _other_member
from odoo.addons.ts_panel.controllers.portal import TsPanelPortal
from odoo.addons.ts_panel.controllers.reports import LEVEL_KIND
from odoo.addons.ts_talent.controllers.main import TsTalent

from ..models.battery import rest_minutes_text
from ..models.catalog import BATTERY_NOT_IN_CATALOG

LIMIT_NOTE = 'این مجموعه برای کمک به گفت‌وگوی مشاوره است، نه تشخیص.'


def battery_url(a):
    return '/my/assessments/battery/%s' % a.id


def panel_battery_url(ws_id, client_id, aid):
    return '/my/workspaces/%s/clients/%s/b/%s' % (ws_id, client_id, aid)


def after_url(attempt, submitted=False):
    """Where a finished battery attempt goes: the transition page while another instrument is open, else the
    battery result page."""
    a = attempt.sudo().assignment_id
    if attempt.ts_battery_next():
        return '/take/%s/next' % attempt.access_token
    return battery_url(a) + ('?submitted=1' if submitted else '')


def _sections(attempts, level_of):
    """One section per attempt of a battery: [{at, inst, level, results, matrix, sec_id}] (results only at a level that
    shows them)."""
    out = []
    for t in attempts:
        lvl = level_of(t)
        matrix = bool(t.ts_is_matrix()) if hasattr(t, 'ts_is_matrix') else False
        show = lvl not in ('none', 'status') and t.state == 'done' and t.released and not matrix
        out.append({'at': t, 'inst': t.instrument_id, 'level': lvl, 'matrix': matrix,
                    'results': t.result_rows() if show else t.env['ts.attempt.result'],
                    'sec_id': 'tsb-sec-%s' % t.id})
    return out


# ====================================================================== player
class TsBatteryPlayer(TsTalent):

    @http.route()
    def take(self, token, page=None, **kw):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if attempt.ts_battery():
            first = attempt.ts_battery_first()
            if attempt.state == 'consent' and first and first != attempt:
                if first.state == 'consent':
                    return request.redirect('/take/%s' % first.access_token)     # one consent page per battery
                attempt.ts_battery_copy_consent()
            if attempt.state == 'done':
                return request.redirect(after_url(attempt))
            if attempt.state == 'in_progress':
                earlier = attempt.ts_battery_earlier_open()
                if earlier:
                    return request.redirect('/take/%s' % earlier.access_token)   # instruments in battery order
        return super().take(token, page=page, **kw)

    @http.route()
    def submit(self, token, **post):
        res = super().submit(token, **post)
        attempt = _my_attempt(token)
        if attempt.ts_battery() and attempt.state == 'done':
            return request.redirect(after_url(attempt, submitted=True))
        return res

    @http.route()
    def finish(self, token, **post):
        res = super().finish(token, **post)
        attempt = _my_attempt(token)
        if attempt.ts_battery() and attempt.state == 'done':
            return request.redirect(after_url(attempt, submitted=True))
        return res

    @http.route('/take/<string:token>/next', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def battery_next(self, token, **kw):
        """«سنجهٔ ۲ از ۵ تمام شد»: the next instrument, its size, continue now or later."""
        _ts_site_or_404()
        attempt = _my_attempt(token)
        b = attempt.ts_battery()
        if not b or attempt.state != 'done':
            return request.redirect('/take/%s' % token)
        nxt = attempt.ts_battery_next()
        if not nxt:
            return request.redirect(battery_url(attempt.sudo().assignment_id))
        sib = attempt.ts_battery_siblings()
        inst = nxt.instrument_id
        matrix = bool(nxt.ts_is_matrix()) if hasattr(nxt, 'ts_is_matrix') else False
        # what is left of the whole battery (G6-P14-2); item counts only when no talent inventory (fields, not items) is left
        rest = sib.filtered(lambda t: t.state != 'done')
        rest_matrix = any(hasattr(t, 'ts_is_matrix') and t.ts_is_matrix() for t in rest)
        rest_items = 0 if rest_matrix else sum(rest.mapped('instrument_id.active_item_count'))
        # minutes = the sum the per-instrument labels show (verify T7), the same number as /my and the player
        return request.render('ts_battery.transition', {
            'attempt': attempt, 'battery': b, 'n_done': attempt.ts_battery_index(), 'total': len(sib),
            'done_count': len(sib.filtered(lambda t: t.state == 'done')), 'nxt': nxt, 'inst': inst, 'matrix': matrix,
            'items': inst.active_item_count or 0, 'minutes': inst.duration_minutes or 0,
            'rest_count': len(rest), 'rest_items': rest_items, 'rest_minutes': rest_minutes_text(rest),
            'tu': attempt.ts_informal(), 'fa': fa_digits, 'page_name': 'ts_assessments'})

    # ------------------------------------------------------------------ /my/assessments: a battery is one row
    @http.route()
    def my_list(self, **kw):
        res = super().my_list(**kw)
        qc = getattr(res, 'qcontext', None)
        if qc is None:
            return res
        qc.setdefault('batteries_going', [])
        qc.setdefault('batteries_done', [])
        bat_att = qc['attempts'].filtered(lambda t: t.sudo().assignment_id.battery_id)
        if not bat_att:
            return res
        qc['going'] = qc['going'] - bat_att
        groups = []
        for g in qc['groups']:
            rows = [r for r in g['rows'] if r not in bat_att]
            if rows:
                groups.append(dict(g, rows=rows))
        qc['groups'] = groups
        seen = []
        for t in bat_att.sorted(lambda t: -t.id):
            a = t.sudo().assignment_id
            if a in seen:
                continue
            seen.append(a)
            done, total = a.ts_battery_progress()
            nxt = a.ts_battery_attempts().filtered(lambda x: x.state != 'done')[:1]
            row = {'a': a, 'name': a.battery_id.ts_title(), 'org': a.workspace_id.ts_public_name(),
                   'done': done, 'total': total, 'when': jalali_long(a.accepted_at or a.create_date)}
            if nxt:
                rest = a.ts_battery_attempts().filtered(lambda x: x.state != 'done')
                # T7 (B26-1): which instrument is next and about how long the rest takes
                row.update(url='/take/%s' % nxt.access_token, fresh=nxt.state == 'consent',
                           next_name=nxt.instrument_id.ts_title(),
                           minutes_left=rest_minutes_text(rest))   # same sum as the player and the invite (verify T7)
                qc['batteries_going'].append(row)
            else:
                row.update(url=battery_url(a), shared=a.share_level != 'none', when=jalali_long(
                    max([d for d in a.ts_battery_attempts().mapped('submitted_at') if d] or [a.create_date])))
                qc['batteries_done'].append(row)
        return res

    # ------------------------------------------------------------------ battery result page (participant)
    @http.route('/my/assessments/battery/<int:assignment_id>', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def my_battery(self, assignment_id, **kw):
        _ts_site_or_404()
        a = request.env['ts.assignment'].sudo().search([
            ('id', '=', int(assignment_id)), ('user_id', '=', request.env.user.id), ('battery_id', '!=', False)], limit=1)
        if not a:
            raise request.not_found()
        rows = a.ts_battery_attempts()
        if not rows.filtered(lambda t: t.state == 'done'):
            nxt = rows.filtered(lambda t: t.state != 'done')[:1]
            if nxt:
                return request.redirect('/take/%s' % nxt.access_token)
            raise request.not_found()
        request.env['ts.audit.event'].sudo().log('report.view', a, workspace=a.workspace_id, battery=a.battery_id.code)
        done, total = a.ts_battery_progress()
        sections = _sections(rows, lambda t: 'self' if (t.state == 'done' and t.released) else 'status')
        resp = a.responsible_id.sudo().user_id.name if a.responsible_id else ''
        return request.render('ts_battery.my_battery', {
            'a': a, 'battery': a.battery_id, 'sections': sections, 'done': done, 'total': total,
            'org': a.workspace_id.ts_public_name(), 'counselor': resp,
            'when': jalali_long(max(rows.filtered(lambda t: t.submitted_at).mapped('submitted_at') or [a.create_date])),   # «۲۱ مهر ۱۴۰۵» (PT7)
            'submitted': kw.get('submitted'), 'limit_note': LIMIT_NOTE, 'tu': rows[:1].ts_informal(),
            'nxt': rows.filtered(lambda t: t.state != 'done')[:1],     # T7 B24-1: «ادامهٔ مجموعه» near the top
            'fa': fa_digits, 'page_name': 'ts_assessments'})


# ====================================================================== invitation link, old panel route
class TsBatteryOrg(TsOrg):

    @http.route()
    def invite_page(self, token, **kw):
        _ts_site_or_404()
        a = request.env['ts.assignment'].sudo().search([('token', '=', token)], limit=1)   # the secret token is the key
        user = request.env.user
        if a and a.battery_id and a.user_id == user and a.state == 'done':
            return request.redirect(battery_url(a))
        return super().invite_page(token, **kw)

    @http.route()
    def unshare(self, attempt_id, **post):
        """The report of one battery instrument stops sharing the whole battery invitation (one share per battery)."""
        _ts_site_or_404()
        at = request.env['ts.attempt'].sudo().search([('id', '=', int(attempt_id)), ('user_id', '=', request.env.user.id)], limit=1)
        a = at.assignment_id
        if a.battery_id and a.user_id == request.env.user:
            a.action_revoke_share(request.env.user)
            return request.redirect(battery_url(a))
        return super().unshare(attempt_id, **post)

    @http.route()
    def assignment(self, ws_id, assignment_id, **kw):
        me = member_or_404(ws_id)
        a = request.env['ts.assignment'].sudo().search([('id', '=', int(assignment_id)),
                                                         ('workspace_id', '=', me.workspace_id.id)], limit=1)
        if a and a.battery_id and a.client_id and a.state == 'done' and me.can_see(a):
            return request.redirect(panel_battery_url(me.workspace_id.id, a.client_id.id, a.id))
        return super().assignment(ws_id, assignment_id, **kw)


# ====================================================================== /my home: a battery is one item
class TsBatteryPortal(TsPanelPortal):

    @http.route()
    def home(self, **kw):
        res = super().home(**kw)
        qc = getattr(res, 'qcontext', None)
        if qc is None or 'going' not in qc:
            return res
        qc.setdefault('done_batteries', [])
        done_rows = qc.get('done') or request.env['ts.attempt'].sudo().browse()
        first_done = done_rows[:1]
        nxt = qc.get('next_action')
        if nxt and nxt.get('kind') == 'invite':
            inv = qc['invites'][:1]
            if inv and inv.battery_id:
                nxt['title'] = 'مجموعهٔ %s' % inv.battery_id.name
        elif nxt and nxt.get('kind') == 'resume':
            t = request.env['ts.attempt'].sudo().browse(nxt['attempt_id'])
            a = t.assignment_id
            if a.battery_id:
                done, total = a.ts_battery_progress()
                cur = t.ts_battery_next() or t
                pct = int(round(100.0 * done / total)) if total else 0
                if not pct and cur.state == 'in_progress' and cur.answered_count:
                    pct = 1
                # the headline is the battery name only; the progress is part of the meta line (G6-P16-1).
                # T7 (B25-1/2): «ادامهٔ مجموعه» once anything is answered; next instrument with its place, time left.
                rest = a.ts_battery_attempts().filtered(lambda x: x.state != 'done')
                rest_min = rest_minutes_text(rest)   # same sum as the player and the invite (verify T7)
                nxt.update(title='مجموعهٔ %s' % a.battery_id.name,
                           battery_progress='%s از %s سنجه انجام شده' % (fa_digits(done), fa_digits(total)),
                           url='/take/%s' % cur.access_token, progress=pct, attempt_id=cur.id, battery=True,
                           battery_next=cur.instrument_id.ts_title(),
                           battery_place='%s از %s' % (fa_digits(cur.ts_battery_index()), fa_digits(total)),
                           battery_minutes_left=rest_min, when=cur.jalali_long(cur.write_date),
                           label='ادامهٔ مجموعه' if pct else 'شروع مجموعه')
                qc['going'] = qc['going'].filtered(lambda x: x.sudo().assignment_id != a)
        elif nxt and nxt.get('kind') == 'result' and first_done:
            a = first_done.sudo().assignment_id
            if a.battery_id and a.state == 'done':
                nxt.update(title='مجموعهٔ %s' % a.battery_id.name, url=battery_url(a))
        # the other unfinished items: one row per battery (its current instrument)
        going, seen = qc['going'].browse(), set()
        for t in qc['going']:
            a = t.sudo().assignment_id
            if a.battery_id:
                if a.id in seen:
                    continue
                seen.add(a.id)
                t = t.ts_battery_next() or t
            going |= t
        qc['going'] = going
        bats = done_rows.filtered(lambda t: t.sudo().assignment_id.battery_id)
        if bats:
            qc['done'] = done_rows - bats
            for a in bats.sudo().mapped('assignment_id'):
                d, n = a.ts_battery_progress()
                if d == n:
                    qc['done_batteries'].append({
                        'a': a, 'name': a.battery_id.name, 'url': battery_url(a), 'shared': a.share_level != 'none',
                        'when': jalali_long(max(a.attempt_ids.mapped('submitted_at') or [a.create_date]))})
        return res


# ====================================================================== panel: a member's catalog (catalog:assign)
def _names_line(names, shown=3):
    """«فقط «الف»، «ب»، «ج» و ۲ مورد دیگر»; '' for no names."""
    if not names:
        return ''
    line = 'فقط ' + '، '.join('«%s»' % n for n in names[:shown])
    if len(names) > shown:
        line += ' و %s مورد دیگر' % fa_digits(len(names) - shown)
    return line


class TsBatteryMembers(TsPanelMembers):

    @http.route()
    def member_page(self, ws_id, mid, **kw):
        res = super().member_page(ws_id, mid, **kw)
        qc = getattr(res, 'qcontext', None)
        if qc is None or 'm' not in qc:
            return res
        me, m = qc['member'], qc['m']
        can = me.has_perm('catalog:assign') and me.can_act()
        qc['can_catalog'] = can
        if can:
            ws = me.workspace_id
            restricted = bool(m.catalog_restricted or m.restrict_instrument_ids or m.restrict_battery_ids)
            bats = m.allowed_batteries() if restricted else request.env['ts.battery'].browse()
            insts = m.allowed_instruments() if restricted else request.env['ts.instrument'].browse()
            qc.update(panel_insts=ws.ts_catalog_instruments(), panel_bats=ws.ts_catalog_batteries(),
                      cat_restricted=restricted, cat_insts=set(insts.ids), cat_bats=set(bats.ids),
                      # «اکنون: فقط «X»، «Y» و ۲ مورد دیگر» (G6-P1-3): batteries first, then single instruments
                      cat_now=_names_line([b.ts_title() for b in bats.sudo()] + [i.ts_title() for i in insts.sudo()]))
        return res

    @http.route('/my/workspaces/<int:ws_id>/members/<int:mid>/catalog', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def member_catalog(self, ws_id, mid, **post):
        me = member_or_404(ws_id)
        denied = require(me, 'catalog:assign', 'members')
        if denied:
            return denied
        if not me.can_act():
            return forbidden(me, 'catalog:assign', 'members')
        m = _other_member(me, mid)
        form = request.httprequest.form
        restricted = post.get('catalog_mode') == 'list'
        inst_ids = [int(x) for x in form.getlist('instrument_ids') if x.isdigit()]
        bat_ids = [int(x) for x in form.getlist('battery_ids') if x.isdigit()]
        try:
            changed = m.ts_set_catalog(me, restricted, inst_ids, bat_ids)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok(('موارد مجاز ذخیره شد.' if restricted else 'این عضو از همهٔ موارد پنل استفاده می‌کند.')
                     if changed else 'تغییری نبود.')
        return request.redirect('/my/workspaces/%s/members/%s#tsp-catalog' % (ws_id, m.id))


# ====================================================================== panel: invite a battery
def _read_battery(me, post, d):
    """Shared by the wizard and group invitations: item_kind=battery + battery_id. Returns an error text or None."""
    bid = post.get('battery_id') or ''
    bats = me.allowed_batteries()
    if not bid.isdigit() or int(bid) not in bats.ids:
        return BATTERY_NOT_IN_CATALOG
    b = bats.filtered(lambda x: x.id == int(bid))
    d['battery_id'] = b.id
    d['instrument_id'] = b.ts_first_instrument().id
    return None


def _wants_battery(post):
    return post.get('item_kind') == 'battery' or (bool(post.get('battery_id')) and not post.get('instrument_id'))


def _catalog_note(me):
    """A member whose catalog was narrowed by the panel learns why the list is short (G6-P5-1); '' otherwise."""
    if not (me.catalog_restricted or me.restrict_instrument_ids or me.restrict_battery_ids):
        return ''
    who = 'مدیر مرکز' if me.workspace_id.purpose == 'clinical' else 'مالک یا هماهنگ‌کنندهٔ پنل'
    return '%s این موارد را برای شما فعال کرده است؛ برای مورد دیگر با او هماهنگ کنید.' % who


def _picker_ctx(me, d):
    # listed by the name people see (G7-PAT-2)
    bats = me.allowed_batteries().sorted(lambda b: b.ts_title().replace('\u200c', ' '))
    bat = bats.filtered(lambda b: b.id == d.get('battery_id'))[:1] if d.get('battery_id') else bats.browse()
    # a member without single instruments (catalog restricted to batteries) gets the battery choice directly
    only_bats = bool(bats) and not me.allowed_instruments()
    return {'batteries': bats, 'bat': bat, 'bat_cards': {b.id: b.ts_card() for b in bats},
            'item_kind': 'battery' if (bat or only_bats) else 'single', 'cat_note': _catalog_note(me)}


class TsBatteryInvites(TsPanelInvites):

    def _read_item(self, me, post, d):
        if _wants_battery(post):
            return _read_battery(me, post, d)
        d.pop('battery_id', None)
        return super()._read_item(me, post, d)

    def _item_allowed(self, me, d):
        if d.get('battery_id'):
            return d['battery_id'] in me.allowed_batteries().ids
        return super()._item_allowed(me, d)

    def _item_vals(self, me, d):
        vals = super()._item_vals(me, d)
        if d.get('battery_id'):
            vals['battery_id'] = d['battery_id']
        return vals

    def _wizard_ctx(self, me, ws_id, step, **extra):
        vals = super()._wizard_ctx(me, ws_id, step, **extra)
        vals.update(_picker_ctx(me, vals.get('draft') or {}))
        if vals['batteries']:
            vals['steps'] = [(k, 'کدام سنجه یا مجموعه' if k == '2' else label) for k, label in vals['steps']]
        return vals

    @http.route()
    def invites(self, ws_id, **kw):
        res = super().invites(ws_id, **kw)
        qc = getattr(res, 'qcontext', None)
        if qc and qc.get('rows') is not None and isinstance(qc.get('results'), dict):
            me = qc['member']
            for a in qc['rows'].filtered(lambda r: r.battery_id and r.client_id and r.state == 'done'):
                if a.result_level(me) != 'none':
                    qc['results'][a.id] = panel_battery_url(ws_id, a.client_id.id, a.id)
        return res

    @http.route()
    def unseen(self, ws_id, **kw):
        """One waiting result of a battery opens the battery page, not its first instrument."""
        res = super().unseen(ws_id, **kw)
        loc = res.headers.get('Location', '') if hasattr(res, 'headers') else ''
        m = re.search(r'/clients/(\d+)/r/(\d+)$', loc)
        if m:
            a = request.env['ts.attempt'].sudo().search([('id', '=', int(m.group(2))), ('workspace_id', '=', int(ws_id))],
                                                         limit=1).assignment_id
            if a.battery_id:
                return request.redirect(panel_battery_url(ws_id, m.group(1), a.id))
        return res

    @http.route()
    def invite(self, ws_id, aid, **kw):
        """A battery invitation shows its result button only when at least one instrument is done; a partly done
        battery says which part (G6-P8-1). Who may open it is unchanged (the base sets `result` only when allowed)."""
        res = super().invite(ws_id, aid, **kw)
        qc = getattr(res, 'qcontext', None)
        if qc is None:
            return res
        qc.setdefault('result_label', None)
        qc.setdefault('result_partial', False)
        if qc.get('a') and qc['a'].battery_id and qc.get('result'):
            a = qc['a']
            done, total = a.ts_battery_progress()
            if not done:
                qc['result'] = None
            else:
                qc['result'] = panel_battery_url(ws_id, a.client_id.id, a.id)
                if done < total:
                    qc['result_partial'] = True
                    qc['result_label'] = 'دیدن نتیجهٔ بخش انجام‌شده (%s از %s)' % (fa_digits(done), fa_digits(total))
        return res


class TsBatteryCampaigns(TsPanelCampaigns):

    def _read_item(self, me, post, d):
        if _wants_battery(post):
            return _read_battery(me, post, d)
        d.pop('battery_id', None)
        return super()._read_item(me, post, d)

    def _item_allowed(self, me, d):
        if d.get('battery_id'):
            return d['battery_id'] in me.allowed_batteries().ids
        return super()._item_allowed(me, d)

    def _item_vals(self, me, d):
        vals = super()._item_vals(me, d)
        if d.get('battery_id'):
            vals['battery_id'] = d['battery_id']
        return vals

    def _form_ctx(self, me, d, **extra):
        vals = super()._form_ctx(me, d, **extra)
        vals.update(_picker_ctx(me, d or {}))
        return vals

    @http.route()
    def new(self, ws_id, **post):
        res = super().new(ws_id, **post)
        qc = getattr(res, 'qcontext', None)
        if qc is not None and 'draft' in qc and 'bat' not in qc:
            d = qc.get('draft') or {}
            qc['bat'] = request.env['ts.battery'].sudo().browse(d.get('battery_id') or []).exists()
        return res


# ====================================================================== panel: battery result page
class TsBatteryPanelReport(http.Controller):

    def _context(self, ws_id, cid, aid):
        me = member_or_404(ws_id)
        client = _client_or_404(me, cid)
        a = request.env['ts.assignment'].sudo().search([
            ('id', '=', int(aid)), ('workspace_id', '=', me.workspace_id.id), ('client_id', '=', client.id),
            ('battery_id', '!=', False)], limit=1)
        if not a or not me.can_act() or not me.can_see(client):
            deny(me, 'no_result', assignment=int(aid))
            raise request.not_found()
        level = a.result_level(me)
        if level == 'none':
            deny(me, 'result_level_none', assignment=a.id)
            raise request.not_found()
        return me, client, a, level

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/b/<int:aid>', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def battery(self, ws_id, cid, aid, print=None, **kw):
        me, client, a, level = self._context(ws_id, cid, aid)
        request.env['ts.audit.event'].sudo().log('result.view', a, workspace=me.workspace_id, member=me, level=level,
                                                 battery=a.battery_id.code)
        url = panel_battery_url(me.workspace_id.id, client.id, a.id)
        rows = a.ts_battery_attempts()
        done, total = a.ts_battery_progress()
        sections = _sections(rows, lambda t: level if (t.state == 'done' and t.released) else 'status')
        resp = a.responsible_id.sudo().user_id.name if a.responsible_id else ''
        back = '/my/workspaces/%s/clients/%s' % (me.workspace_id.id, client.id)
        return render_in_shell(
            'ts_battery.panel_battery', me, 'clients', 'مجموعهٔ %s' % a.battery_id.name, a=a, client=client,
            battery=a.battery_id, level=level, kind=LEVEL_KIND.get(level, ''), sections=sections, done=done, total=total,
            counselor=resp, org=me.workspace_id.partner_id.name or me.workspace_id.name, limit_note=LIMIT_NOTE,
            result_url=lambda t: '/my/workspaces/%s/clients/%s/r/%s' % (me.workspace_id.id, client.id, t.id),
            print_url=url + '/print', autoprint=bool(print), back_url=back, back_label=client.name or 'شرکت‌کننده',
            when=max(rows.filtered(lambda t: t.submitted_at).mapped('submitted_at') or [a.create_date]))

    @http.route('/my/workspaces/<int:ws_id>/clients/<int:cid>/b/<int:aid>/print', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def battery_print(self, ws_id, cid, aid, **kw):
        me, client, a, level = self._context(ws_id, cid, aid)
        request.env['ts.audit.event'].sudo().log('result.print', a, workspace=me.workspace_id, member=me, level=level,
                                                 battery=a.battery_id.code)
        return request.redirect(panel_battery_url(me.workspace_id.id, client.id, a.id) + '?print=1')
