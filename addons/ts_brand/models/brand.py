"""Institution and counselor identity on reports (docs/clinic/01_architecture.md section 5; clinic phase 5).

The institute manages itself: owner / clinic director edit the panel's identity on the settings page (permission
panel:profile, as for the name and logo); each member edits their own title, bio, photo and signature on their member page;
owner / admin / clinic director may set any member's title and «show on report». The licence number is entered and verified
as before (only the platform manager verifies it); a report shows it only when verified.

The report header (screen, print, PDF) is drawn only for attempts of a counseling-center or education panel; a self-taken
attempt outside any panel keeps the plain استعدادیاب header. The counselor block never carries contact data.
"""
import base64
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

BRAND_PURPOSES = ('clinical', 'education')
BRAND_ROLES = ('owner', 'admin', 'clinic_director')      # may edit any member's title / show_on_report
HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
PUBLIC_MAX, SMS_MAX, CONTACT_MAX, TITLE_MAX, BIO_MAX = 100, 18, 80, 40, 160
PHOTO_MAX, SIGNATURE_MAX = 512 * 1024, 300 * 1024
FOOTER_LINE = 'تهیه‌شده با استعدادیاب (از خانوادهٔ هیجان اندیشه)'


def clean_line(text):
    """One line of user text: whitespace collapsed, no control characters."""
    text = ''.join(ch for ch in (text or '') if ch == ' ' or ch.isprintable() or ch == '‌')
    return ' '.join(text.split())


def short_name(text, limit=SMS_MAX):
    """The longest prefix of `text` that ends on a word boundary and fits `limit` (a single long word is cut)."""
    text = clean_line(text)
    if len(text) <= limit:
        return text
    head = text[:limit + 1]
    cut = head.rfind(' ')
    out = (head[:cut] if cut > 0 else text[:limit]).strip()
    while out.endswith(' و') and len(out) > 2:          # never end a sender line on «و» («مرکز مشاوره و»)
        out = out[:-2].strip()
    return out


def image_kind(data):
    head = (data or b'')[:12]
    if head.startswith(b'\x89PNG'):
        return 'png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    return None


def png_data_uri(b64, size=256):
    """A stored image (base64) as a PNG data URI: wkhtmltopdf's WebKit has no WEBP, and the PDF must not fetch anything."""
    if not b64:
        return False
    try:
        from odoo.tools.image import image_process
        raw = base64.b64decode(b64)
        png = image_process(raw, size=(size, size), output_format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(png).decode()
    except Exception:
        _logger.info('ts_brand: image could not be converted for a report header')
        return False


class TsWorkspaceBrand(models.Model):
    _inherit = 'ts.workspace'

    public_name = fields.Char('نام مرکز در گزارش‌ها', help='اگر خالی باشد نام پنل نمایش داده می‌شود.')
    sms_name = fields.Char('نام کوتاه در پیامک', help='حداکثر ۱۸ نویسه؛ سطر اول پیامک‌های دعوت. اگر خالی باشد از نام مرکز '
                                                     'ساخته می‌شود (بریده‌شده سر یک واژه).')
    brand_color = fields.Char('رنگ نشان مرکز', help='#rrggbb؛ فقط خط باریک بالای سربرگ گزارش.')
    contact_line = fields.Char('تلفن یا نشانی وب در گزارش‌ها', help='حداکثر ۸۰ نویسه.')

    @api.constrains('public_name', 'sms_name', 'brand_color', 'contact_line')
    def _check_brand(self):
        for ws in self:
            if ws.public_name and len(ws.public_name) > PUBLIC_MAX:
                raise ValidationError('نام مرکز در گزارش‌ها حداکثر ۱۰۰ نویسه است.')
            if ws.sms_name and len(ws.sms_name) > SMS_MAX:
                raise ValidationError('نام کوتاه پیامک حداکثر ۱۸ نویسه است.')
            if ws.brand_color and not HEX_RE.match(ws.brand_color):
                raise ValidationError('رنگ را به شکل #rrggbb بنویسید، مثلاً #5446a8.')
            if ws.contact_line and len(ws.contact_line) > CONTACT_MAX:
                raise ValidationError('خط تماس حداکثر ۸۰ نویسه است.')

    # ------------------------------------------------------------------ reading
    def ts_brand_enabled(self):
        self.ensure_one()
        return self.purpose in BRAND_PURPOSES

    def ts_public_name(self):
        self.ensure_one()
        return clean_line(self.public_name) or self.name or ''

    def ts_sms_sender(self):
        """Line 1 of an SMS sent on behalf of this panel (05_sms_texts.md rule 7): sms_name, else the public name cut at a
        word boundary to 18 characters."""
        self.ensure_one()
        return clean_line(self.sms_name) or short_name(self.ts_public_name())

    def ts_brand_member(self, assignment=None, attempt=None):
        """The counselor shown on a report: the responsible member of the invitation (or of an imported attempt), else the
        member who invited. An empty recordset when there is none."""
        self.ensure_one()
        M = self.env['ts.workspace.member'].sudo()
        a = assignment.sudo() if assignment else self.env['ts.assignment']
        m = a.responsible_id if a else M
        if not m and attempt is not None and 'responsible_id' in attempt._fields:
            m = attempt.sudo().responsible_id
        if not m and a and a.invited_by_id:
            m = M.search([('workspace_id', '=', self.id), ('user_id', '=', a.invited_by_id.id), ('active', '=', True)], limit=1)
        return m if m and m.workspace_id == self else M

    def ts_brand_header(self, assignment=None, attempt=None):
        """Values of the report header, or False when this panel has none (employment/benefits panels)."""
        self.ensure_one()
        ws = self.sudo()
        if not ws.ts_brand_enabled():
            return False
        m = ws.ts_brand_member(assignment, attempt)
        return {
            'name': ws.ts_public_name(), 'contact': clean_line(ws.contact_line), 'color': ws.brand_color or False,
            'logo': png_data_uri(ws.partner_id.image_256 or ws.partner_id.image_1920),
            'counselor': m.ts_brand_block() if m and m.show_on_report else None,
            'footer': FOOTER_LINE,
        }

    def ts_brand_preview(self, member):
        """Header values for the settings preview: this panel, with the editing member as the sample counselor."""
        self.ensure_one()
        h = dict(self.ts_brand_header() or {'name': self.ts_public_name(), 'contact': '', 'color': False, 'logo': False,
                                             'footer': FOOTER_LINE})
        h['counselor'] = member.ts_brand_block() if member and member.show_on_report else None
        return h

    # ------------------------------------------------------------------ writing (settings page)
    def ts_brand_save(self, by, vals):
        """Owner / clinic director (panel:profile, in a counseling-center or education panel). vals: public_name, sms_name,
        brand_color, contact_line (strings from the form). -> list of changed field names; audit brand.change."""
        self.ensure_one()
        if by.workspace_id != self or not by.has_perm('panel:profile') or not by.ts_brand_manager():
            raise UserError('هویت مرکز را مالک یا مدیر مرکز مشاوره تغییر می‌دهد.')
        new = {
            'public_name': clean_line(vals.get('public_name')) or False,
            'sms_name': clean_line(vals.get('sms_name')) or False,
            'brand_color': (vals.get('brand_color') or '').strip().lower() or False,
            'contact_line': clean_line(vals.get('contact_line')) or False,
        }
        if new['public_name'] and len(new['public_name']) > PUBLIC_MAX:
            raise UserError('نام مرکز در گزارش‌ها حداکثر ۱۰۰ نویسه است.')
        if new['sms_name'] and len(new['sms_name']) > SMS_MAX:
            raise UserError('نام کوتاه پیامک حداکثر ۱۸ نویسه است؛ اکنون %s نویسه است.' % len(new['sms_name']))
        if new['brand_color'] and not HEX_RE.match(new['brand_color']):
            raise UserError('رنگ را به شکل #rrggbb بنویسید، مثلاً #5446a8.')
        if new['contact_line'] and len(new['contact_line']) > CONTACT_MAX:
            raise UserError('خط تماس حداکثر ۸۰ نویسه است.')
        changed = sorted(k for k, v in new.items() if (self[k] or False) != v)
        if changed:
            self.sudo().write({k: new[k] for k in changed})
            self.env['ts.audit.event'].sudo().log('brand.change', self, workspace=self, member=by, fields=changed, scope='panel')
        return changed


class TsMemberBrand(models.Model):
    _inherit = 'ts.workspace.member'

    title = fields.Char('عنوان حرفه‌ای در گزارش‌ها', help='مثلاً «روان‌شناس و مشاور»؛ حداکثر ۴۰ نویسه.')
    report_bio = fields.Char('معرفی کوتاه در گزارش‌ها', help='حداکثر ۱۶۰ نویسه.')
    signature = fields.Binary('تصویر امضا', attachment=True, help='PNG یا JPG، کمتر از ۳۰۰ کیلوبایت.')
    show_on_report = fields.Boolean('نمایش در گزارش‌ها', default=True)
    cap_alert_month = fields.Char('ماه آخرین اعلان سقف', readonly=True, copy=False,
                                  help='ماه شمسی (YYYY-MM) آخرین اعلان «سقف ماهانه پر شد»؛ در هر ماه یک بار.')

    @api.constrains('title', 'report_bio')
    def _check_brand_texts(self):
        for m in self:
            if m.title and len(m.title) > TITLE_MAX:
                raise ValidationError('عنوان حرفه‌ای حداکثر ۴۰ نویسه است.')
            if m.report_bio and len(m.report_bio) > BIO_MAX:
                raise ValidationError('معرفی کوتاه حداکثر ۱۶۰ نویسه است.')

    def ts_brand_manager(self):
        """Owner, admin or clinic director of a counseling-center / education panel who can work in it."""
        self.ensure_one()
        return bool(self.active and self.role in BRAND_ROLES and self.workspace_id.ts_brand_enabled() and self.can_act())

    def ts_license_shown(self):
        self.ensure_one()
        return self.license_number if (self.license_number and self.verification_state == 'verified') else False

    def ts_brand_block(self):
        """The counselor block of a report header: photo, name, title, verified licence, bio, signature. No contact data."""
        self.ensure_one()
        m = self.sudo()
        partner = m.user_id.partner_id
        return {
            'name': m.user_id.name or '', 'title': clean_line(m.title), 'bio': clean_line(m.report_bio),
            'license': m.ts_license_shown(),
            'photo': png_data_uri(partner.image_256 or partner.image_1920, 192),
            'signature': png_data_uri(m.signature, 400),
        }

    def ts_brand_save(self, by, vals, photo=None, signature=None, remove_photo=False, remove_signature=False):
        """Self: title, report_bio, show_on_report, photo (<= 512 KB), signature (<= 300 KB). A brand manager of the same panel:
        title and show_on_report of any member. -> list of changed names; audit brand.change."""
        self.ensure_one()
        own = by == self and self.active
        manager = by.workspace_id == self.workspace_id and by.ts_brand_manager()
        if not self.workspace_id.ts_brand_enabled() or not (own or manager):
            raise UserError('این بخش را خود عضو یا مالک، هماهنگ‌کننده و مدیر مرکز مشاوره تغییر می‌دهند.')
        allowed = {'title', 'show_on_report'} | ({'report_bio', 'photo', 'signature'} if own else set())
        new = {}
        if 'title' in vals:
            new['title'] = clean_line(vals.get('title')) or False
            if new['title'] and len(new['title']) > TITLE_MAX:
                raise UserError('عنوان حرفه‌ای حداکثر ۴۰ نویسه است.')
        if 'show_on_report' in vals:
            new['show_on_report'] = bool(vals.get('show_on_report'))
        if 'report_bio' in vals and 'report_bio' in allowed:
            new['report_bio'] = clean_line(vals.get('report_bio')) or False
            if new['report_bio'] and len(new['report_bio']) > BIO_MAX:
                raise UserError('معرفی کوتاه حداکثر ۱۶۰ نویسه است.')
        changed = sorted(k for k, v in new.items() if (self[k] or False) != v)
        if (photo or remove_photo) and 'photo' not in allowed or (signature or remove_signature) and 'signature' not in allowed:
            raise UserError('عکس و امضا را فقط خود عضو بارگذاری می‌کند.')
        if signature:
            if image_kind(signature) not in ('png', 'jpg'):
                raise UserError('امضا باید تصویر PNG یا JPG باشد.')
            if len(signature) > SIGNATURE_MAX:
                raise UserError('حجم تصویر امضا باید کمتر از ۳۰۰ کیلوبایت باشد.')
            self._ts_check_image(signature)
            new['signature'] = base64.b64encode(signature).decode()
            changed.append('signature')
        elif remove_signature and self.signature:
            new['signature'] = False
            changed.append('signature')
        if new:
            self.sudo().write(new)
        if photo:
            if image_kind(photo) not in ('png', 'jpg', 'webp'):
                raise UserError('عکس باید تصویر PNG، JPG یا WEBP باشد.')
            if len(photo) > PHOTO_MAX:
                raise UserError('حجم عکس باید کمتر از ۵۱۲ کیلوبایت باشد.')
            try:
                with self.env.cr.savepoint():
                    self.user_id.partner_id.sudo().write({'image_1920': base64.b64encode(photo).decode()})
            except Exception:
                raise UserError('این فایل تصویر معتبری نیست.')
            changed.append('photo')
        elif remove_photo and self.user_id.partner_id.image_1920:
            self.user_id.partner_id.sudo().write({'image_1920': False})
            changed.append('photo')
        changed = sorted(set(changed))
        if changed:
            self.env['ts.audit.event'].sudo().log('brand.change', self, workspace=self.workspace_id, member=by, fields=changed,
                                                  scope='self' if by == self else 'member', target=self.id)
        return changed

    @api.model
    def _ts_check_image(self, data):
        try:
            from odoo.tools.image import image_process
            image_process(data, size=(64, 64))
        except Exception:
            raise UserError('این فایل تصویر معتبری نیست.')


class TsAssignmentBrand(models.Model):
    _inherit = 'ts.assignment'

    def ts_brand_header(self):
        self.ensure_one()
        a = self.sudo()
        return a.workspace_id.ts_brand_header(a) if a.workspace_id else False


class TsAttemptBrand(models.Model):
    _inherit = 'ts.attempt'

    def ts_brand_assignment(self):
        self.ensure_one()
        at = self.sudo()
        a = at.assignment_id if 'assignment_id' in at._fields else self.env['ts.assignment']
        return a or self.env['ts.assignment'].sudo().search(
            [('attempt_id', '=', at.id), ('workspace_id', '=', at.workspace_id.id)], limit=1)

    def ts_brand_header(self):
        """Header values for this attempt's report, or False (self-taken outside a panel, or not a branded panel)."""
        self.ensure_one()
        at = self.sudo()
        if not at.workspace_id:
            return False
        return at.workspace_id.ts_brand_header(at.ts_brand_assignment(), at)
