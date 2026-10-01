"""Every notification text of the panel in one place (S10, PLT-6). Titles never carry a name or a score: the name is seen
only after opening the page, which checks the permission again. SMS texts carry a link and never a result.
"""

TYPES = [
    ('invite', 'دعوت تازه'),
    ('reminder', 'یادآوری دعوت'),
    ('result_ready_participant', 'نتیجهٔ شما آماده است'),
    ('result_ready_staff', 'نتیجهٔ یک شرکت‌کننده آماده است'),
    ('shared_with_panel', 'نتیجه با پنل به اشتراک گذاشته شد'),
    ('share_revoked', 'اشتراک یک نتیجه لغو شد'),
    ('panel_approved', 'پنل تأیید شد'),
    ('panel_rejected', 'پنل تأیید نشد'),
    ('panel_suspended', 'پنل تعلیق شد'),
    ('member_joined', 'عضو تازه به پنل پیوست'),
    ('client_handover_request', 'درخواست واگذاری شرکت‌کننده'),
    ('export_ready', 'فایل خروجی آماده است'),
    ('import_done', 'ورود فایل تمام شد'),
    ('support_access_opened', 'دسترسی پشتیبانی باز شد'),
    ('panel_transferred', 'مالکیت پنل منتقل شد'),
    ('panel_closed', 'پنل بسته شد'),
    ('data_request_update', 'وضعیت درخواست داده‌های شما تغییر کرد'),
]
TITLES = dict(TYPES)

# Types whose SMS leg is controlled by the staff switch and the person's own opt-in (preferences page).
SMS_STAFF_TYPES = ('result_ready_staff', 'panel_approved', 'panel_rejected', 'panel_suspended')

SMS_BODIES = {
    'result_ready_staff': 'در تلنت سرچ نتیجهٔ یکی از شرکت‌کنندگان پنل شما آماده است. برای دیدن آن وارد پنل شوید:\n%(url)s',
    'panel_approved': 'پنل شما در تلنت سرچ تأیید شد. برای ادامه وارد پنل شوید:\n%(url)s',
    'panel_rejected': 'درخواست پنل شما در تلنت سرچ تأیید نشد. جزئیات را در پنل ببینید:\n%(url)s',
    'panel_suspended': 'پنل شما در تلنت سرچ تعلیق شد. جزئیات را در پنل ببینید:\n%(url)s',
    'reminder': 'یادآوری: دعوت شما به یک سنجش در تلنت سرچ هنوز باز است. پذیرش کاملاً اختیاری است:\n%(url)s',
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
    'client_handover_request': 'درخواست واگذاری شرکت‌کننده',
    'export_ready': 'آماده‌شدن فایل خروجی',
    'import_done': 'پایان ورود فایل',
    'support_access_opened': 'باز شدن دسترسی پشتیبانی',
    'panel_transferred': 'انتقال مالکیت',
    'panel_closed': 'بسته‌شدن پنل',
    'data_request_update': 'درخواست داده‌های من',
}
