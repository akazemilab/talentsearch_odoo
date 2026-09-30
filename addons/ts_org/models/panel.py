import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.ts_core.models.workspace import GATED_PURPOSES as GATED, ROLES_BY_PURPOSE

TERMS_VERSION = 'panel-terms-1405-07-v1'
MAX_PANELS_PER_DAY = 3
# what the person picks -> workspace purpose
KINDS = {'school': 'education', 'org': 'employment', 'clinic': 'clinical'}
SOLO_AS = {'counselor': 'education', 'psychologist': 'clinical', 'hr': 'employment'}
ROLE_LABELS = {
    'owner': 'مالک (مدیر اصلی)', 'hr_admin': 'مدیر منابع انسانی', 'hiring_manager': 'مدیر استخدام',
    'clinic_director': 'مدیر درمانگاه', 'clinician': 'متخصص بالینی', 'counselor': 'مشاور',
    'reviewer': 'بازبین', 'school_admin': 'مدیر مدرسه',
}


_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def norm_phone(raw):
    """Iranian mobile in the 09xxxxxxxxx form, else False."""
    d = re.sub(r'\D', '', (raw or '').translate(_DIGITS))
    if d.startswith('0098'):
        d = d[4:]
    elif d.startswith('98') and len(d) == 12:
        d = d[2:]
    if len(d) == 10 and d.startswith('9'):
        d = '0' + d
    return d if re.fullmatch(r'09\d{9}', d) else False


def norm_email(raw):
    e = (raw or '').strip().lower()
    return e if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]{2,}', e) and len(e) <= 200 else False


def role_choices(ws):
    """Roles the owner can hand out in this kind of panel, with readable labels."""
    roles = ROLES_BY_PURPOSE.get(ws.purpose, set())
    return [(r, ROLE_LABELS.get(r, r)) for r in sorted(roles)]


class TsWorkspace(models.Model):
    _inherit = 'ts.workspace'

    @api.model
    def ts_panel_create(self, user, name, kind, solo_as=None, terms=False, escalation_ok=False):
        """Self-service panel: the person becomes owner. Education is active at once; organizations and
        clinics start in the limited «pending approval» mode (panel + colleagues, no real participants)."""
        name = ' '.join((name or '').split())
        if not (2 <= len(name) <= 100):
            raise UserError('نام پنل باید بین ۲ تا ۱۰۰ نویسه باشد.')
        if kind == 'solo':
            purpose = SOLO_AS.get(solo_as)
        else:
            purpose = KINDS.get(kind)
        if not purpose:
            raise UserError('نوع پنل را انتخاب کنید.')
        if not terms:
            raise UserError('برای ساخت پنل باید شرایط استفاده را بپذیرید.')
        if purpose == 'clinical' and not escalation_ok:
            raise UserError('برای پنل بالینی باید مسئولیت پاسخ فوری بالینی را بپذیرید.')
        if not user.share or user._is_public():
            raise UserError('برای ساخت پنل وارد حساب خود شوید.')
        S = self.sudo()
        since = fields.Datetime.now() - timedelta(days=1)
        if self.env['ts.workspace.member'].sudo().search_count(
                [('user_id', '=', user.id), ('role', '=', 'owner'), ('create_date', '>=', since)]) >= MAX_PANELS_PER_DAY:
            raise UserError('در ۲۴ ساعت گذشته چند پنل ساخته‌اید؛ کمی بعد دوباره تلاش کنید.')
        partner = self.env['res.partner'].sudo().create({'name': name, 'is_company': True})
        partner.write({'is_company': True})  # Odoo recomputes is_company on create (see lessons learned)
        me = user.partner_id
        ws = S.create({
            'name': name, 'purpose': purpose, 'partner_id': partner.id,
            'state': 'pilot' if purpose in GATED else 'active',
            'data_contact_id': me.id,
            'escalation_contact_id': me.id if purpose == 'clinical' else False,
            'terms_version': TERMS_VERSION, 'terms_accepted_on': fields.Datetime.now(),
            'terms_accepted_by_id': user.id,
        })
        self.env['ts.workspace.member'].sudo().create({'workspace_id': ws.id, 'user_id': user.id, 'role': 'owner'})
        audit = self.env['ts.audit.event'].sudo()
        audit.log('workspace.self_create', ws, workspace=ws, purpose=purpose, kind=kind)
        audit.log('workspace.terms_accept', ws, workspace=ws, version=TERMS_VERSION,
                  clinical_escalation=bool(purpose == 'clinical'))
        if ws.gated:
            ws._notify_review()
        return ws

    def _notify_review(self):
        group = self.env.ref('ts_core.group_ts_manager')
        managers = self.env['res.users'].sudo().search([('group_ids', 'in', group.id), ('share', '=', False)])
        for ws in self:
            ws.message_post(
                body='پنل تازه «%s» (%s) ساخته شد و در انتظار تأیید است.' % (
                    ws.name, dict(ws._fields['purpose'].selection).get(ws.purpose)),
                partner_ids=managers.partner_id.ids, message_type='notification', subtype_xmlid='mail.mt_comment')

    def ts_update_profile(self, name=None, logo_bytes=None):
        self.ensure_one()
        vals = {}
        if name is not None:
            name = ' '.join(name.split())
            if not (2 <= len(name) <= 100):
                raise UserError('نام پنل باید بین ۲ تا ۱۰۰ نویسه باشد.')
            vals['name'] = name
        self.sudo().write(vals)
        if vals.get('name'):
            self.partner_id.sudo().write({'name': vals['name']})
        if logo_bytes:
            import base64
            head = logo_bytes[:12]
            if not (head.startswith(b'\x89PNG') or head.startswith(b'\xff\xd8\xff') or (head[:4] == b'RIFF' and head[8:12] == b'WEBP')):
                raise UserError('لوگو باید تصویر PNG، JPG یا WEBP باشد.')
            if len(logo_bytes) > 512 * 1024:
                raise UserError('حجم لوگو باید کمتر از ۵۱۲ کیلوبایت باشد.')
            self.partner_id.sudo().write({'image_1920': base64.b64encode(logo_bytes)})
        self.env['ts.audit.event'].sudo().log('workspace.profile', self, workspace=self, logo=bool(logo_bytes))


