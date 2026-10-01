"""Plain-Persian wording of the roles and permissions (used by /help/roles and, from S14, the audit page).

Every permission string of ts_org.models.perms has a label here (a test fails otherwise). LIVE lists the permissions
whose feature exists in the product today; the role table shows only those, so it never promises a page that is
not built yet. Each stage that builds a feature adds its permission strings to LIVE.
"""
from odoo.addons.ts_org.models.perms import ALL_PERMS

PERM_LABELS = {
    'panel:view': 'دیدن داشبورد پنل',
    'panel:profile': 'ویرایش نام و لوگوی پنل',
    'panel:settings': 'دیدن شرایط استفاده و اطلاعات پنل',
    'panel:transfer': 'واگذاری مالکیت پنل',
    'panel:close': 'بستن پنل',
    'members:read': 'دیدن فهرست اعضا',
    'members:invite': 'دعوت همکار',
    'members:manage': 'تغییر نقش و غیرفعال‌کردن اعضا',
    'members:add_owner': 'افزودن مالک دیگر',
    'clients:read_all': 'دیدن همهٔ شرکت‌کنندگان',
    'clients:read_own': 'دیدن شرکت‌کنندگانی که مسئول آن‌ها هستید',
    'clients:read_unassigned': 'دیدن شرکت‌کنندگان بدون کارشناس مسئول',
    'clients:write': 'ثبت و ویرایش شرکت‌کننده',
    'clients:assign': 'تعیین کارشناس مسئول',
    'clients:be_responsible': 'مسئول شرکت‌کننده شدن',
    'clients:archive': 'بایگانی شرکت‌کننده',
    'clients:merge': 'یکی‌کردن رکوردهای تکراری',
    'clients:import': 'ورود فهرست از فایل',
    'clients:export': 'خروجی فهرست شرکت‌کنندگان',
    'groups:manage': 'ساخت و ویرایش گروه',
    'invites:create': 'فرستادن دعوت',
    'invites:bulk': 'دعوت گروهی و پیوند باز',
    'invites:manage': 'یادآوری، تمدید و لغو دعوت',
    'results:summary': 'دیدن خلاصهٔ نتیجه (بازهٔ هر بُعد)',
    'results:education': 'دیدن گزارش در سطح مشاور',
    'results:clinical': 'دیدن گزارش بالینی کامل',
    'results:export': 'خروجی نتیجه‌ها',
    'reports:group': 'گزارش گروهی',
    'credits:read': 'دیدن اعتبار و مصرف',
    'audit:read': 'دیدن سابقهٔ رویدادها',
    'audit:export': 'خروجی سابقهٔ رویدادها',
    'support:view': 'دیدن دسترسی‌های پشتیبانی به پنل',
    'help:view': 'راهنما',
}

# Features that exist today (S3). Later stages extend this set.
LIVE = {
    'panel:view', 'panel:profile', 'panel:settings',
    'members:read', 'members:invite', 'members:manage', 'members:add_owner',
    'clients:read_all', 'clients:read_own', 'clients:read_unassigned', 'clients:assign',
    'clients:write', 'clients:archive', 'clients:merge', 'clients:be_responsible', 'groups:manage',
    'results:summary', 'results:education', 'results:clinical',
}

ROLE_BLURBS = {
    'owner': 'مالک پنل: مسئول نهایی پنل است و اعضا و تنظیمات را اداره می‌کند. هر پنل دست‌کم یک مالک دارد.',
    'admin': 'هماهنگ‌کنندهٔ پنل: کارهای اجرایی را پیش می‌برد و هیچ نتیجه‌ای را نمی‌بیند؛ فقط وضعیت دعوت‌ها را می‌بیند.',
    'counselor': 'مشاور: شرکت‌کنندگان خود را می‌بیند و گزارش را در سطح مشاور می‌خواند.',
    'clinic_director': 'مدیر درمانگاه: اعضا و دعوت‌ها را اداره می‌کند و پس از احراز صلاحیت، گزارش بالینی را می‌بیند.',
    'clinician': 'متخصص بالینی: پس از احراز صلاحیت، گزارش کامل مراجعان خود را می‌بیند.',
    'hr_admin': 'مدیر منابع انسانی: اعضا و دعوت‌ها را اداره می‌کند و خلاصهٔ نتیجهٔ داوطلبان را می‌بیند.',
    'hiring_manager': 'مدیر استخدام: داوطلبان خود را می‌بیند و خلاصهٔ نتیجهٔ آن‌ها را می‌خواند.',
    'reviewer': 'بازبین: خلاصهٔ نتیجهٔ داوطلبان را می‌خواند و دعوت نمی‌فرستد.',
}

assert set(PERM_LABELS) == set(ALL_PERMS), 'every permission string needs a Persian label'
assert LIVE <= set(PERM_LABELS)

ROLE_ORDER = ['owner', 'admin', 'clinic_director', 'hr_admin', 'counselor', 'clinician', 'hiring_manager', 'reviewer']
