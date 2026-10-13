# onb2 — one-tap invitations and test first (release 2 of onboarding)

Branch `onb2`, module `ts_onboard` (new) plus small changes in ts_sms, ts_assessment, ts_brand, ts_website and ts_hire.
Design: Project doc `claude/ONBOARDING_RESEARCH_AND_DESIGN.md` §4–§5 (P1, P2, P3, minors) and §8. eot.ir (website 1),
the back office and internal users are not changed: every website behaviour is gated to talentsearch.ir.

## O2. One-tap invitations

**Welcome screen** (`/invite/<token>`, also reached by `/i/<code>`): «سلام {first name the panel wrote}» (or «سلام»), who
invites (centre + the responsible counselor when the centre shows counselors on reports; for employment «{company} برای
موقعیت «…» از شما دعوت کرده است.»), minutes and parts (or statements), «روی کامپیوتر بهتر است (بخش زمان‌دار)» when the
battery has a timed task, what the inviter sees in three lines plus «بیشتر» (the existing full text: `ts_org.share_box`, or
`ts_hire.position_terms` for a position, the parts of a battery, save/stop/support, the optional research box, the consent
version), the share tick (ticked, as before), one primary button «موافقم و شروع می‌کنم» and a quiet «نمی‌خواهم شرکت کنم».

- **GET never consumes, accepts or binds anything** (messenger previews open links). It only marks the invitation as
  opened, as before (the panel says «بازشده», not «خوانده‌شده»).
- **The POST is the consent.** It accepts and records the consent on the first attempt (a battery copies it to every
  instrument) with `CONSENT_VERSION`, and `welcome_version` / `welcome_at` on the invitation; the separate consent page is
  not shown any more for these attempts. A POST without the welcome field (older forms, attempts accepted before the
  release) keeps the old way: sign in, then the consent page.
- **Responses** of `/invite/`, `/take/`, `/i/`, `/j/`, `/c/` and `/start` carry `Referrer-Policy: no-referrer`.

**Delivery proof.** `ts.assignment.delivered_via` = sms / email / manual, set by the existing send paths only when they
report success (invitation SMS, invitation e-mail, a reminder by SMS or e-mail); `delivered_phone` / `delivered_email` keep
what the message reached (EOT team only). Copied links, QR codes and open links stay «manual».

**Scoped sign-in, no typing.** A visitor who is not signed in taps the button on an invitation proven by SMS to P (or
e-mail to E): he is signed in as the account of P / E (found, or made as a phone-only portal account with the name unknown —
the panel's name is never copied; an e-mail account is made the same way), browser-session cookie, and the session carries
`ts_scope = {invitation, user, number}`. `ir.http._pre_dispatch` (talentsearch.ir only) lets such a session reach only:
this invitation and its short link, the player of its attempts (`/take/<token>/…`, the timed-task endpoints included), the
participant's own result of those attempts (`/my/assessments/<id>`, `/pdf`, `/unshare`, `/my/assessments/battery/<id>/…`),
static assets, sign-out, `/signup`. Anything else answers 303 to `/signup?next=…` showing the number masked
(«۰۹۱۲***۴۵۶۷», the mask /my/phone already uses: bullets «•••» read as Persian zeros «۰۰۰» in Vazirmatn) with «دریافت
کد»; after the code the session is an ordinary full session. A scoped e-mail account that
verifies a number nobody holds gets that number (one person, one account). Staff or archived accounts are never signed in
by a link (the ordinary sign-in follows).

**Device binding.** The first accept binds the invitation to this browser: cookie `ts_dev` (signed with the database secret,
HttpOnly, SameSite=Lax, Secure on https, 90 days, one per browser); the server stores only sha256 of its random part
(`device_hash`). A later open of an accepted invitation by a visitor who is not signed in shows «ادامه»: the bound browser
goes on (scoped again, no code); another browser gets «برای ادامه، کدی به ۰۹۱۲***۴۵۶۷ فرستادیم» — a code to the invited
number (the code page never shows the number in full, «ویرایش شماره» is hidden) and after the code it continues. The same
code-first path applies to a manual invitation that has a number. No number and no address: the ordinary sign-in first.

**Mismatch.** A signed-in account that does not hold the invited number (or address) sees one notice («این دعوت برای شمارهٔ
۰۹۱۲***۴۵۶۷ فرستاده شده است و شما با حساب دیگری وارد شده‌اید.») and one action «خروج و ادامه با این دعوت»; the POST
accepts nothing. An invitation accepted by another account shows the same notice instead of a bare 404. Links without a
number keep the old name notice.

**Short links.** New codes have 12 characters of [a-z0-9]; the 8-character codes of earlier invitations keep working.
`/i/`, `/j/` and the open link `/c/` are limited per hashed address: 30 lookups a minute (`ts_onboard.short_per_minute`),
then a polite 429 page «کمی صبر کنید» with `Retry-After: 60` (`ts.rate.hit`, rows kept one day).

**Fairness questions at the end.** The optional gender and age questions left the invitation page. After the last part of a
position battery the candidate sees them once (`/my/assessments/battery/<id>/about`) before the feedback card, with «رد
شدن». Same fields (`ts_gender`, `ts_age_band`, EOT team only), same use. `ts_fair_asked`; the ts_hire migration marks every
candidate who accepted before the release as asked (they saw the questions on the invitation page).

**Minors: one screen.** The welcome screen carries the guardian tick and, for a minor client who answers himself, the
button is his own «من هم موافقم». A child instrument (BAT-CHILD-1: the parent answers) has the parent's tick and the
ordinary button; there is never a second consent screen. Ledger rows: service (+ research), share, and for a minor client
`guardian` (given as guardian) + `assent` (text version `TS-MINOR-1405-07-22-v3`).

«نمی‌خواهم شرکت کنم» works without an account: the invitation is declined without tying it to any account, the panel's hold
is released as for any decline.

## O3. Test first for individuals

**Starter instrument** (`ts.instrument.ts_guest_ok`, «شروع بدون حساب»). Only a published adult, general (not employment,
not invite-only), single-mode questionnaire of at most 40 statements may carry it (constraint). The data step sets it once
on **inventory_002 «فهرست ارجمندی»** (17 statements, about 3 minutes, four factors: بالندگی، خودکامیابی، درست‌زیستی،
وجاهت). Choice, from the live catalog: the shorter instruments are a distress screen (inventory_007 «فهرست پاکزیستی»,
4 statements, category «بیتابی روانی»: clinical risk), three employment questionnaires (inventory_014/032/036) and the
talent inventory (TALENT-INV-15, excluded); inventory_019 «فهرست درستی» has the same 17 statements but sits in «بیتابی
روانی». inventory_002 reads as a general self-worth questionnaire (no risk item). `ts.instrument.ts_starter()` answers
«سنجهٔ آغاز» (`ts_onboard.starter_code`, default inventory_002). A later back-office change of the flag is never undone.

**Start screen** (`/start`, `/start/<slug>` for a guest-ok instrument; the detail page's «شروع سنجه» links there): what it
measures, statements, minutes, «پاسخ‌ها فقط برای خودتان است؛ در پایان با شمارهٔ موبایل نتیجه را می‌بینید و نگه می‌دارید.»,
an unticked research box, the button «۱۸ سال یا بیشتر دارم؛ موافقم و شروع می‌کنم» (adult age and service consent) and
«کمتر از ۱۸ سال دارم» → `/start/under-18` (school or counselor, link to /schools; no guest attempt for minors). «بیشتر
بدانید» holds who sees it, 48-hour keeping, saving, limits, support. A signed-in visitor goes straight into an ordinary
attempt (the same one-tap consent; the ledger rows are written at once).

**Guest attempt.** An ordinary `ts.attempt` of the website's public user with `ts_guest`, keyed by the digest of a signed
random token in the HttpOnly SameSite=Lax cookie `ts_guest` (never in an address: the player is `/start/q`, `/start/q/answer`,
`/start/q/page`, `/start/q/review`, `/start/q/submit`, the same templates with `take_url`). Same autosave and player. Limits:
3 new guest attempts per hashed address per hour (`ts_onboard.guest_per_hour`), one open guest attempt per browser (a
second tap returns to it). No panel, no invitation: never billed, never visible to a panel; nothing is sent at the end.
Consent is stored on the attempt; the ledger rows (service, research) are written at the claim.

**Result gate** (`/start/result`): «نتیجه‌تان آماده است.» with the mobile sign-in inline and «شماره‌تان را بزنید تا نتیجه را
ببینید و برای همیشه داشته باشید.» (number, then code, as in onb1). A successful code claims the attempt: re-owned by the
account, the token digest cleared, the cookie dropped; then the report opens (`?submitted=1&claimed=1`). A second result of
the same instrument is kept beside the first. The report of a claimed attempt offers «نامی که روی گزارش بیاید (اختیاری)»
(written only while the account has no name: the person's own entry), «سنجهٔ بعدی» and «فرستادن نتیجه برای مشاورتان»
(the existing share by panel code). Someone already signed in (another tab) keeps it with one button.

**Clean-up.** Hourly cron «پاک‌کردن پاسخ‌های مهمان پس از ۴۸ ساعت»: unclaimed guest attempts of a public user, without a
panel, 48 hours after their last activity, with their answers and results (cascade). Claimed and ordinary attempts are never
touched.

**Entry points.** Home hero: primary «شروع سنجهٔ رایگان» → /start, «حدود N دقیقه · بدون ثبت‌نام برای شروع · نتیجه فقط برای
خودتان» (N from the starter), «ساخت پنل رایگان» stays as the quiet second action; the rest of the page is unchanged (release
3 redesigns it). The detail page of a guest-ok instrument starts without a sign-in.

**Funnel** (`ts.funnel.event`): step (start_view, start, q1, finish, gate_view, gate_signed_in, report_view, invite_view,
invite_accept), instrument or invitation, a salted hash of a random funnel id kept in the session (never the session id, an
address, a number or a name), website, time. At most one row per funnel id, step and target. Back office «سنجش › قیف ورود»
(pivot by step and week, list; platform managers only). Kept 180 days (daily cron).

## Tests

`tools/prod/tests_onb2.py` (ORM, never commits): delivery proof from the send paths, who matches, 12-character codes, rate
limit, minors, the scope rules on every route family, guest consent / submit without notices / claim and ledger / clean-up
of guest rows only, funnel fields and retention, fairness migration, anonymous decline. `tools/prod/ts_http_onb2.py` (HTTP,
fake Kavenegar on 18097 + 10 × slot): GET not consuming, one-tap accept with the device cookie, the scope on /my, /my/
assessments, /my/account, panels, other invitations, /web, /odoo, the catalog, /start and the share page, the masked code to
leave the scope, device binding (same browser goes on, another gets the masked code), mismatch, e-mail proof, typed number,
plain link, anonymous decline, minors' one screen (and BAT-CHILD-1), fairness at the end, short-link and guest rate limits,
start screen, under-18, detail start, guest player without tokens, gate, claim, name, keep both, one open guest attempt,
48-hour clean-up, no token in any address, funnel, eot.ir 404. Older suites updated: ts_http_hire (welcome screen,
questions at the end), ts_http_org and ts_http_signup (welcome screen, notice instead of 404, «ادامه»), tests_brand,
ts_http_pv2_6 and ts_http_sms (12-character codes). Shots matrix: welcome (clinic, employment), minors, /start, under-18,
guest player, result gate (`COOKIE name value` directive in ts_shot.py), masked-code screen (tools/vps/ts_onb2_seed.py).

## Notes and decisions

- A visitor who is not signed in and opens an accepted invitation sees «ادامه», not «این دعوت قبلاً استفاده شده است»: he may
  be the invited person on another browser. The tap sends a code to the invited number (or the ordinary sign-in when there
  is none); a stranger gets no further.
- An e-mailed invitation opened later on another browser has no number to send a code to: the ordinary sign-in follows; a
  number verified while the e-mail session was scoped joins that account.
- Odoo's session cookie is not marked Secure by Odoo; the onb2 cookies are (on https).
