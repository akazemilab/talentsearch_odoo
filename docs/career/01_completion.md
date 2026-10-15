# Career test (ts_career): completion research and plan (2026-10-15)

The career test is the signature product. Goal: more people who start it finish level 1 (interests -> result), and more of
them go on to level 2 (work styles) and level 3 (abilities).

## 1. Today's path (code read 2026-10-15)

| # | Screen | Friction |
|---|--------|----------|
| 1 | /career landing | fine: 8 min, 3 steps, free |
| 2 | sign-in wall (mobile + OTP code) BEFORE the first question | biggest wall: asks for a phone before any value |
| 3 | consent page (summary + long text + tick box) | second wall before item 1 |
| 4 | 60 interest items, 12 pages of 5, full page reload per page | 12 network round trips on a weak mobile network |
| 5 | review page, then submit | one more screen |
| 6 | education + experience (2 questions) | fine ("one step to result") |
| 7 | result (quick tier) | good; levels 2/3 offered as "optional" |
| L2 | work styles: 120 items, ~15 min, 24 pages + review | long single sitting |
| L3 | 3 timed tasks, ~23 min, "easier on a computer" | long; device switch |

Reminders: none. The invitation reminder (ts_panel, `_cron_reminders`) and the onboarding nudges (ts.onb.nudge) do not
cover career runs, so a person who stops at item 30, or never starts level 2, hears nothing.
Measurement: 3 career runs on live so far (launched 2026-10-13): no usable completion data yet.

## 2. What the evidence says

1. **Length is the strongest lever.** Longer announced length -> fewer starts and fewer completions (Galesic & Bosnjak
   2009, 10/20/30 min). Mobile breakoff meta-analysis (Mavletova & Couper, 14 studies / 39 samples): shorter surveys,
   simpler design, mobile-optimised layout and more reminders all cut breakoff. Quality drops after ~10-13 min.
2. **Do not cut the 60 interest items.** O*NET's 30-item Mini-IP correlates .95-.96 with the 60-item form but agrees on
   the top interest for only 73% of people; O*NET says it does not replace the 60-item form when accuracy matters. For a
   signature test we keep 60 and instead cut the friction around them.
3. **Progress bars: honest and front-loaded.** Meta-analysis of 32 experiments (Villar, Callegaro & Yang 2013): a
   constant-speed bar does not reduce breakoff; a fast-then-slow one does; slow-then-fast increases it. So: show the
   whole journey as a few steps, count short steps first, show minutes left, never fake speed.
4. **Goal gradient / endowed progress.** People speed up near a goal and finish more when they see they already started
   (Kivetz et al. 2006; Nunes & Drèze 2006). Use step lists where finished steps are ticked and "almost there" moments.
5. **One item at a time on phones, auto-advance is safe.** Item-by-item beats grids on smartphones (Revilla et al.).
   Auto-advance had no effect on breakoff or straightlining, a small gain in ease and design ratings, and fewer changed
   answers; the one complaint was that going back looked impossible -> keep a clear "back" (Survey Practice, LSSSE 2017).
6. **SMS reminders work, mainly by speeding response.** Pew: texted reminders lifted day-10 response 48% vs 39% (final
   61% vs 55%); more reminders reduce breakoff (meta-analysis). Only people who agree to texts may get them.
7. **Ask for the account after the effort, not before.** "Lazy registration": let people use the product, ask for sign-up
   when there is something to save. Our own starter test already works this way (guest player + claim on sign-in).
8. **The result is the reward.** Promised personal feedback raises participation, most of all when topic interest is low
   (Marcus et al. 2007). Each level must say exactly what it adds to *their* list.
9. **Iran context.** Mobile networks were cut for most of H1 2026 and are still spotty: every answer must survive a dropped
   connection, and pages must be light.

## 3. Plan (each phase rehearsed on a clone, then shipped with owner approval)

**Phase A - finish what was started (no change to the questions)**
- Career reminders (new `ts.career.nudge`, same safety rules as ts.onb.nudge: one row per person and kind, claim before
  send, quiet hours 22-08 Tehran, at most one SMS a day, at most 3 career SMS per person in all, stops the moment the
  step is done, owner switch `ts_career.nudges_enabled`):
  - `ip_stall`: interests started, not finished, 24 h idle -> "you are N questions from your list" + resume link.
  - `bg_stall`: interests done, education/experience missing, 3 h -> "one step to your list".
  - `l2_invite`: quick result seen, level 2 not started, 3 days -> what level 2 adds.
  - `l2_stall`: level 2 started, not finished, 48 h idle.
  - Only for people who ticked «یادآوری پیامکی» (explicit opt-in, unticked by default, on the start screen and on the result
    page; one-tap stop on /my). Text never names the test; short link `/n/...` style; Persian digits; link last.
- Journey header on every career screen: «۱ علایق ← ۲ دو پرسش ← ۳ نتیجه» with finished steps ticked, and minutes left
  (honest, from items left).
- Milestone notes inside the interests player at 50% and the last page ("almost there: N left").
- Level cards on the result page: what changes in *their* list (e.g. "your 20 jobs are re-ordered by work style and
  readiness"), honest minutes, and "you can stop any time; answers are saved".
- Level 2 split into sittings: after every 30 items a "good place to stop" screen (continue now / remind me tomorrow).
- Funnel per step for career (landing, start, first answer, 25/50/75%, done, background, result, L2/L3 start/done,
  reminder sent / came back) in the existing ts.funnel.event, with a back-office view.

**Phase B - fewer walls before the first question**
- Start the interests as a guest (existing guest player + cookie + claim). Consent becomes the one-screen start of /start
  ("18+; I agree and start" + unticked research box). Mobile number asked once the 60 answers are in: «فهرست شغل‌های شما
  آماده است» -> sign in -> claim -> education/experience -> result. Same daily free cap, same guest rate limits.
- Answers kept in the browser as well as on the server, so a dropped connection loses nothing and the page re-sends.

**Phase C - faster answering on phones (player change, career only first)**
- Interest items one card at a time with auto-advance and a visible «قبلی», no page reloads (answers autosaved, page
  boundaries invisible). Review page only lists missing items. Measured on the funnel before it is applied to other tests.

**Not doing**: cutting items, interim scores during the test (they bias the rest of the answers), fake progress, prizes.

**Needs a clinician / owner decision (not in this plan)**: answer labels for interests. O*NET uses dislike/like labels
(and tested emoji faces as equivalent); ours are «بسیار کم … بسیار زیاد». Changing them changes the instrument.

## Sources
- Villar, Callegaro, Yang (2013) progress indicators meta-analysis: https://research.google/pubs/where-am-i-a-meta-analysis-of-experiments-on-the-effects-of-progress-indicators-for-web-surveys/
- Mavletova & Couper, breakoff in mobile web surveys meta-analysis: https://dx.doi.org/10.5334/bar.f
- O*NET Mini-IP report (2016): https://www.onetcenter.org/dl_files/Mini-IP.pdf
- O*NET Interest Profiler emoji anchors: https://www.onetcenter.org/dl_files/IP_Emoji.pdf
- Pew, text messaging for web surveys (2016): https://www.pewresearch.org/wp-content/uploads/2016/09/Text-Messaging-for-Web-Surveys-FINAL-9-6-2016.pdf
- Revilla et al., grids vs item-by-item on smartphones: https://www.upf.edu/documents/3966940/3986764/RECSM_wp046.pdf
- Auto-advance experiment (Survey Practice): https://surveypractice.org/article/6381-impacts-of-implementing-an-automatic-advancement-feature-in-mobile-and-web-surveys
- Galesic & Bosnjak (2009) questionnaire length: https://synapsesocial.com/papers/W1989597713
- Angus Reid, survey length and quality: https://angusreid.com/wp-content/uploads/2024/09/The-Hidden-Costs-of-Long-Surveys-Why-Survey-Length-Impacts-Data-Quality.pdf
- Endowed progress (Nunes & Drèze): https://en.wikipedia.org/wiki/Goal_pursuit
- Iran connectivity, AP 2026-05-28: https://ktla.com/news/nationworld/ap-international/ap-iranians-are-back-online-after-a-monthslong-shutdown-but-still-face-heavy-restrictions/amp/
