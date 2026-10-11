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
    'panel:transfer': 'انتقال مالکیت پنل',
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
    'clients:merge': 'ادغام رکوردهای تکراری',
    'clients:import': 'ورود فهرست از فایل',
    'clients:export': 'خروجی فهرست شرکت‌کنندگان',
    'groups:manage': 'ساخت و ویرایش گروه',
    'invites:create': 'فرستادن دعوت',
    'invites:bulk': 'دعوت گروهی و پیوند باز',
    'invites:manage': 'یادآوری، تمدید و لغو دعوت',
    'results:summary': 'دیدن خلاصهٔ نتیجه (بازهٔ هر بُعد)',
    'results:education': 'دیدن گزارش در سطح مشاور',
    'results:clinical': 'دیدن گزارش کامل ویژهٔ مشاور',
    'results:export': 'خروجی نتیجه‌ها',
    'reports:group': 'گزارش گروهی',
    'credits:read': 'دیدن اعتبار و مصرف',
    'audit:read': 'دیدن دفتر ممیزی',
    'audit:export': 'خروجی از دفتر ممیزی',
    'support:view': 'دیدن دسترسی‌های پشتیبانی به پنل',
    'help:view': 'راهنما',
}

# Features that exist today (S3). Later stages extend this set.
LIVE = {
    'panel:view', 'panel:profile', 'panel:settings',
    'members:read', 'members:invite', 'members:manage', 'members:add_owner',
    'clients:read_all', 'clients:read_own', 'clients:read_unassigned', 'clients:assign',
    'clients:write', 'clients:archive', 'clients:merge', 'clients:be_responsible', 'groups:manage',
    'invites:create', 'invites:manage', 'invites:bulk',
    'results:summary', 'results:education', 'results:clinical',
    # UX audit 2026-10-11 (G4 P17-3): owner powers that exist today and that an owner needs to see before delegating.
    'panel:transfer', 'panel:close', 'clients:import', 'clients:export', 'results:export', 'reports:group',
    'credits:read', 'audit:read', 'audit:export',
}

# One line per role, WITHOUT the role name: pages print the bold role label first (UX audit G4 PT15).
ROLE_BLURBS = {
    'owner': 'مسئول نهایی پنل است و اعضا و تنظیمات را اداره می‌کند. هر پنل دست‌کم یک مالک دارد.',
    'admin': 'کارهای اجرایی را پیش می‌برد و هیچ نتیجه‌ای را نمی‌بیند؛ فقط وضعیت دعوت‌ها را می‌بیند.',
    'counselor': 'شرکت‌کنندگان خود را می‌بیند و گزارش را در سطح مشاور می‌خواند.',
    'clinic_director': 'اعضا و دعوت‌ها را اداره می‌کند و پس از احراز صلاحیت، گزارش ویژهٔ مشاور را می‌بیند.',
    'clinician': 'پس از احراز صلاحیت، گزارش کامل مراجعان خود را می‌بیند.',
    'hr_admin': 'اعضا و دعوت‌ها را اداره می‌کند و خلاصهٔ نتیجهٔ شرکت‌کنندگان را می‌بیند.',
    'hiring_manager': 'شرکت‌کنندگان خود را می‌بیند و خلاصهٔ نتیجهٔ آن‌ها را می‌خواند.',
    'reviewer': 'خلاصهٔ نتیجهٔ شرکت‌کنندگان را می‌خواند و دعوت نمی‌فرستد.',
}

assert set(PERM_LABELS) == set(ALL_PERMS), 'every permission string needs a Persian label'
assert LIVE <= set(PERM_LABELS)

ROLE_ORDER = ['owner', 'admin', 'clinic_director', 'hr_admin', 'counselor', 'clinician', 'hiring_manager', 'reviewer']

# Order of role PICKERS (invite, change role, transfer): least privilege first, the owner last, so the most powerful role is
# never the first target under the thumb (UX audit G4 P1-4, PT15). ROLE_ORDER above stays the order of lists and tables.
PICK_ORDER = ['counselor', 'clinician', 'reviewer', 'hiring_manager', 'admin', 'hr_admin', 'clinic_director', 'owner']
# The role preselected in the invite form of each panel purpose (None = the person must choose).
DEFAULT_PICK = {'education': 'counselor', 'clinical': 'clinician', 'employment': 'reviewer'}
assert sorted(PICK_ORDER) == sorted(ROLE_ORDER)
