# CareQual QMS: Hospital Management Software Quality Management System

An academic Software Quality Assurance (SQA) prototype for managing quality across the development and
maintenance of a hospital management system. **It is not a real patient-management application. Do not store real patient data.**

**Stack:** Python Flask · SQLite · Jinja2 · HTML5/CSS3/JavaScript · Chart.js (bundled locally, works offline)

This release is a full **UI/UX redesign** ("Modern Quality Intelligence Workspace"). The SQLite schema, routes,
accepted form values and business rules of the original prototype are preserved. See *Backend changes* for the few additions.

---

## 1. Run it on Windows with VS Code

1. Install **Python 3.10 or newer** from python.org (tick *Add python.exe to PATH*).
2. Unzip the project and open the folder in VS Code (*File → Open Folder…*).
3. Open a terminal (*Terminal → New Terminal*, PowerShell) and create/activate a virtual environment:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once, then activate again.
   (In Command Prompt use `.venv\Scripts\activate.bat`.) In VS Code choose *Python: Select Interpreter → .venv*.
4. Install the only dependency:

   ```powershell
   pip install -r requirements.txt
   ```
5. Start the app:

   ```powershell
   python app.py
   ```
6. Open **http://127.0.0.1:5000** in your browser. Stop the server with `Ctrl+C`.

No internet connection is needed: fonts, icons and Chart.js are bundled in `static/`.

### Keeping your existing data

Your records live in **`qms.db`** next to `app.py`. This package deliberately does **not** include a `qms.db`.

* **Upgrading your current project:** copy this project's files over your old project folder (or copy your old `qms.db` into this folder).
  The app uses the existing database as-is; the schema is unchanged and nothing is migrated, reset or overwritten.
  It creates a fresh seeded `qms.db` only if none exists.
* Back up `qms.db` before any major change; it is an ordinary file you can copy.
* To use a database elsewhere, set `QMS_DB_PATH` (e.g. `$env:QMS_DB_PATH="D:\backup\qms.db"` in PowerShell).

### Optional settings

| Variable | Purpose |
|---|---|
| `FLASK_DEBUG=1` | Developer mode with auto-reload. **Off by default.** Never use it on a shared network. |
| `QMS_SECRET_KEY` | Fixed session/CSRF key. If unset, a random key is created once in `.secret_key` (don't share or commit that file). |
| `QMS_DB_PATH` | Alternative SQLite file location. |

---

## 2. What's in the redesign

**Application shell:** top bar (logo, global search, theme toggle, "needs attention" bell, prototype-session menu),
collapsible navigation rail (off-canvas drawer on mobile), breadcrumb + page header on every page, flash toasts, footer.

| # | Module | Highlights |
|---|---|---|
| A | **Overview** | Release-gate hero built from the real checklist, 10-indicator KPI board (all linked), 4 charts, recent defects, audit-trail activity |
| B | **Quality plans** | Register, search/filter, approval stepper, create + status change, past-target flag |
| C | **Reviews** | Register, decision workflow with comments, completion rate |
| D | **Test management** | Result strip, failed/blocked rows highlighted, record results, *log defect from failed test* (pre-fills the form) |
| E | **Defects** | Critical rows emphasised, workflow stepper, update form, **locked-until-fix-notes verification**, reopen, linked CAPA |
| F | **Document control** | Metadata register with an explicit "no file storage / no version history" notice |
| G | **CAPA & improvement** | Root cause / corrective / preventive, overdue flag, effectiveness verification, links to defects |
| H | **Metrics & reports** | 6 rates, 6 charts, summary tables, **date-range filter**, CSV exports, definitions, audit trail |
| I | **Release readiness** | Gate checklist, live evidence, requirement approvals, ready / not-ready verdict from the real rules |

Also added: global **search** across all modules (press `/`), light/dark theme, and CSV exports for every register.

### Design decisions

* **Identity:** deep navy and charcoal foundations, electric-blue → violet accent, used sparingly (logo, active-nav marker, primary buttons, the release-gate glow). The navigation rail stays navy in both themes as a constant anchor.
* **One signature element:** the release-gate strip. A QMS exists to answer "can we release?", so that answer, built from real checklist data, leads the dashboard.
* **Type:** Sora (headings and KPI figures) with IBM Plex Sans (interface text). Both are bundled.
* **Tables + side drawers:** lists stay scannable; every edit/verify action happens in a keyboard-accessible drawer (native `<dialog>`), so nothing is cramped into table rows. On phones, tables become stacked cards.
* **Status is never colour-only:** every badge has a text label; failed/blocked/critical add an icon.
* **Honest UI:** the notification bell lists *computed attention items*, not sent notifications; the profile menu says the session is a prototype; documents say no files are stored.
* **Logic stays in Python:** JavaScript only handles presentation (theme, dialogs, filtering rows already sent by the server, inline validation, charts).

---

## 3. Backend changes (and why)

Everything below is additive or hardening. No table, column, route, accepted value or business rule was removed or altered.

| Change | Reason |
|---|---|
| **Fixed: creating a review crashed (HTTP 500)** | The original insert supplied 6 values for 7 columns. Reproduced on the original code, now fixed. |
| Added CSRF protection on every POST | Session-token based, no extra dependency. |
| Debug mode off by default; friendly 400/404/405/413/500 pages | No stack traces for users. |
| Secret key from `QMS_SECRET_KEY` or a generated `.secret_key` | The original hard-coded key. |
| Security headers incl. a strict Content-Security-Policy (not applied in debug mode) | Possible because all assets are local. |
| `QMS_DB_PATH` option; connections are now closed after each query | Testing/backups; avoids file locks on Windows. |
| Shared `snapshot()` and `build_release()` functions | One source of truth for Overview, Metrics and Release. Their numbers are verified equal to the original's (see §4). |
| Overview no longer shows two misleading progress bars | The original "documents" bar was `approved ÷ (approved+1)` and the "defects closed" bar was only 0% or 100%. Replaced with real ratios. |
| Release: an **empty** mandatory-gate list can no longer read as "ready" | `all([])` is `True` in Python. |
| `404` for updates to non-existent record ids; `result` on test creation is validated | Previously silent "success". |
| CSV exports neutralise cells starting with `= + - @` | Prevents spreadsheet formula injection. Added exports for tests, reviews, plans, documents, CAPA and audit log. |
| **New route `POST /requirements/<id>/status`** (+ panel on the Release page) | The original app read requirements to evaluate the gate *Critical requirements approved* but gave no way to approve one, so that gate could never pass from the UI. Values: Pending Review / Approved / Rejected. |
| New read-only routes: `/search`, `/export/<dataset>`; optional `?from_test=` / `?from_defect=` form pre-fill | Search, extra exports, convenience. |

---

## 4. Testing report

Run in the development environment on Python 3.12, Flask 3.1, headless Chromium 141.

### Passed: automated backend and regression tests (81 checks)

* Built a database with the **original** app and added varied records; the new app's **test pass rate, review completion, defect totals/closure, critical-open count, requirement counts and every release-gate status** equal the original's.
* **Schema is identical** before and after starting the new app; no records lost or added by viewing.
* All pages return 200 on existing data; CSRF rejects missing/invalid tokens; user input is HTML-escaped.
* Create: plan, review (the fixed bug), test case, defect, document, CAPA. Invalid severity/result values → 400.
* **Defect verification:** blocked without fix notes; blocked without verifier; cannot be closed via the update form; closes with verifier + timestamp.
* **CAPA verification:** same rules; overdue flag; defect link resolves from `DEF-3` text.
* Release: cannot pass a gate without evidence + reviewer; stays **not ready** while any mandatory gate is Pending/Fail/Not Applicable; becomes ready only when all genuinely pass; an empty checklist is never ready.
* Metrics date filter, invalid/reversed dates, CSV content and formula-injection safety, search (wildcard-safe, by identifier).

### Passed: browser tests (51 checks, 3 consecutive clean runs)

* All 4 dashboard charts render real pixels; legends match data. **No JavaScript console errors or warnings** on any page.
* No horizontal overflow on any of the 9 pages at 1440 px (dark and light) and 390 px (mobile).
* Theme and collapsed-rail state persist; tooltips on the collapsed rail; popovers; `/` search shortcut; deep links open the right record drawer.
* Filters (text, dropdown, URL-preset from KPI links, empty state, reset); inline validation (including whitespace-only input); confirmation dialogs (cancel and confirm paths); full defect update → verify → close flow through the UI; release gate and requirement forms.
* Skip link is the first Tab stop, one `h1`/`main` per page, all controls labelled, no duplicate ids.
* Mobile: off-canvas menu opens/closes, tables become cards, drawers go full-width.

### Not tested

* Browsers other than Chromium (Firefox, Safari, Edge), real touch devices, and screen readers. Keyboard operation was tested; formal WCAG contrast auditing was not.
* Running on Windows itself (developed and tested on Linux); the Windows steps above are standard but unverified here.
* Very large datasets (hundreds of rows): lists are rendered in full and filtered in the browser.
* Concurrent multi-user editing (SQLite prototype, single user assumed).

---

## 5. Known limitations and features not implemented

* **No login or role-based access.** Every action is logged as "QMS User". Don't expose the server beyond `127.0.0.1`.
* **Documents:** metadata only. No upload, download, file storage or version history.
* **Approvals** (plans, documents, requirements) store a status only, not approver identity or date.
* **No edit-details or delete** for existing records (the original backend has none). Only status/decision/result/verification changes are supported, so no destructive actions exist.
* Defects have no stored test-case link. "Log defect from test" writes the reference into the description text only. CAPA→defect links are matched from the `DEF-<n>` text.
* "Open" defects means *not Closed*, which, as in the original, includes **Rejected** defects until they are verified and closed. This is surfaced in the UI rather than changed.
* Forms don't keep typed input if the server rejects them (the original redirect-after-post pattern); client-side validation catches the common cases first.
* Date filters on Metrics use creation date (documents: last updated), the only dates stored.
* The release verdict summarises gates; it doesn't replace a human release decision.

---

## 6. Files

**New**

```
templates/_macros.html        reusable components (icons, badges, fields, drawers, modals…)
templates/_icons.svg          Lucide icon sprite (inlined into every page)
templates/search.html         global search results
static/css/style.css          the design system (tokens + components)
static/js/theme-init.js       pre-paint theme/menu state
static/js/app.js              shell interactions
static/js/charts.js           Chart.js rendering
static/vendor/                Chart.js (MIT) + licences
static/fonts/                 Sora + IBM Plex Sans (OFL) + licences
```

**Modified (fully redesigned)**

```
app.py                        see "Backend changes"
templates/base.html  overview.html  plans.html  reviews.html  tests.html
templates/defects.html  documents.html  capa.html  metrics.html  release.html  error.html
README.md  (requirements.txt unchanged: Flask only)
```

**Removed:** `static/style.css` (the old Clinical Teal stylesheet, replaced by `static/css/style.css`).

---

## 7. Project structure

```
CareQual_QMS/
├── app.py                 Flask app, routes, SQLite helpers, shared calculations
├── requirements.txt
├── qms.db                 created on first run (not included in this package)
├── templates/             Jinja2 templates (base layout + one per module)
└── static/
    ├── css/style.css      design system
    ├── js/                app.js, charts.js, theme-init.js
    ├── vendor/            Chart.js
    └── fonts/             Sora, IBM Plex Sans
```

Third-party assets and licences: Chart.js (MIT), Lucide icons (ISC), Sora and IBM Plex Sans (SIL OFL 1.1).
