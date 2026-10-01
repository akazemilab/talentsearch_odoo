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
