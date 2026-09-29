import re

from odoo import fields, http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_org.controllers.main import TsOrg

from ..models.phone_otp import iran_mobile

MESSAGES = {
    'sent': ('ok', 'کد تأیید پیامک شد و تا ۵ دقیقه معتبر است.'),
    'format': ('warn', 'شمارهٔ موبایل ایران را به شکل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.'),
    'cooldown': ('warn', 'لطفاً یک دقیقه صبر کنید و دوباره کد بخواهید.'),
    'limit': ('warn', 'تعداد درخواست‌ها زیاد بوده است؛ کمی بعد دوباره تلاش کنید.'),
    'send': ('warn', 'ارسال پیامک انجام نشد. کمی بعد دوباره تلاش کنید.'),
    'disabled': ('warn', 'تأیید شمارهٔ موبایل هنوز فعال نشده است.'),
    'verified': ('ok', 'شمارهٔ موبایل شما تأیید شد.'),
    'wrong': ('warn', 'کد درست نیست.'),
    'expired': ('warn', 'مهلت کد تمام شده است؛ کد تازه بخواهید.'),
    'attempts': ('warn', 'تعداد تلاش‌ها بیش از حد بود؛ کد تازه بخواهید.'),
    'none': ('warn', 'ابتدا کد بخواهید.'),
    'saved': ('ok', 'تنظیمات ذخیره شد.'),
    'removed': ('ok', 'شمارهٔ موبایل حذف شد.'),
}


def _enabled():
    c = request.env.company.sudo()
    return bool(c.kv_enabled and c.ts_sms_otp)


class TsSmsController(TsOrg):

    # invitation: optional phone + consent, handled after the stock invite created the record
    @http.route()
    def invite(self, ws_id, **post):
        resp = super().invite(ws_id, **post)
        loc = resp.headers.get('Location', '') if hasattr(resp, 'headers') else ''
        m = re.search(r'[?&]created=(\d+)', loc)
        raw = (post.get('invitee_phone') or '').strip()
        if not (m and raw):
            return resp
        a = request.env['ts.assignment'].sudo().browse(int(m.group(1))).exists()
        if not (a and a.workspace_id.id == ws_id):
            return resp
        phone = iran_mobile(raw)
        if phone and post.get('sms_consent'):
            a.write({'invitee_phone': phone, 'sms_consent': True})
            a._ts_send_invite_sms()
        else:
            a.sms_error = 'شمارهٔ معتبر و تأیید موافقت شرکت‌کننده لازم است'
        return resp

    def _phone_values(self, msg=None, pending=False):
        p = request.env.user.partner_id.sudo()
        phone = p.ts_phone or ''
        return {
            'enabled': _enabled(), 'verified': bool(phone),
            'masked': fa_digits(phone[:4] + '***' + phone[-4:]) if phone else '',
            'opt_results': p.ts_sms_results, 'pending': pending,
            'msg': MESSAGES.get(msg), 'page_name': 'ts_phone',
        }

    @http.route('/my/phone', type='http', auth='user', website=True, sitemap=False)
    def phone(self, msg=None, pending=None, **kw):
        _ts_site_or_404()
        return request.render('ts_sms.phone', self._phone_values(msg, bool(pending)))

    @http.route('/my/phone/send', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def phone_send(self, phone=None, **post):
        _ts_site_or_404()
        ok, reason = request.env['ts.phone.otp'].request_code(request.env.user, phone)
        return request.redirect('/my/phone?msg=%s%s' % ('sent' if ok else reason, '&pending=1' if ok else ''))

    @http.route('/my/phone/verify', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def phone_verify(self, code=None, **post):
        _ts_site_or_404()
        ok, reason, phone = request.env['ts.phone.otp'].verify_code(request.env.user, code)
        if not ok:
            return request.redirect('/my/phone?msg=%s%s' % (reason, '&pending=1' if reason == 'wrong' else ''))
        request.env.user.partner_id.sudo().write({
            'ts_phone': phone, 'ts_phone_verified_at': fields.Datetime.now(), 'ts_sms_results': True})
        return request.redirect('/my/phone?msg=verified')

    @http.route('/my/phone/prefs', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def phone_prefs(self, **post):
        _ts_site_or_404()
        p = request.env.user.partner_id.sudo()
        if p.ts_phone:
            p.ts_sms_results = bool(post.get('results'))
        return request.redirect('/my/phone?msg=saved')

    @http.route('/my/phone/remove', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def phone_remove(self, **post):
        _ts_site_or_404()
        request.env.user.partner_id.sudo().write(
            {'ts_phone': False, 'ts_phone_verified_at': False, 'ts_sms_results': False})
        return request.redirect('/my/phone?msg=removed')
