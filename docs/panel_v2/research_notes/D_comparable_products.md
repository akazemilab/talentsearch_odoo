# Research D: how established assessment platforms structure the business "panel" and the participant side

Fetched 2026-10-01 via WebSearch/WebFetch. Every fact below is tagged with the URL actually opened.
Method caveats (read first):
- WebFetch returns a small-model summary of each page, not raw HTML. I quote only wording the tool returned in quotation marks. curl was blocked by the proxy (HTTP 403 on CONNECT), so I could not cross-check raw HTML.
- Not readable: support.pearson.com/usclinical articles (Salesforce JS shell, "CSS Error") including "Usages, Subscriptions and Digital Assets Explained", "How to order usage", "Add new users", "Reprinting a report at no charge". I used Q-global's own WebHelp instead. Robots-blocked: MHS FAQ PDF, SHL user guide PDF, Psytech page. 404: parinc HIPAA page, Unifrog parent-help page.
- "Not documented publicly" = I opened the relevant page(s) and the fact was absent, or no public page was found. It does not prove the product lacks the feature.
- Products covered: NovoPsych, Pearson Q-global, PAR PARiConnect (thin public docs), MHS (MAC+ and TAP), Hogrefe HTS, TestGorilla, SHL TalentCentral, GL Assessment Testwise, Morrisby, Unifrog, Xello, Qualtrics (reminders only). Thomas Assess, Psytech GeneSys, Schuhfried VTS: partial only. Hogan: no public admin docs found.

---------------------------------------------------------------------------
## 1. NovoPsych (clinician platform)

Navigation / objects
- Tabs named in help: Home (with "Recent Activity" feed), Clients, Assessments; account area "Account > Data & Privacy"; User Management screen. https://novopsych.com/support/user-guide/how-to-email-an-assessment-from-the-assessments-tab/ ; https://novopsych.com/support/user-guide/how-to-export-assessment-data-in-csv/ ; https://novopsych.com/support/user-guide/managing-users-in-your-practice-plan/
- Objects: Client, Informant (parent/teacher/other rater), Group, Assessment, Schedule, User, Practice Plan.

Client record
- "First Name and Last Name are the only mandatory fields." Optional: email, gender, DOB, assigned-to user. Client needs no account. https://novopsych.com/support/user-guide/how-to-add-a-client/
- Unique identifier: not documented as an ID field. De facto matching is exact first name + last name + DOB: if a self-entered respondent matches exactly, "it will add the assessment to their existing file". https://novopsych.com/support/user-guide/qr-code-for-assessments/
- Informants: name and email mandatory; "each informant's results are kept seperate, while still being stored within the same client file". Informant results are not graphed against the client's own self-reports. https://novopsych.com/support/user-guide/parent-teacher-or-informant-rated-scales-sending-assessments-to-informants/ ; https://novopsych.com/support/user-guide/how-to-add-a-client/
- Bulk import: CSV template; required first name, last name, DOB (dd/mm/yy); optional email, gender, "Assigned to user email", informant names/emails; preview with per-row validation. Duplicate rule not documented. https://novopsych.com/support/user-guide/how-to-import-your-clients-on-novopsych/
- Multiple assessments per person: all under one client file with results graphed over time (https://novopsych.com/functionality/).
- Free plan has a client cap (up to 15 clients, 5 assessments/month) https://novopsych.com/pricing/

Assigning
- Email from Assessments/Clients/Home tabs; client completes on any device; "Generate Link" for an existing client or "Respondent to enter own details" (asks first name, last name, DOB); "This link can be used multiple times and will remain active indefinitely"; QR "will work in perpetuity". https://novopsych.com/support/user-guide/how-to-share-an-assessment-url/ ; https://novopsych.com/support/user-guide/qr-code-for-assessments/
- Scheduling: start date, frequency (weekly/monthly etc.), number of cycles; emails sent 7am AEST on schedule days; schedule statuses "In Progress" then "Expired"; client can unsubscribe via email link. https://novopsych.com/support/user-guide/schedule-psychometric-assessments-reoccurring-emails/
- Link expiry and automatic reminder cadence for one-off emails: not documented publicly (email page).
- Groups can be used for "Mass communication" (send to many) https://novopsych.com/support/user-guide/organising-clients-with-groups/

Roles
- Three roles: Account Manager, Supervisor, Practitioner. Account Manager and Supervisor "have access to all client files"; Practitioners "will only be able to see clients that are assigned to them". A client can be assigned to several practitioners. Clients created by Account Managers start unassigned and are visible to all users while active. https://novopsych.com/support/user-guide/how-to-share-client-access-with-another-practitioner/
- Groups = access-control unit: allocate a practitioner to a group and they see all its clients; only Account Managers/Supervisors create/edit groups. https://novopsych.com/support/user-guide/organising-clients-with-groups/
- Deleted users "lose access immediately. Their historical data remains securely stored." https://novopsych.com/support/user-guide/managing-users-in-your-practice-plan/

Charging
- Per-user subscription (Practice plan from $20/month per practitioner; minimum two users; all charged to Account Manager). Metric: "Pro Action" = completing a clinical assessment measure or generating an AI note; Free = 5 assessments/month. Account Managers can "Monitor assessment and AI Notes usage per user". https://novopsych.com/pricing/ ; https://novopsych.com/support/user-guide/setting-up-a-practice-plan-in-novopsych/
- Neither marking inactive nor deleting a client "reduce your overall client count for billing purposes". https://novopsych.com/support/user-guide/making-clients-active-or-inactive/
- Administering an assessment to an inactive client automatically reactivates them (same page).

Results / participant side
- Results hidden from the client by default; practitioner can tick "Make these results available to the client". https://novopsych.com/support/user-guide/how-to-email-an-assessment-from-the-assessments-tab/ ; schedule page above
- No dedicated client portal documented (client-management page).

Data lifecycle
- Patient data stored in Australia by default; "Clinicians may delete assessment data at any time", then removed from backups on normal lifecycle; system events (auth, admin access, config changes) "are logged and retained"; paid accounts: "By default, no user data is used for research" (opt-in under Account > Data & Privacy). https://novopsych.com/security/
- Export: CSV zip by date range, emailed link. https://novopsych.com/support/user-guide/how-to-export-assessment-data-in-csv/
- Training-clinic variant: supervisor oversight and aggregated de-identified "Insights". https://novopsych.com/university-training-clinics/
- Onboarding checklist / sample client data: not documented publicly.

---------------------------------------------------------------------------
## 2. Pearson Q-global

Navigation / objects
- Top tabs: Examinee, Group Administration, Reports. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Getting_Started_on_Q-global/General_Navigation.htm
- Manage Accounts tabs: Details, Portfolios and Assessments, Inventory, Users, Consent Builder. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Manage_Account/Account_Details_Overview.htm
- Terminology is configurable ("Respondent" instead of "Examinee"); up to 4 custom examinee fields per account (same page).

Examinee record
- Bulk CSV: First/Last name, DOB required (mm/dd/yyyy); ExamineeID (max 20) only required if names blank; Gender; Email; AccountSystemID; Comments; Custom 1-4. "Import files containing duplicate examinee records will be imported." https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Import/Importing_Examinee_records.htm
- A field may be optional to save but required to score/report. "If you delete an Examinee record all assessments associated with the Examinee will be deleted as well." Archive = Move To Inactive. Merge: choose the record to keep; the other is deleted and its assessments move to the kept one. "Move To" another account/sub-account. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Examinees/manage_examinee_record.htm
- Examinee Details page lists all assessments for the examinee. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Assessments/Manage_Assessments.htm

Assigning / ROSA
- Assign New Assessment; delivery = manual entry, on-screen, or Remote On-Screen Administration (ROSA) by invitation email with template tokens. Examinees have 30 days; reminder email 7 days after assignment (owner can toggle in Assessment Settings); completion email on finish. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Assessments/Remote_On_Screen_Administration.htm
- Eight assessment statuses: Needs Verification, Needs Editing, Ready for Reporting, Ready for Administration, Administration in Progress, Edit in Progress, Ready to Resume, Report Generated. Resume exists ("Ready to Resume" for paused on-screen assessments). https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Assessments/Manage_Assessments.htm
- Group Administration (proctored): create group, add examinees, assign assessments; new members inherit group assessments; removal keeps assigned assessments except those still "Ready for Administration". https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Groups/Managing_Groups.htm
- Consent Builder: consent form (up to six custom fields) for group proctored sessions; examinee enters full name and last four SSN digits; stored as PDF under Group Administration, "not stored with the examinee or the examinee's assessment data". https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Manage_Account/Consent_Builder.htm

Roles / hierarchy
- Account Owner and Account Administrator add users (activation email); custom roles possible, system roles locked; examiners can be non-users; user qualification level capped by account. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Manage_Account/Account_Users.htm
- Hierarchy example State > District > Schools; sub-accounts inherit address/settings/portfolios/qualification; moving a user "may impact the user's ability to see examinee records"; group reports at different levels. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Manage_Account/Account_Details.htm
- FAQ: "Create multiple sub-accounts to help manage sites, departments, and examiners". https://www.pearsonclinical.ca/en/digital-solutions/q-global/resources.html?tab=faqs

Inventory / charging
- Three inventory types: Digital Assets, Subscriptions (reports consumed on subscription), Usages (per use). When a report is generated for an examinee "the account inventory will decrement by one usage." Allocations transferable between sub-accounts/users; deallocated subscriptions return to account inventory; admins view sum totals of consumed reports. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Manage_Account/Inventory.htm
- "Report usage inventory is not required when assigning an assessment(s) to an examinee(s)." (Manage Assessments page above.)
- Report page shows "Inventory Needed" before generating. https://www.pearson.com/content/dam/one-dot-com/one-dot-com/apac/Industry/Q-Global%20Quick%20Start%20Guide.pdf
- Regenerate same report "at anytime at no additional cost"; first edit/save allows free regeneration, later edits create billable duplicates. Group/batch reports need 2+ examinees and DO consume inventory ("the same quantity"). Output = ZIP of PDFs or one PDF. https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Reports/Reports.htm ; https://qglobal.pearsonclinical.com/qg/static/Platform/Customer/en/WebHelp/Groups/Generate_Group_Reports.htm
- Low-balance behaviour, retention defaults, deletion policy: not documented publicly (FAQ says retention/deletion not addressed).
- Related Pearson page (pan Platform, pearsonassessmentsupport.com; not confirmed to be Q-global): "Assessments that were never started will automatically expire 30 days after the assignment date"; "An assessment that has been started will NEVER EXPIRE"; expired inventory can be reclaimed. https://pearsonassessmentsupport.com/support/index.php?View=entry&EntryID=4448
- Security: encryption in transit and at rest; Canada-hosted (CA FAQ).

---------------------------------------------------------------------------
## 3. PAR PARiConnect (public docs are thin)

- Objects: clients (add "individually, by group, or by clinician"), groups with custom labels, client home screen (demographics, completed assessments, notes, reports); sole practitioners can give limited access to admin assistants; supervisors allocate uses across clinicians; Enterprise Manager for linked multi-account organisations with batch imports and cross-account data movement. https://paa.com.au/help-and-support/pariconnect-online-account-features/
- Delivery: on-screen in office, email invitation to anyone with an email address, copy link and send by text/email, paper-entry. https://www.parinc.com/customer-support/pariconnect-digital-materials ; https://www.parinc.com/pariconnect
- Units: i-Admins (administrations) and reports bought separately, minimum 5 per type; score vs interpretive reports; "You can regenerate reports without depleting your report inventory" including with different norms; no setup fee; restocking alerts. https://www.parinc.com/customer-support/pariconnect-digital-materials ; https://www.parinc.com/pariconnect
- Paper-and-pencil: only pay for reports, no i-Admin needed (FAQ above).
- Supervisor controls which clinicians can export data; inventory usage reports side by side per clinician. https://www.parinc.com/learning-center/par-blog/detail/blog/2022/07/19/digital-solutions-in-PARiConnect-for-your-assessment-needs
- Terms: PAR "reserves the right to delete a PARiConnect Account, including all associated client records and data, after a period of 36 months of inactivity"; customer is "solely" responsible for backups; organisations must designate a Supervisor/Account Manager responsible for each additional user's test access; BAA when customer is a Covered Entity; PAR may de-identify/aggregate data for internal analytics. https://www.parinc.com/legal-privacy-policies/pariconnect-terms-and-conditions
- HIPAA design, TLS 1.2+, SOC 2 Type 2 (pariconnect and FAQ pages above).
- NOT documented publicly (pages opened): when an i-Admin is deducted (assign / start / finish), invitation expiry, reminders, client import columns, client unique ID, client self-service results.

---------------------------------------------------------------------------
## 4a. MHS: MAC+ (clinical) and Talent Assessment Portal (TAP)

MAC+ navigation: left menu Home, Manage Inventory (Account Balance), Account Settings, Manage Users (admin only); pages My Clients, My Assessments, Completed Assessments. https://help.mhs.com/mac-help/use-the-dashboard/ ; index https://help.mhs.com/macplus/
- Two user types: Administrator (creates sub-users, buys form uses, distributes uses, transfers clients) and Sub-user (enters clients, conducts assessments, generates reports; "no control over inventory or account permissions"). https://help.mhs.com/mac-help/understand-user-types/ ; https://help.mhs.com/macplus/create-a-sub-user/
- Distribute uses either manually per sub-user (+/-) or "Share my uses with Everyone" pool. https://help.mhs.com/macplus/distribute-form-uses-to-sub-users/
- Admin client transfer between sub-users carries assessments and reports; triggers receipt to old owner, new owner, admin; "useful when you or a sub-user is out sick". https://help.mhs.com/macplus/transfer-clients-between-sub-users/
- "A form use is only deducted from your inventory when a report is generated, not when you send an invitation or when a rater completes an assessment." https://help.mhs.com/mac-help/create-an-invitation/
- Automatic reminders: checkbox on Pending Invitations; only for overdue assessments; overdue threshold set in Account Settings. https://help.mhs.com/mac-help/automatically-send-reminders/
- Low-uses alert: red balance + email to account holder plus up to five more addresses. https://help.mhs.com/mac-help/set-a-low-uses-alert/
- Usage history: chart per sub-user/assessment, up to 12 months. https://help.mhs.com/mac-help/view-a-sub-users-usage-history/
- Client record: add on My Clients page; tags (school, grade); field list/ID not documented. https://help.mhs.com/mac-help/add-clients/
- Delete client removes "all of the assessments, pending invites, active links, and reports"; listing stays in Deleted Items 7 days, recoverable, or permanently delete early. https://help.mhs.com/mac-help/delete-a-client/

TAP (talent):
- Home shows product icons, Manage Tokens, Account Settings, Report Calculator, Deleted Items (7 days). https://help.mhs.com/tap/use-the-home-page/
- Help IA mirrors the workflow: Personal Invitations, Open Invitations, Manage Assessments, Generate Reports, Group Reports, Multi-rater. https://help.mhs.com/tap/
- Four account types: Single-user, Multi-user (admin; shares tokens, cannot test unless they create a personal sub-user), Distributor, Sub-user. Multi-user can "transfer tokens to specific sub-users or enable a token pool". https://help.mhs.com/tap/understand-user-types/
- Participant entry: "Only an email address is required. If privacy is an issue, you do not have to enter a first or last name"; optional ID, and if ID plus names are entered "only the text entered in the ID text box will appear on the report"; Excel "Invitation Import Template". https://help.mhs.com/tap/enter-participants/
- Open invitation: single link for many people, not emailed automatically; cannot be reactivated, personal links can. https://help.mhs.com/tap/create-an-open-invitation/ ; https://help.mhs.com/tap/set-the-invitation-to-expire-2/
- Expiry date set manually (no default documented); status becomes Expired and link dead; reactivate with new date. (same expiry page)
- Statuses: Pending, Completed (no report yet), Scored (report generated), Expired. https://help.mhs.com/tap/manage-participants/
- Reminders manual only: "Send Reminders to All Pending" / "to Selected"; "Last Reminder" date recorded. https://help.mhs.com/tap/send-reminders/
- Deleting a participant "removes their assessment and all personal data from the portal." (manage-participants page)
- Tokens: "You will be charged the full price the first time you generate a report"; regenerate free unless norm region/type changes; price shown on Review page; "When you run out of tokens, you can still administer an assessment; however, you cannot generate any new reports". https://help.mhs.com/tap/generate-a-report/ ; https://help.mhs.com/tap/regenerate-reports/ ; https://help.mhs.com/tap/purchase-tokens/
- Reports archive five days after generation; regenerate from My Reports (regenerate page).
- Token expiry: tokens/uses "expire and revert to MHS if there has been no account activity for one (1) year"; account credit valid 1 year. https://mhs.com/account-expiration/
- Group min size / anonymity thresholds: not documented publicly (manage-groups and view-a-group-report pages).

---------------------------------------------------------------------------
## 4b. Hogrefe Testsystem (HTS 5)

- Two logins: Nutzer (user) and Supervisor ("übergeordnete Accounteinstellungen"); more users need more serial numbers. https://www.hogrefe.com/at/etesting/hogrefe-testsystem/support-faq ; https://www.testzentrale.de/etesting/hogrefe-testsystem/faqs
- Credits: "Eine Testnutzung wird dann reserviert, wenn Sie einen Link generieren, dieser jedoch noch nicht verwendet wurde" (reserved at link creation); unused invitations can be deactivated to free reserved credits; "Erst wenn der Test oder Fragebogen bis zum Ende durchgeführt wurde und Sie eine Auswertung inkl. Report ... erhalten entstehen Ihnen Kosten" (cost only on completion plus report); re-reporting with other norms is free; usage view shows Durchführung / Report / Export balances. (FAQ pages above)
- Help topics include "Gérer les passations abandonnées et les crédits réservés" and a "journal" in which "all account procedures are logged and searchable"; anonymous evaluations supported. https://www.hogrefe.com/fr/aide/test-en-ligne-hts
- Anonymous group testing: shared link (same login for all) or individual logins; Personen tab; results export PDF/XML/CSV/Excel; "Data stored in the test system are regularly deleted" so export then delete. https://www.bib.uni-mannheim.de/media/Einrichtungen/Universitaetsbibliothek/Dokumente/Standorte/BB_A3_Testverfahren_Psychologie/Anleitung-Nutzung-Testsystem-24-02.pdf
- Group analysis (mean, SD, min/max), profile comparison, ranking against target profile, follow-up analysis; ISO 27001 (Nov 2025). https://www.hogrefe.com/uk/key-features-of-the-hts-5-online-portal
- Schuhfried VTS: link testing "proctored or in unsupervised mode" https://www.schuhfried.com/en/faq/ ; Persons page create/import/delete https://help.schuhfried.com/__attachments/a_e411cfd2d0e46776e3b8acd9460cb5d61ab70749e69489b7020257989513a9c8/Technical%20Documentation%20and%20Help%208.29.02.pdf ; credit rules not documented publicly.

---------------------------------------------------------------------------
## 5. TestGorilla (hiring)

- Onboarding checklist: 1 Create team, 2 Create assessment, 3 Invite candidates, 4 Analyze results. https://support.testgorilla.com/hc/en-us/articles/8651682993563-Getting-started-with-TestGorilla
- Invite: email single or bulk CSV/XLSX (paid plans), "Every assessment includes one general public link" (Plus: multiple links), ATS integration (Plus). Candidate fields: name, email, status, progress, stage. https://support.testgorilla.com/hc/en-us/articles/9028116465563-Managing-candidates
- Statuses: Invited, Assessment started, Assessment completed, Disqualified; separate 13 internal hiring stages (no notifications). (same page)
- Reminders: automatic after 48h of no activity; plus one manual; max two. https://support.testgorilla.com/hc/en-us/articles/9027616233371-Candidate-communications-through-TestGorilla
- Deadline: candidate deadline min 3 days; plus assessment expiration date; up to 90% extra time; results shown to candidate via TestGorilla Profile by default (toggle on paid plans); snapshots can be disabled. https://support.testgorilla.com/hc/en-us/articles/9028441070619-Advanced-assessment-settings
- Roles: Account Owner (billing, admins, ownership), Admin, Recruiter, Hiring Manager (cannot create assessments or delete candidates; can comment/rate). https://support.testgorilla.com/hc/en-us/articles/9027695915547-Managing-your-team
- Credits: deducted "when candidates start the assessment, not when invited"; free tools cost 0; credits expire at contract end, no rollover; at 100 or fewer credits auto-upgrade or manual upgrade needed to keep inviting. https://support.testgorilla.com/hc/en-us/articles/42729664355739-Everything-you-need-to-know-about-credits ; per-candidate cost varies by tools (1 to 5) https://support.testgorilla.com/hc/en-us/articles/45120918896155-Recent-changes-to-credits-January-2026
- No reset: "It isn't possible to reset assessments"; delete candidate and re-invite; deletion permanent. https://support.testgorilla.com/hc/en-us/articles/30469857170331-FAQ-Candidate-related-questions ; managing-candidates page
- Retention: customer-visible data 2 years; webcam pictures/video answers 6 months; after expiry PII deleted but anonymised scores kept for benchmarking; TestGorilla and the customer are joint controllers; GDPR erasure via privacy@testgorilla.com (not self-serve in account settings). https://www.testgorilla.com/privacy-policy/ ; https://support.testgorilla.com/hc/en-us/articles/9028288183195-Account-settings
- Candidate privacy page: must accept privacy policy to take test; proctoring snapshots every 15 seconds; only hiring company sees them. https://candidates.testgorilla.com/hc/en-us/articles/30851874108315-Common-questions-about-data-and-privacy
- Company-level retention setting / auto-purge: not documented publicly.

---------------------------------------------------------------------------
## 6. SHL / Thomas / Psytech / Hogan

- SHL TalentCentral: Project = container "all your assessments, reports, dates, and candidates"; invite by individual entry, CSV bulk (First, Last, Email), single-use link, multi-use link (self-register); deadline as exact date or number of days; multiple reminders; user groups per project; bulk PDF reports. Credits not addressed. https://support.shl.com/documents/495/attachments/2409
- Thomas Assess Accredited: People tab; single, multiple, or bulk spreadsheet; required first name, surname, gender, country; optional "Unique identifier"; actions Email / Input scores / Complete now; dashboard to track, remind, cancel. Credit rules and expiry not documented in page opened. https://knowledge.thomas.co/assess-accredited/how-to-add-invite-candidates-in-assess-accredited ; terms define "Unit" only by reference, parties are each controllers https://www.thomas.co/sites/default/files/2019-08/Master%20Terms%20and%20Conditions_V1.pdf
- Psytech GeneSys: "full organisational level hierarchy"; "Master users can control data and credits for all other users within the account"; email invitations; 360 projects and sessions; tutorials cover Tags and Groups. https://www.psychometrix1.com/etesting ; https://eu.genesysonline.net/Tutorial . Credit consumption event not documented publicly.
- Hogan: no public admin help found.

---------------------------------------------------------------------------
## 7. School examples

GL Assessment Testwise (CAT4 etc.)
- Six areas: Students, Sittings, Insights and Reports, Subscriptions and Credits, Users, Manage School; Users/Manage School for School Administrators only; Users area shows users "at the same level or the level below yourself". https://support.gl-assessment.co.uk/knowledge-base/platforms/testwise/getting-started/main-functional-areas
- Student import xlsx/csv; required Forename, Surname, DOB, Unique Identifier, Gender; warning "If a unique identifier has been used across multiple students their results cannot be separated later"; validation tab flags ID clashes and duplicates; class via "Group" field. https://support.gl-assessment.co.uk/knowledge-base/platforms/testwise/students/import-students ; https://support.gl-education.com/media/2368/testwise_0218_digi-file.pdf
- Delete student "completely erases all data"; changing DOB after tests deletes responses. https://support.gl-assessment.co.uk/knowledge-base/platforms/gl-ready/managing-student-records/managing-student-records
- Sitting = which students, which tests, when; start period max 30 days; unique 8-digit access code per student per sitting, not auto-delivered (print, email, or staff enters it). https://support.gl-assessment.co.uk/knowledge-base/platforms/testwise/sittings/create-sittings ; https://support.gl-assessment.co.uk/knowledge-base/platforms/testwise/sittings/download-student-login-details
- Sitting statuses Draft/Pending/Live/Started/Completed/Expired/Closed; student statuses Not Started, In Progress, Marking, Complete, Failed to Finish. https://support.gl-assessment.co.uk/knowledge-base/platforms/testwise/sittings/understand-sitting-details
- Credits: "One credit is required for each student completing one test"; deducted when student is added to a sitting (draft = not deducted) and "used as soon as a student starts"; sitting cannot be created if insufficient balance; subscription expiry loses credits; unstarted tests on expired sitting: "you will be reallocated that credit"; partial completions get 30 extra days on same code. https://support.gl-assessment.co.uk/knowledge-base/platforms/testwise/subscriptions-and-credits ; create-sittings page ; https://support.gl-assessment.co.uk/knowledge-base/platforms/testwise/troubleshooting/troubleshooting-faqs
- Interruption: improper logout means no results saved, retake whole section (FAQ above).
- Reports: individual reports for students, teachers, and parents separately; group reports for teachers/other professionals; no minimum cohort size stated; digital reports on demand. https://support.gl-assessment.co.uk/knowledge-base/assessments/cat4-support/after-the-test/scoring-and-reporting

Morrisby (careers profile)
- Three ways to create student accounts: self-registration with a unique code (name, DOB, email), CSV upload then invite emails, MIS sync; "Morrisby Manager" role sets up, anyone can run the session; send invites close to session to prevent early login; students see results immediately by default or staff unlock later; PDF individual and cohort/year-group reports. https://support.morrisby.com/support/solutions/articles/44002054625-administration-guide-morrisby-profile
- Student-controlled parent sharing: student invites parent by name/email; link "expires after 7 days"; read-only; student can add several and remove at any point; school visibility not documented. https://support.morrisby.com/support/solutions/articles/44002130236-how-can-students-share-their-results-with-a-parent-
- "Login for life" accounts; GDPR statement. https://support.morrisby.com/support/solutions/articles/44002058084-morrisby-profile-information-for-parents

Unifrog
- Student/teacher accounts via MIS sync, manual, or CSV; SSO needs matching email. https://www.unifrog.org/help/using-sso-to-sign-in-to-unifrog
- Parent account only after the school links the parent email ("You can only create a parent/guardian account if they've done this first"); parents see tasks, events, teacher-added interactions. https://www.unifrog.org/parent ; https://www.unifrog.org/know-how/what-is-unifrog-a-guide-for-parents-and-caregivers
- Post-school account ownership and deletion: not documented publicly in pages opened.

Xello
- Educators can view student results incl. past results after a reset; parents reach Xello through the school's Parent Portal; Course Planner approval "if required by the school". https://help.xello.world/en-us/Content/Knowledge-Base/Xello-6-12/Assessments/View-Student-Assessment-Results.htm ; https://www.philasd.org/blog/2025/12/02/xelloaccess/

---------------------------------------------------------------------------
## 8. Qualtrics (reminders)
- Reminders only to people who have not completed (not started or partial), only for individual-link distributions; scheduled as separate distributions; pausing collection cancels scheduled reminders; auto-blocked if more than 0.1% spam complaints or under 0.5% of emails lead to a started session; thank-you emails unsupported when anonymize responses is on. https://www.qualtrics.com/support/survey-platform/distributions-module/email-distribution/reminder-thank-emails/

---------------------------------------------------------------------------
# SYNTHESIS

## (a) Universal vs varying

| Pattern | Seen in | Status |
|---|---|---|
| Person record separate from assessment records (one person, many assessments) | NovoPsych, Q-global, MHS, GL, HTS | Near-universal |
| Minimal required identity (name, DOB or email; ID optional) | NovoPsych, Q-global, TAP, GL, TestGorilla | Near-universal |
| Test-taker needs no account; tokenised link or access code | NovoPsych, Q-global ROSA, TAP, GL, TestGorilla, SHL | Near-universal (Morrisby/Unifrog/Xello are the exception: they create student accounts) |
| Personal link plus open/multi-use link or QR | NovoPsych, TAP, SHL, TestGorilla | Common |
| Bulk upload via template (CSV/XLSX) | Q-global, NovoPsych, TAP, GL, SHL, Thomas, Morrisby, TestGorilla (paid) | Near-universal |
| Admin tier above ordinary user; admin manages users and inventory | Q-global, MAC+, TAP, HTS, NovoPsych, TestGorilla, Psytech | Near-universal |
| Ordinary user sees only own/assigned clients; supervisors see all | NovoPsych (explicit); Q-global, MAC+ (not stated) | Varies (explicit in 1 of the products opened) |
| Hierarchy of sub-accounts with inventory allocation | Q-global, MAC+/TAP, Psytech, PAR Enterprise | Common in B2B clinical; absent in TestGorilla/NovoPsych (seats instead) |
| Free re-generation of a report with same norms | Q-global, PAR, MHS, HTS | Near-universal among pay-per-report |
| Hard delete cascades to assessments | Q-global, MHS, GL, TestGorilla | Near-universal; recovery window only in MHS (7 days) |
| Archive/inactive distinct from delete | NovoPsych, Q-global | Common |
| Statuses: pending/started/completed/expired (+ scored) | TAP, TestGorilla, GL, Q-global | Near-universal vocabulary, different counts (4 to 8) |
| Expiry default | Q-global 30d; pan 30d; GL max 30d window; TAP none; TestGorilla min 3d; NovoPsych links never | Varies |
| Reminder cadence | Q-global 1 at 7d; TestGorilla 1 at 48h plus 1 manual; MAC+ overdue only; TAP manual; NovoPsych not documented | Varies |
| Charge event | see (c) | Varies |
| Results to test-taker | NovoPsych hidden by default; Morrisby shown by default; TestGorilla shared by default; Q-global not documented | Varies |
| Group/cohort reports with minimum size or anonymity threshold | Q-global needs 2+; others none documented | Not documented publicly (no k-anonymity threshold found anywhere) |
| Retention default | TestGorilla 2y; PAR deletes after 36m inactivity; MHS tokens revert after 1y inactivity; others not documented | Varies, mostly undocumented |

## (b) Ten most transferable design decisions

1. Two-layer model: Participant (minimal identity, no account) 1..n Assignment. Show the participant's whole history on one page. Allow an optional pseudonymous ID that replaces the name on reports. NovoPsych (client file, informants in same file), Q-global (examinee details table), TAP (ID-only reports).
2. Four delivery modes behind one "Send" action: personal emailed link, open link or QR with self-entry, in-room access code per participant per sitting, group sitting. TAP personal vs open invitations; NovoPsych QR; GL 8-digit code; SHL single vs multi-use link.
3. Group/cohort as a first-class object that drives access control, bulk send and group reports; newly added members inherit the group's assignments. NovoPsych groups, Q-global Group Administration, GL sitting, SHL project, TAP groups.
4. One canonical status set with timestamps: Pending, In progress, Completed, Expired, plus Report generated; keep internal pipeline stages (hired, referred) separate from delivery status and silent. TAP, GL, TestGorilla (13 stages vs 4 statuses), Q-global.
5. Expiry and reminder defaults set per assignment: default 30 days, one automatic reminder (7 days, or 48h after inactivity), manual reminders capped, "started never expires or gets a grace extension", and a "reactivate link" action. Q-global, pan, GL (30 extra days), TestGorilla, MHS reactivate.
6. Three-plus-one roles: Owner/Account manager (billing, users), Supervisor (sees all, creates groups), Practitioner (only assigned or group clients), plus a view-only/reviewer role. Admin transfers a person between practitioners with notification receipts. NovoPsych, TestGorilla, MAC+ transfer.
7. Org-level wallet with per-user allocation or shared pool, price shown before the action, low-balance alerts to several addresses, usage history per user for 12 months. MHS (allocation vs pool, alert to 5 extra addresses, calculator, usage chart), Q-global (allocation table), Psytech (master user).
8. Charge rule: reserve optionally at assignment, consume at the first delivery of value (report/results), release on expiry or deactivation, never block administering because credits ran out, free regeneration with same norms. MHS TAP, Hogrefe, GL, Q-global.
9. Participant side: results hidden by default for clinical/employer panels, with a per-assignment "share results" switch; for school panels a staff-controlled release time; any onward sharing (to a parent) is student-initiated, read-only, expiring and revocable. Autosave so interruption does not lose answers (GL loses data on improper logout; PAR/HTS store progress). NovoPsych, Morrisby, GL.
10. Lifecycle controls: separate Inactive/Archive from Delete; delete shows the cascade and offers export first; soft-delete window (7 days) then purge; per-org activity journal; panel-type terminology (Client/Student/Candidate) and a short onboarding checklist. MHS (Deleted Items), Q-global (Move To Inactive, configurable "Respondent" label), Hogrefe (journal, export then delete), NovoPsych (CSV export, system logs), TestGorilla (4-step checklist).

## (c) When is a credit consumed

| Product | Reserved/earmarked | Consumed | Returned |
|---|---|---|---|
| Q-global | no inventory needed to assign | report generation ("decrement by one usage"); group reports also consume | free regeneration of same report; subscriptions return on de-allocation |
| MHS MAC+ / TAP | none | first report generation (not at invite or completion) | regenerate free unless norm changes; tokens revert after 1y inactivity |
| PAR PARiConnect | not documented | i-Admin vs report separate; i-Admin trigger not documented | reports regenerate free |
| Hogrefe HTS | at link generation | at completion plus report | deactivate unused link frees reserved |
| TestGorilla | none | when candidate starts | none; credits expire at contract end |
| GL Testwise | when student added to sitting (not in draft) | when student starts | unstarted credit reallocated when sitting expires |
| NovoPsych | none | counted per completed measure within monthly plan allowance | monthly allowance, no per-credit return |
| Pearson pan page | at assignment | not stated | expired unstarted inventory can be reclaimed |

Most common rule in this sample: charge at the first moment value is delivered, i.e. report/results generation (Q-global, MHS x2, Hogrefe with completion, PAR reports), with start-of-test as the second most common (TestGorilla, GL). Nobody documented consuming at the moment an invitation is merely sent; where credits are earmarked at assignment (Hogrefe, GL) they come back when the invitation is deactivated or expires unstarted. Count is small (7 products), so treat "most common" as indicative.

## (d) What a privacy-first design should NOT copy

- Collecting last four digits of SSN for consent identity (Q-global Consent Builder), and storing consent separate from the examinee record, with the verification code being the proctor's username.
- Matching returning people by exact first name + last name + DOB, with links and QR codes that never expire (NovoPsych): identity collisions, wrong-file attachment, enumeration by anyone holding the link. Also "unassigned" clients visible to all users.
- Import that silently accepts duplicates (Q-global).
- Deleting or inactivating a person without reducing billed counts (NovoPsych): works against erasure.
- Inactivity-based deletion at vendor discretion with the customer solely responsible for backups (PAR 36 months), and credits reverting after inactivity (MHS 1 year): retention driven by commercial rules, not by purpose.
- Keeping "anonymised" scores for benchmarking after deletion, 2-year default retention, per-15-second webcam snapshots, results flowing to a persistent candidate profile by default, and erasure only via support email (TestGorilla).
- Joint-controller ambiguity (TestGorilla, Thomas "each a Controller"): define panel as controller and platform as processor.
- Destructive edits: changing DOB deletes a student's responses (GL); deleting a record cascades to all assessments with no recovery (Q-global, GL).
- School gatekeeping of parent links with no student control (Unifrog) when minors' data is involved; Morrisby's student-initiated, 7-day, revocable link is closer to privacy-first.
- Shared anonymous group login identical for all participants (HTS shared link) when results must be attributable or non-collidable.
- Group reports with no documented minimum cohort or small-cell suppression anywhere in the sample (Q-global minimum is 2): add your own threshold.
- Research/de-identified reuse (PAR terms, NovoPsych default off) should be opt-in per panel, as NovoPsych does.
- Qualtrics-style engagement thresholds that permanently block reminders: avoid opaque automated blocks.

## Not documented publicly (honest gaps)
PAR: i-Admin deduction event, invitation expiry, reminders, client ID, import columns. Q-global: retention, deletion policy, low-balance behaviour. Hogan, Thomas, Psytech, SHL, Schuhfried: credit consumption rules. All products: sample/demo client data; group-report anonymity thresholds; audit logs beyond NovoPsych system events and HTS journal.
