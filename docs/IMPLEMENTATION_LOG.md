# Talent Search implementation log

Website 2 in `eot_main` (eot-odoo-prod, 95.38.235.225). eot.ir is website 1 and must stay untouched.
Every stage: rehearse on an `eot_ts*` clone -> `ts guard compare` (eot.ir unchanged) -> tests -> apply live -> guard again.

## Decisions (owner, 2026-09-29)
- Staging host: ts.innerquest.me (DNS via Cloudflare; Let's Encrypt cert on eot-odoo-prod, expires 2026-12-28).
- Invoices under the EOT company (company 1); no separate company; backend shared with eot.
- Install whatever apps are needed; no payment provider, SMS or email setup for now.
- Separate repo: akazemilab/talentsearch_odoo (VPS pushes with deploy key `vps-talentsearch-rw`).
- Remaining open points decided by Claude and recorded below.

## Decisions taken by Claude
- Customer staff (HR, clinicians, directors) and participants are **portal users**; only EOT operators get back-office groups (Talent Search: operations support / instrument curator / platform manager). Keeps customers out of the shared eot backend and off Enterprise internal seats.
- Talent Search CSS lives in its own asset bundle `ts_website.assets_ts`, called only from website-2 layout views; `web.assets_frontend` is never extended (shared with eot.ir). eot.ir's theme assets are already filtered per website by Odoo (theme_* modules).
- All ts_website views and pages are `ir.ui.view`/`website.page` records with `website_id` = website 2 (no generic views).
- Global (website_id NULL) eot.ir course 301s are ignored on website 2 by an `ir.http._serve_redirect` override that only changes behaviour when the current website is Talent Search.
- Stock app side effects on eot.ir found by the guard are reversed in `website._ts_contain_stock_apps` (runs on every ts_website install/upgrade).
- Answer scale verified from the source instance (old sepehrtherapy.ir Odoo, read-only): all 1,340 items are Odoo `scale` questions 1-5; only inventory_012 has anchor labels (بسیار کم / متوسط / بسیار زیاد). Source engine `S09-V3.0-multi-inventory`: reverse = 6 - x, disabled items excluded, every active item must have exactly one answer, each factor score must match exactly one band (inclusive min/max). Source export timestamps are Asia/Tehran (UTC 07:46:53 = Jalali 11:16:53).
- Clinical interpretation texts stay draft until re-approved by a named clinician (approver in source is the test account "PSY TEST - Manager").

## Stage 1 - foundation (in progress)
### Rehearsal 1 (eot_ts1): stock apps only
- `-i survey,crm,helpdesk,account` -> 57 modules added (not the 151 statically estimated in Phase 0), ~2 min, no errors.
- Guard found eot.ir side effects:
  - website_helpdesk publishes demo team "Customer Care" on website 1 -> "Help" menu item on 1,048 eot.ir pages.
  - website_helpdesk generic page `/your-ticket-has-been-submitted`.
  - website_crm creates a website-1 copy of `website_crm.contactus_form` (pre-fills form values from URL params; no visible change).
  - website 1 record: only new empty columns (crm_default_team_id/user_id).
  - 12 new ir.config_parameter keys (additive).
- Fixes: containment step in ts_website; guard v2 ignores added columns, compares form markup strictly, and fails on eot.ir sitemap changes.

### Rehearsal 2-3 (eot_ts2, eot_ts3): apps + ts_core + ts_website
- Found and fixed:
  - theme_eot_custom's global controllers (/privacy, /courses, /your-ticket-has-been-submitted, /my/psychological-results) fired on website 2 -> theme_* modules dropped from website 2's routing map.
  - `_UNSLUG_RE` import path (500 on unknown TS URLs).
  - Odoo 20 does not pass `t-set` from a `t-call` body -> inner heroes were empty; params now passed as attributes.
  - Desktop menu hidden by `<details>`; mobile menu replaced by button + aria-expanded (plain JS bundle, `@odoo-module ignore`).
  - Headings fell back to "Inter Tight"; hero text under the decorative circle (contrast); English 404 title and skip link.
  - `website.menu_id` stale after website creation (install failure).
- Rehearsal 3 (fresh, final code at that time): eot.ir /contactus 200 -> 500 again. Cause: Odoo copies new inheriting views onto website 1 at the END of loading, after ts_website's setup. Fix: containment also runs from an `ir.ui.view._create_all_specific_views` override.
- Stage 1 tests: 29/29 pass (tenant/purpose isolation, portal denials, audit immutability, gating, pipeline separation).
- Lead form (server-side test on clone): missing consent -> error; valid -> lead in Talent Search team, stage «درخواست ورودی», HTML escaped, audit event; missing CSRF -> 400.

### Rehearsal 4 (eot_ts4, fresh, final code) - PASS
- eot.ir UNCHANGED (1,072 pages + forms + sitemap + all existing website-1/generic rows); website_crm copy contained (inactive).
- All 13 Talent Search pages 200 on website 2; /masnavi, /courses -> Persian 404; unknown host -> eot.ir; 29/29 stage tests.

### LIVE (eot_main), 2026-09-29 06:35-06:48 UTC - PASS
- `tools/prod/ts_ship.sh install survey,crm,helpdesk,account,ts_core,ts_website s1`
- /etc/odoo20.conf addons_path += /opt/odoo/talentsearch/addons (backup next to the file).
- Backup: /var/backups/odoo/eot_main_pre_ts_s1_20260929-0635.dump + filestore tgz.
- odoo20 stopped 06:40:28 -> started 06:42:42 (eot.ir downtime ~2 min 20 s); install rc=0.
- Live guard: **eot.ir UNCHANGED** (1,072 pages, forms, sitemap, existing rows).
- Website 2 = db id 4 (xmlid ts_website.website_ts), https://ts.innerquest.me (nginx upstream -> 8069, noindex header).
- Rehearsal clones dropped (pg/fs/proc all 0).

### 2026-09-29 owner decisions (10:32 local)
- All 33 contract-bearing instruments, their scoring rules, interpretation texts (participant and clinician), and the privacy/consent texts are approved by the owner (EOT). Recorded as `TS-OWNER-APPROVED-1405-07-07`, approver = platform admin. The texts claim no psychometric reliability, validity or norms, because the source records none.
- The owner authorised fixing the eot.ir problems caused by the shared instance in theme_eot_custom.

### Incident 2026-09-29 ~07:20 UTC (live, contained)
- `ts sync` wrote unshipped code into the LIVE addons dir. A theme ship then restarted odoo20 on that code, and the upgrade failed: UnboundLocalError `IMD` in `_ts_contain_stock_apps`.
- Live TS code was restored to ed70629 and odoo20 restarted. eot.ir /, /contactus and /web/login stayed 200.
- Fixes:
  - The IMD bug.
  - Rehearsals now use /opt/odoo/talentsearch_stage.
  - `ts_ship.sh` alone copies stage to live, keeping the previous copy and restoring it on failure.
  - Rehearsal baselines are served on the live code.

### Stage 2: assessments + organizations (rehearsals r6-r9)
- ts_assessment: 36 source instruments. 33 are published (locked versions, exhaustive band validation); 3 are retired (no contract).
  - Golden parity against an independent re-implementation of S09-V3.0: 198 attempts, compared at the stored 4-decimal precision.
  - Duplicate base title (inventory_003/004): the title and URL now carry the item count.
- ts_org:
  - Invitations by copyable link (no email/SMS).
  - Participant opt-in sharing, revocable from the report.
  - Employment workspaces see only the band per factor. Clinical workspaces show the full report with clinician texts, and only to verified clinicians.
  - Operations dashboard and a clinician verification queue.
  - Employment-eligible instruments: adult + استعدادیابی/خودشناسی/مسائل شغلی.
- Trust/privacy/consent pages:
  - Drafts replaced by «نسخهٔ ۱، لازم‌الاجرا از ۷ مهر ۱۴۰۵؛ تأییدشده توسط EOT».
  - Claims that did not match the product were removed: reference group, reviewer signature before release, support-access workflow, minors path "not active".
- eot.ir fixes:
  - Stage 1 had added stock portal cards ("Invoices to pay", payment methods, ...) and an e-invoice selector to eot.ir's signed-in /my. They are now scoped to website 2, and eot.ir /my, /my/home, /my/account and /my/security are identical to the pre-Talent-Search text.
  - Theme: retired-URL redirects answer only on website 1, and the contact form hook is kept. Branch ts-isolation was rehearsed (1,067 routes, only the 3 pre-existing English article titles flagged), shipped live 08:2x UTC and merged to main.
- Headless layout audit (tools/vps/ts_shot.py) found two issues, both fixed:
  - Odoo's menu-autohide script threw on every website-2 page because header#top had no .top_menu.
  - The dashboard table's visually-hidden header widened the page by 17px at 375px.
- r8 results:
  - Guard: eot.ir UNCHANGED (1,072 pages).
  - Tests: stage 29/29, assessment 35/35, HTTP participant 24/24, org 32/32, HTTP org 27/27.

### LIVE stage 2 (eot_main), 2026-09-29 08:39-08:50 UTC - PASS
- Rehearsal r9 (final code): guard eot.ir UNCHANGED; eot.ir /my, /my/home, /my/account, /my/security identical to pre-TS; tests 29/29, 35/35, 24/24, 32/32, 27/27; headless layout audit clean at 1280/375 + print.
- `ts_ship.sh ts_assessment,ts_org ts_website s2`: backup /var/backups/odoo/eot_main_pre_ts_s2_20260929-0839.dump; previous live code kept at /opt/odoo/talentsearch_prev_s2_20260929-0839; install rc=0; odoo20 down 08:44:27-08:44:58.
- Live guard: **eot.ir UNCHANGED** (1,072 pages). Live: 33 published (10 employment-eligible, 23 personal), 3 retired; website-2 portal cards scoped.
- Theme ts-isolation shipped to live earlier the same hour (`eot ship`, verify OK, 1,067 routes) and merged to main (0905f7f).

### LIVE fix s3, 2026-09-29 09:13-09:32 UTC - «سنجه‌های من» card hidden
- Symptom (owner): no «سنجه‌های من» on signed-in /my. Cause: Odoo renders a portal card with `d-none` unless it is a config card or has a counter; the card had neither. The test only checked that the text was in the HTML.
- Fix: `PortalEntry._filter_visible_portal_cards` shows website-2 cards without a counter; the header has a «سنجه‌های من» link for signed-in users; `ts_http_flow` now asserts the card has no `d-none` (and that the workspace card is hidden for a non-member).
- Rehearsal r10: guard UNCHANGED, eot.ir /my pages identical to pre-TS, tests 29/35/26/32/27 all pass. Ship: `ts_ship.sh '' ts_website s3` (backup /var/backups/odoo/eot_main_pre_ts_s3_*).
- Guard: the upgrade cascades to ts_assessment/ts_org and re-saves their 16 backend views (models ts.*); the guard reported them as changed. They never render on a website, so the guard now excludes `ts.*` backend views. Re-compared against the pre-ship snapshot: 1,072 pages, eot.ir UNCHANGED.

### Unresolved gates carried forward
- Norms/psychometric evidence do not exist in the source; reports say so and use contract bands only.
- No payment provider, SMS or outgoing email (owner decision, not needed now).
- talentsearch.ir DNS cutover: owner decision.

## SMS (Kavenegar) - 2026-09-29
Owner asked for the whole Kavenegar REST API inside Odoo's native SMS model, token entered at the end.
Answers: shared module (ts_kavenegar, not in theme_eot_custom), token in Settings, webhooks on ts.innerquest.me,
flows = assignment invitations, result-ready notice, phone OTP. Built ts_kavenegar + ts_sms, rehearsed on eot_ts11/eot_ts12
clones with fake Kavenegar (51/51 gateway, 8/8 webhooks, 30/30 flows; eot.ir UNCHANGED, 1,072 pages).
Shipped live 11:44-11:54 Tehran-time-of-server as `sms1` (backup eot_main_pre_ts_sms1_20260929-1144.dump); live guard: eot.ir UNCHANGED.
kv_enabled is OFF: nothing is sent until the owner enters the API key in Settings -> SMS -> Kavenegar and ticks Send SMS via Kavenegar.

## 2026-09-29 - interactive talent inventory (ts_talent), branch talent-inventory
Built ts_talent (matrix engine, field/cell models, 5-screen taking flow, 7-level report, catalog/detail extensions) and the historical-import tooling. Rehearsed on eot_ts11/12/13 clones: eot.ir UNCHANGED (1,072 pages, /my portal identical), engine 44/44, ORM 38/38, HTTP talent flow 36/36, old suites green after excluding the matrix instrument from source-instrument counts.

## 2026-09-30 - انتخاب رشتهٔ ۱۴۰۵ (branch entekhab-1405)
Owner decisions (8 Mehr 1405): counselor-first channel; the 114 imported results visible to the institute's members (workspace 1) but still unreleased to participants, no messages; free this season.
Built: (1) ts_core - `ts.workspace` owner approval (`approved_by_id/approved_on/approval_note`, `action_approve()` manager-only, audit `workspace.approve`; `gated` = education/benefits AND not approved). (2) ts_org - education `visible_results` level `education` for owner/counselor (`EDU_ROLES`), `ts.attempt.ts_org_visible_to(member)` (imports of the same workspace, or a shared assignment), workspace page lists imported results with source filter. (3) ts_talent - "زمینه‌ها کنار هم" section (`compare_rows/field_cards/compare_lines`), `report_ctx()` shared by participant and institute view (`/my/workspaces/<ws>/p/<attempt>`, audited `attempt.result_view`, co-brand line, no raw answers), default fields 3 -> 4 (loader updates the live version's `field_default`; content hash unchanged), landing `/entekhab-reshteh` and fictional `/entekhab-reshteh/sample` (website 4 only, 404 on eot.ir).
Tooling fix: the rehearsal harness/tests still used the old staging host `ts.innerquest.me`; after the talentsearch.ir cutover website 4's domain is `https://talentsearch.ir`, so hosts in tools/ were switched (website.xml data stays noupdate). New `tools/prod/ts_http_edu.py` (16 checks) is run by `ts_rehearse.sh`.
Rehearsal eot_ts14: eot.ir UNCHANGED (1,049 pages) + portal UNCHANGED; stage1 29/29, assessment 35/35, participant flow 26/26, engine 44/44, talent 53/53, talent HTTP 43/43, org 32/32 + HTTP 27/27, edu HTTP 16/16, SMS 30/30, webhooks 8/8. Known unrelated: `tests_kavenegar` "inbox stored 2 messages" counts every inbound row in the clone, which now includes real rows from prod (test assumes an empty inbox).
Data step (owner-only, NOT in code): approve workspace 1, set pilot, add the counselor portal user as member.

## er3 — Kavenegar line dropdown (2026-09-30)
- `kv_sender`/`kv_inbox_line` are now Selections fed by `res.company.kv_lines`. Kavenegar has no API listing lines (30 endpoints probed -> 404), so lines are discovered from latest outbox senders, account default sender, stored messages; refreshed by "Fetch lines" and by Test connection.
- Live: kv_sender set to 90008956 (the account's actual line). Known quirk: discovery also lists '1' and '100010' (from stored inbound receptors); filter short values in a later change.
