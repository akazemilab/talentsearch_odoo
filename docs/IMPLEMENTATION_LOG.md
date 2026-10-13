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

## resp1 — responsible specialist (stage 1 of the two-mode signup work, 2026-09-30)
- `ts.assignment.responsible_id` and `ts.attempt.responsible_id` (imports only) -> `ts.workspace.member`; constraint: same workspace, active, role in INVITE_ROLES, never the participant themselves. Every change writes `assignment.responsible_change` / `attempt.responsible_change` (old/new member ids).
- Visibility (`ts.workspace.member.can_see`): owner, `hr_admin`, `clinic_director`, `reviewer` see everything; other specialists only what they are responsible for. Unassigned queue is visible to owner/managers everywhere and to counselors in education only. Applied in `visible_results`, `ts_org_visible_to`, workspace list/counts and the assignment/report routes (404 otherwise).
- Default: the inviter is responsible if they are a specialist; an owner only while they are the only member; owner accepting their own invite drops the self-responsibility (unassigned).
- UI: workspace page has "تخصیص‌نشده" and "مسئولیت من" filters and a per-row dropdown (owner/`hr_admin`/`clinic_director` only, POST `/my/workspaces/<id>/{a|p}/<id>/responsible`). The 114 imported results stay unassigned until the owner hands them over.
- NOT changed: `GATED_PURPOSES` is still `{'education','benefits'}` (the brief assumed the opposite; changing it would ungate workspace 1, so it waits for stage 3 and the owner's decision).
- Tests: `tools/prod/tests_org_resp.py` (22), `tools/prod/ts_http_resp.py` (12), both run by `ts_rehearse.sh`; `tests_org.py` clinical fixture now assigns the clinician (unassigned clinic results are hidden from clinicians by design).
- Rehearsal eot_ts13: eot.ir UNCHANGED (1,050 pages) + portal UNCHANGED; stage1 29/29, assessment 35/35, participant flow 26/26, engine 44/44, talent 56/56, talent HTTP 43/43, org 32/32 + HTTP 27/27, edu HTTP 17/17, responsible 22/22 + HTTP 12/12. First rehearsal caught a 500 (union of two models in the controller) before ship.
- Leftover clone server `eot_ts_kv1` held port 8071; its process was stopped, its database was not dropped.

## sgn1 — mobile sign-in + hardened invites (stage 2, 2026-09-30)
- `ts_sms`: `/signup` (mobile -> 6-digit code -> session login; new users get name step), models `ts.signup.otp` (5/hour/phone, 20/hour/IP-hash, 60 s cooldown, 5 attempts, 5-minute TTL, Persian digits accepted) and `ts.login.token` (single-use, 120 s) consumed by a custom `res.users._check_credentials` type `ts_phone_login`. `next` is validated (`//`, backslashes, newlines rejected). Audit `account.signup_phone` / `account.login_phone`. Works only when Kavenegar + OTP are on; otherwise the old email flow is untouched.
- `ts_org`: invites expire after 30 days (`invite_state()`: ok/expired/used/declined/withdrawn, each with its own message); invite page offers mobile sign-in and uses education wording for schools.
- Tests: `tests_signup.py` 27, `ts_http_signup.py` 22 (fake Kavenegar on :18098). Test fix: OTP-expiry test now edits the row through the ORM (raw SQL hit a format mismatch).
- Rehearsal eot_ts13 + ship `sgn1`: eot.ir UNCHANGED (1,050 pages) both on the clone and live; live /signup 200, eot.ir /signup 404; only journal errors were harmless `.map` asset requests.

## pnl1 — self-service panels + share with counselor (stages 3 and 4, 2026-09-30)
- `GATED_PURPOSES` is now `{'employment','clinical','benefits'}`: education panels are live at once; organization/clinic panels start in «pending approval» = `state='pilot'` + `gated` (owner can build the panel, invite colleagues; `ts.assignment` creation for real participants is refused until `action_approve()`). Workspace 1 (education, already approved) and workspace 2 (closed) are unaffected.
- `ts.workspace`: `terms_version/terms_accepted_on/terms_accepted_by_id`, `rejected_on/rejection_note`, `owner_user_id`; `action_reject/suspend/resume` (manager-only, audited: `workspace.reject|suspend|resume`); pending-approval queue menu for platform managers; `_notify_review()` posts an internal message to managers on every new gated panel; the last active owner can be neither deactivated nor deleted.
- `ts_org`: `ts_panel_create` (kinds school/org/clinic/solo, terms + clinical-escalation acceptance, max 3 panels/day per person, audit `workspace.self_create` + `workspace.terms_accept`), `ts_update_profile` (name + PNG/JPEG/WEBP logo < 512 KB, decodability checked), `ts.member.invite` (locked to ONE verified mobile or email, 7-day expiry, max 20 pending, revocable, shareable `/join/<token>` link; no SMS is sent for colleague invites), `ts.usage.event` (one row per completed workspace attempt, unique per attempt; nothing deducted or blocked; self-taken attempts have no workspace so no event).
- Routes: `/panel` (landing), `/panel/terms` (version `panel-terms-1405-07-v1`), `/my/workspaces/new`, settings, member invite/revoke, `/join/<token>`; workspace page gets the pending banner (+ rejection note), setup checklist, members + invites, name/logo form. The old "request a workspace via /contact" text is gone.
- Stage 4: homepage hero is «پنل بساز» (→ `/panel`) + «فقط می‌خواهم آزمون بدهم» (→ `/assessments`); after a finished self-taken result the participant can send it to ONE education panel by its code (`/my/assessments/<id>/share` -> confirm page showing the panel name -> `ts.assignment.ts_share_attempt`: a normal accepted summary-level assignment, so unshare, visibility and the responsible-counselor rules are the same as for an invited result; audit `assignment.self_share`; bands only, never answers). Older results stay private unless the participant sends them.
- Chores: Kavenegar line discovery drops values shorter than 7 digits (`1`, `100010`); invite menu label for TALENT-INV-15 is now «۱۵ جمله برای هر زمینه». Competitor pricing: no public price claim was made, so no live check was needed.
- Tests: `tests_panel.py` 68 (ORM), `ts_http_panel.py` 51 (HTTP, incl. homepage CTA + share flow + eot.ir isolation), fixtures of older suites now set `approved_on` for employment/clinical. Rehearsal eot_ts16: eot.ir UNCHANGED (1,050 pages) + portal UNCHANGED; all suites green except the two known `inbox` Kavenegar tests (clone holds real inbound rows). Ship `pnl1`: eot.ir UNCHANGED live; /panel 200, www.eot.ir/panel 404.
- Not done on purpose: SMS/email delivery of colleague invites (link only), multiple simultaneous shares of one self-taken result (one panel at a time).

## edg1 — edge cases (stage 5, 2026-10-01)
- A specialist who is deactivated, deleted or moved to a non-responsible role releases their clients: `responsible_id` on assignments and imported attempts is cleared (audited by the records' own `*.responsible_change` events), the leaver loses access at once, owners/managers still see everything and hand clients on from the «تخصیص‌نشده» queue. Nothing disappears, no access lingers.
- Panel switcher: a person in several panels sees «تغییر پنل» links on each panel page; data stays per panel (an independent counselor's private clients never show in the institute panel; responsibility across panels is refused by constraint).
- `ts.emergency.access` (model in ts_core, views/menu in ts_org because ts_core cannot declare new views on a database that has `website`): platform manager, clinical panels only, reason >= 15 characters, 24 hours, owners notified, audits `emergency.open|view|close`. It is a procedure with a trail, NOT a technical lock - managers keep their read ACLs on clinical data; enforcing it with record rules is a separate decision.
- Terms text now covers "when a specialist leaves / client transfer" (no automated transfer between panels; a client appears in a new panel only by sending it again or accepting an invite) and emergency access; `TERMS_VERSION` is `panel-terms-1405-07-v2` (v1 never shipped to users).
- Tests: `tests_edge.py` 25 (ORM); `ts_http_panel.py` 53 now checks the switcher and terms wording. Rehearsal eot_ts17: eot.ir UNCHANGED (1,050 pages); the first run failed at install on the ts_core view (caught before ship); the signed-in portal comparison was redone on clone eot_ts18 with live code as baseline -> UNCHANGED (360 lines, signed-in 303). Ship `edg1`: eot.ir UNCHANGED live, /panel 200, www.eot.ir/panel 404.
- Decisions left for the owner: (1) record rules to make emergency access a real lock on clinical data; (2) whether `benefits` panels are ever offered; (3) approving the first real organization/clinic panels from the pending queue; (4) legal review of the terms text; (5) whether colleague invites should also go out by SMS (link only today).

## tools1 — toolkit review after stages 1-5 (2026-10-01)
- Review of the stage 1-5 session: ~60 blind polls, ~25 manual ssh tails of ship logs, 7 ad-hoc helper scripts, and about 6 lost cycles (QWeb t-else 500, ts_core view install failure, `ts db stop` dropping a clone, empty argument lost by `$*`, portal compare signed out, test phone collision).
- New commands: `ts check`, `ts wait|status`, `ts test`, `ts db reload|halt|errors`, `ts ship` (ts_shipjob.sh; dry-run mode), `ts live`, `ts slots`, `ts wt`, `ts clean`. Also: a safe `ts push`; the guard fetches pages in threads; ORM suites run during the guard compare; one REHEARSAL verdict line with a known-failures list; `ts_pages.py`; parallel slots with locks and capacity rules; ship dumps written as `.part`; per-slot fake SMS ports; per-DB kv fixture files; __pycache__ untracked.
- Verified: two full rehearsals ran in parallel (eot_ts20 slot 0, eot_ts21 slot 1) in 12 min each. Both: guard UNCHANGED (1,050 pages), portal UNCHANGED signed in, 653/655 checks, the 2 failures on the known list. Also verified: `ts db reload` + `ts test` on a kept clone, the port-collision refusal, the ship dry run (live baseline in 3 min, odoo20 untouched, `ts live` clean), sync/rehearsal refused during a ship, and the capacity refusal with 2 slots busy. Clones dropped afterwards.
- `ts clean` (dry run) lists 10 old `talentsearch_prev_*` code dirs and the `eot_ts_kv1` clone as removable; the owner decides before `ts clean --yes`.

- Cleanup done 2026-10-01: dropped clone eot_ts_kv1, removed 10 old talentsearch_prev_* dirs (kept edg1, pnl1, sgn1), merged local branches deleted (still on origin). Bug found by the real run: `ssh` inside a `while read` loop swallowed the rest of the list (fixed with `ssh -n`).

## pv2s0 — Panel v2, stage S0 tooling (2026-10-01)
- New module `ts_panel` (depends `ts_talent`), installed live. Contents: `models/attempt.py` (G28: `action_submit` override above ts_talent's matrix branch, which never calls `super()`; writes one `ts.usage.event` per finished panel attempt, idempotent, never for imports or self-taken results); `views/report_share.xml` (G30: sharing/revoke block on the TALENT-INV-15 report, `t-if="not org_view"` so the institute view never shows it; G31: share-by-code page now says the counselor sees the profile report without answers for matrix instruments); empty `panel.scss` / `panel.js` registered in `ts_website.assets_ts` / `assets_ts_js`.
- Tooling: `tools/prod/pv2_fixtures.py` (3 panels, 9 members, 1 shared real TALENT-INV-15 result; upserts, two runs give identical counts); `ts_check.py` panel rules (audit `.log(` with personal keywords = warning until S1; `sudo().search/browse` in `ts_panel/controllers` without `workspace_id` = error; forbidden claims in `ts_panel` templates = error; `--selftest`); `ts_shot.py` now has `--matrix FILE.json` (routes per fixture role) and checks h1, labels, English in `<title>`, contrast (skips gradient backgrounds), exit code; `ts_rehearse.sh` has a `has ts_panel` block (self-test, fixtures twice, `tests_pv2_0.py`, `ts_http_pv2_0.py`).
- Tests: `tests_pv2_0.py` 7 (ORM), `ts_http_pv2_0.py` 17 (HTTP: revoke button, institute view clean, counselor view 404 after revoke, share-page wording, eot.ir 404). Rehearsal eot_ts30 (third run): guard eot.ir UNCHANGED (1,050 pages), portal UNCHANGED (360 lines), 135/135 checks, unexpected failures 0. Ship `pv2s0` (commit d378b5d): eot.ir UNCHANGED live, `/panel` 200 on talentsearch.ir and 404 on www.eot.ir.
- Owner note: usage counting for TALENT-INV-15 starts now; earlier completions in panels (none live) were not counted.
- Lessons: a fixture builder that fails inside `odoo shell` still prints the same traceback twice, so "run twice, outputs equal" must require a `FIXTURES` line; clinical panels need `escalation_contact_id` before `state='pilot'`; `action_verify` needs the platform-manager group, fixtures set the verified state directly.


## pv2s1 — Panel v2, stage S1 permissions (2026-10-01)
- Roles: new `admin` («هماهنگ‌کنندهٔ پنل», never sees a result beyond status), owner label «مالک پنل». One active membership per person per panel (unique partial index; migration deactivates older duplicates, keeping the highest rank). `owner_practices` on the member (solo panels set it; fixes G1: a verified solo psychologist now sees clinical results of the own clients).
- `ts_org/models/perms.py`: 33 permission strings per role and purpose, attribute conditions A1-A5b in `member.perms()`, `has_perm()` (unknown string raises). Old role-set API kept as thin wrappers (`can_invite`, `can_assign`, `sees_all`, `VERIFIED_ROLES`, ...), so existing call sites behave as before; `result_level()` (none/status/summary/education/clinical) sits under `visible_results`.
- Gates: settings POST = `panel:profile`, colleague invitations/revoke = `members:invite`, members/settings sections likewise (admin does not get them); accepting a colleague invitation while already an active member is refused with a Persian message.
- Audit (ts_core 20.0.1.1.0): detail cleaner drops name/phone/email/answer/token/reason/note/text keys and masks phone/email-shaped values; raw IP no longer written (salted hash `ip_hash`, legacy column nulled by migration); new fields outcome/route/request_id/member_id; `log_denied()` writes `authz.deny` through its own cursor so it survives the 404, throttled to one row per user, route and minute. Free-text reasons and approval notes are no longer stored in audit detail (only lengths/flags).
- Tests: `tests_pv2_1.py` 48 (P01-P17, P23; the table of 05_permissions_matrix.md is parsed from a copy embedded in the test and compared with `ROLE_PERMS`), `ts_http_pv2_1.py` 20 (P24 deny event + throttle, admin sees no members/settings, POSTs refused, solo licence + owner_practices). `ts_check`: audit calls with personal keywords are now errors.
- Rehearsal eot_ts31 (second run): eot.ir UNCHANGED, portal UNCHANGED, all old suites green (org 35, org_resp 22, panel 68, edge 25, signup 27, HTTP suites). Ship `pv2s1` (commit 7ca39bb): eot.ir UNCHANGED live.
- Lessons: Odoo 20 `ir.config_parameter` has `get_str/set_str` (no `get_param`); `ts_flowlib`/`ts_http_flow` hardcoded the slot-0 stage path, so HTTP-suite shells ran old code on slot 1 (now slot-aware); a write followed by a create of the same unique key needs `env.flush_all()` in tests; the first rehearsal run was wasted on these three, so run one new test file by hand on a kept clone before the full rehearsal.

## pv2s2 — Panel v2, stage S2 shell (2026-10-01)

- `ts_panel` 20.0.1.1.0: shared shell (menu per permission, mobile menu button, 403 inside the shell), dashboard `W/home` with six counters, state pages (draft, suspended, closed, awaiting verification), `W/settings` (profile and contact for `panel:profile`, terms for `panel:settings`), header link «پنل من» (`res.users.ts_panel_home()`), notice on the old page. New design tokens in `ts.scss`.
- Tests: `tests_pv2_2.py` (9 ORM), `ts_http_pv2_2.py` (46 HTTP). Rehearsal eot_ts32: eot.ir UNCHANGED, portal UNCHANGED, unexpected failures 0. Ship `pv2s2` (commit bc08113): eot.ir UNCHANGED live.
- Lesson: Bootstrap's `:root` overrides `--success`/`--danger`, so panel-local tokens are needed (pill contrast was 2.7:1). Running each new test file by hand on a kept clone first saved a full rehearsal.

## pv2s3 — Panel v2, stage S3 members (2026-10-01)

- `ts_panel` 20.0.1.2.0 (now depends on `ts_sms`): `W/members` (list incl. inactive, pending invitations, invite form), `W/members/<id>` (change role, deactivate with a confirmation page, reactivate, «I also see clients» for owners with licence in clinical panels), send-again (old link dies, new 7-day link), revoke, `/help/roles` generated from the permission table (only permissions that exist today), re-authentication `/my/reauth` (code to the account's verified mobile via the OTP sender, password when there is none; adding an owner needs it; 10 minutes).
- New model `ts.reauth.code` (hashed code, 5 tries, 5 min, no ACL rows). Never writes to the shared `ts.phone.otp`.
- Tests: `tests_pv2_3.py` (34 ORM, sender patched, no SMS), `ts_http_pv2_3.py` (35 HTTP). Rehearsal eot_ts33: eot.ir UNCHANGED, portal UNCHANGED, unexpected failures 0. Ship `pv2s3` (commit 2bbb31c): eot.ir UNCHANGED live.
- Lessons: HTTP test found a real bug (inactive member lookup needs `active_test=False`); a served kept clone keeps old Python after `ts sync` (halt + serve again); ships run from slot 0 only (`TS_SLOT=0`).

## pv2s4 — Panel v2, stage S4 clients (2026-10-01)

- `ts_panel` 20.0.2.0.0: model `ts.panel.client` (name, normalised name, code, phone, email, responsible, age group, guardian, account link, source, locked contact for imported people, merge/archive state, counters), idempotent migration `ts_migrate_s4()` (invitations M3, imported results M4 as locked clients without contact data, web attempts M5; pre-migrate snapshots old responsible ids). Invitation linking: account, then exact phone, then exact email, never by name. List `W/clients` (relationship rules R0-R3 as a domain, filters, whitelisted sort, 25 per page, search text kept in the session with PRG so it never reaches a URL), client page with responsible-specialist change.
- Tests: `tests_pv2_4.py` (38 ORM), `ts_http_pv2_4.py` (30 HTTP); old suites adjusted (S2 menu order, `tests_edge` audit expectations, `ts_http_resp` audits `client.responsible_change`). Rehearsal eot_ts34 (second run): eot.ir UNCHANGED, portal UNCHANGED, unexpected failures 0. Ship `pv2s4` (commit 4d18327): eot.ir UNCHANGED live.
- Deviations from the plan: `channel` and `expires_at` on assignment are deferred to S6; `responsible_id` on assignment/attempt is a non-stored related field (a stored one made `tests_edge` fail because recompute runs constraints); audit event `client.responsible_change` is added alongside the old assignment/attempt events.
- Lessons: stored related fields re-run constraints on recompute, so use non-stored related fields for write-through; `odoo.osv.expression` does not exist in Odoo 20 (list domains with explicit `'|'`); the shell frame already prints flash messages; a test that converts an attempt to an import with `write()` bypasses `create`, so `attempt.write` must link the client too (found by the old responsible-specialist HTTP suite); `pkill -f` over ssh matches its own command line (use a bracket pattern); `git add -A tools addons` before `ts sync`.


## pv2s5 — Panel v2, stage S5 clients-edit (2026-10-01)

- `ts_panel` 20.0.2.1.0: client edit, archive/restore, merge (`ts_merge` flushes between freeing and re-taking unique values), groups page `W/groups` (menu seq 25, `groups:manage`), perm labels, CSS/JS.
- Tests: `tests_pv2_5.py` (33 ORM), `ts_http_pv2_5.py` (38 HTTP). Rehearsal eot_ts35 (second run): eot.ir UNCHANGED, portal UNCHANGED, unexpected failures 0. Ship `pv2s5` (commit bb2e414): eot.ir UNCHANGED live.
- Lessons: flush ordering with unique indexes (also around `raises()` savepoints); the test client does not follow redirects (`lib.follow`); an overridden compute must list all `@api.depends` inputs; menu tests should not depend on menu length.

## pv2s6 — Panel v2, stage S6 invites (2026-10-01)

- `ts_panel`: invite wizard, invitation list (`W/invites`), dashboard without forms; `ts.assignment.expires_at` is stored, and `write()` recalculates it when `deadline` changes on a not-yet-accepted invitation. `?minv=` redirects to `/members?minv=`. The old workspace page stays at `W/legacy` until S20; the setup checklist moved to the dashboard.
- Tests: `tests_pv2_6.py`, `ts_http_pv2_6.py` (48 checks); older suites moved to `/legacy` and to stored expiry. Rehearsal eot_ts36s (second run): eot.ir UNCHANGED, portal UNCHANGED, unexpected failures 0. Ship `pv2s6` (commit c722bb9): eot.ir UNCHANGED live.
- Deviations: attempt state `stopped` on withdraw is deferred to S18; the QR check has no decoder; `opened` can be set by link previews; `ts.job` gets a `draft` state in S8.
- Lessons: when a page moves, move the old suites that read it in the same stage; stored expiry replaces read-time age; a kept clone on a slot's port blocks the rehearsal; a stale ts_shot tunnel on 18071 needs `fuser -k`.

## pv2s7 — Panel v2, stage S7 campaigns (2026-10-01)

- `ts_panel` 20.0.4.0.0: `ts.campaign` (group invitation and open link), pages `W/campaigns`, `/new`, `/<id>`, `/sheet`, `/qr.png`, public `/c/<token>` and `/c/<token>/join`, button «دعوت گروه» on the groups page. Both launch and join are refused on gated panels; locked (import), archived and busy clients are skipped with the reason shown.
- Tests: `tests_pv2_7.py` (36 ORM), `ts_http_pv2_7.py` (48 HTTP, fake Kavenegar, SMS sender patched in ORM). Rehearsal eot_ts37r (second run, after adding `# ts-scope-ok` comments): eot.ir UNCHANGED, portal UNCHANGED, unexpected failures 0. Ship `pv2s7` (commit 0f70cf3): eot.ir UNCHANGED live.
- Lessons: `ts check` run in the main repo does not check a worktree's new files, so run it inside the worktree; HTTP-test SQL inside `% L` strings needs `%%`; menu tests must not depend on later menu items.

## pv2s9 — Panel v2, stages S8 import + S9 export (2026-10-01)

- `ts_panel` 20.0.5.0.0 / 20.0.6.0.0 shipped together (label `pv2s9`, commit fc6c971). S8: file import of clients (csv/xlsx, windows-1256 with Arabic yeh/kaf normalised), `ts.job` background runner (crons every minute / hourly expiry), pages `W/import`, map, review, start, job page. S9: exports of clients, invitation status and results as jobs (`models/exporter.py`), UTF-8 BOM csv or RTL xlsx, Latin digits, Jalali and ISO dates, formula guard (`'` prefix), fresh re-authentication to create and to download, audit `export.create` / `export.download`, results only at the level the member holds, TALENT rows hold field number and scales, never the field label.
- Tests: `tests_pv2_8.py`, `ts_http_pv2_8.py`, `tests_pv2_9.py` (51 ORM), `ts_http_pv2_9.py` (34 HTTP). S8 alone (reh38) failed only 4 S2 menu tests (fixed via `LATER`); combined rehearsal eot_ts39r green, eot.ir UNCHANGED, ship OK.
- Deviations: `ts.job` has a `draft` state; manual reminders (S10) are refused in quiet hours instead of queued.
- Lessons: never name a model method `_table`; `attachment.raw` may be a lazy BinaryValue (use `.content`); `flush_all()` before raw SQL in crons; openpyxl writes inline strings with entities and is not in prod's system python (tests read the zip + `html.unescape`); education panels allow TALENT-INV-15 only; `ts_for_invitation` never links by name; never run two HTTP tests on one fake port.

## pv2s10 — Panel v2, stage S10 notify (2026-10-01)

- `ts_panel` 20.0.7.0.0 (commit adfd096): `ts.notification` and `ts.notify.pref` (in-app centre `/my/notifications`, preferences, header bell with unread count), 15 event types, hooks for invitation, result ready, share attempt/revoke, panel approve/reject/suspend, colleague-invite accept, handover request, finished background jobs. Reminders: `ts.assignment.reminder_count`/`last_reminder_at`, one automatic reminder (3 days before the deadline, or 7 days after creation when there is none), cron daily 10:00 Tehran, manual «یادآوری» button on the invitation page (at most one per 24 h and three in all). Quiet hours 21–08 Tehran, `sms_per_day` 5, flush and vacuum crons.
- New company switches `ts_sms_staff` and `ts_sms_reminder` ship **OFF**: nothing new reaches a phone until the owner turns them on in Settings → SMS. Existing invitation and result SMS are untouched. Imported (locked) people never get a reminder.
- Tests: `tests_pv2_10.py` (67 ORM), `ts_http_pv2_10.py` (26 HTTP; fake Kavenegar message count 0 with the switches off). Rehearsal eot_ts41r green, eot.ir UNCHANGED, ship OK.
- Deviations: manual reminders in quiet hours are refused with a message instead of queued; email channel not built (D8).
- Lessons: `is not true` is not a valid ORM domain operator (use the stored `state` field); `ts check` in the worktree finds the `ts_scope` errors that the main repo run misses; a pill that depends on `.tsp-shell` variables fails the contrast audit outside the shell (use plain colours).

## pv2s11 — Panel v2, stage S11 wallet (2026-10-01)

- `ts_panel` 20.0.8.0.0 (ship commit c4113d3): `ts.wallet` per panel (stored balance and units used), append-only `ts.wallet.txn` with a unique `idem_key`, one debit per finished panel attempt (amount 0 and `free` while `ts_panel.credit_mode` is `free`), `action_void` with a single refund (manager only, audited), daily reconcile cron, credits page `W/credits` (perm `credits:read`), back-office views, menu item «اعتبار و مصرف».
- Tests: `tests_pv2_11.py` (42 ORM), `ts_http_pv2_11.py` (15 HTTP). Rehearsal eot_ts48r: portal UNCHANGED, unexpected failures 0; guard showed one group (view of ts_panel's own settings, same arch) which the guard now treats as ours. Ship `pv2s11`: eot.ir UNCHANGED.
- Deviation: voided attempts are not yet left out of reports until S13.
- Lessons: `ts.instrument.name` is varchar, not jsonb; audit `detail` takes ids only (no `text`); old menu tests must allow later menu items (`LATER`).
- Toolkit: rehearsal clones are restored from the newest `eot_main_pre_*.dump`, which predates a stage's own install. After a ship the live code can be newer than the newest dump, so the portal baseline fails ("login 200") because columns are missing. Take a fresh `pg_dump -Fc` into `/var/backups/odoo/eot_main_pre_<name>.dump` before rehearsing after any ship.

## pv2s12 — Panel v2, stage S12 dashboard (2026-10-01)

- `ts_panel` 20.0.8.0.0 + dashboard (ship commit 1703dc3): `models/dashboard.py` (needs-attention lines, period tiles 7/30/90 days, funnel, workload, setup checklist with dismiss), list filters on invitations and clients so that every tile count equals its list count, small-group guard `MIN_N` 5.
- Tests: `tests_pv2_12.py` (38 ORM), `ts_http_pv2_12.py` (21 HTTP). Old S2 tests updated for the new tiles and menu. Rehearsal eot_ts49r: portal UNCHANGED, unexpected failures 0. Ship `pv2s12`: eot.ir UNCHANGED.
- Lessons: tiles must be built from the same filters as their lists; `'is not true'` is not a domain operator.
- Incident (not caused by the code): during the ~3 min Odoo stop of each ship the owner saw eot.ir served from the old server 45.82.138.67. DNS and Arvan answers from the VPS pointed only at the new server; root cause is open (see memory lessons).


## pv2s13 — Panel v2, stage S13 reports (2026-10-01)

- `ts_panel` 20.0.9.0.0 + `ts_talent` (ship label `pv2s13`, commit 979f87c): one result page per attempt `W/clients/<cid>/r/<attempt>` whose content follows `ts_result_level` (none -> 404 + deny event, status, summary bands, education, clinical); opening and printing audited (`result.view`, `result.print`); old `/a/` and `/p/` routes redirect there. Group report `W/reports/group` with small-cell suppression (`ts_panel.group_min_n` default 5; every cell below k hidden, and when exactly one cell is hidden the next-smallest too; voided attempts excluded).
- Tests: `tests_pv2_13.py` (24 ORM), `ts_http_pv2_13.py` (33 HTTP). Rehearsal eot_ts54r: guard UNCHANGED, portal UNCHANGED; the only failures were three old tests (print button, renamed audit event, status page after revoke) updated and re-run green. Ship: eot.ir UNCHANGED.
- Lessons: flowlib `req` now follows the old `/a/` and `/p/` redirects unless `follow_old=False`; after any ship take a fresh `pg_dump` before the next rehearsal (stale dump -> invalid portal baseline).
- Watch during the ship: www.eot.ir through Arvan returned only 502 for ~3 min while odoo20 was stopped, never the old server (45.82.138.67). Root cause of the earlier old-server report is still OPEN.

## pv2s14 — Panel v2, stage S14 audit (2026-10-01)

- `ts_panel` 20.0.10.0.0 + `ts_core` (ship label `pv2s14`, commit 39329d5): the panel audit page `W/audit` (owner only, families and plain sentences, day/member filters, Tehran day edges, paging), CSV export `W/audit/export` after re-authentication, support access (`kind` emergency/support with a ticket reference, owners notified), "who viewed" list on the result page. `ts_core` emergency access now asks small methods (`_check_scope`, `_hours`) that `ts_panel` overrides.
- Tests: `tests_pv2_14.py` (34 ORM), `ts_http_pv2_14.py` (20 HTTP). Rehearsal eot_ts55r: guard UNCHANGED, portal UNCHANGED, one old menu test updated for the new item (re-run green). Ship: eot.ir UNCHANGED.
- Lessons: events seeded for a test must be keyed by actor so a re-run on a kept clone stays valid; cross-panel checks must tolerate the page's own export events.
- Ship window: www.eot.ir through Arvan again showed only 502 for ~3 min and one curl timeout; never the old server.

## pv2s15 — Panel v2, stage S15 participant portal (2026-10-01)

- `ts_org` 20.0.2.0.0 + `ts_panel` 20.0.11.0.0 (ship label `pv2s15`, commit aeb1ec4): participant home `/my` and account `/my/account` on Talent Search only, sharing page `/my/sharing` (up to `ts_panel.share_max_panels` = 3 panels per result, decision D3), privacy page `/my/privacy` (export as ZIP of JSON + CSV, erase request due in 30 days), append-only consent ledger `ts.consent.record`, data requests `ts.data.request`, and the block "who can see this result" on both report pages.
- Rehearsal reh58: guard and portal UNCHANGED; only two stale checks in `ts_http_flow.py` (old /my cards) were rewritten.
- Ship note: the script said NOT OK because the eot.ir comparison saw differences. They came from concurrent work on eot.ir (a website page edited 18:48 and `theme_eot_custom` upgraded with an odoo20 restart 18:52-18:53), not from this ship (upgrade list was only ts_org, ts_panel; probes 200). Lesson: if the compare shows many text diffs, look at `ir_ui_view` / `website_page` write_date and the journal for other deploys before blaming the ship.

## pv2s16 — Panel v2, stage S16 minors (2026-10-01)

- `ts_panel` 20.0.12.0.0 (ship label `pv2s16`, commit 0593c58): `ts.panel.client.guardian_consent` (none / attested / confirmed); the school attests that it holds the guardian's consent (decision D2) with a tick in the invite wizard (step 4) and in the group campaign review; this writes a `guardian_attest` ledger row (given by a panel member) and the audit event `guardian.attest`. A minor's result stays at `status` level until it is attested (`_ts_guardian_blocks`). `account_is_guardian` is set when a guardian accepts a child/adolescent invitation (GRD-7). The consent page now asks people who test themselves whether they are 18; under 18 needs a tick that a guardian agrees (ledger `guardian`), and a minor inside a panel ticks their own assent (ledger `assent`). Every accepted consent also writes `service` / `research` ledger rows.
- Wording: the guardian/assent texts are conservative and not yet approved by the owner (the plan says the owner approves); text versions `TS-GUARDIAN-1405-07-v1`, `TS-MINOR-1405-07-v1`. Flag in the final report.
- Rehearsal reh60: guard and portal UNCHANGED; two stale S15 checks (`/my` phone card in `ts_http_sms.py`, user name in `ts_http_signup.py`) moved to `/my/account`.
- Ship note: compare again showed differences that come from other work on eot.ir (`theme_eot_custom.page_founder` view changed, odoo20 restarted 19:46:33 right after the compare). Second time this happened during a ship; see the open follow-up in the lessons file.


## pv2s17 — Panel v2, stage S17 back office (2026-10-01)

- `ts_org` 20.0.3.0.0 + `ts_panel` 20.0.13.0.0 (ship label `pv2s17`, commit 5a80b15): tenant health list (member / client / open invite counts, done in 30 days, last activity, days pending; SQL-computed), pending-approval list, data-request queue (review, decide, mark done, reject for legal reasons; overdue shown by an explicit domain, not a search method), operator-only access cleanup (`ts_org` assignments menu is manager-only).
- Tests: `tests_pv2_17.py` (25 ORM). Ship: OK, eot.ir UNCHANGED.
- Lessons: a non-stored computed field with a `search=` method returned nothing in Odoo 20 here, so use an explicit domain; menu groups are additive on upgrade, reset them with an `ir.ui.menu` record and `(6,0,[...])`.

## pv2s18 — Panel v2, stage S18a lifecycle (2026-10-01)

- `ts_panel` 20.0.14.0.0 (ship label `pv2s18`, commit e9dc498): ownership transfer and closing a panel (owner only, re-authentication; notifications `panel_transferred` / `panel_closed`; closed members keep only `panel:view`), client anonymisation, retention job `ts.retention.log` + daily cron (ships OFF: `ts_panel.retention_enabled`; abandoned attempts and audit events are report-only), data-erasure action on the data request (revokes shares, empties attempts, anonymises clients, deactivates the account; clinical-panel attempts are hidden and the decision is `legal_hold`, open item L2).
- Tests: `tests_pv2_18.py` (39 ORM), `ts_http_pv2_18.py` (20 HTTP). Rehearsal reh62: 1312/1312, guard and portal UNCHANGED. Ship: OK, eot.ir UNCHANGED.

## pv2s18b — Panel v2, stage S18b security (2026-10-01)

- `ts_panel` 20.0.15.0.0 (ship label `pv2s18b`): staff idle timeout (`ts_panel.staff_idle_hours`, default 8, 0 = off; hook in `ir.http._authenticate`, only on website 4 and only for panel members; the last-seen mark is touched every 60 s); sessions page `/my/sessions` with "sign out of other devices" (re-authentication, audit `account.sessions_revoke` with a count); password of at least 15 characters on website 4 only (`_set_password`); SMS sign-in risk notice (`#ts-sms-risk`) on the sign-up page.
- Tests: `tests_pv2_18b.py` (4 ORM), `ts_http_pv2_18b.py` (11 HTTP). Rehearsal reh63: guard and portal UNCHANGED; one stale S18a check (audit count) made relative. Ship: OK, eot.ir UNCHANGED.
- Lessons: Odoo 20 `logout` is `odoo.http.session.logout(session, keep_db=True)`; at `_authenticate` time the website is in `env.context['website_id']`/`host_id`; `password` is write-only so a constrains never sees it, override `_set_password`.

## pv2s19 — Panel v2, stage S19 help and accessibility (2026-10-02)

- `ts_panel` 20.0.16.0.0 + `ts_website` 20.0.1.1.0 (ship label `pv2s19`, commit 52bd0ca): panel help center `/help/panel` (9 task sections with anchors, "last checked" date in `controllers/help_center.py`, support link `/contact?topic=panel&panel=<id>`), the panel menu "راهنما" and the dashboard notices point to it, contextual «این چیست؟» links on the export, audit (support access), invite and campaign (minors) pages and on `/my/sharing`; the audit page shows the system user as empty actor instead of OdooBot; trust pages text (G27) now says that an erase request is reviewed within 30 days, that clinical-panel results may be kept under a legal duty (hidden only), and how minors' consent is attested.
- Tests: `ts_http_pv2_19.py` (42 HTTP): help page anchors, contextual links, and a scan of 13 panel routes + 6 participant routes for two roles (one h1, Persian title, no English words other than file-format names, labelled fields, forbidden claims). The scan found English file-format names and OdooBot; the first are allowed (codes), the second was fixed. Rehearsal reh64b: 1369/1369, guard and portal UNCHANGED. Ship: OK, eot.ir UNCHANGED.
- Not done in S19: a headless-browser audit at 1280/375 px (`ts_shot`) was not extended; the scan is HTTP/HTML only. A manual look with a test account on a phone is still recommended.

## pv2s20 — Panel v2, stage S20 cleanup, lite (2026-10-02)

- `ts_panel` 20.0.17.0.0 (ship label `pv2s20`, commit 325b177): the unused first-steps helper `_setup_steps` removed. Rehearsal reh65: 1369/1369, guard and portal UNCHANGED. Ship: OK, eot.ir UNCHANGED.
- Deliberately NOT done: `W/legacy`, `ts_org.tpl_workspace` / `tpl_assignment` and `ts_sms.tpl_workspace_sms` stay. Nine old suites test responsible-assignment, invite and phone-card behaviour through W/legacy; deleting the page means moving those checks to the new pages first. Open decision for the owner.

## ui1 — Design system v2, layout modes, panel navigation (2026-10-02)

- `ts_website` 20.0.2.0.0, `ts_org` 20.0.4.0.0, `ts_panel` 20.0.17.0.0 (ship label `ui1`, commit 8f39565). Estedad + Vazirmatn variable fonts with Persian digits mapped onto 0-9 (built with `tools/fonts/build_fd.py` + `woff2enc.js`), design tokens v2, three layout modes (marketing / app / focus / auth) decided from the path, compact app bar, slim footer, panel rail on wide screens + drawer and bottom tab bar on phones (fixes the invisible desktop menu: `panel.js` had hidden the list for every width), Persian sign-in form for website 4, home page with the five-angle profile figure, pricing page «پنل رایگان / همیار تفسیر به‌زودی», `/panel` copy, website menu reduced to six items.
- Benchmark and plan: `docs/panel_v2/09_ui_benchmark.md`. Rehearsal reh66: guard and portal UNCHANGED, two stale checks rewritten. Ship: OK, eot.ir UNCHANGED.

## ui2 — Panel pages, portal and player polish, inner pages (2026-10-02)

- `ts_website`, `ts_assessment`, `ts_panel` (ship label `ui2`, commit eeb1b11): clients page order with a folding saved-views card, one-row search, scrolling filter chips and wizard steps, tables in cards, 44 px controls everywhere, participant pills, player sticky progress and sticky actions on phones, option-label contrast, inner page hero without the eyebrow label. Rehearsal reh67: 1387/1387, guard and portal UNCHANGED. Ship: OK, eot.ir UNCHANGED.
- Lessons: `.ts-band` existed twice (CTA band and score pill); `hasclass()` needs a static class; `ts_shot.py` must open one tunnel per clone port.

## pv3a — Client portal v3, first release (2026-10-02)

- `ts_website` 20.0.3.0.0, `ts_org` 20.0.5.0.0, `ts_assessment` 20.0.3.0.0, `ts_panel` 20.0.20.0.0 (ship label `pv3a`): see `docs/portal_v3/02_handoff.md`. Home with one dominant action, four-item navigation, account hub, consent «چه کسی می‌بیند» from the real invitation, submission block, unavailable-result page (no redirect loop), report lead + folded details + same-instrument history, grouped results list, quiet layout for invitations, visible sharing checkbox, site-wide status colours, Latin digits for identifiers.
- Tests: `ts_http_pv3.py` (24), older suites green; shots at 320/390/430/768/1280. Rehearsal reh68 and ship: see HANDOFF.


## redesign1 — Website 4 redesign + product restyle (2026-10-10)

- `ts_website` 20.0.4.0.0, `ts_assessment`, `ts_talent`, `ts_panel` (ship label `redesign1`, commit e882605, branch `redesign` fast-forwarded into main). Spec: Project docs «Talent Search Website.html» / «Talent Search App.html» + IMPLEMENTATION_PROMPT.md.
- Tokens light/dark (`static/src/scss/tokens.scss`, legacy variables remapped so every module rethemes), theme toggle stored in `localStorage['ts-site-theme']` with an inline pre-paint script, five pages (/, /schools, /assessments, /pricing, /contact) + /privacy, /contact/thanks, new 404, FAQ accordion (button + aria-expanded), contact form takes email OR mobile, grouped panel sidebar, «دفتر ممیزی».
- 301s (website 4 only, `data/redirects.xml`): /how-it-works, /evidence, /about, /help, /employers, /clinics, /sample-report, /entekhab-reshteh(+/sample), /consent-policy. Old catalog kept at /assessments?all=1.
- Rehearsal reh_eot_ts72: guard UNCHANGED, portal UNCHANGED, 1 stale check (top menu 6 -> 4 items, fixed in tests_stage1.py). Ship: OK, eot.ir UNCHANGED (1050 pages compared).
- Deviations: Phosphor could not be downloaded (npm/CDN blocked) -> inline SVG icon template `ts_website.icon` in the same style; product screens restyled through tokens, not rebuilt 1:1; statement spelling fixes NOT applied (owner confirmation needed); /ts_website/static/img/dr-kazemi.webp not supplied yet (slot hides).
- Known polish left: sign-in primary button contrast, consent radios default style, contact card heights, dashboard member-workload table.

## uxhot1 + ux2 — UX audit of all product pages, fixed and shipped (2026-10-11)

- Audit: `ts shots DB ux` (new full matrix tools/vps/ts_ux_seed.py: 90 page/role/state combinations, 375/1280/dark, extra checks for heading order, landmarks, names, focus ring, lang) + five `ts-ux-auditor` agents (.claude/agents) against ISO 9241-11/-110/-112/-125/-143/-171/-210, ISO/IEC 25010, WCAG 2.2 AA. 302 findings (sev4 27, sev3 65). docs/ux_audit/2026-10-11/.
- uxhot1 (commit 1aada8d): participant page 500 (live before the redesign: `client.id` -> `c.id` in web_client.xml), dark surfaces (`--white` -> `--color-surface`; Odoo's frontend CSS redefines `--white` after our bundle), matrix `/take/<t>/review` redirects to the player. Rehearsal eot_ts74 green; ship OK, eot.ir UNCHANGED.
- ux2 (commit d8e5927, modules ts_core, ts_website, ts_assessment, ts_org, ts_talent, ts_panel, ts_sms): 297/302 fixed by four parallel implementers + an integrator. New shared components: `ts_website.jdate` (Solar Hijri date field + `ts_website.tools.parse_jdate`), `ts_website.filefield`, `ts_website.auth_choices`, CSS `.ts-confirm/.ts-backlink/.ts-bdi/.ts-scroller`; Persian 500 and reset-password pages; talent player progress, check-answers step, reopen field (`/take/<t>/reopen`), consent text v2 (`TS-CONSENT-1405-07-19-v2`, `TS-MINOR-1405-07-19-v2`); report tie handling (never the same field best and worst); reauth keeps the pending action; danger actions with confirm pages; audit log names actors; import shows who is updated; TERMS_VERSION v3 (owners re-accept); copy per docs/ux_writing (voice.md, glossary.md; `ts-ux-writer` agent).
- Rehearsal eot_ts75: 9 failures (tests following old flows/wording; exact-tie marks) fixed in 30fcc1a/2aa27f6; visual verification found 10 defects (RTL CSS build flips left/right: set `direction:ltr` inline on SVG charts; select chevron) fixed in e15f093/d8e5927; shots 0 problems. Rehearsal eot_ts76: guard UNCHANGED, portal UNCHANGED, 0 unexpected. Ship ux2: OK, eot.ir UNCHANGED.
- Open on purpose: book statement spelling; sharing checkbox default; /legacy route still serves (unlinked; SMS invite form + 8 suites use it); import "skip updates" option; cancelling an erasure request.
- Lesson: Odoo's RTL asset build flips physical left/right in our SCSS; use logical properties, or inline style for things that must stay LTR.

## clinic phase 2 — ts_battery on a clone (2026-10-11, not shipped)

- New module `ts_battery` 20.0.1.0.0 (commit 21d3209 + test fix 47b8413): `ts.battery` / `ts.battery.line` (draft/published/retired, item_count, est_minutes, purpose flags, has_retired), workspace catalog (`catalog_mode` purpose|granted, catalog instruments/batteries), member restrictions, `allowed_instruments()` / `allowed_batteries()`, server-side refusal of invitations outside a granted catalog («این سنجه برای این پنل فعال نیست.»), audit `catalog.change`, back-office menus (باتری‌ها; «کاتالوگ» tab on panels; restrictions on members), six starter batteries loaded by code.
- tools/prod/clinic_seed_sepehr.py (idempotent; clone-only unless TS_ALLOW_LIVE=1; phones from TS_SEPEHR_PHONES JSON): partner + clinical workspace «سپهر هیجان اندیش» in granted mode (6 batteries, 22 instruments), approved, owner member, 9 phone-bound colleague invites (Dr. Kazemi as clinic_director). Wrappers tests_zseed_sepehr.py / tests_zdebug.py let `ts test` run it and show tracebacks.
- Clone eot_ts77 (slot 1): rehearsal guard UNCHANGED, portal UNCHANGED; tests_battery 54/54; seed twice (second run creates nothing); regression tests_org 35, tests_panel 68, tests_pv2_1 48, tests_pv2_4 38, ts_http_pv2_2 46, ts_http_pv2_4 30, ts_http_pv2_6 48 all green.

## clinic3 — batteries, institute self-management, counseling wording, «استعدادیاب» (2026-10-11, LIVE)

- Ship clinic3 (commit fb873ee): install ts_battery (Phase 2 + Phase 3), upgrade ts_core..ts_panel. Rehearsal eot_ts79: guard UNCHANGED, portal UNCHANGED, 0 unexpected (2038+ checks). Ship OK, eot.ir UNCHANGED (1049 pages). Backup /var/backups/odoo/eot_main_pre_ts_clinic3_20261011-1509.dump.
- Phase 3: battery invitations (wizard + list campaigns), one consent page per battery (CONSENT v3), player chaining with transition pages (/take/<t>/next), combined battery report for participant (/my/assessments/battery/<a>) and panel (/my/workspaces/<ws>/clients/<c>/b/<a>, print audited), counselor-level catalog chosen by the institute in the panel member page (perm catalog:assign, flag catalog_restricted), seed creates no invites unless TS_SEPEHR_INVITES=1.
- Owner wording decision: counseling vocabulary only (no درمان/بالینی/کلینیک/بیمار in UI); labels: purpose «مشاوره», panel «مرکز مشاوره», clinic_director «مدیر مرکز مشاوره», clinician «مشاور مرکز»; display-time word map for book texts (50 sentences listed in docs/clinic/03_terms_in_book_texts.md for the owner). Battery 1 «ارزیابی آغاز مشاوره». Starter batteries are not offered to school panels.
- Persian product name «استعدادیاب» (website record, CRM team/tag, sequences renamed on upgrade).
- Live bug fixed: /web/signup 500 (layout title fallback set main_object=None; seo_object needs it). Known cosmetic: fallback title reads «استعدادیاب | استعدادیاب» on pages without a title.
- ts_check: inherited t-elif inserted before a t-elif is valid.

## clinic4 — prepaid billing on native Odoo (2026-10-12, LIVE)

- Ship clinic4 (commit d0d52a9): install ts_billing, upgrade all ts modules. Rehearsal eot_ts81: guard UNCHANGED, portal UNCHANGED, 0 unexpected (63 suites, 2152 checks). Ship OK, eot.ir UNCHANGED (1049 pages). Backup /var/backups/odoo/eot_main_pre_ts_clinic4_20261012-0335.dump.
- Live effects: company 1 currency USD -> IRR (rounding 1, audit billing.currency_switch; 0 journal entries existed), 40 service products (one per published instrument/battery, list price 0, category «استعدادیاب / سنجه‌ها»), top-up product «اعتبار پیش‌پرداخت استعدادیاب». Every panel stays `billing_mode='free'` (Sepehr included) until the super admin switches it in the back office.
- Design: docs/clinic/04_billing_brief.md (contract) + 04_billing_stages.md (plan written from another session). Ledger Monetary in Rial; types hold/release/topup; keys hold:<asg>, release:<asg>, usage:<attempt>, topup:<move>, topup-rev:<credit note>; cap spend = -SUM(hold, release, debit_usage, refund) per Jalali month; prices via the partner's explicit pricelist (specific_property_product_pricelist) rounded to 10 Rial; top-up hooks on write, register-payment wizard, payment post, move post, reversal + daily cron; credits page per role; tests tests_billing (87) + ts_http_billing (27).
- Reviewer (Fable) changes: low-balance check also after a hold; no explicit decimal_places write on IRR. Fixes during rehearsal: low_balance added to SMS_STAFF_TYPES; pv2_11 follows per-panel billing; C03 currency test only on a clone without journal entries; fixture names without the forbidden money words; money inputs RTL.
- Live to do by the owner: set prices on the products (ریال, multiples of 10), optionally a pricelist for Sepehr, switch Sepehr to prepaid, issue the first top-up invoice and register its payment.

## live config 2026-10-12 + clinic5 — branding, PDF, SMS templates (LIVE)

- Owner 2026-10-12 07:18: "set prices (Iran B2B in a clinic), switch to prepaid, 10 million toman top-up". Done by tools/prod/tests_zlive_sepehr_prepaid.py on eot_main: singles by length 80k/120k/180k toman (≤30/≤60/>60 statements), TALENT-INV-15 250k; batteries 70% of their singles (intake 300k, distress 250k, work 250k, life 220k, couple 220k, child 160k); Sepehr billing_mode prepaid; 10,000,000 toman start credit as a back-office grant (reason promo, key grant:sepehr-start-1405-07-20; no invoice because no payment was received); low-balance threshold 900k toman.
- Ship clinic5 (commit a23a72b): install ts_brand. Rehearsal eot_ts84 0 unexpected, guard/portal UNCHANGED; ship OK, eot.ir UNCHANGED. Backup /var/backups/odoo/eot_main_pre_ts_clinic5_20261012-0652.dump. Live: 16 SMS templates, every invitation has a short code.
- ts_brand: institution identity (public name, SMS short name ≤18, colour, contact line, logo) on panel settings; counselor identity (title, bio, photo, signature, show on report; licence shown only when verified) on the member page; branded report header/footer on participant, panel, talent and battery reports; PDF routes render via ir.actions.report when a PDF engine exists, otherwise (eot-odoo-prod has no wkhtmltopdf) 303 to the report in print mode (browser «save as PDF»), audited result.print kind pdf|print; all SMS from sms.template (docs/clinic/05_sms_texts.md; no assessment/battery names in SMS; short links /i /j /n); cap_reached notice; page-title fallback without duplicate site name.
- Fixes during rehearsal: content_disposition not exported by odoo.http in Odoo 20; ir.actions.report has no report_file; report actions load after their templates; guard treats backend views of ts_battery/ts_billing/ts_brand like ts_panel's; render failures log a warning not a traceback (rehearsal digests count tracebacks); tools/prod/ts_db.sh apply prints exception lines on failure.

## clinic6 — UX pass on the clinic pages + center onboarding (2026-10-12, LIVE)

- Phase 6: three UX audits (G6 battery pages, G7 billing pages, G8 center/branding/onboarding; ts-ux-auditor) on the eot_ts85 screenshots, 121 findings fixed by three implementers (battery 53, billing 31, center 37) plus one integrator for the 36 cross-module hand-offs (commits f477730, 42b39f6). Decision logic unchanged (ts_hold / ts_launch / campaign create decide as before); only texts, layout and presentation helpers changed.
- New: «راه‌اندازی مرکز» checklist on the counseling-center dashboard (identity, counselors, credit, catalog, caps (optional), first invite; per-member hide/restore; EOT-team status lines) and the help section /help/panel#center-setup; terms re-acceptance POST /my/workspaces/<id>/settings/terms (panel:settings, recorded like the create form, audited workspace.terms_accept); «شارژ اعتبار» card and contact topic `credit` (/contact?topic=credit&panel=<code>, panel code prefilled); credits page reordered (cards, total, low notice, top-up, invoices, history, per-member commitment «تعهد این ماه», caps, threshold, price list folded); wizard refuses an unaffordable item already at step 2 (same text as creation).
- Copy: «داشبورد» -> «پیشخوان» everywhere; «از طرف» -> «به دعوت»; «عامل / سطح» in reports; «چاپ همین صفحه» + «دریافت فایل PDF»; catalog display titles via ts_title() (book name kept in `name`); ws.ts_public_name() in participant-facing strings; separators via ts_website.sep (screen-reader comma); band texts de-duplicated at display time (docs/clinic/06_data_issues.md lists the source data issues for the owner); CONSENT_VERSION v4; unsaved-form guard (data-ts-dirty, capture phase).
- ts_brand: report images sniffed from the bytes (PNG/JPEG/GIF/WEBP/SVG), Odoo stand-ins and non-images draw no <img> (monogram instead); Odoo 20 binary fields return lazy values (BinaryBytes / BinaryValueAttachment): not sliceable, so helpers convert with bytes() first, and tests keep image bytes instead of re-assigning a read value.
- Clone eot_ts87 (slot 0, fresh dump of eot_main): tests_battery 96, tests_billing 87, tests_brand 179, tests_pv2_2 9, tests_pv2_11 42, ts_http_battery 38, ts_http_billing 28, ts_http_brand 63, ts_http_pv3 25, pv2_0 17, pv2_2 46, pv2_6 48, pv2_7 48, pv2_12 21, pv2_13 33, pv2_15 50, ts_http_org 27 — all green after test updates (card facts «،», one-page player has no page count, O13 follows the panel-name rule).
- Screenshots eot_ts88 (398 files, all 21 test users signed in): no h-scroll, English words or console errors; fixed before ship: the switcher link «هویت شما در گزارش‌ها» had no accessible name in the mobile drawer; prints from dark mode had pale text (dark tokens now `@media screen` only); one-paragraph notices were flex boxes that squeezed their link; report ids broke at the hyphen; wizard step-1 legend sat on the card border. Visual review (Sonnet helper): SHIP-OK.
- Rehearsal eot_ts89 (slot 0): 65 suites, 2395/2395 checks, guard UNCHANGED (1049 pages), portal UNCHANGED; the 4 «unexpected» were SMTP tracebacks: eot_main has a Liara mail server since 2026-10-12 and the clone tried to mail through it (rejected) — tools/prod/ts_db.sh clone now switches mail servers off and drops the outgoing queue (same as the hr1 branch).
- Ship clinic6 (commit 2cc4d11, upgrade all ts modules): OK, eot.ir UNCHANGED. Live: catalog display titles corrected by the loader (e.g. «فهرست ظرفیت‌های شناختی»، «فهرست بی‌تابی»; `name` unchanged).
- Tooling: a stale ssh tunnel (Oct 1, 18071 -> prod:8073) sent slot-0 screenshots to slot 1's clone (every sign-in failed, tokens 404): ts_shot.py now kills a tunnel on its local port that forwards elsewhere, retries navigation and sign-in, and never stops the matrix on one page; its contrast check skips screen-reader-only text.

## hr1 — HR hiring: positions, job fit, timed tasks, email (2026-10-12, LIVE)

- Owner decisions 2026-10-12: HR persona = company HR inviting applicants from an employment panel; hiring fit = personality + timed tasks only (O*NET says its interest/values/ability tools must not be used for hiring); early access as decision support (bands, no cut-scores, no auto-reject); email through Sepehr's Liara account as no-reply@sepehrtherapy.ir. Audit and plan: Project doc claude/ONET_HR_AUDIT_AND_PRODUCTION_PLAN.md; design docs/hr/01_architecture.md.
- New modules: `ts_onet` (923 O*NET 31.0 occupations with Persian titles/descriptions, search, JOBFIT-v1 engine), `ts_tasks` (TASK-REASON/SPATIAL/NUMERIC/SPEED/VERIFY: per-candidate generated items, keys and deadlines server-side, PN-0 then empirical norms with weekly cron, integrity signals, extra time), `ts_hire` (HR-HEXACO-1: IPIP-HEXACO 120 + 3 attention items; BAT-HR-SHORT/FULL; ts.hire.position; panel pages /positions, /profile, candidates, candidate report, compare, fairness; decisions; verification test; candidate feedback card; email templates; 12-month retention cron).
- eot_main config (outside the ship): ir.mail_server «Liara (sepehrtherapy.ir) - استعدادیاب» copied from sp_main server-to-server (credentials never shown), from_filter sepehrtherapy.ir (eot.ir senders do not match it); SMTP login tested OK.
- Reviews: risk review (Opus) found 2 high + 8 medium (non-sharing candidates leaked through order and the «strong» count; live fairness view could single out a person; invite text promised less than HR sees; retention promised but missing; mail server not pinned; emails sent before a batch could roll back; HR refresh could fail a candidate's submit; speed timings trusted) — all fixed and tested. Visual review: SCSS min(%,rem) broke the bundle (fixed), task player ran before DOM ready (fixed), requirement tables as cards on phones.
- Tests: tests_hire_engine.py 30 (pure), tests_hire.py 41 (ORM), ts_http_hire.py 35 (HTTP); older suites updated (source-instrument counts, clinical catalog excludes the employment-only HR instruments, HR menu item, brand suite answers only Likert batteries). Rehearsal eot_ts96 on merge 96e680e: 70 suites, 2560/2562 (2 known kavenegar inbox), guard UNCHANGED, portal UNCHANGED. Ship hr1: OK, eot.ir UNCHANGED (1049 pages).
- Clones: tools/prod/ts_db.sh switches mail servers off and drops the outgoing queue (also adopted by the clinic6 session).
- Open: translator/psychologist review of the questionnaire and WS-XW-v0; real norms (automatic at 100 completions per block); criterion validation with early-access employers; no employment panel exists on live yet (the super admin approves the first HR customer's panel).

## clinic7 — final polish (2026-10-12/13, LIVE)

- Credits page caps table: per counselor «بدون سقف» / «با سقف» radios + amount (required only for «با سقف», `data-ts-req` in ts_org.reveal_js); server stores 0 for no cap as before and now refuses «با سقف» without an amount (member page too). «اشتراک» alone → «اشتراک‌گذاری» / «قطع اشتراک‌گذاری» in 18 files (all meant sharing); contact page «راه‌های دیگر» h3 → h2; contact top-up page in the shots matrix; shots digit check ignores textareas.
- Clone eot_ts94: 9 suites 489/489; shots 435 files, only contact heading skip (fixed) and HR's pre-existing 404 on /my/assessments/battery/<id> for ts.hire.cand.http (also in the HR session's own shots eot_ts91 — for the HR session).
- Rehearsal eot_ts95: 1 failure (tests_pv2_15 expected «لغو»; now «قطع»). eot_ts98 was destroyed mid-run by another session's job with the same clone name: use distinctive clone names. Rehearsal eot_ts181 (commit 73aecca, incl. ts_onet/ts_tasks/ts_hire): guard UNCHANGED, portal UNCHANGED, unexpected failures 0. Ship clinic7: OK, eot.ir UNCHANGED.

## onb1 — sign-in (S-AUTH) and panels without approval (2026-10-12, built, not shipped)

- Owner decisions 2026-10-12: every panel is active when made; approval replaced by a first-week invitation limit (50 / 24 h for 7 days, self-service panels only, every invite surface; open-link joins not counted), a super-admin suspend («این پنل موقتاً متوقف شده است…»: no invitations, no new attempts, participants keep their results) and the back-office list «پنل‌های تازه (۷ روز)»; the licence is a badge (optional, edited by the member, reset on change, «پروانهٔ تأییدشده» after the EOT check, printed on reports only when verified; A5b kept with an explicit message); one mobile sign-in for talentsearch.ir. Design and owner actions: docs/onboarding/01_signin_and_approval.md.
- ts_core 20.0.2.0.0: states draft/active/suspended/closed (pilot, gated, approve/reject removed), self_service, suspend note/time, licence badge actions, res.partner.ts_name_unknown; migration pilot → active with one audit row each (live: workspace 7 → active, workspace 2 stays closed), pending members without a number → not_required, old self-service panels marked. ts_org/ts_panel/ts_hire/ts_brand: gates and approval copy removed everywhere, invite limit + calm quota line, suspend pages, «نام شما» where others see the name, panel terms v4, consent v5.
- ts_sms 20.0.2.0.0 (S-AUTH): /signup (alias /login, /web/login on website 4 in place, /web/login?email=1 the e-mail way, /web/signup → /signup except /join/ and tokens; only while SMS codes can be sent); two states without reload (JSON with X-TS-Auth, plain POST fallback), WebOTP SMS line «@talentsearch.ir #code», no name step, 30-day cookie for «این دستگاه شخصی من است» (browser-session otherwise; e-mail sign-in, eot.ir, internal users unchanged; long sessions survive the 7-day clean-up up to 30 days), staff numbers refused, one number per account (/my/phone «taken»), once-offer to link a mobile, 10 wrong codes → 15-minute lock per number.
- Tests: tests_onb1.py (ORM, 67), ts_http_onb1.py (HTTP, 51), 60+ older suites updated (no approved_on/pilot fixtures, badge instead of gate, suspend instead of approve/reject, no name step); all affected suites green on kept clone eot_ts97. Found and fixed while testing: /web/login rendered a page without a form while SMS was off (now the stock e-mail sign-in), resend countdown could show 61 s.
- Rehearsal eot_ts981 (slot 1, INSTALL ts_brand, UPGRADE ts_core,ts_website,ts_assessment,ts_org,ts_sms,ts_talent,ts_panel,ts_battery,ts_brand,ts_hire): 68 suites, 2486/2486 checks, guard UNCHANGED (1049 pages), portal UNCHANGED, unexpected failures 0. The clone stays served on :8073.
- Incident (tooling): a first attempt named eot_ts98 collided with a slot-0 rehearsal of the same name (another session): `ts db clone` dropped and re-created that database mid-run. Both runs were abandoned; the other session re-ran as eot_ts181. Rule: check `ts slots` and pick a clone name no slot uses before `ts rehearse`.

### onb1 fixes (2026-10-13, risk review + screenshot review)
- Sign-in: one validator `ts_core/safe_url.local_path` for every next/redirect (rejects schemes, `//`, backslash, control chars, encoded `/%2f /%5c /%09`; decodes once and re-checks); signin.js navigates only to same-origin paths. OTP to a number owned by another account: format/cooldown/limits first, nothing sent, a blocked row refused at verify with the neutral «این کد پذیرفته نشد…». Signup lock per (phone, IP hash): 10 wrong / 60 min → 15 min; per-phone ceiling 30 / 24 h → 1 h; 5 tries per code unchanged (ts_sms 20.0.2.0.1 rebuilds ts_signup_lock). 30-day cookie only for share users on the talentsearch website; ts_session_mode cleared on every login and logout; sid rotation checked. /web/signup on TS only with a token or a /join/ redirect (else 303 → /signup). Odoo 20 logout is POST-only: header, /my, panel and org logout links are now POST forms.
- Suspended/closed panels: no participant SMS (invitation, result), no reminders (cron or manual), no HR e-mail; only the suspend/close notices go out.
- «در این مرکز مشاوره می‌کنم» needs a self-declared licence number; audit row `licence_self_declared`, `practising_since`, back-office list «مالک مشاور شد (بررسی پروانه)»; solo psychologist panels need the number at creation. pre-migrate: NULL verification_state with a licence → pending.
- Names: staff never see phone-only names (campaign prefill via ts_known_name, reports via client/invitee name, membership refused for a name-unknown partner); invite accept no longer copies invitee_name into the account.
- Screenshot review: /panel/notifications → /my/notifications (was 404), skip link hidden until focused, empty workload shows ۰, licence preview/report/members list show «پروانهٔ تأییدشده» only when verified, solid primary «دریافت کد»/«ورود», members invite note without «تأیید», /pricing and /contact headings h2. Left as asked: duplicate «دعوت تازه», empty-state redesign.
- Rehearsal eot_ts983 on 161e841 (slot 1, same INSTALL/UPGRADE): 68 suites, 2510/2510, guard UNCHANGED (1049 pages), portal UNCHANGED, unexpected failures 0; served on :8073. eot_ts981/eot_ts982 dropped; eot_ts98 left (idle pooled connections from another Odoo process).
- Merge of main (clinic7, live) 10c0dbf: conflicts only in notify_texts.py (clinic7's «قطع اشتراک‌گذاری» wording + onb1's suspend/history labels) and this log; clinic7 adds no gate, approval copy, name step or /web/login link. Rehearsal eot_ts984 (INSTALL ts_brand, UPGRADE onb1's list + ts_billing): 70 suites, 2629/2629, guard UNCHANGED, portal UNCHANGED, unexpected failures 0; served on :8073, eot_ts983 dropped.
- Visual re-check at 375 px: the skip link showed in signed-in shots because ts_shot.py pressed Tab (focus check) and shot the focused link; the harness now blurs first and flags «skip-link-visible», and the link carries visually-hidden-focusable (rest state !important). /panel copy without «تأیید» («هر پنل همان لحظهٔ ساخت فعال است.»). `ts shots` now shows the real mobile sign-in: ts_ui_matrix.sh turns SMS on for the clone with Kavenegar at 127.0.0.1:9 (dead) and a dummy key, invitation/result SMS off, and seeds a pending code so the matrix captures the code step (POSTSHOT /signup/send). Persian digits in the public mocks (/, /schools, /assessments sample); the remaining ascii-digits on panel pages are the fixture panel name «S19 http».
- Rehearsal eot_ts985 (636bc19): unexpected failures 1, tests_onb1 ended in a traceback at M05, whose ALTER TABLE ts_workspace_member ran beside the served clone (passed on eot_ts983/984). M05 now uses a temporary shadow table (2f7045f). Rehearsal eot_ts986 (same INSTALL/UPGRADE incl. ts_billing): 70 suites, 2630/2630, guard UNCHANGED, portal UNCHANGED, unexpected failures 0; `ts shots eot_ts986` (375, 1280): only the intended /nist-404 page flagged; served on :8073, eot_ts984/985 dropped.

## onb2 — one-tap invitations and test first (2026-10-13, built, not shipped)

- Spec: Project doc claude/ONBOARDING_RESEARCH_AND_DESIGN.md §5 P1–P3, P7 and §7 O2/O3; design and behaviour: docs/onboarding/02_invites_and_guest.md. Branch `onb2` from main 6152b42 (onb1, live).
- New module `ts_onboard`: invitation welcome screen (GET never consumes or binds; the POST «موافقم و شروع می‌کنم» is the consent, consent version recorded, no second consent page), minors on one screen (guardian tick + the child's own «من هم موافقم»), `delivered_via` sms/email/manual/campaign with the number or address the message reached, sign-in scoped to one invitation by the SMS or e-mail that carried the link (one central check in `ir.http._pre_dispatch`, talentsearch.ir only; anything else → S-AUTH with the number masked), device binding (signed `ts_dev` cookie, sha256 on the invitation; another browser gets a code to the invited number, masked), mismatch notice with «خروج و ورود با شمارهٔ دعوت‌شده», 12-character short codes, rate limits per hashed address (/invite/ and /i/ /j/ 60 a minute, /c/ 120; hits counted in their own transaction so unknown codes count), one neutral page for unknown or closed links, Referrer-Policy no-referrer + Cache-Control no-store on invite/take/short/start pages.
- Test first: `ts_guest_ok` on ts.instrument (constraint: published, adult, general, single-mode, ≤ 40 statements, not invite-only, not TALENT-INV-15) set by a data step on ONE starter. Starter: inventory_002 «فهرست ارجمندی», 17 statements, ~3 minutes — the shortest general adult self-scoring questionnaire; the shorter ones are a distress screen (inventory_007, 4 statements), employment questionnaires and the talent inventory, and inventory_019 (also 17) sits in «بیتابی روانی». /start screen with the age button, «کمتر از ۱۸ سال دارم» → /start/under-18, guest attempt keyed by a signed HttpOnly SameSite=Lax Secure cookie (never in a URL), autosave/resume, 5 new guest attempts an hour and 200 answers a minute per hashed address, result gate with S-AUTH inline, atomic claim at the gate only (row lock; second or racing claim does nothing), optional name on the report while the name is unknown, «سنجهٔ بعدی» and «فرستادن نتیجه برای مشاورتان», hourly 48-hour clean-up. Home hero: one primary action «شروع سنجهٔ رایگان» (real minutes) + text links for centres, companies, schools; the catalog card and detail page of the starter open its start screen.
- Funnel `ts.funnel.event` (step, kind of entry, instrument or invitation, salted session hash, website, time; no personal data): start screen, guest started, first answer, finished, gate shown, signed in at gate, report viewed; invitation welcome viewed, accepted, first answer, finished. First answer / finished are counted by the attempt model for every player (one indexed probe, one insert). Back office «قیف ورود» pivot/list, managers only, 180-day retention.
- ts_hire: the optional gender and age-band questions moved after the last part (once, «رد شدن»); migration marks earlier candidates as asked. ts_sms/ts_assessment/ts_brand/ts_website: masked known number in S-AUTH, the player's address for the guest player, 12-character codes, header modes for /start.
- Tests: tests_onb2.py (ORM, 42), ts_http_onb2.py (HTTP, 97: GET-does-not-consume, scope on every route family, device binding, mismatch, minors, fairness at the end, neutral page, no-store, rate limits incl. unknown tokens, cross-token guest isolation, claim idempotency, answer limit, both funnel paths, eot.ir 404), registered in tools/vps/ts_rehearse.sh; older suites updated (ts_http_hire, ts_http_org, ts_http_signup, ts_http_panel, tests_brand, ts_http_pv2_6, ts_http_sms). On kept clone eot_ts989: tests_onb2, ts_http_onb2, ts_http_org, ts_http_panel, ts_http_signup, ts_http_hire, tests_brand, ts_http_brand, ts_http_pv2_6, ts_http_sms, ts_http_onb1, ts_http_pv2_7 all green.
- Shots (`ts shots eot_ts989`, 375 + 1280): welcome (centre, employment with the timed line, minor), /start, under-18, guest player, gate, masked-code screen and the claimed report (own login, ts_ui_matrix.sh copies the owner's password file); only the intended /nist-404 flagged. Visual fixes during the build: solid primary action, «***» mask (bullets read as Persian zeros), .ts-bdi direction, one pronoun per screen.
- Rehearsals: eot_ts988 (3df4a90) 1 unexpected failure (ts_http_panel expected the old hero); eot_ts989 (e48cb71) 72 suites, 2754/2754, guard UNCHANGED, portal UNCHANGED, unexpected failures 0; then the spec gaps above were closed (1c699a4).
- «شمارهٔ دیگری دارم» (d3975a7): the masked-number pages offer the ordinary sign-in with any number (`/signup?other=1`); the invitation still checks who may accept it (ts_http_onb2 D08–D10).
- take1 shipped to main during the build (05:07). Merge f2c1f40 (main 46429e2 into onb2): take1's 5-per-page paging, review rows and skip notes kept with the guest player's address (guest controller uses the same helpers); take1's invite context and «تو» in S-AUTH with the masked number; take1's truthful «what the employer sees» in the position terms; the welcome screen takes effort_facts, invite_card/state_card, the instant-result line (`id="ts-invite-facts"`) and the crisis line «اورژانس اجتماعی ۱۲۳ یا صدای مشاور ۱۴۸۰»; an invitation accepted by another account and unknown links answer take1's explained link 404 (onb2's own neutral page dropped; ir.http `_handle_error` adds no-referrer/no-store there); detail-page xpath by `#ts-detail-signup` (ts_talent changes its t-if); the S-AUTH intro xpath drops take1's second paragraph and keeps «تو». ts_http_flow counts the starter card's /start/<slug>. Eight suites (take1 + onb2) re-run green on kept clone eot_ts991 (fresh dump after take1).
- Rehearsal eot_ts990 was started on 99ba318 and stopped at its restore step (before any test) to add «شمارهٔ دیگری دارم» and the merge; its half-made database was dropped.
- Visual review on eot_ts991 (375, 1280): the share list inside «بیشتر» is shown open (no second toggle), «شمارهٔ دیگری دارم» without a repeated id (5f80ba0). Rehearsal eot_ts992 on 5f80ba0 (slot 1, INSTALL ts_onboard, UPGRADE ts_core,ts_website,ts_assessment,ts_org,ts_sms,ts_talent,ts_panel,ts_battery,ts_billing,ts_brand,ts_onet,ts_tasks,ts_hire): 72 suites, 2818/2818, guard UNCHANGED (1049 pages), portal UNCHANGED, unexpected failures 0; served on :8073; eot_ts988–991 dropped.
- `ts shots eot_ts992` (375, 1280): 109 files, only the intended /nist-404 flagged. Not shipped, not pushed.

### onb2 risk-review fixes (2026-10-13, built, not shipped)
- HIGH 1, delivery secret: every invitation SMS / e-mail / reminder the system sends carries a fresh secret (16 random bytes, 22 url-safe characters; `/i/<code>/<secret>` → `/invite/<token>?d=<secret>`, e-mail `?d=`), made in a send window around the send paths; only digests stored (`dlv_sms_hash`, `dlv_email_hash`); never in invite_url() outside the window (panel pages, copy buttons, QR, exports), Kavenegar log row masked (`kv_secret`), access log line redacted. The welcome form carries it as a hidden field; only the POST checks it (constant-time, per channel). No-typing sign-in needs it and only into an account made now or a Talent Search phone-only account whose login is the invited number with no eot.ir activity (orders, invoices, payments, events, courses, eot.ir visits, another website); anything else: a code to the invited number, or S-AUTH without a number. A new message replaces its channel's secret; a failed one keeps the old.
- HIGH 2: no number is linked to an account from a scoped session, except the account the flow made for this invitation within the hour that holds nothing else (no other invitation/attempt, membership, other client, written message, partner link, eot.ir activity); otherwise P's own account (or a new phone-only one) and the calm page /my/invitation-elsewhere.
- HIGH 3: the scope guard fails closed: a scoped session on any other or unresolvable website is logged out (session destroyed; GET → 303 to itself as a visitor, else 403); on talentsearch.ir JSON-RPC, /json, /mail, /web/session/*, /web/dataset and any non-GET outside the allow-list answer 403; `_serve_fallback` (website pages, attachments) is guarded too.
- MEDIUM: e-mail match escaped (`%`, `_`) plus exact lower-case comparison; device binding only with «این دستگاه شخصی من است» (ticked by default: 30 days; unticked: browser-session cookie + 12 h on the server), ends when the invitation is finished; compare_digest everywhere; cookies always carry their expiry (Odoo's Response.set_cookie adds one year otherwise).
- LOW: /websocket and /web/image out of the scope allow-list; known numbers by their last four digits «*** ۴۵۶۷» (asterisks: the shots showed bullets reading as Persian zeros in Vazirmatn); the claim needs the gate's session mark and next == /start/result (else the explicit button); funnel rows hold only step, channel, instrument, salted hash, day and hour (`_log_access = False`; no invitation/website columns), robots and cookie-less repeats (once per hashed address and minute, no session write) skipped; rate hits in the request's own transaction, the miss's 404 rendered inside the request (`invite.counted`), no second cursor.
- Client addresses (prod): nginx sends X-Forwarded-For/Proto/Host and X-Real-IP; Odoo 20 runs ProxyFix (x_for=1) only with X-Forwarded-Host, which nginx sends (robots.txt says https://); hashed addresses of onb1 code requests and audit rows on prod are distinct per visitor. remote_addr is the real client; the onb1 code limits and the onb2 limits key on it.
- Main moved during the fix (take2 live): merge 611d756 keeps the fairness questions at the end (take2's invitation-page block dropped) and carries take2's owner decisions to the welcome screen: the one sharing tick `ts_org.share_tick` (same words as /c), unticked under another name (8dfb197).
- Tests: tests_onb2 64, ts_http_onb2 126 (delivery secret end to end through the fake Kavenegar and the real e-mail template, copied link → code, scope on JSON/images/websocket/pages, eot.ir logout, device tick, HIGH 2 both ways, gate mark, funnel robots and cookie-less visits); ts_http_sms and ts_http_pv2_6 accept the secret in the SMS link and check the panel page never shows it. Clone eot_ts992 (kept, then dropped): onb2, signup, sms, onb1, brand, org, hire, battery, pv2_6, pv2_7, panel, flow green before and after the merge.
- Rehearsal eot_ts993 was restored and stopped before any test (port 8073 still held by eot_ts992) and dropped. Rehearsal eot_ts994 on 8dfb197 (slot 1, INSTALL ts_onboard, UPGRADE ts_core,ts_website,ts_assessment,ts_org,ts_sms,ts_talent,ts_panel,ts_battery,ts_billing,ts_brand,ts_onet,ts_tasks,ts_hire): 72 suites, 2909/2909, guard UNCHANGED (1049 pages), portal UNCHANGED, unexpected failures 0; served on :8073. Not shipped, not pushed.
- `ts shots eot_ts994` (375, 1280): 109 files, only the intended /nist-404 flagged; looked at the welcome screens (share tick, «این دستگاه شخصی من است», minors' screen), the result gate and the masked-code screen («*** ۰۳۷۵»).

### onb2 closing items (re-review OK)

- eot.ir activity check (fail-closed) also counts crm.lead, helpdesk.ticket, survey.user_input (partner child_of), forum.post (create_uid) and person-written mail.message (comment/email) on non-`ts.*` records; each model only `if in env`; a full scan page (200) counts as activity.
- Scoped pages get no `bus_info`/`websocket_worker_version` in the frontend session info, so the bus worker never starts (no reconnect loop, no log noise). Rate limiter: `pg_advisory_xact_lock(hashtext('ts_rate:'+key))` before the count, same transaction, no second cursor. Kavenegar outbox import masks `/i/<code>/<secret>` and `?d=` secrets (`mask_link_secrets`; length and parts from the original text).
- Tests: tests_onb2 Z01–Z06 (activity models, messages, crm.lead, fail-closed, advisory lock, outbox mask); ts_http_onb2 8b: a scoped session starts, answers and finishes the timed tasks of an HR battery over HTTP, another person's token gets 403/404, scoped Likert answer POST. Commit 137807a; origin/main unchanged.
- eot_ts994 dropped. Rehearsal eot_ts995 on 137807a (slot 1, INSTALL ts_onboard, UPGRADE ts_core,ts_website,ts_assessment,ts_org,ts_sms,ts_talent,ts_panel,ts_battery,ts_billing,ts_brand,ts_onet,ts_tasks,ts_hire,ts_kavenegar): 74 suites, 2984/2986 (the two known tests_kavenegar inbox failures only), guard UNCHANGED, portal UNCHANGED, unexpected failures 0; served on :8073. Not shipped, not pushed.

## take1 — test-taking UX pass (2026-10-13, LIVE)

- Research (docs in session /home/claude/ux7/research_notes.md, summary in the Project report «Test-taking UX audit»): radio-style options, few items per page on phones, honest progress, stated time, transition interstitials, no silent skips, OTP autofill (WCAG 3.3.8), result promise, short consent; WCAG 2.2 AA, ISO 9241-110/-11, GOV.UK question pages, ITC 2022.
- Live funnel (read-only): 131 attempts, 123 done (114 of them imported); of 8 unfinished real attempts 7 stopped with 0 answers (at consent or the first page). Too small for statistics; first-screen motivation was the priority.
- New shots mode `ts shots DB take` (ts_ui_matrix.sh + ts_ux_seed.py take branch): 73 participant pages/states at 360/390/1280, dark 390, phone-fold captures (TS_SHOT_FOLD).
- Audit (3 auditors + writer): 150 findings (2 sev4, 37 sev3) + 66 copy items; fixed by 3 implementers + integrator + verification round (99 verified fixed, owner items listed).
- Owner decisions 2026-10-13: crisis line «اورژانس اجتماعی ۱۲۳ یا صدای مشاور ۱۴۸۰» everywhere (was ۱۱۵); «این دستگاه شخصی من است» stays ticked; questionnaire player 5 items per page, balanced.
- Main changes: invite/c first screen (who, size, time, result promise, privacy, button); shared state card for expired/declined/withdrawn/closed/full; one explanation page (404) for unknown/foreign/closed links with sign-in; wrong-account invite puts sign-out first; hiring invite/consent/task pages state one truthful «what the employer sees»; one minute estimate everywhere (sum of parts); signup code step above the keyboard, LTR phone groups; consent short first screen with details folded (same words, same version), one focused error summary, ticks restored; player 5/page with sticky prev/next, clear selected state (light+dark), one-time skip notice, review grouped by page with jump links; battery «ادامهٔ مجموعه», per-instrument progress; talent: error states, nudge tone, finish state, report summary first; timed tasks: overview (rules, recorded page exits, extra time), save queue with retry, one focus-loss event per leave, resume shows time left, exit label «بازگشت (زمان می‌گذرد)».
- Clones: eot_ts301/302/304 (slot 2), suites 827/828 then green; rehearsal eot_ts303 (slot 2, commit 2f5e99e): guard UNCHANGED, portal UNCHANGED, unexpected 0. Ship take1: OK, eot.ir UNCHANGED.
- Open for the owner: factor descriptions vs names on detail pages, deficit-toned report texts, statement spelling in TALENT-INV-15, text alternatives for figure items in timed tasks, consent wording simplifications (need a new consent version), /c→/invite double page, pre-checked sharing tick on a wrong-name invite, automatic SMS reminders (research: +3.6% per reminder).

## take2 — content v2 and owner-delegated decisions (2026-10-13, LIVE)

- Owner 2026-10-13: participant data on the live site are samples; the tests are correct; Claude writes the content and decides the open items, no separate review.
- Content v2 (TS-CONTENT-2.0): addons/ts_assessment/data/content_v2/<code>.json for all 33 scored instruments (131 factors, 393 bands) and addons/ts_talent/data/content_v2/TALENT-INV-15.json — new factor definitions (matching the items), participant texts in second person, strengths first (register shoma / tu / parent), cleaned counselor texts, 2–3 talk points per band («پیشنهاد برای گفت‌وگو»), crisis line in the highest-distress bands, renamed opaque factor names (e.g. inventory_003 الف/ب…), talent statement spelling (statement 12 reworded, meaning kept). Where book texts contradicted the item scoring, the scoring decided.
- Loader overlay (`_ts_content_overlay`, switch `ts_assessment.content_v2`): only approved, complete files; v1 hashes unchanged; scoring-identity check per instrument (contract fingerprint) before switching; new versions, open attempts moved with answers remapped by qid; finished reports keep their stored texts (content_format book|v2 on band and result). textfmt.py (ORM-free split_interpretation/counseling_terms); export tool tools/content/ts_content_export.py. Fixes: superseded flag on every load, group report keyed by (instrument, factor code) and 'medium' counted, pre-line in panel report text.
- Decided UX items: consent v6 (TS-CONSENT-1405-07-21-v6, assent TS-MINOR-1405-07-21-v3) with a five-line plain summary and the full text folded (same rights and facts); /c join accepts and goes straight to consent; wrong-name invite leaves the sharing tick unticked; text alternatives for timed-task figures and options; Sepehr sms_name «سپهر هیجان اندیش» set live (tools/prod/tests_zlive_sepehr_smsname.py).
- Clone eot_ts305 (slot 2): loader `content_v2: 33, content_errors: 0`, 393 v2 bands; suites green (tests_assessment 60, tests_talent 68 after fixes). Rehearsal eot_ts306 (slot 2, commit da4a9c2): guard UNCHANGED, portal UNCHANGED, unexpected 0 (2774/2776, 2 known Kavenegar inbox).
- Ship take2: upgrade rc=0, live up (all probes 200); guard reported one difference: eot.ir /sitemap.xml lastmod 2026-10-12 → 2026-10-13 (Odoo regenerates the sitemap after the restart on a new day; no page content changed), so the ship line reads NOT OK by rule. Live: 34 of 40 published instruments on TS-CONTENT-2.0 (the 6 others are HR/timed tasks, unchanged).
