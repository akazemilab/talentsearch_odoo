import re

from markupsafe import escape

from odoo import http
from odoo.http import request

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MOBILE_RE = re.compile(r'^(\+98|0098|98|0)?9\d{9}$')
PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
TOPICS = {
    'demo': 'جلسهٔ معرفی',
    'pro': 'خبرم کنید: همیار تفسیر',
    'question': 'پرسش',
    'support': 'پشتیبانی',
    'partner': 'سازمان یا کلینیک',
    # older form values, still accepted
    'quote': 'درخواست پیش‌فاکتور',
    'evidence': 'پرسش دربارهٔ شواهد',
    'other': 'موضوع دیگر',
}
SEGMENTS = {'employer': 'سازمان / منابع انسانی', 'clinic': 'مرکز مشاوره یا درمان',
            'practitioner': 'متخصص مستقل', 'participant': 'شرکت‌کننده', 'other': 'سایر'}


def _split_contact(post):
    """The 2026-10 form has one «ایمیل یا موبایل» field (`contact`); older posts send `email` / `phone`."""
    email = (post.get('email') or '').strip()[:160]
    phone = (post.get('phone') or '').strip()[:40]
    contact = (post.get('contact') or '').strip()[:160]
    if contact:
        if EMAIL_RE.match(contact):
            email = email or contact
        else:
            digits = re.sub(r'[\s\-()]', '', contact.translate(PERSIAN_DIGITS))
            if MOBILE_RE.match(digits):
                phone = phone or digits
    return email, phone


class TsWebsite(http.Controller):

    @http.route('/ts/lead', type='http', auth='public', methods=['POST'], website=True, sitemap=False)
    def ts_lead(self, **post):
        website = request.env.website
        if not website._ts_is_current():
            raise request.not_found()
        name = (post.get('name') or '').strip()[:120]
        email, phone = _split_contact(post)
        topic = post.get('topic') if post.get('topic') in TOPICS else 'demo'
        if not name or not (EMAIL_RE.match(email) or phone) or post.get('consent_contact') != '1':
            return request.redirect('/contact?topic=%s&error=1' % topic)
        segment = SEGMENTS.get(post.get('segment') or '', '')
        lines = [
            ('موضوع', TOPICS[topic]), ('نوع مجموعه', segment), ('مدرسه یا مرکز', post.get('company')),
            ('تعداد کارکنان', post.get('size')), ('سنجش سالانهٔ تقریبی', post.get('volume')), ('نقش‌ها یا کاربرد', post.get('roles')),
            ('رضایت تماس', 'بله'), ('دریافت اخبار', 'بله' if post.get('consent_news') == '1' else 'خیر'),
        ]
        desc = ''.join('<p><b>%s:</b> %s</p>' % (k, _esc(v)) for k, v in lines if v)
        desc += '<p>%s</p>' % _esc((post.get('message') or '')[:3000]).replace('\n', '<br/>')
        team = request.env.ref('ts_website.crm_team_ts', raise_if_not_found=False)
        tag = request.env.ref('ts_website.crm_tag_ts', raise_if_not_found=False)
        lead = request.env['crm.lead'].sudo().create({
            'name': '%s - %s' % (TOPICS[topic], (post.get('company') or name)[:80]),
            'contact_name': name,
            'email_from': email if EMAIL_RE.match(email) else False,
            'phone': phone,
            'partner_name': (post.get('company') or '').strip()[:160],
            'description': desc,
            'type': 'lead',
            'team_id': team.id if team else False,
            'tag_ids': [(6, 0, tag.ids)] if tag else False,
        })
        request.env['ts.audit.event'].sudo().log('lead.web', lead, topic=topic,
                                                 consent_contact=True, consent_news=post.get('consent_news') == '1')
        return request.redirect('/contact/thanks')


def _esc(value):
    return str(escape(value or ''))


from odoo.addons.account.controllers.portal import PortalAccount  # noqa: E402


class TsPortalAccount(PortalAccount):
    """Installing Invoicing (for Talent Search) added an electronic-invoice
    format selector (France FacturX, Peppol, XRechnung, ...) to every
    signed-in user's /my/account, eot.ir's included. None of these formats
    apply in Iran: hide the selector on every website."""

    def _prepare_my_account_rendering_values(self, *args, **kwargs):
        values = super()._prepare_my_account_rendering_values(*args, **kwargs)
        values['invoice_edi_formats'] = {}
        return values
