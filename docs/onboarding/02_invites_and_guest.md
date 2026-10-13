# onb2 — one-tap invitations and test first (release 2 of onboarding)

Branch `onb2`, module `ts_onboard` (new) plus small changes in ts_sms, ts_assessment, ts_brand, ts_website and ts_hire.
Merged with main after take1 (test-taking UX pass, live 2026-10-13): the welcome screen uses take1's size/time source, its
dead-end cards and its explained link 404. Design: Project doc `claude/ONBOARDING_RESEARCH_AND_DESIGN.md` §4–§5 (P1, P2,
P3, minors) and §8. eot.ir (website 1), the back office and internal users are not changed: every website behaviour is
gated to talentsearch.ir. The independent risk review (3 high, 2 medium, 4 low) is fixed in this branch; see «Risk
review fixes» at the end.

## O2. One-tap invitations

**Welcome screen** (`/invite/<token>`, also reached by `/i/<code>` and the SMS's `/i/<code>/<secret>`): «سلام {first name
the panel wrote}» (or «سلام»), who invites (centre + the responsible counselor when the centre shows counselors on
reports; for employment «{company} برای موقعیت «…» از شما دعوت کرده است.»), time and size from take1's `effort_facts`
(one source for every page) and, outside hiring, «نتیجه بلافاصله پس از پایان آماده است.», «روی کامپیوتر بهتر است (بخش
زمان‌دار)» when the battery has a timed task, what the inviter sees in three lines plus «بیشتر» (the existing full text:
`ts_org.share_box`, or `ts_hire.position_terms` for a position, the parts of a battery, save/stop/support with the crisis
line «اورژانس اجتماعی ۱۲۳ یا صدای مشاور ۱۴۸۰», the optional research box, the consent version), the share tick (ticked, as
before), the small «این دستگاه شخصی من است» (ticked, the same words and hint as the sign-in page), one primary button
«موافقم و شروع می‌کنم» and a quiet «نمی‌خواهم شرکت کنم». Dead ends (expired, declined, withdrawn, paused) use take1's
`invite_card` words in `ts_website.state_card`.

- **GET never consumes, accepts or binds anything** (messenger previews open links). It only marks the invitation as
  opened, as before (the panel says «بازشده», not «خوانده‌شده»).
- **The POST is the consent.** It accepts and records the consent on the first attempt (a battery copies it to every
  instrument) with `CONSENT_VERSION`, and `welcome_version` / `welcome_at` on the invitation; the separate consent page is
  not shown any more for these attempts. A POST without the welcome field (older forms, attempts accepted before the
  release) keeps the old way: sign in, then the consent page.
- **Headers.** Responses of `/invite/`, `/take/`, `/i/`, `/j/`, `/c/` and `/start` carry `Referrer-Policy: no-referrer` and
  `Cache-Control: no-store`, their error pages too (`ir.http._handle_error`).

**Delivery and the delivery secret.** `ts.assignment.delivered_via` = sms / email / manual / campaign: where the system's
message went (set by the send paths only when they report success: invitation SMS, invitation e-mail, a reminder by SMS or
e-mail); `delivered_phone` / `delivered_email` keep what it reached (EOT team only). The panel shows and copies the same
invitation link, so the link alone proves nothing. Every message the system sends carries a fresh **delivery secret**
(16 random bytes, 22 url-safe characters): `/i/<code>/<secret>` in an SMS (the short link redirects to
`/invite/<token>?d=<secret>`), `/invite/<token>?d=<secret>` in an e-mail. Only its digest is stored (`dlv_sms_hash`,
`dlv_email_hash`, administrators only); the secret exists only while the message is rendered (a send window around the
send paths: `invite_url()` / `ts_short_url()` add it inside the window and never outside, so no panel page, copy button, QR
code, export, audit row or log holds it). The SMS row of the Kavenegar log is masked («***», `kv_secret`, as for sign-in
codes), and a row imported from Kavenegar's outbox without a sent-log row keeps the link with `/i/<code>/***` / `d=***`;
the e-mail is auto-deleted after sending; the access log line is redacted (`/i/<code>/***`, `d=***`). The welcome
screen carries the secret as a hidden field of its form; only the POST checks it (constant-time, per channel). A new
message replaces the secret of its channel (an older link then gets a code, as a copied link does); a message that did not
go out keeps the previous one. Copied links and QR codes are «manual»; an invitation made by joining an open link or class
code is «campaign» (set on create; the data step marks the earlier ones).

**Who may be signed in without typing.** Only with a valid delivery secret, and only into an account that
- does not exist yet: made now (a phone-only portal account for an SMS, a portal account for an e-mail; the name unknown —
  the panel's name is never copied; `ts_account_made` on the invitation), or
- is a Talent Search phone-only portal account whose login is exactly the invited number (number verified here, no
  internal access, no eot.ir activity: orders, invoices, payments, events, courses, eot.ir visits, leads, helpdesk
  tickets, survey answers, forum posts, a message the person wrote or was sent on a record outside Talent Search, an
  account bound to another website; a model that is not installed is skipped, a check that cannot run counts as
  activity).
Any other existing account (an e-mail account, one with eot.ir activity, anything our phone flow did not make) and any link
without a valid secret (the panel's copy, a wrong or older secret): a code to the invited number (shown by its last four
digits), then accept; an invitation without a number: the ordinary sign-in (S-AUTH, or e-mail and password). Staff or
archived accounts are never signed in by a link.

**The scope.** A session signed in without typing carries `ts_scope = {invitation, user, number}` and a browser-session
cookie. `ir.http._pre_dispatch`, and `_serve_fallback` for website pages and attachments, enforce it and fail closed:
- seen on any other website than talentsearch.ir (eot.ir), or where the website cannot be told: the session is destroyed at
  once; a GET is sent back to the same address as a visitor, anything else answers 403;
- on talentsearch.ir it reaches only this invitation and its short links, the player of its attempts (`/take/<token>/…`, the
  timed-task endpoints included), the participant's own result of those attempts (`/my/assessments/<id>`, `/pdf`,
  `/unshare`, `/my/assessments/battery/<id>/…`), static assets (never `/web/image` or `/websocket`), sign-out and `/signup`.
  Any other page answers 303 to `/signup?next=…` with the number by its last four digits («*** ۴۵۶۷») and «دریافت کد»;
  anything else (JSON-RPC, `/json`, `/mail`, `/web/dataset`, `/web/session/*`, a POST) answers 403.
After the code the session is an ordinary full session. A number is never linked to or written onto an account from a
scoped session, with one exception: the account the flow made for this invitation within the last hour that holds nothing
else (no other invitation or attempt, membership, other client record, written message, partner link or eot.ir activity).
Otherwise the code for number P signs into P's own account (or makes a phone-only one); the invitation stays where it is,
and one calm page says so (`/my/invitation-elsewhere`: «دعوت در حساب دیگری است», where the invitation is, how to get back).

**Device binding.** The first accept binds the invitation to this browser: cookie `ts_dev` (signed with the database secret,
HttpOnly, SameSite=Lax, Secure on https, one per browser); the server stores only sha256 of its random part (`device_hash`)
and the end of the binding (`device_until`). With «این دستگاه شخصی من است» ticked: 30 days. Unticked: a browser-session
cookie and 12 hours on the server. The binding also ends when the invitation is finished. A later open of an accepted
invitation by a visitor who is not signed in shows «ادامه»: the bound browser (or the message's secret) goes on without a
code when the account may be signed in so (the rules above); anything else gets «برای ادامه، کدی به *** ۴۵۶۷ فرستادیم» —
a code to the invited number — and continues after it. «شمارهٔ دیگری دارم» on that page (and on the masked sign-in of a
scoped session) opens the ordinary sign-in with any number (`/signup?other=1`); the invitation still checks who may accept
it. Every comparison of a token or secret is constant-time.

**Mismatch.** A signed-in account that does not hold the invited number sees one notice («این دعوت برای شمارهٔ *** ۴۵۶۷
فرستاده شده است و شما با حساب دیگری وارد شده‌اید.») and one action «خروج و ورود با شمارهٔ دعوت‌شده» (sign-out returns to
the invitation); the POST accepts nothing. An e-mailed invitation shows the same notice with «خروج و ادامه با این دعوت». An
invitation already accepted by another account answers take1's explained link 404 (`ts_website.page_404`: sign out and sign
in with the invited number), the same page as an unknown token, so nobody learns who holds it. Links without a number keep
the old name notice. A known number is always shown by its last four digits after three asterisks (bullets would read as
Persian zeros in Vazirmatn, seen in the shots); a number the visitor typed is shown in full (it is theirs).

**Link hygiene.** New short codes have 12 characters of [a-z0-9]; the 8-character codes of earlier invitations keep
working. Lookups are limited per hashed address and family, then a polite 429 page «کمی صبر کنید» with `Retry-After: 60`:
`/invite/` and the short links `/i/`, `/j/` 60 a minute each, the open class link `/c/` 120 (a whole class opens it from one
school network); parameters `ts_onboard.{invite,short,campaign}_per_minute`. A hit is counted in the request's own
transaction (`ts.rate.hit`, rows kept one day, no second cursor) under a transaction-scoped advisory lock on the key
(`pg_advisory_xact_lock`), so concurrent requests of one address and family cannot overshoot the limit (they wait for each
other; other keys never do); a miss is answered with the link 404 inside the request
(`invite.counted`), so the hit is committed with it and guessing unknown codes is slowed down too. An unknown token or
code, or the link of a closed panel, answers the one explained link 404 «این پیوند باز نمی‌شود» (status 404, sign-in back
to the link) with the same words whatever the reason.

**Client addresses.** The limits key on `request.httprequest.remote_addr`. On the production server nginx sends Host,
X-Real-IP, X-Forwarded-For (`$proxy_add_x_forwarded_for`), X-Forwarded-Proto and X-Forwarded-Host (eot-tools SEO milestone,
2026-09-29), and Odoo runs with proxy_mode: Odoo 20 applies werkzeug's ProxyFix (x_for=1, x_proto=1, x_host=1) only when
X-Forwarded-Host is present (`odoo/http/router.py`), so remote_addr is the last X-Forwarded-For hop, the one nginx appends
(a client cannot forge it). Evidence on 2026-10-13: robots.txt of talentsearch.ir advertises `https://` (x_proto applied)
and the hashed addresses of onb1's code requests and audit rows on prod are distinct per visitor (3 in 4 code requests,
5–7 a week in the audit), not one shared 127.0.0.1. onb1's code limits (`ts.signup.otp`, per number and per hashed
address) use the same address. No CDN sits in front (DNS-only records). nginx's own access log keeps request lines (the
token and, for the SMS link, the secret) as it does for every link: outside Odoo.

**Fairness questions at the end.** The optional gender and age questions left the invitation page. After the last part of a
position battery the candidate sees them once (`/my/assessments/battery/<id>/about`) before the feedback card, with «رد
شدن». Same fields (`ts_gender`, `ts_age_band`, EOT team only), same use. `ts_fair_asked`; the ts_hire migration marks every
candidate who accepted before the release as asked (they saw the questions on the invitation page). What the employer sees
is take1's one truthful description (factor levels, job-fit summary, integrity signals) everywhere.

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
`/start/q/page`, `/start/q/review`, `/start/q/submit`, the same templates and take1's balanced 5-per-page paging with
`take_url`). Same autosave and player. Limits per hashed address: 5 new guest attempts an hour (`ts_onboard.guest_per_hour`)
and 200 saved answers a minute (`ts_onboard.answers_per_minute`); one open guest attempt per browser (a second tap returns
to it). No panel, no invitation: never billed, never visible to a panel; nothing is sent at the end. Consent is stored on
the attempt; the ledger rows (service, research) are written at the claim. A forged, malformed or spent cookie reaches
nothing.

**Result gate** (`/start/result`): «نتیجه‌تان آماده است.» with the mobile sign-in inline and «شماره‌تان را بزنید تا نتیجه را
ببینید و برای همیشه داشته باشید.» (number, then code, as in onb1). Showing the gate marks its attempt in the session; a code
claims the attempt only when that mark is there and the code was asked for from the gate (`next == /start/result`). The
claim is atomic (the row is locked; a second or racing claim finds it claimed and does nothing): re-owned by the account,
the token digest cleared, the cookie dropped; then the report opens (`?submitted=1&claimed=1`). A sign-in anywhere else
never claims it (a shared computer must not hand one person's answers to the next account); the gate then offers one
explicit button. A second result of the same instrument is kept beside the first. The report of a claimed attempt offers
«نامی که روی گزارش بیاید (اختیاری)» (written only while the account has no name: the person's own entry), «سنجهٔ بعدی» and
«فرستادن نتیجه برای مشاورتان» (the existing share by panel code).

**Clean-up.** Hourly cron «پاک‌کردن پاسخ‌های مهمان پس از ۴۸ ساعت»: unclaimed guest attempts of a public user, without a
panel, 48 hours after their last activity, with their answers and results (cascade). Claimed and ordinary attempts are never
touched.

**Entry points.** Home hero: one primary action «شروع سنجهٔ رایگان» → /start, «حدود N دقیقه · بدون ثبت‌نام برای شروع ·
نتیجه فقط برای خودتان» (N from the starter), then three quiet text links «برای مراکز مشاوره» · «برای شرکت‌ها و استخدام» ·
«برای مدرسه‌ها» (/panel, /panel, /schools until release 3 adds audience pages); the rest of the page is unchanged.

**Funnel** (`ts.funnel.event`, `_log_access = False`): only the step (start_view, start, q1, finish, gate_view,
gate_signed_in, report_view, invite_view, invite_accept), the channel (guest, user, or how the invitation came: sms, email,
manual, campaign), the instrument, a salted hash, and the day and hour (Tehran). No invitation, account, website, address or
create/write user. The hash: a random funnel id kept in the session (never the session id) — but a GET without any cookie
(a first visit, a link preview) writes nothing into a session and is hashed from the hashed address and the minute, so it
counts at most once per address and minute. Obvious robots (empty agent, crawlers, link-preview fetchers such as
WhatsApp, Telegram, Slack, command-line clients) are not counted. q1 and finish are counted by the attempt model for every
player (one indexed probe at the first answer, one insert), only for guest attempts, signed-in attempts of a guest-ok
instrument and invitations (q1 of its first part, finish when every part is done). At most one row per hash, step,
channel and instrument. Back office «سنجش › قیف ورود» (pivot by step and channel, per week; list; platform managers only).
Kept 180 days (daily cron). Odoo itself still answers a first visit with a session cookie; the session is only stored when
something writes into it, and the funnel no longer does for cookie-less GETs.

## Tests

`tools/prod/tests_onb2.py` (ORM, never commits): delivery from the send paths and «campaign»; the delivery secret (plain
links outside a send window, one secret per channel inside, digests only, per-channel proof, a failed message keeps the old
secret, a new one replaces it, the Kavenegar row masked, the access log redacted); who may be signed in without a code (new
number, phone-only account, an e-mail account holding the number, eot.ir activity as a visit or a bound website, «_» is not
a wildcard, an existing address, «made here» within the hour and only while it holds nothing else); who matches; the
four-digit mask; 12-character codes; rate limits (no second cursor); minors and the device choice in the consent; the scope
rules on every route family (JSON, images, websocket, pages included); guest consent / submit without notices / claim and
ledger / clean-up of guest rows only; funnel fields (no invitation, website or access columns), channels, retention by day,
robots; fairness migration; anonymous decline.

`tools/prod/ts_http_onb2.py` (HTTP, fake Kavenegar on 18097 + 10 × slot; the invitation SMS goes through it, the e-mail is
rendered from the real template and never sent): GET not consuming, no-referrer and no-store, the explained 404 for unknown
links (also with a secret), the SMS link with its secret and the e-mail link with theirs, the secret nowhere on the server
(Kavenegar log, audit, messages, mails, SMS, invitations, funnel), the welcome form's hidden field and the device tick; the
panel's copied link and a wrong secret get a code and no session; one tap with the secret (30-day cookie); answers through
the player in the scoped session; the scope on /my, /my/assessments, /my/account, panels, other invitations, /web, /odoo,
the catalog, /start, the share page, JSON-RPC, /json/2, /mail/data, /web/image, /websocket and a website page; the session
taken to eot.ir is destroyed; the masked code to leave the scope; device binding (same browser goes on, another gets the
masked code, «شمارهٔ دیگری دارم» accepts nothing for another number; unticked: a session cookie and 12 hours; the binding
ends when the invitation is finished); mismatch with the four-digit mask; an invitation accepted by another account (404);
e-mail one tap for a new address, an e-mail-scoped session cannot attach a number to an older account (the calm page), the
fresh-account exception; the panel's copy of an e-mail invitation (sign-in); typed number; plain link; anonymous decline;
minors' one screen (and BAT-CHILD-1); fairness at the end; rate limits (short links, /invite/ with unknown tokens counted,
/c/); home hero, catalog card, start screen, under-18, detail start, guest player without tokens, gate, claim, name,
cross-token isolation, keep both, one open guest attempt, guest and answer limits, a sign-in outside the gate claims nothing
(then the explicit button), 48-hour clean-up, no token in any address, funnel (both paths, channels, robots, cookie-less
visits), eot.ir 404. Older suites updated: ts_http_hire, ts_http_org, ts_http_signup, ts_http_panel, tests_brand,
ts_http_pv2_6 (12-character codes; the SMS link with its secret, never on the panel page) and ts_http_sms (the SMS link with
its secret). Shots matrix: welcome (clinic, employment; with the device tick), minors, /start, under-18, guest player,
result gate (`COOKIE name value` directive in ts_shot.py), masked-code screen, and the claimed report with the optional
name (tools/vps/ts_onb2_seed.py; its own login with the matrix owner's password); `ts shots DB take` includes the onb2
screens too.

## Notes and decisions

- A visitor who is not signed in and opens an accepted invitation sees «ادامه», not the link 404: he may be the invited
  person on another browser. The tap sends a code to the invited number (or the ordinary sign-in when there is none); a
  stranger gets no further.
- An e-mailed invitation opened later on another browser has no number to send a code to: the e-mail's own link (its
  secret) goes on for an account the flow made for it; anything else gets the ordinary sign-in.
- Odoo's session cookie is not marked Secure by Odoo; the onb2 cookies are (on https). Odoo adds a one-year Expires to every
  cookie unless told otherwise: the onb2 cookies always give theirs (30 days, or none for a browser-session cookie).
- Rate limits are higher than the plan's example (30 a minute) for /invite/ and the short links (60) and /c/ (120): a
  class on one school network opens its links within the same minute; 12-character codes keep guessing hopeless.
- The SMS link with its secret is about 61 characters (`https://talentsearch.ir/i/` + 12 + `/` + 22), longer than the 34
  of docs/clinic/05_sms_texts.md rule 2: ts_brand's drop order (counselor, minutes, deadline, then the `_short` template)
  still keeps the institution name and the link; an invitation SMS may take one part more.
- The clone's threaded server refuses every websocket upgrade itself (400); on production websockets go through the gevent
  port, which dispatches through the same ir.http and its scope guard.
- A page of a scoped session never starts the website bus: its frontend session info has no `bus_info`, so the bus service
  does not open /websocket at all (no connection attempt, no reconnect loop, no 303).

## Risk review fixes (2026-10-13)

| # | Finding | Fix |
|---|---|---|
| H1 | The panel shows the link the SMS/e-mail carries, so a staff member could sign in as the invitee | Delivery secret only in the system's own message; no-typing sign-in needs it and only into a new or phone-only account; a copied link gets a code |
| H2 | An e-mail-scoped session could write a number onto an existing account | Never from a scoped session, except the account made for this invitation within the hour holding nothing else; otherwise P's own account and the calm page |
| H3 | The scope check skipped other websites | Fails closed: any other or unknown website destroys the session; JSON and non-GET answer 403; website pages through `_serve_fallback` too |
| M1 | `=ilike` on the e-mail let `%`/`_` act as wildcards | Escaped, then an exact lower-case comparison |
| M2 | Device cookie bound every browser for 90 days | Only when «این دستگاه شخصی من است» is ticked (30 days); otherwise a session cookie and 12 hours; ends when finished; constant-time comparisons |
| L1 | /websocket and /web/image in the allow-list | Removed; website pages guarded |
| L2 | The mask showed the operator prefix | Last four digits only («*** ۴۵۶۷») on the sign-in, welcome and mismatch screens |
| L3 | The claim needed only next=/start… | Needs the gate's session mark and next == /start/result |
| L4 | Funnel rows held the invitation, website and access columns; robots counted; a second cursor for rate hits | Step, channel, instrument, hash, day/hour only; robots and cookie-less repeats skipped; hits in the request's own transaction with the 404 rendered inside it |
