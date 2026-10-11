# UX audit 2026-10-11

Scope: all 90 page/role/state combinations of website 4's product pages (tools/vps/ts_ux_seed.py matrix), 375 px,
1280 px and dark at 375. Standards: ISO 9241-11/-110/-112/-125/-143/-171/-210, ISO/IEC 25010, WCAG 2.2 AA, Persian RTL.
Run: `ts shots DB ux` on a served clone (slot), then five `ts-ux-auditor` agents (G1 entry+player, G2 participant,
G3 panel daily work, G4 panel admin+account, G5 other roles). Findings: G*.json (302; sev4 27, sev3 65, sev2 141,
sev1 67; 32 owner decisions). report.html = the published Artifact.
Wave 0 fixed (commit d3d5d46): client page 500, dark surfaces, matrix review loop.
