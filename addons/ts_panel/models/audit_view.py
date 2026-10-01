"""The panel audit page (S14, AUD-3, AUD-4, EXP-4; 02_feature_catalog.md).

Every audit `event_type` belongs to a family and has one Persian sentence. An unknown type falls back to «رویداد دیگر», so a new
event never breaks the page. Names are resolved when the page is drawn, for the owner who looks (owners may see all clients), and
only for the events of the owner's own panel.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import SUPERUSER_ID, api, models

from odoo.addons.ts_assessment.models.attempt import jalali
from odoo.addons.ts_org.models.panel import ROLE_LABELS

TEHRAN = ZoneInfo('Asia/Tehran')
UTC = ZoneInfo('UTC')
PAGE = 50
EXPORT_MAX = 5000

FAMILIES = [('access', 'ورود و دسترسی'), ('members', 'اعضا'), ('clients', 'مراجعان'), ('invites', 'دعوت‌ها'),
            ('results', 'نتایج'), ('exports', 'خروجی‌ها'), ('settings', 'تنظیمات'), ('support', 'پشتیبانی')]
OTHER = ('other', 'رویداد دیگر')

# event_type -> (family, sentence). {who} = the person who acted, {obj} = the participant the event is about (may be empty).
EVENTS = {
    'account.login_phone': ('access', '{who} با موبایل وارد شد'),
    'account.signup_phone': ('access', '{who} با موبایل ثبت‌نام کرد'),
    'auth.reauth': ('access', '{who} هویت خود را دوباره تأیید کرد'),
    'auth.reauth_fail': ('access', 'تأیید دوبارهٔ هویت {who} ناموفق بود'),
    'authz.deny': ('access', 'دسترسی {who} به یک صفحه رد شد'),
    'member.add': ('members', '{who} عضوی را افزود'),
    'member.change': ('members', '{who} نقش یا وضعیت یکی از اعضا را تغییر داد'),
    'member.invite': ('members', '{who} همکاری را دعوت کرد'),
    'member.invite_accept': ('members', '{who} دعوت همکاری را پذیرفت'),
    'member.invite_resend': ('members', '{who} دعوت یک همکار را دوباره فرستاد'),
    'member.invite_revoke': ('members', '{who} دعوت یک همکار را لغو کرد'),
    'member.practice': ('members', '{who} نوع فعالیت یکی از اعضا را ثبت کرد'),
    'member.verify': ('members', '{who} صلاحیت حرفه‌ای یکی از اعضا را بررسی کرد'),
    'client.create': ('clients', '{who} شرکت‌کننده‌ای را افزود'),
    'client.edit': ('clients', '{who} اطلاعات {obj} را ویرایش کرد'),
    'client.archive': ('clients', '{who} {obj} را بایگانی کرد'),
    'client.restore': ('clients', '{who} {obj} را از بایگانی درآورد'),
    'client.merge': ('clients', '{who} دو شرکت‌کنندهٔ تکراری را ادغام کرد'),
    'client.auto_link': ('clients', 'سامانه حساب یک شرکت‌کننده را به پروندهٔ او وصل کرد'),
    'client.responsible_change': ('clients', '{who} مسئول {obj} را تغییر داد'),
    'client.handover_request': ('clients', '{who} درخواست واگذاری {obj} را ثبت کرد'),
    'client.handover_decide': ('clients', '{who} دربارهٔ واگذاری {obj} تصمیم گرفت'),
    'attempt.responsible_change': ('clients', '{who} مسئول {obj} را تغییر داد'),
    'assignment.responsible_change': ('clients', '{who} مسئول {obj} را تغییر داد'),
    'import.run': ('clients', '{who} فایل شرکت‌کنندگان را وارد کرد'),
    'assignment.create': ('invites', '{who} برای {obj} دعوتی فرستاد'),
    'assignment.accept': ('invites', '{obj} دعوت را پذیرفت'),
    'assignment.decline': ('invites', '{obj} دعوت را رد کرد'),
    'assignment.extend': ('invites', '{who} مهلت دعوت {obj} را تمدید کرد'),
    'assignment.withdraw': ('invites', '{who} دعوت {obj} را پس گرفت'),
    'campaign.create': ('invites', '{who} دعوت گروهی ساخت'),
    'campaign.close': ('invites', '{who} دعوت گروهی را بست'),
    'campaign.join': ('invites', '{obj} از راه پیوند باز پیوست'),
    'campaign.join_try': ('invites', 'تلاشی برای پیوستن از راه پیوند باز ثبت شد'),
    'notify.reminder': ('invites', 'یادآوری دعوت برای {obj} فرستاده شد'),
    'notify.send': ('invites', 'یک اعلان فرستاده شد'),
    'assignment.result_view': ('results', '{who} نتیجهٔ {obj} را دید'),
    'attempt.result_view': ('results', '{who} نتیجهٔ {obj} را دید'),
    'result.view': ('results', '{who} نتیجهٔ {obj} را دید'),
    'result.print': ('results', '{who} نتیجهٔ {obj} را چاپ کرد'),
    'report.view': ('results', 'گزارش {obj} دیده شد'),
    'report.group_view': ('results', '{who} گزارش گروهی را دید'),
    'assignment.self_share': ('results', '{obj} نتیجهٔ خود را با پنل به اشتراک گذاشت'),
    'assignment.share_revoke': ('results', '{obj} اشتراک نتیجهٔ خود را لغو کرد'),
    'attempt.consent': ('results', 'رضایت‌نامهٔ یک سنجه پذیرفته شد'),
    'attempt.submit': ('results', 'یک سنجه تکمیل شد'),
    'attempt.void': ('results', '{who} یک سنجهٔ {obj} را باطل کرد'),
    'attempt.score_error': ('results', 'در محاسبهٔ یک نتیجه خطا رخ داد'),
    'export.create': ('exports', '{who} خروجی گرفت'),
    'export.download': ('exports', '{who} فایل خروجی را دانلود کرد'),
    'audit.export': ('exports', '{who} از ممیزی پنل خروجی گرفت'),
    'workspace.create': ('settings', 'پنل ساخته شد'),
    'workspace.self_create': ('settings', '{who} پنل را ساخت'),
    'workspace.profile': ('settings', '{who} مشخصات پنل را تغییر داد'),
    'workspace.state': ('settings', 'وضعیت پنل تغییر کرد'),
    'workspace.approve': ('settings', 'پنل تأیید شد'),
    'workspace.reject': ('settings', 'پنل تأیید نشد'),
    'workspace.suspend': ('settings', 'پنل تعلیق شد'),
    'workspace.resume': ('settings', 'تعلیق پنل برداشته شد'),
    'workspace.terms_accept': ('settings', '{who} شرایط استفاده را پذیرفت'),
    'wallet.grant': ('settings', 'اعتبار پنل افزوده شد'),
    'wallet.adjust': ('settings', 'اعتبار پنل اصلاح شد'),
    'wallet.reconcile_mismatch': ('settings', 'مغایرتی در حساب اعتبار پنل پیدا شد'),
    'job.failed': ('settings', 'یک کار پس‌زمینه ناموفق ماند'),
    'emergency.open': ('support', 'پشتیبانی پلتفرم دسترسی اضطراری باز کرد'),
    'emergency.view': ('support', 'پشتیبانی پلتفرم با دسترسی اضطراری نتایج را دید'),
    'emergency.close': ('support', 'دسترسی پشتیبانی پلتفرم بسته شد'),
    'support.open': ('support', 'پشتیبانی پلتفرم دسترسی پشتیبانی باز کرد'),
}


def family_of(event_type):
    return EVENTS.get(event_type, (OTHER[0], OTHER[1]))[0]


def types_of(family):
    return [t for t, (f, _s) in EVENTS.items() if f == family]


def tehran_day_start(day):
    """A date -> the naive UTC datetime where that Tehran day starts."""
    return datetime.combine(day, time(0, 0), tzinfo=TEHRAN).astimezone(UTC).replace(tzinfo=None)


def parse_day(text):
    try:
        return datetime.strptime((text or '').strip().translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')), '%Y-%m-%d').date()
    except ValueError:
        return None


def clean_filters(kw, members):
    """Whitelisted filters of the audit page. `members` = the panel's members (a member id from outside it is dropped)."""
    out = {}
    d1, d2 = parse_day(kw.get('from')), parse_day(kw.get('to'))
    if d1:
        out['from'] = d1.isoformat()
    if d2:
        out['to'] = d2.isoformat()
    if kw.get('family') in [f for f, _l in FAMILIES] + [OTHER[0]]:
        out['family'] = kw['family']
    if (kw.get('member') or '').isdigit() and int(kw['member']) in members.ids:
        out['member'] = kw['member']
    return out


class TsAuditView(models.AbstractModel):
    _name = 'ts.audit.view'
    _description = 'Talent Search panel audit page'

    @api.model
    def domain(self, ws, f):
        dom = [('workspace_id', '=', ws.id)]
        if f.get('from'):
            dom.append(('create_date', '>=', tehran_day_start(parse_day(f['from']))))
        if f.get('to'):
            dom.append(('create_date', '<', tehran_day_start(parse_day(f['to']) + timedelta(days=1))))
        fam = f.get('family')
        if fam == OTHER[0]:
            dom.append(('event_type', 'not in', list(EVENTS)))
        elif fam:
            dom.append(('event_type', 'in', types_of(fam)))
        if f.get('member'):
            dom.append(('actor_id', '=', self.env['ts.workspace.member'].sudo().browse(int(f['member'])).user_id.id))
        return dom

    @api.model
    def rows(self, ws, f, page=0, limit=PAGE):
        """-> (list of row dicts, total). The newest events first."""
        Ev = self.env['ts.audit.event'].sudo()
        dom = self.domain(ws, f)
        total = Ev.search_count(dom)
        events = Ev.search(dom, limit=limit, offset=page * limit)
        return self._describe(ws, events), total

    @api.model
    def _describe(self, ws, events):
        roles = {m.user_id.id: ROLE_LABELS.get(m.role, m.role) for m in
                 self.env['ts.workspace.member'].sudo().search([('workspace_id', '=', ws.id)])}
        names = {}
        for model in ('ts.assignment', 'ts.attempt', 'ts.panel.client'):
            ids = [e.res_id for e in events if e.res_model == model]
            if ids:
                recs = self.env[model].sudo().search([('id', 'in', ids), ('workspace_id', '=', ws.id)])
                for r in recs:
                    c = r if model == 'ts.panel.client' else r.client_id
                    names[(model, r.id)] = c.name or ''
        out = []
        for e in events:
            fam, sentence = EVENTS.get(e.event_type, (OTHER[0], OTHER[1]))
            who = e.actor_id.name or 'سامانه'
            obj = names.get((e.res_model, e.res_id)) or 'یک شرکت‌کننده'
            text = sentence.replace('{who}', who).replace('{obj}', obj)
            out.append({
                'id': e.id, 'type': e.event_type, 'family': dict(FAMILIES).get(fam, OTHER[1]), 'text': text,
                'when': jalali(e.create_date), 'iso': e.create_date, 'actor': who if e.actor_id else '',
                'role': roles.get(e.actor_id.id, ''), 'outcome': e.outcome, 'detail': e.detail or ''})
        return out

    @api.model
    def support_rows(self, ws):
        """Every support or emergency access ever opened on this panel (SUP-1), newest first."""
        out = []
        for a in self.env['ts.emergency.access'].sudo().search([('workspace_id', '=', ws.id)], limit=100):
            out.append({'id': a.id, 'kind': dict(a._fields['kind'].selection).get(a.kind, a.kind), 'ticket': a.ticket_ref or '',
                        'opened': jalali(a.opened_at), 'expires': jalali(a.expires_at), 'state': dict(a._fields['state'].selection).get(a.state),
                        'reason': a.reason or ''})
        return out

    @api.model
    def viewers(self, ws, attempt):
        """AUD-4: who opened this result, by role and date (no names): [(jalali date, role label)]."""
        Ev = self.env['ts.audit.event'].sudo()
        a = self.env['ts.assignment'].sudo().search([('attempt_id', '=', attempt.id), ('workspace_id', '=', ws.id)], limit=1)
        dom = [('workspace_id', '=', ws.id), ('event_type', 'in', ['assignment.result_view', 'attempt.result_view', 'result.view']),
               '|', '&', ('res_model', '=', 'ts.attempt'), ('res_id', '=', attempt.id),
               '&', ('res_model', '=', 'ts.assignment'), ('res_id', '=', a.id or 0)]
        roles = {m.user_id.id: ROLE_LABELS.get(m.role, m.role) for m in
                 self.env['ts.workspace.member'].sudo().search([('workspace_id', '=', ws.id)])}
        return [(jalali(e.create_date), roles.get(e.actor_id.id, 'عضو سابق')) for e in Ev.search(dom, limit=20)]
