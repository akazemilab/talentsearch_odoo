# FACTS (generated, do not edit by hand)

Generated: 2026-10-14T03:21Z from commit 6b85fc7 on branch main.
Regenerate: `bash tools/vps/handoff_facts.sh`. Scope: talentsearch.ir only.

## Modules (addons/*, manifest version, python lines, test files)

| module | version | py lines | in-module tests (suites live in tools/prod: tests_*.py, ts_http_*.py) | depends |
|---|---|---|---|---|
| ts_assessment | 20.0.3.0.0 | 1581 | 0 | ts_core,ts_website,portal,website |
| ts_battery | 20.0.2.0.0 | 1449 | 0 | ts_panel,product |
| ts_billing | 20.0.1.0.0 | 1552 | 0 | ts_battery,account,product |
| ts_brand | 20.0.1.0.0 | 1472 | 0 | ts_billing,sms,web |
| ts_career | 20.0.1.1.0 | 791 | 0 | ts_onboard |
| ts_core | 20.0.2.0.0 | 676 | 0 | base,mail,portal |
| ts_hire | 20.0.1.1.0 | 1224 | 0 | ts_brand,ts_tasks,ts_onet,mail |
| ts_kavenegar | 20.0.1.0.0 | 1576 | 0 | sms,phone_validation |
| ts_onboard | 20.0.2.0.0 | 3773 | 0 | ts_hire,ts_sms,website |
| ts_onet | 20.0.1.0.0 | 422 | 0 | ts_core,website |
| ts_org | 20.0.5.0.0 | 1610 | 0 | ts_assessment |
| ts_panel | 20.0.20.0.0 | 7757 | 0 | ts_talent,ts_sms |
| ts_sms | 20.0.2.0.1 | 1120 | 0 | ts_kavenegar,ts_org,ts_assessment,ts_website |
| ts_talent | 20.0.1.0.0 | 1929 | 0 | ts_assessment,ts_org,ts_sms |
| ts_tasks | 20.0.1.0.0 | 1266 | 0 | ts_battery,ts_onet,website |
| ts_website | 20.0.4.1.0 | 564 | 0 | website,auth_signup,crm,website_crm,account,ts_core |

## Routes (controllers, count per module)

- ts_assessment: 11
- ts_battery: 18
- ts_billing: 3
- ts_brand: 13
- ts_career: 6
- ts_hire: 16
- ts_kavenegar: 2
- ts_onboard: 37
- ts_org: 22
- ts_panel: 91
- ts_sms: 12
- ts_talent: 10
- ts_tasks: 8
- ts_website: 1

## Docs

- docs/IMPLEMENTATION_LOG.md
- docs/OPS.md
- docs/clinic/01_architecture.md
- docs/clinic/02_decisions.md
- docs/clinic/03_terms_in_book_texts.md
- docs/clinic/04_billing_brief.md
- docs/clinic/04_billing_stages.md
- docs/clinic/05_sms_texts.md
- docs/clinic/06_data_issues.md
- docs/handoff/CLIENT_HANDOFF.md
- docs/handoff/FACTS.md
- docs/handoff/RULES.md
- docs/handoff/START_HERE.md
- docs/handoff/TOKENS_AND_DELEGATION.md
- docs/hr/01_architecture.md
- docs/onboarding/01_signin_and_approval.md
- docs/onboarding/02_invites_and_guest.md
- docs/onboarding/03_panel_first_session.md
- docs/onboarding/HANDOFF.md
- docs/panel_v2/01_research.md
- docs/panel_v2/02_feature_catalog.md
- docs/panel_v2/03_ia_and_ux.md
- docs/panel_v2/04_data_model.md
- docs/panel_v2/05_permissions_matrix.md
- docs/panel_v2/06_gap_analysis.md
- docs/panel_v2/07_build_plan.md
- docs/panel_v2/08_design_system.md
- docs/panel_v2/09_ui_benchmark.md
- docs/panel_v2/HANDOFF.md
- docs/portal_v3/01_gap_list_and_plan.md
- docs/portal_v3/02_handoff.md
- docs/talent_assessment_research.md
- docs/talent_assessment_spec.md
- docs/ux_writing/glossary.md
- docs/ux_writing/voice.md

## Helper agents (.claude/agents)

- ts-risk-reviewer.md
- ts-runner.md
- ts-scribe.md
- ts-shipper.md
- ts-shots.md
- ts-ux-auditor.md
- ts-ux-writer.md
- web-researcher.md

## Toolkit scripts

- tools:
- content
- fonts
- gw
- konkur
- prod
- vps
- 
- tools/prod:
- __pycache__
- clinic_seed_sepehr.py
- pv2_fixtures.py
- tests_assessment.py
- tests_battery.py
- tests_billing.py
- tests_brand.py
- tests_career_engine.py
- tests_edge.py
- tests_hire.py
- tests_hire_engine.py
- tests_kavenegar.py
- tests_onb1.py
- tests_onb2.py
- tests_onb3.py
- tests_org.py
- tests_org_resp.py
- tests_panel.py
- tests_pv2_0.py
- tests_pv2_1.py
- tests_pv2_10.py
- tests_pv2_11.py
- tests_pv2_12.py
- tests_pv2_13.py
- tests_pv2_14.py
- tests_pv2_15.py
- tests_pv2_16.py
- tests_pv2_17.py
- tests_pv2_18.py
- tests_pv2_18b.py
- tests_pv2_2.py
- tests_pv2_3.py
- tests_pv2_4.py
- tests_pv2_5.py
- tests_pv2_6.py
- tests_pv2_7.py
- tests_pv2_8.py
- tests_pv2_9.py
- tests_signup.py
- tests_stage1.py
- tests_talent.py
- tests_talent_engine.py
- tests_zdebug.py
- tests_zdebug_brand.py
- tests_zdebug_talent.py
- tests_zlive_sepehr_checklist.py
- tests_zlive_sepehr_prepaid.py
- tests_zlive_sepehr_smsname.py
- tests_zseed_sepehr.py
- tests_zseed_sepehr_live.py
- ts_db.sh
- ts_domain.py
- ts_flowlib.py
- ts_guard.py
- ts_http_battery.py
- ts_http_billing.py
- ts_http_brand.py
- ts_http_career.py
- ts_http_edu.py
- ts_http_flow.py
- ts_http_hire.py
- ts_http_kv.py
- ts_http_onb1.py
- ts_http_onb2.py
- ts_http_onb3.py
- ts_http_org.py
- ts_http_panel.py
- ts_http_pv2_0.py
- ts_http_pv2_1.py
- ts_http_pv2_10.py
- ts_http_pv2_11.py

## Recent commits

- 6b85fc7 docs: onb3 LIVE in HANDOFF
- d5f60a4 Merge branch 'main' of github-talentsearch:akazemilab/talentsearch_odoo into onb3
- f0608c2 onb3: fix career1 merge conflicts (norm rebuild excludes career, preview, voided; career hero entry is a quiet text link)
- 71c7ead ts_career sitemap: Odoo 20 request website (env.website)
- 7ad8add ts_career: /career in talentsearch.ir's sitemap only (guard: eot.ir sitemap must not change)
- febadff Merge branch 'main' of github-talentsearch:akazemilab/talentsearch_odoo into career
- 49ba27b ts_career 20.0.1.1.0
- a0ff540 ts_career precision: CAREER-MATCH-v2 (interest shape + top-code congruence, neutral for unchecked domains, gated short list of 5-10 with at most 4 per area), results grouped by area, full list behind a link
- ca255ee Onboarding handoff (onb1/onb2 live, onb3 built)
- 7b3aba9 Merge main (career1) into onb3
- c0c6e15 log: career1 shipped (free career match)
- a84abb3 Merge branch 'main' of github-talentsearch:akazemilab/talentsearch_odoo into career
- 909c766 ts_career risk fixes: no result SMS per module, erase removes the run, hiring norms exclude career takes, service-only carried consent stated on the button, site check first, cap guard, create race
- 3c6e46d tests_assessment: the free career instruments are not source instruments
- 58df92d Merge branch 'main' of github-talentsearch:akazemilab/talentsearch_odoo into onb3
