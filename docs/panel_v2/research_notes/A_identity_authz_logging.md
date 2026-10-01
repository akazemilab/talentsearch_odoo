# Research baseline verification A (checked 2026-10-01)

METHOD CAVEATS (read first)
- curl to the primary sites was blocked by the egress proxy (policy 403), so I did NOT bypass it. All pages were read via WebFetch, which returns a model-summarised view of the page. Quotes below are as returned by WebFetch; they are short and consistent across repeated fetches unless flagged, but treat them as near-verbatim, not byte-exact.
- Where a fetch returned only a nav shell (Clerk API ref, Atlassian KB, Salesforce 000388857) that is marked NOT VERIFIABLE; no guessing.
- Two WebFetch results were wrong/contradictory and are flagged: ASVS GitHub releases page "May 30, 2026" (contradicted by 3 other sources saying May 2025) and a Cyber Chief blog chapter list for ASVS 5.0 (does not match the OWASP repo file names).

---
### A1
Verdict: PARTLY (all six concepts exist, but only 2 of 6 use the claimed wording; the lens lists 14 principles)
Source URL: https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/general-design-principles.html (dates from https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/document-revisions.html and .../saas-lens.html)
Short quote: "Isolate all tenant resources" ; "Bind user identity to tenant identity" ; "Create tenant-aware operational views"
Principles exactly as titled on the page (14):
1 There's no one-size-fits-all SaaS architecture
2 Decompose each service based on its multi-tenant load and isolation profile
3 Isolate all tenant resources
4 Design for growth
5 Instrument, capture, and analyze tenant metrics
6 Onboard tenants through a single, automated, repeatable process
7 Plan to support multiple tenant experiences
8 Support one-off requirements through global customization
9 Bind user identity to tenant identity
10 Align infrastructure consumption with tenant activity
11 Limit developer awareness of multi-tenant concepts
12 SaaS is a business strategy - not a technical implementation
13 Create tenant-aware operational views
14 Measure the cost impact of individual tenants
Mapping of the claimed principles:
- "bind user identity to tenant context, pass through every layer": PRESENT as #9 ("Bind user identity to tenant identity"); body says "Every layer of your architecture is likely to need some notion of tenant context". Wording differs: "tenant identity", not "tenant context" in the title.
- "isolate all tenant resources": PRESENT, exact (#3).
- "automate tenant onboarding": PRESENT as #6 ("Onboard tenants through a single, automated, repeatable process").
- "tiered tenant experiences": PRESENT as #7 "Plan to support multiple tenant experiences"; "tiers" appear only in #2's body ("tenant tiers"). Title does not say "tiered".
- "tenant-aware operational views": PRESENT, exact (#13).
- "one-off customer requests -> configurable features for all tenants": PRESENT as #8 "Support one-off requirements through global customization" (body: single environment run by all customers). "Configurable features" is a paraphrase.
Correction or nuance: Do not present the six as "the" principles; they are 6 of 14. Unclaimed but design-relevant: #2 (isolation profile per service), #5 (tenant metrics), #11 (limit developer exposure to tenancy - i.e. centralise tenant context in middleware), #14 (cost per tenant).
Lens dates: No date on the principles page itself. Revisions page: initial publication December 3, 2020; latest entry April 4, 2023 ("Major update - Guidance for sustainability was added"); earlier minor updates Sep 23 2022, Aug 1 2022, Dec 11 2020. saas-lens.html shows "Publication Date: April 4, 2023".
Anything newer: Nothing newer than April 2023 found in the revision history, i.e. the lens is ~3.5 years old at Oct 2026. It predates ASVS 5.0 and NIST 800-63-4.

---
### A2
Verdict: CONFIRMED for the model (one user, many memberships, org switching); PARTLY for invitation details (sources differ on what they document)
Source URLs fetched: https://workos.com/blog/user-management-for-b2b-saas ; https://clerk.com/multi-tenancy ; https://clerk.com/docs/guides/organizations/overview ; https://clerk.com/docs/guides/organizations/invitations ; https://clerk.com/docs/reference/backend/organization/create-organization-invitation ; https://workos.com/docs/reference/user-management/invitation ; https://auth0.com/docs/manage-users/organizations/configure-organizations/send-membership-invitations
Short quotes:
- WorkOS blog: "Users are globally unique individuals (e.g., identified by email or UUID) who may belong to one or more orgs."
- WorkOS blog: "This gives you full flexibility to support: Multi-org users [and] Org switching"
- Clerk docs overview: "Users can belong to multiple Organizations, and Clerk provides the Organization context (memberships, Roles, and the Active Organization) in each session."
- Clerk docs: "switch between them with the <OrganizationSwitcher/> component" (the clerk.com/multi-tenancy marketing page only says "One user. Multiple teams" and does not mention the switcher).
Invitation facts and default expiry values:
- WorkOS blog: "Expire invites after a set time (e.g., 7 days)"; "Auto-associate invite on sign-up (using email matching)"; "Allow re-inviting or canceling old invites"; invite = "pending membership record with a token". This blog gives an example (7 days), not a platform default.
- WorkOS API docs (the actual default): default expiry 7 days, range 1-30 days via expires_in_days; states pending/accepted/expired/revoked; resend and revoke exist; list invitations filterable by org or email; token usable as single-use credential; docs say app "should verify that the invitation is intended for the user accepting it... email matches the email address of the accepting user".
- Clerk (createOrganizationInvitation docs): expiresInDays "Defaults to 30"; no maximum stated. Clerk docs: invitation email carries "a unique invitation link"; revoking "prevents the user from using the invitation link"; "By default, only admins can invite users". emailAddress is a required param (email-bound at creation). Clerk docs fetched did not state single-use, resend, or a pending-list in the pages I could read (status values page was a nav shell -> NOT VERIFIABLE).
- Auth0 Organizations: "If unspecified or set to 0, defaults to 604800 seconds (7 days). Maximum of 2592000 seconds (30 days)." Invitee email required; option to generate invitation URL and send it yourself. Single-use, resend, revoke not stated on the page fetched.
Correction or nuance: defaults differ by vendor (WorkOS 7d, Auth0 7d, Clerk 30d); design should make expiry a configurable per-panel setting, store invitations as a pending record bound to the invitee identifier (for this platform: mobile number or email), and verify the accepting identity matches the invited one (WorkOS explicitly warns about this).
Anything newer: none identified beyond what is above.

---
### A3
Verdict: CORRECTED (date) / CONFIRMED (technical points, with number corrections noted below)
Source URLs fetched: https://pages.nist.gov/800-63-4/ ; https://pages.nist.gov/800-63-4/sp800-63b.html ; .../sp800-63b/authenticators/ ; .../sp800-63b/aal/ ; .../sp800-63b/syncable/ ; https://csrc.nist.gov/pubs/sp/800/63/b/4/final
Date: NOT end of 2024. Landing page: "In July 2025, NIST released the final version of SP 800-63, Revision 4." CSRC page for 63B-4: Publication Date July 31, 2025, Status Final, supersedes SP 800-63B dated March 2, 2020. (Drafts: initial public draft Dec 16, 2022; second public draft Aug 21, 2024 - so "2024" was the 2PD, not final.) Final-version volumes: SP 800-63-4, 63A-4, 63B-4, 63C-4.
Final text, SP 800-63B-4:
a. SMS/PSTN OOB = "restricted".
 - Sec 3.1.3.3: PSTN OOB "is restricted ... and SHALL satisfy the requirements of [Sec. 3.2.9]"; "verifiers SHALL ensure that alternative authenticator types are available to all subscribers and SHOULD remind subscribers of this limitation"; "Verifiers SHOULD consider risk indicators (e.g., device swap, SIM change, number porting, other abnormal behavior)". Changing the pre-registered phone number = binding a new authenticator (SHALL follow Sec 4.1.2).
 - Sec 3.2.9 (Restricted Authenticators), CSP obligations (SHALL): "Offer subscribers at least one alternative authenticator that is not restricted and can be used to authenticate at the required AAL"; "Provide subscribers with meaningful notice regarding the restricted authenticator's security risks and the availability of unrestricted alternatives"; "Address any additional risks to subscribers and RPs in its risk assessment"; "Develop a migration plan for the possibility that the restricted authenticator will not be acceptable in the future and include this migration plan in its Digital Identity Acceptance Statement". All four items the prompt listed are confirmed. Note the risk-indicator check at 3.1.3.3 is SHOULD, the rest SHALL. PSTN is the only restricted category named in the final.
 - Caveat: the 3.2.9 text came from two WebFetch passes that agreed on substance but split the bullets slightly differently; one pass attributed the risk-assessment bullet to an RP-responsibility sentence. Substance (4 obligations) stable.
b. Passwords, Sec 3.1.1.2: "SHALL require passwords that are used as a single-factor authentication mechanism to be a minimum of 15 characters" ; MFA-only passwords "MAY ... be shorter but SHALL ... a minimum of eight characters". Max: "SHOULD permit a maximum password length of at least 64 characters" (it is SHOULD, not SHALL). Blocklist: "SHALL compare the prospective secret against a blocklist". "SHALL NOT impose other composition rules". "SHALL NOT require subscribers to change passwords periodically" (but SHALL force change on evidence of compromise). Paste: "SHOULD permit claimants to use the 'paste' function ... password manager use".
c. Syncable authenticators / passkeys: Appendix B (syncable page): they can support AAL2; "Syncing violates the non-exportability requirements of AAL3" (so not AAL3). Conditions (SHALL): keys in the sync fabric stored encrypted with strength per SP 800-131A; "All authentication transactions SHALL perform private-key operations on the local device"; sync-fabric access control so only the authenticated user can reach keys; access to the fabric protected by AAL2-equivalent MFA. Federal-enterprise extras: FISMA-moderate fabric and agency-managed accounts. Sec 2.2: "Verifiers SHALL offer at least one phishing-resistant authentication option at AAL2".
d. Throttling Sec 3.2.2: "limit consecutive failed authentication attempts using a specific authenticator on a single subscriber account to no more than 100 by disabling that authenticator." Biometrics Sec 3.2.3: no more than 5 consecutive failures (10 with PAD) then disable biometric. Note the 100 is a ceiling, per authenticator, not a recommended lockout number.
e. Reauth/session timeouts (Sec 2.1.3 / 2.2.3 / 2.3.3): AAL1 overall timeout SHALL be established, SHOULD be no more than 30 days; inactivity timeout MAY be applied, not required. AAL2: overall SHALL be established, SHOULD be <= 24 hours; inactivity SHOULD be <= 1 hour. AAL3: overall SHALL be <= 12 hours; inactivity SHOULD be <= 15 minutes. So only the existence of an overall timeout is SHALL at AAL1/AAL2; the numbers are SHOULD.
f. OOB code lifetime Sec 3.1.3.2: "the authentication SHALL be considered invalid unless completed within 10 minutes"; and "SHALL accept a given authentication secret as valid only once during the validity period" (single use).
Anything newer: The final (July 2025) is the current revision; the 2020 63B is superseded. Key shifts to design for: 15-char single-factor password minimum, 100-failure ceiling per authenticator, PSTN formally "restricted" with CSP notice/alternative/migration-plan duties, syncable passkeys defined (AAL2 only), phishing-resistant option required at AAL2.

---
### A4
Verdict: CONFIRMED (all eight bullets); the "pure RBAC poorly suited to multi-tenant" claim is PARTLY correct - narrower than stated
Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
Short quotes:
- Least privilege: "the principle of assigning users only the minimum privileges necessary to complete their job"
- Deny by default: "an application should be configured to deny access by default"
- Every request: "Permission should be validated correctly on every request, regardless of whether the request was initiated by an AJAX script, server-side, or any other source"
- IDOR/object: "Perform access control checks on every request for the specific object or functionality being accessed"
- Static: "Ensure that static resources are incorporated into access control policies"
- Fail safely: "Ensure all exception and failed access control checks are handled no matter how unlikely they seem"
- Logging: "Logging is one of the most important detective controls in application security"
- Tests: "automated unit and integration testing of access control logic can help reduce the number of security flaws that make it into production"
(Server-side enforcement wording not separately quoted by the fetch; "every request ... server-side" covers the gist - not independently confirmed as its own bullet.)
RBAC/ABAC/ReBAC wording: "Although RBAC has a long history and remains popular among software developers today, ABAC and ReBAC should typically be preferred for application development." And under the heading "Supports Multi-Tenancy and Cross-Organizational Requests": "RBAC is poorly suited for use cases where distinct organizations or customers will need access to the same set of protected resources." Follow-on: RBAC would need "configuring rule sets for each customer in a multi-tenant environment or requiring pre-provisioning of identities for cross-organizational requests."
Correction or nuance: "multi-tenant"/"Multi-Tenancy" IS literally used. But the statement is scoped to cross-organization access to shared resources (the case where customers share the same protected resources), listed as one ABAC advantage - it is NOT a blanket statement that RBAC is unsuitable for all multi-tenant SaaS. The "ABAC and ReBAC should typically be preferred" sentence is general (application development), not tenancy-specific. Pure RBAC within a tenant-isolated data model is not condemned.
Anything newer: ASVS 5.0 V8.4.1 (A7) adds an explicit multi-tenant requirement.

---
### A5
Verdict: CONFIRMED (including "2-4 levels")
Source URL: https://workos.com/blog/rbac-fga-multi-tenant-b2b
Short quote: "Keep hierarchies shallow (2-4 levels). Deep hierarchies are harder to reason about and harder to explain to customers"
Details: two layers = org-level permissions "embedded in the session JWT and can be checked without any network call. Use this for coarse-grained feature access" + resource-level permissions "checked via the FGA API when you need to know whether a specific user can act on a specific resource". Naming: recommends "resource:action" (delimiters ":", "." or "_"); "Keep them concise because permission slugs end up in session JWTs, which have a size limit of around 4 KB in most browsers." Advice: start with RBAC in the dashboard, then "identify where RBAC breaks down" before adding resource-scoped features.
Correction or nuance: the two layers are described as JWT-embedded org permissions vs FGA API checks (an enforcement split), not strictly "roles vs relationship rules" - close enough, but the vendor-neutral lesson is: coarse role->permission strings in the token, object-level checks server-side. This is a vendor blog (WorkOS sells FGA), so treat as design advice, not a standard.
Anything newer: none found.

---
### A6
Verdict: PARTLY (events list: most confirmed, but "config changes" and "suspicious use" are listed as OPTIONAL; exclusion list confirmed)
Source URL: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html (fetched twice; the second fetch gave the fuller list)
Short quotes (events): "Authentication successes and failures"; "Authorization (access control) failures"; "Session management failures"; higher-risk functionality listed as user administration, privileged access, sensitive data access, data import/export, file uploads, cryptographic key usage; "Legal and other opt-ins e.g. permissions for mobile phone capabilities, terms of use".
Optional (not "always"): sequencing failure, excessive use, data changes, fraud, "Suspicious, unacceptable, or unexpected behavior", "Modifications to configuration".
Attributes: When = log date/time (international format) + event date/time; Where = application identifier, application address (cluster/hostname), service, code location; Who = source address (user's device/IP) and "User identity (if authenticated)"; What = type of event, severity, description.
Exclusion list ("Never log directly"): application source code; "Session identification values" (consider hashing if tracking needed); "Access tokens"; "Sensitive personal data and some forms of personally identifiable information (PII)" - the first fetch returned the examples as "e.g. health, government identifiers" but the second fetch dropped the examples, so the "health" example is supported by one of two reads; authentication passwords; database connection strings; encryption keys/primary secrets; bank account/card data; "Data of a higher security classification than the logging system"; commercially-sensitive information; "Information it is illegal to collect in the relevant jurisdictions"; "Information a user has opted out of collection, or not consented to".
Hashing/masking: "Consider using personal data de-identification techniques such as deletion, scrambling or pseudonymization of direct and indirect identifiers where the individual's identity is not required." Hashing is suggested for session IDs. Also "sanitization on all event data to prevent log injection".
Correction or nuance: "opt-ins/consents" is covered as "Legal and other opt-ins" (always-log). "Config changes" and "suspicious/excessive use" are optional items. For a psychological-assessment platform, test answers/scores are health-adjacent: log participant/assessment IDs, never answer content or scores.
Anything newer: ASVS 5.0 V16.2.5 (A7) says sensitive data "may only be logged by being hashed or masked".

---
### A7
Verdict: CONFIRMED with corrections (ASVS release date; chapter numbering differs from ASVS 4)
Source URLs: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html ; .../Forgot_Password_Cheat_Sheet.html ; .../Multifactor_Authentication_Cheat_Sheet.html ; https://github.com/OWASP/ASVS ; ASVS 5.0.0 files at https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/ (0x15-V6-Authentication.md, 0x16-V7-Session-Management.md, 0x17-V8-Authorization.md, 0x25-V16-Security-Logging-and-Error-Handling.md)
ASVS release date: May 2025 (repo README: "Released LIVE on stage at Global AppSec EU Barcelona 2025!"; PDF titled "Version 5.0.0 May 2025"). WARNING: one WebFetch of the GitHub releases page returned "May 30, 2026" - contradicted by the README and the PDF title, so I treat 2026 as a fetch error; the exact day (30 May 2025) is unconfirmed.
Relevant chapters (verified from file names/titles in the 5.0.0 repo): V6 Authentication, V7 Session Management, V8 Authorization, V16 Security Logging and Error Handling. A Cyber Chief blog chapter list (Access Control as V4 etc.) conflicts with the repo - NOT TRUSTED. Other chapter names (V9 Self-contained Tokens, V10 OAuth and OIDC) I could not open to verify.
Design-changing requirements:
- V6.5.5 (L2): "Out of band requests must have a maximum lifetime of 10 minutes and for TOTP a maximum lifetime of 30 seconds."
- V6.5.1 (L2): OOB codes/TOTP "are only successfully usable once." V6.5.4: min 20 bits entropy (e.g. 6 random digits). V6.6.2: OOB token bound to the original authentication request. V6.6.3 (L2): code-based OOB "protected against brute force attacks by using rate limiting". V6.6.1: SMS/phone OTP only with validated numbers, stronger alternatives available and risk disclosure; L3 apps must not offer them.
- V7.3.1/7.3.2 (L2): inactivity timeout and absolute max session lifetime per documented risk analysis; V7.5.1 (L2): full re-authentication before changing sensitive account attributes; V7.4.5 (L2): admins can terminate a user's sessions.
- V8.1.1 (L1) documented authorization rules; V8.2.1/8.2.2 (L1) function-level and data-item-level permissions "to mitigate IDOR and BOLA"; V8.3.1 (L1) enforce at a trusted service layer; V8.4.1 (L2): "multi-tenant applications use cross-tenant controls to ensure consumer operations will never affect tenants with which they lack permissions"; V8.4.2 (L3) admin interfaces with extra layers.
- V16.3.1 (L2) log all authentication operations incl. failures; failed authorization logged; V16.2.5: sensitive data "may only be logged by being hashed or masked"; V16.4.1 log-injection encoding; V16.4.2/16.4.3 logs protected and sent to a separate system.
OWASP cheat sheets: Authentication CS: "An application must respond (both HTTP and HTML) in a generic manner" (enumeration); "The counter of failed logins should be associated with the account itself, rather than the source IP address"; passwords <8 weak with MFA, <15 without, max "at least 64". Forgot Password CS: tokens "Invalidated after they have been used", "expire after an appropriate period", per-account rate limiting, "Return a consistent message for both existent and non-existent accounts", consistent response time, do not auto-login after reset. MFA CS: SMS/voice OTP exposed to SIM swap/number takeover; "Enforce a short time-to-live (TTL)", "Ensure OTPs are single use", invalidate on success; MFA reset/recovery flows are an attack path.
Anything newer: ASVS 5.0 supersedes 4.0.3 (renumbered; mapping to 4.0.3 provided by OWASP). Any design doc citing "ASVS V4 Access Control" is using the old numbering.

---
### A8
Verdict: CONFIRMED (two credible vendor sources; Atlassian source NOT VERIFIABLE)
Source URLs fetched: https://help.salesforce.com/s/articleView?language=en_US&id=xcloud.granting_login_access.htm&type=5 ; https://learn.microsoft.com/en-us/azure/security/fundamentals/customer-lockbox-overview
Short quotes:
- Salesforce: users grant login access to admins/support from their own settings, choosing an expiry; "the maximum period for granting access is 1 year" (as returned by WebFetch); audit: "the setup audit trail lists the changes and the username"; only admins and Salesforce support can be granted. Nuance: "By default, your company's administrators can access your account without any action from you" (admins have default access; the grant is required for support/other cases).
- Microsoft Customer Lockbox: access requires explicit customer approval; request stays queued 4 days then auto-expires ("Lockbox Request Expiry"); access is granted for the duration stated in the request; approvals/denials logged (Create/Approve/Deny Lockbox Request).
Model for design: customer-granted, scoped, time-boxed grant with automatic expiry, named approver role, every use audit-logged with the real operator's identity (not the impersonated user).
Not verifiable: Atlassian support-access FAQ (nav shell only); Salesforce article 000388857 (nav shell only). Atlassian was not confirmed.
Anything newer: none found.

---
SUMMARY OF OPEN ITEMS (could not open / not confirmed)
- All primary sites unreachable via curl (proxy policy); WebFetch used instead.
- Clerk: invitation status values, resend, pending-list, single-use; clerk.com/multi-tenancy does not show an org switcher (docs do).
- Auth0: single-use, resend, revoke not on the page fetched.
- Atlassian and Salesforce 000388857: nav shell only.
- ASVS: exact release day; names of chapters other than V6/V7/V8/V16.
- OWASP Authorization CS: "server-side enforcement" as its own bullet not separately quoted.
- OWASP Logging CS: "health" example in sensitive-data exclusion seen in 1 of 2 fetches.
