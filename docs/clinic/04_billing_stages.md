# Phase 4: prepaid billing on native Odoo (`ts_billing`), stage plan (2026-10-11)

Source of truth for the design: `01_architecture.md` §2.3 and §4; decisions in `02_decisions.md`.
Live facts at planning time: company 1 «Emotion of Thought Institution», currency USD, `account_move` count 0,
`account_accountant` 20.0.1.1 installed (Enterprise), `sale` not installed (not needed: invoices are created directly),
3 wallets with 0 transactions, Sepehr workspace id 4 («سپهر هیجان اندیش») live since clinic3.

Rules for every stage: built and tested on an `eot_ts*` clone, one rehearsal per bundle, guard `eot.ir UNCHANGED`,
no live change until B5. Each stage ends with something the owner can look at (a page or a back-office form on
the clone, screenshots by `ts-shots`).

| Stage | Scope | What the owner sees |
|---|---|---|
| B1 Money foundation | Currency migration script USD -> IRR (asserts `account_move` = 0 and currency USD first; IRR decimal places 0), `fmt_toman()` display helper, product category «استعدادیاب / سنجه‌ها», one service product per published instrument and battery (`ts_ensure_product()` on publish + one-off sync), top-up product «اعتبار پیش‌پرداخت استعدادیاب», pricelist lookup helper (`property_product_pricelist`, default «عمومی»). Tests: products sync idempotent, price lookup, currency script refuses when moves exist. | Back-office product list with every instrument and battery as a product, prices editable in the standard form; sample prices on the clone shown in تومان in the panel catalog. |
| B2 Wallet v2 + invite checks | `ts.workspace.billing_mode` free/prepaid; `ts.wallet.txn.amount` / `balance_after` Monetary (old integer rows migrated as 0), types hold/release/topup, idempotency keys; invite-time checks in order (catalog, `available >= price`, cap placeholder) with the exact Persian refusals; hold per assignment, all-or-nothing for campaigns; charge on first submitted instrument (battery) or on submit (single); release on expiry/withdraw/decline; open-link floor `price * min(open_max, 10)`. Tests: balance math, idempotency, battery charged once, refusals. | On the clone, Sepehr set to prepaid with a small grant: a counselor's invite goes through, the next one is refused with «اعتبار پنل کافی نیست…»; the ledger page shows hold -> usage. |
| B3 Caps + credits page | `member.monthly_cap`, `month_spent` over the Jalali month (`ts_website.tools.parse_jdate` family), refusal text, cap bar on the counselor dashboard, credits page per role (§4.6), low-balance SMS + in-app notice once per day. Tests: cap arithmetic across a month boundary, visibility per role. | Credits page as owner vs as counselor; a capped counselor blocked at the cap. |
| B4 Top-up by invoice (native) | `account.move.ts_workspace_id`, back-office button «صدور فاکتور اعتبار» (partner, top-up product, qty 1, unit price), hook on `payment_state` paid/in_payment -> `topup` idem `topup:<move>`, credit note -> negative `adjust`, invoices listed on the credits page, native portal PDF. Taxes: none until the accountant decides. Tests: paid invoice credits the wallet once, reversal debits once, unpaid does nothing. | Super admin issues an invoice on the clone, registers the payment, the panel balance rises; the institute admin sees the invoice and downloads the PDF. |
| B5 Rehearsal + ship + live | Full suites, `ts-risk-reviewer`, `ts-shots`, rehearsal, ship. Live, in this order: currency switch, Sepehr -> prepaid, real prices set by the owner, first real invoice issued by the owner, payment recorded by the owner. | The live Sepehr panel in prepaid mode with a real balance. |

Owner decisions needed before B5 (not before B1):
1. Confirm §11 items 1-7 of the architecture (defaults stand unless changed).
2. The currency switch of company 1 to IRR is one-way and happens live in B5; confirm.
3. Real prices per instrument and battery, in تومان (entered by the owner in the product form, or sent as a list).
4. Low-balance threshold (default proposal: price of the most expensive granted battery x 3).

Model routing: stage design here; implementation stages B1-B4 in the main session on Sonnet 5.5 with
`ts-runner` (haiku) for clones and tests, `ts-shots` (sonnet) for screenshots; B5 review by `ts-risk-reviewer` (opus).
