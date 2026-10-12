"""Every Talent Search SMS from a native `sms.template` (docs/clinic/01_architecture.md section 6, texts and rules in
docs/clinic/05_sms_texts.md).

`env['ts.brand'].sms_render(xmlid, record, values)` renders the template body with Odoo's inline-template engine and falls
back to the hard-coded text of the calling module (with the short link) when the template is missing, empty or fails.
Rules enforced here: lines trimmed and empty lines dropped, so the link stays last and alone (rule 2); Latin digits become
Persian outside the link (rule 3; OTP keeps its Latin code); over 2 parts (134 characters) the counselor clause, then the
battery minutes, then the deadline are dropped, then the template's `<xmlid>_short` sibling is used (rule 6). Variables are
the `ts_sms_*` fields below (non-stored, context-dependent); none of them is a participant's name or a result word (rule 1).
"""
import logging
import sys
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import SUPERUSER_ID, api, fields, models

from odoo.addons.ts_billing.tools import fmt_toman, rial_int
from odoo.addons.ts_org.models.panel import ROLE_LABELS, norm_phone
from odoo.addons.ts_website.tools import MONTHS, gregorian_to_jalali

from .brand import clean_line
from .short import site_base

_logger = logging.getLogger(__name__)
TEHRAN = ZoneInfo('Asia/Tehran')
UTC = ZoneInfo('UTC')
PART1, PART2 = 70, 134          # UCS-2: 70 characters for one part, 67 per part when split
DROPS = ((), ('counselor',), ('counselor', 'minutes'), ('counselor', 'minutes', 'deadline'))
_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa(value):
    return str(value).translate(_FA)


def sms_parts(body):
    """Parts of a UCS-2 SMS (any Persian letter makes the whole message UCS-2)."""
    n = len(body or '')
    if n <= PART1:
        return 1 if n else 0
    return int(math.ceil(n / 67.0))


def clean_body(body, latin_ok=False):
    """Trim every line, drop empty lines (the link becomes the last line, alone), Persian digits outside links."""
    lines = [ln.strip() for ln in (body or '').replace('\r', '').split('\n')]
    lines = [ln for ln in lines if ln]
    if not latin_ok:
        lines = [ln if ln.startswith('http') else ln.translate(_FA) for ln in lines]
    return '\n'.join(lines)


def jalali_day(d, today=None):
    """date -> «۲۵ مهر» (+ year when not the current Jalali year), rule 8."""
    if not d:
        return ''
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    now = today or datetime.now(UTC).astimezone(TEHRAN).date()
    cy = gregorian_to_jalali(now.year, now.month, now.day)[0]
    return fa('%d %s' % (jd, MONTHS[jm - 1]) + ('' if jy == cy else ' %d' % jy))


def jalali_month_key(now=None):
    now = (now or datetime.now(UTC)).astimezone(TEHRAN)
    jy, jm, _ = gregorian_to_jalali(now.year, now.month, now.day)
    return '%04d-%02d' % (jy, jm)


class TsBrand(models.AbstractModel):
    _name = 'ts.brand'
    _description = 'Talent Search branding and SMS helpers'

    @api.model
    def sms_template(self, xmlid):
        tpl = self.env.ref(xmlid, raise_if_not_found=False)
        return tpl.sudo() if tpl and tpl._name == 'sms.template' else None

    @api.model
    def _sms_render_once(self, tpl, record, values):
        # the engine browses `object` in its own env: render from the record's env so its context (ts_sms_drop,
        # ts_sms_link) reaches the ts_sms_* fields
        ctx = dict(record.env.context)
        ctx.update(values or {})
        add = dict(values or {}, ctx=ctx)
        out = record.env['mail.render.mixin'].sudo()._render_template(
            tpl.body, tpl.model, [record.id], engine='inline_template', add_context=add)
        return out.get(record.id) or ''

    @api.model
    def sms_render(self, xmlid, record, values=None, fallback=None, latin_ok=False):
        """Body of one SMS from the template `xmlid` bound to `record` (rules 2, 3, 6 applied). `values` are extra template
        variables, also readable as ctx.get(...). `fallback`: text or callable used when the template is missing, empty or
        fails to render. Never raises."""
        def fb():
            try:
                text = fallback() if callable(fallback) else (fallback or '')
            except Exception:
                _logger.exception('ts_brand: SMS fallback for %s failed', xmlid)
                text = ''
            return clean_body(text, latin_ok=latin_ok)

        tpl = self.sms_template(xmlid)
        if not tpl or not (tpl.body or '').strip() or not record:
            return fb()
        body = ''
        try:
            for drop in DROPS:
                body = clean_body(self._sms_render_once(tpl, record.with_context(ts_sms_drop=drop), values), latin_ok=latin_ok)
                if len(body) <= PART2:
                    break
            if len(body) > PART2:
                short = self.sms_template(xmlid + '_short')
                if short and (short.body or '').strip():
                    body = clean_body(self._sms_render_once(short, record.with_context(ts_sms_drop=DROPS[-1]), values),
                                      latin_ok=latin_ok)
        except Exception:
            _logger.warning('ts_brand: SMS template %s could not be rendered (%s); the fallback text is used', xmlid,
                            str(sys.exc_info()[1])[:200])
            return fb()
        if not body:
            return fb()
        if len(body) > PART2:
            _logger.warning('ts_brand: SMS %s is %d characters (%d parts); the institution name and the link are never cut',
                            xmlid, len(body), sms_parts(body))
        else:
            _logger.info('ts_brand: SMS %s, %d characters, %d part(s)', xmlid, len(body), sms_parts(body))
        return body


# ====================================================================== template variables (rule 1: no names, no results)
class TsAssignmentSms(models.Model):
    _inherit = 'ts.assignment'

    ts_sms_org = fields.Char(compute='_compute_ts_sms')
    ts_sms_counselor = fields.Char(compute='_compute_ts_sms')
    ts_sms_deadline = fields.Char(compute='_compute_ts_sms')
    ts_sms_link = fields.Char(compute='_compute_ts_sms')
    ts_sms_count = fields.Char(compute='_compute_ts_sms')
    ts_sms_minutes = fields.Char(compute='_compute_ts_sms')

    @api.depends_context('ts_sms_drop', 'ts_sms_link')
    def _compute_ts_sms(self):
        drop = self.env.context.get('ts_sms_drop') or ()
        for a in self:
            s = a.sudo()
            ws = s.workspace_id
            a.ts_sms_org = fa(ws.ts_sms_sender()) if ws else ''
            counselor = ''
            if 'counselor' not in drop and ws and ws.ts_brand_enabled():
                m = ws.ts_brand_member(s)
                if m and m.show_on_report:
                    counselor = fa(clean_line(m.user_id.name))
            a.ts_sms_counselor = counselor
            a.ts_sms_deadline = '' if 'deadline' in drop else jalali_day(s.deadline)
            a.ts_sms_link = self.env.context.get('ts_sms_link') or (s.ts_short_url() if s.id else '')
            bat = s.battery_id if 'battery_id' in s._fields else False
            a.ts_sms_count = fa(len(bat.line_ids)) if bat else ''
            a.ts_sms_minutes = fa(bat.est_minutes) if (bat and bat.est_minutes and 'minutes' not in drop) else ''

    def _ts_sms_is_student(self):
        """The «تو» texts only in an education panel and only when the number on file is the student's own (rule 9)."""
        self.ensure_one()
        s = self.sudo()
        if s.purpose != 'education' or s.instrument_id.audience == 'child':
            return False
        c = s.client_id if 'client_id' in s._fields else False
        phone = norm_phone(s.invitee_phone)
        if not c or not phone or c.account_is_guardian:
            return False
        if c.guardian_phone and norm_phone(c.guardian_phone) == phone:
            return False
        return bool(c.phone) and norm_phone(c.phone) == phone

    def _ts_invite_template(self):
        self.ensure_one()
        if self._ts_sms_is_student():
            return 'ts_brand.sms_invite_student'
        return 'ts_brand.sms_invite_battery' if self.battery_id else 'ts_brand.sms_invite_single'

    def _ts_invite_sms_body(self):
        self.ensure_one()
        return self.env['ts.brand'].sms_render(
            self._ts_invite_template(), self,
            fallback=lambda: super(TsAssignmentSms, self.with_context(ts_sms_short=True))._ts_invite_sms_body())

    def _ts_reminder_sms_body(self):
        self.ensure_one()
        return self.env['ts.brand'].sms_render(
            'ts_brand.sms_reminder', self,
            fallback=lambda: super(TsAssignmentSms, self.with_context(ts_sms_short=True))._ts_reminder_sms_body())


class TsAttemptSms(models.Model):
    _inherit = 'ts.attempt'

    ts_sms_you = fields.Char(compute='_compute_ts_sms')
    ts_sms_link = fields.Char(compute='_compute_ts_sms')

    @api.depends_context('ts_sms_link')
    def _compute_ts_sms(self):
        base = site_base(self.env)
        for at in self:
            s = at.sudo()
            client = s.client_id if 'client_id' in s._fields else False
            informal = s.ts_informal() if s.id else False
            at.ts_sms_you = 'تو' if (informal and not (client and client.account_is_guardian)) else 'شما'
            at.ts_sms_link = self.env.context.get('ts_sms_link') or base + '/my/assessments'

    def _ts_result_sms_body(self):
        self.ensure_one()
        return self.env['ts.brand'].sms_render(
            'ts_brand.sms_result_ready_client', self,
            fallback=lambda: super(TsAttemptSms, self)._ts_result_sms_body())


class TsWorkspaceSms(models.Model):
    _inherit = 'ts.workspace'

    ts_sms_link = fields.Char(compute='_compute_ts_sms_link')

    @api.depends_context('ts_sms_link')
    def _compute_ts_sms_link(self):
        base = site_base(self.env)
        for ws in self:
            ws.ts_sms_link = self.env.context.get('ts_sms_link') or '%s/my/workspaces/%s' % (base, ws.id)


class TsWalletSms(models.Model):
    _inherit = 'ts.wallet'

    ts_sms_available = fields.Char(compute='_compute_ts_sms')
    ts_sms_link = fields.Char(compute='_compute_ts_sms')

    @api.depends_context('ts_sms_link')
    def _compute_ts_sms(self):
        base = site_base(self.env)
        for w in self:
            w.ts_sms_available = fmt_toman(w.sudo().ts_available()) if w.id else ''
            w.ts_sms_link = self.env.context.get('ts_sms_link') or '%s/my/workspaces/%s/credits' % (base, w.workspace_id.id)


class TsMemberSms(models.Model):
    _inherit = 'ts.workspace.member'

    ts_sms_cap = fields.Char(compute='_compute_ts_sms')
    ts_sms_panel_short = fields.Char(compute='_compute_ts_sms')
    ts_sms_link = fields.Char(compute='_compute_ts_sms')

    @api.depends_context('ts_sms_link')
    def _compute_ts_sms(self):
        base = site_base(self.env)
        for m in self:
            m.ts_sms_cap = fmt_toman(rial_int(m.sudo().monthly_cap))
            m.ts_sms_panel_short = fa(m.sudo().workspace_id.ts_sms_sender())
            m.ts_sms_link = self.env.context.get('ts_sms_link') or '%s/my/workspaces/%s/credits' % (base, m.workspace_id.id)

    def _ts_cap_reached_notify(self):
        """cap_reached (05_sms_texts.md section 8): in-app row + SMS leg (staff switch, the person's opt-in, quiet hours: the
        usual dispatcher), at most once per member per Jalali month."""
        N = self.env['ts.notification'].sudo()
        month = jalali_month_key()
        sent = 0
        for m in self.sudo():
            if not m.active or m.cap_alert_month == month:
                continue
            m.cap_alert_month = month
            row = N._notify(m.user_id, 'cap_reached', '/my/workspaces/%s/credits' % m.workspace_id.id, m.workspace_id)
            sent += bool(row)
            self.env['ts.audit.event'].sudo().log('credit.cap_notice', m, workspace=m.workspace_id, member=m, month=month)
        return sent


class TsMemberInviteSms(models.Model):
    _inherit = 'ts.member.invite'

    ts_sms_org = fields.Char(compute='_compute_ts_sms')
    ts_sms_role = fields.Char(compute='_compute_ts_sms')
    ts_sms_link = fields.Char(compute='_compute_ts_sms')

    @api.depends_context('ts_sms_link')
    def _compute_ts_sms(self):
        for i in self:
            s = i.sudo()
            i.ts_sms_org = fa(s.workspace_id.ts_sms_sender())
            i.ts_sms_role = ROLE_LABELS.get(s.role, '')
            i.ts_sms_link = self.env.context.get('ts_sms_link') or (s.ts_short_url() if s.id else '')

    def ts_member_invite_sms_body(self):
        """Text of a colleague-invitation SMS (template member_invite). Nothing sends it today: the panel shares the link
        itself (owner decision 2026-10-11); a future explicit «send by SMS» button uses this body."""
        self.ensure_one()
        return self.env['ts.brand'].sms_render(
            'ts_brand.sms_member_invite', self,
            fallback=lambda: '%s\nشما را با نقش «%s» به پنل ما در استعدادیاب دعوت کرده‌ایم.\n%s' % (
                self.sudo().workspace_id.ts_sms_sender(), ROLE_LABELS.get(self.role, ''), self.sudo().ts_short_url()))


# ====================================================================== staff notices (ts.notification SMS leg)
def _notice_record(row):
    """(xmlid, record bound to the template) of a staff notice, or (None, None)."""
    t, ws = row.type, row.workspace_id
    if t == 'result_ready_staff':
        return 'ts_brand.sms_result_ready_staff', row
    if t in ('panel_approved', 'panel_rejected', 'panel_suspended') and ws:
        return 'ts_brand.sms_' + t, ws
    if t == 'low_balance' and ws:
        return 'ts_brand.sms_low_balance', row.env['ts.wallet'].sudo()._for_workspace(ws)
    if t == 'cap_reached' and ws:
        m = row.env['ts.workspace.member'].sudo().search(
            [('workspace_id', '=', ws.id), ('user_id', '=', row.user_id.id), ('active', '=', True)], limit=1)
        return ('ts_brand.sms_cap_reached', m) if m else (None, None)
    return None, None


class TsNotificationSms(models.Model):
    _inherit = 'ts.notification'

    ts_sms_link = fields.Char(compute='_compute_ts_sms_link')

    def _compute_ts_sms_link(self):
        base = site_base(self.env)
        for row in self:
            row.ts_sms_link = '%s/n/%s' % (base, row.id) if row.id else base

    def _ts_sms_body(self):
        """The SMS of a staff notice: its template, with the notice's own short link /n/<id> (the page behind it checks the
        reader again)."""
        self.ensure_one()
        xmlid, rec = _notice_record(self.sudo())
        if not xmlid:
            return super()._ts_sms_body()
        link = self.ts_sms_link
        return self.env['ts.brand'].sms_render(xmlid, rec.with_context(ts_sms_link=link),
                                               fallback=lambda: self._ts_sms_fallback(link))

    def _ts_sms_fallback(self, link):
        from odoo.addons.ts_panel.models.notify_texts import SMS_BODIES
        ws = self.sudo().workspace_id
        amount = ''
        if self.type == 'low_balance' and ws:
            amount = fmt_toman(self.env['ts.wallet'].sudo()._for_workspace(ws).ts_available())
        elif self.type == 'cap_reached' and ws:
            m = self.env['ts.workspace.member'].sudo().search(
                [('workspace_id', '=', ws.id), ('user_id', '=', self.user_id.id)], limit=1)
            amount = fmt_toman(rial_int(m.monthly_cap)) if m else ''
        return SMS_BODIES.get(self.type, '%(url)s') % {'url': link, 'panel': ws.name or '', 'amount': amount}


# ====================================================================== OTP (plain SMS path; the Kavenegar lookup stays)
class TsPhoneOtpSms(models.Model):
    _inherit = 'ts.phone.otp'

    @api.model
    def _ts_otp_body(self, code, phone=None):
        from odoo.addons.ts_sms.models.phone_otp import TTL_MIN
        signup = self.env.context.get('ts_otp_kind') == 'signup'
        model = 'ts.signup.otp' if signup else 'ts.phone.otp'
        rec = self.env[model].sudo().search([('phone', '=', phone)], limit=1) if phone else self.env[model]
        return self.env['ts.brand'].sms_render(
            'ts_brand.sms_otp_signup' if signup else 'ts_brand.sms_otp_phone', rec,
            values={'code': code, 'minutes': fa(TTL_MIN)}, latin_ok=True,
            fallback=lambda: super(TsPhoneOtpSms, self)._ts_otp_body(code, phone))


class TsSignupOtpSms(models.Model):
    _inherit = 'ts.signup.otp'

    @api.model
    def request_code(self, phone_raw, ip=None):
        return super(TsSignupOtpSms, self.with_context(ts_otp_kind='signup')).request_code(phone_raw, ip=ip)


# ====================================================================== cap refusal -> cap_reached (after commit)
class TsWalletCapNotice(models.Model):
    _inherit = 'ts.wallet'

    @api.model
    def _ts_on_refused(self, err):
        """A cap refusal tells the counselor once a month. The refusal itself runs inside savepoints that are rolled back
        (and a campaign logs the same refusal twice), so the notice is sent once, after the request's transaction commits."""
        super()._ts_on_refused(err)
        try:
            member = getattr(err, 'ts_member', None)
            if getattr(err, 'ts_kind', None) != 'cap' or not member:
                return None
            cr = self.env.cr
            pending = cr.postcommit.data.setdefault('ts_brand.cap_reached', set())
            if not pending:
                registry = self.env.registry

                @cr.postcommit.add
                def _send_cap_notices():
                    with registry.cursor() as cr2:
                        env = api.Environment(cr2, SUPERUSER_ID, {})
                        env['ts.workspace.member'].browse(sorted(pending)).exists()._ts_cap_reached_notify()
            pending.add(member.id)
        except Exception:
            _logger.exception('ts_brand: cap notice could not be scheduled')
        return None
