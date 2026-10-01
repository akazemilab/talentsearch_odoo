# Research baseline C — verification notes (checked 2026-10-01 = 9 Mehr 1405)

## How this was checked (read first)

- **WebFetch/WebSearch** from the cloud session reached iso.org, hl7.org, gdpr-info.eu, ico.org.uk, edpb.europa.eu, nces.ed.gov, unicode.org, support.microsoft.com, MDN.
- **Unreachable from WebFetch:** every Iran-hosted site (rc.majlis.ir, enamad.ir, shaparak.ir, pcoiran.ir, peivast.com, digiato.com, donya-e-eqtesad.com, wikihoghoogh.net … → `robots.txt fetch failed: ConnectTimeout`), apa.org HTML (Incapsula challenge), web.archive.org (blocked), fa.wikisource/fa.wikipedia ("cache-only"). The ITC PDF was truncated by WebFetch after chapter 2. Direct `curl` from the cloud container is blocked by the egress policy (403 on CONNECT).
- **Workaround used:** the Iranian sources, the full ITC/ATP PDF and the APA PDFs were fetched **from the tools VPS (Iranian IP) with read-only HTTP GETs** via `vps_exec`, text extracted there, and only short excerpts printed. Small reusable tools were left in `/root/research/` on the VPS: `rfetch.py` (parallel fetch + text/PDF extraction), `rgrep.py` / `rbody.py` (Persian-safe excerpts), `rsearch.py` (DuckDuckGo HTML search; rate-limits after ~6 queries), `venv/` (pypdf), `out/*.txt` (extracted texts), `itc_guidelines.json` (all 262 numbered ITC/ATP guidelines). ~24 MB; safe to delete.
- Still unreachable even from the VPS: irna.ir / isna.ir / wikihoghoogh.net / qavanin.ir (JS cookie challenge, 71-byte body), mojavez.ir and shaparak.ir (JS single-page apps, no server-rendered text), apa.org HTML pages (empty body), enamad.ir rules/news sub-pages (404).
- Quotes are verbatim, under 25 words; Persian quotes carry an English gloss. Dates given Jalali → Gregorian.

---

### C1 — ITC/ATP Guidelines for Technology-Based Assessment (2022)
**Verdict: CONFIRMED** (eleven chapters; the prompt's paraphrased chapter names are close but not the real titles).

**Source fetched:** https://www.intestcom.org/upload/media-library/guidelines-for-technology-based-assessment-v20221108-16684036687NAG8.pdf (full text via VPS, 486k chars; also identical ATP copy https://www.testpublishers.org/assets/TBA%20Guidelines%20final%202-23-2023%20v4.pdf) and https://www.siop.org/tip-article/new-guidelines-for-technology-based-assessment/

**Actual chapter list (Part III), count = 11:** 1 Test Development · 2 Test Design and Assembly · 3 Test Delivery Environments · 4 Scoring · 5 Digitally Based Results Reporting · 6 Data Management · 7 Psychometric and Technical Quality · 8 Test Security · 9 Data Privacy · 10 Fairness and Accessibility · 11 Global Testing Considerations. (Parts I–II are introduction/foundations; Part IV "Emerging Applications": AI, big data/social media, facial recognition, automated item generation, regulatory considerations; plus glossary and a locked-down-browser checklist.) The text contains 262 numbered guidelines (1.x 49, 2.x 12, 3.x 44, 4.x 28, 5.x 21, 6.x 15, 7.x 15, 8.x 8, 9.x 22, 10.x 25, 11.x 23).

**Concrete guidelines (verbatim, with real numbers) relevant to a test player, reports and data:**
- **3.3** "Web-based delivery systems should be designed to prevent the loss of test taker response data (e.g., capturing each test taker response when submitted, where possible)."
- **3.9** "The test system/platform should be capable of allowing test takers to resume the test (where they stopped or as close to it as possible) after a service disruption or a planned break."
- **3.6** "Scoring should be conducted at the server level to prevent compromise or subversion at the browser level…"
- **3.5** role-based access "commensurate with the minimum required for specific roles".
- **3.27** "The user interface for test delivery should be designed to respond to the types of devices on which the test is intended to be administered."
- **3.11 / 3.13** troubleshooting information for test takers; "Ethical issues surrounding the impact of negative feedback should be taken into consideration, and directions for accessing support should be provided…"
- **4.21** "Data collection systems used for tests should be able to document all technological disruptions, including information about testing interruptions for each test taker."
- **4.22–4.24** recover data after disruptions; imputation only if empirically validated; may choose not to report scores, after weighing consequences.
- **4.25** "If response times are used in scoring the test, this should be disclosed to test takers…"
- **5.2** define the types of reported scores (raw, scaled, classifications). **5.3** "Digital reports, when printed or exported, should be date stamped, identify any filters used, and indicate sample sizes, where applicable."
- **5.6** reports "should be piloted with stakeholders … for accessibility, usability, and understanding prior to operational deployment". **5.10** interpretive materials available to anyone who accesses reports.
- **5.14** audit trail for any score change. **5.16** confidentiality agreement for anyone with access to non-public scores. **5.17** role-appropriate data per login.
- **5.18** "When group-level interactive reporting tools are available, data privacy mechanisms such as minimum display thresholds … should be implemented…" (direct support for small-group suppression).
- **5.19** scores delivered so "only the intended recipient receives them and the transmission is secure". **5.20** ISO 27001-like security for score stores.
- **6.2** "Data models should be designed to address the management of different versions and stages of assessment content…" **6.7** backup, retention and removal procedures. **6.8** integrity of responses, scores and evidence.
- **7.4** "Claims of assessment score comparability should support score interpretation across different technologies, devices, and administrative conditions…"
- **9.6** "…only collect the minimum personal data needed … and retain it only as long as needed for the stated purpose(s)…" **9.9** document retention period per data type. **9.10** secure deletion after retention. **9.8** encrypt/pseudonymise. **9.11–9.12** clear privacy notice; rights told in advance. **9.22** enhanced safeguards for health data and "children's personal data".
- **10.4** "A testing organization should require WCAG compliance." **11.20–11.23** hardware list, practice opportunity, and score-interpretation info before testing.

**Nuance:** the guidelines are "should" statements (best practice), not a certifiable standard. The device-comparability guidance sits in ch. 7 (7.4–7.7), not ch. 3.
**Newer:** no newer edition found; the 2022 version (ATP file dated 2-23-2023) is still the one both ITC and ATP host.

---

### C2 — ISO 10667-1:2020 / 10667-2:2020
**Verdict: CONFIRMED, with a status update** (both are now flagged for revision).

**Sources fetched:** https://www.iso.org/standard/74716.html · https://www.iso.org/standard/74717.html · https://www.iso.org/standard/94563.html · https://www.iso.org/standard/94564.html

- Exact titles: "Assessment service delivery — Procedures and methods to assess people in work and organizational settings — Part 1: Requirements for the client" and "… — Part 2: Requirements for service providers". Edition 2, published Nov 2020, ISO/TC 260.
- Part 1 abstract: "establishes requirements and guidance for clients working with one or more service provider(s) to carry out the assessment…"; Part 2: "…requirements and guidance for one or more service provider(s) in working with a client…".
- Part 2 abstract covers (c) "the collection, processing and storage of personal data of assessment participants and of assessment data" and interpretation of results/reports; Part 1 covers (e) "decisions about the access, use and storage of assessment results and subsequent reports".
- **Status (ISO page, dated 2026-05-27): 90.92 "International Standard to be revised"** for both parts. Edition 3 projects are registered: **ISO/AWI 10667-1 and ISO/AWI 10667-2, stage 20.00 (new project registered), 2026-05-27.**

**Correction/nuance:** the abstracts do not literally list "agreement, informing participants, feedback"; those are clauses in the body (not readable without buying the standard). Scope is **work and organizational settings only** — it does not cover school or clinical assessment, so it is a reference for the employer panel only. "No detailed technical or professional specifications are included".
**Newer:** the revision started in May 2026; no draft text is public yet, so the 2020 edition remains the citable one.

---

### C3 — HL7 FHIR QuestionnaireResponse / Questionnaire
**Verdict: CONFIRMED** (status set, subject/author/source, separation of definition and response); **PARTLY** on "responses must reference the version".

**Sources fetched:** https://hl7.org/fhir/questionnaireresponse.html (R5, v5.0.0) · https://hl7.org/fhir/R4/questionnaireresponse.html · https://hl7.org/fhir/valueset-questionnaire-answers-status.html · https://hl7.org/fhir/questionnaireresponse-definitions.html · https://hl7.org/fhir/questionnaire.html · https://hl7.org/fhir/references.html

- Status codes (R4 and R5): "in-progress | completed | amended | entered-in-error | stopped".
  - amended: "…filled out with answers, then marked as complete, yet changes or additions have been made to it afterwards."
  - stopped: "…partially filled out with answers but has been abandoned. No subsequent changes can be made."
  - entered-in-error: "This QuestionnaireResponse was entered in error and voided." (status is a modifier element).
- subject: "who/what the answers apply to, but is not necessarily the source of information." source: "The individual or device that answered the questions about the subject." author: "…received the answers to the questions in the QuestionnaireResponse and recorded them in the system."
  - Requirement text for source: "When answering questions about a subject that is minor, incapable of answering or an animal, another human source may answer the questions."
- Definition vs response: "Questionnaires define 'permitted' answers and are subject and time-independent, while QuestionnaireResponse define a specific user's answers…at a particular time-point".
- `questionnaire` is `canonical(Questionnaire)`; items link by `linkId` ("unique within the Questionnaire").
- Amendments: there is no separate amendment resource; the same resource is updated, status becomes `amended`, and `authored` is "the date and/or time that this questionnaire response was last modified by the user". History is the server's resource versioning.

**Correction/nuance:** core FHIR does **not** require the canonical to carry a version. Versioned form is `url|version`; "if a canonical URL reference does not have a version … the system … should pick the latest version". So pinning the questionnaire version is a design decision you must make yourself (recommended for psychometrics). The SDC implementation-guide profile could not be read (page returned only a header), so any stricter SDC rule is NOT VERIFIED.
**R4 → R5 differences:** `questionnaire` 0..1 → **1..1 (required)**; `identifier` 0..1 → 0..*; `source`/`author` widened to include Device and Organization; `item.answer.value[x]` now 1..1. R5 Questionnaire adds `versionAlgorithm[x]`. R5 is still the current published release on hl7.org/fhir.

---

### C4 — APA Ethics Code, Section 9
**Verdict: CONFIRMED** (text) ; revision status **PARTLY** verified.

**Source fetched:** https://www.apa.org/ethics/code/ethics-code-2017.pdf (full text via VPS; the HTML page is behind an Incapsula challenge). Council minutes: https://www.apa.org/about/governance/council/minutes-february-2026.pdf and …/minutes-august-2026.pdf. Draft notice: https://apadivision16.org/2024/12/new-apa-draft-ethics-code-available-for-public-comment/

Header: "Adopted August 21, 2002 Effective June 1, 2003 … With the 2016 Amendment to Standard 3.04 … Effective January 1, 2017".

- **9.03(a)** consent required "except when (1) testing is mandated by law…; (2) informed consent is implied because testing is conducted as a routine educational, institutional, or organizational activity…; or (3) one purpose of the testing is to evaluate decisional capacity." Consent "includes an explanation of the nature and purpose of the assessment, fees, involvement of third parties, and limits of confidentiality".
- **9.03(b)** persons with questionable capacity are still informed "using language that is reasonably understandable to the person being assessed."
- **9.04(a)** "The term test data refers to raw and scaled scores, client/patient responses to test questions or stimuli, and psychologists' notes and recordings…" · "Pursuant to a client/patient release, psychologists provide test data to the client/patient or other persons identified in the release." · may refrain "to protect a client/patient or others from substantial harm or misuse or misrepresentation of the data or the test". **(b)** without a release, "only as required by law or court order."
- **9.06** when interpreting, "including automated interpretations", take into account purpose, test factors and "situational, personal, linguistic, and cultural differences"; "indicate any significant limitations".
- **9.07** "Psychologists do not promote the use of psychological assessment techniques by unqualified persons, except … for training purposes with appropriate supervision."
- **9.09(c)** "Psychologists retain responsibility for the appropriate application, interpretation, and use of assessment instruments, whether they score and interpret such tests themselves or use automated or other services." (a) describe "purpose, norms, validity, reliability, and applications".
- **9.10** explanations of results are given "to the individual or designated representative unless the nature of the relationship precludes" it (e.g. pre-employment screening) "and this fact has been clearly explained … in advance."
- **9.11** "The term test materials refers to manuals, instruments, protocols, and test questions or stimuli and does not include test data as defined in Standard 9.04".

**Nuance:** note 9.04's second sentence — the parts of test materials that carry the client's responses count as test data. 9.03(a)(2) is the basis for "implied consent" in routine school/employer testing, but it does not remove the duty to explain.
**Revision status:** a full draft of a new code was released for public comment on 19 Dec 2024 (deadline "March 19, 2025"). The APA Council minutes of Aug 2025, Feb 2026 and 4–5 Aug 2026 contain **no** adoption of a new code (text search for "Ethics Code Task Force"/"new Ethics Code" = 0 hits) and the Feb 2026 minutes still cite the "(2017)" code. So **the 2017 code is still in force as of Aug 2026**. The current stage of the draft (second comment round, planned vote date) is NOT VERIFIED — apa.org/ethics/task-force is unreadable from both routes.

---

### C5 — GDPR as reference model
**Verdict: CONFIRMED** on the articles; **PARTLY** on "psychological test results = health data" (it depends on the instrument).

**Sources fetched:** https://gdpr-info.eu/art-4-gdpr/ · /recitals/no-35/ · /art-9-gdpr/ · /art-8-gdpr/ · /art-22-gdpr/ · /art-12-gdpr/ · /art-15-gdpr/ · /art-17-gdpr/ · /art-20-gdpr/ · https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-are-the-conditions-for-processing/ · …/special-category-data/what-is-special-category-data/ · …/lawful-basis/consent/when-is-consent-appropriate/ · https://www.edpb.europa.eu/system/files/documents/files/file1/edpb_guidelines_202005_consent_en.pdf · https://nces.ed.gov/pubs2011/2011603.pdf · https://support.cultureamp.com/en/articles/7048386-confidentiality-protections-in-reporting

- Art. 4(15): "personal data related to the physical or mental health of a natural person … which reveal information about his or her health status". Recital 35: data "which reveal information relating to the past, current or future physical or mental health status".
- ICO: you process special category data when you "intend to make an inference linked to one of the special categories" — "regardless of how confident you are that the inference is correct."
- **Nuance:** clinical/symptom instruments (depression, anxiety, clinical personality scales) are health data. Aptitude, interest or normal-range personality results are not automatically health data; they become so when used to infer mental-health status. Safe design: treat all results as special-category.
- Art. 9(2)(a): "explicit consent to the processing of those personal data for one or more specified purposes". ICO: explicit = "confirmed in a clear statement (whether oral or written), rather than by any other type of affirmative action."
- Art. 8(1): lawful "where the child is at least 16 years old"; Member States may lower, not below 13. Art. 8(2): "reasonable efforts to verify" parental consent. (Applies only to consent-based information-society services offered directly to a child.)
- Art. 22(1): right "not to be subject to a decision based solely on automated processing, including profiling, which produces legal effects … or similarly significantly affects him or her." Art. 22(4): no such decisions on special-category data unless 9(2)(a) or (g). Art. 4(4) profiling expressly includes "performance at work". → employment screening must keep a human decision-maker.
- Art. 12(3): "without undue delay and in any event within one month of receipt of the request" (extendable by two months). Art. 15(3) copy of the data. Art. 17(1)(b) erasure on withdrawal of consent; 17(3) exceptions (legal obligation, legal claims, research). Art. 20(1) portability only where processing is based on consent/contract and "carried out by automated means"; "structured, commonly used and machine-readable format".
- Imbalance of power — EDPB Guidelines 05/2020 para 21: "it is unlikely that the data subject is able to deny his/her employer consent to data processing without experiencing the fear or real risk of detrimental effects". ICO: "If you are a public authority or are processing employee data, or are in any other position of power over an individual, you should look for another basis".
- Small groups — NCES SLDS Technical Brief 3 (US education): "Use a minimum of 10 students for the reporting subgroup size limitation." / "Suppress results for all reporting groups with 0 to 9 students." plus complementary suppression of related subgroups and top/bottom coding of extreme percentages. HR-survey practice: Culture Amp exposes a configurable "reporting group minimum" (its own example uses 5) and hides the next-smallest group to stop identification by subtraction. ITC/ATP 5.18 asks for "minimum display thresholds".

**Correction/nuance:** GDPR itself sets **no numeric minimum group size**; n≥10 (education, NCES) and n≥5 (common HR default) are conventions. Threshold alone is not enough — subtraction between overlapping groups must also be blocked. US ED's PTAC FAQ page could not be read (landing page only); ICO anonymisation guidance was not fetched.

---

### C6 — IRAN: personal-data law (most care taken here)
**Verdict: CONFIRMED that there is still NO personal-data-protection statute; everything "comprehensive" is a draft.**

**Sources fetched (via VPS unless noted):** https://rc.majlis.ir/fa/legal_draft/show/1816729 · https://rc.majlis.ir/fa/legal_draft/show/1675111 · https://rc.majlis.ir/fa/legal_draft?keyword=داده · https://peivast.com/p/202493 · https://peivast.com/p/212052 · https://digiato.com/tech/personal-data-protection-plan-in-parliment · https://donya-e-eqtesad.com/fa/tiny/news-4145558 · https://www.tabnak.ir/fa/news/1266116 · https://www.ekhtebar.ir/قانون-تجارت-الکترونیکی/ · https://majazi.ir/fa/page/102098-… and https://majazi.ir/fa/sis_law_roles/56414-… · ekhtebar.ir text of the privacy directive · https://rc.majlis.ir/fa/law/show/135717 · ekhtebar.ir text of the Citizens' Rights Charter · https://moshirin.com/laws/ghanoon-melli-toseeh-hoosh-masnoei · https://peivast.com/p/236820 · https://www.dlapiperdataprotection.com/index.html?t=law&c=IR (WebFetch)

**A. Drafts (NOT law):**
1. Government bill «لایحه حفاظت از داده‌های شخصی»: approved by the cabinet's legal commission 15 Ordibehesht 1403 (4 May 2024) and by the cabinet on 20 Tir 1403 (10 Jul 2024): «در جلسه ۲۰ تیرماه هیات دولت به تصویب نهایی رسید» ("given final approval in the cabinet session of 20 Tir"). On 30 Mehr 1403 (21 Oct 2024) it had still not been sent to parliament; the new ICT minister said «این لایحه به کمیسیون برگشته» ("the bill has gone back to the commission"). **The Majlis register (rc.majlis.ir) today lists no government bill on personal data** — keyword «داده» returns 4 entries, all MPs' plans.
2. MPs' plan «طرح حفاظت از داده‌های شخصی», registration no. 96, 12th Majlis: «تاریخ اعلام وصول: 1403/07/15» (received 6 Oct 2024). Its status list shows only three events: receipt, and two Research Center reports dated 1404/01/17 (6 Apr 2025). No committee report, no vote on generalities, nothing sent to the Guardian Council.
3. Older plan «طرح حمایت و حفاظت از داده و اطلاعات شخصی», 11th Majlis, reg. no. 612, received 1399/07/12 — lapsed with that parliament.
4. Supreme Council of Cyberspace «سند حکمرانی داده» (data-governance document): on 23 Tir 1404 (14 Jul 2025) the NCC head only hoped it «در جلسه بعدی شورای عالی فضای مجازی نهایی شود» ("be finalised at the next SCC session"). It does **not** appear in the official list of approved/notified documents on majazi.ir as fetched today (latest entry there is dated 14 Shahrivar 1405). Treat as not yet in force. NOT VERIFIABLE beyond that list.

**B. In force now:**
1. **Electronic Commerce Law, approved 1382/10/17 (7 Jan 2004), Arts. 58–61, 71–73.**
   - Art. 58 (verbatim): «ذخیره، پردازش و یا توزیع «داده پیام»‌های شخصی مبین ریشه‌های قومی یا نژادی، دیدگاه‌های عقیدتی، مذهبی، خصوصیات اخلاقی و «داده پیام»‌های راجع به وضعیت جسمانی، روانی و یا جنسی اشخاص بدون رضایت صریح آن‌ها به هر عنوان غیرقانونی است.» — "Storing, processing or distributing personal data messages revealing ethnic or racial origin, beliefs, religion, moral characteristics, and data messages about a person's physical, mental or sexual condition, without their explicit consent, is unlawful on any ground."
   - Art. 59 conditions even with consent: purposes specified and clearly explained; only as much as necessary; accurate and up to date; data subject can access and correct; «درخواست محو کامل» (can ask for complete erasure) "at any time, subject to the relevant rules".
   - Art. 60: medical and health records follow a separate by-law (Art. 79).
   - Art. 71: violating Arts. 58–59 «به یک تا سه سال حبس محکوم می‌شود» ("is sentenced to one to three years' imprisonment").
   - Scope caveat: the text says «در بستر مبادلات الکترونیکی» (in the context of electronic exchanges) — it is an e-commerce statute, not a general data law; Art. 61 leaves supervision and exceptions to a by-law, and no dedicated data-protection authority was found.
2. **Computer Crimes Law**, approved 1388/03/05 (26 May 2009), 56 articles: Art. 1 criminalises unauthorised access to protected data/systems (91 days–1 year and/or fine). Only Art. 1 was re-read; the other articles were not checked.
3. **NCC privacy directive** «دستورالعمل اجرایی بهبود حفاظت از حریم خصوصی کاربران و شیوه جمع‌آوری، پردازش و نگهداری اطلاعات کاربران در سامانه‌ها و سکوهای فضای مجازی» — issued by the National Center for Cyberspace, «تاریخ تصویب: ۱۱ دی ۱۴۰۲» (1 Jan 2024), amended 1402/12/21. Binds "non-governmental legal persons" and executive bodies that run online systems/platforms. Requirements:
   - publish a privacy policy and «رضایت صریح آنان … را اخذ نمایند» (obtain users' explicit consent); separate mandatory from optional data items;
   - give at least two months' notice before changing the policy and obtain consent again;
   - collect only what is needed for the stated purposes;
   - on a user's deletion request, delete immediately from the online system, keeping only an offline backup for legally required periods, then destroy;
   - identity data «صرفاً باید به صورت رمزنگاری شده ذخیره شود» ("must be stored only in encrypted form");
   - sector regulators/licensing bodies must condition licence renewal on compliance.
   - Caveat: it is an administrative directive, not a statute; Donya-e-Eqtesad (Dey 1403) described «تعلیق یک‌ساله در اجرای دستورالعمل» ("a year-long suspension in implementing the directive"). Actual enforcement: NOT VERIFIABLE.
4. **Citizens' Rights Charter** (presidential, 29 Azar 1395 / 19 Dec 2016) Art. 38: «گردآوری و انتشار اطلاعات خصوصی شهروندان جز با رضایت آگاهانه یا به حکم قانون ممنوع است» ("collecting and publishing citizens' private information is prohibited except with informed consent or by law"). Declaratory; not a statute.
5. Other statutes that touch data: Law on Management of National Data and Information (cited in Art. 9 of the new AI law; government data exchange), and criminal-procedure rules on retaining data (Arts. 667–670 CPC, cited in the directive).

**Newer than the prompt:**
- **«قانون ملی توسعه هوش مصنوعی» (National AI Development Law)** — passed 28 Mordad 1405 (19 Aug 2026), Guardian Council 4 Shahrivar 1405, notified 22 Shahrivar 1405 (13 Sep 2026); 12 articles. Creates a National AI Organization; Art. 9 orders a special AI data-exchange process and standards for "ownership, production, supply, retention, exchange and sharing of data". It is not a personal-data law, but its by-laws may affect any AI-generated interpretation feature.
- Fines in the E-Commerce Law were inflation-adjusted by cabinet decision of 1403/4/4 (e.g. Art. 73 fine now 500,000,000 rial).
- DLA Piper's country page ("Iran has not enacted comprehensive data protection legislation") is dated 2019 — do not cite it as current; the Majlis register above is the current evidence.

---

### C7 — IRAN: professional rules (Psychology and Counseling Organization, PCO)
**Verdict: PARTLY.** Ethics code and licensing duty are sourced; a dedicated licence for an *online assessment platform* could not be found, and PCO states it endorses no platform.

**Sources fetched (via VPS):** https://pcoiran.ir/media/2023/1/10/1673338743108280.pdf (ethics code) · https://pcoiran.ir/centralcouncil/legal/ (founding law) · https://pcoiran.ir/news/post/1604/ · https://pcoiran.ir/news/post/1323/ · https://pcoiran.ir/news/post/1213/ · https://pcoiran.ir/ (licence pages)

- **Founding law:** Art. 4 note 3 «برای اشتغال در حرفه‌های روانشناسی و مشاوره اخذ پروانه از سازمان و عضویت در آن الزامی است» ("to practise psychology or counselling, a licence from the Organization and membership are mandatory"); membership needs at least a master's degree in psychology/counselling.
- **Ethics code** («نظام‌نامه اخلاقی روان‌شناسان و مشاوران», revised at the 68th Central Council session, 05/06/1386 = 27 Aug 2007), section 5 on testing:
  - 5-2 «فقط آزمون‌هایی را به کار می‌برند که قبلاً صلاحیت‌های لازم برای استفاده از آنها را کسب کرده باشند» ("use only tests they are already qualified to use").
  - 5-4 «اجازه نمی‌دهند که آزمون‌های روانشناختی توسط افراد فاقد صلاحیت اجرا، نمره‌گذاری و تفسیر شود» ("do not allow tests to be administered, scored and interpreted by unqualified persons").
  - 5-5 results are given «فقط به درخواست کتبی مراجع، قیم قانونی و یا دادگاه» ("only on the written request of the client, legal guardian or a court"), unless harm or misuse is expected.
  - 5-7 interpretation must weigh test conditions and «تفاوت‌های زبانی و فرهنگی» (linguistic and cultural differences).
  - 2-8 informed agreement in understandable language; 2-9 where a client is a minor, obtain «رضایت قیم قانونی یا ولی» (consent of legal guardian or parent).
  - 3-2 collect only needed information; 3-5 confidentiality exceptions.
  - 6-4 records kept securely «حداقل برای 5 سال بعد از خاتمه مداخله و در مورد کودکان و نوجوانان تا رسیدن به سن قانونی» ("at least 5 years after the intervention ends, and for children/adolescents until legal age").
  - The code says nothing about online/computerised testing ("برخط", "آنلاین", "مجازی": 0 hits; internet appears only for public advice in 9-2).
- **PCO notice of 1405/07/08 (30 Sep 2026 — yesterday):** «خدمات روانشناختی و مشاوره هیچ‌یک از اپلیکیشن‌ها، پلتفرم‌ها، وب‌سایت‌ها … مورد تأیید سازمان نیست» ("the psychological and counselling services of no app, platform or website are endorsed by the Organization"); no platform has received a PCO permit to accredit psychologists; the public should verify licences only at my.pcoiran.ir/member/.
- Other PCO notices (dates not recoverable): anyone offering services online must show «شماره پروانه اشتغال یا شماره عضویت معتبر» (licence or valid membership number) on the page; online workshops/courses/media activity in psychology by natural or legal persons «مستلزم دریافت مجوز رسمی از این سازمان است» ("require an official permit from this Organization").
- Centre licences: PCO issues three kinds — individual, corporate («پروانه مراکز حقوقی») and joint marriage-counselling centres. The individual «پروانه اشتغال مشاوره روانشناسی» can be applied for through the national licensing portal (secondary source, 1401–1403).

**Not verifiable:** mojavez.ir is a JavaScript app and returned no text, so the exact licence titles there (and whether a "مرکز مشاوره آنلاین" title exists) could not be confirmed. An ISNA item titled "انتشار آیین‌نامه فعالیت روانشناسان در فضای مجازی" exists but its text and the by-law itself could not be fetched. No Iranian rule on test security for online delivery was found.
**Design consequence:** do not claim PCO approval of the platform; show each interpreter's licence number; keep interpretation with licensed members; platform-generated narrative reports sit in a grey zone under 5-4.

---

### C8 — IRAN: commerce / payments / tax
**Sources fetched (via VPS):** https://www.zarinpal.com/blog/اینماد-چیست/ (published 1405-03-26, modified 20 Sep 2026) · https://zibal.ir/blog/payment-gateway-without-enamad/ (1403-12-05) · https://modireshop.com/enamad-ir/ (Jul 2026) · https://www.zoomit.ir/tech-iran/387854-enamad-payment-canceled/ (14 Nov 2022) · https://www.ibena.ir/fa/news/143507 (29 Nov 2022) · https://vandar.io/blog/… (gateway prerequisites) · https://ana.ir/fa/news/1084427 (21 Sep 2026) · https://borna.news/fa/news/2395163 (29 Sep 2026) · https://jamejamonline.ir/fa/news/1568634 · nabzgheymat.ir Moadian explainer (17 Sep 2026) · https://keysuntsp.com/blog/modian-system/ · https://www.sepidarsystem.com/blog/vat-sepidar-slg/ (22–26 Jul 2026) · https://etarazoo.com/blog/value-added-tax/ · https://www.rade.ir/32905-… (18 Jul 2026) · https://hamrahyaar.com/books/mavad/3010235 (VAT Law Art. 9) · mehrnews 6699738 / entekhab 901582 (Dec 2025)

**(a) eNamad — Verdict: CORRECTED.** The claim that eNamad became non-mandatory in 2023–2024 is **not supported**. It is still a precondition for an internet payment gateway.
- Zarinpal (updated Sep 2026): «بدون اینماد می‌توان درگاه پرداخت گرفت؟ خیر. طبق مصوبات بانک مرکزی و شاپرک…» ("Can you get a gateway without eNamad? No. Under Central Bank and Shaparak rules…").
- Zibal: mandatory for direct PSP gateways since Bahman 1398 and via payment facilitators since 3 Azar 1400 (24 Nov 2021); «شاپرک هنگام ثبت هر پذیرنده جدید، وضعیت نماد اعتماد الکترونیکی را استعلام می‌کند» ("Shaparak checks eNamad status when registering every new merchant").
- History: in Nov 2022 the Digital Economy Working Group asked Shaparak to cancel the enforcement, but the head of the e-commerce centre replied «لغو اینماد صحت ندارد» ("cancellation of eNamad is not true"). No later repeal found.
- What did change: an **unstarred eNamad** for micro-businesses, issued on identity + domain check, capped at about 100 transactions and 100 million toman a month; and for activities that need a trade licence, only a virtual business licence with a QR code verifiable through mojavez.ir is accepted. So the national licensing portal **complements** eNamad; it does not replace it.
- Caveat: the primary Shaparak/Central Bank circular text was not obtained (shaparak.ir renders no text; enamad.ir rule pages 404). Evidence is from licensed payment companies' current documentation.

**(b) Gateway requirements — Verdict: PARTLY.** Payment-facilitator documentation lists two prerequisites besides KYC: «کد رهگیری مالیاتی» (tax tracking code from tax.gov.ir) and «اینماد». eNamad for a legal entity needs: official-gazette notice and articles of association, latest changes, managing director's ID, a bank account in the company's name, proof of domain ownership, and an activity licence "if needed". Zibal: «داشتن کد مالیاتی برای تمامی کسب‌وکارها الزامی است» ("a tax code is mandatory for all businesses"). Shaparak's own rulebook for facilitators: NOT VERIFIABLE (not reachable).

**(c) Moadian / e-invoices — Verdict: CONFIRMED for a company.** Legal persons must issue electronic invoices; the sales-threshold exemption is only for natural-person business owners.
- New tax-administration circular (reported 21–29 Sep 2026) under Art. 14 bis of the Law on Store Terminals and Taxpayers System: natural-person business owners are exempt in 1405 «مادامی که مجموع فروش کالا و خدمات آنها در سال ۱۴۰۵ کمتر از ۱۲۰ میلیارد ریال باشد» ("as long as their total sales in 1405 are below 120 billion rial") — i.e. 12 billion toman = 25 × the Art. 84 annual exemption (480 million toman).
- Earlier thresholds per the same circular: 180 billion rial for 1402; 144 billion rial for 1403 and 1404.
- «اشخاص حقوقی … حد نصاب ۱۲ میلیاردی شامل آنها نمی‌شود» ("legal persons … the 12-billion threshold does not apply to them"), including non-profit legal persons.
- Regardless of sales, medical/paramedical professions and legal/family-counselling businesses must issue e-invoices (budget law 1402 groups).
- Rollout: 1402 first professional groups; 1403 legal persons and most filers; 1404–1405 threshold regime for individuals. The 100% penalty amnesty for Moadian was extended to the end of 1405 (secondary source).
- An online service company selling to businesses and consumers is in scope once it charges: type 1 invoices (with buyer identity) for business buyers and type 2 for consumers — the type definitions themselves were not re-verified at source.

**(d) VAT — Verdict: CORRECTED.** The standard rate in 1405 is **10%**, not 12%.
- Dec 2025 headlines ("به ۱۲ درصد رسید") described the budget *bill*. Sepidar (Jul 2026): «نرخ مالیات بر ارزش افزوده در سال ۱۴۰۵ مانند سال گذشته، برای بیشتر کالاها 10 درصد است» … «نرخ پایه همانند سال گذشته حفظ شد» ("the base rate was kept as last year"). Two other 2026 accounting sources agree. The VAT Law's own base rate is 9%; annual budget laws have raised it to 10% (one source dates this from the 1403 budget, another from 1404).
- Exemptions, VAT Law (approved 1400/03/02) Art. 9(b): item 1 «خدمات درمانی، تشخیصی و پیشگیری، خدمات توانبخشی و حمایتی» ("treatment, diagnostic and preventive services, rehabilitation and support services"); item 14 «خدمات آموزشی، پژوهشی و ورزشی دارای مجوز از مراجع ذی‌صلاح» ("educational, research and sports services holding a licence from the competent authorities"), under a cabinet by-law.
- **Nuance:** whether a paid online psychometric report counts as an exempt diagnostic or licensed educational service, or as a taxable software/online service, is NOT VERIFIED — it turns on holding the relevant licence and needs a tax adviser's ruling. The 1405 Budget Law text itself was not read; the 10% figure rests on three consistent secondary sources dated May–Jul 2026.

---

### C9 — Guardian consent and minors
**Verdict: CONFIRMED.**

**Sources fetched:** APA PDF (as C4) · https://www.intestcom.org/files/guideline_test_use.pdf (ITC Guidelines on Test Use; via WebFetch and VPS) · gdpr-info.eu Art. 8 · https://rc.majlis.ir/fa/law/show/97937 (Civil Code) · https://rc.majlis.ir/fa/law/show/1554444 (Child and Adolescent Protection Law) · PCO ethics code (as C7)

- APA 3.10(b): for persons legally incapable of consent, psychologists "(1) provide an appropriate explanation, (2) seek the individual's assent, (3) consider such persons' preferences and best interests, and (4) obtain appropriate permission from a legally authorized person". 3.10(d): "appropriately document written or oral consent, permission, and assent."
- ITC Test Use 2.4.5: "Gain the explicit consent of test takers or their legal guardians or representatives before any testing is done." 1.5.1–1.5.6: specify who has access, explain confidentiality levels beforehand, "Obtain the relevant consents before releasing results to others", and "Establish clear guidelines as to how long test data are to be kept on file."
- GDPR Art. 8: 16 (Member States may go down to 13), with reasonable verification of parental consent.
- Iran, Civil Code Art. 1210 note 1: «سن بلوغ در پسر پانزده سال تمام قمری و در دختر نه سال تمام قمری است» ("age of puberty is fifteen full lunar years for boys and nine for girls"); note 2: a matured minor's property is handed over only once «رشد او ثابت شده باشد» (his/her maturity is proven). Art. 1212: a minor's acts concerning property are void.
- Iran, Child and Adolescent Protection Law (approved 1399/02/23 = 12 May 2020) Art. 1: «نوجوان: هر فرد زیر هجده سال کامل شمسی که به سن بلوغ شرعی رسیده است» ("adolescent: any person under eighteen full solar years who has reached religious puberty").
- PCO ethics 2-9: guardian's or parent's consent where the client is a minor.

**Nuance:** Iranian law gives no single statutory "age of digital consent". The defensible platform rule is: under 18 → guardian (father/paternal grandfather or court-appointed guardian) consent plus the minor's own assent, documented. The practice of treating 18 as the age of financial maturity rests on case law that was not fetched (NOT VERIFIED here).

---

### C10 — Persian technical conventions
**Verdict: CONFIRMED.**

**Sources fetched:** https://support.microsoft.com/en-us/office/opening-csv-utf-8-files-correctly-in-excel-8a935af5-3416-4edd-ba7e-3dfd2bc4a032 · https://www.unicode.org/Public/18.0.0/charts/PDF/U0600.pdf · https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/supportedValuesOf

- Excel: "You can open a CSV file encoded with UTF-8 normally if it was saved with BOM (Byte Order Mark)." Without a BOM Microsoft tells users to import through Get Data/Power Query. → write `EF BB BF` at the start of exported CSVs (or offer .xlsx).
- Digits: U+0660–0669 ARABIC-INDIC DIGITS are "used with Arabic proper; for languages of Iran, Afghanistan, Pakistan, and India, see … 06F0-06F9"; U+06F0–06F9 EXTENDED ARABIC-INDIC DIGITS are for "Persian, Sindhi, Urdu, etc." Glyphs for 4, 5, 6 differ between the two sets. ECMA-402 names them numbering system `arabext`.
- Letters: Persian uses U+06CC ARABIC LETTER FARSI YEH and U+06A9 ARABIC LETTER KEHEH; Arabic keyboards produce U+064A YEH and U+0643 KAF. Normalise ي→ی and ك→ک (and both digit sets → one) on input and in search indexes.
- Calendar: ECMA-402 calendar `persian` = "Persian (or Solar Hijri) calendar". Store timestamps in UTC/Gregorian; render Jalali for display.

**Nuance:** the Microsoft page does not describe Excel's detection on double-click, only that BOM files open "normally". Zero-width non-joiner (U+200C) handling in search was not sourced.

---

## Items that could NOT be verified, and why
1. Current stage of the APA draft Ethics Code after the March 2025 comment deadline — apa.org HTML unreadable (Incapsula) from both routes; only Council minutes (PDF) were readable.
2. Whether the SDC implementation guide requires a version-specific `questionnaire` canonical — profile page returned no content.
3. Whether the Supreme Council of Cyberspace has approved the data-governance document — absent from the official list today; no positive or negative statement found.
4. Real-world enforcement of the 1402 NCC privacy directive.
5. Exact licence titles on mojavez.ir for counselling/online counselling, and the text of PCO's by-law on psychologists' activity in cyberspace — sites are JS-only or challenge-protected.
6. Shaparak's primary rules for payment facilitators and supported merchants — shaparak.ir not machine-readable; evidence is from licensed payment companies.
7. Text of the 1405 Budget Law (VAT rate) and the number/date of the Sept 2026 tax circular — only consistent secondary reports.
8. VAT treatment of paid online psychometric reports (exempt vs taxable).
9. ISO 10667 clause-level content (agreement, participant information, feedback) — paywalled; only abstracts read.
10. ICO anonymisation guidance and US ED PTAC disclosure-avoidance FAQ — not fetched / landing page only.
