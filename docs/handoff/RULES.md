# RULES: hard rules for the whole talentsearch.ir project (2026-10-14)

These are binding for every session, agent and contractor. They consolidate CLAUDE.md "Hard rules" and docs/OPS.md.
If a task needs to break one, stop and ask the owner; do not decide alone.

## 1. Scope fence (owner, 2026-10-14)
- Work ONLY on talentsearch.ir (website 4 in db eot_main, repo talentsearch_odoo, ts_* modules).
- NEVER touch eot.ir (website 1, theme_eot_custom, its DNS, generic views/pages/menus/redirects).
- NEVER touch app.sepehrtherapy.ir / the sp-new server (sp_main, sp_* modules, wallet, Hesabfa sync, hesabfa-odoo-sync,
  sp-tools). Reading Sepehr data is not part of this project; ask the owner for what you need.
- The `mcp__VPS__vps_exec` root shell reaches directories that belong to those other projects. Use it only with paths under
  /root/talentsearch_odoo. Prefer the gateway tools (`ts`, `vps_read`, `vps_write`, `vps_patch`, `vps_git`), which are
  allow-listed.
- Live talentsearch.ir DNS and nginx are out of scope unless the owner asks in that session.

## 2. Change control
- Every install/upgrade: `ts rehearse` on a fresh clone first. Ship only when the REHEARSAL line is green AND the guard says
  "eot.ir UNCHANGED" (and portal UNCHANGED). Then `ts ship` (needs confirm). One rehearsal and one ship per bundle.
- ts_* modules must not depend on theme_eot_custom.
- Tests that create records run only on eot_ts* clones.
- Never edit the live code directory (/opt/odoo/talentsearch); only `ts ship` copies stage to live.
- Never re-run a mutating command after an error: check the job state first.
- Docs-only commits need no rehearsal. Pushing is a separate step (the GitHub repo is PUBLIC).

## 3. Data, money, privacy
- Never store, print or repeat secrets (API keys, SMTP, Kavenegar, Liara, passwords). Secrets live on the server only.
- The GitHub repos are public: no secrets, no real phone numbers, no participant data, no client financial figures.
- Never record a payment that did not happen (use a grant, not an invoice). Invoices name only the institution.
- SMS never name the assessment or battery. Clones cannot send SMS or email; keep it that way.
- Results are shown only to the people the design allows (participant, responsible counselor, institution by role).
  HR hiring is decision support only: bands, no cut-scores, no auto-reject, interests never used for hiring.
- Erase requests delete the data they promise to delete. Retention crons stay on.

## 4. Writing and UX
- Counseling vocabulary only for clinic surfaces; name is «استعدادیاب»; «پیشخوان», never «داشبورد».
- Never quote poems or song lyrics in product text. Copy follows docs/ux_writing/voice.md and glossary.md.
- Owner-facing reports are short, plain Persian: result, one decision, a recommendation.

## 5. Stop conditions (ask the owner)
- Anything affecting eot.ir or app.sepehrtherapy.ir, DNS, payment gateway, Enterprise licence, real SMS/email blasts,
  deleting data, restoring a backup over live, or changing prices/credits.
