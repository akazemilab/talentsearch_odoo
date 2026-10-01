# Panel v2 — 03 Information architecture and UX

Server-rendered pages (QWeb) inside the Talent Search site layout, with small vanilla
JavaScript only as an enhancement: every action works without it. Components and their class
names are defined in `08_design_system.md`.

`W` below means `/my/workspaces/<int:ws_id>`. Existing URLs are kept wherever they exist.

## 1. Site maps

### 1.1 Staff panel (one shell, the same on every page)

```
[panel switcher: panel name · code · «تغییر پنل»]
داشبورد                     W
شرکت‌کنندگان*                W/clients            (*label follows the panel's client word:
  گروه‌ها                    W/groups               دانش‌آموزان / مراجعان / داوطلبان / …)
سنجه‌ها و دعوت‌ها            W/invites
  دعوت تازه                  W/invites/new
  دعوت گروهی و پیوند باز     W/campaigns
  ورود از فایل               W/import
گزارش‌ها                     W/reports
اعضا و نقش‌ها                W/members
اعتبار و مصرف                W/credits
ممیزی                        W/audit
تنظیمات                      W/settings
راهنما                       /help/panel          (always last: WCAG 3.2.6)
```

- A menu item is shown only when the member holds the permission for its page; a direct visit
  without permission gives the 403 page inside the shell.
- Desktop (≥ 992 px): the menu is a sidebar at the inline start; content beside it.
- Below 992 px: the menu is a button «منوی پنل» that opens the list under the page header
  (button with `aria-expanded`, the pattern the site header already uses; never `<details>`,
  see `CLAUDE.md`).
- The site header gets one role-aware link: members see «پنل من» (to `/my/workspaces`, or
  straight to the panel when they have exactly one), participants see «کارهای من»; plus the
  notification bell with the unread count.

### 1.2 Participant portal

```
کارهای من          /my                     to do · continue · newest results
نتایج من           /my/assessments         (existing URL)
اشتراک‌گذاری        /my/sharing             who can see what; revoke
اعلان‌ها            /my/notifications
حساب               /my/account             name · mobile (/my/phone) · security (/my/security)
                   /my/privacy             my data: export, erase request
راهنما             /help
```

A person who is both staff and participant sees both entries in the header.

### 1.3 Platform back-office (Odoo backend, menu «تلنت سرچ»)

```
مشتریان
  پنل‌ها (سلامت و مصرف)            tenants list with health columns
  پنل‌های در انتظار تأیید           existing queue + age
  احراز صلاحیت حرفه‌ای              existing
  درخواست‌های داده                  ts.data.request queue
سنجه‌ها                              existing catalog, ops dashboard
اعتبار و مصرف
  دفتر اعتبار                        ts.wallet.txn list + pivot
  رویدادهای مصرف                     ts.usage.event
حاکمیت و ممیزی
  رویدادهای ممیزی                    existing, + outcome and family filters
  دسترسی پشتیبانی و اضطراری          ts.emergency.access with kind
  متن اعلان‌ها                       read-only list
```

## 2. Page conventions (apply to every page; not repeated below)

- **Page header**: back link when the page is below a list, `h1`, one line of help, primary
  action at the inline end. One `h1` per page.
- **Flash messages**: after a POST the next page shows one message (success or error) at the
  top, `role="status"` or `role="alert"`; the existing `ts_flash` session pattern is reused.
- **Destructive or irreversible actions** (withdraw, archive, deactivate member, merge, close
  panel, transfer ownership): the button leads to a confirmation page that names the object
  and says what will happen; the confirm button repeats the verb («بله، دعوت لغو شود»).
- **Forms**: label above the field; hint under the label; errors under the field and
  summarised at the top; input kept after an error; the message says what to do, not only
  "invalid".
- **Four list states** (wording per page in section 3):
  1. First use, nothing yet → what belongs here + the action to create it.
  2. No result for this filter → the filter summary + «پاک کردن فیلترها».
  3. No permission → what this section is + who can grant access.
  4. Error → «مشکلی پیش آمد. دوباره تلاش کنید» + retry link + support link; no stack trace.
- **Filters and search**: filters, sort and page number live in the URL (GET), so a filtered
  list can be bookmarked and saved as a view. The **search text** can be a person's name, so it
  is sent by POST, kept in the session for that list, shown in the search box with a «پاک
  کردن» button, and never appears in a URL, a saved view or a job.
- **Loading**: pages are server-rendered, so there is no skeleton. A submit button shows
  «در حال انجام…» and is disabled after the first click. Long work is a job with its own
  status page that refreshes itself.
- **Numbers and dates**: Persian digits and Jalali dates in pages; a full date has a
  `title` with the ISO date.
- **Names**: when a panel uses pseudonymous display (next), the code replaces the name.
- **Mobile**: at 375 px no horizontal page scroll; tables become cards.

## 3. Page inventory — staff

Columns: route · permission · purpose and main components · empty-state text (state 1).
The other three states are the same on every page and come from section 2: state 2 appears on
every page that has filters or search («با این فیلترها موردی پیدا نشد» + «پاک کردن فیلترها»);
state 3 is the 403 page inside the shell («به این بخش دسترسی ندارید. مالک پنل می‌تواند نقش
شما را تغییر دهد» + link to `/help/roles`), or 404 when the object is not visible; state 4 is
the error block with retry and support links. Pages with their own extra states say so in the
table.

| Route | Permission | Purpose and components | Empty state |
|---|---|---|---|
| `/my/workspaces` | signed in | Cards of my panels (name, type, my role, state pill, code). Button «ساخت پنل تازه». Pending colleague invitations addressed to my verified mobile or email are listed on top | «عضو هیچ پنلی نیستید. اگر همکاری شما را دعوت کرده، پیوند دعوت را باز کنید؛ یا پنل خودتان را بسازید.» |
| `W` (from S6; `W/home` in S2–S5 while `W` still shows the old page) | `panel:view` | Dashboard: state banner (pending approval, suspended, awaiting verification) → needs-attention list → KPI tiles → funnel → workload table → onboarding checklist | Checklist is the empty state for a new panel |
| `W/clients` | `clients:read_all` or `read_own` | Table (TBL), saved views, bulk bar, button «افزودن» and «ورود از فایل» | «هنوز کسی را اضافه نکرده‌اید. یک نفر اضافه کنید یا فهرست را از فایل وارد کنید.» |
| `W/clients/new`, `W/clients/<cid>/edit` | `clients:write` | Form: name*, code, mobile, email, groups, responsible, age group (+ guardian fields) | — |
| `W/clients/<cid>` | R0–R3 | Header + tabs: سنجه‌ها (timeline of assignments: instrument, state pill, dates, result link when allowed, invitation actions) · رضایت‌ها (S16) · فعالیت (events about this client that the viewer may see). Actions: دعوت به سنجه، تغییر مسئول، ویرایش، بایگانی | Tab سنجه‌ها: «هنوز سنجه‌ای برای این فرد ثبت نشده است.» + «دعوت به سنجه» |
| `W/clients/<cid>/r/<attempt_id>` | `result_level ≥ summary` | The report at the viewer's level; print link; "who saw this" for the owner. Old routes `W/a/<assignment_id>` and `W/p/<attempt_id>` redirect here | Level `status` renders a short page instead of a report, with the reason in words: «این فرد نتیجه را با پنل به اشتراک نگذاشته است.» / «این نتیجه هنوز منتشر نشده است.» / «رضایت ولی ثبت نشده است.» / «برای دیدن نتیجهٔ بالینی باید صلاحیت شما تأیید شود.» / «این سنجه متوقف شده است.» |
| `W/groups`, `W/groups/<gid>` | `groups:manage` (read for anyone who can see clients) | List of groups with counts; group page = client table filtered + «دعوت گروه» + «گزارش گروهی» | «گروه‌ها برای کلاس‌ها، تیم‌ها یا برچسب‌ها هستند. اولین گروه را بسازید.» |
| `W/invites` | `invites:create` or client visibility | Table of assignments with state chips and counts (funnel), filters by instrument, campaign, responsible, overdue | «هنوز دعوتی نفرستاده‌اید.» + «دعوت تازه» |
| `W/invites/new` | `invites:create` | Wizard, 4 steps with a step indicator: چه کسی → کدام سنجه → تنظیمات → مرور و ارسال | — |
| `W/invites/<aid>` | client visible | Invitation: state, link with copy button and QR, delivery status, timeline, actions (یادآوری، تمدید، لغو) | — |
| `W/campaigns`, `W/campaigns/new`, `W/campaigns/<id>` | `invites:bulk` | List; wizard (گروه یا پیوند باز → سنجه → تنظیمات → مرور); campaign page with counts, list, QR sheet for open links, «بستن» | «برای دعوت یک کلاس یا گروه، دعوت گروهی بسازید.» |
| `W/import` | `clients:import` | Wizard: الگو → بارگذاری → تطبیق ستون‌ها → بررسی → ورود; ends on the job page | — |
| `W/jobs/<id>` | **the requester only**; the download re-checks the permission of that export kind and the re-authentication | Job status with progress, result summary, download or error report. Extra states: در صف، در حال انجام (auto-refresh), آماده, ناموفق (what to do), منقضی («دوباره بسازید») | — |
| `W/exports` | `clients:export` or `results:export` | Choose what to export (cards per kind), recent exports with expiry | «خروجی تازه‌ای ندارید.» |
| `W/reports` | any result permission | Entry to group reports; table of newest results the viewer may open | «هنوز نتیجه‌ای برای نمایش نیست.» |
| `W/reports/group` | `reports:group` | Filters (group or campaign, instrument, period) → counts, distributions with a data table; print | «برای گزارش گروهی دست‌کم ۵ نتیجهٔ به‌اشتراک‌گذاشته‌شده لازم است.» |
| `W/members` | `members:read` | Members table, pending invitations, invite form, link to `/help/roles` | Solo panel: «شما تنها عضو این پنل هستید. همکاری را دعوت کنید یا تنها ادامه دهید.» |
| `W/credits` | `credits:read` | Free-mode banner, usage tiles, committed invitations, history table | «هنوز سنجه‌ای تکمیل نشده است.» |
| `W/audit` | `audit:read` | Filter bar, event table in plain Persian, support-access block, export | «در این بازه رویدادی ثبت نشده است.» |
| `W/settings` | `panel:profile` for مشخصات and تماس; `panel:settings` for the rest | Sections: مشخصات (name, logo, client word) · تماس · شرایط استفاده · مالکیت و بستن پنل. A member with `panel:profile` only sees the first two sections | — |
| `W/settings/transfer`, `W/settings/close` | `panel:transfer`, `panel:close` + re-auth | Confirmation pages | — |
| `/help/panel`, `/help/roles` | signed in | Task help; role table | — |
| `/my/reauth` | signed in | One OTP field (or password), reason line «برای این کار باید دوباره هویت خود را تأیید کنید.» | — |

Routes that already exist and stay as they are: `/panel`, `/panel/terms`, `/my/workspaces/new`,
`/join/<token>`, `/invite/<token>` (extended), `/take/<token>…`, `/signup`, `/my/phone`.
POST endpoints follow the page they belong to (`W/clients/<cid>/archive`, `W/members/<mid>/role`,
…), all with CSRF, all through the helpers of `05_permissions_matrix.md` 9, all redirecting
back with a flash message.

## 4. Page inventory — participant

| Route | Purpose and components | Empty state |
|---|---|---|
| `/my` | Three blocks: «منتظر شما» (invitations accepted but not started; attempts in progress with a progress bar and «ادامه»), «تازه‌ترین نتایج», shortcuts. One primary button per card. Website 4 only; on any other website the stock portal home is returned unchanged | «کاری در انتظار شما نیست. اگر مشاور یا سازمانی شما را دعوت کرده، پیوند دعوت را باز کنید.» + «دیدن سنجه‌ها» |
| `/my/assessments` | Results and attempts table (exists) + sharing state per row | exists |
| `/my/assessments/<id>` | Report (exists) + block «چه کسی این نتیجه را می‌بیند» + «ارسال برای مشاور» | — |
| `/my/sharing` | Per result: each panel (name, responsible specialist, level in words, since), «لغو اشتراک» with a confirmation that says the panel loses access at once; list of views by role and date | «نتیجه‌ای را با کسی به اشتراک نگذاشته‌اید. نتایج شما فقط برای خودتان دیده می‌شود.» |
| `/my/notifications` | List, unread first; «همه خوانده شد»; link to preferences | «اعلانی ندارید.» |
| `/my/account`, `/my/phone`, `/my/security` | Name; verified mobile and SMS choices (exists); password and «خروج از همهٔ دستگاه‌ها» | — |
| `/my/privacy` | What we hold (plain list), «دریافت نسخه‌ای از داده‌های من», «درخواست حذف داده‌ها», state of open requests | — |
| `/invite/<token>` | Who invites (panel name, logo, contact), which assessment, time needed, what the panel will see (level in words), sharing tick, sign-in buttons | invalid states exist (expired, used, declined, withdrawn) |
| `/c/<token>` | Open-link join: same content + a name field; full or closed campaign → «ظرفیت این دعوت تکمیل شده است» / «این دعوت بسته شده است» | — |
| `/take/<token>` (exists) | Player. New states: a stopped attempt shows «این سنجه متوقف شده است» with the panel's contact; an erased one is 404 | — |
| `/my/privacy/jobs/<id>` | The participant's own data-export job (requester only), same job component as the panel's | — |

## 5. Dashboard definitions

Period `P` = last 7, 30 (default) or 90 days, by Tehran date. "Visible" means the clients the
member may see (R0–R3). Every number is a link to the list with the same filter, and the list's
count must equal the tile (tested).

### 5.1 Needs attention (first block; a line appears only when its count > 0)

| Line | Definition (ORM level) | Who | Link |
|---|---|---|---|
| Panel pending approval | `workspace.gated` | all | help anchor |
| Awaiting my verification | member A5 | that member | help anchor |
| Results ready, not opened by me | visible assignments with `state='done'`, `result_level ≥ summary`, and no `result.view` / `assignment.result_view` / `attempt.result_view` audit row by this member for that record | holders of a result permission | `W/invites?state=done&unseen=1` |
| Unassigned clients | `ts.panel.client` active, `responsible_id` empty | `clients:assign` or `read_unassigned` | `W/clients?resp=none` |
| Overdue | assignments in `invited, opened, accepted, in_progress` with `deadline < today` | visible | `W/invites?overdue=1` |
| Expiring in 3 days | same states, `expires_at` within 3 days | visible | `W/invites?expiring=1` |
| Handover requests | open requests | `clients:assign` | `W/clients?handover=1` |
| Colleague invitations waiting | `ts.member.invite` pending and not expired | `members:invite` | `W/members` |
| Terms changed | accepted `terms_version != TERMS_VERSION` | owner | `W/settings` |

### 5.2 KPI tiles

| Tile | Definition | Who | Privacy note |
|---|---|---|---|
| دعوت‌های فرستاده‌شده | assignments created in `P`, `channel != 'self_share'` | all (visible scope) | count only |
| پذیرفته‌شده | assignments with `accepted_at` in `P` | all | |
| تکمیل‌شده | assignments whose attempt has `submitted_at` in `P` and `state='done'` | all | |
| نرخ تکمیل | of assignments created in `P` (not withdrawn): share with `state='done'`; shown as «x از y» | all | shown only when y ≥ 5 |
| میانهٔ زمان تکمیل | median of `submitted_at − started_at` over attempts done in `P` | OW, managers | shown only when n ≥ 5 |
| مراجعان باز من | visible clients with `responsible_id = me` and `open_count > 0` | SP | |
| مصرف این دوره | sum of ledger `units` (`debit_usage` minus `refund`) in `P`; subtitle «رایگان در این فصل» while free | `credits:read` | |
| به‌اشتراک‌نگذاشته | done assignments in `P` with `share_level='none'` | OW, managers | count only; explains missing results |

Funnel (one bar list with a data table): invited → opened → accepted → in progress → done, for
assignments created in `P`. Workload table: per member with `clients:be_responsible`: clients,
open invitations (owner and managers only).

No dashboard shows a score, a band or any inference about a person.

### 5.3 Platform (back-office list and pivot)
Panels by state and purpose; pending approvals and the age of the oldest; panels with at least
one completion in 30 days; completions per panel per month; open data requests and overdue
ones; open support accesses.

## 6. Key flows

### F1 Create a panel (exists; changes marked NEW)
1. `/panel` → «پنل بساز» → sign in by mobile if needed.
2. `/my/workspaces/new`: name, kind (مدرسه یا مؤسسه، سازمان، مرکز بالینی، مستقل), terms tick
   (+ clinical escalation tick).
3. Created: creator is `owner`; solo kinds set `owner_practices` (NEW); a solo psychologist is
   asked for the licence number (NEW) and sees «در انتظار احراز صلاحیت».
4. Lands on the dashboard with the onboarding checklist. Education is active at once; organization and
   clinic show the pending banner and cannot invite participants until approval.

### F2 Invite a colleague
1. `W/members` → «دعوت همکار»: role (from the panel's set, each with a one-line description
   and a link to the role table), mobile or email.
2. Result page: the link with a copy button; note that no message is sent (link only).
3. Colleague opens `/join/<token>`: sees inviter, panel, role; signs in with the invited mobile
   or email; clinicians enter a licence number; accepts.
4. Lands on `W`. Inviter gets `member_joined`. Audit: `member.invite`, `member.invite_accept`.
5. Wrong identity, expired, revoked: existing messages.

### F3 Invite a class (bulk)
1. `W/groups` → create «کلاس نهم الف», add clients by hand or `W/import` (F8).
2. Group page → «دعوت گروه» → campaign wizard: instrument, deadline, note, SMS choice with the
   consent attestation, minors attestation when the group has minors (S16).
3. Review step lists: n to invite, k skipped (already have an open invitation for this
   instrument, archived, or no way to reach them), and what the participants will see.
4. Send → a job when more than 500; campaign page shows counts by state and each personal
   link; printable sheet of links or QR codes per student for classes without phones.
5. Hourly cron expires; daily cron reminds once (INV-8).
6. Alternative: «پیوند باز» creates one link/QR for the whole class; each student signs in,
   types their name, accepts; capped and time-limited.

### F4 Take an assessment (participant)
1. Opens `/invite/<token>` (or `/c/<token>`): sees who, what, how long, who will see what.
2. Signs in by mobile code (one field, paste allowed).
3. Accept with the sharing tick (default on, revocable) or decline.
4. Consent page (minor wording when applicable) → player. Every answer is saved as it is
   given; leaving and returning resumes at the first unanswered item (exists).
5. Review → submit (idempotent) → own report. The responsible member gets
   `result_ready_staff`; the ledger gets one usage row.

### F5 Share a self-taken result with a counselor
1. Report page → «ارسال برای مشاور» → type the panel code.
2. Confirmation page shows the panel's name and what it will see, in the words that match the
   instrument: for TALENT-INV-15 «گزارش نتیجهٔ شما، بدون پاسخ‌هایتان»; for every other
   instrument «فقط بازهٔ هر بُعد (کم، متوسط، زیاد)، بدون نمره و بدون پاسخ‌ها».
3. Confirm → assignment with `channel='self_share'`, client found or created, consent record.
   Only education panels can be reached by code (as today). A share that was revoked can be
   given again.
4. The panel's responsible member (or the unassigned queue) is notified.

### F6 Revoke
1. `/my/sharing` or the report → «لغو اشتراک» → confirmation.
2. `share_level='none'` at once; consent record `share_revoke`; the panel sees the client
   with level `status`; responsible member gets `share_revoked`.

### F7 Export
1. `W/exports` → pick a kind → filters (same as the list; search text is not carried) →
   «ساخت خروجی».
2. Re-authentication if the last one is older than 10 minutes.
3. Job page; when done, download button, expiry shown («تا ۲۴ ساعت»). Each download is audited.
4. After expiry the button is replaced by «منقضی شد؛ دوباره بسازید».

### F8 Import clients
1. `W/import` → download the template (headers: نام، کد، موبایل، ایمیل، گروه، گروه سنی).
2. Upload (limits stated before the button). The file is parsed in a job.
3. Column mapping: detected headers preselected; unmapped columns ignored.
4. Validation: table of rows with errors (row number, field, what is wrong, how to fix); counts
   of new, to update, duplicates inside the file, invalid.
5. Preview of the first 20 valid rows → «ورود n ردیف معتبر».
6. Result: created, updated, skipped; «دانلود گزارش خطا»; optional next step «دعوت همه به سنجه».
7. Running the same file again changes nothing (matched by code, then phone, then email).

### F9 Credit debit
1. Participant submits; attempt scored (`action_submit`).
2. One `ts.usage.event` (written by `ts_panel`'s submit override for every instrument; the
   older hook misses TALENT-INV-15, gap G28) + ledger `debit_usage` with
   `idem_key='usage:<attempt_id>'`.
3. Free mode: `amount=0`, `units=1`. A retry or double click creates nothing new.
4. Platform manager voids an attempt → `refund` once.
5. Daily reconcile compares events and ledger.

### F10 Member leaves
Owner deactivates a member → confirmation shows how many clients return to the unassigned
queue → clients released (existing behaviour), the member loses access at the next request,
owner sees the queue count on the dashboard.

## 7. Optional mockups
Four clickable HTML mockups (owner dashboard, client list, client page with a result,
participant home) can be produced as Design artifacts in the Talent Search visual style before
coding, if the owner asks for them at the Phase 1 gate. They are not required for Phase 2:
stage S2 builds the shell first and the owner can judge the real pages on a clone.
