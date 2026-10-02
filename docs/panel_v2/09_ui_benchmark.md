# 09 — UI/UX benchmark and design system v2 (1405-07-10 / 2026-10-02)

Owner request: benchmark, then fix the UI/UX of the panel, the participant portal and the whole talentsearch.ir site for
phone and desktop; the panel is free, a paid Pro feature («همیار تفسیر», an interpretation copilot for centres) is coming;
every page fully Persian (words and digits), good Persian type.

## 1. Baseline (headless shots of 49 routes × 375/1280 px, clone eot_ts70, before any change)

Machine audit (`tools/vps/ts_shot.py --matrix`): 40 problem rows out of 98. Real findings:

| # | Finding | Where | Severity |
|---|---------|-------|----------|
| B1 | **The panel menu was invisible on desktop.** `panel.js` set `hidden` on the menu list for every width and Bootstrap's `[hidden]{display:none!important}` beat the desktop CSS. Members navigated by URL or through the dashboard tiles only | every panel page ≥ 992 px | high |
| B2 | Marketing header (7 menu items + 2 buttons) rendered on panel/portal pages; wrapped to two lines at 1280 px inside the panel | panel, /my | medium |
| B3 | Full marketing footer (4 columns, ~600 px tall) under every questionnaire page and every panel page | /take, panel, /my | medium |
| B4 | Stock Odoo sign-in page: English `<title>` "Login", English placeholders, "Use a Passkey", "- or -" | /web/login | high (first screen for staff) |
| B5 | ASCII digits in dates, codes, counters and anywhere Odoo formats numbers (`۰` only where a template called `fa_digits`) | site-wide | high (owner rule) |
| B6 | One typeface (Vazirmatn) at one weight scale; headings and body not distinguishable at a glance; hero kicker 3.7:1 contrast | public pages | medium |
| B7 | Home and audience pages built from identical 3-card rows; pricing page was a quote form, no statement that the panel is free | /, /pricing | medium |
| B8 | Panel on phones: the menu button sat below the workspace card, no quick way back to home/clients; tables fold to cards but values and labels run together | panel ≤ 991 px | medium |
| B9 | Clients page shows the whole "saved views" form before the list | /clients | low |
| B10 | Questionnaire page: progress bar barely visible, "next page" button not reachable without scrolling past ten items | /take | medium |

Everything else measured clean: no horizontal overflow at 375 px, one h1 per page, all inputs labelled, RTL on every page.

## 2. References (what was borrowed, not copied)

- Persian consumer apps (Divar, Snapp, Tapsi): bottom tab bar with 4–5 destinations on phones, 44 px targets, Persian digits
  everywhere including prices and times, one-column flows.
- Persian B2B back offices (Digikala seller centre, Hesabfa): right rail navigation on desktop, dense tables that become
  label/value cards on phones, status chips, a compact top bar inside the app instead of the marketing menu.
- Assessment platforms (TestGorilla, Thomas International result pages): bands in plain language, "what this does not
  mean" next to the score, no radar charts for lay readers.
- Restraint from Linear/Stripe dashboards: one accent colour, typography carries hierarchy, empty states are an invitation.
- WCAG 2.2 AA and the project checklist in `08_design_system.md` section 5 (unchanged).
- Type: Estedad (Amin Abedi, OFL) for display/headings and Vazirmatn (Saber Rastikerdar, OFL) for text. Neither ships a
  variable "Farsi digits" build, so `tools/fonts/build_fd.py` remaps U+0030–0039 to the Persian digit glyphs in the variable
  TTFs and `tools/fonts/woff2enc.js` (null-transform WOFF2 encoder, needs only Node) packs them. Result: every 0–9 on the
  site renders as ۰–۹ with no template work; templates keep using `fa_digits` so copied text is Persian too.

## 3. Design plan v2

- **Colour**: ink `#1a2238`, muted `#5b6577`, line `#dde1ea`, paper `#f5f6fa` (app canvas), mist `#eef0f8` (section tint),
  brand deep `#393e70` (kept: logo and identity), brand `#4650a8` (links), brand bright `#5a65d6` (focus, current item),
  signal `#a3680a` on `#fbf1dc` only for «به‌زودی». Public pages on white, app pages on paper.
- **Type**: Estedad 700–800 for h1–h3, stat numbers and the brand lockup; Vazirmatn 400/600/700 for everything else.
  Scale 13 / 15 / 16 / 18 / 20 / 24 / 30 / 38 / 48 px, body line-height 1.85, headings 1.3, `text-wrap: balance`.
- **Layout**: content 1120 px; split hero 7/5 with the five-angle profile figure as the one bold element; audiences as
  rows, principles as a ruled list, numbered steps only for the real three-step sequence; plans as two columns
  (free / pro-soon). App: rail 256 px on ≥ 1024 px, below that a top bar with the workspace name + «منو» opening a drawer
  from the start side, and a fixed bottom tab bar (home, clients, invites, reports, more).
- **Layout modes** (decided from the path in `ts_website/views/layout.xml`): marketing (full menu, full footer), app
  (`/my/*`, `/help/roles`: quiet bar with «سنجه‌های من / حساب من / خروج», slim footer), focus (`/take/*`: logo only, no
  footer), auth (`/web/login`, `/signup*`: logo only, slim footer).
- **Copy**: panel is «رایگان» (owner, 1405-07-10); Pro is «همیار تفسیر … به‌زودی» with the honesty line that it drafts for
  the specialist, never diagnoses, nothing reaches the participant without review. Menu: سنجه‌ها، پنل مراکز، روند کار،
  شواهد و محدودیت‌ها، هزینه، تماس.

Reviewed against the generic defaults: no cream+serif+terracotta, no card kit on the home page, no eyebrow labels (the
old hero kicker is gone), numbering only on the three-step sequence, one animated moment (the profile bars on load,
disabled under `prefers-reduced-motion`).

## 4. Stages

| Stage | Scope | Ship list |
|-------|-------|-----------|
| UI-1 foundation | fonts, tokens, layout modes, header/footer, panel rail + drawer + tab bar (fixes B1–B8 partly), home, pricing, /panel copy, Persian sign-in, scan test for public pages | ts_website, ts_panel, ts_org |
| UI-2 panel pages | page heads, tables/cards, forms, dashboard tiles, clients page order (B9), empty states; every panel route re-shot | ts_panel |
| UI-3 portal + player | /my pages, questionnaire focus layout, sticky next button, progress (B10), result pages and print | ts_assessment, ts_talent, ts_panel, ts_sms |
| UI-4 public pages + audit | audience/trust/help pages on the v2 components, headless matrix at 375/1280 in the rehearsal, final English/digit sweep | ts_website |

Each stage: `ts check` → kept clone → hand tests (`ts_http_pv2_19.py` carries the scan) → `ui_matrix.sh` shots reviewed by
eye → full rehearsal → ship with the guard.

## 5. What shipped

- **ui1** (2026-10-02, commit 8f39565; ts_website 20.0.2.0.0, ts_org 20.0.4.0.0, ts_panel 20.0.17.0.0 + assets): everything
  in UI-1. Rehearsal reh66: 1589/1591, guard and portal UNCHANGED; the two failures were the menu-count and header-link
  checks of older suites, rewritten and re-run green. Ship: OK, eot.ir UNCHANGED.
- **ui2** (same day): UI-2 + UI-3 + UI-4 in one ship (ts_website, ts_assessment, ts_panel) — see IMPLEMENTATION_LOG.

## 6. Lessons

- `[hidden]` loses to Bootstrap's `[hidden]{display:none!important}`; a menu that must show on wide screens cannot rely on
  CSS overriding the attribute. Decide in JavaScript by `matchMedia`.
- One class name across modules: `.ts-band` was both the CTA band (ts_website) and the score pill (ts_assessment); the CTA
  rendered as a pill for weeks. Prefix per component family and grep the other modules before adding a class.
- Odoo xpath `hasclass()` matches only a static `class`; a `t-attf-class` needs `contains(@t-attf-class, …)`.
- `ts_shot.py` reused one SSH tunnel on 18071 for every slot: the slot-2 shots silently photographed slot 1's clone.
  Now one tunnel per clone port (10000 + port).
- The screenshot loop (VPS → /root/share/out → MacBook → device_stage_files → Read) is the only way to look at pages from
  the cloud session; ~4 min for 49 routes × 2 widths.
