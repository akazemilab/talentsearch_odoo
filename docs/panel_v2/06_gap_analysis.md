# Panel v2 — 06 Gap analysis (code at `main` 03ad6d6, 2026-10-01)

What exists, what is missing, and where each change lands. Target definitions are in
`02_feature_catalog.md`, `04_data_model.md` and `05_permissions_matrix.md`.

## 1. Live state (aggregates only, read 2026-10-01)

| Item | Count |
|---|---|
| Panels (`ts.workspace`) | 3, all education: 1 active (workspace 1), 1 pilot, 1 closed |
| Active members | 2 (1 owner, 1 counselor with verification "pending"); 1 person belongs to more than one panel |
| Pending colleague invites | 1 |
| Participant invitations (`ts.assignment`) | 3 (2 invited, 1 in progress), all with phone and email, none with a deadline |
| Attempts | 114 imported (done, not released, no account, no responsible member) + 7 web (3 done) |
| People behind the imports | 108 partners, none linked to a user |
| Usage events | 0 |
| Audit events | 75 |
| Emergency accesses | 0 |
| Users with a verified mobile | 0 |
| Kavenegar | enabled; invitation, result and OTP SMS switches are on |
| Published instruments | 34 (10 employment, 20 personal adult, 1 adolescent, 3 child) |
| Odoo | 20.0, all seven `ts_*` modules installed |

Consequences: the data migration is small and low-risk; SMS is live, so every new notification
path must respect the "no SMS to the 108 historical people" rule by construction (imports have
no account and no consent tick, so no path can reach them; a test asserts it).

## 2. Findings that are bugs or risks today (fix in the stage named)

| # | Finding | Evidence | Stage |
|---|---|---|---|
| G1 | A **solo psychologist cannot open their own clients' clinical results.** A solo clinical panel gives the creator role `owner`; the clinical level requires role `clinician` or `clinic_director`. No test covers it | `ts_org/models/panel.py` `SOLO_AS`, `assignment.py` `visible_results` | S1 |
| G2 | **Several memberships per person in one panel** are allowed (`unique(workspace_id, user_id, role)`); `_membership()` takes the first usable row, so the effective role is arbitrary | `ts_core/models/workspace.py`, `ts_org/controllers/main.py` | S1 |
| G3 | No way to **change a member's role or deactivate a member** from the panel; only invite and revoke exist. The model-level guards (last owner, release of clients) are ready | `ts_org/controllers/panel.py` | S3 |
| G4 | **Role label mismatch**: `ROLE_LABELS` has `school_admin`, which is not a role; `owner` is labelled «مالک سازمان» in one place and «مالک (مدیر اصلی)» in another | `ts_core/models/workspace.py`, `ts_org/models/panel.py` | S1 |
| G5 | The audit trail stores the **raw IP address** and has no outcome, route or request id; `detail` is free-form (`emergency.open` stores the free-text reason, `workspace.reject` stores the note) | `ts_core/models/audit.py`, `emergency.py` | S1 |
| G6 | **Authorization failures are not logged** (controllers raise 404 silently) | `ts_org/controllers/*.py` | S1 |
| G7 | TALENT-INV-15 is `audience='adult'`, but the education channel sends it to school students. **No guardian step, no assent wording, no record of who consented** for minors | `ts_talent/models/loader.py`, `ts_assessment/controllers/main.py` | S16 |
| G8 | Guardian flow for child/adolescent instruments stores `respondent_role` and a free-text `subject_label` on the attempt only: no client link, no versioned consent record | `ts_assessment/models/attempt.py` | S16 |
| G9 | Invitation expiry is computed at read time (`create_date + 30 d` or deadline); the stored `state` never becomes "expired", so lists and counts cannot show it | `ts_org/models/assignment.py` `invite_state()` | S6 |
| G10 | Participant invitation carries its own `invitee_name/email/phone`; the same person invited twice becomes two unrelated rows. No history per person | `ts_org/models/assignment.py`, `ts_sms/models/assignment.py` | S4 |
| G11 | The whole staff panel is **one page** (`ts_org.workspace`, about 200 lines): stats, invite form, table, members, settings. No search, sort or pagination; lists are filtered in Python with `.filtered()`, which will not scale past a few hundred rows | `ts_org/views/web_org.xml`, `controllers/main.py` | S2–S5 |
| G12 | Platform operators (`group_ts_user`) can **read invitation rows** (names, emails, phones) in the back-office although their group description says no participant identity | `ts_org/security/ir.access.csv` | S17 |
| G13 | Platform managers keep technical read access to answers and results; emergency access is a logged procedure only (known open decision) | `ts_assessment/security/ir.access.csv` | S14 (decision D4) |
| G14 | `ts.usage.event` is written only inside `action_submit`; nothing reconciles it, and there is no wallet or page | `ts_org/models/attempt.py`, `usage.py` | S11 |
| G15 | No in-app notifications; result-ready SMS exists only for participants; staff are never told a result is ready | `ts_sms/models/attempt.py` | S10 |
| G16 | No reminders for unfinished invitations | — | S10 |
| G17 | No export, no import in the panel; the only import is the operator tool `ts_import_talent.py` | — | S8, S9 |
| G18 | No group or class concept; no bulk invitation; no open link or QR | — | S5–S7 |
| G19 | No group report; no anonymity threshold | — | S13 |
| G20 | Panel owner cannot see the audit trail of their own panel | — | S14 |
| G21 | Participant portal is one table (`/my/assessments`): no to-do view, no "who can see my results" page, no notifications, no data export/delete request | `ts_assessment/views/web_portal.xml` | S15 |
| G22 | No session timeout for staff, no re-authentication before sensitive actions, no sessions page of our own (Odoo's `/my/security` is available) | — | S3 (re-auth), S18 |
| G23 | Email+password accounts follow Odoo's instance-wide password policy, which is shared with eot.ir and must not be changed. NIST's 15-character rule can only be applied on website-4 forms | — | S18 |
| G24 | No retention jobs: abandoned attempts, expired invitations' contact data and old notifications are never purged | — | S18 |
| G25 | No design-system document; panel pages reuse marketing-site classes; no status colour tokens for warning/info; table and pill styles live in `assessment.scss` | scss files | S2 |
| G26 | Header shows «درخواست جلسهٔ معرفی» and «سنجه‌های من» to signed-in staff; no entry to the panel from the header | `ts_website/views/layout.xml` | S2 |
| G27 | Trust pages and terms must be re-checked against what v2 actually does before each ship that changes behaviour (lesson of 2026-09-29) | `ts_website/views/pages_trust.xml`, `ts_org/views/web_panel.xml` | every stage |
| G28 | **No usage event is written for TALENT-INV-15.** `ts_talent` scores matrix attempts in its own `action_submit` without calling `super()`, so the hook in `ts_org` that writes `ts.usage.event` never runs for the only instrument education panels can assign. "Usage is recorded" is not true for it | `ts_talent/models/attempt.py` `action_submit`, `ts_org/models/attempt.py` | S0 |
| G29 | A self-taken result of an ordinary (non-matrix) instrument shared with an education panel **cannot be opened by the counselor**: the assignment page redirects education-level results to `/p/<attempt>`, which answers 404 for anything that is not a matrix attempt | `ts_org/controllers/main.py` `assignment()`, `ts_talent/controllers/main.py` `org_person()` | S13 (rule in permissions 5) |
| G30 | **The TALENT-INV-15 report has no sharing block.** «لغو اشتراک» and «ارسال نتیجه برای مشاورم» are added by a view that inherits `ts_assessment.tpl_report` only; the matrix report is a different template. A student who accepted an invitation with sharing on has no button to revoke it, although the invitation page says it is revocable | `ts_org/views/web_org.xml` `tpl_report_share`, `ts_talent/views/web_talent.xml` | S0 |
| G31 | The share-by-code page says the counselor sees «فقط بازهٔ هر زمینه»; for TALENT-INV-15 the counselor sees the whole report without the answers | `ts_org/views/web_panel.xml` | S0 |

## 3. Target versus code, by module and file

Legend: KEEP (no change), EXTEND (add, behaviour kept), CHANGE (behaviour changes),
REPLACE (superseded by `ts_panel`, removed in S20), NEW.

### ts_core (changed only in S1; it has no `website` dependency, so no new views here)
| File | Now | Target | Action |
|---|---|---|---|
| `models/workspace.py` | `ROLES`, `ROLES_BY_PURPOSE`, `GATED_PURPOSES`, approve/reject/suspend/resume, last-owner guard, `unique(workspace_id,user_id,role)` | Add role `admin`; one active membership per person per panel; fix labels | CHANGE (S1) |
| `models/audit.py` | Append-only `ts.audit.event` with `event_type, actor_id, workspace_id, res_model, res_id, detail, ip_address` | Add `outcome, route, request_id, ip_hash, member_id`; sanitise `detail`; stop storing raw IP | EXTEND (S1) |
| `models/emergency.py` | `ts.emergency.access` (clinical only, 24 h, reason ≥ 15 chars) | Generalise to support access for any panel (S14); reason stays on the record, not in audit `detail` | EXTEND (S14, from `ts_panel` by `_inherit`) |
| `security/*` | Three back-office groups; portal read on own panels and co-members | Unchanged | KEEP |
| `views/*` | Workspace list/form, pending queue, audit list | Tenant-health columns arrive from `ts_panel` backend views | KEEP |

### ts_assessment
| File | Now | Target | Action |
|---|---|---|---|
| `models/attempt.py` | States `consent, in_progress, done, error`; consent fields on the attempt; idempotent submit; autosave per answer; `released` | Add `stopped` and `erased` states and `voided` flag (by `_inherit` in `ts_panel`); consent ledger rows written next to the existing fields | EXTEND (S15, S16, S18) |
| `controllers/main.py` | Catalog, player, review, submit, `/my/assessments`, report | Player kept. `/my/assessments` list and the `/my` home are redesigned in `ts_panel` by overriding the routes | KEEP + override (S15) |
| `views/web_player.xml`, `web_catalog.xml` | Player and catalog | Accessibility pass only | KEEP (S19) |
| `views/web_portal.xml` | `my_list`, `report` | `my_list` REPLACE (S15); `report` gets a "who can see this" block | EXTEND |
| `static/src/scss/assessment.scss` | Holds `.ts-table`, `.ts-pill`, `.ts-btn--sm`, `.ts-progress` used by the panel | Tokens and shared components documented; panel-only styles go to `ts_panel/static/src/scss/panel.scss` | KEEP |
| `security/ir.access.csv` | Portal reads own attempts/answers/results; manager reads all | See G13 | per decision D4 |

### ts_org
| File | Now | Target | Action |
|---|---|---|---|
| `models/assignment.py` | Invitation = share carrier; `INVITE_ROLES, VIEW_ROLES, VERIFIED_ROLES, EDU_ROLES, SEE_ALL_ROLES`; `visible_results(member)`; `can_see`, `can_assign`, `sees_unassigned`; default responsible; `ts_share_attempt` (one panel only) | Role sets replaced by the permission registry; `result_level()` is the single decision function; `visible_results` kept as a thin wrapper | CHANGE (S1) |
| `models/panel.py` | `ts_panel_create`, `ts_update_profile`, `TERMS_VERSION`, phone/email normalisers | Solo panels set `owner_practices`; profile gains contact fields (in `ts_panel`) | CHANGE (S1) |
| `models/member_invite.py` | Identity-bound, 7 days, max 20 pending, revoke | Add "send again" (new token, old one revoked) in `ts_panel` | KEEP |
| `models/attempt.py` | `responsible_id` for imports; `ts_org_visible_to`; usage event on submit | Visibility goes through `result_level()`; usage event also writes the ledger row (from `ts_panel`) | CHANGE (S1), EXTEND (S11) |
| `models/usage.py` | `ts.usage.event`, unique per attempt | Stays the metering fact | KEEP |
| `models/perms.py` | — | Permission registry and helpers | NEW (S1) |
| `controllers/main.py` | `/my/workspaces`, the one-page panel, invite POST, assignment view, responsible POSTs, `/invite/<token>` flow, unshare | Staff routes overridden page by page from `ts_panel`; `/invite/<token>` kept and extended (opened_at, client link, minors) | REPLACE staff pages (S2–S6), KEEP invite flow |
| `controllers/panel.py` | `/panel`, `/panel/terms`, create, settings POST, member invite/revoke, `/join/<token>`, share by code | Landing, terms, create and join kept; settings and members move to their own pages | KEEP + override |
| `views/web_org.xml` | `workspaces`, `workspace`, `assignment`, `invite`, report-sharing note | `workspace` and `assignment` REPLACE; `invite` EXTEND; `workspaces` restyled as the switcher page | S2–S6, removal S20 |
| `views/web_panel.xml` | Landing, terms, new, join, share form | KEEP; terms text gets a new version when behaviour changes | KEEP |
| `views/backend.xml`, `emergency.xml` | Assignment list/pivot, ops dashboard, verification queue, emergency access | Tenant health and new queues are added from `ts_panel` | KEEP |
| `security/ir.access.csv` | Operator reads assignments; manager cru | G12 | CHANGE (S17) |

### ts_sms
| File | Now | Target | Action |
|---|---|---|---|
| `controllers/main.py` | `TsSmsController(TsOrg)` overrides `invite` (phone + consent tick); `TsSmsPanelController(TsPanel)` adds mobile sign-in URLs; `/my/phone*` | `ts_panel` controllers must subclass these two classes so the SMS behaviour stays in the chain | KEEP |
| `views/web_sms.xml` | Inherits `ts_org.tpl_workspace` with three xpaths (phone input, SMS note, hint). It is the only view that inherits a template the plan retires | The phone field and consent tick are rebuilt in the v2 invite wizard (S6). The inherited view and its parent `ts_org.tpl_workspace` are removed together in S20 | REPLACE (S20) |
| `models/assignment.py`, `attempt.py` | Invitation SMS on create (valid mobile + consent tick); result-ready SMS (verified mobile + opt-in) | Called through the notification dispatcher so rate limits, quiet hours and the log are shared | EXTEND (S10) |
| `models/signup_otp.py`, `phone_otp.py` | OTP 6 digits, 5 minutes, 5 attempts, 60 s cooldown, 5/hour/phone, 20/hour/IP hash; login token 120 s | Meets NIST/ASVS limits. Add a re-authentication purpose (S9) and a short risk notice (S18) | EXTEND |

### ts_talent
| File | Now | Target | Action |
|---|---|---|---|
| `controllers/main.py` | Matrix player; `report_ctx()`; institute view `/my/workspaces/<ws>/p/<attempt>` (audited `attempt.result_view`); its own `action_submit` path never reaches the usage hook (G28) | Institute view is reached from the client page; permission check goes through `result_level()` (the model method it already calls); route kept as a redirect from S13 | KEEP; overridden from `ts_panel` (S13) |
| `views/web_talent.xml` | Matrix report template without the sharing block (G30) | Block added by an inherited view of `ts_panel` | S0 |
| `models/attempt.py` | `person_id`, `source`, `import_batch`, matrix fields/cells, `profile_json` | `client_id` added by `ts_panel`; imports get client rows in the backfill | EXTEND (S4) |
| `models/loader.py` | TALENT-INV-15 `audience='adult'` | See G7 | S16 |
| Group report | — | Aggregates for TALENT-INV-15 (scale means, top-field distribution) with threshold | NEW in `ts_panel` (S13) |

### ts_website
| File | Now | Target | Action |
|---|---|---|---|
| `views/layout.xml` | Header actions for signed-in users: «سنجه‌های من», account | Role-aware header: staff get «پنل من», participants get «کارهای من»; notification bell (S10) | CHANGE (S2, done by an inherited view owned by `ts_panel`) |
| `static/src/scss/ts.scss` | Tokens and marketing components | Add status tokens (`--warn`, `--info` and their soft backgrounds). No other change | EXTEND (S2) |
| `models/website.py` | Site setup, stock-app containment, portal cards | Unchanged | KEEP |
| Trust pages | Privacy, consent policy, help | Text re-checked against behaviour at each ship (G27) | review |

### ts_kavenegar
No change. New SMS texts use the existing gateway and log; OTP texts stay masked.

### New module `ts_panel` (S0)
Depends on `ts_talent` (which already depends on `ts_org`, `ts_sms`, `ts_assessment`), so it
sits at the top of the dependency graph: upgrading it touches no other module. It owns every
new model, page, stylesheet and back-office view of Panel v2. Rule kept from `CLAUDE.md`: all
its website views are records with `website_id` = website 4, and its assets go only into
`ts_website.assets_ts` / `assets_ts_js`.

## 4. Feature coverage summary

| Area (catalogue 4.3 / 5.2) | Exists | Thin | Missing |
|---|---|---|---|
| Tenancy, switcher, self-service panel, approval queue | ✓ | | |
| Roles and invitations of colleagues | ✓ | role change, deactivate, resend | role matrix page, admin role |
| Authorization | role sets + responsible member | | permission registry, deny logging, test matrix |
| Client records, groups | | | ✓ |
| Participant invitations | single, by link (+SMS) | expiry state, reminders | bulk, CSV, open link/QR, campaigns |
| Dashboard | six counters | | role-based KPIs, needs-attention, checklist v2 |
| Tables | plain table | | search, filters, sort, pagination, bulk, saved views |
| Reports | individual (three levels), print CSS | | group report, export |
| Import / export | operator tool only | | ✓ |
| Notifications | SMS to participant | | in-app, staff events, preferences, reminders |
| Wallet / usage | usage event row (not written for TALENT-INV-15, G28) | | ledger, page |
| Audit | platform-side list | detail hygiene | owner view, export, deny events |
| Help and onboarding | 4-item checklist, FAQ page | | contextual help, role help, help placement |
| Support access | emergency (clinical) | | support access for any panel, owner visibility |
| Security | CSRF, OTP limits, object checks by 404 | | re-auth, staff session timeout, upload checks beyond logo |
| Privacy lifecycle | consent fields on attempt, terms version on panel | | consent ledger, retention jobs, data requests, anonymisation |
| Localization | RTL, Jalali, Persian digits helpers | | Latin digits and BOM in exports, search normalisation |
| Accessibility | focus ring, 44 px controls, skip link | | WCAG 2.2 AA audit of panel pages |
| Platform back-office | pending queue, verification queue, ops pivot | | tenant health, usage per tenant, data-request queue |
| Guardian / minors | parent-report instruments | | minors in school panels, guardian record |
