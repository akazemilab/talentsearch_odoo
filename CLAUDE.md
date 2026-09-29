# talentsearch_odoo - working rules

Talent Search (talentsearch.ir) by EOT = **website 2** (xmlid `ts_website.website_ts`,
db id 4) inside `eot_main` on eot-odoo-prod, next to eot.ir (website 1, theme
`theme_eot_custom`, repo akazemilab/theme_eot_custom). Staging host: ts.innerquest.me.
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

## Workflow
Source of truth is /root/talentsearch_odoo on the VPS (pushes with deploy key
`vps-talentsearch-rw`); the cloud session can read the GitHub repo but cannot push.
`ts sync` rsyncs to /opt/odoo/talentsearch on prod. Long jobs: `ts bg NAME CMD`,
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
