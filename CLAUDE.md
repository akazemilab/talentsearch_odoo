# talentsearch_odoo - working rules

Talent Search (talentsearch.ir) by EOT = **website 2** (xmlid `ts_website.website_ts`,
db id 4) inside `eot_main` on eot-odoo-prod, next to eot.ir (website 1, theme
`theme_eot_custom`, repo akazemilab/theme_eot_custom). Staging host: ts.innerquest.me (before the 2026-09-29 cutover; website 4's domain is now https://talentsearch.ir and the test tools use that host).
Read theme_eot_custom's CLAUDE.md too: its Odoo 20 pitfalls apply here.

## Hard rules
- Never modify eot.ir: no website-1 or generic view/page/menu/redirect edits, no theme
  changes, no deploys/merges in theme_eot_custom, no eot.ir DNS. The live
  talentsearch.ir DNS is also out of scope.
- ts_* modules must NOT depend on theme_eot_custom: `-u theme_eot_custom` would then
  also upgrade ts modules and couple the two deploy paths.
- Every install/upgrade: `ts_rehearse eot_tsN MODULES` (fresh clone -> eot.ir
  baseline -> install -> `ts_guard compare` -> stage tests) BEFORE
  `tools/prod/ts_ship.sh` on eot_main. Guard verdict must be "eot.ir UNCHANGED".
- Tests that create records run only on eot_ts* clones (scripts assert it).
- Theme exception (owner, 2026-09-29): eot.ir problems caused by the shared
  instance may be fixed in theme_eot_custom (branch `ts-isolation`), rehearsed with the
  theme's own `eot` toolkit and shipped with `eot ship`; never mixed into a ts ship.

## Workflow
Source of truth is /root/talentsearch_odoo on the VPS (pushes with deploy key
`vps-talentsearch-rw`); the cloud session can read the GitHub repo but cannot push.
`ts sync` rsyncs to the STAGING dir /opt/odoo/talentsearch_stage on prod; every
rehearsal, clone, test and guard runs from there. Only `ts_ship.sh` copies stage ->
LIVE /opt/odoo/talentsearch (the dir in odoo20's addons_path), after stopping odoo20,
keeping /opt/odoo/talentsearch_prev_<label>_<ts> and restoring it if the install
fails. (2026-09-29 incident: `ts sync` used to write the live dir, so a theme ship
restarted odoo20 on unshipped code and failed.) Rehearsal baselines serve the clone
on the LIVE code (`TS_CODE=/opt/odoo/talentsearch`), because the stage may already
hold newer code that the old clone DB cannot run. Long jobs: `ts bg NAME CMD`,
`ts job NAME`. Clones are served on :8071; nginx `ts-innerquest.conf` upstream
`ts_odoo` points ts.innerquest.me at 8071 (clone review) or 8069 (live).

## Multi-website isolation facts (each one found by the guard)
1. Stock app installs change eot.ir; `website._ts_contain_stock_apps` reverses them
   on every ts_website install/upgrade:
   - website_helpdesk publishes its demo team on the company website (website 1)
     and adds a "Help" menu (`/helpdesk`) to every eot.ir page.
   - website_helpdesk ships a generic page /your-ticket-has-been-submitted.
   - website_crm creates a website-1 copy of `website_crm.contactus_form` whose
     xpath (`contactus_form_values`) is missing from eot.ir's redesigned contact
     page -> eot.ir /contactus 500. Install-generated website-1 copies of
     website_crm/helpdesk/survey/payment views are deactivated.
2. Python controllers are global. theme_eot_custom's redirects (/privacy,
   /courses, /your-ticket-has-been-submitted, /my/psychological-results) would
   fire on website 2. `ts_website.ir_http._generate_routing_rules` drops theme_*
   modules from website 2's routing map (Odoo keeps one map per website).
3. Global (website_id NULL) 301 rewrites for eot.ir course short links: website 2
   honours only its own rewrites (`_serve_redirect` override). A `404`-type rewrite
   does NOT shadow them: `_serve_redirect` only looks at 301/302.
4. Talent Search CSS/JS are in their own bundles (`ts_website.assets_ts`,
   `ts_website.assets_ts_js`) called from website-2 layout views; never extend
   web.assets_frontend (shared with eot.ir). Theme assets are already per-website.
5. All ts_website views/pages are records with `website_id` = website 2. The guard
   fails on any generic `ts_*` view.

## Odoo 20 pitfalls (new here)
- Access rights: `security/ir.access.csv` (model `ir.access`), columns
  `id,name,model_id,group_id/id,operation,domain`; operation is a subset of
  "crud"; a row with a group grants, a row without one restricts everyone.
- Groups use `privilege_id` -> `res.groups.privilege` (with `category_id`); users'
  groups field is `group_ids`. SQL constraints: `models.Constraint(...)`.
- QWeb: `t-set` inside a `t-call` body is NOT passed to the callee. Pass params as
  attributes: `<t t-call="x" title.f="..."/>` (static) or `title="expr"`.
- `website.menu_id` is computed and stale right after `website.create()` in the same
  transaction; search `website.menu` (website_id, parent_id=False) instead.
- `website.menu.url` is computed from column `manual_url`; `website.page.url` is a
  translatable jsonb; page publish field is `website_published`.
- `_UNSLUG_RE` lives in `odoo.addons.http_routing.models.ir_http`.
- Every bundled JS file becomes an `odoo.define` module; a standalone script needs
  `/** @odoo-module ignore **/`, and `defer_load` on a custom bundle never ran it.
- A closed `<details>` hides its content regardless of CSS (and Odoo's page JS
  interfered): use a button with aria-expanded + a few lines of JS.
- Odoo's heading font rule beats `#wrapwrap` body font: set font-family on h1-h6,
  buttons and form controls explicitly.
- The core skip link (`a.o_skip_to_content`, "Skip to Content") and the 404 page
  are English; website-2 views replace them (404 title via t-set BEFORE the t-call).
- Installing survey+crm+helpdesk+account adds 57 modules (localizations are filtered
  by company country; a static manifest walk wrongly predicted 151).

## Source data facts (assessments)
Exports came from the old sepehrtherapy.ir Odoo (read-only via the `odoo` connector):
x_psy_* models, engine `S09-V3.0-multi-inventory` (server action 1290): answers are
Odoo `scale` 1-5, reverse = 6 - x, disabled items excluded, every active item must
have exactly one answer, each factor score must match exactly one band (inclusive).
Only inventory_012's questions carry anchor labels (بسیار کم / متوسط / بسیار زیاد).
Export timestamps are Asia/Tehran. Clinical texts' approver is a test account -> draft.
Factor codes are not globally unique (factor_073, factor_098): key by (inventory, code).

## Organizations and clinicians (ts_org)
- `ts.assignment` = one invitation (workspace, instrument, invitee). No email/SMS is
  sent: the member copies the link `/invite/<token>`. The participant signs in,
  accepts (sharing opt-in, default checked, revocable from the report) and takes the
  attempt through the normal player; the attempt carries `workspace_id`.
- Visibility (`visible_results`): employment -> reviewer/hr/hiring roles see only the
  band per factor (no scores, answers or texts) when share_level=summary; clinical ->
  only verified clinician/clinic_director see the full report with therapist texts.
  Nobody in a workspace has ACL on attempts/answers/results: controllers read with
  sudo after the membership check. Portal users have no ACL on ts.assignment.
- Employment-eligible instruments: `EMPLOYMENT_CATEGORIES` in ts_assessment/loader.py
  (adult + استعدادیابی/خودشناسی/مسائل شغلی), owner rule TS-OWNER-APPROVED-1405-07-07.

## SMS (Kavenegar) - modules ts_kavenegar (generic) and ts_sms (Talent Search flows)
- `ts_kavenegar` (depends only on `sms`, `phone_validation`) is the native Odoo 20 gateway: `res.company._get_sms_api_class`
  returns `SmsApiKavenegar` (tools/sms_api.py) when `kv_enabled`, exactly how stock `sms_twilio` plugs in. Every native
  SMS (chatter, templates, mass SMS, automations, composer) therefore goes through Kavenegar. Same body -> `sms/send`
  (localid = sms uuid per receptor); different bodies -> `sms/sendarray`; chunks of 200; limits 1800 (4000 messenger) chars.
- Full REST coverage lives in `tools/kavenegar.py` (send, sendarray, status*, select, outbox, cancel, inbox, blocked, verify lookup +
  template CRUD, TTS call, account info/config, media, getdate). Error codes map to Odoo `failure_type` (added `kv_*` types on
  `sms.sms` and `mail.notification`).
- API key: company field `kv_api_key` (groups=base.group_system), typed by the owner in Settings -> SMS -> Kavenegar. Never in
  chat, code, logs or the message log. `ts_kavenegar.api_base` (ir.config_parameter) overrides the API base URL: tests point it at a
  local fake server; empty in production.
- Webhooks (payload format is NOT in rest.html; parser accepts query/form/JSON): `/kavenegar/<secret>/status` and
  `/kavenegar/<secret>/inbound`. They answer only on website 2 (404 on eot.ir even with the secret). Cron polling (status every
  10 min, inbox every 5 min) covers a missed webhook. Secret is generated in Settings and can be rotated.
- `kavenegar.message` = log of every outgoing/incoming message (status, cost, parts); native `sms.tracker`/notifications are
  updated from Kavenegar statuses (`_kv_sync_native`). OTP/secret texts are masked (`***`) in the log (`sms.sms.kv_secret`).
- `ts_sms` (Talent Search): invitation SMS (only with a valid mobile AND the org's consent tick), result-ready SMS (only a link,
  never result text; only for users who verified a mobile and opted in), `/my/phone` mobile verification (OTP: 6 digits, 5 min,
  5 attempts, 60 s cooldown, 5 per hour per user and per number, hashed with per-code salt). Everything is a no-op until
  `kv_enabled` is ticked, and the invite hint text on the workspace page switches accordingly.
- Tests: `tools/prod/tests_kavenegar.py` (fake session), `ts_http_kv.py` (webhooks), `ts_http_sms.py` (flows with a fake local
  Kavenegar server); `ts_rehearse` runs them when `ts_kavenegar` / `ts_sms` are in the module list. Real sends are never made
  by tests; the first real send happens only after the owner enters the key and says so.
- Pitfall: `dict.setdefault` does not replace an existing None value (default sender was skipped); use `get(k) or default`.


## Going live on a domain (learned 2026-09-29, talentsearch.ir)
Use `ts domain`, never hand-typed certbot/nginx/psql:
- `ts bg dom "ts domain cutover DOMAIN --website ID --from-domain https://old.host --wait 900"` then `ts job dom`.
  Gate = authoritative-NS DNS is DNS-only (grey cloud) for apex AND www; it names the record that is still proxied.
  Then certbot (idempotent) -> nginx conf (backup, `nginx -t`, auto-restore) -> website.domain + kv_webhook_base
  with preconditions -> odoo20 restart -> verify. `ts domain check DOMAIN [--website ID]` is the read-only verify.
- website.domain is ormcache'd: a DB update alone keeps serving website 1's homepage on the new host until odoo20 restarts.
- Never trust the VPS resolver right after a DNS change (it kept returning Cloudflare IPs); the tool uses `curl --resolve` to this server.
- Website 1 / eot.ir is refused by the tool. Canonical = apex, www 301s to it. Keep records grey unless SSL mode is Full (strict).
- Robots: Odoo's stock robots.txt emits an http:// Sitemap line (proxy_mode off) - stock behaviour, also on eot.ir; not changed.

## Interactive talent inventory (ts_talent)
- Instrument `TALENT-INV-15` (matrix mode): the participant WRITES 2-8 fields and answers the same 15 statements per field (5-point). Scale = sum of 3 items /15*100 (20-100); item i -> scale (i-1) mod 5 (ANA, EXP, ACA, NOV, DUT); composites are plain means of scales (TOT, INT, ACT, CRE, SCH, CRT, CRP). Engine `models/engine_matrix.py` is pure (golden tests `tools/prod/tests_talent_engine.py` run anywhere).
- Answers live in `ts.attempt.field` / `ts.attempt.cell`, results in `attempt.profile_json` (see spec §9). Controllers subclass `TsAssessment` with `@http.route()` (no args) to reuse the base routes.
- Stored item text is verbatim from the book; «این زمینه» is replaced by the field name only at display time.
- Old source-instrument tests must exclude `TALENT-INV-15` (33 source instruments; the catalog shows 34).
- Flow tests reuse password files `/root/.ts_flow_<DB>_*` on prod: a re-used clone name carries stale files; `ensure_user` now upserts the user every run.
- Historical import: dry-run first (`TS_IMPORT_XLSX=... < ts_import_talent.py` in odoo shell), counts only, never print rows. The export never lives in the repo; use a 700 directory and delete it afterwards.

## Panels, sign-in and responsible specialist (stages 1-5, 2026-09-30)
- Two-mode signup: `/signup` (mobile OTP, ts_sms) and `/panel` -> `/my/workspaces/new` (ts_org). A panel is a `ts.workspace`; education is active at once, employment/clinical start as `state='pilot'` + `gated` until `action_approve()` (members may build and invite colleagues; `ts.assignment` creation is refused while gated). `GATED_PURPOSES = {employment, clinical, benefits}`.
- Who sees a participant: owner/`hr_admin`/`clinic_director`/`reviewer` see all, others only what they are responsible for (`member.can_see`); the unassigned queue is visible to owners/managers and, in education only, to counselors. When a member is deactivated, deleted or loses a responsible role their clients go back to the unassigned queue (audited) - nothing disappears.
- Colleague invites (`ts.member.invite`) are bound to one verified mobile (`res.users._ts_verified_phones()`, filled by ts_sms from `ts_phone`) or email; the link is always shareable, no SMS is sent. Self-taken results reach a counselor only through `ts.assignment.ts_share_attempt` (panel code + explicit confirm).
- `ts.usage.event` records one row per completed workspace attempt; nothing is deducted (next phase).
- `ts.emergency.access` is a procedure (reason >= 15 chars, 24 h, owner notified, audited), not a technical lock: platform managers still have read ACLs on clinical data.
- Gotchas found while building: Odoo 20 Binary fields need `base64.b64encode(x).decode()`; a `<p>` between a `t-if` and its `t-else` 500s the page (ORM suites never render templates - run the HTTP suite); `ts db stop` drops the clone database; new test phone numbers must not collide across suites (`ts_http_signup.py` owns 09127770001).

## Toolkit workflow (2026-10-01; measured on two parallel full rehearsals)
- Before any rehearsal: `ts check` (2 s). It catches the two failures that each cost a full cycle on 2026-09-30: a `t-else` that does not follow its `t-if` (page 500) and a NEW view in a module that does not depend on `website` (install fails).
- Rehearse: `ts bg NAME "bash /root/talentsearch_odoo/tools/vps/ts_rehearse.sh DB INSTALL UPGRADE"`, then poll with `ts wait NAME 50` (returns early only on FAIL / `!!` / verdicts / the end) or `ts status NAME`. The last line is `REHEARSAL DB slot N: guard ..., portal ..., unexpected failures: N`; known failures live in tools/vps/known_failures.txt.
- Timings: full rehearsal 28 min -> 12 min. Guard snapshots/compares fetch pages in threads (4 on clones, 2 on live port 8069), and the non-committing ORM suites run beside the guard compare. Ship live baseline 5 -> 3 min.
- Fast iteration on one clone: `ts db reload DB MODS` (halt + upgrade + serve, DB kept), `ts test DB file...`, `ts db errors DB` (condensed tracebacks of the clone server). `ts db halt` stops the server only; `ts db stop` = drop.
- Ship: `ts ship INS UPG LABEL` (refuses uncommitted changes, a failing preflight, a running ship, odoo20 restarts in the last 3 min; holds slot 0; mirrors the prod log into job ship_LABEL; ends with `ts live` and writes /root/ts-jobs/LIVE_COMMIT). `TS_SHIP_DRY=1 ts ship '' ts_core dry1` exercises everything except backup/install (live baseline only).
- Parallel: `ts wt 1 BRANCH` creates /root/ts_wt_s1; `TS_SLOT=1 ts bg ...` rehearses it on port 8073, stage /opt/odoo/talentsearch_stage_s1, fake SMS ports +10, its own lock. Rules enforced by the tools: one ship at a time and it owns slot 0 (no sync of stage during a ship); at most 2 rehearsals at once and only 1 while a ship runs (4 cores, load ~6 with two); a clone server cannot take a port held by another clone; no serve below 1.5 GB free RAM; ship dumps are written as .part so a parallel `ts db clone` never restores a half-written dump. Clone names must differ between slots. `ts slots` shows who holds what.
- `ts clean` lists leftovers (unserved clones, old prev code dirs, old guard snapshots/logs); `--yes` removes them. `ts push` never stages untracked files or __pycache__ (now untracked, in .gitignore).
