"""Every notification text of the panel in one place (S10, PLT-6). Titles never carry a name or a score: the name is seen
only after opening the page, which checks the permission again. SMS texts carry a link and never a result.
"""

TYPES = [
    ('invite', 'دعوت تازه'),
    ('reminder', 'یادآوری دعوت'),
    ('result_ready_participant', 'نتیجهٔ شما آماده است'),
    ('result_ready_staff', 'نتیجهٔ تازه در پنل شما'),             # clinic phase 5 (docs/clinic/05_sms_texts.md section 3)
    ('shared_with_panel', 'نتیجه با پنل به اشتراک گذاشته شد'),
    ('share_revoked', 'اشتراک یک نتیجه لغو شد'),
    ('panel_approved', 'پنل تأیید شد'),
    ('panel_rejected', 'پنل تأیید نشد'),
    ('panel_suspended', 'پنل معلق شد'),
    ('member_joined', 'عضو تازه به پنل پیوست'),
    ('client_handover_request', 'درخواست سپردن شرکت‌کننده'),
    ('export_ready', 'فایل خروجی آماده است'),
    ('import_done', 'ورود فایل تمام شد'),
    ('support_access_opened', 'دسترسی پشتیبانی باز شد'),
    ('panel_transferred', 'مالکیت پنل منتقل شد'),
    ('panel_closed', 'پنل بسته شد'),
    ('data_request_update', 'وضعیت درخواست داده‌های شما تغییر کرد'),
    ('low_balance', 'اعتبار پنل کم شده است'),      # clinic phase 4 (ts_billing); the row title names the panel and the amount
    ('cap_reached', 'سقف ماهانهٔ دعوت شما پر شد'),   # clinic phase 5 (ts_brand): a counselor's invitation refused for the cap
    ('member_invite', 'دعوت به همکاری در یک پنل'),   # clinic phase 5: reserved; the colleague invite sends nothing today
]
TITLES = dict(TYPES)

# Types whose SMS leg is controlled by the staff switch and the person's own opt-in (preferences page).
SMS_STAFF_TYPES = ('result_ready_staff', 'panel_approved', 'panel_rejected', 'panel_suspended', 'low_balance', 'cap_reached')

SMS_BODIES = {
    'result_ready_staff': 'در استعدادیاب نتیجهٔ یکی از شرکت‌کنندگان پنل شما آماده است. برای دیدن آن وارد پنل شوید:\n%(url)s',
    'panel_approved': 'پنل شما در استعدادیاب تأیید شد. برای ادامه وارد پنل شوید:\n%(url)s',
    'panel_rejected': 'درخواست پنل شما در استعدادیاب تأیید نشد. جزئیات را در پنل ببینید:\n%(url)s',
    'panel_suspended': 'پنل شما در استعدادیاب تعلیق شد. جزئیات را در پنل ببینید:\n%(url)s',
    'reminder': 'یادآوری: دعوت شما به یک سنجش در استعدادیاب هنوز باز است. پذیرش کاملاً اختیاری است:\n%(url)s',
    # Fallbacks only: with ts_brand installed every body comes from its sms.template (docs/clinic/05_sms_texts.md).
    # low_balance / cap_reached keys: panel, amount, url (a missing key renders empty, see notify._Fill)
    'low_balance': 'اعتبار پنل «%(panel)s» در استعدادیاب به %(amount)s رسید. برای ادامهٔ دعوت‌ها اعتبار را شارژ کنید:\n%(url)s',
    'cap_reached': 'سقف ماهانهٔ دعوت شما در پنل «%(panel)s» پر شد: %(amount)s\n%(url)s',
}

PREF_LABELS = {
    'invite': 'دعوت تازه به من',
    'reminder': 'یادآوری دعوت‌های باز',
    'result_ready_participant': 'آماده‌شدن نتیجهٔ خودم',
    'result_ready_staff': 'آماده‌شدن نتیجهٔ شرکت‌کنندگان من',
    'shared_with_panel': 'به‌اشتراک‌گذاری نتیجه با پنل',
    'share_revoked': 'لغو اشتراک نتیجه',
    'panel_approved': 'تأیید پنل',
    'panel_rejected': 'رد پنل',
    'panel_suspended': 'تعلیق پنل',
    'member_joined': 'پیوستن عضو تازه',
    'client_handover_request': 'درخواست سپردن شرکت‌کننده',
    'export_ready': 'آماده‌شدن فایل خروجی',
    'import_done': 'پایان ورود فایل',
    'support_access_opened': 'باز شدن دسترسی پشتیبانی',
    'panel_transferred': 'انتقال مالکیت',
    'panel_closed': 'بسته‌شدن پنل',
    'data_request_update': 'درخواست داده‌های من',
    'low_balance': 'کم شدن اعتبار پنل',
    'cap_reached': 'پر شدن سقف ماهانهٔ دعوت من',
    'member_invite': 'دعوت به همکاری در یک پنل',
}
