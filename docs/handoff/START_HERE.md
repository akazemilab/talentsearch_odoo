# START HERE: استعدادیاب (talentsearch.ir), whole project (2026-10-14)

Read in this order: this file, RULES.md, TOKENS_AND_DELEGATION.md, FACTS.md (generated). Then only the doc of the area you work on.
Scope: talentsearch.ir only. Never eot.ir, never app.sepehrtherapy.ir (RULES.md section 1).

## What it is
Persian talent / personality / counseling assessment platform on Odoo 20 Enterprise, db eot_main (shared instance with eot.ir),
website 4. Repo talentsearch_odoo (public), source of truth /root/talentsearch_odoo on the tools VPS. Live code /opt/odoo/talentsearch
on prod, changed only by `ts ship`.

## Product areas and where they are documented
| Area | Modules | Doc |
|---|---|---|
| Public assessments, results, signup | ts_core, ts_website, ts_assessment, ts_talent | docs/talent_assessment_spec.md |
| Organizations, clinicians, panels | ts_org, ts_panel | docs/panel_v2/, docs/portal_v3/ |
| SMS (Kavenegar) | ts_kavenegar, ts_sms | CLAUDE.md "SMS" section, docs/clinic/05_sms_texts.md |
| Clinic: batteries, prepaid billing, branding | ts_battery, ts_billing, ts_brand | docs/clinic/ (01 architecture, 02 decisions, 04 billing) |
| HR hiring (early access) | ts_onet, ts_tasks, ts_hire | docs/hr/01_architecture.md |
| Onboarding (OTP, invites, first session, pages) | ts_onboard | docs/onboarding/HANDOFF.md |
| Career discovery | ts_career | IMPLEMENTATION_LOG (grep career) |
| UX copy and audits | n/a | docs/ux_writing/, docs/ux_audit/ |

## Status (from the 2026-10-12 handoff, verified 2026-10-14)
- Live commit d5f60a4 (main 6b85fc7 adds docs only). `ts live`: talentsearch.ir 200, eot.ir 200, odoo20 active, 0 journal errors.
- All clinic phases 1-6, HR hiring, onboarding LIVE. No employment (HR) panel exists yet. Sepehr's panel is prepaid, no counselors invited yet.
- No build phase is pending. What remains is owner input and hardening (below).

## Open items
Owner: Kavenegar Verify Lookup template (`@talentsearch.ir #%token`); look at the Kavenegar outbox for 2026-10-13 13:48-13:56
(possible test SMS from a clone); pin live odoo20 to eot_main (db_name/dbfilter); counselor titles and licences; clinician review
of the six batteries; decide the 50 book sentences and 3 band-text questions (docs/clinic/03, 06); SMS short name for Sepehr
(<= 18 chars); activate Enterprise (trial ends 2026-11-02); rights record for TALENT-INV-15; rotate old credentials.
Engineering (no owner input needed, bundle into one session): restore test + off-server backup; install wkhtmltopdf on prod for real PDFs;
translator + psychologist review of HR questionnaire wording; eNamad before any payment gateway; CRM bridge branch is NOT shipped.

## First commands of any session
`ts slots` / `ts live` / `ts check` / `git log --oneline -5` (vps_git) / `bash tools/vps/handoff_facts.sh`.
