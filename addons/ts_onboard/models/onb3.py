"""onb3 (release 3 of onboarding): the first session inside a panel (docs/onboarding/03_panel_first_session.md).

* The panel's kind (clinic / solo / school / hr) picks its starter: BAT-INTAKE-1, TALENT-INV-15 or BAT-HR-SHORT on a sample
  position «کارشناس فروش (نمونه)» made with every new employment panel.
* «اول خودتان ببینید …»: a member takes the starter as a participant of his own panel (ts_preview). Never billed and never
  counted (usage, statistics, funnels, fairness, norms, reminders); it ends on the report view the panel's practitioners see.
* «شروع کار» (four steps with real ticks) and, after the first real result is opened, «پنل را کامل کنید».
* One-screen invitations with a permanent link of the panel (an open-link campaign that never closes by itself).
* Activation events (ts.funnel.event, no personal data) and the back-office follow-up after 7 days without a result.
Nothing here widens who sees what: a try-out is the member's own data, every other read keeps its own checks.
"""
import logging
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.ts_assessment.models.attempt import fa_digits

_logger = logging.getLogger(__name__)

KINDS = [('clinic', 'مرکز مشاوره'), ('solo', 'مشاور یا روان‌شناس مستقل'), ('school', 'مدرسه'),
         ('hr', 'استخدام و منابع انسانی')]
# the word for the people the panel serves: (one, many)
WORDS = {'clinic': ('مراجع', 'مراجعان'), 'solo': ('مراجع', 'مراجعان'), 'school': ('دانش‌آموز', 'دانش‌آموزان'),
         'hr': ('داوطلب', 'داوطلبان')}
# kind -> ('battery' | 'instrument', code)
STARTERS = {'clinic': ('battery', 'BAT-INTAKE-1'), 'solo': ('battery', 'BAT-INTAKE-1'),
            'school': ('instrument', 'TALENT-INV-15'), 'hr': ('battery', 'BAT-HR-SHORT')}
SAMPLE_POSITION = 'کارشناس فروش (نمونه)'
SAMPLE_OCCUPATIONS = ('41-4012.00', '41-3091.00', '41-2031.00')    # نمایندهٔ فروش عمده و بازاریاب, then fallbacks
PREVIEW_PREFIX = 'پیش‌نمایش — '
REAL = [('ts_preview', '=', False), ('channel', 'not in', ('self_share', 'import', 'preview'))]
PERM_NAME = 'پیوند همیشگی پنل'
KIND_OF_KIND = {'school': 'school', 'org': 'hr', 'clinic': 'clinic', 'solo': 'solo'}


def kind_of_purpose(purpose):
    return {'clinical': 'clinic', 'education': 'school', 'employment': 'hr'}.get(purpose)


def sms_allowed(env):
    """The guide and join SMS of onb3 go out from the production database only, or to a local fake gateway (the test
    suites). A clone restored from a dump carries the live Kavenegar settings and the live cron runs on it: without this
    rule a stale clone would text real panel owners (the weekly digest) and test numbers."""
    ICP = env['ir.config_parameter'].sudo()
    if env.cr.dbname == ((ICP.get_str('ts_onboard.sms_db') or '').strip() or 'eot_main'):
        return True
    return (ICP.get_str('ts_kavenegar.api_base') or '').startswith(('http://127.0.0.1:', 'http://localhost:'))


class TsWorkspaceOnb3(models.Model):
    _name = 'ts.workspace'
    _inherit = ['ts.workspace', 'mail.activity.mixin']

    ts_kind = fields.Selection(KINDS, 'نوع پنل (شروع کار)', copy=False,
                               help='پیش‌نمایش، نمونهٔ گزارش، سنجهٔ آغاز و متن‌های «شروع کار» از همین نوع می‌آیند.')
    # «شروع کار» is for panels made since onb3; the migration turns it off for older panels (they are already set up)
    ts_onb_start = fields.Boolean('نمایش «شروع کار»', default=True, copy=False)
    ts_onb_first_invite_at = fields.Datetime('نخستین دعوت واقعی', readonly=True, copy=False)
    ts_onb_result_ready_at = fields.Datetime('نخستین نتیجهٔ آماده', readonly=True, copy=False)
    ts_onb_result_opened_at = fields.Datetime('نخستین نتیجهٔ بازشده', readonly=True, copy=False)
    ts_onb_followup_at = fields.Datetime('پیگیری تیم (۷ روز بدون نتیجه)', readonly=True, copy=False)
    ts_perm_campaign_id = fields.Many2one('ts.campaign', 'پیوند همیشگی پنل', readonly=True, copy=False, ondelete='set null')

    # ------------------------------------------------------------------ kind, words, starter
    def ts_onb_kind(self):
        self.ensure_one()
        ws = self.sudo()
        if ws.ts_kind:
            return ws.ts_kind
        k = kind_of_purpose(ws.purpose)
        if k == 'clinic':
            owners = ws.member_ids.filtered(lambda m: m.active)
            if len(owners) == 1 and owners.role == 'owner' and owners.owner_practices:
                return 'solo'
        return k

    def ts_onb_words(self):
        """{'one': «مراجع», 'many': «مراجعان»} for this panel's kind (copy only)."""
        one, many = WORDS.get(self.ts_onb_kind() or '', ('شرکت‌کننده', 'شرکت‌کنندگان'))
        return {'one': one, 'many': many}

    def ts_onb_starter(self, member=None):
        """(battery, instrument) of this panel's starter, as `member` may invite it (both empty when it is not in his
        catalog or not published)."""
        self.ensure_one()
        B, I = self.env['ts.battery'].sudo(), self.env['ts.instrument'].sudo()
        what, code = STARTERS.get(self.ts_onb_kind() or '', (None, None))
        if what == 'battery':
            b = B.search([('code', '=', code), ('state', '=', 'published')], limit=1)
            if b and (not member or b in member.allowed_batteries()):
                return b, b.ts_first_instrument()
        elif what == 'instrument':
            i = I.search([('code', '=', code), ('state', '=', 'published')], limit=1)
            if i and (not member or i in member.allowed_instruments()):
                return B, i
        return B, I

    def ts_onb_starter_facts(self, member=None):
        """{'name', 'time'} of the starter for the cards (one source with the invitation pages)."""
        from odoo.addons.ts_org.controllers.main import effort_facts
        b, i = self.ts_onb_starter(member)
        if not i:
            return None
        facts = effort_facts(i, b or None, self.purpose)
        return {'name': b.ts_title() if b else i.ts_title(), 'time': facts.get('time') or ''}

    # ------------------------------------------------------------------ HR: the sample position
    def ts_onb_sample_position(self, create=True, by=None):
        """The sample position of an employment panel; made on first use (editable like any other position)."""
        self.ensure_one()
        if self.purpose != 'employment' or 'ts.hire.position' not in self.env:
            return self.env['ts.hire.position'] if 'ts.hire.position' in self.env else None
        P = self.env['ts.hire.position'].sudo()
        p = P.search([('workspace_id', '=', self.id), ('ts_sample', '=', True)], order='id', limit=1)
        if p or not create:
            return p
        Occ = self.env['ts.onet.occupation'].sudo()
        occ = Occ.browse()
        for code in SAMPLE_OCCUPATIONS:
            occ = Occ.search([('code', '=', code)], limit=1)
            if occ:
                break
        bat = self.env['ts.battery'].sudo().search([('code', '=', 'BAT-HR-SHORT'), ('state', '=', 'published')], limit=1)
        if not occ or not bat:
            return P
        owner = by.user_id if by else self.owner_user_id
        with self.env.cr.savepoint():
            p = P.create({'name': SAMPLE_POSITION, 'workspace_id': self.id, 'occupation_id': occ.id, 'battery_choice': 'short',
                          'deadline': date.today() + timedelta(days=30), 'created_by_id': (owner or self.env.user).id,
                          'ts_sample': True, 'profile_reviewed': True, 'state': 'open',
                          'note': 'موقعیت نمونه برای شروع؛ تغییرش دهید یا داوطلب واقعی دعوت کنید.'})
        self.env['ts.audit.event'].sudo().log('position.create', p, workspace=self, occupation=occ.code, sample=True)
        return p

    # ------------------------------------------------------------------ the permanent link
    def ts_onb_permanent_link(self, member, create=True):
        """The panel's permanent link for its starter (an open-link campaign, onb3): the participant signs in with his own
        number (S-AUTH), types his name and joins with the sharing choice of /c. Made on first use by a member who may
        invite; a counseling panel needs its escalation contact first (the join is an invitation of a client)."""
        self.ensure_one()
        ws = self.sudo()
        c = ws.ts_perm_campaign_id
        if c and c.state == 'open':
            return c
        if not create:
            return c.browse()
        if not (member.can_act() and member.has_perm('invites:create')):
            raise UserError('ساخت پیوند همیشگی با عضوی است که دعوت می‌فرستد.')
        if ws.purpose == 'clinical' and not ws.escalation_contact_id:
            raise UserError('پیش از ساخت پیوند همیشگی، پیگیری فوری نشانه‌های خطر را بپذیرید.')
        b, i = ws.ts_onb_starter(member)
        if not i:
            raise UserError('سنجهٔ آغاز این پنل در فهرست شما نیست؛ از «تنظیمات بیشتر» سنجهٔ دیگری بفرستید.')
        vals = {'workspace_id': ws.id, 'name': PERM_NAME, 'instrument_id': i.id, 'kind': 'open_link', 'created_by_id': member.id,
                'ts_permanent': True, 'open_max': 500, 'open_expires_at': False}
        if b:
            vals['battery_id'] = b.id
        c = self.env['ts.campaign'].sudo().create(vals)
        c.open_expires_at = False
        ws.ts_perm_campaign_id = c.id
        self.env['ts.audit.event'].sudo().log('campaign.create', c, workspace=ws, member=member, kind='open_link', permanent=True)
        return c

    # ------------------------------------------------------------------ money: one calm line (free panels)
    def ts_onb_usage_line(self):
        """«تا امروز N نتیجه؛ در دورهٔ آزمایشی رایگان» for a free panel (None for a prepaid one: its credit card says it)."""
        self.ensure_one()
        ws = self.sudo()
        if 'billing_mode' in ws._fields and ws.billing_mode == 'prepaid':
            return None
        n = self.env['ts.assignment'].sudo().search_count([('workspace_id', '=', ws.id), ('state', '=', 'done')] + REAL)
        return 'تا امروز %s نتیجه؛ در دورهٔ آزمایشی رایگان' % fa_digits(n)

    # ------------------------------------------------------------------ activation marks
    def _ts_onb_mark(self, field, step):
        """Set an activation timestamp once and log the funnel step (no personal data). Never raises."""
        for ws in self.sudo():
            try:
                if ws[field]:
                    continue
                ws[field] = fields.Datetime.now()
                self.env['ts.funnel.event'].sudo().ts_log_panel(step, ws)
            except Exception:       # noqa: BLE001 - measuring never breaks the work
                _logger.exception('ts_onboard: activation mark %s failed', field)

    # ------------------------------------------------------------------ creation
    @api.model
    def ts_panel_create(self, user, name, kind, solo_as=None, terms=False, escalation_ok=False, license_number=None):
        ws = super().ts_panel_create(user, name, kind, solo_as=solo_as, terms=terms, escalation_ok=escalation_ok,
                                     license_number=license_number)
        k = KIND_OF_KIND.get(kind)
        if kind == 'solo' and ws.purpose != 'clinical':
            k = kind_of_purpose(ws.purpose)          # an older caller's solo counselor (education) or solo HR
        ws.sudo().write({'ts_kind': k, 'ts_onb_start': True})
        if ws.purpose == 'employment':
            owner = ws.member_ids.filtered(lambda m: m.role == 'owner')[:1]
            ws.ts_onb_sample_position(by=owner)
        self.env['ts.funnel.event'].sudo().ts_log_panel('panel_created', ws)
        self.env['ts.onb.nudge'].sudo().ts_on_panel_created(ws)
        return ws


class TsMemberOnb3(models.Model):
    _inherit = 'ts.workspace.member'

    ts_guide_sms = fields.Boolean('پیامک‌های راهنما', default=True,
                                  help='پیامک‌های کوتاه راهنمای شروع کار و خلاصهٔ هفتگی پنل. هیچ‌کدام نام سنجه، مراجع یا نتیجه را نمی‌آورد.')
    ts_start_hidden_on = fields.Datetime('«شروع کار» پنهان شد', readonly=True, copy=False)
    ts_more_hidden_on = fields.Datetime('«پنل را کامل کنید» پنهان شد', readonly=True, copy=False)

    # ------------------------------------------------------------------ the member's own try-out
    def ts_onb_preview(self):
        """This member's latest try-out in this panel (any state), or an empty recordset."""
        self.ensure_one()
        return self.env['ts.assignment'].sudo().search([
            ('workspace_id', '=', self.workspace_id.id), ('ts_preview', '=', True), ('user_id', '=', self.user_id.id),
            ('withdrawn', '=', False)], order='id desc', limit=1)

    def ts_onb_can_try(self):
        self.ensure_one()
        return bool(self.active and self.can_act() and (self.has_perm('invites:create') or self.role == 'owner'))

    def ts_onb_try(self):
        """Start (or go on with) this member's try-out of the panel's starter. Returns the assignment."""
        self.ensure_one()
        me = self.sudo()
        ws = me.workspace_id
        if not me.ts_onb_can_try():
            raise UserError('پیش‌نمایش با عضو فعالی است که دعوت می‌فرستد.')
        a = me.ts_onb_preview()
        if a and a.state not in ('declined', 'withdrawn', 'expired'):
            return a
        bat, inst = ws.ts_onb_starter(me)
        if not inst:
            raise UserError('سنجهٔ آغاز این پنل در فهرست شما نیست.')
        name = me.user_id.partner_id.ts_known_name() or 'عضو پنل'
        label = PREVIEW_PREFIX + name
        C = self.env['ts.panel.client'].sudo()
        client = C.search([('workspace_id', '=', ws.id), ('user_id', '=', me.user_id.id), ('source', '=', 'preview')], limit=1)
        if not client:
            client = C.create({'workspace_id': ws.id, 'name': label, 'user_id': me.user_id.id, 'source': 'preview',
                               'age_group': 'adult', 'responsible_id': False})
        elif client.state != 'active':
            client.write({'state': 'active', 'archived_on': False})
        vals = {'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': label, 'invited_by_id': me.user_id.id,
                'client_id': client.id, 'ts_preview': True, 'responsible_id': False,
                'note': 'پیش‌نمایش: همان چیزی که %s می‌بیند.' % ws.ts_onb_words()['one']}
        if bat:
            vals['battery_id'] = bat.id
        if ws.purpose == 'employment':
            p = ws.ts_onb_sample_position(by=me)
            if p:
                vals.update(position_id=p.id, ts_fair_asked=True, deadline=False)
        a = self.env['ts.assignment'].sudo().with_user(me.user_id).sudo().create(vals)
        a.action_accept(me.user_id, share=True)
        self.env['ts.audit.event'].sudo().log('onboarding.try', a, workspace=ws, member=me,
                                              item=bat.code if bat else inst.code)
        return a

    def ts_onb_take_url(self, a):
        """Where a try-out goes on: its next unfinished part, or its end page."""
        self.ensure_one()
        parts = a.ts_battery_attempts() if hasattr(a, 'ts_battery_attempts') else a.attempt_id
        nxt = parts.filtered(lambda t: t.state != 'done')[:1]
        if nxt:
            return '/take/%s' % nxt.access_token
        return '/my/workspaces/%s/try/end' % self.workspace_id.id

    def ts_onb_preview_url(self, a):
        """The report of a finished try-out as the panel's practitioners see a client's (with the coach line)."""
        self.ensure_one()
        ws = self.workspace_id
        if 'position_id' in a._fields and a.position_id:
            return '/my/workspaces/%s/positions/%s/c/%s?preview=1' % (ws.id, a.position_id.id, a.id)
        if 'battery_id' in a._fields and a.battery_id:
            return '/my/workspaces/%s/clients/%s/b/%s?preview=1' % (ws.id, a.client_id.id, a.id)
        return '/my/workspaces/%s/clients/%s/r/%s?preview=1' % (ws.id, a.client_id.id, a.attempt_id.id)

    def ts_onb_coach(self):
        """The coach line on the try-out's report: {'one', 'url', 'cta'} when this member has a finished try-out."""
        self.ensure_one()
        a = self.ts_onb_preview()
        if not a or a.state != 'done':
            return None
        ws = self.workspace_id
        w = ws.ts_onb_words()
        return {'one': w['one'], 'many': w['many'], 'url': self.ts_onb_invite_url(), 'cta': self.ts_onb_invite_cta()}

    # ------------------------------------------------------------------ where the first invitation is sent from
    def ts_onb_invite_url(self):
        self.ensure_one()
        ws = self.workspace_id
        kind = ws.ts_onb_kind()
        if kind == 'hr':
            p = ws.ts_onb_sample_position(create=False)
            return '/my/workspaces/%s/positions/%s#tsh-invite' % (ws.id, p.id) if p else '/my/workspaces/%s/positions' % ws.id
        if kind == 'school':
            return '/my/workspaces/%s/invites/new?mode=link' % ws.id
        return '/my/workspaces/%s/invites/new' % ws.id

    def ts_onb_invite_cta(self):
        kind = self.workspace_id.ts_onb_kind()
        return {'school': 'حالا پیوند کلاس را بسازید', 'hr': 'حالا نخستین داوطلب‌ها را دعوت کنید'}.get(
            kind, 'حالا نخستین %s را دعوت کنید' % self.workspace_id.ts_onb_words()['one'])

    # ------------------------------------------------------------------ «شروع کار»
    def ts_onb_start_card(self):
        """The dashboard card «شروع کار»: None, or {'steps', 'done_n', 'total', 'current', 'hero', 'finished'}."""
        self.ensure_one()
        me = self.sudo()
        ws = me.workspace_id
        if not (ws.ts_onb_start and ws.state == 'active' and me.active and me.can_act()):
            return None
        owner_like = me.has_perm('members:invite')
        if me.ts_start_hidden_on:
            return None
        kind = ws.ts_onb_kind()
        if not kind:
            return None
        w = ws.ts_onb_words()
        base = '/my/workspaces/%d' % ws.id
        pv = me.ts_onb_preview()
        tried = bool(pv and pv.state == 'done')
        invited = bool(ws.ts_onb_first_invite_at) or bool(self.env['ts.assignment'].sudo().search_count(
            [('workspace_id', '=', ws.id)] + REAL, limit=1))
        opened = bool(ws.ts_onb_result_opened_at)
        ready = bool(ws.ts_onb_result_ready_at)
        if not owner_like:
            # a colleague who joined: only his own try-out, until he did it
            if tried or not me.ts_onb_can_try():
                return None
            invited = opened = True
        label3 = {'school': 'پیوند کلاس', 'hr': 'دعوت داوطلب‌ها'}.get(kind, 'نخستین دعوت')
        label4 = 'نخستین گزارش کلاس' if kind == 'school' else 'نخستین نتیجه'
        steps = [{'key': 'made', 'label': 'پنل ساخته شد', 'done': True},
                 {'key': 'try', 'label': 'خودتان امتحان کنید', 'done': tried},
                 {'key': 'invite', 'label': label3, 'done': invited},
                 {'key': 'result', 'label': label4, 'done': opened}]
        if not owner_like:
            steps = steps[:2]
        done_n = sum(1 for s in steps if s['done'])
        # the first real result opened is the goal: the card is finished even if the owner never tried it himself (the
        # dashboard then shows «پنل را کامل کنید»)
        current = None if (owner_like and opened) else next((s for s in steps if not s['done']), None)
        facts = ws.ts_onb_starter_facts(me) or {}
        hero = None
        if current and current['key'] == 'try':
            going = bool(pv and pv.state not in ('done', 'declined', 'withdrawn', 'expired'))
            hero = {'title': 'اول خودتان ببینید %s چه می‌بیند' % w['one'],
                    'text': ('«%s» را مثل یک %s پر کنید%s. پیش‌نمایش رایگان است و در هیچ هزینه یا آماری شمرده نمی‌شود؛ '
                             'در پایان، گزارش را همان‌طور می‌بینید که گزارش %s را خواهید دید.') % (
                        facts.get('name') or 'سنجهٔ آغاز', w['one'], ('؛ %s' % facts['time']) if facts.get('time') else '',
                        w['many']),
                    'post': base + '/try' if not going else None,
                    'url': me.ts_onb_take_url(pv) if going else None,
                    'btn': 'ادامهٔ پیش‌نمایش' if going else 'امتحان کنید',
                    'second': (base + '/sample', 'یا نمونهٔ گزارش را ببینید')}
        elif current and current['key'] == 'invite':
            hero = {'title': me.ts_onb_invite_cta(),
                    'text': {'school': 'یک پیوند یا QR برای کل کلاس؛ هر دانش‌آموز با شمارهٔ خودش وارد می‌شود و نتیجه با اجازهٔ او به پنل می‌رسد.',
                             'hr': 'نام و موبایل داوطلب‌ها را در موقعیت نمونه بنویسید؛ یا نخست موقعیت را به شغل خودتان تغییر دهید.'}.get(
                        kind, 'با نام و موبایل %s دعوت بفرستید یا پیوند همیشگی پنل را در پیام نوبت‌دهی بگذارید.' % w['one']),
                    'url': me.ts_onb_invite_url(), 'btn': label3 if kind in ('school', 'hr') else 'دعوت نخستین %s' % w['one'],
                    'second': (pv and pv.state == 'done' and me.ts_onb_preview_url(pv) or None, 'دیدن دوبارهٔ پیش‌نمایش')}
        elif current and current['key'] == 'result':
            if ready:
                hero = {'title': 'نخستین نتیجه آماده است', 'text': 'آن را باز کنید؛ گزارش‌های بعدی هم همین‌جا می‌آیند.',
                        'url': base + '/invites/unseen', 'btn': 'دیدن نتیجه'}
            else:
                hero = {'title': 'منتظر نخستین نتیجه', 'wait': True,
                        'text': 'وضعیت هر دعوت را پایین‌تر می‌بینید. وقتی نخستین نتیجه آماده شود، پیامک کوتاهی هم می‌فرستیم.'}
        return {'steps': steps, 'done_n': done_n, 'total': len(steps), 'current': current, 'hero': hero,
                'finished': current is None, 'help': '/help/panel#start-%s' % kind}

    def ts_onb_hide(self, which):
        self.ensure_one()
        field = {'start': 'ts_start_hidden_on', 'more': 'ts_more_hidden_on'}[which]
        self.sudo()[field] = fields.Datetime.now()
        self.env['ts.audit.event'].sudo().log('onboarding.hide', self, workspace=self.workspace_id, member=self, card=which)

    # ------------------------------------------------------------------ «پنل را کامل کنید»
    def ts_onb_more_card(self):
        """The second card, after the first real result was opened: optional items ticked by real data, or None."""
        self.ensure_one()
        me = self.sudo()
        ws = me.workspace_id
        if not (ws.state == 'active' and ws.ts_onb_start and me.active and me.can_act() and ws.ts_onb_result_opened_at
                and not me.ts_more_hidden_on):
            return None
        # every item needs its own permission: a member sees only the items he can do (a coordinator of a prepaid panel:
        # credit and caps; a counselor: nothing)
        base = '/my/workspaces/%d' % ws.id
        kind = ws.ts_onb_kind()
        prepaid = 'billing_mode' in ws._fields and ws.billing_mode == 'prepaid'
        brand = hasattr(ws, 'ts_brand_enabled') and ws.ts_brand_enabled()
        items = []

        def add(key, label, why, done, url, perm=True, nocap=False, btn=None):
            if perm:
                items.append({'key': key, 'label': label, 'why': why, 'done': bool(done), 'url': url, 'btn': btn or label,
                              'nocap': nocap and not done})

        has_logo = ws.ts_has_logo() if hasattr(ws, 'ts_has_logo') else bool(ws.partner_id.image_1920)
        add('identity', 'نام و لوگو روی گزارش', 'بالای گزارش هر %s، در صفحه و در PDF.' % ws.ts_onb_words()['one'],
            has_logo, base + ('/settings#tsbr-org' if brand else '/settings'), me.has_perm('panel:profile'), btn='ثبت نام و لوگو')
        if kind != 'solo':
            others = ws.member_ids.filtered(lambda m: m.active and m != me) or self.env['ts.member.invite'].sudo().search_count(
                [('workspace_id', '=', ws.id), ('state', '=', 'pending')])
            add('team', 'دعوت همکاران', 'همکار با پیامکی که استعدادیاب می‌فرستد می‌پیوندد.', others, base + '/members#tsp-invite',
                me.has_perm('members:invite'), btn='دعوت همکار')
        if brand:
            add('sms', 'نام پیامکی', 'سطر اول پیامک‌های دعوت (تا ۱۸ نویسه).', ws.sms_name, base + '/settings#tsbr-org',
                me.has_perm('panel:profile'), btn='نوشتن نام پیامکی')
        if prepaid:
            avail = self.env['ts.wallet']._for_workspace(ws).ts_available()
            add('credit', 'اعتبار و قیمت‌ها', 'هر دعوت هزینه‌اش را از اعتبار پنل رزرو می‌کند.', avail > 0, base + '/credits',
                me.has_perm('credits:read'), btn='دیدن اعتبار و قیمت‌ها')
            capped = self.env['ts.workspace.member'].sudo().search_count(
                [('workspace_id', '=', ws.id), ('active', '=', True), ('monthly_cap', '>', 0)])
            add('caps', 'سقف‌ها', 'سقف ماهانهٔ هزینهٔ دعوت‌های هر مشاور.', capped or ws.ts_onb_nocap_on, base + '/credits#tsb-caps',
                me.has_perm('credits:manage'), nocap=True, btn='تعیین سقف')
        if me.role == 'owner' and me.owner_practices and ws.purpose == 'clinical':
            add('licence', 'رسیدگی به پروانه', 'شماره را بنویسید؛ پس از بررسی، نشان «پروانهٔ تأییدشده» می‌آید.',
                me.license_number, '%s/members/%s#tsbr-member' % (base, me.id), btn='نوشتن شمارهٔ پروانه')
        open_items = [x for x in items if not x['done']]
        if not open_items:
            return None
        recent = ws.ts_onb_result_opened_at and ws.ts_onb_result_opened_at > fields.Datetime.now() - timedelta(days=7) \
            and ws.ts_onb_start
        return {'items': items, 'open': open_items, 'done': [x for x in items if x['done']], 'celebrate': bool(recent),
                'done_n': len(items) - len(open_items), 'total': len(items)}

    # ------------------------------------------------------------------ live invitation status on the dashboard
    def ts_onb_recent(self, limit=5):
        """The latest real invitations this member may see (30 days), for the live stepper."""
        self.ensure_one()
        if not (self.can_act() and self.has_perm('invites:manage')):
            return self.env['ts.assignment']
        from odoo.addons.ts_panel.controllers.invites import assignment_domain
        since = fields.Datetime.now() - timedelta(days=30)
        return self.env['ts.assignment'].sudo().search(
            assignment_domain(self) + [('create_date', '>=', since), ('state', 'in', ('invited', 'opened', 'accepted',
                                                                                        'in_progress', 'done'))],
            order='create_date desc, id desc', limit=limit)


class TsAssignmentOnb3(models.Model):
    _inherit = 'ts.assignment'

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for ws in recs.filtered(lambda a: not a.ts_preview and a.channel not in ('self_share', 'import')).workspace_id:
            ws._ts_onb_mark('ts_onb_first_invite_at', 'first_invite')
        return recs

    def ts_onb_step(self):
        """0..3 on «فرستاده شد → باز شد → در حال پاسخ → آماده», None for an ended invitation."""
        self.ensure_one()
        return {'invited': 0, 'opened': 1, 'accepted': 2, 'in_progress': 2, 'done': 3}.get(self.state)


class TsAttemptOnb3(models.Model):
    _inherit = 'ts.attempt'

    def action_submit(self, *args, **kwargs):
        was = {t.id for t in self if t.state == 'done'}
        res = super().action_submit(*args, **kwargs)
        for t in self:
            if res and t.id not in was and t.state == 'done' and t.workspace_id:
                try:
                    t._ts_onb_after_done()
                except Exception:       # noqa: BLE001 - the result is saved whatever the follow-up does
                    _logger.exception('ts_onboard: after-done of attempt %s', t.id)
        return res

    def _ts_onb_after_done(self):
        s = self.sudo()
        a = s.assignment_id if 'assignment_id' in s._fields and s.assignment_id else \
            self.env['ts.assignment'].sudo().search([('attempt_id', '=', s.id)], limit=1)
        if not a:
            return
        a.invalidate_recordset(['state'])
        if a.state != 'done':
            return                                   # a battery is finished when every part is
        if a.ts_preview:
            self.env['ts.funnel.event'].sudo().ts_log_panel('self_test_done', a.workspace_id, extra=str(a.user_id.id))
            return
        ws = a.workspace_id
        if a.share_level != 'none' and not ws.ts_onb_result_ready_at and a.channel not in ('self_share', 'import'):
            ws.sudo().ts_onb_result_ready_at = fields.Datetime.now()
            self.env['ts.onb.nudge'].sudo().ts_on_first_result(a)


class TsAuditOnb3(models.Model):
    _inherit = 'ts.audit.event'

    @api.model
    def log(self, event_type, record=None, workspace=None, member=None, outcome='ok', **detail):
        res = super().log(event_type, record=record, workspace=workspace, member=member, outcome=outcome, **detail)
        if event_type in ('result.view', 'hire.view', 'report.group_view') and outcome == 'ok':
            try:
                self._ts_onb_opened(event_type, record, workspace)
            except Exception:       # noqa: BLE001 - auditing never breaks the page
                _logger.exception('ts_onboard: first-result mark failed')
        return res

    @api.model
    def _ts_onb_opened(self, event_type, record, workspace):
        ws = (workspace or (record.workspace_id if record and 'workspace_id' in record._fields else None))
        if not ws or ws.sudo().ts_onb_result_opened_at:
            return
        rec = record.sudo() if record else None
        if event_type == 'report.group_view':
            real = self.env['ts.assignment'].sudo().search_count([('workspace_id', '=', ws.id), ('state', '=', 'done')] + REAL,
                                                                limit=1)
        elif rec is not None and rec._name == 'ts.attempt':
            real = not rec.ts_preview and rec.source != 'import' and rec.state == 'done'
        elif rec is not None and rec._name == 'ts.assignment':
            real = not rec.ts_preview and (rec.state == 'done' or bool(
                'battery_id' in rec._fields and rec.battery_id and rec.ts_battery_progress()[0] > 0))
        else:
            real = False
        if real:
            ws._ts_onb_mark('ts_onb_result_opened_at', 'first_result_opened')


class TsCampaignOnb3(models.Model):
    _inherit = 'ts.campaign'

    ts_permanent = fields.Boolean('پیوند همیشگی پنل', readonly=True, copy=False,
                                  help='پیوند باز سنجهٔ آغاز پنل (onb3): خودبه‌خود بسته نمی‌شود و سقف پیوستن ندارد؛ پنل هر وقت بخواهد آن را می‌بندد.')

    def open_state(self):
        self.ensure_one()
        if self.ts_permanent:
            return 'ok' if (self.kind == 'open_link' and self.state == 'open') else 'closed'
        return super().open_state()


class TsMemberInviteOnb3(models.Model):
    _inherit = 'ts.member.invite'

    @api.model
    def ts_create(self, by_member, role, phone_raw=None, email_raw=None):
        """onb3: a colleague invited with a mobile number gets the join SMS (/j/ link) from the system at once; the join
        itself is unchanged (sign-in with that number, then «پذیرفتن»; the licence is never asked at the door)."""
        inv = super().ts_create(by_member, role, phone_raw=phone_raw, email_raw=email_raw)
        if inv.phone:
            inv.sudo()._ts_onb_send_join_sms()
        return inv

    def _ts_onb_send_join_sms(self):
        self.ensure_one()
        ws = self.workspace_id
        company = (ws.company_id or self.env.company).sudo()
        if ws.state != 'active' or not company.kv_enabled or not sms_allowed(self.env):
            return False
        from odoo.addons.ts_sms.models.phone_otp import iran_mobile
        number = iran_mobile(self.phone)
        if not number:
            return False
        ok = self.env['ts.notification']._send_sms(company, number, self.ts_member_invite_sms_body())
        if ok:
            self.write({'sms_sent': True})
        self.env['ts.audit.event'].sudo().log('member.invite_sms', self, workspace=ws, role=self.role, outcome='ok' if ok else 'error')
        return ok
