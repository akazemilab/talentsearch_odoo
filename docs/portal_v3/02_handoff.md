# Client portal v3 — handoff (first release, 1405-07-11 / 2026-10-02)

## What changed and why

| Journey | Before | After |
|---------|--------|-------|
| Returning person opens `/my` | Three equal cards; nothing said who had invited whom or when | One dominant action decided from the real state (open invitation → unfinished attempt → result released in the last 14 days → peaceful state with a path to history); every row names the assigning organisation and a date; deadlines shown when set |
| Finding one's way | Seven pills overlapping with the header | Four destinations: کارهای من / سنجه‌ها و نتیجه‌ها / چه کسی می‌بیند / حساب; notifications stay in the header with the unread count; the account page is the hub (notifications, sharing, data, devices, password, help, support, sign out) |
| Invitation page | Marketing header and a four-column footer; the sharing permission looked like a dark button (it used the player's option-tile class, the checkbox was invisible) | Quiet layout (logo only, slim footer); the permission is a visible checkbox with its text |
| Consent page | «فقط شما… با هیچ کارفرما یا مرکزی به اشتراک گذاشته نمی‌شود» for every attempt — wrong for attempts taken on a panel's invitation with sharing accepted | «چه کسی نتیجه را می‌بیند» comes from the real invitation: purpose (education / employment / clinical) and the accepted share level; who invited is named under the title; self-started attempts still say «فقط شما» |
| Submission | A one-line notice on the report | A received block: what was received, that answers no longer change, who sees the result, one next step («خواندن نتیجه» / «بازگشت به کارهای من») |
| Finished result that is not released (legal hold, imported) | Redirect loop between `/my/assessments/<id>` and `/take/<token>` | An honest page: why it is not available, the tracking id, support |
| Report | Opened with report id, engine and contract versions before anything readable | Plain-language lead (whose result, when, what the measure describes), summary table, then a folded «جزئیات گزارش», per-dimension texts, «نتیجه‌های قبلی همین سنجه» with the comparability note (same contract version only; a changed number is not improvement or deterioration), limitations |
| Results list | One flat table | Unfinished first (with progress and last save), then results grouped per instrument, newest first, with the scoring-contract version and whether the result is available |
| Site-wide | Bootstrap's `--success`/`--danger` leaked into status pills outside the panel (2.7:1) | Design-system colours on the whole site; identifiers (e-mail, codes, versions) keep Latin digits through a plain Vazirmatn face while everything else renders Persian digits |

Instrument content is untouched: item wording, order, the five anchors, ten items per page, autosave and the idempotent
submission are exactly as before (R3). Progress stays the true answered/total count (R4/R5). No tracker, no new storage
of answers in the browser (R6). One question per page was not adopted: the validated grouping has precedence (R7).

## Screens inspected

`/my` (four states), `/my/assessments`, report with and without `?submitted=1`, unavailable result, `/take/<token>`
consent for a company invitation / a school invitation / a self-started attempt, player, review, `/invite/<token>`,
`/my/sharing`, `/my/account`, `/my/notifications`, `/my/privacy`, `/my/sessions` — each at 320, 390, 430, 768 and 1280 CSS px
(`tools/vps/ts_shot.py`, `TS_SHOT_WIDTHS`). Findings fixed from the shots: invitation permission checkbox, consent kicker
contrast (1.3:1 → brand colour), status pill contrast, the results list without navigation.

## Tests actually run (clone eot_ts73, then the full rehearsal eot_ts68r)

- `ts_http_pv3.py` 24/24: home dominant action for four states, four-item navigation, no English words on the home,
  consent texts for company / school / self attempts, unavailable page (200, no redirect), submission block present only
  with the flag, grouped list, lead before summary, folded details, history with the comparability note, account hub.
- Older suites on the same clone, all green: `ts_http_pv2_15.py` 50/50 (one check rewritten for the four-item navigation),
  `ts_http_flow.py` 26/26, `ts_http_org.py` 27/27, `ts_http_talent.py` 43/43, `ts_http_pv2_19.py` 60/60, `ts_http_pv2_1.py` 20/20.
- Headless audit at five widths: no horizontal overflow, one h1, labelled fields, RTL; remaining flags are the selected
  option tile in the player (white on brand-deep, the sampler reads the page background: false positive).
- Not run: screen-reader sessions, 200 % zoom (only the 320 px reflow), formative sessions with participants. This is
  an expert review, not user validation. A test plan for five participants (two with low digital literacy) is in section 5.

## Evidence that shaped decisions

See `01_gap_list_and_plan.md` section 3. Browsing of the original papers was not done from this session; the summaries
supplied with the brief were used as given, and no further claim was attributed to them.

## Remaining dependencies (not solvable from the frontend)

- Result release is immediate for every instrument today (`action_submit` sets `released`). If clinical results are to
  wait for a specialist's review, that is a model change (release queue) plus notification texts — policy decision first.
- Minors and guardians: the S16 attestation stays; no guardian account or proxy flow exists (owner decision D2).
- Urgent help: the only approved resource in copy is ۱۱۵; no crisis pathway beyond «با یک متخصص مشورت کنید» — clinical
  policy needed before anything stronger is shown.
- Messaging with a professional: no service exists; none was added.
- Notifications: the centre lists events; splitting action-required from informational needs event types to carry that
  flag (model change) — left for a later stage.
- Password change lives on Odoo's stock `/my/security`; its page is still Odoo-styled.

## 5. Formative test plan (when participants are available)

Five people (two with low digital or health literacy, one screen-reader user), their own phone, tasks: open an
invitation link, start and pause, resume from the home page, submit, then in their own words say what the result means and
who can see it. Measure task success, errors and recovery, time to first correct answer to "who sees this"; no leading
questions about visual preference.
