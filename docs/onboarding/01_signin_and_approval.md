# onb1 — sign-in (S-AUTH) and panels without approval

Release 1 of the onboarding work (branch `onb1`). Owner decisions of 2026-10-12: every panel is active the moment it is
made; the risk that approval used to cover is handled by a first-week invitation limit, a super-admin suspend and a
back-office list of new panels; the licence number becomes a badge; talentsearch.ir has one mobile sign-in.
eot.ir (website 1), the back office and internal users are not changed.

## A. Panels without approval

| Before | Now |
|---|---|
| `pilot` state, `gated` for employment/clinical, approve/reject buttons, «در انتظار تأیید» banners and pages | States `draft / active / suspended («متوقف») / closed`. Self-service panels are `active` and `self_service = True` at creation |
| Admins e-mailed about each new panel | A log note on the panel (no e-mail). Back office «پنل‌های تازه (۷ روز)» (group_ts_manager) opens on the 7-day filter: created, kind, state, self-service, owner, members, open invitations, results in 30 days, age |
| Approval gated participant invitations (the HR position invite was blocked) | Invitations work at once everywhere, including HR positions |

**First-week limit.** A self-service panel in its first 7 days creates at most 50 invitations per 24 hours
(`ts_panel.new_panel_daily_invites`, default 50). It counts every invitation surface: invite wizard, list campaigns
(a batch that does not fit is refused whole, before anything is made), HR positions (the typed lines come back in the
form), the old invite form. Not counted: self-joins through a class/open link (they have their own caps), a person
sharing his own result, imported past results (an import brings results in; it sends no invitation). Panels made in
the back office have no limit. Forms show one calm line with Persian digits («… امروز ۱۲ دعوت دیگر ممکن است.»).

**Suspend (super admin only).** Back-office buttons «توقف موقت پنل» (with a note) and «ادامهٔ کار پنل». While suspended:
members see «این پنل موقتاً متوقف شده است…» instead of the panel; no invitation, campaign, import or colleague
invitation can be made; an open invitation shows «این دعوت فعلاً در دسترس نیست» and cannot start a new attempt;
participants keep their own results; owners get an in-app notice (SMS only if they opted in). Audit:
`workspace.suspend` / `workspace.resume`. A suspended or closed panel sends nothing else: no automatic or manual
reminder, no staff SMS (except the suspension notice), no HR e-mail, no invitation SMS, no result-ready SMS.

**Migration** (`ts_core` 20.0.2.0.0, pre-migrate): every `pilot` panel becomes `active` with one audit row
(`workspace.state`, `{"from": "pilot"}`), draft/suspended/closed panels are untouched (live: workspace 7 → active,
workspace 2 stays closed); members `pending` without a licence number → `not_required`, a number with no state →
`pending`. Post-migrate marks panels with an audit `workspace.self_create` as self-service and lists owners of
counseling centers who already counsel for a licence review. Idempotent.

**Licence badge.** Optional at join (clinician, clinic director). An owner who ticks «در این مرکز مشاوره می‌کنم» and a
solo psychologist give a number (self-declared; it opens full reports at once, unverified) and the panel appears in the
back-office list «مالک مشاور شد (بررسی پروانه)» with an audit row. The member edits his own number on
his identity page (Persian digits normalised); any change resets the badge to «ثبت‌شده، هنوز تأیید نشده». The super
admin's «تأیید پروانه» sets «پروانهٔ تأییدشده» (who, when); «تأیید نشد» only hides the badge. Reports print the number
only when verified. The badge never gates work; the separate «verify» waiting page is gone. A5b stays: the owner of a
counseling center who does not counsel never sees the full report, and the dashboard says so in words.

Panel terms v4 (`panel-terms-1405-07-v4`), consent text v5 (`TS-CONSENT-1405-07-20-v5`, «مشاوران همین مرکز»).

## B. S-AUTH — one sign-in for talentsearch.ir

- **Entry points.** Header «ورود» → `/signup` (title «ورود یا ثبت‌نام»; `/login` is an alias). Public «شروع سنجه»
  and every sign-in redirect (`/web/login?redirect=…`) land on it with `next=`. `/web/login` on website 4 renders the
  same page in place; `/web/login?email=1` is the e-mail sign-in, linked quietly as «با ایمیل ثبت‌نام کرده بودید؟».
  `/web/signup` on website 4 leads to `/signup`, except for Odoo signup tokens and colleague invitations bound to an
  e-mail (`redirect=/join/…`), which still need it.
- **Two states, one page.** Number (`type=tel`, `inputmode=numeric`, `autocomplete=tel`, ltr, Persian digits and +98
  accepted) and «این دستگاه شخصی من است» (ticked); then code (`autocomplete=one-time-code`, 6 digits, Persian digits
  and spaces accepted, auto-submit at 6 digits), «ویرایش شماره», resend countdown from the server cooldown, «کد نرسید؟»
  help after two resends, inline errors. With JavaScript the same endpoints answer JSON (`X-TS-Auth: 1`) and the page
  switches without reload; without it every step is a normal POST + redirect. WebOTP (`navigator.credentials.get`)
  fills the code on Android Chrome.
- **SMS.** `استعدادیاب` / `کد ورود: 123456` / `این کد را به کسی ندهید.` / `@talentsearch.ir #123456` (≤ 140
  characters, last line for WebOTP; the /my/phone code says «کد تأیید شماره»). With a Kavenegar lookup template set in
  settings the code goes through `verify/lookup` (see owner actions).
- **No name step.** A new number gets an account straight after the code; `name` holds the formatted number for the
  back office and `ts_name_unknown` is set. The site never shows the number as a name (`ts_known_name()`); the name is
  asked where others see it: panel creation, joining a panel, sharing with a counselor («نام شما»), the account page.
  Accepting a participant invitation never copies the panel-typed name into the account: the panel keeps seeing its
  own `invitee_name` / participant record, reports for staff use that, and the account's name is set only by the person.
  A member is never created for an account without a name.
- **Session length.** Portal sign-in by code on website 4: ticked → 30-day cookie (`Max-Age=2592000`, renewed when
  Odoo re-issues it; the session file survives the 7-day clean-up up to 30 days); unticked → browser-session cookie.
  The long cookie needs the flag AND a portal account AND talentsearch.ir (`cookie_mode`); every password sign-in and
  every sign-out clears the flag; the session id is rotated at the code sign-in (Odoo's `finalize`, tested).
  E-mail sign-in, eot.ir and internal users keep Odoo's own cookie and lifetime.
- **Accounts.** One number, one account: `/my/phone` never reveals that another account holds a number — the send
  answers exactly as for any number (cooldown and limits first), no SMS goes out, and every code is refused with the
  neutral «این کد پذیرفته نشد…». An e-mail account without a mobile is offered once on «/my» to link one. A number held
  by an internal (staff) account is never signed in by code: «این شماره به حساب کارکنان وصل است؛ از ورود با ایمیل
  استفاده کنید.» An inactive account says so.
- **Limits.** Unchanged per-number and per-IP hourly limits and the 60 s cooldown; 5 tries per code; a new code does not
  reset the count; 10 wrong codes for one number from one address lock it for that address for 15 minutes; 30 wrong
  codes for one number within 24 hours from anywhere lock it everywhere for 1 hour (`ts.signup.lock`).
- **Return paths.** One validator (`ts_core/safe_url.py`) for every `next` / `redirect` on talentsearch.ir; the page
  script only navigates to a path that passes the same rules.
- **E-mail sign-up.** `/web/signup` (GET and POST) makes no account on talentsearch.ir except for Odoo signup tokens
  and `/join/…` e-mail invitations.

## Deviations and notes

- `/web/signup` stays reachable on website 4 for `/join/…` e-mail invitations and Odoo signup tokens (an e-mail-bound
  colleague invitation cannot be accepted by a mobile account).
- The 30-day session is done without touching Odoo's global session lifetime: only sessions that carry
  `ts_session_mode = 'long'` get the long cookie and survive the clean-up.
- Old in-app notifications of type «پنل تأیید شد / نشد» stay readable; nothing new of those types is sent.

## Owner actions

1. **Kavenegar lookup template** (optional, faster delivery on service lines): in the Kavenegar panel create a
   verification template whose text ends with the WebOTP line, e.g.
   `استعدادیاب\nکد ورود: %token\nاین کد را به کسی ندهید.\n@talentsearch.ir #%token`, wait for Kavenegar's approval,
   then in Odoo Settings → Kavenegar: tick «Advanced service (Verify Lookup)», sync the templates so this one shows
   as Approved, and choose it under «Talent Search SMS» → OTP template. The lookup is used only when all three hold;
   until then the plain send goes out with the same text.
2. After the ship: look at «پنل‌های تازه (۷ روز)» daily for the first weeks; suspend with a note if a panel misuses
   invitations.

## Tests

`tools/prod/tests_onb1.py` (ORM, never commits): no approval, the migration on synthetic rows, the limit (campaign
batch refused whole, open-link joins not counted, after the first week, the setting), suspend, the licence badge,
S-AUTH models (Persian digits, lock, cooldown, SMS text and WebOTP line, phone ownership, unknown names, session
clean-up). `tools/prod/ts_http_onb1.py` (HTTP, fake Kavenegar on 18094 + 10 × slot): pages and redirects on both sites,
the JSON states, cookie lengths, e-mail sign-in cookie on both sites, staff numbers, lock, help, /my/phone, the offer,
names, the HR position limit with refill, suspend pages, the badge. Both are registered in `tools/vps/ts_rehearse.sh`.
