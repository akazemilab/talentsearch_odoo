# Phase 4 brief: `ts_billing` (prepaid credit on native Odoo) — implementation contract

Written by the architect (Fable) 2026-10-11 as the binding detail of spec §4 (docs/clinic/01_architecture.md).
Where this brief and the spec differ, this brief wins. Everything here is on top of what is live (commit 5a4dc65).

## 0. Rules
- Money is a ledger: `ts.wallet.txn` rows are the only truth; `balance` is a stored sum; rows are never edited or deleted.
- One code path posts rows: `ts.wallet._post()` (row lock + idempotency key). Never write `ts.wallet.txn` elsewhere.
- Every blocking decision (insufficient credit, cap) is made server-side at the moment the invitation is created, inside
  the same database transaction as the hold, under the wallet row lock. UI checks are convenience only.
- Free stays free: a workspace with `billing_mode='free'` behaves exactly as today (debit rows of amount 0).
- Nothing here changes who may see results (`result_level`) or any ACL on attempts/answers/results.

## 1. Money representation
- Company currency switches USD -> IRR once (section 7). `IRR` live row: rounding 0.01, decimal_places 2. Set
  `rounding = 1.0`, `decimal_places = 0` on IRR as part of the switch (Rial has no subunit in practice).
- `ts.wallet.amount/balance_after/balance`: change `Integer` -> `Monetary` (`currency_field='currency_id'`,
  `currency_id` related to `workspace_id.company_id.currency_id`). Existing rows are free rows (0 or ±1 units): a
  migration sets `amount = 0` and recomputes `balance_after`/`balance` (existing rows carried units, not money).
  Verify on the rehearsal clone that the int4 -> numeric column conversion happens automatically; if the ORM refuses,
  do it in a `pre_init_hook`/migration script with `ALTER TABLE ... TYPE numeric USING amount::numeric`.
- `units` stays (1 per attempt, statistics). `fmt_toman(rial)` -> «۱٬۲۰۰٬۰۰۰ تومان» (Persian digits, U+066C separator);
  rial values that are not a multiple of 10 are shown with a decimal تومان? No: prices are entered in Rial and MUST be
  multiples of 10 (constraint on products used by us: `list_price % 10 == 0`), so تومان is always an integer.

## 2. Catalog -> products -> prices
- `ts.instrument.product_id` (Many2one product.product, readonly). `ts.battery.product_id` exists (empty) -> fill.
- `_ts_ensure_product()` on both models: create on publish, called by a `<function>` data record on install/upgrade for
  every published record, and when `name` changes sync the product name. Product: `type='service'`, `sale_ok=True`,
  `purchase_ok=False`, `default_code = code`, `categ_id` = «استعدادیاب / سنجه‌ها» (data), `list_price = 0`,
  `taxes_id = []`, `ts_instrument_id` / `ts_battery_id` on product.template (Many2one, readonly, index).
  Back office: on the instrument and battery forms a «قیمت پایه (ریال)» related field editing `product_id.list_price`
  plus a smart button to the product.
- Price for a workspace: `ws.ts_price(product)` = `ws.partner_id.property_product_pricelist._get_product_price(product, 1.0)`
  rounded to integer Rial. Default pricelist = company default (list prices). Institutions with special prices get
  their own `product.pricelist` set on their partner by the super admin (native).
- Top-up product (data, noupdate): «اعتبار پیش‌پرداخت استعدادیاب», service, `ts_topup=True` flag on product.template,
  `taxes_id = []`, not sold through the panel.

## 3. Workspace and member fields
- `ts.workspace.billing_mode` Selection `free` (default) | `prepaid`; super admin only (back office, tracking, audit
  `billing.mode`). Switching to prepaid does not touch open invitations (they stay free: no hold -> debit 0).
- `ts.workspace.member.monthly_cap` Monetary, 0 = none; editable by owner/admin/clinic_director (`credits:read` perm
  plus role check) on the panel member page and by the super admin; applies only to members whose role is in
  `('clinician', 'counselor', 'hiring_manager', 'reviewer')` (never owner/admin/clinic_director/hr_admin).
- `ts.assignment.price_held` Monetary (0 when free/unpriced) and `priced_product_id` (Many2one product.product), both
  readonly, set at create.

## 4. Ledger types, reasons, keys
- TXN_TYPES += `('hold', 'رزرو اعتبار')`, `('release', 'آزادسازی رزرو')`, `('topup', 'شارژ اعتبار')`; keep `purchase`
  for compatibility (unused).
- REASONS += `invite`, `expiry`, `withdraw`, `decline`, `topup`, `topup_reversal`, `insufficient`.
- Keys: `hold:<assignment id>`, `release:<assignment id>`, `usage:<attempt id>` (exists), `topup:<move id>`,
  `topup-rev:<move id>`. `_post` stays idempotent on the key.
- Derived numbers (SQL, one query each): `available = SUM(amount)`; `held = -(SUM(hold) + SUM(release))` (≥ 0 by
  construction); `committed_month(member)` in section 5.

## 5. Flows (prepaid workspace; free workspaces skip all of this)
### 5.1 Hold at invitation (`ts.assignment.create` override in ts_billing, runs AFTER ts_battery's catalog check)
For each new assignment with `workspace_id.billing_mode == 'prepaid'`:
1. product = battery product if `battery_id` else instrument product; price = `ws.ts_price(product)`. If price == 0 ->
   `price_held = 0`, no row, done.
2. `wallet._post('hold', -price, 0, 'hold:<id>', 'invite', assignment=...)` under the wallet row lock, but FIRST, in
   the same locked section, recompute `available`; if `available < price` raise
   `UserError('اعتبار پنل کافی نیست. موجودی: %s، هزینهٔ این دعوت: %s.' % (fmt_toman(available), fmt_toman(price)))`.
   Implement as `wallet.ts_hold(assignment, price, member)` which locks, checks, posts and writes `price_held`.
3. Cap: the inviting member = `ts.workspace.member` of `invited_by_id` in that workspace (fallback: `responsible_id`).
   If the member's role is capped and `monthly_cap > 0` and `committed_month(member) + price > monthly_cap` ->
   `UserError('سقف ماهانهٔ شما پر شده است (%s از %s). با مدیر پنل صحبت کنید.' % (fmt_toman(committed), fmt_toman(cap)))`.
   `committed_month(member)` = over this member's assignments (invited_by = member.user) and txn rows with txn_date in
   the current Jalali month (Asia/Tehran): `-SUM(hold) - SUM(release) - SUM(refund) + 0*debit` ... precisely:
   `SUM(CASE type WHEN 'hold' THEN -amount WHEN 'release' THEN -amount WHEN 'refund' THEN -amount ELSE 0 END)`.
   (A hold is positive spend, a release or refund gives it back; the debit converts a hold and changes nothing.)
4. Audit `credit.hold` (amount, assignment, member). Refusals audit `credit.refused` with kind insufficient|cap.
- Campaign launch (`ts.campaign.ts_launch`) creates assignments in one transaction: the first refusal aborts the whole
  batch (desired: all-or-nothing). Before the loop, `ts_launch` for prepaid checks `available >= price * n` once and
  raises the insufficient message with the total, so the user gets one clear message instead of a partial batch.
- Open-link campaigns (`kind='open_link'`): on create/launch for prepaid require `available >= price * min(open_max or 10, 10)`
  else refuse («برای پیوند باز دست‌کم اعتبار %s لازم است (۱۰ استفاده).»). Each join creates an assignment -> normal hold;
  if the hold fails at join, the participant sees «ظرفیت این پیوند پر شده است. با مرکز مشاوره تماس بگیرید.» (no money
  words to the participant) and the panel gets a `credit.refused` audit + low-balance notification.
### 5.2 Charge at completion (`ts.wallet._debit_usage` override)
- Single: `_debit_usage(attempt)` finds the assignment (`attempt_id` or `assignment_id`); if `price_held > 0` and the
  `release:<id>` row does not exist yet: post `release` (+price, reason completion) then `debit_usage` (-price, units 1,
  key `usage:<attempt>`), both under the lock. Otherwise (free, unpriced, or already converted) debit amount 0 as today.
- Battery: the FIRST attempt of the run to complete converts the hold (release + debit of the full battery price); every
  later attempt posts `debit_usage` amount 0, units 1, key `usage:<attempt>`. `_reconcile` (one usage event + one debit
  per done attempt) therefore stays valid without changes.
- After a debit, if `available < low_threshold` -> `_ts_low_balance_notify()` (section 6).
### 5.3 Release (hold not converted)
- `action_withdraw`, `action_decline`: post `release:<id>` (+price_held) if no debit for the assignment's attempts exists.
- Expiry: daily cron `ts.assignment._cron_release_expired_holds()`: assignments with `price_held > 0`, no `user_id`
  (never accepted), `invite_state() == 'expired'`, no release row -> release (reason expiry). An accepted invitation is
  never released by the cron (an accepted battery never expires mid-way).
- Void (`action_void`, existing) refunds exactly the debit (now money) -> unchanged code; for a battery, voiding the
  first attempt refunds the whole battery price, voiding another attempt refunds 0: document it in the void dialog text
  («بازگشت اعتبار: %s»).
### 5.4 Top-up by invoice (native account.move)
- `account.move.ts_workspace_id` (Many2one ts.workspace, index, copy=False; visible on customer invoices and credit
  notes; domain: `partner_id.commercial_partner_id == workspace.partner_id.commercial_partner_id`, enforced by a constraint).
- Hook: `account.move.write` override: after super, for moves with `ts_workspace_id` and `move_type == 'out_invoice'`
  and `state == 'posted'` whose `payment_state` is now in `('paid', 'in_payment')` and was not before -> `wallet._post('topup',
  +amount, 0, 'topup:<move id>', 'topup')` where amount = sum of `price_subtotal` of lines with `product_id.ts_topup`
  (if no such line: `amount_untaxed`). Rounded to integer Rial. Also handled by `_cron_sync_topups` (daily) that scans
  posted paid invoices with `ts_workspace_id` lacking a `topup:` row (safety net for payments registered in ways that
  skip write, e.g. reconciliation widgets). Credit notes: an `out_refund` with `reversed_entry_id` = a topped-up move,
  when posted and paid -> `adjust` of `-min(amount_untaxed, topup amount)` with key `topup-rev:<credit note id>`.
  Audit `credit.topup` / `credit.topup_reversal` with the move name.
- Back office: on the workspace form (prepaid only) button «صدور فاکتور اعتبار» -> `account.move` form action with
  context defaults: `move_type=out_invoice`, `partner_id=ws.partner_id`, `ts_workspace_id=ws.id`, one line with the
  top-up product, qty 1, price 0 (to be typed). Smart button «فاکتورها» listing the workspace's invoices.
- Panel credits page (section 6) lists the invoices with links `/my/invoices/<id>?access_token=<move._portal_ensure_token()>`
  (native portal invoice page + PDF). The link is generated only for members with `credits:read`.
### 5.5 Low balance (section 6) and messages
- Participant-facing texts never mention money or credit. Panel texts use تومان only.

## 6. Pages (panel, website 4) — counseling vocabulary, «شما», no «!», no «متأسفانه»
- `/my/workspaces/<ws>/credits` (exists, rework for prepaid): cards «موجودی قابل استفاده» (available), «رزروشده برای
  دعوت‌های باز» (held), «مصرف این ماه» (renamed «کسرشده این ماه» in the 2026-10-12 UX pass, see the end of this section); table of this month's usage per counselor (name, invitations, amount) for
  `credits:read`; caps editor per capped member (owner/admin/clinic_director); price list of the panel's granted
  items (`allowed_instruments()` ∪ `allowed_batteries()` with `fmt_toman`); invoices list (number, Jalali date, amount,
  state «پرداخت‌شده / در انتظار پرداخت», link). For a clinician: own cap and «مصرف این ماه» only, plus the price list.
  Free panels keep today's page.
- Invite wizard and campaign form (prepaid): each item card shows «هزینه: … تومان»; unaffordable items are shown
  disabled with «اعتبار کافی نیست»; wizard summary shows the price before sending; after the cap/insufficient
  refusal the UserError text is shown as the page error (existing pattern).
- Dashboard (prepaid, `credits:read`): one line «اعتبار: … تومان · رزروشده: …» linking to credits; clinician: own cap bar
  when capped.
- Low balance: `ts.wallet.low_threshold` becomes Monetary (default 0 = off; owner sets it on the credits page);
  `_ts_low_balance_notify()` creates one in-app notification of type `low_balance` (add to TYPES/TITLES) for members
  with `credits:read`, at most once per 24 h per wallet (`low_alert_sent_on`). SMS body added to SMS_BODIES (Phase 5
  may reword). Text: «اعتبار پنل «%s» به %s رسید. برای ادامهٔ دعوت‌ها اعتبار را شارژ کنید.»
- Back office: wallet form shows Monetary columns; `ts_grant`/`ts_adjust` accept Rial amounts (multiples of 10).
  A base price above 50,000,000 Rial (`PRICE_WARN_RIAL`, ts_billing/models/catalog.py) shows an onchange warning on the
  instrument and battery forms (a toman/Rial slip; nothing is blocked, G8-P4-2).

**UX pass 2026-10-12 (G7/G8 audits; presentation only, `ts_hold` / `ts_launch` / campaign creation decide as before):**
- Credits page cards: «موجودی قابل استفاده» (available), «رزروشده برای دعوت‌های باز» (held) and «کسرشده این ماه»
  (the month's debits, `wallet.ts_month_debited()`); the held + debited figure moved to the per-member table as
  «تعهد این ماه» (what the monthly cap counts; every capped member listed, ۰ when none). Order: cards, total line
  («کل اعتبار پنل = قابل استفاده + رزروشده»), low notice, «شارژ اعتبار» card (button «درخواست شارژ اعتبار» ->
  `ws.ts_topup_request_url()` = `/contact?topic=credit&panel=<code>`, the contact page prefills «کد پنل» and
  «مبلغ شارژ»), invoices, history (collapsed), commitment per member, caps, threshold, price list (collapsed).
- Capped roles without `credits:read` in a prepaid panel reach their own page from the panel menu as «هزینهٔ دعوت‌ها»
  (ts_billing appends the item to ts_panel's MENU with a `when` check). The member page offers «بدون سقف» / «با سقف»
  (`cap_mode`); ۰ typed in the caps table still means no cap.
- Refusal texts reworded (INSUFFICIENT, INSUFFICIENT_ASK, INSUFFICIENT_BATCH, CAP_OVER, OPEN_LINK_FLOOR): balances only
  for `credits:read` members, others are told whom to ask (`tools.credit_ask`). The invitation wizard refuses an
  unaffordable item already at step 2 (`TsBillingInvites._read_item`) with the same text as creation; `ts_hold` still
  decides at creation.
- The dashboard count tile is «سنجه‌های تکمیل‌شدهٔ این دوره» (a count, never «مصرف»).

## 7. Company currency switch (one-off, guarded, part of ts_billing install)
`ts.wallet._ts_switch_company_currency()` called from a `<function>` data record (runs on install and every upgrade,
idempotent): company 1 with `currency_id.name == 'USD'`: assert `account.move` count == 0 and `account.move.line` count
== 0 and no `product.template` with a non-zero price; activate IRR, set IRR `rounding=1.0`, `decimal_places=0`,
`position='after'`; write `company.currency_id = IRR`; log an audit `billing.currency_switch`. If the assertions fail,
log a WARNING and skip (never raise during install). If the currency is already IRR, do nothing.
Rehearsal proves eot.ir is unchanged by this (guard). Pricelists created afterwards are in IRR automatically.

## 8. Permissions and privacy
- New perm keys in ts_org perms: `credits:manage` (owner, admin, clinic_director, hr_admin): edit caps, threshold.
  `credits:read` unchanged. Add labels in perm_labels.py and the matrix doc.
- Invoices name the institution only. No participant data on any accounting record.
- Audit events: `billing.mode`, `billing.currency_switch`, `credit.hold`, `credit.release`, `credit.debit`,
  `credit.refused`, `credit.topup`, `credit.topup_reversal`, `credit.cap_change`, `credit.threshold_change`.

## 9. Tests
- ORM `tools/prod/tests_billing.py` (clone only; savepoints; never commits): product sync on publish/rename; price via
  pricelist (default and per-partner pricelist); hold/insufficient/cap refusals with exact messages; hold->release+debit
  on completion (single); battery first-attempt conversion, later attempts 0; withdraw/decline/expiry release once
  (idempotent, cron twice = same state); void refund amount; topup on paid invoice (create invoice, post, register
  payment via `account.payment.register` wizard), cron safety net, credit note reversal; free workspace unchanged
  (amount 0 everywhere); currency switch function idempotent and skipped when moves exist (test on a savepoint with a
  fake draft move); `_reconcile()` returns no problems after the whole scenario; Jalali month boundary for the cap
  (freeze dates by writing txn_date).
- HTTP `tools/prod/ts_http_billing.py`: owner sees credits page with balance/held/prices/invoices; clinician sees own
  cap; wizard shows price and disables unaffordable items; refusal messages render; participant never sees money text
  on /invite, /take, transition and result pages (grep for تومان/اعتبار/ریال).
- Register both in tools/vps/ts_rehearse.sh when `ts_billing` is in the module list.

## 10. Module facts
`addons/ts_billing`: depends `ts_battery`, `account`, `product` (both installed live), version 20.0.1.0.0. Views carry
website_id for website pages; back-office views normal. Templates in Persian per docs/ux_writing. New CSS in
`static/src/scss/billing.scss` registered in `ts_website.assets_ts`. Reuse `ts_website.jdate`, `.ts-confirm`, `.ts-bdi`.
