"""Clinic phase 6: the set-up guide of a counseling-center panel (owner decision: "the institute must manage its own institute").

Two pieces, both computed from real data on every page load (nothing is ticked by hand):

* «راه‌اندازی مرکز»: a checklist on the dashboard of the owner, admin and clinic director of a counseling-center panel
  (purpose `clinical`) until every step is done or the member hides it («بعداً نشانم نده», stored per member, reversible
  from /help/panel#center-setup). It replaces ts_panel's generic DSH-3 checklist for those members.
* A first-run card for a counselor (role `clinician`) whose own report identity is empty (no title), linking to their member
  page section «هویت شما در گزارش‌ها»; dismissible per member, and gone by itself once a title is saved.

Nothing here grants or checks access: every button points at an existing page that keeps its own permission check, and a
step whose page the viewer may not open shows who does it instead of a button.
"""
from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_billing.tools import CAPPED_ROLES

from .brand import clean_line

ONB_ROLES = ('owner', 'admin', 'clinic_director')     # who sees «راه‌اندازی مرکز»
STAFF_ROLES = ('clinician', 'clinic_director')        # step 2: colleagues who work with clients
HELP_URL = '/help/panel#center-setup'
NOT_YOURS = 'این کار با مالک پنل یا مدیر مرکز مشاوره است.'


class TsWorkspaceOnboarding(models.Model):
    _inherit = 'ts.workspace'

    ts_onb_nocap_on = fields.Datetime('«بدون سقف» برای مشاوران', readonly=True, copy=False,
                                      help='زمانی که مالک یا مدیر پنل در راهنمای راه‌اندازی گفت مشاوران بدون سقف ماهانه کار کنند.')

    def ts_onb_mark_nocap(self, by):
        """«بدون سقف بماند» (step 4): the owner / admin / director (credits:manage) of this prepaid panel decides that the
        counselors work without a monthly cap. Returns True when it was not recorded yet."""
        self.ensure_one()
        if by.workspace_id != self or not by.has_perm('credits:manage') or not by.can_act():
            raise UserError('سقف ماهانه را مالک، هماهنگ‌کننده یا مدیر پنل تعیین می‌کند.')
        if not self.ts_is_prepaid():
            raise UserError('سقف ماهانه فقط در پنل پیش‌پرداخت معنا دارد.')
        if self.sudo().ts_onb_nocap_on:
            return False
        self.sudo().ts_onb_nocap_on = fields.Datetime.now()
        self.env['ts.audit.event'].sudo().log('onboarding.nocap', self, workspace=self, member=by)
        return True


class TsMemberOnboarding(models.Model):
    _inherit = 'ts.workspace.member'

    ts_onb_hidden_on = fields.Datetime('راهنمای راه‌اندازی پنهان شد', readonly=True, copy=False)
    ts_onb_card_hidden_on = fields.Datetime('یادآوری هویت در گزارش‌ها بسته شد', readonly=True, copy=False)
    ts_catalog_seen_on = fields.Datetime('فهرست مجاز بررسی شد', readonly=True, copy=False,
                                         help='آخرین بار که فرم «سنجه‌ها و مجموعه‌های مجاز» این عضو ذخیره شد، حتی بدون تغییر.')

    # ------------------------------------------------------------------ who sees what
    def ts_onb_applies(self, ignore_hidden=False):
        """The checklist is for an owner / admin / clinic director who can work in a running counseling-center panel."""
        self.ensure_one()
        m = self.sudo()
        ws = m.workspace_id
        if not (m.active and m.role in ONB_ROLES and ws.purpose == 'clinical' and ws.state in ('pilot', 'active')):
            return False
        if not m.can_act():
            return False
        return ignore_hidden or not m.ts_onb_hidden_on

    def dash_checklist(self):
        """ts_panel's generic set-up list (DSH-3) gives way to «راه‌اندازی مرکز» for the members who get that one, also when
        they hid it (one list, one decision)."""
        if self.ts_onb_applies(ignore_hidden=True):
            return []
        return super().dash_checklist()

    # ------------------------------------------------------------------ the six steps
    def _ts_onb_clinicians(self):
        ws = self.sudo().workspace_id
        return self.env['ts.workspace.member'].sudo().search(
            [('workspace_id', '=', ws.id), ('active', '=', True), ('role', '=', 'clinician')], order='id')

    @staticmethod
    def _ts_catalog_decided(m):
        """A counselor's catalog is a decision on record when it is restricted, or when the catalog form was saved for them
        (also unchanged: «همهٔ موارد پنل» kept on purpose)."""
        return bool(m.catalog_restricted or m.restrict_instrument_ids or m.restrict_battery_ids or m.ts_catalog_seen_on)

    def ts_onb_steps(self):
        """[{key, n, label, why, state ('done' | 'way' | 'open'), done, optional, current, url, btn, note, nocap}] for this
        member's panel, whatever the member's role (the caller decides whether to show them). Order (UX audit G8-P1-4: the
        real dependency chain): identity, counselors, credit, catalog, caps (optional), first invitation."""
        self.ensure_one()
        me = self.sudo()
        ws = me.workspace_id
        env = self.env
        base = '/my/workspaces/%d' % ws.id
        prepaid = ws.ts_is_prepaid()
        steps = []

        def add(key, label, why, done, url=None, btn=None, note=None, way=False, optional=False, nocap=False, keep_note=False):
            steps.append({'key': key, 'label': label, 'why': why, 'done': bool(done),
                          'state': 'done' if done else ('way' if way else 'open'), 'optional': optional,
                          'url': None if done else url, 'btn': btn, 'note': note if (keep_note or not done) else None,
                          'nocap': nocap and not done})

        # 1. identity on reports: the name the client sees (ts_public_name(): the report name, else the panel name) and a
        #    real logo (= the institution partner's image, Odoo's stand-in picture does not count). The logo field lives in
        #    the identity section of the settings page, so the button always opens that section.
        has_name = bool(ws.ts_public_name())
        has_logo = ws.ts_has_logo()
        can1 = me.has_perm('panel:profile') and me.ts_brand_manager()
        missing = [t for t, ok in (('نام مرکز در گزارش‌ها', has_name), ('لوگو', has_logo)) if not ok]
        add('identity', 'هویت مرکز در گزارش‌ها', 'نام و لوگوی مرکز بالای گزارش هر مراجع، در صفحه و در فایل PDF، می‌آید.',
            has_name and has_logo, url=(base + '/settings#tsbr-org') if can1 else None, btn='تکمیل هویت مرکز',
            note=('مانده: %s.' % ' و '.join(missing)) if can1 else NOT_YOURS)

        # 2. counselors: an active clinician or clinic director (roles that never include the owner); a pending colleague
        #    invitation for one of those roles is «در راه»
        staff = env['ts.workspace.member'].sudo().search_count(
            [('workspace_id', '=', ws.id), ('active', '=', True), ('role', 'in', list(STAFF_ROLES))])
        pending = env['ts.member.invite'].sudo().search_count(
            [('workspace_id', '=', ws.id), ('state', '=', 'pending'), ('role', 'in', list(STAFF_ROLES)),
             ('expires_at', '>', fields.Datetime.now())])
        can2 = me.has_perm('members:invite')
        note2 = ('%s دعوت همکار در انتظار پذیرش است.' % ws.ts_fa_num(pending)) if pending else (None if can2 else NOT_YOURS)
        add('counselors', 'دعوت مشاوران', 'مشاوران با حساب خودشان مراجعان را دعوت می‌کنند و گزارش ویژهٔ مشاور را می‌بینند.',
            staff, url=(base + '/members#tsp-invite') if can2 else None, btn='دعوت همکار', note=note2, way=bool(pending))

        if prepaid:
            # 3. credit: the panel can hold the price of an invitation. Credit is added only by an invoice the EOT team
            #    issues, so the button asks for it (contact form, topic «شارژ اعتبار پنل», panel code filled in).
            available = env['ts.wallet']._for_workspace(ws).ts_available()
            balance = 'موجودی: %s.' % ws.ts_toman(available)
            add('credit', 'اعتبار پنل', 'هر دعوت هزینهٔ خود را از اعتبار پنل رزرو می‌کند؛ بدون اعتبار، دعوت فرستاده نمی‌شود.',
                available > 0, url=ws.ts_contact_url('credit') if me.has_perm('credits:read') else None, btn='درخواست شارژ اعتبار',
                note=balance if available > 0 else balance + ' شارژ اعتبار با فاکتوری است که تیم استعدادیاب صادر می‌کند.',
                keep_note=True)

        # 4. each counselor's catalog. RULE (explainable in one sentence on the help page): done when the panel has exactly
        #    one active counselor (role clinician; there is nothing to divide, the panel catalog is theirs), or when every
        #    active counselor has a catalog decision on record: a restriction (catalog_restricted or a non-empty list), or
        #    the catalog form of their member page saved at least once (ts_catalog_seen_on, set by ts_set_catalog even when
        #    nothing changed: «همهٔ موارد پنل» kept on purpose). No counselor yet = not done, nothing to decide before step 2.
        clin = me._ts_onb_clinicians()
        undecided = clin.filtered(lambda m: not self._ts_catalog_decided(m))
        done3 = len(clin) == 1 or (len(clin) > 1 and not undecided)
        can3 = me.has_perm('catalog:assign') and me.has_perm('members:read')
        if not clin:
            note3 = 'پس از پیوستن نخستین مشاور.'
        elif not can3:
            note3 = NOT_YOURS
        else:
            note3 = '%s از %s مشاور بررسی شده است.' % (ws.ts_fa_num(len(clin) - len(undecided)), ws.ts_fa_num(len(clin)))
        add('catalog', 'سنجه‌های هر مشاور', 'برای هر مشاور تعیین کنید به کدام سنجه‌ها و مجموعه‌ها دعوت کند؛ پیش‌فرض، همهٔ موارد پنل است.',
            done3, url=('%s/members/%d#tsp-catalog' % (base, undecided[:1].id)) if (can3 and undecided) else None,
            btn='تعیین سنجه‌های مشاور', note=note3)

        if prepaid:
            # 5. monthly caps (optional): any cap set on a capped role, or «بدون سقف بماند» recorded once
            capped = env['ts.workspace.member'].sudo().search_count(
                [('workspace_id', '=', ws.id), ('active', '=', True), ('role', 'in', list(CAPPED_ROLES)), ('monthly_cap', '>', 0)])
            can4 = me.has_perm('credits:manage')
            add('caps', 'سقف ماهانهٔ مشاوران', 'سقف، هزینهٔ دعوت‌های هر مشاور را در یک ماه شمسی محدود می‌کند.',
                capped or ws.ts_onb_nocap_on, url=(base + '/credits#tsb-caps') if (can4 and clin) else None,
                btn='تعیین سقف', note=(None if clin else 'پس از پیوستن نخستین مشاور.') if can4 else NOT_YOURS,
                optional=True, nocap=can4)

        # 6. the first invitation of a participant (a self-shared result is not an invitation)
        invited = env['ts.assignment'].sudo().search_count([('workspace_id', '=', ws.id), ('channel', '!=', 'self_share')])
        can6 = me.can_act() and me.has_perm('invites:create')
        add('invite', 'نخستین دعوت', 'مراجع پیوند دعوت را می‌گیرد؛ پس از تکمیل، گزارش او در پنل دیده می‌شود.', invited,
            url=(base + '/invites/new?fresh=1') if (can6 and not ws.gated) else None, btn='دعوت تازه',
            note='پس از تأیید پنل، دعوت فرستاده می‌شود.' if ws.gated else None)

        # numbering (the help section uses the same order) and the one current step: the first open, required step that
        # has something to press. Only that step gets the primary button.
        current = next((s for s in steps if s['state'] == 'open' and not s['optional'] and s['url']), None)
        for i, s in enumerate(steps, 1):
            s['n'] = i
            s['current'] = s is current
        return steps

    def ts_onb_status(self):
        """The two set-up conditions the EOT team controls, shown under the progress as status lines (not tasks):
        [{key, label, value, ok, url, link}]. The link opens the contact form with the panel code filled in."""
        self.ensure_one()
        ws = self.sudo().workspace_id
        ask = ws.ts_contact_url('support')
        out = [{'key': 'approval', 'label': 'تأیید پنل', 'ok': not ws.gated,
                'value': 'انجام شد' if not ws.gated else 'در انتظار تیم استعدادیاب',
                'url': None if not ws.gated else ask, 'link': 'پیگیری تأیید پنل'}]
        staff = self.env['ts.workspace.member'].sudo().search(
            [('workspace_id', '=', ws.id), ('active', '=', True), ('role', 'in', list(STAFF_ROLES))])
        if staff:
            ok_n = len(staff.filtered(lambda m: m.verification_state == 'verified'))
            out.append({'key': 'licences', 'label': 'پروانهٔ مشاوران', 'ok': ok_n == len(staff),
                        'value': '%s از %s تأییدشده' % (ws.ts_fa_num(ok_n), ws.ts_fa_num(len(staff))),
                        'url': None if ok_n == len(staff) else ask, 'link': 'پیگیری تأیید پروانه'})
        return out

    def ts_onb_checklist(self):
        """What the dashboard shows: None (not for this member, hidden, or every step done) or
        {'steps', 'done_n', 'total', 'open_n', 'help_url'}."""
        self.ensure_one()
        if not self.ts_onb_applies():
            return None
        steps = self.ts_onb_steps()
        done_n = sum(1 for s in steps if s['done'])
        if done_n == len(steps):
            return None
        return {'steps': steps, 'done_n': done_n, 'total': len(steps), 'open_n': len(steps) - done_n, 'help_url': HELP_URL,
                'open': [s for s in steps if not s['done']], 'done': [s for s in steps if s['done']],
                'status': self.ts_onb_status()}

    def ts_onb_set_hidden(self, by, hidden):
        """«بعداً نشانم نده» / «نمایش دوباره»: each member decides for themselves only."""
        self.ensure_one()
        if by != self or not self.active:
            raise UserError('هر عضو فقط فهرست راه‌اندازی خودش را پنهان یا نمایان می‌کند.')
        self.sudo().ts_onb_hidden_on = fields.Datetime.now() if hidden else False
        return True

    # ------------------------------------------------------------------ counselor first-run card
    def ts_onb_card(self):
        """True when a counselor of a running counseling-center panel has no title on reports yet and has not closed the card."""
        self.ensure_one()
        m = self.sudo()
        ws = m.workspace_id
        return bool(m.active and m.role == 'clinician' and ws.purpose == 'clinical' and ws.state in ('pilot', 'active')
                    and ws.ts_brand_enabled() and not clean_line(m.title) and not m.ts_onb_card_hidden_on)

    def ts_onb_card_hide(self, by):
        self.ensure_one()
        if by != self or not self.active:
            raise UserError('این یادآوری را فقط خود عضو می‌بندد.')
        self.sudo().ts_onb_card_hidden_on = fields.Datetime.now()
        return True

    # ------------------------------------------------------------------ step 3 marker
    def ts_set_catalog(self, by, restricted, instrument_ids=(), battery_ids=()):
        """ts_battery's member catalog form; a successful save (changed or not) is the decision step 3 counts."""
        changed = super().ts_set_catalog(by, restricted, instrument_ids, battery_ids)
        self.sudo().ts_catalog_seen_on = fields.Datetime.now()
        return changed
