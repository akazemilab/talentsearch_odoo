# Panel v2 — 01 Research (verified 2026-10-01 / 9 Mehr 1405)

Purpose: the facts the design rests on, each checked against its source today, and what
differs from the prompt that commissioned this work (`talent-assessment/prompt-panel-v2.md`).

How it was checked
- Four research passes fetched every source with WebFetch/WebSearch. Sites that the cloud
  session cannot reach (all Iran-hosted sites, the full ITC/ATP PDF, the APA PDF) were fetched
  with read-only GETs from the tools VPS.
- WebFetch returns a model-made summary of each page, so quotes in the annexes are
  near-verbatim, not byte-exact. Re-check a quote at its URL before publishing it.
- Full notes with every URL and quote: `research_notes/A_identity_authz_logging.md`,
  `B_ux_a11y_billing.md`, `C_assessment_privacy_iran.md`, `D_comparable_products.md`.
- The "ChatGPT draft" the prompt mentions was not available to this session, so it could not
  be compared line by line. Section 1 lists every place where the prompt's own baseline (which
  summarises that research) disagrees with the sources.

Verdict words: CONFIRMED, CORRECTED (the prompt was wrong), PARTLY (true with a limit),
NOT VERIFIABLE (source unreachable; treated as unknown, never assumed).

---

## 1. What changed versus the prompt

| # | Prompt said | Source says | Effect on the design |
|---|---|---|---|
| 1 | NIST SP 800-63-4 was "final at the end of 2024" | Final in **July 2025** (63B-4 dated 31 Jul 2025); August 2024 was the second draft | Cite the 2025 final |
| 2 | Passwords: at least 8 characters | **15** when the password is the only factor, 8 only as part of MFA; blocklist check SHALL; no composition rules, no forced rotation | Email+password accounts on website 4 need a 15-character minimum or a second factor. Listed as a gap (stage S18) |
| 3 | "Rate-limit OTP" | Hard ceiling: at most 100 consecutive failed attempts per authenticator; out-of-band codes valid 10 minutes at most, single use | Current code is stricter (5 attempts, 5 minutes). Keep |
| 4 | SMS OTP "should not be the only factor for high-privilege roles" | NIST's actual duties for a *restricted* authenticator: offer a non-restricted alternative, tell users about the risk, record the risk acceptance, keep a migration plan | Design: email+password stays as the alternative path; a short risk notice on `/signup`; passkeys stay in "later" |
| 5 | Session rules unspecified | AAL1: overall timeout SHOULD be ≤ 30 days. AAL2: SHOULD be 24 h overall and 1 h idle | The 8 h idle default for staff is stricter than AAL1 and looser than AAL2; kept as the owner default, configurable |
| 6 | WCAG 2.2 "AA includes 2.4.11, 2.5.7, 2.5.8, 3.2.6, 3.3.7, 3.3.8" | 3.2.6 and 3.3.7 are **Level A**; the other four are AA. 4.1.1 Parsing was removed. `wcag22aa.org` is not a W3C site | Checklist in `08_design_system.md` cites W3C and the right levels |
| 7 | 3.3.8: "allow paste/autofill of OTP" | W3C: a service that *requires manual transcription* of a code fails. Paste and autofill must work | One OTP input, `autocomplete="one-time-code"`, never six split boxes that block paste |
| 8 | OWASP "says pure RBAC is poorly suited to multi-tenant systems" | Narrower: RBAC is poorly suited where "distinct organizations or customers" access the same protected resources. A separate sentence says ABAC/ReBAC should typically be preferred | Same conclusion (roles + relationship + attributes), quoted correctly |
| 9 | OWASP Logging: config changes and suspicious use are in the log list | Those two are in the *optional* list; opt-ins/consents are in the always list | Consent events are mandatory audit events; config changes are logged anyway |
| 10 | AWS SaaS Lens principles as worded in the prompt | The lens has 14 principles; only two match the prompt's wording. Last updated April 2023 | Principles used as stated in section 2.1 |
| 11 | Carbon has four empty-state types incl. "no permission" | Three: no data, user action, error. No-permission is a sub-case of error | Four states still designed (see `03_ia_and_ux.md`); taxonomy credited correctly |
| 12 | Material: "do not mirror media controls, checkmarks or charts' time axes" | Not mirrored: numbers, phone numbers, charts and graphs, media controls. **Timelines and progress bars are mirrored.** Checkmarks are not addressed | Progress bars fill right-to-left; charts keep LTR axes |
| 13 | Wallet: "one wallet per panel", "granted vs purchased, expiry per cohort, oldest first" | Lago's docs are inconsistent on one wallet; expiry in Lago is per wallet, in Stripe per grant; neither says "granted first". Reservation/hold appears only in blog posts, not in either API | One wallet per panel is our choice, not a cited rule. Lots/expiry are a paid-mode extension. No ledger reservations (section 2.4) |
| 14 | CSV import flow has seven steps per CSVBox | CSVBox describes four (file/template, map, validate, preview/submit). Encoding, duplicates and limits come from other sources | Our wizard keeps the fuller flow, credited to several sources |
| 15 | ISO 10667 as a general client/provider split | Scope is **work and organizational settings only**. Both parts are now flagged "to be revised" (new projects registered 27 May 2026) | Used for the employer panel; for schools and clinics it is an analogy, not a standard |
| 16 | FHIR: definition separate from response instance | Confirmed, but core FHIR does **not** require the response to pin a questionnaire version | Pinning the version is our own rule (already done: `ts.attempt.version_id`) |
| 17 | "Verify whether eNamad is still required" | **Still required** for a payment gateway (payment companies' documentation, updated September 2026). An "unstarred" eNamad exists for micro-businesses | Paid phase needs eNamad + tax code first |
| 18 | VAT not stated | **10%** in 1405 (the 12% in the news was the budget bill). Whether a paid psychometric report is VAT-exempt is NOT VERIFIABLE; needs a tax adviser | Recorded for the paid phase |
| 19 | Iran data-protection bill "status to verify" | **No personal-data statute is in force.** Binding today: Electronic Commerce Law 1382 Arts. 58–59 and 71; the 1402 cyberspace privacy directive (administrative) | Section 2.6. We claim compliance with nothing that is not in force |
| 20 | — (not in the prompt) | Psychology and Counseling Organization notice of 8 Mehr 1405: **no app, platform or website is endorsed by it** | Marketing rule: never imply PCO approval of the platform |
| 21 | — | Under 18: guardian consent plus the minor's assent (APA 3.10(b), ITC Test Use 2.4.5, PCO ethics 2-9, Child Protection Law 1399) | TALENT-INV-15 is marked `adult` in code but is sent to school students. Gap; stage S16 |
| 22 | — | PCO ethics 6-4: records kept at least 5 years after the intervention ends; for minors until legal age | Retention default for clinical panels |
| 23 | Group threshold n ≥ 5 as a default | No law sets a number. Education practice (NCES) uses 10 with complementary suppression; HR tools default to 5 | Default stays 5 (owner's default) with complementary suppression; 10 for schools is offered as a decision |

---

## 2. Verified baseline the design uses

### 2.1 Tenancy and identity
- **AWS SaaS Lens** (CONFIRMED in substance): bind user identity to tenant identity, isolate
  all tenant resources, create tenant-aware operational views, automate onboarding, plan for
  multiple tenant experiences.
  https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/general-design-principles.html
- **One account, many memberships** (CONFIRMED): one login, several organizations, a switcher,
  role per organization. https://workos.com/blog/user-management-for-b2b-saas ·
  https://clerk.com/multi-tenancy
- **Invitations** (PARTLY): documented defaults for expiry are 7 days (WorkOS, range 1–30),
  7 days (Auth0, max 30), 30 days (Clerk). WorkOS warns to check that the accepting identity
  matches the invited one. Our values: colleague invite 7 days, participant invite 30 days.
- **Authentication** (NIST SP 800-63B-4, final July 2025): see rows 1–5 above.
  https://pages.nist.gov/800-63-4/sp800-63b.html
- **OWASP ASVS 5.0** (released May 2025): chapters V6 Authentication, V7 Session Management,
  V8 Authorization (V8.4.1 is an explicit cross-tenant control), V16 Logging. Out-of-band codes
  ≤ 10 minutes, single use, rate-limited. https://github.com/OWASP/ASVS
- **Vendor/support access** (CONFIRMED): customer-granted, time-boxed, audited (Salesforce
  "Grant Login Access"; Azure Customer Lockbox needs customer approval and expires in 4 days).

### 2.2 Authorization
- **OWASP Authorization Cheat Sheet** (CONFIRMED): least privilege, deny by default, validate
  on every request, check the specific object, enforce server-side including static resources,
  fail safely, log, test. https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- **WorkOS two-layer model** (CONFIRMED): organization roles bundle `resource:action`
  permissions; resource-level checks decide "this record". "Keep hierarchies shallow (2-4
  levels)". https://workos.com/blog/rbac-fga-multi-tenant-b2b

### 2.3 Logging
- **OWASP Logging Cheat Sheet** (PARTLY, see row 9): always log authentication results,
  authorization failures, user administration, sensitive-data access, import/export, opt-ins.
  Never log session ids, access tokens, passwords, health data, or PII beyond need; hash or
  mask identifiers. ASVS V16.2.5: sensitive data in logs only hashed or masked.
  https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

### 2.4 Credits and metering
- **Idempotent usage events** (CONFIRMED): Lago deduplicates on `transaction_id` ("if the same
  event arrives twice, it is billed once").
- **Append-only ledger** (CONFIRMED): Stripe describes credit grants as an immutable,
  append-only ledger with a ledger balance and an available balance; grants carry category
  (paid/promotional), priority and expiry. https://docs.stripe.com/billing/subscriptions/usage-based/billing-credits
- **When comparable assessment platforms charge** (annex D): at first delivery of the result or
  report (Q-global, MHS MAC+/TAP, PAR), or at test start (TestGorilla, GL Testwise), or reserved
  at link creation and charged on completion (Hogrefe HTS). Nobody documents charging for
  merely sending an invitation. Where a unit is earmarked at assignment, it returns when the
  invitation expires. MHS never blocks administration when credits run out.
- Design choice that follows: **debit when the attempt is scored (= first delivery of the
  result), keyed by the attempt; no ledger reservations; open invitations are shown as an
  informational "committed" number.**

### 2.5 UX and accessibility
- **WCAG 2.2** (W3C Recommendation; also ISO/IEC 40500:2025): new criteria and levels in row 6.
  WCAG 3 is still a Working Draft (September 2026) and does not replace 2.2.
  https://www.w3.org/TR/WCAG22/
- **Target size 2.5.8**: 24×24 CSS px with five exceptions (spacing, equivalent, inline,
  user-agent, essential). Our controls already use 44 px (`--control-min`).
- **OTP field** (CONFIRMED, GOV.UK and Twilio): one text input, `inputmode="numeric"`,
  `autocomplete="one-time-code"`, allow spaces. WebOTP is Chromium-only; not relied on.
- **Empty states** (NN/g, CONFIRMED): state the system status, teach what belongs here, give a
  direct action. https://www.nngroup.com/articles/empty-state-interface-design/
- **Data tables** (NN/g + Carbon, PARTLY): four user tasks (find, compare, view/edit a row,
  act on rows); filters, bulk selection with a batch bar, column hide, frozen header,
  pagination. "Cards on mobile" and "KPIs click through to lists" are common practice but were
  **not found in the fetched sources**; they stay as our own design rules.
- **Charts**: WCAG 1.1.1 asks for a text alternative, 1.4.1 forbids colour as the only signal.
- **Bidirectional layout**: Persian digits (U+06F0–06F9) are bidi class EN like Latin digits.
  Use `dir="ltr"` or `<bdi>` for phone numbers, emails, codes and URLs inside RTL text.
- **Import UX** (PARTLY, row 14): template, map columns, validate with inline errors, preview,
  import valid rows, download an error report; detect encoding (including Windows-1256) and
  delimiter; flag duplicates before writing; state the row limit up front.
- **Persian data conventions** (CONFIRMED): Excel opens UTF-8 CSV correctly when it starts with
  a BOM; normalise ي→ی, ك→ک and both digit sets on input and in search.
- **SMS consent and quiet hours** (PARTLY): no Iranian rule on quiet hours was found. Twilio's
  practice (consent per sender and purpose, opt-out wording, quiet hours 21:00–08:00 recipient
  time, OTP exempt) is used as the model; the hours are a platform setting.

### 2.6 Assessment standards, privacy and Iranian rules
- **ITC/ATP Guidelines for Technology-Based Assessment (2022)** (CONFIRMED, 11 chapters, 262
  guidelines). Used directly: 3.3 capture each response when submitted; 3.9 resume where the
  test taker stopped; 3.6 score on the server; 5.3 printed reports are date-stamped and show
  filters and sample sizes; 5.14 audit trail for score changes; 5.17 role-appropriate data per
  login; **5.18 minimum display thresholds for group reports**; 6.2 versioned content; 9.6
  minimum data, kept only as long as needed; 9.9 a retention period per data type; 9.22
  stronger safeguards for health data and children's data; 10.4 require WCAG.
- **ISO 10667-1/-2:2020** (CONFIRMED with row 15): client vs service-provider duties.
- **HL7 FHIR QuestionnaireResponse** (CONFIRMED): status `in-progress | completed | amended |
  entered-in-error | stopped`; `subject` (about whom) vs `source` (who answered) vs `author`
  (who recorded). https://hl7.org/fhir/questionnaireresponse.html
- **APA Ethics Code 2017, §9** (CONFIRMED; a new draft was out for comment until March 2025 and
  had not been adopted by August 2026): 9.04 test data are released to the client or to persons
  the client names; 9.07 no promotion of use by unqualified persons; 9.10 results are explained
  to the person unless the relationship precludes it and that was said in advance; 9.11 test
  materials (items, manuals, scoring keys) stay secure.
- **GDPR as a reference model only**: test results are health data when they reveal or are
  used to infer mental-health status (Art. 4(15), Recital 35); explicit consent (Art. 9(2)(a));
  child consent age 16, States may lower to 13 (Art. 8); no solely automated decisions with
  significant effect (Art. 22), so hiring keeps a human decision-maker; requests answered within
  one month (Art. 12(3)); employee consent is weak because of the power imbalance (EDPB
  05/2020 para 21).
- **Iran, in force today**
  - Electronic Commerce Law 1382, Art. 58: storing, processing or distributing personal data
    about a person's physical or **mental condition** without **explicit consent** is unlawful.
    Art. 59: stated purpose, only what is necessary, accurate, the person can access, correct
    and ask for complete erasure. Art. 71: one to three years' imprisonment.
  - National Center for Cyberspace privacy directive (11 Dey 1402, administrative; enforcement
    NOT VERIFIABLE): published privacy policy, explicit consent, mandatory vs optional data
    separated, two months' notice before a policy change, deletion on request, identity data
    stored encrypted.
  - Psychology and Counseling Organization: licence mandatory to practise; ethics code 5-4 (no
    administration, scoring or interpretation by unqualified persons), 5-5 (results on the
    written request of the client or guardian), 2-9 (guardian consent for minors), 6-4
    (records kept 5 years; minors until legal age).
  - Child and Adolescent Protection Law 1399: an adolescent is under 18.
- **Iran, not in force**: the government personal-data bill (approved by the cabinet 20 Tir
  1403, not in the Majlis register), the MPs' plan (received 15 Mehr 1403, no vote), the
  Supreme Council of Cyberspace data-governance document.
- **Iran, paid phase** (not needed while the service is free): eNamad and a tax tracking code
  are prerequisites for a gateway; a company must issue electronic invoices through the
  taxpayers' system once it charges; VAT 10%.

### 2.7 How comparable products build the same thing (annex D)
Near-universal across NovoPsych, Q-global, PARiConnect, MHS, Hogrefe HTS, TestGorilla, GL
Testwise, Morrisby:
1. A **person record separate from assessments**, with minimal required identity and an
   optional external ID.
2. Test takers **need no account** to start from a link (we keep sign-in by mobile, because
   our participants own their results and come back to them).
3. Delivery by personal link, open link/QR, access code, or a group sitting.
4. **Groups** as a first-class object for sending and reporting.
5. One status set: pending, in progress, completed, expired.
6. Per-assignment expiry (commonly 30 days), one automatic reminder, a reactivate action.
7. Roles: owner, supervisor (sees all), practitioner (own clients), view-only reviewer; client
   transfer between practitioners with a record.
8. Organization-level credits with usage history and low-balance alerts; charging at result
   delivery; administration is not blocked when credits run out.
9. Results hidden from the organization by default where the person owns them; parent access
   by a student-initiated, revocable link (Morrisby).
10. Archive distinct from delete, with a recovery window.

Patterns we deliberately do **not** copy: re-linking people by name plus birth date
(NovoPsych), links and QR codes that never expire, unassigned clients visible to every user,
imports that create duplicates, consent stored apart from the person, vendor-side deletion
after inactivity, "anonymised" scores kept after deletion, erasure only by emailing support.
No product in the sample documents a minimum group size for cohort reports; ours is a
deliberate addition (ITC/ATP 5.18).

---

## 3. Not verifiable today (treated as unknown)
1. Enforcement of the 1402 privacy directive, and whether the data-governance document has
   been approved.
2. Licence titles on the national licensing portal for online counselling or assessment, and
   the PCO by-law on activity in cyberspace.
3. Shaparak's own rules for payment facilitators (evidence is from licensed payment companies).
4. VAT treatment of paid online psychometric reports.
5. Clause-level text of ISO 10667 (paywalled) and the current stage of the APA draft code.
6. Material Design 3 bidirectionality page (blocked); the M1 page was used.
7. Clerk and Auth0 invitation details beyond expiry defaults.

## 4. Sources
Every URL actually opened is listed per claim in the four annex files. Starting set from the
prompt, all reached except where noted above: OWASP Authorization and Logging cheat sheets,
WorkOS (two articles), Clerk, AWS SaaS Lens, NIST SP 800-63-4, Lago, Flexprice, Stripe billing
credits, W3C WCAG 2.2, NN/g, Carbon, Material (M1), CSVBox, Dromo, Smashing Magazine, ITC/ATP
guidelines, ITC Guidelines on Test Use, ISO 10667-1/-2, HL7 FHIR R4/R5, APA Ethics Code 2017,
gdpr-info.eu, ICO, EDPB Guidelines 05/2020, NCES SLDS Technical Brief 3, rc.majlis.ir,
ekhtebar.ir (law texts), majazi.ir, pcoiran.ir, payment-company documentation, vendor help
centers of the products in 2.7.
