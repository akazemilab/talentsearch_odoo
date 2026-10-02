# Client portal, next version (portal v3) — inspection, gap list, plan (1405-07-11 / 2026-10-02)

Scope: the client-facing portal of talentsearch.ir only — `/invite/<token>`, `/c/<token>`, `/signup`, `/web/login`, `/take/*`,
`/my`, `/my/assessments*`, `/my/sharing`, `/my/notifications*`, `/my/account`, `/my/privacy*`, `/my/sessions`. The organisation
panel (`/my/workspaces/*`) is out of scope except where a shared component is touched. Routes, authentication, permissions,
data contracts and scoring stay as they are.

## 1. What already works (kept)

- Invitation page explains the assigning organisation, the question count and time, what is shared per purpose
  (education / employment / clinical), and the expired / used / wrong-account states (`ts_org.invite`, `inv_msg`).
- Consent page per attempt with a versioned text, separate research tick, guardian confirmation for child/adolescent
  instruments, the S16 age question and minor assent; a consent ledger (`ts.consent.record`).
- Player: ten validated items per page (instrument structure preserved), autosave of each answer with honest states
  (`در حال ذخیره…` / `ذخیره شد` / `ذخیره نشد؛ با «صفحهٔ بعد» دوباره ذخیره می‌شود`), review page listing unanswered items,
  idempotent submission with a submission key (`action_submit` locks the row), no preselected answers.
- Report: summary table per factor with the band and a meter, approved client text per band, limitations, print view;
  sharing section (who sees, revoke); audit of every view.
- Account pages: name, phone/OTP, notification preferences, sharing, privacy (export / erase request), sessions.
- RTL, Persian digits (FD fonts since ui1), 44 px controls, app header + slim footer (ui1), portal pills (ui2).

## 2. Gap list (priority: lose answers / misrepresent / expose / block > comprehension > polish)

| # | Gap | Where | Priority | Stage |
|---|-----|-------|----------|-------|
| G1 | Redirect loop: a finished attempt that is not released (erased under legal hold, or imported) sends `/my/assessments/<id>` → `/take/<token>` → back. No "unavailable" state | `ts_assessment` controllers | block | P2 |
| G2 | Consent page says «فقط شما… با هیچ کارفرما یا مرکزی به اشتراک گذاشته نمی‌شود» for every attempt, including attempts taken on a panel's invitation where sharing was accepted. Privacy statement must come from the actual assignment | `ts_assessment.consent` | misrepresent | P2 |
| G3 | Home has no single dominant action; three equal cards; nothing says who assigned what; no dates on the invite rows | `/my` | comprehension | P1 |
| G4 | Navigation: seven pills (کارهای من، نتیجه‌ها، چه کسی می‌بیند، اعلان‌ها، حساب من، داده‌های من، نشست‌ها) overlap with the header; no account hub | portal nav | comprehension | P1 |
| G5 | `/my/assessments` is one flat table mixing drafts and results; no grouping per instrument, no previous results of the same instrument on the report page | list, report | comprehension | P3 |
| G6 | Report opens with a metadata list (report id, engine version, contract) before the plain-language summary; on a phone the first screen is bureaucratic | report | comprehension | P3 |
| G7 | After submission the report shows only «پاسخ‌های شما ثبت شد و گزارش آماده است»; no explicit "what was received / who sees it / one next action" | report | comprehension | P2 |
| G8 | Review page promises «نتیجه بلافاصله … نمایش داده می‌شود» — true today for every instrument; keep but phrase as a statement of the current rule | review | copy | P2 |
| G9 | Player navigation on phones: fixed since ui2 (sticky actions, sticky progress); the progress text shows answered/total and page — honest, keep. No "saved to account" wording after a page save | player | polish | P2 |
| G10 | No test covers: pending/unreleased result, invited-by-panel consent text, home dominant action, 320 px width | tests | verification | P5 |
| G11 | Notifications: the header badge exists; the center page is a list; no split of "action required" vs "information" | `/my/notifications` | polish | P4 |
| G12 | Sessions page in the account area but not reachable from the account page itself | `/my/account` | polish | P4 |

Assumptions recorded: smartphone-first (owner's product assumption); Persian only; no messaging service exists (none added);
emergency number in copy is the one already approved on the trust pages (۱۱۵); result release is immediate for every
instrument today (`action_submit` sets `released`), there is no review queue for participants to wait on.

## 3. Evidence → decision table

| Source | Finding | Applicability / limit | Decision | Verified by |
|--------|---------|-----------------------|----------|-------------|
| R1 Zikmund-Fisher 2014; R2 Zhang 2020 | People need context and next steps beyond numbers; numeracy and literacy vary independently | Laboratory results, not psychological thresholds | Report opens with a plain-language summary (what the measure assesses, date, who sees it), then dimensions, then score context and limits; bands keep their approved texts | HTTP test: summary block precedes the table; shots at 320–430 px |
| R3 Mowlem 2024 | Keep electronic PROMs faithful to the source | Consensus + evidence | Item wording, order, five anchors and the ten-per-page grouping are untouched; only chrome around the items changes | diff of `web_player.xml` items block = none |
| R4 Villar 2013; R5 Conrad 2010 | Progress indicators do not reduce drop-off in general; honest, non-manipulative feedback | General web surveys | Keep the true answered/total count and page number; no animated or accelerated progress | code review |
| R6 Iwaya 2022 | Privacy must hold in behaviour, not copy | Android app sample, 2022 | No trackers added; consent page derives "who sees" from the real assignment; neutral notification texts stay | `ts_http_pv3.py` consent-text checks |
| R7 GOV.UK question pages | Start from one question per page | Service forms, not validated instruments | Not applied: the instrument's validated grouping (ten items per page, same scale) takes precedence; one item per screen would change administration | — |
| R8 WCAG 2.2 | AA; 2.5.8 target size minimum 24 px (44 px is a comfort target) | Normative | 44–48 px controls kept as comfort target; focus visible; no colour-only state; reflow checked at 320 px | `ts_shot.py` widths 320/390/430/768/1280 |

## 4. Stages

| Stage | Scope | Ship list |
|-------|-------|-----------|
| P1 | Home with one dominant action and dated rows naming the assigning organisation; four-item navigation (کارهای من / سنجه‌ها و نتیجه‌ها / چه کسی می‌بیند / حساب); account hub links to notifications, privacy, sessions | ts_panel |
| P2 | G1 unavailable state; G2 consent "who sees" from the assignment; G7 submission confirmation block; G8/G9 copy | ts_assessment, ts_panel, ts_org |
| P3 | Report progressive disclosure (summary first, metadata folded, previous results of the same instrument and version listed with dates, no trend chart); `/my/assessments` grouped: open first, then results per instrument | ts_assessment, ts_panel |
| P4 | Notifications split action/information; account hub polish; empty and error states review | ts_panel |
| P5 | `ts_http_pv3.py` journeys; `ts_shot.py` widths 320/390/430/768/1280 on every portal route; handoff doc | tools |

Each stage: `ts check` → kept clone → hand tests → shots → full rehearsal → ship with the eot.ir guard.
