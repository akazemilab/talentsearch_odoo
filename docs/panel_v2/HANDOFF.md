STATUS: PHASE 1 APPROVED

# Panel v2 — handoff between Phase 1 (design) and Phase 2 (implementation)

The first line is the switch. It becomes `STATUS: PHASE 1 APPROVED` only after the owner's
explicit approval («تأیید فاز ۱»). While it says DRAFT, Phase 2 must not start and `addons/`
must not change.

- Design written: 2026-10-01 (9 Mehr 1405). Approved by the owner 2026-10-01 (defaults for D4, D6, D7, D8 accepted).
- Last finished stage: **S6 `invites`** (shipped 2026-10-01, label `pv2s6`, commit c722bb9).
- **Next stage: S7 `campaigns`** (branch `pv2-7-campaigns` is rebased on main and under full rehearsal; then S8 `import`, drafts in /root/s8wip on the VPS).

## 1. Read in this order (Phase 2)
1. This file.
2. `07_build_plan.md` (the stage you are on; section 0 rules).
3. `05_permissions_matrix.md` and `04_data_model.md` (the parts the stage names).
4. `08_design_system.md` (before writing any template).
5. `03_ia_and_ux.md` (the pages of the stage) and `02_feature_catalog.md` (acceptance criteria
   by feature id).
6. `CLAUDE.md` at the repo root and Project memory `areas/eot-lessons-learned.md`.
`01_research.md` and `06_gap_analysis.md` explain why; read them when a rule looks odd.

## 2. Decisions

### 2.1 Taken in Phase 1 by the designer (the owner may overrule any of them at the gate)
| # | Decision |
|---|---|
| T1 | All new code lives in a new top-level module `ts_panel` (depends on `ts_talent`); `ts_core` changes only in S1, `ts_org` in S1, S17 and S20, `ts_sms` in S20 |
| T2 | Staff URLs stay under `/my/workspaces/<id>/…`; server-rendered pages, JavaScript only as enhancement |
| T3 | Add a panel-scoped client record `ts.panel.client`; the participant's account stays separate; responsibility moves from the invitation to the client; never link people by name |
| T4 | The invitation (`ts.assignment`) remains the share grant; no separate grant model; consents get an append-only ledger |
| T5 | New role `admin` («هماهنگ‌کنندهٔ پنل»): manages clients and invitations, never sees a result |
| T6 | One active membership per person per panel; a practising owner is a flag on the owner (fixes the solo-psychologist gap) |
| T7 | Credits: one wallet per panel, append-only ledger, debit when the attempt is scored, idempotent per attempt, **no reservations**, self-shared results not charged, free mode records `amount = 0` and blocks nothing |
| T8 | Group report threshold 5 with complementary suppression; counts only shared results |
| T9 | Private specialist notes: not built |
| T10 | Colleague invitations: link only, no SMS |
| T11 | Staff session idle timeout 8 hours; re-authentication (10 minutes) before exports, ownership transfer, closing a panel, adding an owner, data requests |
| T12 | Open link / QR invitations allowed, capped at 60 joins and 14 days by default, closable any time |
| T13 | One automatic reminder per invitation plus at most three manual ones; SMS quiet hours 21:00–08:00 Tehran; at most 5 SMS a day per person |
| T14 | No bulk export of clinical results; no raw answers anywhere outside the participant's own attempt |
| T15 | Persian only |
| T16 | Retention periods as proposed in `04_data_model.md` section 6 (see D7); the retention job ships switched off and only reports what it would remove until the owner turns it on |
| T17 | In an education panel, a shared result of an ordinary (non-matrix) instrument is shown as the band summary; TALENT-INV-15 keeps today's report without the answers |
| T18 | Imported historical people are locked: no invitation, reminder, message, merge or contact edit until the owner changes one setting |
| T19 | New SMS kinds (reminders, messages to staff) ship switched off; the owner turns them on in Settings. Reminders by SMS only for invitations whose consent tick mentioned the reminder |
| T20 | Search text is never put in a URL, a saved view or a job (it can be a name) |
| T21 | Accepting a colleague invitation while already a member of that panel is refused; the owner changes roles |
| T22 | Moved out of this plan (the brief listed them under "must have now"): co-brand colour, invoices list (comes with the paid phase), low-credit notification (meaningless while free), guardian's own view of the child's status and result, email as a notification channel (D8). Sessions list is in the plan (S18) but depends on Odoo's stock device models working for accounts without a password |

### 2.2 Answered by the owner on 2026-10-01 (9 Mehr 1405)
| # | Question | Answer | Affects |
|---|---|---|---|
| D1 | Clickable mockups of four screens before coding? | **No.** The owner judges the real pages on a clone after S2 | — |
| D2 | Minors: how is the guardian's consent recorded? | **The panel attests** that it holds the guardian's consent, plus the minor's own assent text. Guardian-link mode (S16b) is not built | S16 |
| D3 | May a self-taken result be shared with more than one panel at a time? | **Yes, up to 3 panels**; each share is revoked separately (`ts_panel.share_max_panels = 3`) | S15 |
| D5 | Create client rows for the 108 historical people in workspace 1? | **Yes, locked**: names only; no invitation, message, contact detail, merge or release until the owner decides otherwise (T18). Migration M4 is approved | S4 |

### 2.2b Still open (each has a default that Phase 2 uses if nothing else is said)
| # | Question | Default | Affects |
|---|---|---|---|
| D4 | Make support/emergency access a technical lock on clinical data for platform managers? | No; logged procedure, owner notified | S14b |
| D6 | Group-report threshold 10 for schools (education practice) instead of 5? | 5 everywhere | one setting |
| D7 | Retention table (`04_data_model.md` 6): approve or change periods, then switch the job on | As proposed, job off | S18 |
| D8 | Email as a notification channel (needs a sender address and a mail setup that does not touch eot.ir)? | No email | after the plan |

Approving Phase 1 also approves the bookkeeping migrations M1–M3 and M5–M8 of
`04_data_model.md` section 5: they add columns and rows about records that already exist
(audit IP hashes, one client row per existing invitation, expiry dates, consent rows copied
from existing consent fields, last-activity dates). They send nothing and change nothing a
person can see. M4 (the 108 people) was approved separately as D5.

### 2.3 Carried over, not blocking
- Approve or reject the organization/clinic panels waiting in the pending queue.
- `benefits` panels stay unoffered.
- Release of the 114 imported results to participants: no change, no message to those people.

### 2.4 Needs a lawyer or an accountant, not a developer
| # | Item |
|---|---|
| L1 | Terms text `panel-terms-1405-07-v2` (already open) |
| L2 | A participant asks for erasure while a clinician must keep records 5 years (PCO ethics 6-4): which wins, and how is it said in the terms |
| L3 | Consent and assent wording for under-18s; who counts as guardian |
| L4 | Privacy text against the 1402 cyberspace directive (two months' notice before changes; "identity data stored encrypted" is not met by the database today) |
| L5 | Before any paid phase: eNamad, tax tracking code, electronic invoices, VAT treatment of reports |

## 3. Defects found in the live product while designing (each has a stage)
| Gap | What is wrong today | Fixed in |
|---|---|---|
| G30 | The TALENT-INV-15 report has no «لغو اشتراک» button and no «ارسال برای مشاورم»; a student who accepted an invitation with sharing on cannot revoke it from the report | S0 |
| G31 | The share-by-code page promises the counselor sees only bands; for TALENT-INV-15 the counselor sees the whole report without the answers | S0 |
| G28 | No usage event is recorded for TALENT-INV-15 completions in a panel | S0 |
| G1 | A solo psychologist cannot open the clinical results of their own clients | S1 |
| G2 | One person can hold several memberships in one panel; the effective role is arbitrary | S1 |
| G29 | A self-shared result of an ordinary instrument gives the counselor a 404 | S13 |
| G12 | Platform operators can read invitation names and contacts in the back-office | S17 |
| G7 | School students (under 18) take TALENT-INV-15 with no guardian step | S16 |
The full list is `06_gap_analysis.md` section 2.

## 4. Facts Phase 2 must not get wrong
- eot.ir (website 1) never changes; every ship reports `eot.ir UNCHANGED`.
- `/my`, `/my/home`, `/my/account`, `/my/security` are stock portal routes shared with eot.ir:
  an override returns `super()` untouched unless `request.env.website._ts_is_current()`.
- The instance-wide password policy and `res.users._get_session_token_fields()` are shared
  with eot.ir: do not change them.
- Kavenegar is enabled live. A code path that sends SMS reaches real phones after the ship.
- The 108 historical people have no account and no consent tick; nothing may message them, and
  the 114 imported results stay `released = False`.
- Platform operators (`group_ts_user`) must not gain access to client identities.
- No names, phones or emails in audit `detail`, job `params`, notification titles, logs,
  commits or chat.

## 5. Pitfalls already paid for (from `CLAUDE.md` and the lessons file)
- `ts_talent` overrides `ts.attempt.action_submit` for matrix attempts **without calling
  `super()`**: any hook placed below it (in `ts_org`, `ts_sms`) is skipped for TALENT-INV-15.
  Hooks for "an attempt was finished" go in `ts_panel`'s override, which wraps all of them.
- An audit row written just before `raise request.not_found()` is rolled back with the
  request: deny events use `log_denied()` (own cursor).
- Edit a module's XML or Python only when that module is in the stage's upgrade list;
  otherwise extend it from `ts_panel` (rule 7 of the build plan).
- New `ir.ui.view` records only in modules that depend on `website` (never `ts_core`).
- A node between a `t-if` and its `t-else` gives a 500; ORM suites never render templates, so
  every template needs an HTTP test. `ts check` catches the first.
- An inherited view whose target is removed breaks every page that renders it: when a v1
  template goes, its inheritors go in the same ship (`ts_org.tpl_workspace` and
  `ts_sms.tpl_workspace_sms` together, in S20).
- `hasclass()` does not match `t-attf-class`; `position="replace"` cannot target text nodes.
- QWeb `t-set` inside a `t-call` body is not passed: pass parameters as attributes.
- Odoo 20 access rows live in `security/ir.access.csv` (`operation` is a subset of `crud`).
- Binary fields need `base64.b64encode(x).decode()`.
- `is_company` is recomputed on create: write it again after create.
- Stored phones are normalised: compare normalised values.
- Never put two models in one recordset union in a controller.
- `ts db stop` drops the clone; `ts db halt` only stops its server.
- Poll with `ts wait NAME 50`; no `sleep` near the 60 s bridge limit.
- Do not edit the repo directory that a running rehearsal syncs from; use `ts wt` for parallel
  work.
- Persian text: slice in Python, never `cut -c`.
- Adding a record of an existing kind can break counts in old tests: grep the tests first.
- A test must check visibility (no `d-none`, real render), not only that a string is in the
  HTML.
- Push with an explicit `origin <branch>` and read the ref line.

## 6. Stage log (Phase 2 fills this in)
| Stage | Label | Shipped on | Commit | Notes |
|---|---|---|---|---|
| S0 | tooling | 2026-10-01 | d378b5d | `ts_panel` installed; G28, G30, G31 fixed; fixtures + ts_check/ts_shot rules; rehearsal eot_ts30 green, eot.ir UNCHANGED. Slow step: three rehearsals (fixtures failed twice: clinical panel needs an emergency contact; member verification needs the manager group). |
| S1 | perms | 2026-10-01 | 7ca39bb | `admin` role, permission registry (33 strings), one active membership, audit hardening + deny events; rehearsal eot_ts31 green, eot.ir UNCHANGED. Slow step: first rehearsal wasted on three test-infra bugs (ICP API, slot path, can_invite). |
| S2 | shell | 2026-10-01 | bc08113 | Shared shell, dashboard, settings, state pages, header link; rehearsal eot_ts32 green, eot.ir UNCHANGED. Lesson: Bootstrap overrides --success/--danger. |
| S3 | members | 2026-10-01 | 2bbb31c | Members page, invites resend/revoke, role change, deactivate, role help, re-authentication; rehearsal eot_ts33 green, eot.ir UNCHANGED. |
| S4 | clients | 2026-10-01 | 4d18327 | Client model `ts.panel.client` (single place of responsibility; `responsible_id` on assignment/attempt is a NON-stored related field), migration M3-M5 (1 invite client, 108 locked import clients), list with filters/sort/paging and search kept in the session, client page. Rehearsal eot_ts34 green (second run), eot.ir UNCHANGED. Deviations: `channel`/`expires_at` on assignment move to S6; audit event `client.responsible_change` added next to the old ones. Slow step: first rehearsal wasted on stored-related recompute running constraints. |
| S5 | clients-edit | 2026-10-01 | bb2e414 | Client edit/archive/merge, groups page (`W/groups`, `groups:manage`), bulk responsible change. Rehearsal eot_ts35 green (second run), eot.ir UNCHANGED. Lessons: flush between freeing and re-taking a unique value in merge; menu tests must not depend on menu length. |
| S6 | invites | 2026-10-01 | c722bb9 | Invite wizard, invitation list, stored `expires_at` (+ deadline write rule), dashboard without forms, old page at `W/legacy` until S20. Rehearsal eot_ts36s green (second run), eot.ir UNCHANGED. Deviations: `stopped` attempt state on withdraw deferred to S18; no QR decoder in tests. |
