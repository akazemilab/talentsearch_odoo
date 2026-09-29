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
