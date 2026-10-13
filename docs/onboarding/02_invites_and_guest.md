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
- **Headers.** Responses of `/invite/`, `/take/`, `/i/`, `/j/`, `/c/` and `/start` carry `Referrer-Policy: no-referrer` and
  `Cache-Control: no-store`.

**Delivery proof.** `ts.assignment.delivered_via` = sms / email / manual / campaign. sms and email are set by the existing
send paths only when they report success (invitation SMS, invitation e-mail, a reminder by SMS or e-mail);
`delivered_phone` / `delivered_email` keep what the message reached (EOT team only). Copied links and QR codes stay
«manual»; an invitation made by joining an open link or class code is «campaign» (set on create; the data step marks the
earlier ones). Only sms and email are a proof.

**Scoped sign-in, no typing.** A visitor who is not signed in taps the button on an invitation proven by SMS to P (or
e-mail to E): he is signed in as the account of P / E (found, or made as a phone-only portal account with the name unknown —
the panel's name is never copied; an e-mail account is made the same way), browser-session cookie, and the session carries
`ts_scope = {invitation, user, number}`. `ir.http._pre_dispatch` (talentsearch.ir only) lets such a session reach only:
this invitation and its short link, the player of its attempts (`/take/<token>/…`, the timed-task endpoints included), the
participant's own result of those attempts (`/my/assessments/<id>`, `/pdf`, `/unshare`, `/my/assessments/battery/<id>/…`),
static assets, sign-out, `/signup`. Anything else answers 303 to `/signup?next=…` showing the number masked
(«۰۹۱۲***۴۵۶۷», the mask /my/phone already uses: bullets «•••» read as Persian zeros «۰۰۰» in Vazirmatn) with «دریافت
کد»; after the code the session is an ordinary full session. A scoped e-mail account that verifies a number nobody holds
gets that number (one person, one account). Staff or archived accounts are never signed in by a link (the ordinary
sign-in follows). The scoped session follows the normal session rules and is never extended.

**Device binding.** The first accept binds the invitation to this browser: cookie `ts_dev` (signed with the database secret,
HttpOnly, SameSite=Lax, Secure on https, 90 days, one per browser); the server stores only sha256 of its random part
(`device_hash`). A later open of an accepted invitation by a visitor who is not signed in shows «ادامه»: the bound browser
goes on (scoped again, no code); another browser gets «برای ادامه، کدی به ۰۹۱۲***۴۵۶۷ فرستادیم» — a code to the invited
number (the code page never shows the number in full, «ویرایش شماره» is hidden) and after the code it continues. The same
code-first path applies to a manual invitation that has a number. No number and no address: the ordinary sign-in first.

**Mismatch.** A signed-in account that does not hold the invited number sees one notice («این دعوت برای شمارهٔ
۰۹۱۲***۴۵۶۷ فرستاده شده است و شما با حساب دیگری وارد شده‌اید.») and one action «خروج و ورود با شمارهٔ دعوت‌شده» (sign-out
returns to the invitation, whose tap then signs in with the invited number); the POST accepts nothing. An e-mailed
invitation, or one accepted by another account, shows the same notice with «خروج و ادامه با این دعوت» instead of a bare
404. Links without a number keep the old name notice.

**Link hygiene.** New short codes have 12 characters of [a-z0-9]; the 8-character codes of earlier invitations keep
working. Lookups are limited per hashed address and family, then a polite 429 page «کمی صبر کنید» with `Retry-After: 60`:
`/invite/` and the short links `/i/`, `/j/` 60 a minute each, the open class link `/c/` 120 (a whole class opens it from one
school network); parameters `ts_onboard.{invite,short,campaign}_per_minute`. A hit is counted in its own committed
transaction (`ts.rate.hit`, rows kept one day), so the 404 of an unknown code counts too — otherwise guessing would never
slow down. An unknown token or code, or the link of a closed panel, answers one neutral 404 page «این پیوند باز نمی‌شود»
with the same words whatever the reason.

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

**Start screen** (`/start`, `/start/<slug>` for a guest-ok instrument; the detail page's «شروع سنجه» and the catalog card
«شروع بدون ثبت‌نام» link there): what it measures, statements, minutes, «پاسخ‌ها فقط برای خودتان است؛ در پایان با شمارهٔ
موبایل نتیجه را می‌بینید و نگه می‌دارید.», an unticked research box, the button «۱۸ سال یا بیشتر دارم؛ موافقم و شروع
می‌کنم» (adult age and service consent) and «کمتر از ۱۸ سال دارم» → `/start/under-18` (school or counselor, link to
/schools; no guest attempt for minors). «بیشتر بدانید» holds who sees it, 48-hour keeping, saving, limits, support. A
signed-in visitor goes straight into an ordinary attempt (the same one-tap consent; the ledger rows are written at once).

**Guest attempt.** An ordinary `ts.attempt` of the website's public user with `ts_guest`, keyed by the digest of a signed
random token in the HttpOnly SameSite=Lax cookie `ts_guest` (never in an address: the player is `/start/q`, `/start/q/answer`,
`/start/q/page`, `/start/q/review`, `/start/q/submit`, the same templates with `take_url`). Same autosave and player. Limits
per hashed address: 5 new guest attempts an hour (`ts_onboard.guest_per_hour`) and 200 saved answers a minute
(`ts_onboard.answers_per_minute`); one open guest attempt per browser (a second tap returns to it). No panel, no
invitation: never billed, never visible to a panel; nothing is sent at the end. Consent is stored on the attempt; the
ledger rows (service, research) are written at the claim. A forged, malformed or spent cookie reaches nothing.

**Result gate** (`/start/result`): «نتیجه‌تان آماده است.» with the mobile sign-in inline and «شماره‌تان را بزنید تا نتیجه را
ببینید و برای همیشه داشته باشید.» (number, then code, as in onb1). A successful code at the gate claims the attempt
atomically (the row is locked; a second or racing claim finds it claimed and does nothing): re-owned by the account, the
token digest cleared, the cookie dropped; then the report opens (`?submitted=1&claimed=1`). A sign-in anywhere else never
claims it (a shared computer must not hand one person's answers to the next account); the gate then offers one button.
A second result of the same instrument is kept beside the first. The report of a claimed attempt offers «نامی که روی
گزارش بیاید (اختیاری)» (written only while the account has no name: the person's own entry), «سنجهٔ بعدی» and «فرستادن
نتیجه برای مشاورتان» (the existing share by panel code).

**Clean-up.** Hourly cron «پاک‌کردن پاسخ‌های مهمان پس از ۴۸ ساعت»: unclaimed guest attempts of a public user, without a
panel, 48 hours after their last activity, with their answers and results (cascade). Claimed and ordinary attempts are never
touched.

**Entry points.** Home hero: one primary action «شروع سنجهٔ رایگان» → /start, «حدود N دقیقه · بدون ثبت‌نام برای شروع ·
نتیجه فقط برای خودتان» (N from the starter), then three quiet text links «برای مراکز مشاوره» · «برای شرکت‌ها و استخدام» ·
«برای مدرسه‌ها» (/panel, /panel, /schools until release 3 adds audience pages); the rest of the page is unchanged.

**Funnel** (`ts.funnel.event`): step (start_view, start, q1, finish, gate_view, gate_signed_in, report_view, invite_view,
invite_accept), kind of entry (guest, user, or how the invitation came: sms, email, manual, campaign), instrument or
invitation, a salted hash of a random funnel id kept in the session (never the session id, an address, a number or a
name), website, time. The invitation path uses q1 (first answer of its first part) and finish (every part done) with the
invitation set. q1 and finish are counted by the attempt model for every player (one indexed probe at the first answer,
one insert), only for guest attempts, signed-in attempts of a guest-ok instrument and invitations. At most one row per
funnel id, step and target. Back office «سنجش › قیف ورود» (pivot by step and kind of entry, per week; list; platform
managers only). Kept 180 days (daily cron).

## Tests

`tools/prod/tests_onb2.py` (ORM, never commits): delivery proof from the send paths and «campaign», who matches,
12-character codes, rate limit (a rolled-back request still counts), minors, the scope rules on every route family, guest
consent / submit without notices / claim and ledger / clean-up of guest rows only, funnel fields, kinds of entry and
retention, fairness migration, anonymous decline. `tools/prod/ts_http_onb2.py` (HTTP, fake Kavenegar on 18097 + 10 × slot):
GET not consuming, no-referrer and no-store, the neutral page for unknown links, one-tap accept with the device cookie,
answers through the player in the scoped session, the scope on /my, /my/assessments, /my/account, panels, other
invitations, /web, /odoo, the catalog, /start and the share page, the masked code to leave the scope, device binding (same
browser goes on, another gets the masked code), mismatch, e-mail proof, typed number, plain link, anonymous decline, minors'
one screen (and BAT-CHILD-1), fairness at the end, rate limits (short links, /invite/ with unknown tokens counted, /c/),
home hero and its text links, catalog card, start screen, under-18, detail start, guest player without tokens, gate,
claim, name, cross-token isolation (forged, malformed and spent cookies; another account), keep both, one open guest
attempt, guest and answer limits, 48-hour clean-up, no token in any address, funnel (both paths, kinds of entry), eot.ir
404. Older suites updated: ts_http_hire (welcome screen, questions at the end), ts_http_org and ts_http_signup (welcome
screen, notice instead of 404, «ادامه»), ts_http_panel (home hero), tests_brand, ts_http_pv2_6 and ts_http_sms (12-character
codes). Shots matrix: welcome (clinic, employment), minors, /start, under-18, guest player, result gate (`COOKIE name
value` directive in ts_shot.py), masked-code screen, and the claimed report with the optional name
(tools/vps/ts_onb2_seed.py; its own login with the matrix owner's password).

## Notes and decisions

- A visitor who is not signed in and opens an accepted invitation sees «ادامه», not «این دعوت قبلاً استفاده شده است»: he may
  be the invited person on another browser. The tap sends a code to the invited number (or the ordinary sign-in when there
  is none); a stranger gets no further.
- An e-mailed invitation opened later on another browser has no number to send a code to: the ordinary sign-in follows; a
  number verified while the e-mail session was scoped joins that account.
- Odoo's session cookie is not marked Secure by Odoo; the onb2 cookies are (on https).
- Rate limits are higher than the plan's example (30 a minute) for /invite/ and the short links (60) and /c/ (120): a
  class on one school network opens its links within the same minute; 12-character codes keep guessing hopeless.
