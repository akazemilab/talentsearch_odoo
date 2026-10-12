# استعدادیاب for HR: architecture (2026-10-12)

Owner decisions (2026-10-12): HR persona = company HR inviting applicants from an **employment panel**; hiring fit uses
**personality + timed tasks only** (O*NET says its interest, work-values and ability tools "should not be used for
employment or hiring decisions"; self-rated skills are too easy to inflate); **early access now** as decision support
(bands, no cut-scores, no auto-reject, human decides, validation on incoming data); **email through Sepehr's Liara
account** as `no-reply@sepehrtherapy.ir`. Audit and plan: Project doc `claude/ONET_HR_AUDIT_AND_PRODUCTION_PLAN.md`.

## 1. Modules (on top of the clinic stack)
| module | depends | adds |
|---|---|---|
| `ts_onet` | ts_core, website | `ts.onet.occupation` (923 O*NET 31.0 occupations with work-style/ability requirements, Persian title + one-line description, search), pure engine `models/jobfit.py` (JOBFIT-v1), data `data/onet_hr.json` (built by `/root/onet-match/code/hr/build_hr_data.py`, CC BY 4.0 credit) |
| `ts_tasks` | ts_battery, ts_onet, website | version mode `task`, five task instruments, generators, scoring and norms, `ts.task.norm` + weekly cron, task player (`/take/<token>` + `/task/{start,answer,finish}`), percentile display in report blocks, `invite_only` instruments hidden from the public catalog |
| `ts_hire` | ts_brand, ts_tasks, ts_onet, mail | HR personality questionnaire (IPIP-HEXACO, 24 facets x 5 + 3 attention items), batteries `BAT-HR-SHORT` / `BAT-HR-FULL`, `ts.hire.position`, assignment fields (position, decision, extra time, voluntary gender/age band, job fit, validity, verification), panel pages under `/my/workspaces/<id>/positions`, candidate feedback card, email templates |

Nothing existing changes behaviour: access stays `result_level()`; employment staff still see the summary level only
(bands), now also the job-fit band and the met/not-met status of each requirement; never answers or scores.

## 2. Personality questionnaire (HR-HEXACO-1)
IPIP-HEXACO items (Ashton, Lee & Goldberg 2007, public domain; the copyrighted HEXACO-PI-R/HEXACO-60 wording is not
used), Persian translation by EOT (`ts_hire/data/hexaco_fa.json`), 5 items per facet (Dependence has no reverse item in
IPIP), interleaved by facet, three attention items at about 1/4, 1/2, 3/4 (hidden factor `ATTN`, `report_hidden`).
Normal Likert player and engine; facet = factor; bands low 1.0-2.6, medium 2.8-3.4, high 3.6-5.0. Candidate texts per
facet and band in `hexaco.py` (counselling tone, «شما»).

Validity signals (`ts.assignment._ts_validity`), shown to HR as «نیاز به دقت», never a decision: attention (2 of 3
control items wrong), straight-lining (>= 80% one answer), inconsistency (|keyed - reversed| >= 2 in >= 6 facets),
fast (< 1.5 s per item).

## 3. JOBFIT-v1 (ts_onet/models/jobfit.py)
Requirements of an occupation: work styles with |WI| >= 1.0 (O*NET -3..+3), abilities with importance >= 2.5; HR may
mark at most 3 critical (weight x2) and drop irrelevant ones (audited `position.profile`).
* Work styles: facets centred within person (CENTER-v0, so answering everything higher does not raise the fit) ->
  WS-XW-v0 crosswalk -> match / neutral / gap (+-0.15). Band: limited if a critical style is a gap or gap share >= 0.4;
  strong if match share >= 0.55 and gap share <= 0.2; else moderate.
* Abilities: RE-v0 (job level as percentile among occupations vs candidate percentile, tolerance 10): met / short.
  Band: limited if met share < 0.5 or a critical ability is short by > 25; strong if met share >= 0.8 and no critical
  short; else moderate. Coverage < 30% of the weight -> no ability band (shown as «سنجیده نشده»).
* Overall band from points (strong 2, moderate 1, limited 0): mean >= 1.5 strong, >= 0.5 moderate, else limited.
  Personality-only fits are labelled. Ordering inside a band uses the continuous fit, never shown as a number.
* Persian explanations EXPL-HR-v1: up to 4 "fits" and 4 "ask in the interview"; important unmeasured abilities listed;
  physical/sensory demands go to the occupational-medicine referral list.

## 4. Timed tasks (ts_tasks)
| instrument | blocks (items / seconds) | abilities |
|---|---|---|
| TASK-REASON | matrices 8/240, series 8/180, logic 8/210 | Inductive Reasoning, Information Ordering, Deductive Reasoning |
| TASK-SPATIAL | rotation 16/150 | Visualization, Spatial Orientation |
| TASK-NUMERIC | numeric problems 8/240, arithmetic speed 90 s | Mathematical Reasoning, Number Facility |
| TASK-SPEED (desktop) | symbol comparison 90 s, digit span, flanker 40, choice RT 30 | Perceptual Speed, Memorization, Selective Attention, Reaction Time, Response Orientation |
| TASK-VERIFY | matrices 6/180, series 6/135 | Inductive Reasoning (supervised re-test, ITC 45.3) |

* Items are generated per attempt from a server seed (`generators.py`, pure, deterministic); keys never leave the
  server; deadlines are server-side (+5 s grace); a reload continues the same block and is recorded (`resumed`).
* Scoring (`scoring.py`): power blocks = share correct; speed = correct per minute (arithmetic: wrong / 3 subtracted;
  comparison: wrong subtracted); span = longest length with one correct; flanker = inverse efficiency on incongruent
  trials; choice RT = median correct RT (x1.5 if accuracy < 70%). Percentiles from PN-0 provisional norms until a block
  has 100 real completions, then EMP-n (weekly cron `ts.task.norm._ts_rebuild`); the result records which norm.
* Integrity signals: focus lost >= 3, resumed, > 30% power answers under 2 s, > 10% anticipations (< 150 ms).
* Accommodation: `ts.assignment.ts_extra_time` 1.0 / 1.25 / 1.5 scales every limit; shown on the HR page.
* Results are ordinary `ts.attempt.result` rows (score = percentile 0-100) so battery, billing, SMS and reports work;
  the task branch of `action_submit` calls the lower hooks (usage event -> billing, notifications, result SMS).

## 5. HR flow (ts_hire, panel pages)
`/positions` list -> `/positions/new` (Persian/English occupation search, title, battery, deadline) -> `/profile`
(requirements, <= 3 critical, drop) -> `/positions/<id>` (counts, decision-support note, invite box: one person per
line «نام، موبایل، ایمیل», SMS and/or email, extra time; candidates sorted by band; compare 2-3) -> `/c/<aid>`
(fits / ask in interview, requirement tables, unmeasured abilities, occupational-medicine list, validity signals,
verification test, decision with note) -> `/compare` -> `/fairness` (four-fifths rule on recorded decisions by
voluntary gender and age band; groups < 5 hidden). Permissions: view `results:summary`; create/invite
`invites:create`; decide and remind `invites:manage`; fairness `reports:group`. Audit: `position.create`,
`position.profile`, `position.state`, `hire.view`, `hire.decision`, `hire.verify_invite`, `notify.email_invite`,
`notify.email_reminder`.

Candidate side: the invitation page names the position and says what the employer sees, that nothing is decided
automatically, retention 12 months; two optional fairness questions (stored on the assignment, readable only by the
platform manager group and in aggregate). After the battery the candidate sees a feedback card (top three facets,
ability bands) and the full facet report.

## 6. Email
Native `mail.template` (`ts_hire.mail_invite`, `mail_reminder`, `mail_candidate_done`), sent with `force_send` through
the `ir.mail_server` for `sepehrtherapy.ir` (Liara, from_filter `sepehrtherapy.ir`, added 2026-10-12; eot.ir senders do
not match it). Sender `ts_hire.email_from` (default `"استعدادیاب" <no-reply@sepehrtherapy.ir>`), switch
`ts_hire.email_enabled` (default on). Links only, never results. Clones: `tools/prod/ts_db.sh clone` switches every
mail server off and drops the queue, so tests never send.

## 7. Tests
`tests_hire_engine.py` (pure), `tests_hire.py` (ORM, clone, no commit, H01-H35), `ts_http_hire.py` (HTTP on a served
clone). `ts_rehearse.sh` runs them when `ts_hire` is in the module list.

## 8. Open (owner / science)
Translator and psychologist review of the questionnaire wording and WS-XW-v0; real norms (automatic at 100 per block);
criterion validation with early-access employers (job performance follow-up); forced-choice version of the
questionnaire; reviewer names. PN-0 parameters and band rules are design assumptions until then.
