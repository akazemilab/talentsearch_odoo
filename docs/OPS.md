# OPS — where things run, which tool or agent does what (2026-10-05)

Why this exists: the 2026-10-01..02 session (Panel v2 S0–S20, UI v2, portal v3) cost $287 and 24 h of active time, of
which ~20 h was waiting on tools. ~822 M tokens were cache re-reads: a 300–750 k-token main context re-read on every
poll, test re-run and screenshot. The fix is structural: VPS code does the work, cheap agents wait and read logs, the
main session only decides and edits, and every round of work ends in a short handoff file.

## 1. Places — no Mac in the path (2026-10-05)

| Place | Reach | Holds / does | Never |
|---|---|---|---|
| Gateway eot.innerquest.me (connector `eot_innerquest_me`) | any session, no device | eot.ir tools (check_site, audit, read-only sql_query, odoo_execute, theme rehearse/deploy, logs) **and** the tools-VPS tools: `ts`, `eot_vps`, `vps_read`, `vps_write`, `vps_patch`, `vps_git`, `vps_image`, `vps_inspect` | a blanket shell (none exists: allow-listed ops only) |
| Tools VPS 95.38.234.86 | through the gateway: prod user eotmcp → ssh key pinned to `command="/usr/local/bin/ts-gw"`, `from=prod` (source `tools/gw/ts_gw.py`, gateway side `tools/gw/mcp_ts.py` → theme repo `tools/prod/mcp_ts.py`) | `ts` (this repo, /root/talentsearch_odoo = source of truth, pushes with its deploy key), `eot` (/root/eot-tools/repo), jobs /root/ts-jobs, /root/eot-jobs, worktrees /root/ts_wt_s1|s2, screenshots /root/share/out | long commands in one call (55 s): use jobs + `wait` |
| Prod eot-odoo-prod 95.38.235.225 | only through `ts` / `eot` / the gateway's own tools | eot_main, odoo20, stage dirs, backups | direct edits |
| Cloud session container | local shell | editing, `python3 tools/vps/ts_check.py .` (1 s), research, docs; push to theme_eot_custom works; push to talentsearch_odoo needs the Claude GitHub App to include that repo | — |
| Mac bridge (`mcp__remote-devices__*`) | only while the Mac is awake | FALLBACK ONLY: `vps` (root shell), old `eot-odoo`/`odoo` databases, `hesabfa`, `search-console`, the share folder | anything the gateway can do |

Code to the VPS without the Mac: `vps_patch` (unified diff, checked first) or `vps_write` for new files, then
`ts check` and `ts push` (talentsearch) / `vps_git` add+commit and `git push` from the cloud clone (theme).
Screenshots without the Mac: `ts shots` then `vps_image`.

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
2. Edit on the VPS through the gateway (`vps_write` for new files, `vps_patch` for edits; never re-send or read back a
   whole large file; `vps_read` slices). Run `ts {"args":["check"]}` after every edit batch.
3. Hand tests: `ts-runner` → `TS_SLOT=1 ts keep eot_tsN UPG`, then the new test files. Fix, `ts db reload`, re-run.
   A main-session `ts test` call is fine when it fits in one call.
4. `ts push`; then, once per bundle (not per stage): `ts-runner` full rehearsal; `ts-risk-reviewer` when the bundle
   touches access, consent, results, deletion or migrations; `ts-shots` when it touches templates.
5. `ts-shipper` with the REHEARSAL line → `ts-scribe` with the facts → final Persian report to the owner.
6. New session for the next bundle. A session that passes ~250 k tokens of context gets a handoff and ends.

## 4. Token rules

- Never poll from the main session; an agent waits (its context is ~20 k, the main one is hundreds of k).
- Every VPS call returns a verdict, not a log: `ts status|wait|test|db errors`, `grep`, `tail -n 30`.
- Every gateway call ends within ~55 s: long work is a job (`rehearse`, `keep`, `testjob`, `shots`, `eot audit|rehearse|ship`)
  followed by `wait` (≤ 40 s), one per call. After an error check the job, never re-run a mutating command.
- No images in the main session; `ts-shots` looks and reports.
- Bundle stages: one rehearsal and one ship per bundle. A dead-code removal is not a ship of its own.
- Run `ts_check.py` before any transfer (a syntax error costs a whole remote round trip).
- Documents go to the Project with `project_write local_path`/`content` from a file, not pasted twice.

## 5. Open owner actions

- Reconnect the `eot.innerquest.me` connector in claude.ai (Settings → Connectors) once, so sessions see the 8 new
  tools (the connector caches its tool list; the server already serves 23 tools).
- Add `talentsearch_odoo` to the Claude GitHub App's repositories (theme_eot_custom already pushes from the cloud).
- Still Mac-only (rarely used): `hesabfa`, `search-console`, and the two OLD Odoo databases (`eot-odoo`, `odoo`).
  Moving them needs their credentials placed on the tools VPS by the owner (never through chat).
- Sepehr: `/root/sp-tools/bin` (spx) is not on the tools VPS as of 2026-10-05; the skill's install step applies.
