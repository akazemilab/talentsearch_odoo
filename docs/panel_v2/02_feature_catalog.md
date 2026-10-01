# Panel v2 — 02 Feature catalogue

Every feature of the research baseline (prompt 4.3) and the persona screens (prompt 5.2), with
a priority, the persona, acceptance criteria and a test idea. Stage numbers refer to
`07_build_plan.md`; permissions to `05_permissions_matrix.md`; fields to `04_data_model.md`.

Priority: **MVP** = built in Phase 2 stages S0–S20 · **Next** = designed, built after the plan
· **Later** = named so nobody rebuilds the foundations when it arrives.

Personas: **PA** platform admin · **OW** panel owner · **AD** panel coordinator (`admin`) ·
**SP** specialist (counselor, clinician, hr_admin, hiring_manager) · **RV** reviewer ·
**PT** participant · **GU** guardian.

A feature is done only when it also meets the definition of done in the prompt (server-side
object-level check with a deny test, audit, the four states, RTL, WCAG 2.2 AA items, 375 px,
honest Persian copy, tests in the rehearsal, logs updated).

## 1. Account and profile

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| ACC-1 | Profile (name) | MVP | all | `/my/account` on website 4 shows and saves the name; eot.ir `/my/account` is byte-identical to before (guard) | HTTP: save name; guard portal compare | S15 |
| ACC-2 | Verified mobile and email | MVP | all | `/my/phone` (exists) is linked from the account page; the email shown is the login email; a mobile is verified only by OTP | existing `ts_http_sms` + link check | S15 |
| ACC-3 | Sign out everywhere | MVP | all | After re-authentication, one button revokes the user's other sessions through the stock `res.device` / `res.session` models (`04_data_model.md` 2.6); behaviour on eot.ir is untouched | HTTP: two clients, press in A, B is redirected to sign-in | S18 |
| ACC-4 | Sessions list | MVP | all | `/my/security` on website 4 lists the user's own devices from the stock models (device, browser, last activity) with «خروج از این دستگاه». If the stock models cannot serve accounts without a password, the list moves to Next and only ACC-3 ships (recorded in `DEVIATIONS.md`) | HTTP: list shows two sessions | S18 |
| ACC-5 | My data: export request | MVP | PT | `/my/privacy` → "دریافت نسخه‌ای از داده‌های من": after re-auth a job builds a ZIP with one JSON and one CSV (own profile, attempts, results at participant level, shares, consents). No item keys. Link expires in 24 h | HTTP: request, job done, download once, refused after expiry | S15 |
| ACC-6 | My data: erase request | MVP | PT | `/my/privacy` → request recorded as `ts.data.request`, due in 30 days, the participant sees its state; executed by a platform manager through the erase workflow | ORM: workflow leaves no answers/results; usage rows remain | S15, S18 |
| ACC-7 | Notification preferences | MVP | all | Per type: in-app and SMS (email is hidden until decision D8); SMS only selectable with a verified mobile | HTTP: toggle, then event respects it | S10 |
| ACC-8 | Language | Later | all | Persian only now | — | — |
| ACC-9 | Passkeys, authenticator app | Later | staff | Odoo ships `auth_passkey_portal` and `auth_totp_portal`; installing them changes the shared instance, so it needs its own guard rehearsal and the owner's decision | — | — |
| ACC-10 | Sign-in risk notice and alternative | MVP | all | `/signup` shows one line that SMS codes are a weaker method and links to email sign-in (NIST restricted authenticator duty) | HTTP: text present | S18 |

## 2. Panel settings

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| ORG-1 | Name and logo | MVP | `panel:profile` | Existing rules kept (2–100 chars; PNG/JPG/WEBP < 512 KB, decodable). Saved from the Settings page | existing `ts_http_panel` moved to the new route | S2 |
| ORG-2 | Contact shown to participants | MVP | `panel:profile` | Optional phone and email; shown on invitation and report pages; phone rendered LTR | HTTP: appears on `/invite/<token>` | S2 |
| ORG-3 | Client word | MVP | `panel:profile` | Choice of دانش‌آموز / مراجع / داوطلب / کارمند / شرکت‌کننده changes labels across the panel | HTTP: label on clients page | S4 |
| ORG-4 | Co-brand colour | Next | OW | Accent applied only when contrast ≥ 4.5:1 | unit: contrast function | — |
| ORG-5 | Purpose and panel code | MVP | OW | Shown read-only with a "why can't I change this" help line; code has a copy button | HTTP | S2 |
| ORG-6 | Terms version | MVP | OW | Settings shows the accepted version, date and who accepted. When `TERMS_VERSION` changes, owners see a banner on the dashboard until they accept the new text; accepting updates the existing `terms_*` fields and writes the existing audit event `workspace.terms_accept`. Nothing is blocked while the banner is open (blocking invitations on a text change would be a product rule nobody has decided) | ORM + HTTP | S2 |
| ORG-7 | Ownership transfer | MVP | OW | Owner picks an active member → that member becomes `owner`; the old owner chooses to stay owner or become `admin`. Re-auth, confirmation page naming the person, both notified, audited `panel.transfer` | HTTP flow; last-owner guard | S18 |
| ORG-8 | Close panel | MVP | OW | Confirmation page that names the panel and states what happens (no new invitations, 90 days to export, then clients are anonymised; participants keep their own results). Re-auth. Audited `panel.close` | ORM: state, A2 permissions | S18 |
| ORG-9 | Custom domain, white-label sender | Later | OW | — | — | — |

## 3. Members and roles

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| MEM-1 | Members list | MVP | OW, AD, managers | Name, role, state (active / awaiting verification / deactivated), number of clients, last activity date | HTTP per role; 403 for specialists | S3 |
| MEM-2 | Invite colleague | MVP | OW, managers | Existing rules (one verified mobile or email, role from the panel's set, 7 days, max 20 pending, link shown with copy button). Shows inviter, panel and role on `/join/<token>` | existing tests re-pointed | S3 |
| MEM-3 | Send again / revoke | MVP | `members:invite` | "ارسال دوباره" revokes the old token and issues a new 7-day link; revoke as today | ORM: old token dead | S3 |
| MEM-3b | Accepting while already a member | MVP | — | A person who is already an active member of the panel and opens a colleague invitation for another role sees «شما عضو این پنل هستید؛ مالک پنل می‌تواند نقش شما را تغییر دهد» and nothing changes | P23 | S1 |
| MEM-4 | Change role | MVP | OW | Role chosen from the panel's set; last-owner guard; clients released when the new role cannot be responsible; audited `member.change` | ORM (exists) + HTTP | S3 |
| MEM-5 | Deactivate / reactivate | MVP | OW | Confirmation page naming the person and the number of clients that go to the unassigned queue; audited | HTTP + P16 | S3 |
| MEM-6 | Second owner | MVP | OW | Only an owner can invite an owner; needs re-authentication (SEC-5, built in this same stage) | HTTP | S3 |
| MEM-7 | Practising owner | MVP | OW | Owner ticks «خودم هم مراجع می‌بینم»; in a clinical panel this asks for the licence number and starts verification | P07 | S1, S3 |
| MEM-8 | Role help page | MVP | all staff | `/help/roles`: the table of section 2 of the permissions file in plain Persian, generated from `ROLE_PERMS` so it cannot drift | HTTP: every role label present | S3 |
| MEM-9 | Awaiting-verification view | MVP | SP | An unverified clinician or clinic director can enter and sees only the «در انتظار احراز صلاحیت» notice (A5). Until S2 the existing 404 stays | P06 (S1) + HTTP (S2) | S2 |
| MEM-10 | Care team (several specialists per client) | Next | OW | R4 | — | — |
| MEM-11 | Custom roles, groups of members, SSO/SCIM | Later | OW | — | — | — |

## 4. Clients and groups

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| CLI-1 | Client list | MVP | staff | Table pattern TBL-1…8. Columns: name (or code), group, responsible, open invitations, completed, last activity, state | HTTP: search, filter, sort, page 2 | S4 |
| CLI-2 | Client page | MVP | staff | Header (name, code, groups, responsible, age group, linked-account badge without revealing the account), tabs: assessments timeline with state and result links at the member's level; consents; activity. Result links only where `result_level ≥ summary` | HTTP per role and level | S4, S13 |
| CLI-3 | Create / edit | MVP | `clients:write` | Name required; code unique in the panel; phone and email validated; minor fields shown when age group is minor; duplicate warning when phone, email or normalised name already exists (warning, not a block) | ORM + HTTP | S5 |
| CLI-4 | Set / change responsible | MVP | `clients:assign` | From the page or in bulk; target list limited to eligible members; audited | P15 | S4 |
| CLI-5 | Hand over my client | MVP | SP | A specialist asks to hand a client to a named colleague; it takes effect when a member with `clients:assign` confirms (solo owner: at once) | HTTP | S5 |
| CLI-6 | Archive / restore | MVP | `clients:archive` | Archived clients leave default lists, cannot be invited, keep history; filter "بایگانی‌شده" | ORM + HTTP | S5 |
| CLI-7 | Merge duplicates | MVP | `clients:merge` | Pick two rows, preview what moves, confirm; refused when both have different accounts or when either is an imported historical person (`contact_locked`); audited | ORM | S5 |
| CLI-7b | Imported people are protected | MVP | system | A client with `source='import'` cannot be invited, reminded, messaged, merged or have contact details added until the owner changes `ts_panel.import_contact_unlocked` | P20 | S4 |
| CLI-8 | Groups (class, team, tag) | MVP | `groups:manage` | Create, rename, archive; add/remove clients one by one and in bulk; group page lists members and offers "دعوت گروه" | HTTP | S5 |
| CLI-9 | Pseudonymous display | Next | OW | Panel switch: show code instead of name in lists and print | — | — |
| CLI-10 | Private specialist notes | Later | SP | Default decision: not in MVP (clinical data; would need encryption and an export rule) | — | — |
| CLI-11 | Claim of historical results by the person | Later | PA | Depends on the owner's release decision for the 114 imports | — | — |

## 5. Invitations and campaigns

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| INV-1 | Invite one client | MVP | `invites:create` | Wizard: who (existing client or new) → which assessment (only allowed instruments) → options (deadline, note, SMS with the consent attestation tick) → review → done page with link, copy button and QR. Gated panel: refused with the pending text | HTTP happy path + gated + instrument not allowed | S6 |
| INV-2 | States and funnel | MVP | staff | States: دعوت‌شده، بازشده، پذیرفته، در حال پاسخ، تکمیل‌شده، منقضی، ردشده، لغوشده. Filter chips with counts | ORM state compute incl. expired | S6 |
| INV-3 | Expiry and extend | MVP | `invites:manage` | `expires_at` stored; hourly cron sets `expired`; "تمدید" sets a new date and clears `expired`; an expired link shows the existing Persian message | ORM cron + HTTP | S6 |
| INV-4 | Withdraw | MVP | `invites:manage` | As today; a started attempt becomes `stopped` | ORM | S6 |
| INV-5 | Invite a group | MVP | `invites:bulk` | From a group or a selection: one campaign, one assignment per client, skipping clients who already have an open invitation for that instrument (shown in the review step) | ORM: no duplicates | S7 |
| INV-6 | Open link and QR | MVP | `invites:bulk` | Campaign link `/c/<token>`: the participant signs in, types their name, accepts; a client and assignment are created; stops at `open_max` or `open_expires_at`; can be closed any time; printable QR sheet | HTTP: cap, expiry, close | S7 |
| INV-7 | CSV invite | MVP | `clients:import` + `invites:bulk` | The import wizard (IMP-1) ends with "invite all imported to …" | HTTP | S8 |
| INV-8 | Reminders | MVP | system | One automatic reminder per assignment: `reminder_before_days` before the deadline, or `reminder_after_days` after the invitation when there is no deadline. In-app for people with an account. **By SMS only when all of these hold**: the company switch `ts_sms_reminder` is on (ships off), the invitation has `sms_consent` and `remind_ok` (so it was created in the v2 wizard, whose tick says «با دریافت پیامک دعوت و یک یادآوری موافق است»), it is outside quiet hours, the person is not an imported historical person. Manual "یادآوری" button under the same conditions, at most one per 24 h, total at most 3 | ORM: cron picks, limits, old invitations never get SMS; P20 | S10 |
| INV-9 | Status page per campaign | MVP | staff | Counts per state, list, export of status (EXP-2) | HTTP | S7 |
| INV-10 | Scheduled campaigns, recurring assessments | Later | — | — | — | — |
| INV-11 | Access code for group sittings without accounts | Later | — | Our participants keep accounts; not needed now | — | — |

## 6. Dashboard

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| DSH-1 | Needs-attention block | MVP | by role | First block on the page; each line is a link to the filtered list. Items and exact definitions in `03_ia_and_ux.md` section 5 | ORM: each definition against fixtures | S12 |
| DSH-2 | KPIs | MVP | by role | At most six tiles, each a link; period 7/30/90 days; a text table alternative for the one chart (funnel) | HTTP: numbers equal list counts | S12 |
| DSH-3 | Onboarding checklist | MVP | OW | Shown until all steps are done or dismissed: logo, contact, first colleague (skippable for solo), first client, first invitation, first completed result | HTTP | S12 |
| DSH-4 | Workload per member | MVP | OW, managers | Table: member, clients, open invitations | HTTP | S12 |
| DSH-5 | No clinical inference | MVP | — | Dashboards show counts and states only; never scores or bands | review in template test | S12 |
| DSH-6 | Custom widgets | Later | — | — | — | — |

## 7. Lists and tables

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| TBL-1 | Search | MVP | One search box; matches normalised name, code, phone tail (last 4 digits typed). The text is posted and kept in the session, never in the URL (it can be a name) | S4 |
| TBL-2 | Filters | MVP | Chips and a filter panel; filters, sort and page kept in the URL query; "پاک کردن فیلترها" | S4 |
| TBL-3 | Sort | MVP | Column headers are links; `aria-sort` set; default last activity, newest first | S4 |
| TBL-4 | Pagination | MVP | 25 per page (50, 100 selectable); "x–y از n"; server-side `limit/offset` | S4 |
| TBL-5 | Bulk actions | MVP | Row checkboxes, select page, selection count, batch bar (assign responsible, add to group, invite, archive, export). Works without JavaScript through a form post | S5 |
| TBL-6 | Saved views and column visibility | MVP | `ts.saved.view`; up to 10 per page per member; one default | S5 |
| TBL-7 | Sticky header, row actions | MVP | Header sticks under the site header; each row has one primary action and a "more" link list | S4 |
| TBL-8 | States | MVP | Empty (first use), no results for filter, no permission, error: four distinct texts and actions (design system) | S4 |
| TBL-9 | Mobile | MVP | Below 768 px each row becomes a card; no horizontal page scroll at 375 px | S4 |
| TBL-10 | Inline edit | Later | — | — |

## 8. Reports, export, import

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| REP-1 | Individual report at the member's level | MVP | by level | Reached from the client page; level decided by `result_level`; header shows panel co-brand line, date stamp, instrument version; audit `result.view` | P12 + HTTP | S13 |
| REP-2 | Print / PDF | MVP | same | Print stylesheet (exists) produces a clean A4 page: date, version, "printed by" role (not name), page numbers; audit `result.print` through a print link that logs then calls `window.print()` | headless print check | S13 |
| REP-3 | Group report | MVP | `reports:group` | Choose group or campaign and instrument → counts per state. Ordinary instruments: per factor, how many people are in each band. TALENT-INV-15: per scale (ANA, EXP, ACA, NOV, DUT) the group mean of each person's mean across their fields, and how many people have that scale as their highest; no field names. Imported results are included for members who may see them and the report says so («شامل نتایج واردشده»). Threshold and complementary suppression; shows n of m, filters and date; never names | P18 | S13 |
| REP-4 | Benchmarks, scheduled reports | Later | — | No norms exist in the source data; none are claimed | — | — |
| EXP-1 | Export clients | MVP | `clients:export` | CSV and XLSX; UTF-8 with BOM; Latin digits; two date columns (Jalali and ISO); columns name, code, group, responsible, state, counts; re-auth; job; link 24 h; audit `export.create` and `export.download` | HTTP + file check | S9 |
| EXP-2 | Export status | MVP | `clients:export` | One row per assignment: client, instrument, state, dates; no results | same | S9 |
| EXP-3 | Export results | MVP | `results:export` | Education and employment only; only rows the member may see at that level; never answers; clinical panels have no such export. Rows for ordinary instruments: client, instrument, factor, band. Rows for TALENT-INV-15 (education): client, field number (not the field's name, which is the participant's own free text), the five scale scores (ANA, EXP, ACA, NOV, DUT) and the total | P-level test per row | S9 |
| EXP-4 | Export audit | MVP | `audit:export` | Filtered events as CSV; cleaned detail only | HTTP | S14 |
| EXP-5 | API | Later | — | — | — | — |
| IMP-1 | Import clients (CSV/XLSX) | MVP | `clients:import` | Steps: download template → upload (≤ 2 MB, `.csv`/`.xlsx`, ≤ 2000 rows, limit stated up front) → map columns (auto-matched by header) → validate with a per-row error list → preview → import valid rows → error report download. Encoding detected (UTF-8, UTF-16, Windows-1256); Persian digits accepted; **idempotent**: an existing client is matched by code, else phone, else email, and updated, never duplicated; audit `import.run` with counts | ORM: run twice, same count | S8 |
| IMP-2 | Saved mappings | Later | — | — | — | — |

## 9. Notifications

Events (N-events) and default channels

| Event `type` | To | In-app | SMS | Email |
|---|---|---|---|---|
| `invite` | participant | if they have an account | as today: valid mobile + the member's consent tick + switch `ts_sms_invite` | — |
| `reminder` | participant | ✓ | INV-8 conditions + switch `ts_sms_reminder` (ships off) | — |
| `result_ready_participant` | participant | ✓ | as today: verified mobile + own opt-in + switch `ts_sms_result` | — |
| `result_ready_staff` | responsible member, or members with `clients:assign` if unassigned | ✓ | own opt-in + switch `ts_sms_staff` (ships off) | — |
| `shared_with_panel` | responsible member | ✓ | — | — |
| `share_revoked` | responsible member | ✓ | — | — |
| `panel_approved` / `panel_rejected` / `panel_suspended` | owners | ✓ | own opt-in + `ts_sms_staff` | — |
| `member_joined` | inviter | ✓ | — | — |
| `client_handover_request` | members with `clients:assign` | ✓ | — | — |
| `export_ready` / `import_done` | requester | ✓ | — | — |
| `support_access_opened` | owners | ✓ | — | — |
| `data_request_update` | participant | ✓ | — | — |

The email column is empty on purpose: no outgoing email is set up for Talent Search and the
instance's mail server is shared with eot.ir (decision D8). Until then an email typed on a
client is only a matching key and a contact detail for the panel's own use.

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| NOT-1 | Notification center | MVP | Bell with unread count in the header; `/my/notifications` list, mark one/all read; titles carry no names | S10 |
| NOT-2 | Preferences | MVP | ACC-7 | S10 |
| NOT-3 | Quiet hours and limits | MVP | SMS not sent 21:00–08:00 Tehran (queued to 08:00), at most 5 a day per person; OTP exempt | S10 |
| NOT-4 | Delivery status | MVP | SMS status comes from the existing Kavenegar log; staff see "ارسال شد / نرسید" on the invitation | S10 |
| NOT-5 | Historical people | MVP | No event can reach an imported historical person: enforced by `contact_locked` (CLI-7b) and tested for every sending path (P20) | S4, S10 |
| NOT-5b | Owner's go-ahead before new SMS kinds | MVP | The S10 ship changes nothing that reaches a phone: the two new switches are off. The ship note lists each new SMS text and its conditions; the owner turns the switches on | S10 |
| NOT-6 | Webhooks | Later | — | — |

## 10. Wallet, usage, billing

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| WAL-1 | Ledger | MVP | system | `04_data_model.md` 3.5; one debit per scored attempt; immutable | P19 | S11 |
| WAL-2 | Credits page | MVP | `credits:read` | «رایگان در این فصل» banner while free; usage this month and in total; open invitations ("committed"); history table with date, type, client reference, units | HTTP | S11 |
| WAL-3 | Usage report | MVP | `credits:read`, PA | Per month and per instrument; back-office pivot per panel | HTTP + backend | S11, S17 |
| WAL-4 | Low-balance alert | Next (meaningless in free mode) | OW | Threshold field exists on the wallet; the notification is wired with the paid phase | — | — |
| WAL-0 | Usage event for every finished panel attempt | MVP | system | A finished TALENT-INV-15 attempt in a panel writes one `ts.usage.event` (today it writes none, gap G28) | P22 | S0 |
| WAL-5 | Refund on void | MVP | PA | Voiding an attempt writes `refund` once | ORM | S11 |
| WAL-6 | Grants and adjustments | MVP | PA | Back-office action with a reason code; shown in the panel's history | ORM | S11 |
| WAL-7 | Purchase, gateway, invoices, expiry lots, plans | Later | — | Needs the owner's decision and eNamad, tax code, e-invoice setup | — | — |

## 11. Audit and support access

| Id | Feature | Pri | Who | Acceptance criteria | Test idea | Stage |
|---|---|---|---|---|---|---|
| AUD-1 | Event hygiene | MVP | system | `04_data_model.md` 2.3 | P17 | S1 |
| AUD-2 | Deny events | MVP | system | `authz.deny` for 403/404 on panel routes, throttled | HTTP | S1 |
| AUD-3 | Panel audit page | MVP | `audit:read` | Filters: date range, event family (ورود و دسترسی، اعضا، مراجعان، دعوت‌ها، نتایج، خروجی‌ها، تنظیمات، پشتیبانی), member; each row in plain Persian ("مشاور X نتیجهٔ مراجع Y را دید"), names resolved at render time under the viewer's own permissions | HTTP | S14 |
| AUD-4 | Who saw this result | MVP | OW; PT for own results | On a result page (owner) and on "who can see" (participant): the list of views by role and date | ORM query | S14, S15 |
| SUP-1 | Support access | MVP | PA, OW | `04_data_model.md` 3.10: reason + ticket reference, time-boxed, owner notified, listed on the audit page | ORM + HTTP | S14 |
| SUP-2 | Technical lock on clinical data | decision D4 | PA | Optional stage S14b | — | S14b |
| SUP-3 | Impersonation | never | — | Not built | — | — |

## 12. Help and onboarding

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| HLP-1 | Help link in the same place on every page | MVP | "راهنما" is the last item of the panel menu and of the participant menu on every page (WCAG 3.2.6) | S2 |
| HLP-2 | Panel help center | MVP | `/help/panel`: short task pages (invite, import, read a report, roles, sharing and privacy, credits). Text matches behaviour; each page names the date it was checked | S19 |
| HLP-3 | Contextual help | MVP | A "این چیست؟" link beside sensitive settings (share levels, minors, export, support access) opens the matching help anchor | S19 |
| HLP-4 | Contact support | MVP | Link to the existing `/contact` with the panel code prefilled | S19 |
| HLP-5 | Guided tours, in-app chat | Later | — | — |

## 13. Security

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| SEC-1 | Object-level checks through shared helpers | MVP | `05_permissions_matrix.md` 9; `ts check` rule | S0, S1 |
| SEC-2 | CSRF on every POST | MVP | Odoo default kept; HTTP test posts without a token | every stage |
| SEC-3 | Rate limits | MVP | OTP limits exist. New: invitation creation 200/hour/member, open-link joins 10/hour/IP hash, export jobs 10/day/member, manual reminders (INV-8) | S6–S9 |
| SEC-4 | Upload checks | MVP | Import: extension, size, row count, content sniff (CSV text or XLSX zip signature); never stored beyond the job | S8 |
| SEC-5 | Re-authentication | MVP | `05_permissions_matrix.md` 6 | S3 |
| SEC-6 | Staff session timeout | MVP | 8 h idle (setting); participants keep Odoo's default | S18 |
| SEC-7 | Password rule on website-4 forms | MVP | 15 characters minimum when a password is set on website 4; the instance-wide policy is not touched | S18 |
| SEC-8 | CSV injection | MVP | Cells starting with `= + - @` are prefixed with `'` in exports | S9 |
| SEC-9 | Anomaly alerts | Later | — | — |

## 14. Privacy and data lifecycle

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| PRV-1 | Consent ledger | MVP | `ts.consent.record` rows for service, research, share, revoke, guardian, terms | S15, S16 |
| PRV-2 | Who can see my results | MVP | `/my/sharing`: per result, each panel with its name, the responsible specialist's name, the level in words, since when, a revoke button; views of the result by role and date | S15 |
| PRV-3 | Retention jobs | MVP | `04_data_model.md` 6, daily cron, each run audited with counts | S18 |
| PRV-4 | Erase workflow | MVP | `04_data_model.md` 6 | S18 |
| PRV-5 | Policy-change notice | Next | Banner two months before a privacy text change, re-consent at the change (directive of 1402) | — |
| PRV-6 | Processor agreement template for panels | Later | Legal document, not code | — |

## 15. Localization and accessibility

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| L10N-1 | Persian UI, RTL, Jalali dates, Persian digits | MVP | Helpers `fa_digits`, `jalali` reused; no English string on any panel page (HTTP scan of titles and body) | every stage |
| L10N-2 | Exports use Latin digits and both date forms | MVP | EXP-1 | S9 |
| L10N-3 | LTR runs | MVP | Phones, emails, codes, links in `<bdi dir="ltr">`; inputs `dir="ltr"` with `inputmode` | design system |
| L10N-4 | Search normalisation | MVP | `norm_text` | S4 |
| A11Y-1 | WCAG 2.2 AA on every new page | MVP | Checklist in `08_design_system.md`; headless audit at 1280 and 375 px in the rehearsal | S2 on, full pass S19 |
| A11Y-2 | OTP field | MVP | One input, `autocomplete="one-time-code"`, paste allowed (check `/signup`, `/my/phone`, `/my/reauth`) | S3 |

## 16. Platform admin (Odoo back-office)

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| PLT-1 | Tenants list with health | MVP | Columns: state, purpose, members, clients, open invitations, completed in 30 days, last activity, pending age; filters; no names of clients | S17 |
| PLT-2 | Pending-approval queue | exists | Add the age of each request and a link to the panel's terms acceptance | S17 |
| PLT-3 | Suspend / resume | exists | Owners are notified (`panel_suspended`) | S17 |
| PLT-4 | Usage per tenant | MVP | Pivot of ledger rows by month, panel, instrument | S11 |
| PLT-5 | Instrument catalog | exists | — | — |
| PLT-6 | Notification templates | MVP | Texts live in one Python module `ts_panel/models/notify_texts.py` and one data file for SMS; listed read-only in the back-office | S10 |
| PLT-7 | Support / emergency access | MVP | SUP-1 | S14 |
| PLT-8 | Global audit | exists | Filters for `outcome` and event family | S14 |
| PLT-9 | Data-request queue | MVP | List with due dates; overdue highlighted; actions run the workflows | S17 |
| PLT-10 | Operators lose access to invitation identities | MVP | G12: the access row and the back-office menu «دعوت‌های سازمانی» become manager-only | S17 |
| PLT-11 | Feature flags per tenant | Later | — | — |

## 17. Participant portal

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| PRT-1 | Home «کارهای من» | MVP | `/my` on website 4: invitations waiting for me, attempts to continue (with progress), newest results; one primary action per card | S15 |
| PRT-2 | Results list | MVP | `/my/assessments` keeps its URL; adds the sharing state per result | S15 |
| PRT-0 | Share and revoke on the TALENT-INV-15 report | MVP | The block «اشتراک با سازمان» with «لغو اشتراک», and «ارسال نتیجه برای مشاورم», exist today only on the report of the other instruments (`ts_assessment.report`); the matrix report (`ts_talent.report`) has neither (gap G30). Added to the matrix report, with wording that says what the counselor sees for this instrument: «گزارش نتیجهٔ شما، بدون پاسخ‌هایتان» | S0 |
| PRT-3 | Report page | exists | Both report templates get the "چه کسی این نتیجه را می‌بیند" block; plain-language limits text stays | S15 |
| PRT-4 | Share with my counselor by code | exists | Up to 3 panels at a time (owner decision D3, `ts_panel.share_max_panels`), each revocable on its own; consent record written | S15 |
| PRT-5 | Player: autosave, resume, mobile | exists | Checked against ITC/ATP 3.3 and 3.9 in the S19 pass; resume card on the home page | S15, S19 |
| PRT-6 | PDF | exists (print) | Print page verified in the S13 check | S13 |
| PRT-7 | Notifications, account, privacy | MVP | NOT-1, ACC-1…7 | S10, S15 |
| PRT-8 | Invitations found by my verified mobile | Next | An invitation whose client phone equals my verified mobile appears on my home page even if I lost the link | — |

## 18. Minors and guardians

| Id | Feature | Pri | Acceptance criteria | Stage |
|---|---|---|---|---|
| GRD-1 | Age group on the client | MVP | `adult / minor / unknown`; schools preselect minor | S4 (field), S16 (rules) |
| GRD-2 | Attest mode (owner decision D2) | MVP | When a campaign or invitation includes minors, the member must tick «رضایت ولی یا سرپرست قانونی را گرفته‌ایم» → consent record `guardian_attest` with member and time. Without it the invitation cannot be sent | S16 |
| GRD-3 | Minor's assent wording | MVP | The consent page for a minor uses age-appropriate text, says who will see the result, and records `assent`; new consent text version, owner approves the text | S16 |
| GRD-4 | Self-taken by a minor | MVP | First consent page asks «۱۸ سال یا بیشتر دارید؟»; "no" shows the guardian notice and requires a tick that a parent or guardian agrees | S16 |
| GRD-5 | Guardian-link mode | Later (owner chose attestation, D2) | Guardian opens a link, reads, confirms with name, relation and a mobile OTP → `guardian` record; the minor cannot start before it | — |
| GRD-6 | Guardian sees the child's status and result | Next | Only as the consent defines | — |
| GRD-7 | Parent-report instruments linked to a client | MVP | `account_is_guardian`; result attached to the child's client row | S16 |
