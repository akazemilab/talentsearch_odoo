"""Thin client for the Kavenegar REST API (https://kavenegar.com/rest.html).

Every documented method is wrapped here; nothing in this file touches the
database. The API key travels in the URL path (Kavenegar's design), so it is
never logged: errors are raised with the method name only.
"""
import json
import logging
import re
import time

import requests

_logger = logging.getLogger(__name__)

BASE_URL = 'https://api.kavenegar.com/v1/%s/%s.json'

RETURN_CODES = {
    200: 'تایید شد',
    400: 'پارامترها ناقص هستند',
    401: 'حساب کاربری غیرفعال شده است',
    402: 'عملیات ناموفق بود',
    403: 'کد شناسایی API-Key معتبر نمی‌باشد',
    404: 'متد نامشخص است',
    405: 'متد Get/Post اشتباه است',
    406: 'پارامترهای اجباری خالی ارسال شده اند',
    407: 'دسترسی به اطلاعات مورد نظر برای شما امکان پذیر نیست (نیاز به ثبت IP)',
    409: 'سرور قادر به پاسخگویی نیست، بعدا تلاش کنید',
    411: 'دریافت کننده نامعتبر است',
    412: 'ارسال کننده نامعتبر است',
    413: 'پیام خالی است یا طولانی‌تر از حد مجاز',
    414: 'حجم درخواست بیشتر از حد مجاز است',
    415: 'اندیس شروع بزرگ‌تر از تعداد کل شماره‌هاست',
    416: 'IP سرویس مبدا با تنظیمات مطابقت ندارد',
    417: 'تاریخ ارسال اشتباه است',
    418: 'اعتبار شما کافی نمی‌باشد',
    419: 'طول آرایه‌ها با هم تطابق ندارد',
    420: 'ارسال لینک در این خط محدود شده است',
    422: 'داده حاوی کاراکترهای غیرمجاز است',
    424: 'الگوی مورد نظر پیدا نشد',
    426: 'استفاده از این متد نیازمند سرویس پیشرفته می‌باشد',
    427: 'استفاده از این خط نیازمند سطح دسترسی ویژه است',
    428: 'ارسال کد از طریق تماس ممکن نیست',
    429: 'IP محدود شده است',
    431: 'ساختار کد صحیح نمی‌باشد',
    432: 'پارامتر کد در متن پیام پیدا نشد',
    451: 'فراخوانی بیش از حد در بازه زمانی مجاز',
    501: 'فقط ارسال پیام آزمایشی به شماره صاحب حساب امکان‌پذیر است',
    604: 'تعداد شماره‌ها بیش از حد مجاز است',
    607: 'نام برچسب (tag) معتبر نیست',
}

STATUS_TEXT = {
    1: 'در صف ارسال',
    2: 'زمان‌بندی شده',
    4: 'ارسال شده به مخابرات',
    5: 'ارسال شده به مخابرات',
    6: 'خطا در ارسال',
    10: 'رسیده به گیرنده',
    11: 'نرسیده به گیرنده',
    13: 'لغو شده و اعتبار بازگشت داده شد',
    14: 'مسدود شده (بلک‌لیست) و اعتبار بازگشت داده شد',
    100: 'شناسه نامعتبر',
}
# Kavenegar status -> (sms.sms state, failure type or False)
STATUS_TO_ODOO = {
    1: ('outgoing', False),
    2: ('outgoing', False),
    4: ('pending', False),
    5: ('pending', False),
    6: ('error', 'unknown'),
    10: ('sent', False),
    11: ('error', 'sms_not_delivered'),
    13: ('canceled', False),
    14: ('error', 'sms_blacklist'),
}
FINAL_STATUSES = {6, 10, 11, 13, 14, 100}

CODE_TO_FAILURE = {
    401: 'sms_acc', 403: 'sms_acc', 407: 'kv_ip', 416: 'kv_ip', 429: 'kv_ip',
    409: 'sms_server', 402: 'sms_server',
    411: 'sms_number_format', 418: 'sms_credit',
    412: 'kv_sender', 413: 'kv_message', 420: 'kv_links', 422: 'kv_charset',
    451: 'kv_rate', 501: 'kv_test_only', 426: 'kv_service', 424: 'kv_service',
    427: 'kv_service',
}


class KavenegarError(Exception):
    def __init__(self, code, message=None, method=None):
        self.code = code
        self.method = method
        self.message = message or RETURN_CODES.get(code) or 'خطای ناشناخته'
        super().__init__('Kavenegar %s: [%s] %s' % (method or '', code, self.message))

    @property
    def failure_type(self):
        return CODE_TO_FAILURE.get(self.code, 'unknown')


_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def normalize_receptor(number):
    """Return a number Kavenegar accepts (09xxxxxxxxx for Iran), or False."""
    digits = re.sub(r'[^\d+]', '', (number or '').translate(_DIGITS))
    if digits.startswith('+'):
        digits = digits[1:]
    if digits.startswith('0098'):
        digits = '0' + digits[4:]
    elif digits.startswith('98') and len(digits) == 12:
        digits = '0' + digits[2:]
    elif len(digits) == 10 and digits.startswith('9'):
        digits = '0' + digits
    if re.fullmatch(r'09\d{9}', digits):
        return digits
    if re.fullmatch(r'\d{7,15}', digits):
        return digits
    return False


def sms_parts(text):
    """(characters, parts) using Kavenegar's Persian/Latin part sizes."""
    text = text or ''
    persian = any(ord(c) > 127 for c in text)
    n = len(text)
    single, multi = (70, 67) if persian else (160, 153)
    if n <= single:
        return n, (1 if n else 0)
    return n, -(-n // multi)


class Kavenegar:
    def __init__(self, api_key, timeout=20, session=None, base_url=None):
        if not api_key:
            raise KavenegarError(403, 'کلید API کاوه‌نگار در تنظیمات وارد نشده است')
        self.api_key = api_key.strip()
        self.base_url = base_url or BASE_URL
        self.timeout = timeout
        self.session = session or requests.Session()

    def call(self, path, params=None, method='POST', files=None):
        url = self.base_url % (self.api_key, path)
        params = {k: v for k, v in (params or {}).items() if v not in (None, False, '')}
        for k, v in list(params.items()):
            if isinstance(v, (list, tuple)):
                params[k] = ','.join(str(x) for x in v)
        try:
            if method == 'GET':
                r = self.session.get(url, params=params, timeout=self.timeout)
            elif method == 'DELETE':
                r = self.session.delete(url, params=params, timeout=self.timeout)
            else:
                r = self.session.post(url, data=params, files=files, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            _logger.warning('Kavenegar %s: transport error %s', path, type(e).__name__)
            raise KavenegarError(409, 'ارتباط با کاوه‌نگار برقرار نشد', path)
        try:
            data = r.json()
        except ValueError:
            raise KavenegarError(409, 'پاسخ نامعتبر از کاوه‌نگار (HTTP %s)' % r.status_code, path)
        ret = data.get('return') or {}
        code = ret.get('status')
        if code != 200:
            raise KavenegarError(code, ret.get('message'), path)
        return data

    @staticmethod
    def entries(data):
        e = data.get('entries')
        if e is None:
            return []
        return e if isinstance(e, list) else [e]

    # -- sms ---------------------------------------------------------------
    def send(self, receptor, message, sender=None, date=None, type_=None, localid=None,
             hide=False, tag=None, policy=None, mediaid=None):
        return self.entries(self.call('sms/send', {
            'receptor': receptor, 'message': message, 'sender': sender, 'date': date,
            'type': type_, 'localid': localid, 'hide': 1 if hide else None,
            'tag': tag, 'policy': policy, 'mediaid': mediaid}))

    def sendarray(self, receptors, senders, messages, date=None, types=None,
                  localids=None, hide=False, tag=None, policy=None, mediaid=None):
        p = {'receptor': json.dumps(receptors), 'sender': json.dumps(senders),
             'message': json.dumps(messages, ensure_ascii=False), 'date': date,
             'hide': 1 if hide else None, 'tag': tag, 'policy': policy, 'mediaid': mediaid}
        if types:
            p['type'] = json.dumps(types)
        if localids:
            p['localmessageids'] = json.dumps(localids)
        return self.entries(self.call('sms/sendarray', p))

    def status(self, messageids):
        return self.entries(self.call('sms/status', {'messageid': messageids}))

    def status_localid(self, localids):
        return self.entries(self.call('sms/statuslocalmessageid', {'localid': localids}))

    def status_by_receptor(self, receptor, startdate, enddate):
        return self.entries(self.call('sms/statusbyreceptor', {
            'receptor': receptor, 'startdate': startdate, 'enddate': enddate}))

    def select(self, messageids):
        return self.entries(self.call('sms/select', {'messageid': messageids}))

    def select_outbox(self, startdate, enddate=None, sender=None):
        return self.entries(self.call('sms/selectoutbox', {
            'startdate': startdate, 'enddate': enddate, 'sender': sender}))

    def latest_outbox(self, pagesize=200, sender=None):
        return self.entries(self.call('sms/latestoutbox', {'pagesize': pagesize, 'sender': sender}))

    def count_outbox(self, startdate, enddate=None, status=None):
        return self.entries(self.call('sms/countoutbox', {
            'startdate': startdate, 'enddate': enddate, 'status': status}))

    def cancel(self, messageids):
        return self.entries(self.call('sms/cancel', {'messageid': messageids}))

    def receive(self, linenumber, isread=0):
        return self.entries(self.call('sms/receive', {'linenumber': linenumber, 'isread': isread}))

    def inbox_paged(self, linenumber, isread=0, startdate=None, enddate=None, pagenumber=1):
        data = self.call('sms/inboxpaged', {
            'linenumber': linenumber, 'isread': isread, 'startdate': startdate,
            'enddate': enddate, 'pagenumber': pagenumber})
        meta = (data.get('return') or {}).get('metadata') or data.get('metadata') or {}
        return self.entries(data), meta

    def count_inbox(self, startdate, enddate=None, linenumber=None, isread=0):
        return self.entries(self.call('sms/countinbox', {
            'startdate': startdate, 'enddate': enddate, 'linenumber': linenumber, 'isread': isread}))

    # -- blocked list ----------------------------------------------------------
    def blocked_list(self, linenumber, blockreason=None, startdate=None, pagenumber=1):
        return self.entries(self.call('line/blocked/list', {
            'linenumber': linenumber, 'blockreason': blockreason,
            'startdate': startdate, 'pagenumber': pagenumber}))

    def blocked_add(self, linenumber, receptors):
        return self.entries(self.call('line/blocked/add', {'linenumber': linenumber, 'receptor': receptors}))

    def blocked_exists(self, linenumber, receptors):
        return self.entries(self.call('line/blocked/exists', {'linenumber': linenumber, 'receptor': receptors}))

    def blocked_remove(self, linenumber, receptors):
        return self.entries(self.call('line/blocked/remove', {
            'linenumber': linenumber, 'receptor': receptors}, method='DELETE'))

    # -- verify lookup + templates -----------------------------------------------
    def lookup(self, receptor, template, token, token2=None, token3=None,
               token10=None, token20=None, type_=None, tag=None):
        return self.entries(self.call('verify/lookup', {
            'receptor': receptor, 'template': template, 'token': token, 'token2': token2,
            'token3': token3, 'token10': token10, 'token20': token20,
            'type': type_, 'tag': tag}))

    def template_list(self, page=1):
        return self.entries(self.call('verify/templatelist', {'page': page}))

    def template_get(self, tid):
        return self.entries(self.call('verify/gettemplate', {'id': tid}))

    def template_add(self, **kw):
        return self.entries(self.call('verify/addtemplate', kw))

    def template_update(self, tid, **kw):
        kw['templateId'] = tid
        return self.entries(self.call('verify/updatetemplate', kw))

    def template_clone(self, new_name, source_id=None, source_name=None):
        return self.entries(self.call('verify/clonetemplate', {
            'sourceTemplateId': source_id, 'sourceTemplateName': source_name,
            'newTemplateName': new_name}))

    def template_delete(self, tid):
        return self.entries(self.call('verify/deletetemplate', {'id': tid}))

    # -- voice --------------------------------------------------------------------
    def make_tts(self, receptor, message, date=None, localid=None, repeat=None, tag=None):
        return self.entries(self.call('call/maketts', {
            'receptor': receptor, 'message': message, 'date': date,
            'localid': localid, 'repeat': repeat, 'tag': tag}))

    # -- account -------------------------------------------------------------------
    def account_info(self):
        return self.entries(self.call('account/info', method='GET'))

    def account_config_get(self):
        return self.entries(self.call('account/config', method='GET'))

    def account_config_set(self, **kw):
        return self.entries(self.call('account/config', kw))

    def get_date(self):
        return self.entries(self.call('utils/getdate', method='GET'))

    # -- media (internal messenger lines) ---------------------------------------------
    def media_upload(self, filename, content, mimetype):
        return self.entries(self.call('media/upload', files={'File': (filename, content, mimetype)}))

    def media_list(self, page=1, size=50):
        return self.entries(self.call('media/list', {'page': page, 'size': size}))

    def media_get(self, mid):
        return self.entries(self.call('media/get', {'id': mid}))

    def media_delete(self, mid):
        return self.entries(self.call('media/delete', {'id': mid}))


def unix_now():
    return int(time.time())
