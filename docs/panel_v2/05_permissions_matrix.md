# Panel v2 — 05 Permissions matrix

Three layers, each answering one question (OWASP Authorization Cheat Sheet; WorkOS two-layer
model; see `01_research.md` 2.2):

1. **Role → permissions**: what kind of action may this member do in this panel?
2. **Relationship → which records**: is this client theirs to see?
3. **Attributes → how much detail**: share level, consent, verification, release, panel state.

Deny by default: a permission that is not granted is refused; an unknown permission string
raises `ValueError` (a programming error must not pass silently). Every check is on the server,
on every request, on the specific object.

## 1. Roles

| Code | Persian label | Panels | In one sentence |
|---|---|---|---|
| `owner` | مالک پنل | all | Runs the panel: people, settings, credits, audit. Sees results only at the level the panel type allows, and clinical results only if `owner_practices` and verified |
| `admin` (new) | هماهنگ‌کنندهٔ پنل | all | Office work: clients, groups, invitations, status. **Never sees a result** |
| `counselor` | مشاور | education | Own clients and the unassigned queue; education-level results |
| `clinic_director` | مدیر مرکز بالینی | clinical | Sees all clients; clinical results when verified |
| `clinician` | متخصص بالینی | clinical | Own clients; clinical results when verified |
| `hr_admin` | مدیر منابع انسانی | employment | Sees all candidates; band summaries |
| `hiring_manager` | مدیر استخدام | employment | Own candidates; band summaries |
| `reviewer` | ارزیاب | employment | Read-only: all candidates, band summaries |
| `benefit_admin` | مدیر طرح رفاهی | benefits (not offered) | Same permissions as `admin` |

One active membership per person per panel (`04_data_model.md` 2.1). A person may hold
different roles in different panels; data never crosses panels.

## 2. Permission strings × roles

`✓` granted · `—` refused · `edu` / `emp` / `clin` = only in that panel purpose.
Registry: `ts_org/models/perms.py`, `ROLE_PERMS: dict[role, frozenset[str]]` built from this
table. `member.has_perm(p)`; `member.perms()` returns the effective set after section 3.

| Permission | owner | admin | counselor | clinic_director | clinician | hr_admin | hiring_manager | reviewer |
|---|---|---|---|---|---|---|---|---|
| `panel:view` (enter, dashboard) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `panel:profile` (name, logo, contact, client word) | ✓ | — | — | ✓ | — | ✓ | — | — |
| `panel:settings` (terms, ownership, closing) | ✓ | — | — | — | — | — | — | — |
| `panel:transfer` (hand ownership over) | ✓ | — | — | — | — | — | — | — |
| `panel:close` | ✓ | — | — | — | — | — | — | — |
| `members:read` | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `members:invite` (invite, send again, revoke an invitation) | ✓ | — | — | ✓ | — | ✓ | — | — |
| `members:manage` (role, deactivate) | ✓ | — | — | — | — | — | — | — |
| `members:add_owner` | ✓ | — | — | — | — | — | — | — |
| `clients:read_all` | ✓ | ✓ | — | ✓ | — | ✓ | — | ✓ |
| `clients:read_own` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `clients:read_unassigned` | ✓ | ✓ | ✓ edu | ✓ | — | ✓ | — | ✓ |
| `clients:write` (create, edit) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `clients:assign` (set responsible) | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `clients:be_responsible` | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `clients:archive` | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `clients:merge` | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `clients:import` (CSV) | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — |
| `clients:export` (list, no results) | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `groups:manage` | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — |
| `invites:create` (single) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `invites:bulk` (group, campaign, open link) | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — |
| `invites:manage` (withdraw, remind, extend) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `results:summary` | ✓ emp | — | — | — | — | ✓ | ✓ | ✓ |
| `results:education` | ✓ edu | — | ✓ | — | — | — | — | — |
| `results:clinical` | ✓ clin, only with `owner_practices` | — | — | ✓ | ✓ | — | — | — |
| `results:export` (identifiable results file) | ✓ edu, emp | — | — | — | — | ✓ | — | — |
| `reports:group` | ✓ edu, emp | — | ✓ | — | — | ✓ | — | ✓ |
| `credits:read` | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `audit:read` | ✓ | — | — | — | — | — | — | — |
| `audit:export` | ✓ | — | — | — | — | — | — | — |
| `support:view` (see platform access to this panel) | ✓ | — | — | — | — | — | — | — |
| `help:view` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Notes
- Printing a result needs no separate permission: whoever may open a result at a level may
  print that level.
- There is **no bulk export of clinical results**. A verified clinician prints one client's
  report at a time.
- `clients:read_own` with `clients:be_responsible` refused (admin, reviewer) has no effect;
  they see clients through `clients:read_all`.
- `owner` keeps `clients:be_responsible` (existing behaviour: an owner working alone is the
  default responsible member).
- `clients:be_responsible` is read from the role table **before** section 3 is applied: a
  client can be assigned to a clinician who is still awaiting verification (as today); that
  clinician sees nothing until verified.
- **Who becomes responsible for a new client** (replaces `ts_default_responsible`, same
  outcome): the member who creates the client, if their role holds `clients:be_responsible`;
  an `owner` only when they are the sole active member or have `owner_practices`; otherwise
  nobody (unassigned queue). A member with `clients:assign` may choose someone else in the
  form. Clients created by an open link or a self-share start unassigned. Inviting an existing
  client never changes who is responsible.

Compatibility with the code before S1 (must hold unless marked NEW):
`INVITE_ROLES` = holders of `invites:create` minus `admin` (NEW) · `SEE_ALL_ROLES` = holders of
`clients:read_all` minus `admin` (NEW) · `can_assign()` = `clients:assign` (adds `admin`, NEW)
· the gate of the settings POST and of colleague invitations today is `can_assign()` =
`panel:profile` and `members:invite` (owner, hr_admin, clinic_director; `admin` is **not**
added to these) · `EDU_ROLES` = `results:education` · `VIEW_ROLES` in employment =
`results:summary` · `VERIFIED_ROLES` = `results:clinical` (adds practising owner, NEW, fixes
G1) · an unverified `clinician` or `clinic_director` can do nothing today (`can_act()` is
false, 404) and can do nothing after S1 either; the only change is that from S2 they get a
page that says why (A5).

## 3. Attribute conditions on the member and the panel

Evaluated in `member.perms()` before any role permission is used:

| # | Condition | Effect |
|---|---|---|
| A1 | Member inactive, or not a member | No permission. Response 404 |
| A2 | Panel `state` is `suspended` or `closed` | Only `panel:view`, which renders the «این پنل معلق است» / «این پنل بسته شده است» page with the platform's contact. Owner of a closed panel also keeps `clients:export` for 90 days |
| A3 | Panel `state` is `draft` | Only `panel:view` and `panel:settings` for the owner |
| A4 | Panel is `gated` (pending approval) | `invites:create`, `invites:bulk`, `clients:import` refused with the pending message. Everything else works, so the panel can be prepared |
| A5 | Role is `clinician` or `clinic_director` and `verification_state != 'verified'` | Every permission removed except `panel:view` and `help:view`. The panel page shows only the «در انتظار احراز صلاحیت» notice (from S2; before that the existing 404 stays). Same reach as today's `can_act()` |
| A5b | `owner` with `owner_practices` in a clinical panel, not verified | Only `results:clinical` is removed; the owner keeps running the panel |
| A6 | Staff session idle longer than `ts_panel.staff_idle_hours` | Signed out, sent to sign-in with `next` |
| A7 | Action is in section 6 and the last re-authentication is older than `ts_panel.reauth_minutes` | Redirect to `/my/reauth?next=…` |

## 4. Relationship rules (which client)

`member.can_see(client)`; `client` is a `ts.panel.client`. Assignments, attempts and results
are reached only through their client.

| # | Rule | Result |
|---|---|---|
| R0 | `client.workspace_id != member.workspace_id` | deny (404) |
| R1 | member has `clients:read_all` | allow |
| R2 | `client.responsible_id == member` | allow |
| R3 | `client.responsible_id` is empty and member has `clients:read_unassigned` | allow |
| R4 | (stage "next") member is in the client's care team | allow |
| — | otherwise | deny (404) |

Write rules on a client the member can see: edit needs `clients:write`; set responsible needs
`clients:assign` and the target must hold `clients:be_responsible`, be active, be in the same
panel and not be the client's own account; archive needs `clients:archive`.

Existing behaviour kept: when a member is deactivated, deleted or moves to a role without
`clients:be_responsible`, their clients return to the unassigned queue, audited.

## 5. Result level (how much of a result)

One function decides: `ts.assignment.result_level(member)` (and the same for an imported
attempt without an assignment). `visible_results()` stays as a wrapper for old callers.

Levels and what each one shows

| Level | Shows | Never shows |
|---|---|---|
| `none` | Nothing; the client is not visible to this member (404) | |
| `status` | Instrument, invitation state, dates, whether the participant shared | Any score, band or text |
| `summary` | The band (کم / متوسط / زیاد) per factor | Scores, interpretation texts |
| `education` | TALENT-INV-15: the participant's report **without the answers section** (`report_ctx(org_view=True)`, as today). Any other instrument: the same content as `summary` (band per factor). Today such a result gives a 404 to the counselor (gap G29) | Answers, specialist-only texts |
| `clinical` | The full report including specialist guidance texts | |

No level ever shows raw answers, item texts with answers, scoring keys or cut-offs.

Decision order (first match wins)

| Step | Condition | Level |
|---|---|---|
| 1 | Section 3 A1–A3, or `can_see(client)` is false | `none` |
| 2 | No attempt, or attempt `state` not `done` | `status` |
| 3 | Attempt `voided`, `erased` or `stopped` | `status` |
| 4 | Imported attempt (`source='import'`) in an **education** panel and member has `results:education` | `education` (owner decision of 8 Mehr 1405; imports stay unreleased to participants) |
| 5 | Attempt not `released` | `status` |
| 6 | `share_level == 'none'` (never shared, or revoked) | `status` |
| 7 | Client is a minor and `guardian_consent == 'none'` (from S16) | `status` |
| 8 | Employment panel, `share_level == 'summary'`, member has `results:summary` | `summary` |
| 9 | Education panel, `share_level == 'summary'`, member has `results:education` | `education` |
| 10 | Clinical panel, `share_level == 'clinical'`, member has `results:clinical` (so verified, A5) | `clinical` |
| 11 | otherwise | `status` |

Who sees which level, in short

| Panel | owner | admin | counselor | clinic_director | clinician | hr_admin | hiring_manager | reviewer |
|---|---|---|---|---|---|---|---|---|
| Education | education | status | education (own + unassigned) | | | | | |
| Clinical | status; clinical if practising and verified | status | | clinical if verified | clinical if verified (own) | | | |
| Employment | summary | status | | | | summary | summary (own) | summary |

Every time a result is rendered at `summary`, `education` or `clinical`, an audit event
`result.view` is written with `level`, `member_id`, the assignment or attempt reference and
outcome `ok` (existing events `assignment.result_view` and `attempt.result_view` are kept as
they are; the new name is used for new code paths). Printing writes `result.print`.

Sharing rules kept from today and made explicit: self-share by panel code works only for
education panels; a revoked share can be given again (the same assignment row returns to
`summary`, with a new consent record); `ts_panel.share_max_panels` counts only active shares
(`share_level != 'none'`).

Group reports (`reports:group`): only attempts that would reach `summary` or `education` for
this member are counted; a cell with fewer than `ts_panel.group_min_n` people is shown as
«کمتر از ۵ نفر», and when exactly one cell of a breakdown is hidden the next-smallest is
hidden too (complementary suppression). The report states «n از m نفر» and the filters used.

## 6. Actions that need a fresh re-authentication (A7)

`results:export`, `clients:export`, `audit:export`, `panel:transfer`, `panel:close`,
`members:add_owner`, a participant's own data export and erase request, and (platform side)
opening a support or emergency access.

Re-authentication = a new SMS code sent only to the account's verified mobile
(`ts.reauth.code`, `04_data_model.md` 3.7b), or the account password for accounts without a
verified mobile. The time is kept in the session (`ts_reauth_at`). Back-office users opening a
support or emergency access pass Odoo's own identity check instead.

## 7. Participant and guardian

| Subject | May |
|---|---|
| Participant (account) | See and continue own attempts; see own released results; share a result with a panel by code; revoke any share at any time; see who can see each result; request export or erasure of own data; set notification preferences |
| Guardian account (`account_is_guardian`) | Answer parent-report instruments about the client; see that result; give or withdraw guardian consent for a minor's assignment (guardian-link mode) |
| Minor's own account | Take the assessment after assent; see the own report in the participant wording. The school sees only what the consent allows (level `education`, or `status` when not shared) |

A participant never sees: other clients, the panel's member list beyond the name of the
responsible specialist and the panel's contact, internal ids, or audit rows.

## 8. Platform (back-office groups, unchanged names)

| Capability | `group_ts_user` operator | `group_ts_curator` | `group_ts_manager` |
|---|---|---|---|
| Tenants list, health counts, usage per tenant | ✓ | ✓ | ✓ |
| Approve, reject, suspend, resume a panel; verify a clinician | — | — | ✓ |
| Instrument catalog and versions | read | ✓ | ✓ |
| Global audit list | ✓ | ✓ | ✓ |
| Client identities, invitations | — (G12 fixed in S17) | — | ✓ |
| Attempts, answers, results | — | — | ✓ today; restricted to an open support/emergency access if D4 is taken |
| Open support / emergency access | — | — | ✓, with reason, time box, owner notified |
| Void an attempt, adjust a wallet | — | — | ✓ |
| Data-request queue | read | — | ✓ |

## 9. Responses and logging

| Situation | HTTP | Page | Audit |
|---|---|---|---|
| Not signed in | 303 to sign-in with `next` | | — |
| Signed in, not a member of the panel, or object not visible (R0–R3) | 404 | Persian 404 | `authz.deny`, outcome `denied`, at most one row per user, route and minute. Written through `ts.audit.event.log_denied()`, which uses its own database cursor and commits it, because the request's transaction is rolled back when the 404 is raised |
| Member, lacks the permission for the page | 403 | Shell + «به این بخش دسترسی ندارید» + who can grant it | `authz.deny` |
| Gated panel action (A4) | 200 | The page with the pending notice | — |
| Re-authentication needed | 303 | `/my/reauth` | `auth.reauth` on success or failure |

Controller helpers (`ts_panel/controllers/base.py`), used by every route:
`_member(ws_id)` → member or 404 · `_require(member, perm)` → 403 page + deny event ·
`_client(member, client_id)` → client or 404 · `_fresh_auth()` → redirect if stale.
No controller reads a panel record without going through these helpers; `ts check` gains a
rule that flags `.sudo().browse(` / `.sudo().search(` in `ts_panel/controllers/` outside
`base.py` helpers unless the domain contains `workspace_id` (S0).

## 10. Tests derived from this file (Phase 2 writes them; deny cases first)

ORM, file `tools/prod/tests_pv2_perms.py` (matrix-driven: the table in section 2 is
transcribed once as a dict in the test and compared with `ROLE_PERMS`, so a silent change of
either side fails):

| Id | Test |
|---|---|
| P01 | For every role × permission: `has_perm` equals the table, per purpose |
| P02 | Unknown permission string raises |
| P03 | Inactive member: empty permission set |
| P04 | Suspended and closed panel: only `panel:view` (+ owner export on closed) |
| P05 | Gated panel: `invites:*` and `clients:import` refused, the rest unchanged |
| P06 | Unverified `clinician` and unverified `clinic_director`: only `panel:view` and `help:view`; verified: the table. Unverified practising owner: everything except `results:clinical` |
| P07 | Solo psychologist (`owner_practices`) verified sees `clinical` on own client; unverified sees `status` (G1) |
| P08 | Owner of a clinical panel without `owner_practices` never gets `clinical` |
| P09 | `admin` gets `status` on every result in all three purposes |
| P10 | R0: member of panel A gets `none` for a client of panel B (same person in both panels) |
| P11 | R2/R3: counselor sees own and unassigned (education); clinician and hiring manager do not see unassigned |
| P12 | Result level steps 2–11, one test per step, including revoked share and unreleased import in a non-education panel |
| P13 | A second active membership for the same person in one panel is refused; the same person in two panels is fine |
| P14 | Last owner cannot be deactivated or demoted (existing guard still holds) |
| P15 | Responsible target without `clients:be_responsible` is refused; a client's own account is refused |
| P16 | Member leaves → clients go to unassigned, audited (existing behaviour still holds) |
| P17 | Audit `detail` cleaner drops deny-listed keys and masks phone/email-shaped values; raw IP is not stored |
| P18 | Group report hides cells below the threshold and applies complementary suppression |
| P19 | Wallet: second submit of the same attempt creates no second debit; ledger rows refuse write and unlink |
| P20 | No code path creates an SMS, an email or a notification for an imported person: for a client with `source='import'` the invitation, campaign, reminder and contact-edit paths are refused while `ts_panel.import_contact_unlocked` is false |
| P21 | A job's file is downloadable only by its requester, and only while they still hold the permission of that export kind |
| P22 | A finished TALENT-INV-15 attempt in a panel produces exactly one usage event and one ledger row (G28) |
| P23 | A member accepting a colleague invitation while already an active member of that panel is refused with a message (no database error) |
| P24 | A deny event survives the 404 (separate cursor) and is throttled |

HTTP, file `tools/prod/ts_http_pv2_perms.py`: for each staff page in `03_ia_and_ux.md` section
3, signed in as a role that lacks the permission → 403 page with the Persian text; as a member
of another panel → 404; as the right role → 200 with the key text and no traceback; object ids
of another panel in the URL → 404; POST without CSRF → 400; export without fresh
re-authentication → redirect to `/my/reauth`.
