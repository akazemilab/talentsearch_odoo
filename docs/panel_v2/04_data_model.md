# Panel v2 — 04 Data model

Odoo 20, database `eot_main`, website 4 only. Read `05_permissions_matrix.md` with this file:
models hold data, the permission functions decide who reads it.

## 0. Rules for every model in this file

1. **Where code lives.** New models, pages and back-office views go in the new module
   `ts_panel` (depends on `ts_talent`). `ts_core` changes only in S1 (roles, audit fields,
   two small hooks); `ts_org` in S1 (permission core), S17 (one access row, one menu) and S20
   (removal of old pages); `ts_sms` in S20. Everything else extends existing models from
   `ts_panel` with `_inherit`.
2. **No ACL for portal users on new models.** Customer staff and participants are portal
   users. Controllers check `member.has_perm(...)` and the object rule, then read with
   `sudo()`. This is the existing pattern (`CLAUDE.md`, "Nobody in a workspace has ACL on
   attempts"). `security/ir.access.csv` rows exist only for back-office groups.
3. **Every model that belongs to a panel has `workspace_id`** (required, indexed,
   `ondelete='restrict'`), and every query in a controller filters on the member's
   `workspace_id`. A record id from the URL is always re-read with
   `[('id','=',x),('workspace_id','=',member.workspace_id.id)]`.
4. **Append-only models** (`ts.audit.event`, `ts.consent.record`, `ts.wallet.txn`) raise on
   `write` and `unlink` and are created only through one class method, like `ts.audit.event`
   today.
5. **Constraints** use `models.Constraint`, partial uniqueness uses `models.UniqueIndex`
   (both verified in this Odoo: `odoo/orm/table_objects.py`).
6. **Names of people, phones and emails are never written to `detail` of an audit event**,
   to a job's `params`, or to a log line.
7. Text normalisation helper `norm_text()` (new, `ts_panel/models/text.py`): ي→ی, ك→ک,
   Arabic-Indic and Persian digits → Latin, ZWNJ and repeated spaces collapsed, lower-case.
   Used for `*_norm` search columns and for CSV matching. Phones use the existing
   `norm_phone()` (`ts_org/models/panel.py`), emails `norm_email()`.
8. Platform settings are `ir.config_parameter` keys with the prefix `ts_panel.` (section 9).

## 1. Domain chain

```
ts.workspace (panel)
 ├─ ts.workspace.member (staff, one active row per person, role → permissions)
 ├─ ts.panel.group (class / team / tag)
 ├─ ts.panel.client (the person as this panel knows them)      ← NEW backbone
 │    ├─ responsible_id → member
 │    ├─ user_id → the participant's own account, once they sign in (never merged by name)
 │    └─ ts.assignment (invitation + share grant, one per instrument sitting)
 │         └─ ts.attempt (response) → ts.attempt.result (scores) → released → share_level
 ├─ ts.campaign (a batch of assignments, or an open link)
 ├─ ts.wallet → ts.wallet.txn (ledger)      ts.usage.event (metering fact, exists)
 ├─ ts.job (export / import / group report)
 └─ ts.audit.event, ts.consent.record
ts.notification, ts.notify.pref (per user)        ts.data.request (per user, platform queue)
```

The participant's account (`res.users`) and the panel's client row stay separate objects. A
panel can never read anything of the account except what an assignment shares.

## 2. Changes to existing models

### 2.1 `ts.workspace.member` (S1, in `ts_core` + `ts_org`)
| Field / rule | Type | Notes |
|---|---|---|
| `role` | Selection | Add `('admin', 'هماهنگ‌کنندهٔ پنل')`. Allowed in every purpose. Labels unified: `owner` = «مالک پنل» |
| `owner_practices` | Boolean | Only meaningful when `role == 'owner'`: the owner also works as a specialist (solo counselor, solo psychologist). Set by `ts_panel_create` for `kind == 'solo'`; editable by the owner in Members |
| `license_number`, `verification_state` | existing | `_compute_verification_state`: `pending` when role is `clinician`, `clinic_director`, `counselor`, **or** owner with `owner_practices` in a clinical panel |
| `deactivated_on`, `deactivated_by_id` | Datetime, m2o res.users | Set when `active` becomes False |
| Uniqueness | `models.UniqueIndex('(workspace_id, user_id) WHERE active IS TRUE')` | Replaces `unique(workspace_id, user_id, role)`. Migration: if a person has two active rows in one panel keep the row with the higher rank (owner > clinic_director = hr_admin > admin > others) and deactivate the other; live data has no such case (2 rows) |
| `has_perm(perm)`, `perms()` | methods | See `05_permissions_matrix.md` |

`ROLES_BY_PURPOSE` after S1:
`education: owner, admin, counselor` · `clinical: owner, admin, clinic_director, clinician` ·
`employment: owner, admin, hr_admin, hiring_manager, reviewer` · `benefits: owner, benefit_admin`
(benefits stays unoffered).

### 2.2 `ts.workspace` (fields added from `ts_panel`)
| Field | Type | Notes |
|---|---|---|
| `client_term` | Selection `student / client / candidate / employee / participant` | Word used for clients in this panel's pages. Default by purpose: education → `student`, clinical → `client`, employment → `candidate`. Labels: دانش‌آموز، مراجع، داوطلب، کارمند، شرکت‌کننده |
| `contact_phone`, `contact_email` | Char | Shown to participants on invitation pages so they can reach the panel. Optional |
| `brand_color` | Char (hex) | Optional accent for the co-brand line on participant pages and print. Applied only if contrast with white ≥ 4.5:1, else ignored |
| `closed_on`, `closed_by_id`, `close_reason` | Datetime, m2o, Char | Panel closure (S18) |
| `wallet_id` | m2o `ts.wallet` (computed, one per panel) | S11 |
| Tenant-health fields | computed, not stored: `client_count`, `open_invite_count`, `done_30d`, `last_activity_on`, `pending_age_days` | Back-office list only (S17); computed with `sudo()` so operators see counts, never names |

Logo stays on `partner_id.image_1920` (existing).

### 2.3 `ts.audit.event` (S1)
| Field | Type | Notes |
|---|---|---|
| `outcome` | Selection `ok / denied / error`, default `ok` | |
| `route` | Char | `request.httprequest.path` with ids replaced by `<id>` and tokens by `<token>` (never the raw token) |
| `request_id` | Char | Random id per request (`request.session.sid` is **not** used) |
| `ip_hash` | Char | `sha256(salt + ip)[:16]`, salt = `ir.config_parameter` `ts_core.audit_ip_salt` (random, created once by the S1 migration). Own helper in `ts_core/models/audit.py`; the helper in `ts_sms` is unsalted and is not reused |
| `member_id` | m2o `ts.workspace.member` | The acting membership, when there is one |
| `ip_address` | existing | **No longer written.** Migration: for existing rows compute `ip_hash`, then set `ip_address = NULL` by SQL in the S1 migration (the model forbids `write`) |
| `detail` | existing Text (JSON) | Passed through `_clean_detail()`: drop keys in `DENY_KEYS = {'name','phone','mobile','email','answer','answers','token','code','password','reason','note','text','body'}`; any string value matching a phone or email pattern becomes `'***'`; values longer than 120 chars are cut |
| Index | `models.Index('(res_model, res_id)')`, `models.Index('(workspace_id, event_type, create_date)')` | For "who saw this result" and the owner's audit page |

Existing calls that pass free text and must change in S1: `workspace.reject` and
`workspace.suspend` (`note=` in `ts_core/models/workspace.py`) and `emergency.open` (`reason=`
in `ts_core/models/emergency.py`). They log `has_note=True` / `reason_len=<n>` instead; the
text stays on the record itself.

`log_denied(event_type, route, **detail)` writes a deny event through its own cursor
(`self.env.registry.cursor()`), commits it and closes it, so it survives the rollback that
follows a 404 or 403. It refuses to write more than one row per user, route and minute.

`ts check` gains a static rule: a call to `.log(` with a keyword in `DENY_KEYS` is reported as
a warning in S0 and fails the preflight from S1, when the three calls above are fixed.

### 2.4 `ts.assignment` (extended from `ts_panel`)
| Field | Type | Notes |
|---|---|---|
| `client_id` | m2o `ts.panel.client`, index, `ondelete='restrict'` | Required for every new row; filled by the backfill for old rows (S4), then `required=True` |
| `campaign_id` | m2o `ts.campaign`, optional | S7 |
| `channel` | Selection `link / sms / email / open_link / self_share / import` | How the person was reached. Default `link` |
| `expires_at` | Datetime | Stored. Default: end of `deadline` day if set, else `create_date + ts_panel.invite_ttl_days` (30). Backfill computes it the same way |
| `opened_at` | Datetime | First GET of `/invite/<token>` (S6) |
| `expired` | Boolean | Set by the hourly cron when `expires_at < now` and the invitation was **not accepted yet**. An accepted invitation never expires: its deadline only raises the "overdue" marker, and the participant can still finish until a member withdraws it or the attempt is abandoned |
| `remind_ok` | Boolean | The member's attestation, given in the v2 invite wizard, that the person agreed to one reminder by SMS as well as the invitation. False on every invitation created before S6, so those never get an SMS reminder |
| `state` | existing stored compute | New order of checks: withdrawn → declined → done → in_progress → accepted → **expired** → **opened** → invited. Labels in `03_ia_and_ux.md` |
| `reminder_count`, `last_reminder_at` | Integer, Datetime | S10 |
| `responsible_id` | existing | Becomes `related='client_id.responsible_id', store=True, readonly=True`. The client is the single place where responsibility is set. S4 does not edit `ts_org`, so each existing writer is neutralised from `ts_panel`: (1) `ts_org`'s `create` asks `ts.workspace.member.ts_default_responsible()` for a default → `ts_panel` overrides that method to return an empty recordset, and applies the rule of `05_permissions_matrix.md` section 2 when it creates the **client**; (2) `action_accept` clears a self-responsibility → `ts_panel` overrides `action_accept` to clear it on the client first; (3) `_ts_release_clients` → overridden to write clients; (4) the controller `_set_responsible` → overridden to write the client; (5) `write` on assignment/attempt → `ts_panel` drops `responsible_id` from the values. The `_check_responsible` constraints stay and are repeated on the client. Audit: `client.responsible_change` replaces `assignment.responsible_change` / `attempt.responsible_change` for new events |
| `invitee_name`, `invitee_email`, `invitee_phone` | existing | Kept as the snapshot used when the invitation was sent; new invitations copy them from the client |
| `share_level`, `accepted_at`, `user_id`, `attempt_id` | existing | Unchanged. The assignment **is** the share grant: level + who + revocable |
| `share_changed_at` | Datetime | Set on accept, self-share and revoke |
| Uniqueness | `models.UniqueIndex('(attempt_id, workspace_id) WHERE attempt_id IS NOT NULL')` | One share row per result per panel. The "one panel at a time" limit becomes the setting `ts_panel.share_max_panels`, set to 3 by owner decision D3 |

### 2.5 `ts.attempt` (extended from `ts_panel`)
| Field | Type | Notes |
|---|---|---|
| `client_id` | m2o `ts.panel.client`, index | Set for every attempt that has a `workspace_id` (from the assignment, or by the backfill for imports) |
| `responsible_id` | existing (imports) | Becomes `related='client_id.responsible_id', store=True` |
| `state` | Selection | Add `stopped` (a started attempt whose invitation a member withdrew or the participant declined, or that stayed idle longer than `ts_panel.abandon_days`; its answers are deleted by the retention job, not at once) and `erased` (content removed on a data request; the row stays for usage counts). `/take/<token>` for a stopped attempt shows «این سنجه متوقف شده است» with the panel's contact; for an erased one, 404 |
| `voided`, `voided_on`, `voided_by_id`, `void_reason_code` | Boolean, Datetime, m2o, Selection `wrong_person / duplicate / technical / other` | Platform manager only. A voided attempt is hidden from every report; its usage is refunded in the ledger. FHIR `entered-in-error` |
| `last_activity_at` | Datetime | Updated by `save_answer`/`ts_save_cell`; drives "abandoned" and the resume prompt. Backfill (M8): the newest `answered_at` of its answers or cells, else `started_at`, else `create_date` |

FHIR mapping kept in mind: definition = `ts.instrument.version` (already pinned by
`version_id`); `subject` = `client_id` (or the account for self-taken); `source` =
`respondent_role` (`self` / `guardian`); `author` = the account that recorded. There are no
amendments: a submitted attempt is immutable, a retake is a new attempt.

### 2.6 `res.users` / `res.partner` (from `ts_panel`)
| Field | Model | Notes |
|---|---|---|
| — (no new field first) | `res.device`, `res.session` (stock models in this Odoo, `odoo/addons/base/models/res_device.py`) | Sessions list and "sign out everywhere" (S18) read and revoke the user's **own** rows of these stock models after our re-authentication. Phase 2 reads that file first. Only if the stock revoke cannot be used for accounts without a password: fallback field `ts_session_epoch` (Integer on `res.users`) compared by a website-4 request hook. `_get_session_token_fields()` is never changed (it would log out every eot.ir user once) |
| `ts_is_adult` | `res.partner`, Selection `yes / no / unknown`, default `unknown` | Self-declared on the first consent page (S16). Not a birth date |

## 3. New models (all in `ts_panel`)

### 3.1 `ts.panel.client` — the person as one panel knows them (S4)
| Field | Type | Notes |
|---|---|---|
| `workspace_id` | m2o, required, index | |
| `name` | Char, required, max 120 | As the panel typed it |
| `name_norm` | Char, index | `norm_text(name)`, for search and CSV duplicate checks |
| `code` | Char, max 40 | The panel's own identifier (student number, file number). Optional. `UniqueIndex('(workspace_id, code) WHERE code IS NOT NULL')`. When a code exists, list and print views can show the code instead of the name (pseudonymous mode, as MHS TAP does) |
| `phone` | Char | `norm_phone`; optional |
| `email` | Char | `norm_email`; optional |
| `group_ids` | m2m `ts.panel.group` | |
| `responsible_id` | m2o `ts.workspace.member` | Same constraint as today (`_check_responsible`): active member of this panel with `clients:be_responsible`, never the client's own account. Change is audited `client.responsible_change` (old/new member ids) |
| `handover_to_id`, `handover_by_id`, `handover_on` | m2o member, m2o member, Datetime | An open request by the responsible specialist to hand the client to a colleague (S5). Cleared when a member with `clients:assign` confirms (then `responsible_id` changes) or declines. Audited `client.handover_request` / `client.handover_decide` |
| `age_group` | Selection `adult / minor / unknown`, default `unknown` | Education panels preselect `minor` in forms; the panel can change it |
| `guardian_name`, `guardian_phone`, `guardian_relation` | Char, Char, Selection `father / mother / guardian / other` | Only when `age_group == 'minor'`. Optional in attest mode, required in guardian-link mode (S16) |
| `guardian_consent` | Selection `none / attested / confirmed`, computed + stored from `ts.consent.record` | S16 |
| `user_id` | m2o `res.users`, index | The account that accepted an invitation or shared by code. `UniqueIndex('(workspace_id, user_id) WHERE user_id IS NOT NULL')` |
| `account_is_guardian` | Boolean | True when the linked account answers *about* the client (parent-report instruments) |
| `partner_id` | m2o `res.partner` | Only for imported historical people (`ts.attempt.person_id`); never shown to the panel as a contact card |
| `source` | Selection `manual / csv / invite / open_link / self_share / import` | |
| `contact_locked` | Boolean, computed: `source == 'import'` and the setting `ts_panel.import_contact_unlocked` is false | **Protection of the historical people.** While locked: no invitation, campaign, reminder or notification can be created for this client; phone, email and guardian fields cannot be edited; the client cannot be merged. Enforced in the model (`create`/`write` constraints on assignment, campaign and client), not only in pages. Only the owner's explicit decision changes the setting |
| `merged_into_id` | m2o `ts.panel.client` | Set on the archived row after a merge or an automatic account link |
| `state` | Selection `active / archived`, default `active`; `archived_on` | Archived clients leave default lists and cannot be invited; nothing is deleted |
| `anonymised_on` | Datetime | Set by the erase workflow: `name` → «حذف‌شده»، contact and guardian fields emptied, `user_id` and `partner_id` cleared |
| `last_activity_at` | Datetime, index | Updated on invite, accept, submit, share change; default sort |
| `assignment_ids`, `attempt_ids` | o2m | |
| `open_count`, `done_count` | Integer, stored compute | For list columns and KPIs |

Linking rules (the account is the only automatic key; never name or birth date):
1. Invitation accepted → `client.user_id = user` if empty. If it is already another user →
   refuse (existing "used" message). If **another** client of the same panel already has this
   `user_id` (for example the person shared a result by code earlier): the assignment is moved
   to that client, and the invitation's own client row, if it has nothing else, is archived
   with `merged_into_id`; audited `client.auto_link`.
2. Self-share by panel code → find `[(workspace, user_id)]`; if none, create a client with
   `source='self_share'`, `name = user.name`.
3. Open link → the account's existing client in this panel if there is one; else create a
   client with `source='open_link'`, `name` typed by the participant.
4. A member invites someone. In the wizard (from S6) the member picks an existing client or
   creates one, and the wizard creates the assignment itself with `client_id`,
   `invitee_phone`, `sms_consent` and `remind_ok` (the SMS is sent by `ts_sms`'s model
   `create`, as today). When a new client is typed, an existing active client of the panel
   with exactly that normalised phone, else exactly that email, is offered instead. On the old
   form (S4 and S5 only), where `ts_org` creates the assignment and `ts_sms` writes the phone
   afterwards: `ts_panel`'s `create` override attaches a client matched by exact email, else a
   new client; when `invitee_phone` is written later and the client has no phone, it is
   copied. No match on name, ever.
5. Two rows for the same person can be **merged by a member with `clients:merge`** (S5):
   assignments and attempts move to the kept row, the other is archived with
   `merged_into_id`, event `client.merge` is audited. Refused when the rows have different
   `user_id`, or when either row is `contact_locked`.
6. Responsible for a new client: the rule in `05_permissions_matrix.md` section 2 notes.

Access rows: `group_ts_manager` `r` only; no access for `group_ts_user` (operators see counts
through the workspace's computed fields).

### 3.2 `ts.panel.group` (S5)
`workspace_id` · `name` (required, max 60) · `name_norm` · `kind` Selection `class / team / tag`
(labels: کلاس، گروه، برچسب) · `active` · `client_ids` m2m · `client_count` stored compute ·
`UniqueIndex('(workspace_id, name_norm) WHERE active IS TRUE')`.

### 3.3 `ts.campaign` (S7)
| Field | Type | Notes |
|---|---|---|
| `workspace_id`, `name`, `instrument_id` | | Instrument must be in `member.allowed_instruments()` |
| `kind` | Selection `list / open_link` | `list`: assignments created for chosen clients or groups. `open_link`: anyone holding the link joins |
| `state` | Selection `draft / open / closed` | Closing withdraws nothing; it stops new joins and reminders |
| `deadline` | Date | Copied to assignments |
| `note` | Char 300 | Shown on the invitation page |
| `created_by_id` | m2o member | |
| `group_ids` | m2m | Targets (for display and the group report) |
| `open_token` | Char, unique, `uuid4().hex` | Only for `open_link` |
| `open_max` | Integer, default `ts_panel.open_link_max` (60) | Hard cap of joins |
| `open_expires_at` | Datetime, default +14 days | |
| `send_sms`, `sms_consent_attested` | Boolean | SMS only to clients with a valid mobile and only if the member ticks the attestation, whose text covers the invitation and one reminder. The tick sets `sms_consent` and `remind_ok` on each assignment of the campaign |
| `remind` | Boolean, default True | One automatic reminder (S10) |
| Counts | computed | invited, opened, accepted, in progress, done, expired, declined, withdrawn |
| `guardian_attested_by_id`, `guardian_attested_on` | m2o member, Datetime | Attest mode for minors (S16) |

### 3.4 `ts.consent.record` — append-only consent ledger (S16; written from S15 for sharing)
| Field | Type | Notes |
|---|---|---|
| `kind` | Selection `service / research / share / share_revoke / guardian / guardian_attest / assent / sms / terms / privacy` | |
| `version` | Char | Text version, e.g. `TS-CONSENT-1405-07-07-v1`, `panel-terms-1405-07-v2` |
| `user_id` | m2o res.users | Who gave it (account), if any |
| `given_as` | Selection `self / guardian / panel_member` | |
| `method` | Selection `checkbox / otp_verified / attestation` | |
| `client_id`, `assignment_id`, `attempt_id`, `workspace_id`, `campaign_id` | m2o, optional | What it applies to |
| `level` | Char | For `share`: the share level granted |
| `at` | Datetime | |
| `ip_hash` | Char | |

The existing fields on `ts.attempt` (`consent_service`, `consent_research`, `consent_version`,
`consent_at`) and on `ts.workspace` (`terms_*`) stay; a ledger row is written next to them.
Never stored here: free text, names, phone numbers.

### 3.5 `ts.wallet` and `ts.wallet.txn` (S11)
`ts.wallet`: `workspace_id` (unique) · `balance` (Integer, stored, = sum of `amount`) ·
`units_used` (Integer, stored, = sum of `units` of `debit_usage` minus refunded) ·
`low_threshold` (Integer, default 0 = no alert) · `low_alert_sent_on`.

`ts.wallet.txn` (append-only):
| Field | Type | Notes |
|---|---|---|
| `wallet_id`, `workspace_id` (related, stored) | | |
| `type` | Selection `grant / purchase / debit_usage / refund / expire / adjust` | `purchase` and `expire` are reserved for the paid phase; no code path creates them now |
| `amount` | Integer (credits, signed) | In free mode a `debit_usage` has `amount = 0` |
| `units` | Integer | Assessments completed (1 per attempt) |
| `free` | Boolean | True for rows written while `ts_panel.credit_mode == 'free'` |
| `idem_key` | Char, **unique** | `usage:<attempt_id>`, `refund:<attempt_id>`, `grant:<uuid>`, `adjust:<uuid>` |
| `attempt_id`, `usage_event_id`, `assignment_id` | m2o, optional | |
| `actor_id` | m2o res.users | Who caused it (system user for automatic rows) |
| `reason_code` | Selection `completion / void / manual / promo / correction` | No free text |
| `balance_after` | Integer | For display and for the reconcile check |

Rules
- **Debit at scoring**: `ts_panel` overrides `ts.attempt.action_submit` at the top of the
  inheritance chain. After `super()` returns true, for an attempt that is `done`, has a
  `workspace_id` and is not an import, it makes sure one `ts.usage.event` exists and calls
  `wallet._debit_usage(attempt)`, idempotent on `idem_key`. The existing hook in `ts_org` is
  **not** enough: `ts_talent` scores TALENT-INV-15 without calling `super()`, so no usage event
  is written today for the only instrument education panels use (gap G28; the event part is
  fixed already in S0). Self-taken attempts have no panel, so no debit. A result shared later
  by code (self-share) is **not** charged.
- **No reservations.** `committed` is a computed number on the wallet page: open invitations
  (`invited, opened, accepted, in_progress`). In the paid phase the rule proposed is: creating
  invitations is refused when `balance − committed ≤ 0`; a participant who already started is
  never blocked.
- **Free mode** (`ts_panel.credit_mode = 'free'`): nothing blocks, `amount = 0`, the page says
  «رایگان در این فصل» and shows usage honestly. No fake grants.
- **Reconcile** (daily cron): `wallet.balance == sum(txn.amount)`; every attempt that is
  `done`, in a panel and not an import has exactly one `ts.usage.event` and one `debit_usage`
  (checked from the attempts, not from the events); a mismatch creates an audit event
  `wallet.reconcile_mismatch` (outcome `error`) and a back-office activity.
- Row lock: `SELECT ... FOR UPDATE` on the wallet row while writing a transaction (same
  pattern as `action_submit`).
- Paid-phase extension, **not built now**: grant lots with `expires_at` and allocation rows
  (debit → lot, oldest expiry first), `purchase` from a gateway, invoices. Needs eNamad, tax
  code and e-invoice setup first (`01_research.md` 2.6).

### 3.6 `ts.notification` and `ts.notify.pref` (S10)
`ts.notification`: `user_id` (index) · `workspace_id` (optional) · `type` (Selection, list in
`02_feature_catalog.md` N-events) · `title` Char · `url` Char (internal path) · `read_at` ·
`create_date`. No body text with personal data: titles are built from templates such as
«نتیجهٔ یک مراجع آماده است»; the name is seen only after opening the page, which re-checks
permission.

`ts.notify.pref`: `user_id` · `type` · `in_app` (default True) · `sms` (default False) ·
`email` (default False) · unique `(user_id, type)`.

Dispatcher `ts.notification._notify(user, type, url, workspace=None)`:
in-app row if enabled → SMS through the existing `ts_sms` senders only if the user has a
verified mobile, opted in for that type, the hour is outside quiet hours
(`ts_panel.quiet_start`–`quiet_end`, Asia/Tehran; OTP exempt) and the per-user limit is not
exceeded (`ts_panel.sms_per_day`, default 5). Each send is audited (`notify.send`, channel,
type; no recipient data).

**Email is not a channel in this plan.** No outgoing email is set up for Talent Search (owner
decision of 2026-09-29, `docs/IMPLEMENTATION_LOG.md`), and the mail server of the instance is
shared with eot.ir. The `email` column of `ts.notify.pref` exists but stays unused and hidden
until the owner decides on a sender (decision D8).

New SMS kinds ship **switched off**: company switches `ts_sms_reminder` and `ts_sms_staff`
(default False), next to the existing `ts_sms_invite`, `ts_sms_result`, `ts_sms_otp`. The
owner turns them on in Settings after reading what each one sends.

### 3.7 `ts.job` (S8)
| Field | Type | Notes |
|---|---|---|
| `workspace_id` (optional: empty for a participant's own `data_export`), `member_id`, `user_id` | | Requester. **Only the requester can open the job page or download its file**, and at download time the permission of that export kind is checked again |
| `kind` | Selection `export_clients / export_status / export_results / export_audit / import_clients / group_report / data_export` | |
| `state` | Selection `queued / running / done / failed / expired` | |
| `params` | Text (JSON) | Filter ids and column mapping only; no row data and no search text |
| `progress`, `total` | Integer | |
| `result_attachment_id` | m2o `ir.attachment` (`res_model='ts.job'`, `public=False`) | Export file or the error report |
| `source_attachment_id` | m2o `ir.attachment` | Uploaded import file; deleted when the job ends |
| `summary` | Text (JSON) | Counts: created, updated, skipped, failed |
| `error_code` | Char | Code only, shown as a Persian message |
| `expires_at` | Datetime | `done + ts_panel.export_ttl_hours` (24). After that the download is refused and a cron deletes the attachment |

Runner: a job with at most `ts_panel.job_inline_rows` (500) rows runs in the request; larger
ones are picked up by a cron every minute (`FOR UPDATE SKIP LOCKED`, one job per run, commits
per 200 rows). The status page refreshes itself with `<meta http-equiv="refresh">` and sends a
notification when done.

### 3.7b `ts.reauth.code` (S3)
Re-authentication codes are **not** `ts.phone.otp` rows: that model's `verify_code` accepts the
newest unused code whatever number it was sent to and re-enables an SMS preference, which is
right for verifying a phone and wrong for proving identity.
`user_id` · `salt` · `code_hash` · `expires_at` (5 minutes) · `attempts` (max 5) · `used`.
Rules: the code is sent **only** to `partner.ts_phone` (the already verified mobile) through
the existing sender `ts.phone.otp._send_code(company, phone, code)`; 60 s cooldown, 5 per hour
per user; Persian and Arabic digits are translated before comparing; success stores
`ts_reauth_at` in the session and writes audit `auth.reauth`. Accounts without a verified
mobile re-authenticate with their password. Rows older than 2 days are deleted by autovacuum.

### 3.8 `ts.saved.view` (S5)
`member_id` · `page` Selection `clients / invites / audit` · `name` Char 40 · `query` Char
(the validated filter and sort parameters; **never the search text**) · `is_default` Boolean ·
`columns` Char (comma list of visible optional columns). Unique `(member_id, page, name)`.
Max 10 per member per page.

Search text typed by staff can be a person's name. It is sent by POST, kept in the session per
list page, shown in the search box, and never placed in a URL, a saved view or a job.

### 3.9 `ts.data.request` (S15, queue in S17)
`user_id` · `kind` Selection `export / erase / correct` · `state` Selection
`new / in_review / done / rejected` · `due_on` (create + 30 days) · `handled_by_id` ·
`decision_code` Selection (`done`, `legal_hold`, `not_owner`, `duplicate`) · `job_id` (for
export). Exports of the participant's own data are produced automatically as a job; erase
requests wait for a platform manager (the owner) and follow section 6.

### 3.10 Support access = `ts.emergency.access` generalised (S14)
The model keeps its name. `ts_panel` extends it with `_inherit = 'ts.emergency.access'`: add
`kind` Selection `emergency / support` (existing rows = `emergency`), `ticket_ref` Char
(required for `support`), `hours` (emergency 24, support 8, max 24). `ts_core/models/emergency.py`
hard-codes "clinical only" and 24 hours inside `create`, where a wrapping override cannot
skip them. In S1 (when `ts_core` is edited anyway) the two checks move into small methods,
`_check_scope(vals)` and `_hours(vals)`, with unchanged behaviour; in S14 `ts_panel` overrides
those two methods so the limits apply to `emergency` only. Owners see every access (open and past) on the panel's
audit page and get a notification when one opens. Opening an access in the back-office is
protected by Odoo's own identity check (`check_identity` from `base/models/res_users.py`) on
the button method.

## 4. Record rules and access rows

| Model | `group_ts_user` (operator) | `group_ts_curator` | `group_ts_manager` | `base.group_portal` |
|---|---|---|---|---|
| `ts.panel.client`, `ts.panel.group` | — | — | r | — |
| `ts.campaign` | — | — | r | — |
| `ts.assignment` (existing) | r → **removed in S17** (G12) | — | cru | — |
| `ts.consent.record` | — | — | r | — |
| `ts.wallet`, `ts.wallet.txn` | r | r | r (create only through `wallet` methods) | — |
| `ts.job` | — | — | r | — |
| `ts.notification`, `ts.notify.pref` | — | — | — | — (controllers filter on `user_id = request.env.user.id` and use sudo, like every other model here) |
| `ts.saved.view` | — | — | — | — (sudo after member check) |
| `ts.data.request` | r | — | cru | — |
| `ts.emergency.access` (with `kind`) | — | — | crud (existing) | — |

Decision D4 (technical lock on clinical data for platform managers) would change the rows of
`ts.attempt`, `ts.attempt.answer`, `ts.attempt.result`, `ts.attempt.field`, `ts.attempt.cell`
for `group_ts_manager` from unrestricted `r` to `r` with the domain "self-taken, or the panel
has an open support/emergency access for this user". `ir.access` domains can use `time`
(verified), so the rule is feasible; it is a separate, optional stage (S14b) because it
changes back-office behaviour.

## 5. Migration of live data (stage S4 unless noted)

All steps are idempotent functions called from `data/migrate.xml` (`<function>` records, run on
every upgrade, each one a no-op the second time). Each prints counts only.

| Step | What | Live size | Notes |
|---|---|---|---|
| M1 (S1) | Audit rows: fill `ip_hash`, null `ip_address` | 75 | SQL |
| M2 (S1) | Members: enforce one active row per person per panel; set `owner_practices` on owners of solo panels (panels whose `workspace.self_create` audit detail has `kind = solo`) | 2 | No live conflict. The de-duplication must run **before** the unique index is built, so it is a `ts_core` pre-migration script (`ts_core/migrations/20.0.1.1.0/pre-migrate.py`, with the module version raised to `20.0.1.1.0`), not a `<function>` record. Test clones may hold duplicates created by older suites |
| M3 (S4) | For every `ts.assignment` without `client_id`, oldest first: find a client in the same panel by `user_id`, else by exact `phone`, else by exact `email`; else create one (`source='invite'`). Set `client_id`, `expires_at`, `channel` (`self_share` when `invited_by_id == user_id`, else `sms` if `sms_sent_at`, else `link`). The client's responsible = the `responsible_id` of its newest assignment that has one | 3 (none has a responsible member) | |
| M4 (S4) | For every imported attempt (`source='import'`, has `workspace_id`): one client per `(workspace_id, person_id)` with `source='import'`, `partner_id = person_id`, `name` from the partner, **phone and email not copied**, `age_group='unknown'`. Set `attempt.client_id`. Carry over an existing `responsible_id` | 114 attempts → 108 clients in workspace 1 | Nothing is released, no message is sent, no account is linked; the rows are `contact_locked`. **Approved by the owner on 2026-10-01 (decision D5)** |
| M5 (S4) | Web attempts with a `workspace_id` and an assignment: `attempt.client_id = assignment.client_id` | 1 | |
| M6 (S11) | One wallet per panel; one `debit_usage` (free) per existing `ts.usage.event` | 0 events | |
| M7 (S16) | `ts.consent.record` rows from existing attempt consent fields and panel terms acceptance | 5 + 1 | `method='checkbox'` |
| M8 (S18) | `ts.attempt.last_activity_at` backfill (2.5) | 121 | |

Owner approval: M4 was approved as decision D5 (2026-10-01). M1–M3 and M5–M8 only add
bookkeeping columns and rows about records that already exist; they change nothing a person
can see and send nothing. Approving Phase 1 approves them; they are listed in `HANDOFF.md` so
the approval is explicit.

Rehearsal check for M4: client count per panel equals `count(distinct person_id)`; no
`sms.sms` row and no `ts.notification` row is created by the migration; `released` stays False
on all 114.

Rollback for every stage: `ts ship` restores the previous code directory on failure; data
steps only add rows or fill empty columns, so the previous code keeps working on the migrated
database. The S1 unique-index change is the only one that could refuse old code paths (a
second membership row for the same person); the old code never creates one from the UI.

## 6. Data lifecycle (retention and erasure) — proposal for the owner, built in S18

The retention job ships **switched off** (`ts_panel.retention_enabled = False`). While off it
only writes a daily dry-run count per rule to the back-office (what it would remove). The
owner turns it on after reading the first report (decision D7). Nothing below deletes live
data before that.

| Data | Kept for | Then |
|---|---|---|
| OTP rows, login tokens | 2 days, 1 day | deleted (exists) |
| Colleague invites not accepted | 90 days | deleted (exists) |
| Participant invitation never accepted | 90 days after `expires_at` | `invitee_*` and the client's contact fields are emptied if the client has no other assignment; the row stays for counts |
| Attempt started, never finished | `ts_panel.abandon_days` (180) idle | state `stopped`, answers deleted |
| Results (self-taken) | until the participant deletes them | erase workflow |
| Results in an education or employment panel | until the participant revokes sharing (panel loses the content at once) or the panel archives the client; erased with the participant's account | |
| Results in a clinical panel | at least 5 years after the last activity (PCO ethics 6-4; for minors until 18), unless the participant asks for erasure and the panel records no legal duty to keep | after 5 years the panel owner gets a yearly reminder to archive or erase |
| Notifications | 180 days | deleted |
| Export files | 24 h link, file deleted after 7 days | |
| Import source files | until the job ends, at most 24 h | deleted |
| Audit events | 5 years | purge job that first records `audit.purge` (the model already anticipates this) |
| Consent records | as long as the data they cover, plus 5 years | |
| Closed panel | 90 days to export | clients anonymised; participants keep their own results in their accounts |
| Imported historical results | until the owner decides | no change |
| Usage events and ledger rows | permanent (no personal data: ids only) | |

Erase workflow (`ts.data.request` kind `erase`, or panel closure):
1. Revoke every share of the user's attempts (`share_level='none'`, consent record
   `share_revoke`).
2. For each attempt: delete answers, results, fields and cells; clear `profile_json`,
   `subject_label`; set `state='erased'`; keep `instrument_id`, dates, `workspace_id`.
3. Client rows linked to the user: anonymise (3.1).
4. Clinical panel with a documented retention duty: step 2 is replaced by "restricted": the
   result is hidden from everyone and a review date is set. This branch needs legal review
   (open item L2 in `HANDOFF.md`).
5. Deactivate the account through Odoo's own `/my/deactivate_account` path.
6. Audit `data.erase` with counts only.

## 7. What is never stored

- Raw answers or item texts outside `ts.attempt.answer` / `ts.attempt.cell`; never in exports,
  jobs, notifications, audit or logs. Organizations never get raw answers (hard rule).
- Scoring keys, band cut-offs or item-to-factor maps in any panel-facing page or export.
- Full phone numbers or emails in audit `detail`, job `params`, notification titles, or URLs.
- Raw IP addresses (hash only) after S1.
- Birth dates, national IDs, addresses. Age is one of `adult / minor / unknown`.
- Free-text health notes. Private specialist notes are not in this plan (default decision).
- Guardian identity documents.
- OTP codes and tokens in clear (already hashed with salt).
- The Kavenegar API key anywhere except the company field typed by the owner.

## 8. Indexes worth naming
`ts_panel_client (workspace_id, state, last_activity_at desc)` ·
`ts_panel_client (workspace_id, name_norm)` · `ts_assignment (workspace_id, state)` ·
`ts_assignment (client_id)` · `ts_assignment (expires_at) WHERE expired IS NOT TRUE` ·
`ts_notification (user_id, read_at)` · `ts_job (state, id)` · the two audit indexes in 2.3.
Lists are read with `search(domain, order, limit, offset)` and `search_count`, never with
`.filtered()` over a whole panel (G11).

## 9. Platform settings (`ir.config_parameter`)

| Key | Default | Used by |
|---|---|---|
| `ts_panel.credit_mode` | `free` | wallet |
| `ts_panel.group_min_n` | `5` | group reports (D6: 10 for schools?) |
| `ts_panel.share_max_panels` | `3` | self-share (owner decision D3) |
| `ts_panel.invite_ttl_days` | `30` | assignments |
| `ts_panel.open_link_max` | `60` | campaigns |
| `ts_panel.reminder_after_days` | `7` | reminder if no deadline |
| `ts_panel.reminder_before_days` | `3` | reminder before a deadline |
| `ts_panel.quiet_start` / `quiet_end` | `21` / `8` | SMS quiet hours, Asia/Tehran |
| `ts_panel.sms_per_day` | `5` | per recipient |
| `ts_panel.staff_idle_hours` | `8` | staff session timeout |
| `ts_panel.reauth_minutes` | `10` | sensitive actions |
| `ts_panel.export_ttl_hours` | `24` | downloads |
| `ts_panel.job_inline_rows` | `500` | jobs |
| `ts_panel.import_max_rows` | `2000` | CSV import |
| `ts_panel.abandon_days` | `180` | attempts |
| `ts_panel.minor_consent_mode` | `attest` | minors (owner decision D2) |
| `ts_panel.import_contact_unlocked` | `False` | protection of the historical people (3.1) |
| `ts_panel.retention_enabled` | `False` | retention job (section 6) |
| `ts_core.audit_ip_salt` | generated | audit |
