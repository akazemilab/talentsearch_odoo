# Onboarding programme: handoff (2026-10-13 23:00 Tehran)

The owner asked for all of the following to be deployed: the two research docs (Project `claude/ONBOARDING_RESEARCH_AND_DESIGN.md`, `claude/B2B_PANEL_ONBOARDING_RESEARCH.md`) and their decisions.

The owner's decisions:
- Individuals answer first and give their number at the result.
- There is **no panel approval**.
- The licence is a badge, not a gate.

## Status
| Release | What | State |
|---|---|---|
| onb1 | Approval removed (50 invites/day in week 1, suspend, new-panels list); licence badge; unified mobile-OTP sign-in (WebOTP line, 30-day session, locks) | LIVE (main 6152b42) |
| onb2 | One-tap invites (delivery secret, scoped session, device binding); guest starter inventory_002 with a result gate; funnel events; module ts_onboard | LIVE (main a1562a8) |
| onb3 | Panel first session (one-form creation, per-kind starter, HR sample position, preview self-test, sample reports, «شروع کار», one-screen invite + permanent /c/ link, live status), SMS nudges, join SMS, help, /clinics /hiring /schools /pricing, activation funnel, welcome-credit setting (0 = off); clone SMS neutralised (ts_db.sh) + code guard | LIVE (main d5f60a4). Merged with career1: the norm rebuild excludes career takes, previews and voided attempts; the career entry on the home hero is a quiet text link in the organisation links |

Design notes: docs/onboarding/01, 02, 03. Details in docs/IMPLEMENTATION_LOG.md.

## To finish onb3 (next session, haiku runner and shipper are enough)
1. The slot 1 worktree is on onb3. If origin/main moved, run `vps_git pull --no-rebase --no-edit origin main` there; only the log usually conflicts, so keep both entries.
2. `ts rehearse eot_tsNNNN ts_onboard ts_core,ts_website,ts_assessment,ts_org,ts_sms,ts_talent,ts_panel,ts_battery,ts_billing,ts_brand,ts_onet,ts_tasks,ts_hire,ts_kavenegar,ts_career` on slot 1, using a unique name taken from `ts slots`.
   - Required: guard UNCHANGED, portal UNCHANGED, unexpected failures 0. The 2 known kavenegar inbox failures are acceptable.
   - Watch the interplay with career1: the ts_tasks norm rebuild must exclude both preview and career takes.
3. Ship:
   - `ts push` from slot 1;
   - in /root/talentsearch_odoo, `pull --ff-only origin onb3`;
   - `ts ship ts_onboard <list> onb3` from slot 0 with confirm;
   - `live`, `dump auto`;
   - `push origin main`;
   - drop the clones.
   Ship quickly after the rehearsal: other sessions (career, konkur) ship to main too.

## Owner actions
- Kavenegar: create a Verify Lookup template ending with `@talentsearch.ir #%token`. After approval, tick it in Settings → Kavenegar as the OTP template.
- Check the Kavenegar outbox for 2026-10-13 13:48–13:56. A clone test may have sent join SMS to 09121110001, 09127770951, 09127770955 and 09127779931. Before onb3, earlier rehearsals could also send SMS from clones (test numbers 0912666000x). onb3 closes this.
- Ops: pin the live odoo20 server to eot_main (`db_name`/`dbfilter` in /etc/odoo20.conf). Today it also runs crons on clone databases, which causes errors on stale clones.
- nginx access logs keep full invite URLs (tokens and SMS secret); consider shorter retention.
- Optional settings: `ts_billing.welcome_credit_rial` (welcome credit, 0 = off) and `ts_onboard.followup_user_id` (who gets the 7-day follow-up activity).

## Rules learned
- Run `ts slots` before naming a clone. Drop clones after a ship, because live crons hit them.
- Ships run from slot 0 only: fast-forward main to the rehearsed branch first.
- `vps_git` args cannot contain newlines; use several `-m` flags.
