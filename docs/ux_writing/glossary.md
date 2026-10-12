# Talent Search glossary (Persian product terms)

Version 1.1, 2026-10-11 (owner decision the same day: counseling wording, see the box below). One term per concept. Counts are occurrences in `addons/ts_*/{views,controllers,models,data}`
(raw regex counts on 2026-10-11, including labels, help texts and comments; good enough to show drift, not exact).
eot.ir evidence is from the pages listed in `voice.md` §1. Audit references: `docs/ux_audit/2026-10-11/G*.json` patterns.

Legend: **OWNER DECISION** = a real trade-off; the owner picks, the recommendation is given. Rows without that mark
are decided here under the project rules and can be applied by copy passes.

> **Counseling, never therapy (owner decision 2026-10-11).** Nothing a user sees says «درمان»، «درمانگر»، «روان‌درمانی»، «بیمار»/«مریض»، «بالینی»، «کلینیک»/«درمانگاه» (English: therapy, treatment, patient, clinic, clinical). Counseling terms only: «مشاوره»، «مشاور»، «مرکز مشاوره»، «مراجع». «درماندگی»/«درمانده» (helplessness) stay. Code identifiers stay (`clinical`, `clinician`, `clinic_director`, `therapist_text`). Book band texts are mapped at display time (`counseling_terms()` in ts_assessment/models/attempt.py); leftovers: `docs/clinic/03_terms_in_book_texts.md`.

Audience codes: S student, A adult participant, P parent, E education staff, C counseling-center staff (purpose `clinical`), H HR/employment staff,
B Odoo backend staff, ALL everyone.

## 1. Brand and family

| Term | Meaning | Use for | Never use | Audience | Evidence |
|---|---|---|---|---|---|
| **استعدادیاب** (+ «Talent Search» only in logo/`<bdi>`; domain `talentsearch.ir` stays Latin) | the product | running text, titles, SMS sender line, lockup «استعدادیاب، از خانوادهٔ هیجان اندیشه» | «تلنت سرچ» / «تلنت‌سرچ» (old transliteration, retired 2026-10-11), «استعدادیابی» (that is the activity, not the product), English name inside Persian sentences | ALL | Owner decision 2026-10-11 (§9-1): the Persian name is «استعدادیاب», as on eot.ir («استعدادیاب · قدرت گرفته از هیجان اندیشه»، «آزمون را در استعدادیاب می‌دهید»). Before the rename the product said «تلنت سرچ» ۵۵ times. |
| **هیجان اندیشه** | the parent institute (EOT) | trust lines, footer: «از خانوادهٔ هیجان اندیشه» | «EOT» alone in Persian text (keep `<bdi dir="ltr">EOT</bdi>` only next to the Persian name) | ALL | eot.ir everywhere; product: «هیجان اندیشه» ۰ (only «EOT»). Add the Persian name. |

## 2. Spaces and organisations

| Term | Meaning | Use for | Never use | Audience | Evidence |
|---|---|---|---|---|---|
| **پنل** | an organisation's space in Talent Search (`ts.workspace`) | every UI mention of the space: «پنل مدرسهٔ …»، «کد پنل»، «تنظیمات پنل» | «فضای کاری» (UI), «سازمان»/«مؤسسه»/«مرکز» as a name for the space | ALL | product: «پنل» ۲۹۵؛ «فضای کاری» ۳۳ (۲۱ in ts_core backend, ۹ ts_org web e.g. «این فضای کاری (سازمان، مرکز مشاوره یا …)»). Audit G1 PT-6, G2 X4. Project rule term. Backend may keep the model name, but labels should say «پنل» too. |
| مدرسه / سازمان / مرکز مشاوره | the real-world entity that owns a panel | describing who runs the panel, by purpose: education → «مدرسه» (or «دانشگاه»), employment → «سازمان»، counseling (`clinical`) → «مرکز مشاوره» | «مؤسسه» for a customer (it is EOT's own word: «مؤسسه تعاملی هیجان اندیشه»), «کلینیک»، «درمانگاه»، «مرکز درمانی» | ALL | product: «سازمان» ۳۵، «مؤسسه» ۱۲ (invite: «با مؤسسه و مشاور مسئول به اشتراک»), «مدرسه» ۲۳. eot.ir uses «مؤسسه» only for itself. Owner decision 2026-10-11: counseling wording; the education label became «مدرسه یا دانشگاه» so it never collides with «مرکز مشاوره». |
| **مرکز مشاوره** | a counseling-center customer (purpose `clinical`) | «پنل مرکز مشاوره»، role «مدیر مرکز مشاوره»، create form and landing card «مرکز مشاوره» | «کلینیک»، «درمانگاه»، «مرکز بالینی»، «مراکز درمانی» (also in marketing) | C | Owner decision 2026-10-11 (counseling, never therapy). Was «کلینیک روان‌شناسی و مشاوره» / «مدیر درمانگاه» / «مدیر مرکز بالینی» before. |
| حوزهٔ پنل (آموزشی / استخدامی / مشاوره / رفاه کارکنان) | panel purpose | labels and filters | «نوع کاربری»، «purpose»، «بالینی» | E C H | PURPOSES in ts_core/models/workspace.py: «دانشگاه و مدرسه»، «استخدام و منابع انسانی»، «مشاوره»، «رفاه کارکنان». Battery flag label «پنل مرکز مشاوره». |
| **در انتظار تأیید** | gated panel (`pilot` + `gated`): set up, cannot invite participants yet | state pill and notice on every page of a gated panel | «فعال» for a pilot panel, «پایلوت» in UI | E C H | base.py `PANEL_STATE_LABELS['pilot'] = 'فعال'` hides the state (audit G5 PT-3, which proposes «آزمایشی»). «پایلوت» ۵ (one in public marketing: «در حال پایلوت است»). **OWNER DECISION** (§9-6) |

## 3. People and roles

| Term | Meaning | Use for | Never use | Audience | Evidence |
|---|---|---|---|---|---|
| **شرکت‌کننده** (جمع: شرکت‌کنندگان) | a person who answers an instrument inside a panel | panel UI in all purposes, consent, invites | «کاربر» for this person, «آزمودنی»، «داوطلب» | ALL | product: ۱۳۱ (ts_panel ۷۱، ts_org ۳۵). Project rule term. |
| مراجع (جمع: مراجعان) | a counseling-center client | only in counseling-center panels (purpose `clinical`), through the purpose-aware helpers (`ts_panel/models/text.py`, `audit_view.py`) | «مراجعین»؛ «بیمار»/«مریض» anywhere; «مراجع» in education/employment panels | C | product: «مراجع» ۱۹ + «مراجعان» ۱۰. Owner decision 2026-10-11: «مراجع» is the counseling word for the person a counseling center serves; shared screens keep «شرکت‌کننده» (§9-3). |
| دانش‌آموز / شاگرد | a student as described by school staff | marketing and help aimed at schools («شاگردانتان را دعوت کنید») | as a data label (the record is still «شرکت‌کننده») | E | product: «دانش‌آموز» ۲۸ (ts_website ۲۵). Pick «دانش‌آموز» (official school word, eot.ir articles use it); «شاگرد» ۰ in product, used once in an audit proposal; avoid. |
| **کارشناس مسئول** | the panel member responsible for a participant (`responsible_id`), any role | panel UI: column, filter, assignment action, help | «مشاور مسئول»، «مسئول» alone, «متخصص مسئول» | E C H | product: ۳۲ (panel ۲۱، org ۱۱); «مشاور مسئول» ۴ (invite and sharing). Project rule term. Participant-facing word is §9-4. |
| مشاور | the education role `counselor`; the participant-facing word for the responsible person in education and counseling-center panels | role label (education); «راهنمای مشاور»، «گزارش ویژهٔ مشاور» | for HR | S A P E C | product: «مشاور» ۶۶ (website ۲۴: «ارسال نتیجه برای مشاورم»). eot.ir: «روان‌شناس یا مشاور»، «انتخاب مشاور». The counseling-center role is «مشاور مرکز» (next row) because both labels share one role list. |
| مشاور مرکز | role `clinician` (verified counselor of a counseling-center panel; backend label «مشاور مرکز دارای پروانه») | role label, verification texts | «متخصص بالینی»، «درمانگر»، «روان‌درمانگر»، «بالینگر» | C | Owner decision 2026-10-11. «مشاور» alone is taken by the education role in the same lists (ROLE_LABELS, ROLES). |
| مالک پنل | role `owner` | role label, transfer, close | «مسئول پنل» (collides with کارشناس مسئول), «مدیر پنل» | E C H | product: «مالک پنل» ۱۴، «مسئول پنل» ۲ (help: «مسئول پنل از این دسترسی خبردار می‌شود»), «مدیر پنل» ۴. |
| هماهنگ‌کنندهٔ پنل | role `admin` | role label | «ادمین»، «مدیر» | E C H | ROLE_LABELS. Keep. |
| مدیر مرکز مشاوره | role `clinic_director` | role label | «مدیر کلینیک»، «مدیر درمانگاه»، «مدیر مرکز بالینی» | C | Owner decision 2026-10-11 (ROLE_LABELS and ROLES). |
| مدیر منابع انسانی / مدیر استخدام / بازبین | employment roles | role labels | «HR»، «ریویوئر» | H | ROLE_LABELS. Keep. |
| همکار | another member of the same panel, especially when invited | «دعوت همکار»، «همکاران پنل» | «عضو جدید» for an invitee | E C H | «همکار» ۳۰، «عضو» ۳۴، «اعضا» ۲۱. Rule: «همکار» for the person in invites, «اعضای پنل» for the list page. |
| **ولی** (first mention: «ولی (پدر، مادر یا سرپرست قانونی)») | legal guardian of a minor | consent, minors help, guardian answering for a child | «والد یا مراقب»، «مراقب» (caregiver ≠ legal guardian), «سرپرست» alone | S P E | product: «ولی» ۳۵ (mostly «رضایت ولی» ۱۴), «ولی یا سرپرست قانونی» several, «سرپرست» ۱۸ (fields «نام سرپرست»، «موبایل سرپرست»), «والد یا مراقب» ۶ (ts_assessment guardian mode). eot.ir privacy: «رضایت والد یا سرپرست». **OWNER DECISION** (§9-5; consent text needs a new version) |

## 4. Instruments and results

| Term | Meaning | Use for | Never use | Audience | Evidence |
|---|---|---|---|---|---|
| **سنجه** | an instrument (questionnaire/inventory) in the catalog | product UI, invites, panel, player | «آزمون» in product UI, «پرسشنامه» as the generic word | ALL | product: «سنجه» ۱۴۱، «آزمون» ۴ (panel help, consent «این آزمون»)، «پرسشنامه» ۶ (guardian mode). eot.ir: «آزمون‌ها و ارزیابی‌ها»، «فهرست»، «خودسنجی»؛ search habit is «آزمون استعداد». Project rule term; public SEO exception is §9-2. |
| فهرست … (instrument names) | the book's instrument titles, e.g. «فهرست تعاملی شخصیت» | exactly as in the catalog | rewriting names | ALL | eot.ir assessments page; source data. Never changed. |
| پرسش / جمله | one item | «پرسش» for normal items; «جمله» for the talent inventory statements (TALENT-INV-15) | «سؤال» and «گویه» in UI («گویه» is fine in staff docs) | ALL | product: «پرسش» ۴۷، «سؤال/سوال» ۰. eot.ir uses «گویه» and «تعداد سؤال». Audit G1 PT-1 proposes «۱۵ جمله برای هر زمینه». |
| زمینه | a field the participant writes in the talent inventory | TALENT-INV-15 only | «رشته» for this concept («رشته» = study major) | S A | «زمینه» ۱۲۹ (ts_talent ۹۲). «رشته» ۹ used for majors. Keep apart. |
| عامل / مقیاس / سطح | factor / composite scale / band | report and help | «فاکتور»، «باند»، «بُعد» in UI (eot.ir uses «ابعاد سنجش» on cards; fine on the public catalog only) | ALL | product: «عامل» ۲۳، «مقیاس» ۱۲، «سطح» ۱۷، «فاکتور» ۲ (website). eot.ir method page: «عامل / محور»، «سطح تفسیر». Scoring labels themselves are never changed. |
| نمره | numeric score | report for roles allowed to see scores | «امتیاز» (eot.ir uses it; product ۰) | A C | «نمره» ۵۵. Keep. |
| **نتیجه** (جمع: **نتیجه‌ها**) | the outcome of a completed attempt | participant and panel UI | «نتایج» in UI labels (formal), «کارنامه» | ALL | «نتیجه» ۱۸۸؛ plural «نتیجه‌ها» ۲۷ vs «نتایج» ۲۵ (e.g. «برون‌بری نتایج»). Audit G2 X2 (header «سنجه‌های من» vs subnav «سنجه‌ها و نتیجه‌ها»). |
| گزارش | the rendered page/document of a result («گزارش کامل»، «گزارش خلاصه»); panel section «گزارش‌ها» = analytics | as defined | «گزارش» for the audit log («گزارش رویدادها»، «گزارش ممیزی») | ALL | «گزارش» ۱۱۸. Disambiguate from the audit log (§6). |
| راهنمای مشاور | counselor-only interpretive text (`therapist_text`) | report heading, consent, panel help, backend label | «متن متخصص»، «راهنمای متخصص»، «راهنمای تخصصی درمانگر» | C | Owner decision 2026-10-11. Book texts are stored verbatim; therapy words in them are mapped at display time (`counseling_terms()`). |
| گزارش ویژهٔ مشاور | the full report level `clinical` (scores + counselor guide), seen only by a verified counselor with the participant's consent | level labels, consent, panel help, permission label «دیدن گزارش کامل ویژهٔ مشاور» | «گزارش بالینی»، «گزارش برای متخصص بالینی» | C | Owner decision 2026-10-11. The education level stays «گزارش در سطح مشاور». |
| مسئول پیگیری فوری | the panel's escalation contact (`escalation_contact_id`), required before a counseling-center panel is active | backend field, panel settings, create form tick («می‌پذیرم که پیگیری فوری نشانه‌های خطر با من است») | «مسئول پاسخ فوری بالینی»، «پاسخ فوری بالینی» | C B | Owner decision 2026-10-11. |
| شمارهٔ پروانه یا نظام روان‌شناسی و مشاوره | licence number a counselor enters for verification | every licence label and error | «شمارهٔ پروانه یا نظام حرفه‌ای»، «شماره پروانه/نظام» | E C | Owner decision 2026-10-11. |
| کوشش / پاسخ‌دهی | an attempt (`ts.attempt`) | rarely shown; «در حال پاسخ» state | «تلاش» (reads as "effort"), «اتمپت» | A E | STATE_LABELS «در حال پاسخ». «تلاش» ۱۱ mostly OTP retries («تلاش دوباره») — fine there. |

## 5. Invitations and links

| Term | Meaning | Use for | Never use | Audience | Evidence |
|---|---|---|---|---|---|
| **دعوت** | one invitation of one person to one instrument (`ts.assignment`) | «دعوت تازه»، «دعوت‌ها»، «ارسال دعوت» | «دعوت‌نامه»، «تخصیص سنجه» | ALL | «دعوت» ۳۰۲. |
| **دعوت گروهی** | one shareable link/QR for many people (`ts.campaign`) | nav, buttons, help | «کمپین» (field label in ts_panel models), «فراخوان»، «پویش» | E C H | «دعوت گروهی» ۲۲، «کمپین» ۱. Project list. |
| دعوت تازه | create-new action | button | «دعوت جدید» | E C H | «دعوت تازه» ۱۵، «دعوت جدید» ۱ (stale note on clients page, audit G5 PT-4). |
| **پیوند** | a URL the user copies/opens | UI everywhere, SMS | «لینک» in UI | ALL | product: «پیوند» ۷۴، «لینک» ۰. eot.ir: «لینک جلسه … ارسال می‌شود», «لینک ورود به جلسه». Benchmarks (Digikala, Snapp) say «لینک». Kept: consistent today, Farhangestan form, the rule term. Revisit only if SMS tests show confusion. |
| مهلت | deadline / validity period of an invite or link | «مهلت پاسخ»، «این پیوند تا ۳۰ روز باز است» | «اعتبار» for validity («۳۰ روز اعتبار»، «اعتبار پیوند باز») — collides with credits | E C H | «مهلت» ۲۸؛ «اعتبار» used for validity at least ۴ times. |
| منقضی‌شده | expired invite | state label | «منقضی» bare adjective in sentences | ALL | STATE_LABELS «منقضی». Prefer «مهلتش تمام شده» in participant sentences. |
| کد پنل | code that lets a participant share a self-taken result | sharing flow | «شناسهٔ سازمان» | S A | «کد پنل» ۹. Keep. |

## 6. Responsibility, privacy, audit

| Term | Meaning | Use for | Never use | Audience | Evidence |
|---|---|---|---|---|---|
| **بدون کارشناس** (long: «بدون کارشناس مسئول») | participants with no responsible member (the unassigned queue) | filter, queue name, select option, help | «تخصیص‌نشده»، «صف تخصیص‌نشده»، «بی‌کارشناس» | E C H | «بدون کارشناس» ۶ vs «تخصیص‌نشده» ۱۰ (ts_org ۷: «به صف «تخصیص‌نشده» برمی‌گردند»). «تخصیص» is administrative calque (voice §4). |
| سپردن به / کارشناس مسئول کردن | assign | action: «سپردن به کارشناس»، history: «به … سپرده شد» | «تخصیص دادن»، «واگذاری» for assignment | E C H | «واگذاری» ۱۶ (ts_panel; also used for transfer of ownership), «تخصیص» ۱۰. Keep «واگذاری» only for owner transfer: «واگذاری مالکیت پنل». |
| **دفتر ممیزی** | the panel's append-only audit log | nav, page title, help, flash texts on panel side | «ممیزی پنل» (h1), «گزارش ممیزی»، «لاگ ممیزی»، «گزارش رویدادها» | E C H | «دفتر ممیزی» ۳، «گزارش رویدادها» ۵، «ممیزی» ۲۳ total, «لاگ ممیزی» ۱. Audit G4 PT3, G1 PT-6. Participant/consent side: no term; say «ثبت می‌شود چه کسی و چه وقت آن را دیده است.» |
| اشتراک‌گذاری / قطع اشتراک‌گذاری | participant shares a result with a panel / stops | sharing page, report, consent | «اشتراک» alone (= subscription in Iranian apps), «هم‌رسانی» | S A P | «اشتراک» ۶۸، «به اشتراک» ۲۳. Reserve «اشتراک» alone for nothing; if paid plans come, call them «طرح». |
| رضایت | consent (participant / ولی) | «رضایت ولی»، «رضایت‌نامهٔ سنجه»، «پس گرفتن رضایت» | «رضایت» for satisfaction in UI copy (instrument names like «فهرست رضایت شغلی» stay) | S A P | «رضایت» ۵۴، «موافقت» ۸ (participant's own agreement). Use «موافقت» for the participant's own click, «رضایت» for the formal/guardian consent. |
| دسترسی اضطراری | emergency access procedure (`ts.emergency.access`) | backend and panel notices | «دسترسی ویژه»، «بریک‌گلس» | C B | «دسترسی اضطراری» ۱۱. Keep; do not mix with crisis «اورژانس» copy. |
| تأیید هویت | re-authentication before sensitive actions | page title, prompts | «احراز هویت مجدد»، «ورود دوباره» | E C H | `/my/reauth` (audit G4 PT5 proposes «تأیید هویت»). |

## 7. Account and sign-in

| Term | Meaning | Use for | Never use | Audience | Evidence |
|---|---|---|---|---|---|
| ورود / خروج | sign in / sign out | buttons, nav | «لاگین»، «وارد سیستم شوید» | ALL | «ورود» ۴۴، «خروج» ۳۴. eot.ir header «ورود». |
| ثبت‌نام | create an account | button | «عضویت»، «ساخت حساب کاربری» | ALL | «ثبت‌نام» ۸. |
| حساب | the user's account | «حساب من»، «تنظیمات حساب» | «حساب کاربری» in nav (fine once in help), «پروفایل» | ALL | «حساب» ۶۱، «حساب کاربری» ۱۳. Audit G2 X2. |
| رمز عبور | password | everywhere, matches Odoo's stock Persian login/reset pages that website 2 shows | «گذرواژه» | ALL | «گذرواژه» ۸، «رمز عبور» ۵. «گذرواژه» is the Farhangestan form, but the stock pages users also see say «رمز عبور»; one word wins. |
| شمارهٔ موبایل / موبایل | Iranian mobile number | labels and SMS copy | «تلفن همراه» (formal), «شماره همراه» | ALL | «موبایل» ۷۲، «تلفن همراه» ۱ (import header alias). eot.ir contact: «شماره تماس». Benchmarks say «شماره موبایل». |
| کد تأیید | the 6-digit OTP | input label, SMS | «کد پیامکی»، «رمز یکبارمصرف» | ALL | «کد تأیید» ۸، «کد پیامکی» ۶. |
| پیامک | SMS | text | «اس‌ام‌اس» | ALL | «پیامک» ۶۲. |
| نشست | a signed-in device session (`/my/sessions`) | «نشست‌های فعال» | «سشن» | A E C H | «نشست» ۷. Gloss once: «دستگاه‌هایی که با آن‌ها وارد شده‌اید». |

## 8. Panel sections and actions

| Term | Meaning | Use for | Never use | Audience | Evidence |
|---|---|---|---|---|---|
| پیشخوان | panel home page | nav item, page title | «داشبورد» | E C H | «داشبورد» ۸ before 2026-10-12; applied everywhere user-visible on 2026-10-12 (nav, tab bar, back links, permission label, page title). «پیشخوان» is what Persian WordPress users know. |
| اعتبار و مصرف / اعتبار؛ **شارژ اعتبار** (top-up) | prepaid credit and usage; adding credit by invoice | credits section, invoices, SMS low_balance («اعتبار را شارژ کنید»); button «درخواست شارژ اعتبار» -> `/contact?topic=credit&panel=<code>` (contact topic «شارژ اعتبار پنل») | «کیف پول»، «شارژ» alone, «خرید اعتبار»/«افزایش اعتبار» for top-up, «اعتبار» for validity (§5), «اعتبار:» alone for the balance (say «موجودی قابل استفاده») | E C H | «اعتبار» ۲۳. Owner decision 2026-10-12: top-up is «شارژ اعتبار» everywhere (clinic phase 5). |
| **موجودی قابل استفاده** | available credit: what new invitations can still hold | credits page card, dashboard line, refusals, set-up checklist («موجودی قابل استفاده: …») | «اعتبار:» alone for the balance, «موجودی» alone where held money exists | E C H | UX audit G7-PAT-5 (2026-10-12). |
| رزروشده | held: the price of open invitations, set aside at invitation | «رزروشده برای دعوت‌های باز» | «بلوکه»، «مسدود» | E C H | ts_hold. |
| کسرشده | debited: the price of completed instruments | «کسرشده این ماه» (card) | «مصرف» for money taken | E C H | wallet.ts_month_debited(). |
| تعهد این ماه | held + debited of one member in the current Jalali month; what the monthly cap counts | per-member table, cap bar | «مصرف این ماه» | E C H | G7-P2-1. |
| (count words) | numbers of instruments or invitations | «سنجه‌های تکمیل‌شدهٔ این دوره» | «مصرف» for a count | E C H | G7-P1-3: «مصرف» only for money. |
| خروجی (noun) / «دریافت فایل» (button) | data export | section «خروجی‌ها»، button «دریافت فایل»، job names «خروجی نتیجه‌ها» | «برون‌بری» | E C H | «خروجی» ۲۴، «برون‌بری» ۴ (job kinds), «دریافت فایل» ۳. |
| ورود از فایل | import | section and button | «درون‌ریزی»، «ایمپورت»؛ «واردشده» is fine as a filter label | E C H | «ورود از فایل» ۶، «واردشده» ۱۸. |
| ادغام | merge duplicate participants | action | «یکی کردن» | E C H | «ادغام» ۱۰. |
| بایگانی | archive (hide, keep data) | action, filter | «غیرفعال» for participants (keep «غیرفعال» for members), «حذف» when nothing is deleted | E C H | «بایگانی» ۲۰، «غیرفعال» ۱۵، «حذف» ۲۷. Destructive confirmation must name what is lost. |
| معلق / بسته | panel suspended / closed | state pills | «مسدود» | E C H B | PANEL_STATE_LABELS. Keep. |
| اعلان | in-app notification | nav, settings | «نوتیفیکیشن» | ALL | «اعلان» ۱۸. |

## 9. Owner decisions

1. **Product name in Persian. DECIDED (owner, 2026-10-11): «استعدادیاب».** The product used to say «تلنت سرچ» (a
   transliteration); eot.ir's service map already calls the testing centre «استعدادیاب» and sends visitors there
   («شروع در استعدادیاب»). «استعدادیاب» is now the Persian name in running text, titles, SMS, the lockup and the
   website name (`<title>` suffix); «Talent Search» stays only in the logo, the domain and English-only places.
2. **«سنجه» vs «آزمون» on public pages.** Product UI: «سنجه» (rule term, ۱۴۱ vs ۴). Iranians search «آزمون استعداد» and
   eot.ir says «آزمون‌ها و ارزیابی‌ها». Recommendation: «سنجه» everywhere in the product and in page body copy; allow
   «آزمون» only in public page `<title>`/meta description and once in the home hero as a gloss
   («سنجهٔ استعداد (آزمون استعدادیابی)»), so search still works. Replace the 4 in-product «آزمون» (incl. consent
   «این آزمون» → needs a consent version).
3. **«مراجع» in counseling-center panels.** (Owner, 2026-10-11: «مراجع» is the counseling word for the person a counseling
   center serves; «بیمار»/«مریض» never.) «شرکت‌کننده» is the rule term, but counselors naturally say «مراجع». Today «مراجع/مراجعان»
   leaks into education panels (filters «مراجعان من»، close-panel text, audit list). Recommendation: «شرکت‌کننده» in all
   shared screens; one purpose-aware label helper may show «مراجع» only in counseling-center panels (as audit G4 PT4 proposes).
   If the owner prefers the strict rule, drop «مراجع» everywhere, including ANON_NAME «مراجع ناشناس» → «شرکت‌کنندهٔ ناشناس».
4. **What the participant calls the responsible person.** Panel side: «کارشناس مسئول» (rule term). For a student,
   «کارشناس مسئول» is cold and unclear; audit G2 X4 proposes «مشاور». Recommendation: participant-facing label by panel
   purpose: education «مشاور»، counseling center «مشاور» (owner 2026-10-11; was «روان‌شناس»)، employment «کارشناس سازمان». Panel screens keep
   «کارشناس مسئول». Remove «مشاور مسئول» and «مؤسسه و مشاور مسئول» (invite) in either case.
5. **Guardian word in consent.** Three forms today: «ولی» / «ولی یا سرپرست قانونی» / «والد یا مراقب» (guardian mode of the
   player). «مراقب» is not a legal guardian. Recommendation: «ولی» as the term, glossed at first mention in each consent
   text as «ولی (پدر، مادر یا سرپرست قانونی)»؛ fields «نام ولی»، «موبایل ولی». Consent wording change → new consent version.
6. **State name of a gated panel.** Code shows `pilot` as «فعال»; audit G5 PT-3 proposes «آزمایشی». «آزمایشی» reads as
   "demo/test data" and may make a paying school think results are not real. Recommendation: «در انتظار تأیید» while gated
   (with the one-line reason on every page), «فعال» after approval; «پایلوت» stays a CRM/sales word only.

## 10. Terminology drift found by the UX audit (2026-10-11)

| Audit ref | Drift | Glossary resolution |
|---|---|---|
| G1 PT-6 | آزمون/سنجه; سازمان/مؤسسه/پنل; مراجع/شرکت‌کننده; لاگ ممیزی/گزارش رویدادها/دفتر ممیزی | §4 سنجه (+§9-2), §2 پنل, §3 شرکت‌کننده (+§9-3), §6 دفتر ممیزی |
| G1 PT-1 | «تعداد پرسش ۱۵»/«۸ دقیقه» for the matrix inventory | §4 «جمله»، «زمینه»; real timing = owner |
| G1 PT-2, G2 X3 | students addressed with «شما» | voice §2: «تو» for S; how age band is known = owner (audit) |
| G2 X2 | «سنجه‌های من»/«حساب من» vs «سنجه‌ها و نتیجه‌ها»/«حساب» | one name per destination: «سنجه‌ها و نتیجه‌ها»، «حساب» |
| G2 X4 | پنل/مؤسسه/سازمان/مرکز; مشاور/مشاور پنل/مشاور مسئول/کارشناس مسئول | §2, §3, §9-4 |
| G3 PAT-3 | back links «← بازگشت»، «برگشت»، «همهٔ دعوت‌ها» | «→ {نام صفحهٔ والد}» (not a term issue; copy rule) |
| G4 PT3 | دفتر ممیزی / ممیزی پنل / گزارش ممیزی / گزارش رویدادها | §6 «دفتر ممیزی» |
| G4 PT4 | «مراجعان» in an education panel | §9-3 |
| G4 PT5 | English view names in `<title>`; «تأیید هویت» | §6 |
| G5 PT-2 | proposed role sentences use «شاگردان»، «صف بدون کارشناس» | §3 «دانش‌آموز» (not «شاگرد»), §6 «بدون کارشناس» |
| G5 PT-3 | pilot shown as «فعال» | §9-6 |
| G5 PT-4 | «دعوت جدید» stale note | §5 «دعوت تازه» |

Suggested `ts check` grep rule (from G1 PT-6), for ts_* views and controllers, warn on: «آزمون»، «لاگ»، «مراجعین»،
«تخصیص‌نشده»، «گزارش رویدادها»، «برون‌بری»، «کمپین»، «لینک»، «درمانگاه»، «می‌باشد»، «گردید»، «متأسفانه»، «جهت » ;
and (owner decision 2026-10-11, counseling wording) on «کلینیک»، «بالینی»، «درمانگر»، «روان‌درمانی»، «درمان» as a whole word,
«بیمار» as a whole word, and English «clinic»/«therap»/«patient» inside user-facing strings (not identifiers).
(«مراجع» only after §9-3 is decided.)
