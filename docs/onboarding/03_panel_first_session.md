# onb3 — the first session inside a panel (release 3 of onboarding)

Branch `onb3`, module `ts_onboard` 20.0.2.0.0 (models/onb3.py, onb3_nudge.py, onb3_sample.py, controllers/onb3.py,
views/web_onb3_panel.xml, web_onb3_site.xml, data/onb3_data.xml, a post-migration) plus changes in ts_core, ts_org,
ts_panel, ts_battery, ts_billing, ts_brand, ts_tasks, ts_hire and ts_website. Design: Project docs
`claude/ONBOARDING_RESEARCH_AND_DESIGN.md` and `claude/B2B_PANEL_ONBOARDING_RESEARCH.md`. eot.ir (website 1), the back
office and internal users are not changed: every page is bound to talentsearch.ir.

## B2. From the form to the first result

**One form.** `/panel` asks one question («برای چه کاری از استعدادیاب استفاده می‌کنید؟») with four cards: مرکز مشاوره ·
مشاور یا روان‌شناس مستقل · مدرسه · استخدام و منابع انسانی (kinds clinic, solo (solo_as psychologist), school, org). Every card
and every audience page («ساخت پنل رایگان», `/panel?kind=…`) opens `/my/workspaces/new?kind=…` (sign-in first) with the kind
chosen: kind, panel name, «نام شما» (filled with the account's name; required only when the account has none). The button
«ساخت پنل» is the acceptance of the terms (the line under it says so, as on the sign-in page; terms version unchanged).
No licence number and no escalation question at creation: the licence is a badge on the member profile (onb1; a solo
practitioner panel is listed for the after-the-fact review, audit `member.licence_self_declared`), and the escalation
contact of a counseling panel is asked once, inside its first client invitation.

**Escalation, once.** `ts_core` no longer refuses to activate a clinical panel without an escalation contact. Instead
`ts.assignment` and `ts.campaign` refuse a client invitation or a link of a clinical panel while it has none (the message
names the tick). The one-screen invitation shows the tick «پیگیری فوری نشانه‌های خطر در این مرکز با من است» while it is
missing; ticking it sets the inviting member's partner (`ts_set_escalation`, audit `workspace.escalation`). A member's
own try-out never needs it.

**The kind drives the starter.** clinic / solo → BAT-INTAKE-1; school → TALENT-INV-15; HR → BAT-HR-SHORT on the sample
position «کارشناس فروش (نمونه)» made with every new employment panel (occupation 41-4012.00 «نمایندهٔ فروش عمده و بازاریاب»,
falling back to 41-3091.00 / 41-2031.00; open, profile reviewed, 30-day deadline, `ts_sample`, the pill «نمونه» and a note
that it is editable like any other). The starter is preselected in every invitation surface.

**«اول خودتان ببینید …» (the try-out).** `POST /my/workspaces/<id>/try` makes the member a participant of his own panel:
a preview client (source `preview`), an invitation with `ts_preview` and channel `preview`, accepted at once with
sharing; every battery part carries `ts_preview`. A try-out is never billed (no hold, no usage event, no debit, the wallet
reconcile skips it) and never counted: clients and invitation lists and every dashboard count (the client domain excludes
source preview), backoffice health, position counts and fairness, funnel events, the task norms (`_ts_rebuild` also skips
voided attempts), reminders, notifications and the result SMS. It is listed only where it belongs, always labelled: the
member's own list «(پیش‌نمایش)», the sample position of hiring «پیش‌نمایش — <name>». Its end (`/try/end`, also the
player's «submitted» redirect) is the real staff report view of the panel (`?preview=1`, clinical level for a counseling
panel even when the owner does not counsel: it is his own data) with the coach line «پیش‌نمایش · گزارش مراجعانتان همین‌جا
می‌آید» and under it one primary button «حالا نخستین مراجع را دعوت کنید» (school «حالا پیوند کلاس را بسازید», HR «حالا
نخستین داوطلب‌ها را دعوت کنید»). The HR admin becomes the first candidate of the sample position.

**Sample reports.** `ts.onb.sample` builds a sample per kind in memory from fixed synthetic answers with the real engines
and the real templates (clinic: the intake parts with bands and counselor texts; school: the talent report; HR: the job-fit
block of the candidate page, now its own template `ts_hire.candidate_fit`). Nothing is stored. Inside the panel:
`/my/workspaces/<id>/sample` («یا نمونهٔ گزارش را ببینید»); public: `/sample/clinic|solo|school|hr` (audience pages). Each
says «نمونه — داده‌های ساختگی» and names a synthetic person.

**«شروع کار».** The dashboard card (`ts_onb_start_card`): four steps ticked by real data — «پنل ساخته شد», «خودتان امتحان
کنید», «نخستین دعوت» (school «پیوند کلاس», HR «دعوت داوطلب‌ها»), «نخستین نتیجه» (school «نخستین گزارش کلاس») — «۱ از ۴» and a
bar, a hero for the current step with the page's only primary button, «بعداً» (per member). A colleague who joined sees
only his own try-out step. It replaces ts_panel's 7-step list (its «راه ارتباط با پنل» could never be finished; route
`/dashboard/dismiss` removed) and ts_brand's six-step «راه‌اندازی مرکز» (hide/show routes removed; «بدون سقف بماند», the
catalog marker and the counselor's first-run card stay). The empty state no longer repeats the header's «دعوت تازه».

**«پنل را کامل کنید».** After the first real result was opened (`result.view`, `hire.view`, `report.group_view` of a real
record) the second card lists optional items, each ticked by data and shown only to a member who can do it: نام و لوگو روی
گزارش · دعوت همکاران (not solo) · نام پیامکی · اعتبار و قیمت‌ها (prepaid) · سقف‌ها (prepaid, with «بدون سقف بماند») · رسیدگی
به پروانه (an owner who counsels). A celebration line in the first week, «بعداً» per member.

**One-screen «دعوت تازه».** `/invites/new` is one screen with two equal choices: «فرستادن به یک نفر» (نام, موبایل, the starter
preselected, the SMS as it will read from the real template, «فرستادن»; under «تنظیمات بیشتر»: deadline (Jalali), note,
another instrument or battery (the existing picker and its billing check), e-mail, age group, extra time for hiring; the
minors' guardian attestation; the line under «فرستادن» is the SMS consent attestation) and «پیوند همیشگی و QR». The old
four-step wizard stays only for choosing a registered participant (`?wizard=1`) and for every POST that carries a step.

**The permanent link.** `ts_onb_permanent_link`: an open-link campaign of the starter (`ts_permanent`, no expiry, 500 joins,
open until the panel closes it); the participant signs in with his own number (S-AUTH), types his name and joins with the
sharing choice of `/c`. Copy, share, «دریافت QR» (`/link/qr.png?download=1`) and the QR image. Hiring has none (invitations
belong to a position).

**Live status.** `ts_panel.invite_steps`: «فرستاده شد → باز شد → در حال پاسخ → آماده» (phone: dots and the current label)
in the invitation list and in the dashboard's «دعوت‌های اخیر»; ended invitations keep their pill. Counts start with the
first invitation; rates and medians from the fifth (the tiles say so).

## B3. Guide SMS (`ts.onb.nudge`, back office «پیامک‌های راهنما»)

Native `sms.template` records (`ts_onboard.sms_onb_*`) rendered by `ts.brand.sms_render`; no test, client or result is
named. Switch `ts_onboard.nudges_enabled` (default on).

| kind | when | to |
|---|---|---|
| welcome | the panel is made: «پنل … ساخته شد. نخستین قدم: خودتان امتحان کنید.» | the owner |
| stall_3h | 3 h, no try-out and no real invitation: «اول خودتان ببینید … چه می‌بیند» | owners |
| stall_24h | 24 h, no real invitation: «پیوند همیشگی پنل … آماده است» + link (HR: the sample position) | owners |
| first_result | the first real shared result: «نخستین نتیجه در پنل … آماده است» + link | owners + the inviting member |
| digest | Saturday from 09:00 Tehran, panels with activity: counts only | owners |
| (7 days, no result) | a back-office activity «تماس شخصی با پنل …» for a platform manager (`ts_onboard.followup_user_id`), never an SMS | — |

Rules: one row per member and key (nothing twice); at most one guide SMS a member a day (the first-result SMS answers his
own invitation and is not held back); a stall nudge stops once its step is done (the 24-hour one supersedes a waiting
3-hour one); 22:00–08:00 Tehran queued for the hourly run (`ts_onboard.quiet_start/quiet_end`); suspended or closed panels
get nothing; each member switches them off on his own page («پیامک‌های راهنما»); separate from the staff-SMS switch.
**Clones never text anyone**: the guide and join SMS go out only from the database `eot_main` (`ts_onboard.sms_db`) or to
a local fake gateway (127.0.0.1); elsewhere the row is skipped («not_production»). Panels older than the release get no
stall SMS (the migration marks their follow-up).

**Colleague join SMS.** A colleague invited with a mobile number (and «ساخت پیوند تازه») gets the join SMS (`/j/` link,
template `ts_brand.sms_member_invite`) from the system; the members page says whether it went. Joining is unchanged
(sign-in with that number, «پذیرفتن»; no licence at the door).

## B4, O4. Help and audience pages

`/help/panel#getting-started` with five items per kind (`#start-clinic`, `#start-solo`, `#start-school`, `#start-hr`),
`#hr` (positions, job fit, retention, fairness), `#more`; `#invite` rewritten for the one screen; ts_brand's
`#center-setup` is «کامل کردن پنل مرکز مشاوره»; the help date and the support link (panel code, audit §9.13) updated.
Audience pages: `/clinics` and `/hiring` (new; the old redirects to the contact form are removed, `/employers` → `/hiring`)
and `/schools` (updated): one promise, three benefits, «ساخت پنل رایگان» (the one form, kind chosen), «نمونهٔ گزارش» (the
public sample), three or four questions (who sees what, privacy, cost «رایگان در دورهٔ آزمایشی», HR data retention 12
months), Persian titles and descriptions. `/pricing`: every kind free during early access, links to the audience pages.
The home hero's three quiet links point to `/clinics`, `/hiring`, `/schools`.

## Measures and money

Funnel rows (`ts.funnel.event`, no personal data): `panel_created`, `self_test_done`, `first_invite`, `first_result_opened`
with `panel_kind` (a salted hash of the panel, once per step); back office pivot «فعال‌شدن پنل‌ها» (managers). Usage line
on free panels «تا امروز N نتیجه؛ در دورهٔ آزمایشی رایگان» («رایگان در این فصل» renamed everywhere). Welcome credit
`ts_billing.welcome_credit_rial` (default 0 = off): a new prepaid panel gets one grant through the back-office path
(«اعتبار هدیه», reason promo; never an invoice or a recorded payment), once, and not for a panel that already had a grant
or a purchase.

## Migration (ts_onboard 20.0.2.0.0)

- `ts_kind` from the owner's choice (audit `workspace.self_create`), else from the purpose (a counseling panel whose only
  member is a counselling owner: solo).
- «شروع کار» stays only for active panels that never sent a real invitation; every other panel sees its finished state (no
  start card, no second card). Live on 2026-10-13: Sepehr (workspace 4, prepaid, one invitation) and the school panels
  with invitations (1, 6) finished; 3, 5, 7, 8 (active, no invitation) get «شروع کار»; 2 is closed.
- Activation marks from real data (first invitation, first ready result = first opened); the 7-day follow-up is marked
  done for every older panel, so none of them gets a stall SMS. Nothing is sent by the migration.

## Tests

`tools/prod/tests_onb3.py` (ORM, never commits, SMS recorded, the rules clock patched) and `tools/prod/ts_http_onb3.py`
(HTTP with a local fake Kavenegar), both registered in `tools/vps/ts_rehearse.sh`; old suites updated where the behaviour
changed (stage1, panel, pv2_12, brand, onb1, onb2 and their HTTP companions, pv2_1, pv2_11, pv2_19). Shots: the matrix
owner gets six panels in their first-session states (`tools/vps/ts_onb3_seed.py`).
