# استعدادیاب: final SMS texts (Phase 5, 2026-10-12)

Written by `ts-ux-writer` for `docs/clinic/01_architecture.md` §6 (SMS via native `sms.template`). Owner approves;
the implementer creates one `sms.template` per key (xmlids in `ts_sms`) and maps the variables. Voice and terms:
`docs/ux_writing/voice.md`, `docs/ux_writing/glossary.md`. Code is not edited by this document.

## 0. How the numbers were counted

- Any Persian letter makes the whole SMS UCS-2: **70 characters for one part; 67 per part when split** (2 parts = 134,
  3 parts = 201). Every newline, space, نیم‌فاصله (U+200C), «ٔ» (U+0654 in «سنجهٔ»، «نتیجهٔ»), «٬» and «» counts as 1.
- Link = **34 characters** (`https://talentsearch.ir/i/abcdef` form). **The links the code builds today are much
  longer**: `/invite/<32 hex>` = 63, `/join/<32 hex>` = 61, `/my/workspaces/<id>/credits` ≈ 50. With those, no message
  below fits one part. A short-link route (≤ 34 characters) is a precondition (rule 2).
- Sample values used for every count: institution «مرکز مشاوره آوا» (15)، school «دبیرستان فرزانگان» (17)، counselor
  «دکتر سارا رضایی» (15)، deadline «۲۵ مهر» (6)، count «۳»، minutes «۴۰»، amount «۱٬۲۵۰٬۰۰۰ تومان» (15)، cap
  «۵۰۰٬۰۰۰ تومان» (13)، role «مشاور مرکز» (10)، code `123456`، validity «۵».
- «ثابت» = the template's own characters (everything except variables), so the implementer can recompute:
  total = ثابت + link (34) + the variables' real lengths.
- Layout of every message: **line 1 = sender name alone** (no colon, no quotes; a newline costs 1 character, «: » costs
  2), line 2 = the message, line 3 = the link alone. OTP has no link.

## 1. Summary

| # | key | sender (line 1) | sample total | parts | ثابت (+34 link) | longest sender name that still fits 1 part / 2 parts |
|---|---|---|---|---|---|---|
| 1 | invite_single (الف: no counselor, no deadline) | institution | 67 | **1** | 18 + 34 | 18 / 82 |
| 1 | invite_single (د: counselor + deadline) | institution | 110 | 2 | 40 + 34 | — / 39 |
| 2 | invite_battery (الف) | institution | 81 | 2 | 29 + 34 | — / 68 |
| 2 | invite_battery (د: counselor + deadline) | institution | 124 | 2 | 51 + 34 | — / 25 |
| 3 | invite_student (الف) | school | 68 | **1** | 17 + 34 | 19 / 83 |
| 3 | invite_student (د: counselor + deadline) | school | 110 | 2 | 38 + 34 | — / 41 |
| 4 | reminder (with deadline) | institution | 70 | **1** | 15 + 34 | 15 / 79 |
| 4 | reminder (no deadline) | institution | 68 | **1** | 19 + 34 | 17 / 81 |
| 5 | result_ready_client | «استعدادیاب» | 66 | **1** | 32 + 34 | — |
| 6 | result_ready_staff | «استعدادیاب» | 68 | **1** | 34 + 34 | — |
| 7 | low_balance | «استعدادیاب» | 129 | 2 | 65 + 34 | panel name ≤ 20 in 2 parts |
| 8 | cap_reached | «استعدادیاب» | 112 | 2 | 50 + 34 | panel name ≤ 37 in 2 parts |
| 9 | member_invite | institution | 116 | 2 | 57 + 34 | 33 (role ≤ 10) / 26 (role 17) |
| 10 | panel_approved / rejected / suspended | «استعدادیاب» | 62 / 63 / 61 | **1** | 28 / 29 / 27 + 34 | — |
| 11 | otp_signup / otp_phone | «استعدادیاب» | 51 | **1** | 44 (no link) | — |

## 2. The texts

Templates are Odoo `inline_template` bodies (`{{ … }}` = a Python expression). Variable names are proposals
(`ts_sms_*` helpers on the bound model); the implementer maps them. Line breaks in the body are literal `\n` with no
indentation and nothing after the link.

### 1. invite_single — a counseling center invites a participant to one instrument

Bound model: `ts.assignment` (no `battery_id`). Replaces `_ts_invite_sms_body()` in `ts_sms/models/assignment.py`.

```
{{ object.ts_sms_org }}
{{ (object.ts_sms_counselor + ' یک سنجه برایتان فرستاده‌اند') if object.ts_sms_counselor else 'یک سنجه برای شما' }}{{ ('، مهلت تا ' + object.ts_sms_deadline) if object.ts_sms_deadline else '' }}
{{ object.ts_sms_link }}
```

| case | rendered (sample) | chars | parts |
|---|---|---|---|
| الف no counselor, no deadline | مرکز مشاوره آوا⏎یک سنجه برای شما⏎{link} | 67 | 1 |
| ب deadline only | مرکز مشاوره آوا⏎یک سنجه برای شما، مهلت تا ۲۵ مهر⏎{link} | 83 | 2 |
| ج counselor only | مرکز مشاوره آوا⏎دکتر سارا رضایی یک سنجه برایتان فرستاده‌اند⏎{link} | 94 | 2 |
| د counselor + deadline | مرکز مشاوره آوا⏎دکتر سارا رضایی یک سنجه برایتان فرستاده‌اند، مهلت تا ۲۵ مهر⏎{link} | 110 | 2 |

| variable | meaning |
|---|---|
| `object.ts_sms_org` | `workspace_id.public_name`, falling back to `workspace_id.name` |
| `object.ts_sms_counselor` | the responsible member's name as shown on the report header (may carry «دکتر» if the member wrote it); empty when there is none |
| `object.ts_sms_deadline` | Jalali day + month name in Persian digits, «۲۵ مهر»; add the year only when it is not the current Jalali year («۲۵ مهر ۱۴۰۶»); empty when there is no deadline |
| `object.ts_sms_link` | short link to the invitation (≤ 34) |
| `object.instrument_id.name` | available, **not used** (rule 1: instrument names can reveal a counseling topic) |

Rationale: the institution's name is the trust anchor (the Kavenegar line is a shared number); the counselor's name
is what a client actually recognises, so it earns the second part when present. «یک سنجه برای شما» is the shortest
complete offer that keeps the institution name up to 18 characters in one part. «برایتان فرستاده‌اند» uses the
respectful plural for the counselor. The brand «استعدادیاب» and the old «پذیرش کاملاً اختیاری است» are left to the
link's domain and the invitation page (consent and the right to decline are stated there, before anything starts).

In-app title: «دعوت تازه به یک سنجه»

### 2. invite_battery — the same, for a battery

Bound model: `ts.assignment` with `battery_id`. Replaces the `_ts_invite_sms_body()` override in
`ts_battery/models/run.py`.

```
{{ object.ts_sms_org }}
{{ (object.ts_sms_counselor + ' ' + object.ts_sms_count + ' سنجه برایتان فرستاده‌اند') if object.ts_sms_counselor else (object.ts_sms_count + ' سنجه برای شما') }}، حدود {{ object.ts_sms_minutes }} دقیقه{{ ('، مهلت تا ' + object.ts_sms_deadline) if object.ts_sms_deadline else '' }}
{{ object.ts_sms_link }}
```

| case | rendered (sample) | chars | parts |
|---|---|---|---|
| الف | مرکز مشاوره آوا⏎۳ سنجه برای شما، حدود ۴۰ دقیقه⏎{link} | 81 | 2 |
| د counselor + deadline | مرکز مشاوره آوا⏎دکتر سارا رضایی ۳ سنجه برایتان فرستاده‌اند، حدود ۴۰ دقیقه، مهلت تا ۲۵ مهر⏎{link} | 124 | 2 |

| variable | meaning |
|---|---|
| `object.ts_sms_org`, `ts_sms_counselor`, `ts_sms_deadline`, `ts_sms_link` | as in 1 |
| `object.ts_sms_count` | number of instruments in the battery, Persian digits («۳») |
| `object.ts_sms_minutes` | estimated total minutes from `ts_card()`, Persian digits, rounded up to a multiple of 5 |
| `object.battery_id.name` | available, **not used** (rule 1) |

Rationale: a battery asks for real time, so the honest effort («حدود ۴۰ دقیقه») is always in the text even though it
costs the second part; the count replaces the battery name, which can name a counseling topic. Always 2 parts.

In-app title: «دعوت تازه به {{ count }} سنجه» (e.g. «دعوت تازه به ۳ سنجه»)

### 3. invite_student — a school panel invites a student («تو»)

Bound model: `ts.assignment` in a panel with purpose `education`, when the number on file is the student's own
(rule 9). Same structure as 1 and 2 with «تو».

```
{{ object.ts_sms_org }}
{{ (object.ts_sms_counselor + ' ' + (object.ts_sms_count + ' سنجه' if object.battery_id else 'یک سنجه') + ' برایت فرستاده‌اند') if object.ts_sms_counselor else ((object.ts_sms_count + ' سنجه' if object.battery_id else 'یک سنجه') + ' برای تو') }}{{ ('، حدود ' + object.ts_sms_minutes + ' دقیقه') if object.battery_id else '' }}{{ ('، مهلت تا ' + object.ts_sms_deadline) if object.ts_sms_deadline else '' }}
{{ object.ts_sms_link }}
```

| case | rendered (sample) | chars | parts |
|---|---|---|---|
| الف | دبیرستان فرزانگان⏎یک سنجه برای تو⏎{link} | 68 | 1 |
| د counselor + deadline | دبیرستان فرزانگان⏎دکتر سارا رضایی یک سنجه برایت فرستاده‌اند، مهلت تا ۲۵ مهر⏎{link} | 110 | 2 |
| battery + deadline | دبیرستان فرزانگان⏎۳ سنجه برای تو، حدود ۴۰ دقیقه، مهلت تا ۲۵ مهر⏎{link} | 98 | 2 |

Variables: as in 1 and 2; `ts_sms_org` is the school's public name.

Rationale: a student recognises the school and the school counselor, not the platform; «برای تو» is warm without
being childish, and the adult (the counselor) still gets the respectful plural. What it is, how long and that the
student may stop are said on the invitation page, where there is room to say them properly.

In-app title: «یک سنجهٔ تازه برای تو»

### 4. reminder — invitation not started or not finished

Bound model: `ts.assignment`. Replaces `SMS_BODIES['reminder']`.

```
{{ object.ts_sms_org }}
{{ ('مهلت دعوت تا ' + object.ts_sms_deadline) if object.ts_sms_deadline else 'دعوت هنوز باز است' }}
{{ object.ts_sms_link }}
```

| case | rendered (sample) | chars | parts |
|---|---|---|---|
| with deadline | مرکز مشاوره آوا⏎مهلت دعوت تا ۲۵ مهر⏎{link} | 70 | 1 |
| no deadline | مرکز مشاوره آوا⏎دعوت هنوز باز است⏎{link} | 68 | 1 |

Variables: `ts_sms_org`, `ts_sms_deadline`, `ts_sms_link` as in 1.

Rationale: the person already received the invitation; the reminder only needs who and until when. The text has no
pronoun and no instrument count, so the same template serves adults, students and batteries. The word «یادآوری» is
dropped: the line itself is the reminder, and «یادآوری: » would cost 9 characters.

In-app title: «یادآوری: دعوت هنوز باز است»

### 5. result_ready_client — the participant's own result is ready

Bound model: `ts.attempt`. Replaces the body in `ts_sms/models/attempt.py`.

```
استعدادیاب
نتیجهٔ {{ object.ts_sms_you }} آماده است
{{ object.ts_sms_link }}
```

| case | rendered | chars | parts |
|---|---|---|---|
| adult | استعدادیاب⏎نتیجهٔ شما آماده است⏎{link} | 66 | 1 |
| student | استعدادیاب⏎نتیجهٔ تو آماده است⏎{link} | 65 | 1 |

| variable | meaning |
|---|---|
| `object.ts_sms_you` | «تو» when the participant is a student (15–18), else «شما» |
| `object.ts_sms_link` | short link to `/my/assessments` (login required; the page checks access again) |

Rationale: sent by the platform even for panel attempts: the result lives in the person's استعدادیاب account, the
sentence fits one part, and the lock screen does not name a counseling center a second time. «آماده است» says only that
something exists; nothing about its content.

In-app title: «نتیجهٔ شما آماده است» / «نتیجهٔ تو آماده است»

### 6. result_ready_staff — a participant's result is ready for the counselor

Bound model: the `ts.notification` row (or whatever record carries the URL today). Replaces
`SMS_BODIES['result_ready_staff']`.

```
استعدادیاب
نتیجهٔ تازه در پنل شما
{{ object.ts_sms_link }}
```

Rendered: استعدادیاب⏎نتیجهٔ تازه در پنل شما⏎{link} — 68 characters, 1 part.

Variable: `object.ts_sms_link` = short link to the attempt/participant page in the panel (the page checks the
permission again).

Rationale: no participant name, no instrument; and by not naming the person at all it avoids the
«شرکت‌کننده»/«مراجع» split (glossary §9-3), which would also have pushed the text to 2 parts
(«نتیجهٔ یک شرکت‌کننده آماده است» = 76).

In-app title: «نتیجهٔ تازه در پنل شما» (replaces «نتیجهٔ یک شرکت‌کننده آماده است»)

### 7. low_balance — panel credit is low

Bound model: `ts.wallet`. Replaces `SMS_BODIES['low_balance']` (and should match `LOW_TEXT` in
`ts_billing/models/wallet.py`).

```
استعدادیاب
اعتبار «{{ object.workspace_id.name }}» به {{ object.ts_sms_available }} رسید. برای ادامهٔ دعوت‌ها اعتبار بخرید.
{{ object.ts_sms_link }}
```

Rendered: استعدادیاب⏎اعتبار «مرکز مشاوره آوا» به ۱٬۲۵۰٬۰۰۰ تومان رسید. برای ادامهٔ دعوت‌ها اعتبار بخرید.⏎{link} —
129 characters, 2 parts. Fallback when the rendered text exceeds 134 (panel name over ~20 characters):
«اعتبار پنل شما به {{ amount }} رسید. برای ادامهٔ دعوت‌ها اعتبار بخرید.» (119 with the sample amount).

| variable | meaning |
|---|---|
| `object.workspace_id.name` | the panel's name as its staff know it (not the public name) |
| `object.ts_sms_available` | `fmt_toman(ts_available())`, «۱٬۲۵۰٬۰۰۰ تومان» |
| `object.ts_sms_link` | short link to `/my/workspaces/<id>/credits` |

Rationale: money and a blocked workflow are worth two parts, and the message is rare (at most once per 24 h per
wallet). It names the amount, the consequence and the action. «اعتبار بخرید» follows the glossary (§8 forbids «شارژ»);
the credits page still says «شارژ اعتبار» in several places, so the page and the SMS should be aligned in the same copy
pass (owner picks «خرید اعتبار» or «افزایش اعتبار»; «اعتبار را افزایش دهید» costs 9 more characters and pushes the
sample to 3 parts).

In-app title: «اعتبار پنل کم شده است» (unchanged; the row text keeps naming the panel and the amount)

### 8. cap_reached — a counselor reached the monthly cap

Bound model: `ts.workspace.member`.

```
استعدادیاب
سقف ماهانهٔ دعوت شما در پنل «{{ object.workspace_id.name }}» پر شد: {{ object.ts_sms_cap }}
{{ object.ts_sms_link }}
```

Rendered: استعدادیاب⏎سقف ماهانهٔ دعوت شما در پنل «مرکز مشاوره آوا» پر شد: ۵۰۰٬۰۰۰ تومان⏎{link} — 112 characters, 2 parts.

| variable | meaning |
|---|---|
| `object.workspace_id.name` | panel name (a counselor may work in more than one panel) |
| `object.ts_sms_cap` | `fmt_toman(monthly_cap)` |
| `object.ts_sms_link` | short link to the member's own cap/credits view (`#tsb-cap`), which says who can raise the cap |

Rationale: names the panel and the limit so the counselor knows exactly which invitations stopped and why. It does
not say whom to ask: the code text «با مدیر پنل صحبت کنید» uses «مدیر پنل», which the glossary reserves against (§3),
and the people who can change a cap are several roles (owner, هماهنگ‌کننده، director, HR admin). The linked page
should name them. Send once per member per Jalali month.

In-app title: «سقف ماهانهٔ دعوت شما پر شد»

### 9. member_invite — a colleague is invited to join a panel

Bound model: `ts.member.invite` (SMS only when `phone` is set).

```
{{ object.ts_sms_org }}
شما را با نقش «{{ object.ts_sms_role }}» به پنل ما در استعدادیاب دعوت کرده‌ایم.
{{ object.ts_sms_link }}
```

Rendered: مرکز مشاوره آوا⏎شما را با نقش «مشاور مرکز» به پنل ما در استعدادیاب دعوت کرده‌ایم.⏎{link} — 116
characters, 2 parts (123 with the longest role «هماهنگ‌کنندهٔ پنل»).

| variable | meaning |
|---|---|
| `object.ts_sms_org` | `workspace_id.public_name` (fallback `name`) |
| `object.ts_sms_role` | `ROLE_LABELS[role]` from `ts_org/models/panel.py` |
| `object.ts_sms_link` | short link to `/join/<token>` |

Rationale: this link grants access to a panel, so the colleague must see who invites, for what role and on which
platform before tapping; the brand is the only Persian clue to what talentsearch.ir is. The 7-day validity is left
to the join page (adding it costs 27 characters and a third part).

In-app title (only if the invitee already has an account): «دعوت به همکاری در یک پنل»

### 10. panel_approved, panel_rejected, panel_suspended — staff notices

Bound model: `ts.workspace` (or the notification row). Replace `SMS_BODIES[...]`.

```
استعدادیاب
پنل شما تأیید شد
{{ object.ts_sms_link }}
```
```
استعدادیاب
پنل شما تأیید نشد
{{ object.ts_sms_link }}
```
```
استعدادیاب
پنل شما معلق شد
{{ object.ts_sms_link }}
```

62 / 63 / 61 characters, 1 part each. Variable: `object.ts_sms_link` = short link to the panel home, where
the reason (rejected, suspended) and the next step are written.

Rationale: one fact per message; the reason belongs on the page, which also checks who is reading. «معلق» is the
glossary state word (§8), replacing «تعلیق شد». The panel name is left out (it would cost 2 parts, and owners of more
than one panel are rare).

In-app titles: «پنل تأیید شد» · «پنل تأیید نشد» · «پنل معلق شد» (replaces «پنل تعلیق شد»)

### 11. otp_signup and otp_phone — one-time code

No bound record (the code is never stored in clear): pass it in the render context.

```
استعدادیاب
کد تأیید: {{ ctx.get('code') }} ({{ ctx.get('minutes') }} دقیقه)
به کسی ندهید.
```

Rendered: استعدادیاب⏎کد تأیید: 123456 (۵ دقیقه)⏎به کسی ندهید. — 51 characters, 1 part. Same text for both keys
(two records so the owner can make them differ later).

| variable | meaning |
|---|---|
| `ctx['code']` | 6 Latin digits |
| `ctx['minutes']` | `TTL_MIN` in Persian digits («۵») |

Rationale: «کد تأیید» is the label of the field the person types into (glossary §7); the code sits on its own line,
easy to read on the notification banner; «به کسی ندهید» is the one sentence that protects against the common
"read me the code" fraud, worth 13 characters more than the ~50 target. For the Kavenegar lookup path
(`ts_sms_otp_template_id`), register the same text at Kavenegar with `%token` for the code and the minutes written in
(«۵»); if `TTL_MIN` changes, the Kavenegar template must be re-approved.
Optional (owner): a last line `@talentsearch.ir #123456` lets Android Chrome fill the code automatically (WebOTP); it
makes the SMS 77 characters, 2 parts.

## 3. What changes from the current code

| where | current | becomes |
|---|---|---|
| `ts_sms/models/assignment.py` `_ts_invite_sms_body` | «%(org)s» شما را به یک سنجش در استعدادیاب دعوت کرده است. پذیرش کاملاً اختیاری است: + link (2 parts even with a short link) | 1 invite_single / 3 invite_student |
| `ts_battery/models/run.py` `_ts_invite_sms_body` | «org» شما را به مجموعهٔ «battery» در استعدادیاب دعوت کرده است. پذیرش اختیاری است: + link | 2 invite_battery (no battery name) |
| `ts_sms/models/attempt.py` | نتیجهٔ سنجهٔ شما در استعدادیاب آماده است. برای دیدن آن وارد حساب خود شوید: + link | 5 |
| `ts_sms/models/phone_otp.py` | کد تأیید استعدادیاب: %s⏎این کد را به کسی ندهید. | 11 |
| `ts_panel/models/notify_texts.py` `SMS_BODIES` | result_ready_staff, panel_*, reminder, low_balance (all start «در استعدادیاب…» or a sentence; all 2 parts) | 4, 6, 7, 10 |
| `ts_panel/models/notify_texts.py` `TITLES` | «نتیجهٔ یک شرکت‌کننده آماده است»، «پنل تعلیق شد» | «نتیجهٔ تازه در پنل شما»، «پنل معلق شد»; new: cap_reached, member_invite |

## قواعد

Rules the implementer must enforce (in code and in a test that renders every template with long real values).

1. **No participant names and no result words in any SMS.** No name, no score, level, factor, band or interpretation
   word, and no instrument or battery name (catalog categories such as «مشکلات زناشویی» or «بیتابی روانی» would tell
   anyone who sees the lock screen what the person is being assessed for). «نتیجه … آماده است» is the most an SMS says.
2. **The link is always last, alone on its own line**, with nothing after it (no period, no space). It must be a short
   link of at most 34 characters (`https://talentsearch.ir/i/<code>`); the current `/invite/<32 hex>` and
   `/join/<32 hex>` forms are 61–63 characters and break every count above. Dropping `https://` would save 8 more
   characters; Android and iOS link a bare `talentsearch.ir/...`, but test on both before relying on it.
3. **Persian digits for every number in the text** (counts, minutes, dates, amounts with «٬»), Latin digits only inside
   the link and the OTP code.
4. **No emoji, no «!», no «متأسفانه», no therapy or medical word** (درمان، درمانگر، بالینی، کلینیک، بیمار، مریض).
5. **Line 1 is the sender's name, alone**: the institution's public name for messages sent on behalf of a counseling
   center or a school (1–4, 9), «استعدادیاب» for platform messages (5–8, 10, 11). The Kavenegar line is shared, so the
   body is the only place the sender is named.
6. **Length check at send time**: count `len(body)` (UCS-2: newline, نیم‌فاصله and «ٔ» count). Target 1 part (≤ 70);
   never more than 2 (≤ 134). If the rendered text is over 134, drop in this order: the counselor clause, then
   «حدود … دقیقه» only if the battery invite is still over, then the deadline; for low_balance use its short fallback.
   Never cut the institution name or the link. Log the part count on the message.
7. **Long institution names**: the one-part texts hold a name of up to 15–18 characters. Many real names are longer
   («مرکز مشاوره و خدمات روان‌شناختی …»). Owner decision: add an optional SMS name on the panel (≤ 18 characters,
   defaulting to the public name), or accept 2 parts for long names.
8. **Dates**: Jalali, «روز ماه» with the month's name («۲۵ مهر»); add the year only when it is not the current Jalali
   year. Amounts: `fmt_toman()` («۱٬۲۵۰٬۰۰۰ تومان»).
9. **Pronoun**: «تو» texts (3, 5-student) only when the number on file is the student's own. When the panel has only the
   ولی's mobile, send the «شما» text (1 or 2); the ولی is the reader.
10. **Who receives**: only with the existing switches and consent (`sms_consent` on the invitation, the person's opt-in
    for results, the staff switch for 6–10). Reminders, low_balance and cap_reached are not sent between 22:00 and
    08:00 Asia/Tehran (held until 08:00); OTP and a fresh invitation go at once.
11. **Edits in the back office** (Settings → SMS templates) must keep rules 1–6; the template form should show the
    rendered length and part count of a sample, so an editor sees when a change adds a part.
