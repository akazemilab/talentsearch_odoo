# Panel v2 — 07 Build plan (Phase 2)

Twenty-one stages, each small enough for one rehearsal and one ship. The implementer does not
make product decisions: scope comes from `02_feature_catalog.md` (feature ids), data from
`04_data_model.md`, rules from `05_permissions_matrix.md`, pages from `03_ia_and_ux.md`,
components and copy from `08_design_system.md`. If any of them is silent or wrong, write it in
`docs/panel_v2/DEVIATIONS.md` and ask the owner.

## 0. Rules for every stage

1. Branch `pv2-<n>-<slug>` from `origin/main` (never from local `main`).
2. `ts check` before every rehearsal.
3. Rehearse (the install and upgrade lists are the same list, as in every earlier rehearsal):
   `ts bg pv2s<n> "bash /root/talentsearch_odoo/tools/vps/ts_rehearse.sh eot_ts<NN> <MODS> <MODS>"`
   then `ts wait pv2s<n> 50` (never `sleep`). Use a fresh clone name per stage: `eot_ts30`
   for S0, `eot_ts31` for S1, and so on. A re-run on the same clone name may use `SKIP_BASE=1`.
4. The verdict line must read: guard `eot.ir UNCHANGED`, portal `UNCHANGED`, unexpected
   failures `0`.
5. `ts db stop <clone>`, then `ts ship '' <MODS> pv2s<n>` (S0 installs: `ts ship ts_panel '' pv2s0`),
   then `ts wait ship_pv2s<n>`; it ends with `ts live`.
6. Merge to `main`, push with an explicit `origin main`, add a section to
   `docs/IMPLEMENTATION_LOG.md`, update `docs/panel_v2/HANDOFF.md` (stage log, next stage),
   record any mistake as a lesson in Project memory.
7. **Which files a stage may edit.** A file of module X may be edited only when X is in the
   stage's upgrade list. Everything else is changed from `ts_panel`: models with `_inherit`,
   templates with an inherited view owned by `ts_panel` (website 4), controllers by
   subclassing. Stylesheets and JavaScript files are the exception: they are read from disk,
   so an edit ships with the code and needs no module upgrade.
8. Tests per stage: ORM file `tools/prod/tests_pv2_<n>.py` (deny cases first; runs in the
   non-committing group unless it must commit) and HTTP file `tools/prod/ts_http_pv2_<n>.py`
   (every new or changed template rendered: status, key Persian text, no traceback; flows end
   to end; 403 and 404 cases). Both are wired into `tools/vps/ts_rehearse.sh` under
   `has ts_panel`. Older suites must stay green; when a rule changes, grep the old tests for
   the role or count first.
9. Fixtures are fictional. Logins `ts.pv2.<role>@example.invalid`. Test mobiles for stage `n`:
   `0913 55 <nn> 001…099` (for example S6 uses `09135506001`); `ts check` warns on collisions.
10. Shared fixture builder (S0): `tools/prod/pv2_fixtures.py`, run inside `odoo shell` on a
    clone. It builds three approved panels (education, clinical, employment), one member per
    role, clients in every state, invitations in every state, and one finished and shared
    result per purpose produced by the real `action_submit` (for education a real
    TALENT-INV-15 attempt). It upserts on every run.
11. New website views are `ir.ui.view` records with `website_id` = `ts_website.website_ts`;
    assets go to `ts_website.assets_ts` / `assets_ts_js` only; no view in `ts_core`.
12. Controllers subclass the top-most existing class so earlier overrides stay in the chain:
    staff pages extend `TsSmsController` (which extends `TsOrg`), panel pages extend
    `TsSmsPanelController` (which extends `TsPanel`), participant pages extend the `ts_talent`
    controller class (which extends `TsAssessment`). Route overrides use `@http.route()` with no
    arguments.
13. `/my`, `/my/home`, `/my/account` and `/my/security` are stock portal routes shared with
    eot.ir. Any override first checks `request.env.website._ts_is_current()` and otherwise
    returns `super()` untouched. No change to `res.users` session-token fields, to the
    instance-wide password policy, or to any `ir.http` behaviour outside website 4. No new
    Odoo app is installed by any stage.
14. Never message real people from a test; SMS goes to the fake Kavenegar only. Nothing may
    reach the 108 historical people (`contact_locked`, P20).
15. Before each ship re-read the public texts that describe the changed behaviour (terms,
    privacy, help) and fix them in the same stage, with a new text version when the meaning
    changes.
16. Rollback, every stage: `ts ship` keeps the previous code directory and restores it if the
    install fails. Data steps are additive (new tables, new columns, filled empty columns), so
    the previous code runs on the migrated database. If a shipped stage must be withdrawn
    later, ship the previous commit with the same module list; never drop columns by hand.
    Stages with a specific risk say more below.
17. Parallel work: only the pairs marked in section 1. The parallel stage is rebased on
    `origin/main` after the other one is merged and **rehearsed again** before its own ship.
18. Stop and ask the owner when: a decision is missing from `HANDOFF.md`; the guard shows any
    eot.ir difference; a migration would touch live participant data beyond what `HANDOFF.md`
    approves; anything would message real people (S10 has an explicit gate).

Sizes: **S** one rehearsal expected · **M** one or two · **L** two or three. A rehearsal takes
about 12 minutes and a ship about 25–35 minutes on the current servers; add the coding time of
the session. One stage is one working session in most cases, two for an L.

## 1. Stage overview

| Stage | Slug | What becomes live | Modules to upgrade | Size | May rehearse in slot 1 while the previous stage ships |
|---|---|---|---|---|---|
| S0 | `tooling` | `ts_panel` module, fixtures, preflight rules; two fixes: usage event and sharing block for TALENT-INV-15 | install `ts_panel` | S | — |
| S1 | `perms` | Permission registry, `admin` role, practising owner, one membership per person, audit fields | `ts_core,ts_org,ts_panel` | L | no |
| S2 | `shell` | Panel shell and menu, dashboard v1 at `W/home` (existing counters), settings page, header link, tokens | `ts_panel` | M | no |
| S3 | `members` | Members page: invite, send again, revoke, change role, deactivate, role help; re-authentication | `ts_panel` | M | no |
| S4 | `clients` | Client records with backfill, client list and page, responsibility on the client | `ts_panel` | L | no |
| S5 | `clients-edit` | Create/edit, groups, bulk actions, saved views, merge, handover | `ts_panel` | L | no |
| S6 | `invites` | Invite wizard, states incl. opened/expired, invitation page with QR, extend, withdraw; `W` becomes the dashboard | `ts_panel` | L | no |
| S7 | `campaigns` | Group invitations and open link | `ts_panel` | M | no |
| S8 | `import` | Jobs and CSV/XLSX import | `ts_panel` | L | no |
| S9 | `export` | Exports | `ts_panel` | M | no |
| S10 | `notify` | Notification center, preferences, reminders (new SMS kinds ship switched off) | `ts_panel` | L | no |
| S11 | `wallet` | Ledger, credits page, back-office usage | `ts_panel` | M | no |
| S12 | `dashboard` | Role-based dashboard, onboarding checklist | `ts_panel` | M | no |
| S13 | `reports` | Result page under the client, print, group report | `ts_panel` | L | no |
| S14 | `audit` | Panel audit page, support access | `ts_panel` | M | no |
| S15 | `portal` | Participant home, sharing page, privacy requests | `ts_panel` | L | no |
| S16 | `minors` | Age group rules, guardian attestation, assent text, consent ledger | `ts_panel` | M | no |
| S17 | `backoffice` | Tenant health, data-request queue, operator access fix | `ts_org,ts_panel` | M | **yes** (touches only back-office views and one access row) |
| S18 | `lifecycle` | Retention job (switched off), erase workflow, close/transfer panel, staff timeout, sessions | `ts_panel` | L | no |
| S19 | `help-a11y` | Help center, contextual help, accessibility pass, text check | `ts_panel` | M | **yes** (help pages and template fixes only) |
| S20 | `cleanup` | v1 pages and styles removed | `ts_org,ts_sms,ts_panel` | S | no |

Optional, only if the owner decides: **S14b** technical lock on clinical data for platform
managers (D4). Guardian-link consent (S16b) is not built: the owner chose attestation (D2).

A release the owner can announce exists after S3 (people), S8 (clients and invitations at
scale), S13 (insight), S18 (trust).

## 2. How the old one-page panel is replaced without a gap

Today `W` renders one template (`ts_org.workspace`), and its POST routes redirect back to `W`
(some with query parameters, some bare). To keep every one of those redirects and every old
test working, **`W` stays the old page until S6**:

- S2–S5: the new pages live at their own URLs: dashboard `W/home`, `W/settings`, `W/members`,
  `W/clients`, `W/groups`. The panel menu has one extra item «دعوت و فهرست (نسخهٔ قبلی)» → `W`,
  and an inherited view puts a one-line notice with a link to `W/home` at the top of the old
  page. `/my/workspaces` and the header link point to `W/home`. For a few stages a member can
  do the same thing in two places (members, name and logo); both write the same records.
- S6: the last piece (inviting) is replaced. `ts_panel` overrides `workspace()` to render the
  dashboard at `W`, `W/home` redirects to `W`, the extra menu item goes, and each old POST
  route is overridden to redirect to its new page (invite → invitation page, responsible →
  client page, member invite/revoke → members page, settings → settings page).
- S13: the old result routes `W/a/<id>` and `W/p/<id>` redirect to the result page under the
  client.
- S20: the old template, its inherited SMS view and the old styles are deleted.

| Piece of the old page | New page arrives in | Old piece disappears in |
|---|---|---|
| Counters | S2 (`W/home`) | S6 |
| Name and logo form | S2 | S6 |
| Members, colleague invitations | S3 | S6 |
| Participant list, filters, responsible dropdowns, imported results | S4 | S6 |
| Invite form and created link | S6 | S6 |
| Result pages `W/a/<id>`, `W/p/<id>` | S13 | S13 |
| Templates and styles | — | S20 |

Old HTTP suites (`ts_http_org.py`, `ts_http_resp.py`, `ts_http_panel.py`, `ts_http_edu.py`,
`ts_http_sms.py`) keep passing unchanged through S5. In S6 the checks that read the old page
are moved to the new pages (most are already covered by the `ts_http_pv2_<n>.py` files of
S2–S5); the model-level and participant-side checks stay as they are.

After S4 the old page's responsible dropdowns keep working because the overridden
`_set_responsible` writes the client (imported results have client rows too, decision D5).

## 3. Stages in detail

### S0 — tooling (size S)
- **Scope**: SEC-1 (preflight rules), A11Y-1 tooling, fixtures, WAL-0 (G28), PRT-0 (G30, G31).
- **Files**: new `addons/ts_panel/` (`__manifest__.py` depends `ts_talent`; `models/`,
  `controllers/`, `views/`, `security/ir.access.csv`, `static/src/scss/panel.scss` registered
  in `ts_website.assets_ts`, `static/src/js/panel.js` in `assets_ts_js`);
  `ts_panel/models/attempt.py` (override of `action_submit`: after `super()` returns true, for
  a `done`, non-import attempt with a `workspace_id`, create the `ts.usage.event` if none
  exists); `ts_panel/views/report_share.xml` (inherited view on the matrix report template
  `ts_talent.tpl_report` adding the same sharing block that `ts_org.tpl_report_share` adds to
  the other report, **wrapped in `t-if="not org_view"`** because the same template renders the
  institute's view; and an inherited view on `ts_org.tpl_share_form` correcting the sentence
  about what the counselor sees, per instrument kind); `tools/prod/pv2_fixtures.py`; `tools/vps/ts_check.py`
  (rules: audit `.log(` with a deny-listed keyword, **as a warning until S1**;
  `sudo().search/browse` in `ts_panel/controllers` outside `base.py` without `workspace_id`;
  forbidden marketing words in `ts_panel` templates); `tools/vps/ts_shot.py` (route list per
  fixture role, checks of `08_design_system.md` section 5); `tools/vps/ts_rehearse.sh`
  (`has ts_panel` block).
- **Tests**: P22; HTTP: a participant with a shared TALENT-INV-15 result sees «لغو اشتراک»,
  uses it, and the counselor's view turns to "not shared"; the counselor's view of the same
  report never contains the revoke form; share-by-code text names the right
  content; `ts check` self-test on a sample bad file; fixtures run twice with identical counts.
- **Risk**: low. The two fixes are additive (an event row; a block on a page).
- **Owner note at ship**: usage counting for TALENT-INV-15 starts now; earlier completions in
  panels (none live yet) were not counted.

### S1 — perms (size L)
- **Scope**: `05_permissions_matrix.md` sections 1–5 and 9; MEM-3b, MEM-7; AUD-1, AUD-2;
  gaps G1, G2, G4, G5, G6.
- **Files**: `ts_core/__manifest__.py` (version `20.0.1.1.0`),
  `ts_core/migrations/20.0.1.1.0/pre-migrate.py` (M2 de-duplication before the index),
  `ts_core/models/workspace.py` (role `admin`, `ROLES_BY_PURPOSE`, labels, unique index,
  `owner_practices`, deactivation fields; `workspace.reject`/`suspend` audit calls without the
  free text), `ts_core/models/audit.py` (fields, `_clean_detail`, `log_denied` with its own
  cursor, indexes, IP salt), `ts_core/models/emergency.py` (audit call without the reason
  text; the clinical-only and 24-hour checks moved into `_check_scope(vals)` and
  `_hours(vals)` with unchanged behaviour, so S14 can override them); `ts_org/models/perms.py` (new: `ROLE_PERMS`, `has_perm`, `perms`, `can_see`),
  `ts_org/models/assignment.py` (`result_level`; `visible_results`, `can_invite`, `can_assign`,
  `sees_all`, `sees_unassigned`, `can_act` become thin wrappers over the registry),
  `ts_org/models/attempt.py` (`ts_org_visible_to` through `result_level`),
  `ts_org/models/panel.py` (solo sets `owner_practices`; a solo psychologist is asked for a
  licence number; labels), `ts_org/models/member_invite.py` (`action_accept` refuses an
  existing active member with the MEM-3b message), `ts_org/controllers/*.py` (`_membership`
  uses A1–A5b and writes deny events), `ts_panel/data/migrate.xml` (M1, rest of M2).
- **Behaviour kept**: every existing suite passes unchanged except where the matrix says NEW.
  An unverified clinician or clinic director still gets the 404 in this stage (the notice page
  arrives with the shell in S2).
- **Tests**: `tests_pv2_1.py` = P01–P17, P23, P24; `ts_http_pv2_1.py`: solo psychologist flow
  (create, verify, open own client's clinical result); `admin` sees participants and no result
  on the old page; deny events written and throttled.
- **Risk**: medium-high, it touches the visibility core. Mitigation: the matrix test and the
  five old org suites; rehearse twice if any old test needed editing.
- **Rollback**: the unique index would refuse nothing the old code does from its pages; the
  new columns are ignored by old code.
- **Upgrade list**: `ts_core,ts_org,ts_panel` (dependents follow automatically).

### S2 — shell (size M)
- **Scope**: `03_ia_and_ux.md` 1.1 and section 2; ORG-1, ORG-2, ORG-5, ORG-6; MEM-9; HLP-1;
  G25, G26; section 2 of this file.
- **Files**: `ts_panel/controllers/base.py` (helpers of permissions 9), `controllers/shell.py`
  (`W/home`: dashboard v1 with today's six counters as tiles; `W/settings` page with its own
  POST gated by `panel:profile`; `W` itself is not overridden yet),
  `views/web_shell.xml` (template `ts_panel.shell` called with attributes for title and active
  item; 403 page; suspended/closed/awaiting-verification pages), `views/web_dashboard.xml`,
  `views/web_settings.xml`, `views/layout_inherit.xml` (inherited view on the website-4
  layout: role-aware header link and the place for the bell),
  `ts_website/static/src/scss/ts.scss` (new tokens only; a stylesheet edit, rule 7),
  `panel.scss` (shell, head, stat, empty, flash, field), `panel.js` (menu toggle, copy button),
  an inherited view on the old page with the notice link.
- **Tests**: HTTP: each role gets the menu items of its permissions and no others; settings
  save by owner and by hr_admin, 403 for a counselor; unverified clinician sees the notice
  page at `W/home` (the old `W` still answers 404 for them); header link by role; old suites
  green unchanged; headless audit at 1280 and 375 px for dashboard and settings.
- **Risk**: low-medium (layout inheritance on website 4 only; the guard checks eot.ir).

### S3 — members (size M)
- **Scope**: MEM-1…MEM-8; SEC-5, A11Y-2 (re-authentication, first needed here for MEM-6).
- **Files**: `ts_panel/controllers/members.py`, `views/web_members.xml`,
  `views/web_help_roles.xml`, `ts_panel/models/member.py` (role change and deactivate methods
  with audit; send-again on `ts.member.invite`), `ts_panel/controllers/reauth.py` and
  `views/web_reauth.xml`, `models/reauth.py` (`ts.reauth.code`, `04_data_model.md` 3.7b: the
  code goes only to the account's verified mobile; password for accounts without one; stores
  `ts_reauth_at` in the session; audit `auth.reauth`).
- **Tests**: ORM: role change releases clients when needed, last-owner guard, second owner
  only by owner; HTTP: invite, send again (old token dead), revoke, change role, deactivate
  with confirmation page, reactivate, role help lists every role; adding an owner without a
  fresh re-authentication redirects to `/my/reauth`; one OTP field that accepts paste; a code
  requested for another number through `/my/phone` does not pass re-authentication; 403 for
  roles without `members:read`.
- **Risk**: low.

### S4 — clients (size L) — M4 runs (owner decision D5: yes, locked)
- **Scope**: CLI-1, CLI-2 (assessments tab), CLI-4, CLI-7b, ORG-3, TBL-1…4, TBL-7…9, GRD-1
  (field only), L10N-4; migration M3–M5; G10, G11.
- **Files**: `ts_panel/models/client.py` (incl. `contact_locked` and its model-level
  refusals), `models/text.py` (`norm_text`), `models/assignment.py` and `models/attempt.py`
  (`_inherit`: `client_id`; `responsible_id` as a read-only stored related; the five writers
  of `04_data_model.md` 2.4 neutralised from `ts_panel`, starting with the override of
  `ts_default_responsible()`; client matching rule 4 for the old invite form; linking rules
  1–3 in `action_accept` and `ts_share_attempt`),
  `data/migrate.xml` (M3–M5), `controllers/clients.py` (list with a domain builder, sort
  whitelist, pagination, posted search; client page; responsible POST), `views/web_clients.xml`,
  `panel.scss` (table, chips, pager, cards), back-office list view for clients (manager only).
- The clients page is `W/clients`; the old page at `W` stays (section 2). The existing
  responsible POST routes keep working by writing the client. The 108 imported people appear
  as locked clients (`contact_locked`) with a filter «واردشده».
- **Tests**: ORM: backfill idempotent (run twice), import clients = distinct people, no SMS or
  notification rows created, 114 stay unreleased, `can_see(client)` R0–R3, linking rules 1–4
  incl. the automatic account link, default responsible rule per role, P20 (lock); HTTP: list
  search with Persian and Arabic letter variants (search text not in the URL), filters, sort,
  page 2, card layout at 375 px, client page per role, object id of another panel → 404.
- **Risk**: medium (first data migration; responsibility moves). Compare counts before and
  after on the clone; old suites `tests_org_resp.py` and `tests_edge.py` are the safety net
  for responsibility.

### S5 — clients-edit (size L)
- **Scope**: CLI-3, CLI-5, CLI-6, CLI-7, CLI-8, TBL-5, TBL-6.
- **Files**: `models/group.py`, `models/saved_view.py`, client methods (archive, merge,
  handover), `controllers/clients.py` (forms, bulk endpoint), `controllers/groups.py`,
  `views/web_client_form.xml`, `web_groups.xml`, `panel.scss` (batch bar), `panel.js`
  (select page, count).
- **Tests**: ORM: unique code per panel, duplicate warning sources, merge moves assignments and
  attempts and refuses two accounts or a locked client, archive blocks invitations, handover
  needs confirmation; HTTP: bulk actions through the plain form post, saved view round trip
  (no search text stored), group page.
- **Risk**: medium (bulk endpoints: re-check every id against the panel and R0–R3).

### S6 — invites (size L)
- **Scope**: INV-1…INV-4; G9; SEC-3 (invitation limit).
- **Files**: `models/assignment.py` (`expires_at`, `opened_at`, `expired`, `channel`,
  `remind_ok`, state compute, extend), `data/cron.xml` (hourly expiry),
  `controllers/invites.py` (wizard; its last POST creates the assignment itself with
  `client_id`, `invitee_phone`, `sms_consent`, `remind_ok`, after the same checks the old
  `invite()` does (permission, gated panel, allowed instrument, valid mobile); the SMS is sent
  by `ts_sms`'s model `create`, so that rule stays in one place; invitation page),
  `views/web_invites.xml`, an inherited view on `ts_org.tpl_invite` (panel contact; no edit of
  `ts_org` files), `controllers/shell.py` (`W` becomes the dashboard; the old POST routes
  redirect to the new pages, section 2).
- **Tests**: ORM: state order incl. expired and opened, expiry only before acceptance, cron,
  extend; HTTP: wizard happy path, gated panel, instrument not allowed, SMS consent tick →
  fake Kavenegar receives exactly one message, no tick → none; expired link message; QR image
  answers 200 and decodes to the link; every old POST route lands on its new page; the five
  old HTTP suites moved off the old page (section 2).
- **Risk**: medium (the invitation path is the product's main path: run the participant flow
  suites after it).

### S7 — campaigns (size M)
- **Scope**: INV-5, INV-6, INV-9.
- **Files**: `models/campaign.py`, `controllers/campaigns.py` (staff), public `/c/<token>`
  join in the participant controller, `views/web_campaigns.xml`, print sheet of links/QR.
- **Tests**: ORM: no duplicate open invitation per client and instrument, cap, expiry, close,
  locked clients skipped and reported; HTTP: group invite, open-link join creates or reuses a
  client, full → message, rate limit per IP hash.
- **Risk**: medium (public join route: rate limit and cap).

### S8 — import (size L)
- **Scope**: IMP-1, INV-7, SEC-4; `ts.job` with the cron runner.
- **Files**: `models/job.py`, `models/importer.py` (CSV with encoding detection; XLSX only if
  `openpyxl` is importable on prod: check first and record the result in `DEVIATIONS.md` if it
  is not), `data/cron.xml`, `controllers/imports.py`, `views/web_import.xml`,
  `views/web_job.xml`, static template file.
- **Tests**: ORM: idempotent import (same file twice), match by code then phone then email,
  duplicates inside the file, invalid rows reported not imported, row limit, Windows-1256 file,
  Persian digits in phones, source attachment deleted at the end, P21; HTTP: whole wizard,
  error report download, job page states, another member cannot open the job.
- **Risk**: medium-high (file parsing). Never echo row content into logs or audit.

### S9 — export (size M)
- **Scope**: EXP-1…EXP-3, SEC-8, L10N-2.
- **Files**: `models/exporter.py`, `controllers/exports.py`, `views/web_exports.xml`.
- **Tests**: ORM: rows filtered by `result_level` per requester, no answers column, no field
  names for TALENT-INV-15, formula prefix, BOM bytes, Latin digits, both date columns, link
  expiry, P21; HTTP: export without fresh re-authentication → redirect; clinical panel has no
  results export; download audited; second download after expiry refused.
- **Risk**: medium (data leaves the system: test the row-level filter hardest).

### S10 — notify (size L) — **gate: nothing new reaches a phone at ship**
- **Scope**: NOT-1…NOT-5b, ACC-7, INV-8, PLT-6; G15, G16.
- **Files**: `models/notify.py`, `models/notify_texts.py`, company switches `ts_sms_reminder`
  and `ts_sms_staff` (default False) with their Settings fields, `data/cron.xml` (reminders
  daily at 10:00 Tehran, queued SMS flushed at 08:00), hooks at submit, accept, self-share,
  revoke, member join, approve/reject/suspend, job done; `controllers/notifications.py`,
  `views/web_notifications.xml`, bell in the layout view, preferences page.
- **Tests**: ORM: each event creates exactly the rows of the catalogue table; with both new
  switches off no `sms.sms` row is created by any new path; with them on (clone only): quiet
  hours queue, per-day limit, reminder conditions (`sms_consent` and `remind_ok`), an
  invitation created before S6 never gets an SMS reminder; **P20**; HTTP: bell count, mark
  read, preferences respected, fake Kavenegar message count.
- **At ship**: tell the owner, in Persian, the exact text of each new SMS and when it is sent;
  the owner turns the switches on. Email stays unbuilt (D8).
- **Risk**: medium-high. Rollback: switches off.

### S11 — wallet (size M)
- **Scope**: WAL-1…WAL-3, WAL-5, WAL-6, PLT-4; G14; migration M6.
- **Files**: `models/wallet.py`, debit in the `action_submit` override from S0,
  `controllers/credits.py`, `views/web_credits.xml`, back-office list/pivot, void action on
  attempt (manager).
- **Tests**: P19, P22; ORM: reconcile from attempts detects a missing event or debit; void →
  one refund; self-share not charged; import not charged; HTTP: credits page shows «رایگان در
  این فصل» and never a price.
- **Risk**: low (free mode; nothing blocks).

### S12 — dashboard (size M)
- **Scope**: DSH-1…DSH-5; `03_ia_and_ux.md` section 5.
- **Files**: `models/dashboard.py` (one method per metric returning count and list URL),
  `controllers/shell.py`, `views/web_dashboard.xml`, `panel.scss` (todo list, funnel).
- **Tests**: ORM: each metric against fixtures; HTTP: each tile's number equals the count on
  the linked list; thresholds hide median and rate below 5; no score or band text on the page.
- **Risk**: low. Use `search_count`/`read_group`, not Python loops over all rows.

### S13 — reports (size L)
- **Scope**: REP-1…REP-3, CLI-2 (result links), PRT-6; G29.
- **Files**: `controllers/reports.py` (result page under the client; old routes redirect),
  `views/web_result.xml` (wraps the three renderings: band summary, matrix report via
  `report_ctx(org_view=True)`, clinical report; an ordinary instrument at level `education`
  renders the band summary), `models/group_report.py`, `views/web_group_report.xml`, print CSS.
- **Tests**: P12 over HTTP for every level and role; a self-shared ordinary result opens for
  the counselor (G29); P18; group report with 4 shared results shows the threshold text;
  complementary suppression case; TALENT-INV-15 aggregates as defined in REP-3; print page via
  headless; suite `ts_http_edu.py` moved.
- **Risk**: medium (rendering paths of three report kinds).

### S14 — audit (size M)
- **Scope**: AUD-3, AUD-4 (owner side), EXP-4, SUP-1, PLT-7, PLT-8.
- **Files**: `models/audit_view.py` (event families and one Persian sentence per
  `event_type`; unknown types fall back to «رویداد دیگر»), `controllers/audit.py`,
  `views/web_audit.xml`, `models/support_access.py` (`_inherit = 'ts.emergency.access'`:
  `kind`, `ticket_ref`, overrides of `_check_scope` and `_hours`, `check_identity` on the open
  button), back-office views.
- **Tests**: HTTP: owner sees events of own panel only; another panel's event id → 404;
  filters; export needs re-authentication; support access open → owner notified and listed;
  expired access cannot view.
- **S14b (optional, D4)**: `ir.access` rows with domains for manager read on attempt data;
  the rehearsal must show the back-office ops dashboard still works.

### S15 — portal (size L)
- **Scope**: PRT-1…PRT-5, PRT-7, PRV-1 (share records), PRV-2, ACC-1, ACC-2, ACC-5, ACC-6,
  AUD-4 (participant side); G21; decision D3.
- **Files**: `controllers/portal.py` (override `/my` home on website 4 only; `/my/sharing`,
  `/my/privacy`, `/my/privacy/jobs/<id>`), `views/web_my_home.xml`, `web_my_sharing.xml`,
  `web_my_privacy.xml`, inherited views adding the "who can see this" block to **both** report
  templates (`ts_assessment.report` and the matrix report), `models/consent.py`,
  `models/data_request.py`, share and revoke write consent rows and honour
  `ts_panel.share_max_panels` (active shares only).
- **Tests**: guard portal compare (eot.ir `/my` pages identical); HTTP: home blocks for a new
  user, an invited user, a user with results; sharing page lists panels, revoke and re-share
  work; data export job contains only the user's rows and is not reachable by another user;
  erase request recorded.
- **Risk**: medium-high (stock portal routes are shared with eot.ir: rule 13).

### S16 — minors (size M)
- **Scope**: GRD-1…GRD-4, GRD-7; G7, G8; migration M7; attest mode (owner decision D2).
- **Files**: client age-group rules, campaign and invite attestation, inherited views on the
  two consent pages (`ts_assessment.consent`, `ts_talent.consent`) for the minor wording (new
  consent text version; **the owner approves the Persian text before the ship**), age question
  on the first self-taken consent, result-level step 7.
- **Tests**: ORM: invitation with a minor without attestation refused; consent rows; level
  `status` without guardian consent; HTTP: minor wording shown, adult flow unchanged.
- **Risk**: medium (consent text is a legal text).

### S17 — backoffice (size M) — may run beside S16
- **Scope**: PLT-1, PLT-2, PLT-3, PLT-9, PLT-10; G12.
- **Files**: `ts_panel/views/backend_*.xml`, computed health fields on `ts.workspace`,
  `ts_org/security/ir.access.csv` (operator row on `ts.assignment` removed),
  `ts_org/views/backend.xml` (menu «دعوت‌های سازمانی» restricted to managers).
- **Tests**: ORM: operator cannot read assignments or clients; health counts match; data
  request overdue flag.
- **Risk**: low.

### S18 — lifecycle (size L)
- **Scope**: PRV-3, PRV-4, ORG-7, ORG-8, SEC-6, SEC-7, ACC-3, ACC-4, ACC-10; G22–G24;
  migration M8; decision D7.
- **Files**: `models/retention.py` + cron (ships with `ts_panel.retention_enabled = False`:
  dry-run counts only), erase workflow, panel close and transfer, `ir.http` hook in `ts_panel`
  (website 4 only: staff idle timeout), sessions list and sign-out through the stock
  `res.device` / `res.session` models (read `odoo/addons/base/models/res_device.py` first),
  password-length check on website-4 password forms, notice on `/signup`.
- **Tests**: ORM: each retention rule on aged fixtures, in dry-run nothing is deleted, erase
  leaves usage rows, closed panel permissions (A2); HTTP: idle timeout with a shortened
  setting, sign out everywhere across two clients, transfer and close flows with
  re-authentication; eot.ir login untouched (guard + a login probe on `www.eot.ir`).
- **Risk**: high for the request hook (it runs on every website-4 request; it must be a no-op
  for other websites and for public users). Rehearse with the full guard. Rollback: the hook
  is behind the setting `ts_panel.staff_idle_hours` (0 = off).

### S19 — help-a11y (size M) — may run beside S18
- **Scope**: HLP-2…HLP-4, A11Y-1 full pass, PRT-5 check, G27.
- **Files**: `views/web_help.xml`, help links in pages, fixes found by the audit as inherited
  views or stylesheet edits, trust pages and terms text check (text changes to pages of
  `ts_website` or `ts_org` need those modules in the upgrade list; add them only then).
- **Tests**: headless audit over every route in `03_ia_and_ux.md` for every fixture role at
  1280 and 375 px; HTTP scan for English strings and forbidden words; help pages 200.

### S20 — cleanup (size S)
- **Scope**: remove `ts_org.tpl_workspace` together with its inheritor
  `ts_sms.tpl_workspace_sms`, and `ts_org.tpl_assignment`; the old controller bodies become
  redirects; `org.scss` rules no longer used; inherited views in `ts_panel` that only patched
  old templates are folded into the templates they patch where that module is in this stage's
  list; final `docs` update.
- **Tests**: grep proves no template references the removed ids; all suites green.
- **Risk**: low; done last so a rollback of any earlier stage never needs the old pages back.

## 4. After Phase 2 ("Next", not scheduled)
Care team (R4), pseudonymous display, invitations found by verified mobile, guardian sees the
child's result, co-brand colour, policy-change notice, saved import mappings, low-credit
notification, email as a channel (D8). Paid phase (purchase, gateway, invoices) needs the
owner's decision and the prerequisites in `01_research.md` 2.6.
