# Panel v2 — 08 Design system

The existing Talent Search look (EOT portfolio design system v1, brand "search") written down,
plus the components the panel needs. Every new page uses these and nothing else; a page that
needs something new adds it here first.

Files
- Tokens and site components: `ts_website/static/src/scss/ts.scss` (exists).
- Shared report/table pieces: `ts_assessment/static/src/scss/assessment.scss` (exists).
- Old one-page panel: `ts_org/static/src/scss/org.scss` (retired in S20).
- **New**: `ts_panel/static/src/scss/panel.scss`, loaded through `ts_website.assets_ts` only
  (never `web.assets_frontend`, which eot.ir shares).

Rules that come from the code base and must be kept
- Everything is scoped under `#wrapwrap` so it beats Odoo's own rules.
- Logical properties only (`margin-inline-start`, `inset-inline-end`, `text-align: start`);
  no `left` / `right`.
- No `filter`, `backdrop-filter` or `transform` on the site header (`#top`): it breaks Odoo's
  mobile menu (lesson, milestone 8).
- No `<details>` for menus (Odoo's page script interferes); use a button with `aria-expanded`
  and a few lines of JavaScript in `ts_panel/static/src/js/panel.js`
  (`/** @odoo-module ignore **/`).
- Set `font-family` explicitly on headings, buttons and form controls.
- Check a new class name against the existing files before adding it.

## 1. Tokens

Existing (`:root` in `ts.scss`)

| Token | Value | Use |
|---|---|---|
| `--ink` | `#142932` | Text (14.0:1 on paper) |
| `--muted` | `#53666c` | Secondary text (6.0:1 on white, 5.6:1 on paper) |
| `--line` | `#dce5e3` | Decorative dividers and card borders only (1.3:1; **not** for input borders) |
| `--paper` | `#f7f7f2` | Page background |
| `--white` | `#fff` | Surfaces |
| `--brand-deep` | `#393e70` | Headings, links, primary button (10.0:1 on white) |
| `--brand-accent` | `#6774b7` | Decoration and active borders (4.4:1 on white: **not for text**) |
| `--brand-soft` | `#e9ebf8` | Soft surfaces, default pill background |
| `--brand-warm` | `#dbeee7` | Call-to-action band |
| `--success` | `#216b50` | Success text and icons |
| `--danger` | `#9b2c36` | Error text, destructive buttons (7.5:1 on white) |
| `--space-1 … --space-16` | 4, 8, 12, 16, 24, 32, 48, 64 px | Spacing scale |
| `--radius-sm / md / lg` | 8 / 12 / 16 px | |
| `--content-max` | 1200 px | |
| `--control-min` | 44 px | Minimum height of any control (above the 24 px of WCAG 2.5.8) |

New in S2 (added to the same `:root`)

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--warn` | `#6b4600` | Warning text | 7.6:1 on `--warn-soft` |
| `--warn-soft` | `#fbf3e2` | Warning background (already used literally by `.ts-notice--warn`, `.ts-tag`) | |
| `--info` | `#1f4e79` | Informational text | 7.4:1 on `--info-soft` |
| `--info-soft` | `#e4eef7` | Informational background | |
| `--success-soft` | `#dff0e8` | Success background (used literally by `.ts-pill--ok`) | 5.4:1 with `--success` |
| `--danger-soft` | `#f9e7e9` | Error background | 6.3:1 with `--danger` |
| `--neutral` / `--neutral-soft` | `#3d4a4f` / `#eceeea` | Ended states (expired, withdrawn, archived) | 7.9:1 |
| `--field-line` | `#7d86b3` | Borders of inputs, selects, checkboxes | 3.5:1 on white (WCAG 1.4.11) |
| `--focus` | `var(--brand-deep)` | Focus outline 3 px, offset 3 px (exists as a rule) | 9.3:1 on paper |
| `--shell-nav` | 264 px | Panel sidebar width | |

Known contrast defects to fix where the panel reuses the component (S2): input borders
`#9ea5c7` (2.4:1) in `.ts-form` and `var(--line)` (1.3:1) in `.ts-org-invite` and
`.ts-inline-form`. The panel's form component uses `--field-line`.

Typography: Vazirmatn variable (self-hosted), fallbacks Tahoma, Arial. Body 1rem / 1.75.
Headings weight 750, colour `--brand-deep`. Panel scale: `h1` 1.6rem, `h2` 1.25rem, `h3`
1.05rem, table and meta text 0.9rem, never below 0.82rem. Numbers in tables use
`font-variant-numeric: tabular-nums` (`.ts-num`).

Breakpoints: 576, 768, 992 px (existing usage). The panel's layout switch is at 992 px; tables
become cards below 768 px.

## 2. Components

Existing, reused unchanged

| Component | Classes | Notes |
|---|---|---|
| Button | `.ts-btn` + `--primary`, `--outline`, `--quiet`, `--light`, `--sm` | One primary button per view |
| Card | `.ts-card`, `--soft` | |
| Notice | `.ts-notice`, `--warn` | New modifiers `--ok`, `--danger`, `--info` in S2 |
| Pill | `.ts-pill`, `--ok`, `--warn` | New modifiers `--info`, `--danger`, `--neutral` in S2 |
| Tag | `.ts-tag` | Panel type, role |
| Form | `.ts-form`, `.ts-hint`, `.ts-check`, `.ts-form__error` | Border colour fixed as above |
| Table | `.ts-table-wrap`, `.ts-table` | Extended below |
| Meta list | `.ts-meta` (`dl`) | Key–value blocks |
| Progress | `.ts-progress`, `__bar`, `__text` | Fills from the inline start (right in RTL) |
| Copy field | `.ts-copy` | Read-only input + copy button |
| Back link | `.ts-back` | |
| Container | `.ts-container`, `.ts-narrow` | |
| Print helpers | `.ts-noprint`, `.ts-doc*` | |

New in `panel.scss` (prefix `tsp-` so nothing collides with the site's `ts-` or the talent
module's `tt-` classes)

| Component | Classes | Structure and behaviour |
|---|---|---|
| Shell | `.tsp-shell`, `.tsp-shell__nav`, `.tsp-shell__main` | Grid: nav `--shell-nav` + content; one column below 992 px |
| Panel switcher | `.tsp-switch` | Panel name, code in `<bdi dir="ltr">`, link «تغییر پنل» |
| Panel menu | `.tsp-nav`, `.tsp-nav__item`, `[aria-current="page"]` | `nav` with `aria-label="منوی پنل"`; on mobile a toggle button `.tsp-nav__toggle` with `aria-expanded`, `aria-controls` |
| Page header | `.tsp-head`, `.tsp-head__title`, `.tsp-head__help`, `.tsp-head__actions` | `h1`, one help line, actions wrap under the title on mobile |
| Toolbar | `.tsp-toolbar` | Search form, filter button, view selector |
| Filter chips | `.tsp-chips`, `.tsp-chip`, `.tsp-chip.is-on` | Links (GET) with counts; the active one has `aria-current="true"` |
| Data table | `.ts-table` + `.tsp-table`, `.tsp-th-sort`, `.tsp-row-actions` | Sticky `thead` (`inset-block-start` = header height); sortable headers are links with `aria-sort`; first column is the row header (`th scope="row"`) |
| Card list (mobile table) | `.tsp-table--cards` | Below 768 px each `tr` is a card; each `td` shows its column name from `data-label` |
| Batch bar | `.tsp-batch` | Appears when rows are selected: «n مورد انتخاب شد» + actions; without JavaScript it is always visible above the table |
| Pagination | `.tsp-pager` | `nav aria-label="صفحه‌بندی"`; «قبلی / بعدی», page size select, «x–y از n» |
| Stat tile | `.tsp-stat` (replaces `.ts-stat`) | A link: number, label, optional subtitle |
| Attention list | `.tsp-todo`, `.tsp-todo__item` | Count pill + sentence + chevron; each item is one link |
| Funnel | `.tsp-funnel` | Horizontal bars with numbers, always followed by a `<table>` with the same data (visible in print, visually hidden otherwise) |
| Stepper | `.tsp-steps`, `[aria-current="step"]` | Ordered list «مرحلهٔ ۲ از ۴» |
| Empty state | `.tsp-empty`, `--filter`, `--denied`, `--error` | Title, one sentence, one action |
| Confirm page | `.tsp-confirm` | Card naming the object, consequences list, two buttons (danger + cancel) |
| Danger button | `.ts-btn--danger` | Background `--danger`, white text (7.5:1) |
| Field | `.tsp-field`, `.tsp-field__label`, `.tsp-field__hint`, `.tsp-field__error` | Label above; `aria-describedby` links hint and error; error also in the summary at the top |
| Error summary | `.tsp-errors` | `role="alert"`, list of links to the fields |
| Flash | `.tsp-flash`, `--ok`, `--danger` | `role="status"` / `role="alert"` |
| Timeline | `.tsp-timeline` | `ol`, date + sentence |
| Key-value header | `.tsp-facts` | Client header |
| QR block | `.tsp-qr` | `<img>` from Odoo's public barcode route in its query form, `/report/barcode?barcode_type=QR&value=<url-encoded link>&width=220&height=220` (the path form can mangle the `//` of a URL; check the image on a clone in S6), with `alt="کد QR پیوند دعوت"` and the link text beside it |
| Job status | `.tsp-job` | State, progress bar, summary, download |
| Help link | `.tsp-what` | «این چیست؟» link to a help anchor |
| Bell | `.tsp-bell` | Link with the unread count; `aria-label="اعلان‌ها، n خوانده‌نشده"` |

## 3. Status vocabulary (one word and one colour per state, everywhere)

| Object | State | Persian | Pill |
|---|---|---|---|
| Invitation | `invited` | دعوت‌شده | default |
| | `opened` | بازشده | default |
| | `accepted` | پذیرفته | info |
| | `in_progress` | در حال پاسخ | info |
| | `done` | تکمیل‌شده | ok |
| | `expired` | منقضی | neutral |
| | `declined` | ردشده | neutral |
| | `withdrawn` | لغوشده | neutral |
| Overdue marker | deadline passed | مهلت گذشته | warn |
| Sharing | shared | به اشتراک گذاشته | ok |
| | not shared | بدون اشتراک | neutral |
| Client | `active` / `archived` | فعال / بایگانی‌شده | — / neutral |
| Member | active / awaiting verification / deactivated | فعال / در انتظار احراز صلاحیت / غیرفعال | ok / warn / neutral |
| Panel | `active` / pending approval / `suspended` / `closed` | فعال / در انتظار تأیید / معلق / بسته | ok / warn / danger / neutral |
| Job | queued / running / done / failed / expired | در صف / در حال انجام / آماده / ناموفق / منقضی | default / info / ok / danger / neutral |

A state is never shown by colour alone: the pill always carries the word.

## 4. RTL and bidirectional text

- Layout mirrors: menu at the inline start (right), back arrow points right (`→`, as
  `.ts-back` does), chevrons point left for "forward".
- Not mirrored: charts and their axes, phone numbers, codes, URLs, emails, clock times.
- Progress bars and steppers run from right to left.
- Every phone, email, panel code, link and licence number is wrapped in `<bdi dir="ltr">`.
- Inputs for phone, email, code, URL: `dir="ltr"`, `inputmode="tel" | "email" | "numeric"`,
  `autocomplete` set (`tel`, `email`, `one-time-code`); placeholder shows the expected form
  (`09123456789`).
- Persian and Arabic-Indic digits typed by the user are accepted everywhere and normalised on
  the server.
- Persian digits in pages (`fa_digits`), Latin digits in exports and inside `dir="ltr"` codes.
- Jalali dates in pages («۹ مهر ۱۴۰۵» or `۱۴۰۵/۰۷/۰۹`); exports carry Jalali and ISO columns.

## 5. Accessibility checklist (WCAG 2.2 AA; run on every new page)

| # | Check | Criterion |
|---|---|---|
| 1 | One `h1`; headings in order; landmarks `header`, `nav` (labelled), `main#wrap`, `footer` | 1.3.1, 2.4.6 |
| 2 | Every input has a visible `<label for>`; hints and errors linked with `aria-describedby` | 1.3.1, 3.3.2 |
| 3 | Text contrast ≥ 4.5:1 (large text 3:1); borders of controls and focus ring ≥ 3:1; use only token pairs listed in section 1 | 1.4.3, 1.4.11 |
| 4 | State never by colour alone | 1.4.1 |
| 5 | Works at 375 px and at 200% zoom with no horizontal scroll and no lost content | 1.4.10 |
| 6 | Everything reachable and operable by keyboard; visible focus; the sticky header never covers the focused element (`scroll-margin-top` on focusable rows and anchors) | 2.1.1, 2.4.7, **2.4.11** |
| 7 | No action needs dragging | **2.5.7** |
| 8 | Targets ≥ 24×24 px; ours are 44 px, inline links in sentences excepted | **2.5.8** |
| 9 | «راهنما» in the same place in the same order on every page | **3.2.6** (A) |
| 10 | Wizards never ask twice for what was already entered; values carried forward and kept after an error | **3.3.7** (A) |
| 11 | Sign-in and re-authentication: one code field, paste and autofill allowed, no puzzle, no need to retype from memory | **3.3.8** |
| 12 | Errors identified in text, with a suggestion; error summary focused after submit | 3.3.1, 3.3.3 |
| 13 | Status messages announced (`role="status"` / `alert`) | 4.1.3 |
| 14 | Charts have a data table; images have `alt`; decorative images `alt=""` | 1.1.1 |
| 15 | Page `<title>` is Persian and names the page and the panel | 2.4.2 |
| 16 | `prefers-reduced-motion` respected (rule exists) | 2.3.3 |
| 17 | Print view readable in black and white, with date and page numbers | — (ITC/ATP 5.3) |

How it is verified in a rehearsal: `tools/vps/ts_shot.py` (headless audit) is extended in S0
to load a list of panel routes signed in as each fixture role at 1280 and 375 px and to fail
on: horizontal overflow, missing `h1`, input without label, English text in the title, and a
computed contrast below the thresholds for the listed selectors. Screenshots are kept on the
VPS and only looked at when a check fails.

## 6. Copy rules (Persian)

- Plain, respectful, short sentences; second person «شما». No exclamation marks, no
  marketing adjectives.
- Say what happened and what to do next: «دعوت فرستاده نشد، چون شمارهٔ موبایل معتبر نیست.
  شماره را به شکل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.»
- One word per concept, everywhere: پنل (not «فضای کاری» in new pages), عضو، نقش،
  شرکت‌کننده (or the panel's client word), سنجه، دعوت، نتیجه، گزارش، اشتراک‌گذاری، اعتبار،
  مسئول («کارشناس مسئول»).
- Honest claims only. Forbidden everywhere: «رشتهٔ مناسب تو», «احتمال قبولی», «تضمین», any
  claim of norms, reliability or validity the instruments do not have, any claim of approval
  by the Psychology and Counseling Organization, any price comparison that was not checked
  live. While free: «رایگان در این فصل», never «رایگان برای همیشه».
- Results language: descriptive, with limits («این نتیجه تشخیص نیست»). Dashboards and lists
  never characterise a person.
- Privacy sentences say who sees what in concrete words: «مشاور شما خلاصهٔ نتیجه را می‌بیند؛
  پاسخ‌های شما را هیچ‌کس جز خودتان نمی‌بیند.»
- Buttons are verbs: «دعوت بفرست», «ذخیره», «لغو دعوت». Destructive confirmations repeat the
  object: «بله، این عضو غیرفعال شود».
- No English in the interface except inside `<bdi>` for codes and addresses.
- Every sentence that describes behaviour is checked against the code before a ship
  (lesson of 2026-09-29: public pages claimed things the product did not do).

## 7. Do and don't

| Do | Don't |
|---|---|
| Use a component from section 2 | Write one-off styles in a template |
| Put one primary action on a page | Offer three equal buttons |
| Link every number to its list | Show a number nobody can drill into |
| Show the reason when something is hidden («به اشتراک گذاشته نشده») | Show an empty area |
| Use a confirmation page for irreversible actions | Use a JavaScript `confirm()` |
| Keep filters, sort and page in the URL | Put the search text (often a name) in a URL, a saved view or a job |
| Render names only after the permission check on that page | Put names in notification titles, emails or URLs |
