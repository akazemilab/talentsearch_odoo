# OPS — where things run, which tool or agent does what (2026-10-05)

Why this exists: the 2026-10-01..02 session (Panel v2 S0–S20, UI v2, portal v3) cost $287 and 24 h of active time, of
which ~20 h was waiting on tools. ~822 M tokens were cache re-reads: a 300–750 k-token main context re-read on every
poll, test re-run and screenshot. The fix is structural: VPS code does the work, cheap agents wait and read logs, the
main session only decides and edits, and every round of work ends in a short handoff file.

## 1. Places

| Place | Reach | Holds / does | Never |
|---|---|---|---|
| Cloud session container | local shell | editing, `python3 tools/vps/ts_check.py .` (1 s, same check as `ts check`), research, docs, git read | push to GitHub (needs the Claude GitHub App on akazemilab — owner action) |
| Tools VPS 95.38.234.86 | `vps_exec` through the owner's Mac (60 s per call, Mac must be awake) | `ts` toolkit (this repo, /root/talentsearch_odoo = source of truth, pushes with deploy key), `eot` toolkit (/root/eot-tools, theme repo), jobs in /root/ts-jobs and /root/eot-jobs, worktrees /root/ts_wt_s1|s2 | long commands in the foreground |
| Prod eot-odoo-prod 95.38.235.225 | ssh from the tools VPS only | eot_main, odoo20, stage dirs, backups /var/backups/odoo | any direct edit; everything goes through `ts` / `eot` |
| Share folder | VPS /root/share/in ← Mac ~/Claude/eot-share/to-vps; VPS /root/share/out → Mac …/from-vps (sync each minute, subfolders a minute later) | screenshots back to the session (device_stage_files), files from the owner | code transfer (edit on the VPS or apply a small diff instead) |
| Gateway eot.innerquest.me (MCP, no Mac) | cloud connector `eot_innerquest_me` | eot.ir only: check_site, check_links, placeholders, scss_check, audit, read-only sql_query, odoo_execute (small content edits), theme rehearse/deploy, read_odoo_log, odoo_status | Talent Search ships (no `ts` commands there yet) |
| Mac-bridged connectors | `mcp__remote-devices__*` | `vps`, `eot-odoo` (OLD database uuid 98b98775… — not live), `odoo` (old sepehrtherapy.ir, source data, read-only), `hesabfa`, `search-console` | writes through `eot-odoo` (check `database.uuid` = 9f658a4b… before any Odoo write) |
| Sepehr server | `spx` toolkit, skill `vps-odoo-fast-workflow` | Sepehr build | mixing with ts/eot |

## 2. Task → who does it

Code first: anything repeated with the same steps is a `ts`/`eot` command (free, fast). An agent only drives commands
whose output has to be waited for or read. The main session decides and edits.

| Task | Done by | Model | Returns |
|---|---|---|---|
| Preflight (syntax, QWeb t-else, view placement, phones) | `ts_check.py` locally before any transfer; `ts check` on the VPS | — | `CHECK OK` / errors |
| One quick test file on a kept clone (< 50 s) | main session: `TS_SLOT=1 ts test DB FILE` | — | FAIL/SUMMARY lines only |
| Kept clone for a stage, hand tests, reloads | agent `ts-runner` (`ts keep`, `ts test`, `ts db reload`, `ts db errors`) | haiku | verdict block ≤ 15 lines |
| Fresh dump + full rehearsal | agent `ts-runner` (`ts rehearse DB INS UPG`; `ts dump auto` inside) | haiku | REHEARSAL line + unexpected FAILs |
| Ship | agent `ts-shipper` (only with a green REHEARSAL line of the same commit) | haiku | SHIP line, live probes, new dump |
| Screenshots + visual review | agent `ts-shots` (`ts shots DB WIDTHS`, report first, ≤ 8 images) | sonnet | defect list |
| Risk review of a commit range (access, privacy, data, eot.ir isolation) | agent `ts-risk-reviewer`, read-only | opus | ranked findings |
| Log / handoff / Project copy after a ship | agent `ts-scribe` | haiku | commit id, paths |
| Web research (> 3 searches) | agent `web-researcher` | sonnet | answer + 5 sources, notes in a file |
| Find code across the repo | built-in `Explore` agent with model haiku | haiku | locations only |
| eot.ir live check | gateway `check_site` / `audit` directly (one call) | — | problems only |
| Design of a feature / stage split | the owner's design session (Fable or Opus), output = a plan doc in the Project | fable/opus | plan with stages, acceptance tests |
| Implementation | main session | sonnet | commits on the VPS |

Agent files live in `.claude/agents/` of this repo. A session without the repo can run the same contract with the
general-purpose agent and the `model` parameter (the skill `eot-ops` holds the prompts).

## 3. The stage loop (one session per bundle of stages)

1. Start: read the plan doc and the last handoff from the Project (not the old chat). `ts slots`, `ts dump check`.
2. Edit on the VPS (`vps_write_file` for new/small files, a unified diff + `git apply` for edits; never re-send or read
   back a whole large file). Run `ts check` after every edit batch.
3. Hand tests: `ts-runner` → `TS_SLOT=1 ts keep eot_tsN UPG`, then the new test files. Fix, `ts db reload`, re-run.
   A main-session `ts test` call is fine when it fits in one call.
4. `ts push`; then, once per bundle (not per stage): `ts-runner` full rehearsal; `ts-risk-reviewer` when the bundle
   touches access, consent, results, deletion or migrations; `ts-shots` when it touches templates.
5. `ts-shipper` with the REHEARSAL line → `ts-scribe` with the facts → final Persian report to the owner.
6. New session for the next bundle. A session that passes ~250 k tokens of context gets a handoff and ends.

## 4. Token rules

- Never poll from the main session; an agent waits (its context is ~20 k, the main one is hundreds of k).
- Every VPS call returns a verdict, not a log: `ts status|wait|test|db errors`, `grep`, `tail -n 30`.
- vps_exec under 50 s: no `sleep` over 15 s, `ts wait NAME 40`, one wait per call. "did not respond" → check the job,
  never re-run a mutating command.
- No images in the main session; `ts-shots` looks and reports.
- Bundle stages: one rehearsal and one ship per bundle. A dead-code removal is not a ship of its own.
- Run `ts_check.py` before any transfer (a syntax error costs a whole remote round trip).
- Documents go to the Project with `project_write local_path`/`content` from a file, not pasted twice.

## 5. Open owner actions

- Install the Claude GitHub App on akazemilab (or reconnect GitHub in claude.ai settings): then the cloud session can
  push and the VPS `git pull`s — no Mac in the code path.
- Optional: add `ts` job commands (status / wait / test / rehearse) to the eot.innerquest.me gateway, so Talent Search
  rehearsals do not depend on the Mac being awake. Ships stay on the Mac-bridged path until the gateway has an audit log.
- Sepehr: `/root/sp-tools/bin` (spx) is not on the tools VPS as of 2026-10-05; the skill's install step applies.
