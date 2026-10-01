"""Dashboard definitions (S12: DSH-1..DSH-5; 03_ia_and_ux.md section 5).

One method per block, each returning counts and the list URL that shows exactly the same records: the invitation list and
the client list build their domains from the same helpers (`invite_filters`, the `handover` / `mine_open` client filters),
so a tile and its list cannot disagree. Only counts and states are shown, never a score or a band (DSH-5).
"""
from datetime import datetime, time, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from odoo import fields, models

TEHRAN, UTC = ZoneInfo('Asia/Tehran'), ZoneInfo('UTC')
OPEN_STATES = ('invited', 'opened', 'accepted', 'in_progress')
PERIODS = (7, 30, 90)
MIN_N = 5                       # a rate or a median below this many records is not shown
VIEW_EVENTS = ('assignment.result_view', 'attempt.result_view', 'result.view')
KINDS = ('sent', 'accepted', 'done', 'noshare', 'created', 'active')


def today_tehran():
    return datetime.now(TEHRAN).date()


def period_start(days):
    """Start of the Tehran day `days - 1` days ago, as a naive UTC datetime."""
    d = today_tehran() - timedelta(days=days - 1)
    return datetime.combine(d, time.min, TEHRAN).astimezone(UTC).replace(tzinfo=None)


def kind_domain(kind, days):
    start = period_start(days)
    if kind == 'sent':
        return [('create_date', '>=', start), ('channel', '!=', 'self_share')]
    if kind == 'accepted':
        return [('accepted_at', '>=', start)]
    if kind == 'done':
        return [('state', '=', 'done'), ('attempt_id.submitted_at', '>=', start)]
    if kind == 'noshare':
        return [('state', '=', 'done'), ('attempt_id.submitted_at', '>=', start), ('share_level', '=', 'none')]
    if kind == 'created':
        return [('create_date', '>=', start)]
    if kind == 'active':                       # created in the period and not withdrawn: the base of the completion rate
        return [('create_date', '>=', start), ('state', '!=', 'withdrawn')]
    return []


def overdue_domain():
    return [('state', 'in', list(OPEN_STATES)), ('deadline', '<', today_tehran())]


def expiring_domain(days=3):
    now = fields.Datetime.now()
    return [('state', 'in', list(OPEN_STATES)), ('expires_at', '>=', now), ('expires_at', '<=', now + timedelta(days=days))]


def unseen_ids(env, me, base):
    """Done invitations whose result this member may open and has not opened yet (no result_view audit row of theirs)."""
    A = env['ts.assignment'].sudo()
    done = A.search(base + [('state', '=', 'done')])
    cand = done.filtered(lambda a: a.result_level(me) in ('summary', 'education', 'clinical'))
    if not cand:
        return []
    Audit = env['ts.audit.event'].sudo()
    rows = Audit.search([('actor_id', '=', me.user_id.id), ('event_type', 'in', list(VIEW_EVENTS)),
                         '|', '&', ('res_model', '=', 'ts.assignment'), ('res_id', 'in', cand.ids),
                         '&', ('res_model', '=', 'ts.attempt'), ('res_id', 'in', cand.attempt_id.ids)])
    seen_a = {r.res_id for r in rows if r.res_model == 'ts.assignment'}
    seen_t = {r.res_id for r in rows if r.res_model == 'ts.attempt'}
    return [a.id for a in cand if a.id not in seen_a and a.attempt_id.id not in seen_t]


def clean_filters(kw):
    """The invitation-list filter parameters that survive, as a dict (whitelisted values only)."""
    out = {}
    for k in ('overdue', 'expiring', 'unseen'):
        if kw.get(k) == '1':
            out[k] = '1'
    if kw.get('kind') in KINDS:
        out['kind'] = kw['kind']
    if (kw.get('period') or '').isdigit() and int(kw['period']) in PERIODS:
        out['period'] = kw['period']
    return out


def invite_filters(env, me, base, kw):
    """-> (extra domain, clean parameter dict) for the invitation list."""
    f = clean_filters(kw)
    dom = []
    if f.get('overdue'):
        dom += overdue_domain()
    if f.get('expiring'):
        dom += expiring_domain()
    if f.get('unseen'):
        dom.append(('id', 'in', unseen_ids(env, me, base)))
    if f.get('kind'):
        dom += kind_domain(f['kind'], int(f.get('period') or 30))
    return dom, f


class TsWorkspaceDashboard(models.Model):
    _inherit = 'ts.workspace'

    onboarding_dismissed_on = fields.Datetime(readonly=True, copy=False)


class TsMemberDashboard(models.Model):
    _inherit = 'ts.workspace.member'

    # ------------------------------------------------------------------ 5.1 needs attention
    def dash_attention(self):
        self.ensure_one()
        from odoo.addons.ts_org.models.panel import TERMS_VERSION
        from ..controllers.clients import visible_domain
        from ..controllers.invites import assignment_domain
        env, ws = self.env, self.workspace_id
        base = '/my/workspaces/%d' % ws.id
        A, C = env['ts.assignment'].sudo(), env['ts.panel.client'].sudo()
        out = []

        def add(key, label, n, url):
            if n:
                out.append({'key': key, 'label': label, 'n': n, 'url': url})

        add('gated', 'پنل در انتظار تأیید تیم تلنت سرچ است', 1 if ws.gated else 0, '/help')
        add('verify', 'احراز صلاحیت حرفه‌ای شما در حال بررسی است', 1 if self._ts_unverified_pro() else 0, '/help')
        if self.can_act() and self.has_perm('invites:manage'):
            dom = assignment_domain(self)
            add('unseen', 'نتیجهٔ آماده که هنوز باز نکرده‌اید', len(unseen_ids(env, self, dom)), base + '/invites?unseen=1')
            add('overdue', 'دعوت‌های گذشته از مهلت', A.search_count(dom + overdue_domain()), base + '/invites?overdue=1')
            add('expiring', 'دعوت‌هایی که تا ۳ روز دیگر منقضی می‌شوند', A.search_count(dom + expiring_domain()), base + '/invites?expiring=1')
        if self.has_perm('clients:assign') or self.has_perm('clients:read_unassigned'):
            add('unassigned', 'شرکت‌کنندگان بدون کارشناس مسئول',
                C.search_count(visible_domain(self) + [('state', '=', 'active'), ('responsible_id', '=', False)]),
                base + '/clients?filter=unassigned')
        if self.has_perm('clients:assign'):
            add('handover', 'درخواست‌های واگذاری',
                C.search_count(visible_domain(self) + [('state', '=', 'active'), ('handover_to_id', '!=', False)]),
                base + '/clients?filter=handover')
        if self.has_perm('members:invite'):
            add('invites', 'دعوت‌های همکار در انتظار پذیرش',
                env['ts.member.invite'].sudo().search_count([('workspace_id', '=', ws.id), ('state', '=', 'pending'),
                                                             ('expires_at', '>', fields.Datetime.now())]), base + '/members')
        if self.has_perm('panel:settings') and ws.terms_version != TERMS_VERSION:
            add('terms', 'شرایط استفاده تغییر کرده است', 1, base + '/settings')
        return out

    # ------------------------------------------------------------------ 5.2 KPI tiles and the funnel
    def dash_tiles(self, days):
        self.ensure_one()
        from ..controllers.clients import visible_domain
        from ..controllers.invites import assignment_domain
        env, ws = self.env, self.workspace_id
        base = '/my/workspaces/%d' % ws.id
        A, C = env['ts.assignment'].sudo(), env['ts.panel.client'].sudo()
        out = []
        if self.can_act() and self.has_perm('invites:manage'):
            dom = assignment_domain(self)

            def link(kind):
                return '%s/invites?kind=%s&period=%d' % (base, kind, days)
            out.append({'key': 'sent', 'label': 'دعوت‌های فرستاده‌شده', 'text': None, 'n': A.search_count(dom + kind_domain('sent', days)), 'url': link('sent')})
            out.append({'key': 'accepted', 'label': 'پذیرفته‌شده', 'text': None, 'n': A.search_count(dom + kind_domain('accepted', days)), 'url': link('accepted')})
            out.append({'key': 'done', 'label': 'تکمیل‌شده', 'text': None, 'n': A.search_count(dom + kind_domain('done', days)), 'url': link('done')})
            y = A.search_count(dom + kind_domain('active', days))
            if y >= MIN_N:
                x = A.search_count(dom + kind_domain('active', days) + [('state', '=', 'done')])
                out.append({'key': 'rate', 'label': 'نرخ تکمیل', 'n': y, 'text': (x, y), 'url': link('active')})
            if self.has_perm('clients:assign') or self.role == 'owner':
                done = A.search(dom + kind_domain('done', days))
                mins = [(a.attempt_id.submitted_at - a.attempt_id.started_at).total_seconds() / 60
                        for a in done if a.attempt_id.submitted_at and a.attempt_id.started_at]
                if len(mins) >= MIN_N:
                    out.append({'key': 'median', 'label': 'میانهٔ زمان تکمیل (دقیقه)', 'n': round(median(mins)), 'text': None, 'url': None})
                out.append({'key': 'noshare', 'label': 'تکمیل‌شده بدون اشتراک نتیجه',
                            'n': A.search_count(dom + kind_domain('noshare', days)), 'text': None, 'url': link('noshare')})
        if self.has_perm('clients:be_responsible') and self.has_perm('clients:read_own'):
            out.append({'key': 'mine_open', 'label': 'مراجعان باز من',
                        'n': C.search_count(visible_domain(self) + [('state', '=', 'active'), ('responsible_id', '=', self.id), ('open_count', '>', 0)]),
                        'text': None, 'url': base + '/clients?filter=mine_open'})
        if self.has_perm('credits:read'):
            wallet = env['ts.wallet']._for_workspace(ws)
            out.append({'key': 'usage', 'label': 'مصرف این دوره', 'n': wallet.units_since(period_start(days)),
                        'text': 'رایگان در این فصل' if wallet._free_mode() else None, 'url': base + '/credits'})
        return out[:8]

    def dash_funnel(self, days):
        """[(state, label, n, url)] for the invitations created in the period (invited -> done)."""
        self.ensure_one()
        from ..controllers.base import STATE_LABELS
        from ..controllers.invites import assignment_domain
        if not (self.can_act() and self.has_perm('invites:manage')):
            return []
        A = self.env['ts.assignment'].sudo()
        base = '/my/workspaces/%d' % self.workspace_id.id
        dom = assignment_domain(self) + kind_domain('created', days)
        counts = {st: n for st, n in A._read_group(dom, groupby=['state'], aggregates=['__count'])}
        return [(st, STATE_LABELS[st], counts.get(st, 0), '%s/invites?state=%s&kind=created&period=%d' % (base, st, days))
                for st in ('invited', 'opened', 'accepted', 'in_progress', 'done')]

    # ------------------------------------------------------------------ DSH-4 workload (owner and managers)
    def dash_workload(self):
        self.ensure_one()
        from ..controllers.clients import visible_domain
        if not self.has_perm('clients:assign'):
            return []
        env = self.env
        C, A = env['ts.panel.client'].sudo(), env['ts.assignment'].sudo()
        dom = visible_domain(self) + [('state', '=', 'active'), ('responsible_id', '!=', False)]
        clients = {m.id: n for m, n in C._read_group(dom, groupby=['responsible_id'], aggregates=['__count'])}
        opens = {}
        for a in A.search([('workspace_id', '=', self.workspace_id.id), ('state', 'in', list(OPEN_STATES)),
                           ('client_id', 'in', C.search(dom).ids)]):
            r = a.client_id.responsible_id.id
            opens[r] = opens.get(r, 0) + 1
        members = env['ts.workspace.member'].sudo().search([('workspace_id', '=', self.workspace_id.id), ('active', '=', True)])
        return [(m, clients.get(m.id, 0), opens.get(m.id, 0)) for m in members if m.has_perm('clients:be_responsible')]

    # ------------------------------------------------------------------ DSH-3 onboarding checklist (owner)
    def dash_checklist(self):
        """[(label, done, url or None)] or [] when finished, dismissed or not for this member."""
        self.ensure_one()
        ws = self.workspace_id
        if not self.has_perm('members:invite') or ws.onboarding_dismissed_on:
            return []
        env = self.env
        base = '/my/workspaces/%d' % ws.id
        S = env['ts.assignment'].sudo()
        others = len(ws.member_ids.filtered(lambda m: m.active and m != self))
        others += env['ts.member.invite'].sudo().search_count([('workspace_id', '=', ws.id), ('state', '=', 'pending')])
        solo = self.owner_practices
        steps = [
            ('پنل ساخته شد', True, None),
            ('نام و لوگوی پنل', bool(ws.partner_id.image_1920), base + '/settings'),
            ('راه ارتباط با پنل', bool(ws.partner_id.phone or ws.partner_id.email), base + '/settings'),
            ('دعوت اولین همکار' + (' (برای کار تک‌نفره لازم نیست)' if solo else ''), bool(others) or bool(solo), base + '/members'),
            ('ثبت اولین شرکت‌کننده', bool(env['ts.panel.client'].sudo().search_count([('workspace_id', '=', ws.id)])), base + '/clients'),
            ('دعوت اولین شرکت‌کننده' + (' (پس از تأیید)' if ws.gated else ''), bool(S.search_count([('workspace_id', '=', ws.id)])), base + '/invites/new?fresh=1'),
            ('اولین نتیجهٔ تکمیل‌شده', bool(S.search_count([('workspace_id', '=', ws.id), ('state', '=', 'done')])), base + '/invites'),
        ]
        return [] if all(s[1] for s in steps) else steps
