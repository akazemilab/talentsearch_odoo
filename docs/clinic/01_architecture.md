# استعدادیاب for clinics: architecture and data model (Phase 1, 2026-10-11)

Status: approved design for implementation phases 2-6. Written against repo commit cf02357 (branch `redesign` = main).
Owner decisions this spec implements: one institution wallet with per-counselor monthly caps; top-up by native invoice
paid by bank transfer and recorded by the super admin; client sees the result immediately; invoices from the EOT
company in Rial; six starter batteries; Persian name «استعدادیاب».

## 0. Principles
1. Native first. Catalog, prices, invoices, payments, PDF reports and SMS texts are native Odoo objects
   (`product.product`, `product.pricelist`, `account.move`, `account.payment`, `ir.actions.report`, `sms.template`).
   ts_* code only adds the assessment-specific glue (grants, battery run, reservation ledger, report content).
2. Nothing existing breaks: every current panel keeps working as a free panel (`billing_mode='free'`), every existing
   route, test suite and ACL stays. New behaviour is opt-in per workspace.
3. Access logic for results is NOT redesigned. `result_level()` (ts_org) stays the single authority; batteries only add
   more attempts under one invitation. No new ACL on attempts, answers or results.
4. Money is a ledger. Every change of credit is one append-only `ts.wallet.txn` row with an idempotency key; balances are
   sums. Invoices are the only way credit enters; the super admin's manual `ts_grant` stays for goodwill/corrections.
5. eot.ir untouched (guard). The company currency change is the one shared-company action; it is pre-checked (0 moves)
   and rehearsed.

## 1. Actors
| Actor | Odoo object | Today | Change |
|---|---|---|---|
| Super admin (owner, Dr. Kazemi) | user in `ts_core.group_ts_manager` | back office exists (instruments, verification, wallets) | + batteries, grants, prices, invoices |
| Institution «سپهر هیجان اندیش» | `res.partner` company + `ts.workspace` purpose=clinical | none live | created in Phase 2 (clone), Phase 6 (live) |
| Institution admin | member role `owner` (or `clinic_director`) | exists | sees credit, caps, all results (`owner:clin`) |
| Counselor | member role `clinician`, verified, `license_number` | exists | + title, photo, signature, monthly cap, own usage |
| Client | portal user (mobile OTP) + `ts.panel.client` | exists | takes a battery as one invitation |
| Accountant (later) | native account groups | - | sees invoices and payments only; never clinical data (Phase 3b hides participant partners) |

Counselors sign in with the existing mobile-OTP flow (`/signup`), join the panel through the existing colleague invite
(`ts.member.invite`, phone-bound), and are verified by the super admin as today. Sepehr's 9 counselors are created this
way, never by copying users from the Sepehr database (different system, different consent).

## 2. Catalog: instruments, batteries, products

### 2.1 `ts.battery` (new module `ts_battery`, depends `ts_panel`)
| field | type | notes |
|---|---|---|
| name | Char, required | Persian name, e.g. «ارزیابی آغاز درمان» |
| code | Char, unique | `BAT-INTAKE-1` … |
| description | Text | what it is for, one paragraph, ends with «برای مشاوره است، نه تشخیص» |
| audience | Selection adult/adolescent/child | must match every line's instrument audience (constraint) |
| purpose_ids | Selection flags | clinical / education / employment (which panel purposes may use it) |
| line_ids | One2many `ts.battery.line` | ordered |
| state | draft / published / retired | only published batteries can be granted or invited |
| item_count, est_minutes | computed | sum of items; 8 s per item, rounded up to 5 |
| product_id | Many2one `product.product` | created on publish (see 2.3) |

`ts.battery.line`: battery_id, sequence, instrument_id (published only), required (Boolean, default True).
Constraints: no duplicate instrument in a battery; at least 2 lines; retiring an instrument retires it from draft
batteries and blocks publishing a battery that contains a retired instrument.

Starter data (`data/batteries.xml`, noupdate=1, state=published): the six batteries listed in the handoff
(intake, emotional distress, life satisfaction, couples, child, work). Editable by the super admin afterwards.

### 2.2 Grants (allow-lists)
`ts.workspace` (ts_battery extends): `catalog_instrument_ids` (M2M `ts.instrument`), `catalog_battery_ids` (M2M
`ts.battery`), `catalog_mode` Selection: `purpose` (today's behaviour: everything the purpose allows) | `granted`
(only the allow-lists). Default `purpose` for existing panels; `granted` for Sepehr.
`ts.workspace.member`: `restrict_instrument_ids`, `restrict_battery_ids` (M2M). Empty = inherits the workspace catalog;
non-empty = the member may only invite to those (counselor-level grant, set by the institution admin or super admin).
Enforcement: `allowed_instruments()` and a new `allowed_batteries()` apply mode + member restriction; the
`ts.assignment` create/launch path raises `UserError('این سنجه برای این پنل فعال نیست.')` when the instrument or battery
is outside the catalog (server-side; the wizard only lists allowed ones). Audit event `catalog.change` on every grant edit.
Back office: on the workspace form a «کاتالوگ» tab (mode, two M2M lists) and on the member form the two restriction lists.

### 2.3 Products and prices (module `ts_billing`, depends `ts_battery`, `account`, `product`)
- Product category «استعدادیاب / سنجه‌ها». One `product.product` per published instrument and per published battery:
  type service, `sale_ok`, `default_code` = instrument/battery code, name = Persian name, `ts_instrument_id` /
  `ts_battery_id` back-references. Created by a sync method (`ts.instrument.ts_ensure_product()`, called on publish and by
  a one-off migration) so the super admin sets prices in the standard product form (list_price = price for one use).
- Per-institution prices: native `product.pricelist` assigned to the institution partner
  (`res.partner.property_product_pricelist`). Price for a use = `pricelist._get_product_price(product, 1, partner)`.
  Default pricelist «عمومی» = list prices.
- One top-up product «اعتبار پیش‌پرداخت استعدادیاب» (service, price set per invoice line).
- Price shown in the panel in تومان (`fmt_toman(amount_rial)`), stored in Rial everywhere (company currency). Zero price
  = free instrument (allowed; nothing is reserved).

## 3. Battery run (invitation with several instruments)
- `ts.assignment.battery_id` (M2M? no: Many2one `ts.battery`, optional). `ts.assignment.attempt_ids` (One2many
  `ts.attempt`, inverse new field `ts.attempt.assignment_id`). Existing `attempt_id` keeps meaning "the current/first
  attempt" for compatibility; every existing code path (result_level, reports, tests) keeps working for single
  invitations because `attempt_ids` = [attempt_id] there.
- On accept: all attempts of the battery lines are created at once (state consent), in sequence order, all carrying
  `workspace_id`, `client_id`, `assignment_id`. Consent: the first attempt's consent screen names the battery and lists
  its instruments; `give_consent()` on it copies consent fields to the sibling attempts (the consent record stays per
  attempt as today; the client reads one screen). CONSENT_VERSION gets a battery clause -> v3.
- Player chaining: `/take/<token>` of attempt N ends with «ادامه: سنجهٔ بعدی (۲ از ۵)» to attempt N+1 instead of the
  report; the header shows battery progress «۲ از ۵ سنجه». Stop and continue later works per attempt (existing).
- States on the assignment: computed `battery_progress` (done/total), `state` becomes `done` when all required attempts
  are done; optional lines skipped by the client are marked `skipped` (new attempt state is NOT added; a skipped optional
  attempt is cancelled with the existing `error`/void path? No: add `ts.attempt.skipped` Boolean, state stays consent).
- Results: the client page `/my/assessments/battery/<assignment>` shows one card per instrument (existing report
  blocks reused) under a battery header; the panel page `/my/workspaces/<ws>/clients/<c>/b/<assignment>` likewise,
  through `result_level()` per attempt (same level for all, since share_level is on the assignment). Release is
  immediate (owner decision); no new release flow.
- Expiry: the battery link expires as one (30 days / deadline); an accepted battery is never expired mid-way.

## 4. Prepaid billing
### 4.1 Workspace billing mode
`ts.workspace.billing_mode`: `free` (default, today) | `prepaid`. Company-wide `ts_panel.credit_mode` is kept only as a
master switch for legacy behaviour; the per-workspace mode decides. Sepehr = prepaid.

### 4.2 Ledger changes (`ts.wallet`, `ts.wallet.txn`)
- `amount` and `balance_after` become `Monetary` (company currency, Rial); existing integer unit rows are migrated as
  amount 0 (they were free). `units` stays (1 per attempt) for usage statistics.
- New txn types: `hold` (negative, reserves the price at invite), `release` (positive, cancels a hold), `topup`
  (positive, from a paid invoice; replaces unused `purchase`), existing `debit_usage`, `refund`, `grant`, `adjust`.
- `available = balance` (holds are already negative rows) and `held = -sum(hold) - sum(release)` shown separately.
- Idempotency keys: `hold:<assignment>`, `release:<assignment>`, `usage:<attempt>` (today), `usage:bat:<assignment>`,
  `topup:<move>`, `topup-rev:<move>`.

### 4.3 Flow (prepaid workspace)
1. Invite (single or battery, wizard or campaign launch): price = pricelist price of the product. Checks, in order:
   catalog allows; `available >= price` else `UserError('اعتبار پنل کافی نیست. موجودی: … تومان، هزینهٔ این دعوت: … تومان.')`;
   counselor cap (4.4). Then `hold` txn for the price (one per assignment; campaigns post one hold per created
   assignment inside the same transaction, so a batch is all-or-nothing).
2. Completion: single instrument -> on `action_submit` of the attempt: `release` the hold and `debit_usage` for the
   price held (never the current price). Battery -> charged when the FIRST instrument of the run is submitted
   (recommended: the service is consumed; a half-finished battery still cost the counselor's time); remaining attempts
   charge nothing.
3. Expiry / withdraw / decline before any completion -> `release`. Void of an attempt -> `refund` of its debit (exists).
4. Open-link campaigns (`/c/<token>`): the hold cannot be made per invitee in advance; the price is checked and the
   debit posted at completion, and the launch requires `available >= price * min(open_max, 10)` as a floor. Shown in
   the campaign form.
5. Low balance: when `available < low_threshold` after a debit, SMS + in-app notification to the institution admin
   (once per day). When `available < price` for every granted product, the invite buttons show «اعتبار کافی نیست»
   with a link to the credits page (no price hidden; prices are visible in prepaid panels).

### 4.4 Counselor monthly caps
`ts.workspace.member.monthly_cap` (Monetary, 0 = no cap), set by owner/admin on the member page. `member.month_spent`
= sum of debit_usage + hold rows whose `assignment_id.responsible_id`/`invited_by_id` is this member in the current
Jalali month (computed, not stored). Invite refused with
`'سقف ماهانهٔ شما پر شده است (… از … تومان). با مدیر پنل صحبت کنید.'`; the counselor's dashboard shows a cap bar.
Caps are advisory for the institution admin and owner (no cap applies to them).

### 4.5 Top-up by invoice (native)
- `account.move` gets `ts_workspace_id` (Many2one, visible on customer invoices; domain partner = workspace partner).
  Super admin creates the invoice from the workspace back office button «صدور فاکتور اعتبار» (prefills partner,
  product «اعتبار پیش‌پرداخت», quantity 1, unit price = amount). Taxes per the accountant's setup (none until decided).
- Hook: on write of `payment_state` to `paid` or `in_payment` (native, when the payment is registered and reconciled
  or `in_payment`), post `topup` of `amount_untaxed` of the lines of the top-up product, idem `topup:<move>`. Reversal
  (credit note posted) -> `adjust` negative, idem `topup-rev:<move>`. The institution admin sees invoices on the credits
  page (number, date, amount, state) and downloads the native invoice PDF through the portal (`/my/invoices`, native).
- Company currency: switch company 1 from USD to IRR with a data script that asserts `account_move` count = 0 and
  `currency_id = USD` first (already true), run on a clone, guard-compared, then live. Rounding: IRR decimal places 0.
  Display helper shows تومان.

### 4.6 What is visible to whom
| | balance / holds / invoices | prices | per-counselor usage | own cap and usage |
|---|---|---|---|---|
| owner, admin, clinic_director (`credits:read`) | yes | yes | yes | - |
| clinician | no | yes (on invite) | no | yes |
| super admin back office | all panels | edit | all | edit caps |

## 5. Branding
- `ts.workspace`: `brand_color` (Char hex, validated, used only for the report header rule and the panel accent tile),
  `public_name` (Char, defaults to name), `contact_line` (Char: phone/site shown on reports), logo = partner image
  (exists). `res.partner` of the institution keeps address for the invoice.
- `ts.workspace.member`: `title` (Char, e.g. «روان‌شناس بالینی»), `license_number` (exists), `photo` = user image
  (exists), `signature` (Binary image, optional), `show_on_report` (Boolean, default True), `report_bio` (Char 160).
- Report header (participant and panel views, single and battery, screen and PDF): institution logo + public name +
  contact line on the inline-start, counselor block (photo, name, title, licence «پروانهٔ …») on the inline-end;
  footer «تهیه‌شده با استعدادیاب (هیجان اندیشه)». For self-taken, non-panel attempts the header stays as today.
- PDF: `ir.actions.report` (qweb-pdf) `ts_battery.report_attempt_pdf` and `report_battery_pdf`, rendered on demand
  from the same QWeb blocks with a print stylesheet; never stored as attachment (privacy); download audited as
  `result.print`. Precondition to verify in Phase 5 on a clone: wkhtmltopdf renders Persian with the embedded fonts
  (17 qweb-pdf reports exist in the DB, so the binary is expected to be present).

## 6. SMS via native templates
`sms.template` records (xmlids in `ts_sms`), model-bound, rendered with Odoo's inline templating; `ts_sms` looks each up
by xmlid and falls back to the current hard-coded text when missing or empty: `invite_single`, `invite_battery`,
`reminder`, `result_ready_client`, `result_ready_staff`, `low_balance`, `cap_reached`, `panel_approved`,
`member_invite`. Variables: institution public name, counselor name, instrument/battery name, deadline (Jalali), link,
item count/minutes. Body limits: ≤ 70 Persian characters for one SMS part where possible; links shortened to the
existing `/invite/<token>` form. Texts written by `ts-ux-writer`, approved by the owner, editable later in the back
office (Settings → SMS templates). Sender name is the Kavenegar line (cannot be per institution); the first words of
the body name the institution.

## 7. Security, privacy, audit
- No change to attempt/answer/result ACLs or to `result_level()`. Battery views call it per attempt.
- New audit events (`ts.audit.event`): `catalog.change`, `credit.hold`, `credit.release`, `credit.debit`,
  `credit.topup`, `credit.cap`, `report.pdf`.
- Accountants: native account groups only; participant partners are hidden from CRM/accounting users by Phase 3b
  (`ts_participant` flag) before the first real invoice. Invoices name the institution, never a client.
- SMS never carries result content (existing rule).

## 8. Modules and files
- `ts_battery` (new): models battery, battery line, workspace/member catalog fields, assignment battery run, player
  chaining (inherits `TsAssessment` routes), battery report pages, back-office views, starter batteries data, tests.
- `ts_billing` (new): products sync, pricelist use, wallet Monetary + hold/release/topup, caps, invoice hook, credits
  page rework, back-office invoice button, currency migration script, tests. Depends `ts_battery`, `account`.
- `ts_org` / `ts_panel`: branding fields and report header; `ts_sms`: sms.template records and lookup.
- Docs: this file, `02_decisions.md` (owner decisions log), `03_sms_texts.md` (approved texts), handoff.

## 9. Tests (all on eot_ts* clones)
ORM: battery constraints; grants enforced on assignment create; hold/release/debit idempotency and balance math;
cap arithmetic across the Jalali month boundary; topup hook on paid invoice and on reversal; products sync.
HTTP: counselor invites a battery (wizard shows only granted items, price shown), client accepts, consent once, chaining
through N instruments, combined report (client and counselor), insufficient-credit refusal, cap refusal, credits page
for owner vs clinician, PDF download audited, SMS bodies from templates (fake Kavenegar). Guard: eot.ir UNCHANGED after
the currency switch.

## 10. Rollout order
Phase 2: `ts_battery` back office + grants + starter batteries; Sepehr workspace, 9 counselors (phone invites prepared,
not sent), grants, on a clone. Phase 3: battery run + reports. Phase 4: `ts_billing`. Phase 5: branding, PDF, SMS
templates. Phase 6: UX audit, rehearsal, ship; live: currency switch, Sepehr workspace, first invoice, counselor invites
sent by the super admin.

## 11. Owner decisions taken in this spec (confirm or change)
1. Battery price is charged when the client completes the FIRST instrument of the battery (not at the end).
2. Prices are shown in تومان in the panel; invoices and the ledger are in Rial.
3. Open-link campaigns in prepaid panels need a credit floor of 10 uses before launch.
4. Counselor caps apply to clinicians only; owner/admin/clinic_director are uncapped.
5. Consent is given once per battery (one screen listing all instruments); the record is still kept per instrument.
6. Reports are not stored as PDF files; each download is generated on demand and audited.
7. Sepehr's counselors join through phone-bound colleague invites; nothing is copied from the Sepehr app.
