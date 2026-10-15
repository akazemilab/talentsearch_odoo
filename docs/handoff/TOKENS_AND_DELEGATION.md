# TOKENS AND DELEGATION (2026-10-14)

Principle: code on the VPS does the work, cheap agents wait and read, the main session only decides and edits.
Detail and history: docs/OPS.md (read sections 2-4 only).

## Rules
1. Start each session by reading docs/handoff/START_HERE.md and FACTS.md, not the code and not old chats. Do not read
   IMPLEMENTATION_LOG.md whole; grep it (`grep -n KEYWORD`).
2. Never poll from the main session. Long work is a job (`rehearse`, `keep`, `testjob`, `shots`, `ship`) and an agent
   waits for it (`ts wait NAME`, at most 40 s per call).
3. Every VPS call returns a verdict, not a log: `ts status|wait|test|db errors`, `grep -c`, `tail -n 30`, `cut -c1-200`.
4. Read files in slices (`vps_read` start/end). Never re-send or read back a large file; edit with `vps_patch`.
5. No images in the main session. `ts-shots` looks and returns a defect list (at most 8 images).
6. Generate facts with scripts, not prose: `bash tools/vps/handoff_facts.sh` rewrites docs/handoff/FACTS.md.
7. Run `ts check` after every edit batch (2 s) before any rehearsal.
8. A session past ~250k tokens of context writes a handoff and ends. New bundle = new session.
9. Documents go to the Project once (from a file), not pasted twice into chat.

## Who does what
| Task | Done by | Model |
|---|---|---|
| Preflight | `ts check` | none |
| Kept clone, hand tests, reloads | agent ts-runner | haiku |
| Full rehearsal | agent ts-runner (`ts rehearse`) | haiku |
| Ship | agent ts-shipper, only with a green REHEARSAL line of the same commit | haiku |
| Screenshots and visual review | agent ts-shots / ts-ux-auditor | sonnet |
| Risk review (access, consent, results, deletion, migrations, eot.ir isolation) | agent ts-risk-reviewer, read-only | opus |
| Log / handoff / Project copy | agent ts-scribe | haiku |
| Research (> 3 searches) | agent web-researcher | sonnet |
| Code search | Explore agent | haiku |
| Architecture and money logic | owner's design session | fable |
| Build | main session | opus or sonnet (Opus has a weekly limit) |

## Session loop
1. `ts slots`, `ts live`, read START_HERE. 2. Edit through the gateway, `ts check`. 3. Hand tests on a kept clone.
4. `ts push` (only when the owner agrees; repo is public). 5. One rehearsal, risk review if sensitive, shots if templates.
6. Ship via ts-shipper. 7. ts-scribe updates IMPLEMENTATION_LOG, HANDOFF and re-runs handoff_facts.sh.
8. Short Persian report to the owner.

## Reading code cheaply (2026-10-15)
- `short [N]` (tools VPS and sp-new): cut stdin lines to N characters, UTF-8 safe. `cut -c` cuts bytes, splits Persian
  letters, and the VPS bridge then fails to decode the whole output.
- `qwebmap FILE [FROM TO]` (both hosts): one line per template line with t-name / t-if / href / id / name / t-call and the
  visible text, svg stripped. A 340-line view reads in about a third of the tokens.
- Never `pkill -f PATTERN` from a shell whose own command line contains PATTERN (it kills itself); use `pgrep -f 'x[y]z'`.
