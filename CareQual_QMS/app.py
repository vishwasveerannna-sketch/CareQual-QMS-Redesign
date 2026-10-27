"""CareQual QMS - Hospital Management Software Quality Management System.

Academic prototype (Flask + SQLite). The database schema, routes, accepted form
values and business rules of the original prototype are preserved. Changes made
for the redesign are additive or hardening only and are listed in README.md.
"""
from flask import (Flask, render_template, request, redirect, url_for, flash,
                   abort, session, Response)
from markupsafe import Markup, escape
import sqlite3
import csv
import hmac
import io
import os
import re
import secrets
from contextlib import closing
from pathlib import Path
from datetime import datetime, date

BASE_DIR = Path(__file__).resolve().parent
# DB location: same qms.db as before unless QMS_DB_PATH is set (used for testing/backups).
DB_PATH = Path(os.environ.get("QMS_DB_PATH") or (BASE_DIR / "qms.db"))


def load_secret_key():
    """Secret key for sessions/CSRF: env var, else a random key persisted beside the app."""
    env_key = os.environ.get("QMS_SECRET_KEY")
    if env_key:
        return env_key
    key_file = BASE_DIR / ".secret_key"
    try:
        if key_file.exists():
            saved = key_file.read_text().strip()
            if saved:
                return saved
        key = secrets.token_hex(32)
        key_file.write_text(key)
        return key
    except OSError:
        return secrets.token_hex(32)  # read-only folder: key lasts for this run only


app = Flask(__name__)
app.secret_key = load_secret_key()
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    MAX_CONTENT_LENGTH=1024 * 1024,
)

MODULES = [
    ("overview", "Overview", "layout-dashboard"),
    ("plans", "Quality Plans", "clipboard-list"),
    ("reviews", "Reviews", "file-check"),
    ("tests", "Test Management", "flask-conical"),
    ("defects", "Defects", "bug"),
    ("documents", "Document Control", "files"),
    ("metrics", "Metrics & Reports", "chart-no-axes-combined"),
    ("capa", "CAPA & Improvement", "refresh-cw"),
    ("release", "Release Readiness", "shield-check"),
]

# Accepted option lists. These are the same values the original forms offered.
CHOICES = {
    "plan_status": ["Draft", "Pending Approval", "Approved", "Retired"],
    "review_type": ["Requirement", "Design", "Code", "Test Plan", "Quality Document", "Release"],
    "review_decision": ["Pending", "Approved", "Rejected", "Changes Required"],
    "test_type": ["Unit", "Integration", "System", "Security", "Performance", "Recovery", "Regression", "User Acceptance"],
    "test_result": ["Not Run", "Passed", "Failed", "Blocked"],
    "defect_category": ["Data Integrity", "Patient Safety", "Security", "Reliability", "Performance", "Usability", "Documentation", "Interoperability", "Other"],
    "severity": ["Critical", "High", "Medium", "Low"],
    "priority": ["Urgent", "High", "Normal", "Low"],
    "defect_status": ["Open", "In Progress", "Fixed - Pending Verification", "Closed", "Rejected"],
    "doc_type": ["Plan", "Procedure", "Checklist", "Test Evidence", "Report", "Release Note", "Other"],
    "doc_status": ["Draft", "In Review", "Approved", "Obsolete"],
    "capa_status": ["Open", "In Progress", "Pending Verification", "Closed"],
    "release_status": ["Pending", "Pass", "Fail", "Not Applicable"],
    "requirement_status": ["Pending Review", "Approved", "Rejected"],
}

# Visual tone for each status/severity value (used only for presentation).
TONES = {
    "Approved": "success", "Passed": "success", "Pass": "success", "Closed": "success",
    "Failed": "danger", "Fail": "danger", "Rejected": "danger",
    "Blocked": "orange",
    "Pending": "warning", "Pending Approval": "warning", "Pending Review": "warning",
    "In Review": "warning", "Pending Verification": "warning",
    "Fixed - Pending Verification": "warning", "Changes Required": "warning",
    "Open": "info", "In Progress": "violet",
    "Draft": "neutral", "Not Run": "neutral", "Not Applicable": "neutral",
    "Obsolete": "neutral", "Retired": "neutral",
    "Critical": "danger", "High": "orange", "Medium": "warning", "Low": "neutral",
}


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS quality_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, objective TEXT NOT NULL,
            owner TEXT NOT NULL, target_date TEXT,
            status TEXT NOT NULL DEFAULT 'Draft',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT NOT NULL, item_ref TEXT NOT NULL,
            reviewer TEXT NOT NULL, decision TEXT NOT NULL DEFAULT 'Pending',
            comments TEXT DEFAULT '', review_date TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS test_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requirement_ref TEXT DEFAULT '', title TEXT NOT NULL,
            test_type TEXT NOT NULL, expected_result TEXT NOT NULL,
            actual_result TEXT DEFAULT '', result TEXT NOT NULL DEFAULT 'Not Run',
            tester TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS defects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, description TEXT NOT NULL,
            category TEXT NOT NULL, severity TEXT NOT NULL,
            priority TEXT NOT NULL, owner TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            root_cause TEXT DEFAULT '', fix_notes TEXT DEFAULT '',
            created_at TEXT NOT NULL, verified_by TEXT DEFAULT '',
            verified_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, doc_type TEXT NOT NULL,
            version TEXT NOT NULL, owner TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Draft',
            location TEXT DEFAULT '', updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS capa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, linked_defect TEXT DEFAULT '',
            root_cause TEXT NOT NULL, corrective_action TEXT NOT NULL,
            preventive_action TEXT NOT NULL, owner TEXT NOT NULL,
            due_date TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Open',
            verification_notes TEXT DEFAULT '', created_at TEXT NOT NULL,
            verified_by TEXT DEFAULT '', verified_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, description TEXT NOT NULL,
            risk_level TEXT NOT NULL, acceptance_criteria TEXT NOT NULL,
            owner TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending Review',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL, entity_id INTEGER,
            action TEXT NOT NULL, details TEXT DEFAULT '',
            actor TEXT NOT NULL DEFAULT 'QMS User', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS release_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_name TEXT NOT NULL, mandatory INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'Pending',
            evidence TEXT DEFAULT '', checked_by TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """)
        # Seed once, so records remain user-editable and are not duplicated on restart.
        if c.execute("SELECT COUNT(*) FROM quality_plans").fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.executemany("""INSERT INTO quality_plans
                (title, objective, owner, target_date, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""", [
                ("Patient Data Integrity Plan", "Prevent incorrect, duplicate, or mismatched patient-linked records.", "QA Lead", "2026-11-15", "Approved", now),
                ("Release Verification Plan", "Define mandatory verification evidence before a release.", "Test Lead", "2026-11-20", "Draft", now),
            ])
        if c.execute("SELECT COUNT(*) FROM requirements").fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.executemany("""INSERT INTO requirements
                (title, description, risk_level, acceptance_criteria, owner, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", [
                ("Patient identity association", "The software must prevent a clinical record from being linked to a mismatched patient identifier.", "Critical", "A mismatched or unknown patient identifier is rejected and the event is logged.", "Business Analyst", "Approved", now),
                ("Role-based access control", "The software must restrict sensitive records according to approved user roles.", "Critical", "Unauthorized requests are denied and recorded in the audit trail.", "Security Reviewer", "Pending Review", now),
                ("Billing calculation integrity", "The software must calculate totals consistently and avoid duplicate transaction processing.", "High", "Boundary and duplicate-submission tests pass.", "Business Analyst", "Pending Review", now),
            ])
        if c.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.executemany("""INSERT INTO reviews
                (item_type, item_ref, reviewer, decision, comments, review_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", [
                ("Requirement", "REQ-1 Patient identity association", "Clinical Reviewer", "Approved", "Identity matching is safety-critical.", now, now),
                ("Design", "Access control design", "Security Reviewer", "Pending", "", "", now),
                ("Test Plan", "Release regression suite", "QA Lead", "Pending", "", "", now),
            ])
        if c.execute("SELECT COUNT(*) FROM test_cases").fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.executemany("""INSERT INTO test_cases
                (requirement_ref, title, test_type, expected_result, actual_result, result, tester, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", [
                ("REQ-1", "Reject mismatched patient identifier", "Integration", "Record association is rejected and event logged.", "Validation rejected mismatched ID.", "Passed", "Test Analyst", now),
                ("REQ-2", "Deny unauthorized record access", "Security", "Access is denied and logged.", "Not executed yet.", "Failed", "Security Tester", now),
                ("REQ-3", "Prevent duplicate billing submission", "System", "Duplicate transaction is prevented or safely reconciled.", "", "Not Run", "Test Analyst", now),
                ("REQ-1", "Accept valid patient identifier", "Integration", "Valid association is saved.", "Valid record saved.", "Passed", "Test Analyst", now),
            ])
        if c.execute("SELECT COUNT(*) FROM defects").fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.executemany("""INSERT INTO defects
                (title, description, category, severity, priority, owner, status, root_cause, fix_notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", [
                ("Unauthorized record access not denied", "A test account with an insufficient role could access a restricted record in the test environment.", "Security", "Critical", "Urgent", "Security Developer", "Open", "", "", now),
                ("Billing rounding inconsistency", "Totals differ by a small amount in a boundary case.", "Data Integrity", "High", "High", "Module Developer", "In Progress", "Rounding rule differs between components.", "", now),
                ("Missing test evidence attachment", "One test record has no reproducible evidence.", "Documentation", "Medium", "Normal", "Test Analyst", "Open", "", "", now),
            ])
        if c.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.executemany("""INSERT INTO documents
                (title, doc_type, version, owner, status, location, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", [
                ("Quality Management Plan", "Plan", "1.0", "QA Lead", "Approved", "QMS/Plans/QMP-v1.0", now),
                ("Risk-Based Test Strategy", "Procedure", "0.9", "Test Lead", "Draft", "QMS/Testing/Test-Strategy", now),
                ("Defect Handling Procedure", "Procedure", "1.0", "QA Lead", "Approved", "QMS/Procedures/Defect-Handling", now),
            ])
        if c.execute("SELECT COUNT(*) FROM capa").fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.execute("""INSERT INTO capa
                (title, linked_defect, root_cause, corrective_action, preventive_action, owner, due_date, status, verification_notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("Strengthen authorization checks", "DEF-1", "Authorization was not enforced consistently in one request path.",
                 "Correct the authorization check and retest affected routes.",
                 "Add role-based negative tests to the regression suite.",
                 "Security Lead", "2026-11-05", "Open", "", now))
        if c.execute("SELECT COUNT(*) FROM release_checks").fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.executemany("""INSERT INTO release_checks
                (check_name, mandatory, status, evidence, checked_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)""", [
                ("No open critical defects", 1, "Pending", "", "", now),
                ("Critical requirements approved", 1, "Pending", "", "", now),
                ("Critical test cases passed", 1, "Pending", "", "", now),
                ("Security review completed", 1, "Pending", "", "", now),
                ("Backup and recovery test evidence recorded", 1, "Pending", "", "", now),
                ("Release notes and rollback plan approved", 1, "Pending", "", "", now),
            ])

def log_action(entity_type, entity_id, action, details=""):
    with closing(connect()) as c, c:
        c.execute("""INSERT INTO audit_log
            (entity_type, entity_id, action, details, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (entity_type, entity_id, action, details, "QMS User", datetime.now().strftime("%Y-%m-%d %H:%M")))

def count(query, params=()):
    with closing(connect()) as c:
        return c.execute(query, params).fetchone()[0]

def rows(query, params=()):
    with closing(connect()) as c:
        return c.execute(query, params).fetchall()

def insert(table, fields, values):
    cols = ", ".join(fields)
    marks = ", ".join(["?"] * len(values))
    with closing(connect()) as c, c:
        cur = c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", values)
        return cur.lastrowid

def update(table, field, value, row_id, extra_fields=None, extra_values=None):
    assignments = [f"{field} = ?"]
    vals = [value]
    if extra_fields:
        assignments += [f"{f} = ?" for f in extra_fields]
        vals += list(extra_values or [])
    vals.append(row_id)
    with closing(connect()) as c, c:
        c.execute(f"UPDATE {table} SET {', '.join(assignments)} WHERE id = ?", vals)

def require(table, rid):
    """404 if a record does not exist (table names are literals in this file)."""
    if not count(f"SELECT COUNT(*) FROM {table} WHERE id = ?", (rid,)):
        abort(404)


# --------------------------------------------------------------------------
# Security: CSRF token (session based), response headers, secure error pages
# --------------------------------------------------------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]

def csrf_field():
    return Markup('<input type="hidden" name="csrf_token" value="%s">') % csrf_token()

@app.before_request
def protect_from_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(sent.encode("utf-8"), expected.encode("utf-8")):
            abort(400, description="csrf")

@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if not app.debug:  # the Werkzeug debugger needs inline scripts, so only enforce CSP outside debug mode
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'")
    return resp


# --------------------------------------------------------------------------
# Shared calculations (single source of truth for dashboard, metrics, release)
# --------------------------------------------------------------------------
def pct(part, whole):
    return round(part / whole * 100) if whole else 0

def date_clause(column, d_from, d_to):
    """Optional created-date range. `column` is always a literal from this file."""
    clauses, params = [], []
    if d_from:
        clauses.append(f"substr({column}, 1, 10) >= ?"); params.append(d_from)
    if d_to:
        clauses.append(f"substr({column}, 1, 10) <= ?"); params.append(d_to)
    return ((" AND " + " AND ".join(clauses)) if clauses else ""), params

def grouped(table, column, known, date_col, d_from, d_to, extra=""):
    """Counts per value of `column`, known values first (zeros kept), unknown values appended."""
    w, p = date_clause(date_col, d_from, d_to)
    found = {r[0]: r[1] for r in rows(
        f"SELECT {column}, COUNT(*) FROM {table} WHERE 1=1{w}{extra} GROUP BY {column}", p)}
    result = {k: found.pop(k, 0) for k in known}
    result.update(found)
    return result

def valid_date(text):
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    except (TypeError, ValueError):
        return ""

def snapshot(d_from="", d_to=""):
    """All quality indicators. With no date range the numbers equal the original app's."""
    today = date.today().isoformat()
    wc, pc = date_clause("created_at", d_from, d_to)
    wu, pu = date_clause("updated_at", d_from, d_to)
    s = {"range": {"from": d_from, "to": d_to}}

    # plans
    s["plans_by_status"] = grouped("quality_plans", "status", CHOICES["plan_status"], "created_at", d_from, d_to)
    s["plans_total"] = sum(s["plans_by_status"].values())
    s["plans_approved"] = s["plans_by_status"].get("Approved", 0)
    s["plans_rate"] = pct(s["plans_approved"], s["plans_total"])

    # reviews (completion = decision recorded, as in the original)
    s["reviews_by_decision"] = grouped("reviews", "decision", CHOICES["review_decision"], "created_at", d_from, d_to)
    s["reviews_total"] = sum(s["reviews_by_decision"].values())
    s["reviews_done"] = s["reviews_total"] - s["reviews_by_decision"].get("Pending", 0)
    s["review_rate"] = pct(s["reviews_done"], s["reviews_total"])

    # tests (pass rate = passed / executed, as in the original)
    s["tests_by_result"] = grouped("test_cases", "result", CHOICES["test_result"], "created_at", d_from, d_to)
    s["tests_all"] = sum(s["tests_by_result"].values())
    s["tests_total"] = s["tests_all"] - s["tests_by_result"].get("Not Run", 0)
    s["tests_passed"] = s["tests_by_result"].get("Passed", 0)
    s["test_rate"] = pct(s["tests_passed"], s["tests_total"])
    by_type = {}
    for r in rows(f"SELECT test_type, result, COUNT(*) FROM test_cases WHERE 1=1{wc} GROUP BY test_type, result", pc):
        t = by_type.setdefault(r[0], {"type": r[0], "total": 0, "Passed": 0, "Failed": 0, "Blocked": 0, "Not Run": 0})
        t["total"] += r[2]
        t[r[1]] = t.get(r[1], 0) + r[2]
    s["tests_by_type"] = sorted(by_type.values(), key=lambda x: -x["total"])

    # defects ("open" = not Closed, as in the original)
    s["defects_by_status"] = grouped("defects", "status", CHOICES["defect_status"], "created_at", d_from, d_to)
    s["defects_total"] = sum(s["defects_by_status"].values())
    s["defects_closed"] = s["defects_by_status"].get("Closed", 0)
    s["defects_open"] = s["defects_total"] - s["defects_closed"]
    s["closure_rate"] = pct(s["defects_closed"], s["defects_total"])
    sev_open = grouped("defects", "severity", CHOICES["severity"], "created_at", d_from, d_to, " AND status != 'Closed'")
    sev_all = grouped("defects", "severity", CHOICES["severity"], "created_at", d_from, d_to)
    s["defects_by_severity"] = {k: {"open": sev_open.get(k, 0), "closed": sev_all[k] - sev_open.get(k, 0), "total": sev_all[k]} for k in sev_all}
    s["critical_open"] = sev_open.get("Critical", 0)
    s["defects_by_category"] = grouped("defects", "category", [], "created_at", d_from, d_to)

    # CAPA
    s["capa_by_status"] = grouped("capa", "status", CHOICES["capa_status"], "created_at", d_from, d_to)
    s["capa_total"] = sum(s["capa_by_status"].values())
    s["capa_closed"] = s["capa_by_status"].get("Closed", 0)
    s["capa_open"] = s["capa_total"] - s["capa_closed"]
    s["capa_rate"] = pct(s["capa_closed"], s["capa_total"])
    s["capa_overdue"] = count(
        f"SELECT COUNT(*) FROM capa WHERE status != 'Closed' AND due_date != '' AND due_date < ?{wc}", [today] + pc)

    # documents (date filter uses last-updated, the only date the table stores)
    s["docs_by_status"] = grouped("documents", "status", CHOICES["doc_status"], "updated_at", d_from, d_to)
    s["docs_total"] = sum(s["docs_by_status"].values())
    s["docs_approved"] = s["docs_by_status"].get("Approved", 0)
    s["docs_rate"] = pct(s["docs_approved"], s["docs_total"])
    types = {}
    for r in rows(f"SELECT doc_type, status, COUNT(*) FROM documents WHERE 1=1{wu} GROUP BY doc_type, status", pu):
        t = types.setdefault(r[0], {"type": r[0], "total": 0, "approved": 0})
        t["total"] += r[2]
        if r[1] == "Approved":
            t["approved"] += r[2]
    s["docs_by_type"] = sorted(types.values(), key=lambda x: -x["total"])

    # requirements (feed the release gate "Critical requirements approved")
    s["req_by_status"] = grouped("requirements", "status", CHOICES["requirement_status"], "created_at", d_from, d_to)
    s["req_total"] = sum(s["req_by_status"].values())
    s["req_approved"] = s["req_by_status"].get("Approved", 0)
    s["req_rate"] = pct(s["req_approved"], s["req_total"])
    return s


RELEASE_AUTO = {  # gate name -> how the original code derives its status
    "No open critical defects": "auto",
    "Critical requirements approved": "auto",
    "Critical test cases passed": "partial",
}

def build_release():
    """Release gate evaluation: the original release() logic, unchanged, in a reusable function."""
    critical_open = count("SELECT COUNT(*) FROM defects WHERE severity='Critical' AND status != 'Closed'")
    critical_req_unapproved = count("SELECT COUNT(*) FROM requirements WHERE risk_level='Critical' AND status != 'Approved'")
    critical_tests_failed = count("""SELECT COUNT(*) FROM test_cases
        WHERE result IN ('Failed','Blocked') AND (test_type IN ('Security','Integration','System'))""")
    checks = rows("SELECT * FROM release_checks ORDER BY id")
    check_rows = []
    for ch in checks:
        derived = ch["status"]
        note = ch["evidence"]
        if ch["check_name"] == "No open critical defects":
            derived = "Pass" if critical_open == 0 else "Fail"
            note = f"{critical_open} open critical defect(s)"
        elif ch["check_name"] == "Critical requirements approved":
            derived = "Pass" if critical_req_unapproved == 0 else "Fail"
            note = f"{critical_req_unapproved} critical requirement(s) not approved"
        elif ch["check_name"] == "Critical test cases passed":
            derived = "Fail" if critical_tests_failed > 0 else ("Pass" if ch["status"] == "Pass" else "Pending")
            note = f"{critical_tests_failed} failed/blocked critical-type test(s); other critical test evidence must be confirmed"
        check_rows.append(dict(id=ch["id"], check_name=ch["check_name"], mandatory=ch["mandatory"], status=derived,
                               evidence=note, checked_by=ch["checked_by"],
                               auto=RELEASE_AUTO.get(ch["check_name"]), stored_evidence=ch["evidence"],
                               updated_at=ch["updated_at"]))
    mandatory = [x for x in check_rows if x["mandatory"]]
    # An empty mandatory list must never read as "ready".
    ready = bool(mandatory) and all(x["status"] == "Pass" for x in mandatory)
    blockers = [x for x in mandatory if x["status"] != "Pass"]
    return dict(checks=check_rows, ready=ready, blockers=blockers,
                passed=sum(1 for x in check_rows if x["status"] == "Pass"),
                critical_open=critical_open, critical_req_unapproved=critical_req_unapproved,
                critical_tests_failed=critical_tests_failed)



def series(counts):
    """Chart payload for a {label: count} mapping; tones come from the same table as the badges."""
    labels = list(counts.keys())
    return {"labels": labels, "values": [counts[k] for k in labels], "tones": [TONES.get(k, "neutral") for k in labels]}

def severity_series(by_severity):
    labels = list(by_severity.keys())
    return {"labels": labels, "open": [by_severity[k]["open"] for k in labels], "closed": [by_severity[k]["closed"] for k in labels]}

DEFECT_REF = re.compile(r"^\s*DEF[-\s]*0*(\d+)\s*$", re.I)

def defect_id_from_ref(text):
    """'DEF-1' / 'DEF-001' / 'def 1' -> 1 (the CAPA table stores the reference as free text)."""
    m = DEFECT_REF.match(text or "")
    return int(m.group(1)) if m else None


def csv_cell(value):
    """Neutralise spreadsheet formula injection in exported text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


# --------------------------------------------------------------------------
# Template helpers: navigation badges and computed "attention" items
# --------------------------------------------------------------------------
def attention_items():
    """Items needing action, computed from live records (not push notifications)."""
    today = date.today().isoformat()
    items = []
    def add(n, tone, text, endpoint, **args):
        if n:
            items.append({"count": n, "tone": tone, "text": text, "url": url_for(endpoint, **args)})
    add(count("SELECT COUNT(*) FROM defects WHERE severity='Critical' AND status != 'Closed'"), "danger",
        "critical defect(s) not yet closed", "defects", severity="Critical", status="__open")
    add(count("SELECT COUNT(*) FROM test_cases WHERE result='Failed'"), "danger", "failed test case(s)", "tests", result="Failed")
    add(count("SELECT COUNT(*) FROM test_cases WHERE result='Blocked'"), "warning", "blocked test case(s)", "tests", result="Blocked")
    add(count("SELECT COUNT(*) FROM capa WHERE status != 'Closed' AND due_date != '' AND due_date < ?", (today,)),
        "danger", "CAPA action(s) past due date", "capa", due="overdue")
    add(count("SELECT COUNT(*) FROM reviews WHERE decision='Pending'"), "warning", "review(s) awaiting a decision", "reviews", decision="Pending")
    add(count("SELECT COUNT(*) FROM quality_plans WHERE status='Pending Approval'"), "warning", "quality plan(s) awaiting approval", "plans", status="Pending Approval")
    add(count("SELECT COUNT(*) FROM documents WHERE status='In Review'"), "info", "document(s) in review", "documents", status="In Review")
    rel = build_release()
    if not rel["ready"]:
        add(len(rel["blockers"]), "warning", "mandatory release gate(s) not passed", "release")
    return items


app.add_template_global(lambda v: TONES.get(v, "neutral"), name="tone")
app.add_template_global(csrf_field, name="csrf_field")


@app.context_processor
def inject_globals():
    nav_counts = {
        "defects": count("SELECT COUNT(*) FROM defects WHERE status != 'Closed'"),
        "tests": count("SELECT COUNT(*) FROM test_cases WHERE result IN ('Failed','Blocked')"),
        "reviews": count("SELECT COUNT(*) FROM reviews WHERE decision = 'Pending'"),
        "capa": count("SELECT COUNT(*) FROM capa WHERE status != 'Closed'"),
    }
    items = attention_items()
    return {
        "modules": MODULES, "current_year": date.today().year, "choices": CHOICES,
        "today": date.today().isoformat(), "nav_counts": nav_counts,
        "attention": items, "attention_total": sum(i["count"] for i in items),
    }


# --------------------------------------------------------------------------
# Routes (all original endpoints preserved)
# --------------------------------------------------------------------------
@app.route("/")
def overview():
    s = snapshot()
    rel = build_release()
    charts = {
        "tests": series(s["tests_by_result"]),
        "severity": severity_series(s["defects_by_severity"]),
        "reviews": series(s["reviews_by_decision"]),
        "capa": series(s["capa_by_status"]),
    }
    return render_template("overview.html", page_title="Quality Overview", s=s, rel=rel, charts=charts,
                           recent=rows("SELECT * FROM defects ORDER BY id DESC LIMIT 5"),
                           activity=rows("SELECT * FROM audit_log ORDER BY id DESC LIMIT 8"))

@app.route("/plans", methods=["GET", "POST"])
def plans():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        objective = request.form.get("objective", "").strip()
        owner = request.form.get("owner", "").strip()
        if not all([title, objective, owner]):
            flash("Title, objective, and owner are required.", "error")
        else:
            rid = insert("quality_plans", ["title","objective","owner","target_date","status","created_at"],
                         [title, objective, owner, request.form.get("target_date",""), "Draft", datetime.now().strftime("%Y-%m-%d %H:%M")])
            log_action("Quality Plan", rid, "Created", title)
            flash("Quality plan created as Draft.", "success")
        return redirect(url_for("plans"))
    records = [dict(r) for r in rows("SELECT * FROM quality_plans ORDER BY id DESC")]
    today = date.today().isoformat()
    for r in records:
        r["past_target"] = bool(r["target_date"]) and r["target_date"] < today and r["status"] in ("Draft", "Pending Approval")
    return render_template("plans.html", page_title="Quality Plans", records=records)

@app.post("/plans/<int:rid>/status")
def plan_status(rid):
    status = request.form.get("status")
    if status not in ["Draft", "Pending Approval", "Approved", "Retired"]:
        abort(400)
    require("quality_plans", rid)
    update("quality_plans", "status", status, rid)
    log_action("Quality Plan", rid, "Status changed", status)
    flash("Quality plan status updated.", "success")
    return redirect(url_for("plans"))

@app.route("/reviews", methods=["GET", "POST"])
def reviews():
    if request.method == "POST":
        vals = [request.form.get(k, "").strip() for k in ["item_type","item_ref","reviewer"]]
        if not all(vals):
            flash("Item type, reference, and reviewer are required.", "error")
        else:
            rid = insert("reviews", ["item_type","item_ref","reviewer","decision","comments","review_date","created_at"],
                         [*vals, "Pending", "", "", datetime.now().strftime("%Y-%m-%d %H:%M")])
            log_action("Review", rid, "Created", vals[1])
            flash("Review created.", "success")
        return redirect(url_for("reviews"))
    return render_template("reviews.html", page_title="Reviews", records=rows("SELECT * FROM reviews ORDER BY id DESC"))

@app.post("/reviews/<int:rid>/decision")
def review_decision(rid):
    decision = request.form.get("decision")
    if decision not in ["Approved", "Rejected", "Changes Required", "Pending"]:
        abort(400)
    require("reviews", rid)
    comments = request.form.get("comments", "").strip()
    update("reviews", "decision", decision, rid, ["comments","review_date"], [comments, datetime.now().strftime("%Y-%m-%d %H:%M")])
    log_action("Review", rid, "Decision recorded", f"{decision}: {comments}")
    flash("Review decision saved.", "success")
    return redirect(url_for("reviews"))

@app.route("/tests", methods=["GET", "POST"])
def tests():
    if request.method == "POST":
        keys = ["requirement_ref","title","test_type","expected_result","tester"]
        vals = [request.form.get(k, "").strip() for k in keys]
        result = request.form.get("result", "Not Run")
        if result not in CHOICES["test_result"]:
            abort(400)
        if not all([vals[1], vals[2], vals[3], vals[4]]):
            flash("Title, test type, expected result, and tester are required.", "error")
        else:
            rid = insert("test_cases", keys + ["actual_result","result","created_at"],
                         vals + [request.form.get("actual_result","").strip(), result, datetime.now().strftime("%Y-%m-%d %H:%M")])
            log_action("Test Case", rid, "Created", vals[1])
            flash("Test case created.", "success")
        return redirect(url_for("tests"))
    return render_template("tests.html", page_title="Test Management", records=rows("SELECT * FROM test_cases ORDER BY id DESC"))

@app.post("/tests/<int:rid>/result")
def test_result(rid):
    result = request.form.get("result")
    if result not in ["Not Run", "Passed", "Failed", "Blocked"]:
        abort(400)
    require("test_cases", rid)
    actual = request.form.get("actual_result", "").strip()
    update("test_cases", "result", result, rid, ["actual_result"], [actual])
    log_action("Test Case", rid, "Result recorded", f"{result}: {actual}")
    if result == "Failed":
        flash("Test failed. Review the result and log a defect if required.", "warning")
    else:
        flash("Test result saved.", "success")
    return redirect(url_for("tests"))

@app.route("/defects", methods=["GET", "POST"])
def defects():
    if request.method == "POST":
        keys = ["title","description","category","severity","priority","owner"]
        vals = [request.form.get(k, "").strip() for k in keys]
        if not all(vals):
            flash("Complete all required defect fields.", "error")
        elif vals[3] not in ["Critical","High","Medium","Low"] or vals[4] not in ["Urgent","High","Normal","Low"]:
            abort(400)
        else:
            rid = insert("defects", keys + ["status","root_cause","fix_notes","created_at"],
                         vals + ["Open", "", "", datetime.now().strftime("%Y-%m-%d %H:%M")])
            log_action("Defect", rid, "Created", vals[0])
            flash(f"Defect DEF-{rid} recorded.", "success")
        return redirect(url_for("defects"))
    # Optional pre-fill when a defect is raised from a failed test (?from_test=<id>)
    prefill = None
    from_test = request.args.get("from_test", type=int)
    if from_test:
        t = rows("SELECT * FROM test_cases WHERE id=?", (from_test,))
        if t:
            t = t[0]
            prefill = {
                "title": f"Test failed: {t['title']}",
                "description": (f"Raised from TC-{t['id']:03d}"
                                + (f" (requirement {t['requirement_ref']})" if t["requirement_ref"] else "")
                                + f".\nExpected: {t['expected_result']}\nActual: {t['actual_result'] or 'not recorded'}"),
                "category": "Security" if t["test_type"] == "Security" else "Other",
            }
    linked = {}
    for c in rows("SELECT id, title, status, linked_defect FROM capa ORDER BY id"):
        did = defect_id_from_ref(c["linked_defect"])
        if did:
            linked.setdefault(did, []).append(dict(c))
    return render_template("defects.html", page_title="Defects", records=rows("SELECT * FROM defects ORDER BY id DESC"),
                           prefill=prefill, linked_capa=linked)

@app.post("/defects/<int:rid>/update")
def defect_update(rid):
    status = request.form.get("status")
    if status not in ["Open", "In Progress", "Fixed - Pending Verification", "Closed", "Rejected"]:
        abort(400)
    require("defects", rid)
    root = request.form.get("root_cause", "").strip()
    fix = request.form.get("fix_notes", "").strip()
    if status == "Closed":
        flash("Use Verify & Close after entering fix evidence.", "warning")
        return redirect(url_for("defects"))
    update("defects", "status", status, rid, ["root_cause","fix_notes"], [root, fix])
    log_action("Defect", rid, "Updated", f"{status}; root cause: {root}")
    flash("Defect updated.", "success")
    return redirect(url_for("defects"))

@app.post("/defects/<int:rid>/verify")
def defect_verify(rid):
    defect = rows("SELECT * FROM defects WHERE id=?", (rid,))
    if not defect:
        abort(404)
    d = defect[0]
    verified_by = request.form.get("verified_by", "").strip()
    if not verified_by or not d["fix_notes"].strip():
        flash("Add fix notes and a verifier before verification.", "error")
        return redirect(url_for("defects"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    update("defects", "status", "Closed", rid, ["verified_by","verified_at"], [verified_by, now])
    log_action("Defect", rid, "Verified and closed", f"Verified by {verified_by}")
    flash("Defect verified and closed.", "success")
    return redirect(url_for("defects"))

@app.route("/documents", methods=["GET", "POST"])
def documents():
    if request.method == "POST":
        keys = ["title","doc_type","version","owner"]
        vals = [request.form.get(k, "").strip() for k in keys]
        if not all(vals):
            flash("Title, document type, version, and owner are required.", "error")
        else:
            rid = insert("documents", keys + ["status","location","updated_at"],
                         vals + ["Draft", request.form.get("location","").strip(), datetime.now().strftime("%Y-%m-%d %H:%M")])
            log_action("Document", rid, "Created", vals[0])
            flash("Document registered as Draft.", "success")
        return redirect(url_for("documents"))
    return render_template("documents.html", page_title="Document Control", records=rows("SELECT * FROM documents ORDER BY id DESC"))

@app.post("/documents/<int:rid>/status")
def document_status(rid):
    status = request.form.get("status")
    if status not in ["Draft", "In Review", "Approved", "Obsolete"]:
        abort(400)
    require("documents", rid)
    update("documents", "status", status, rid, ["updated_at"], [datetime.now().strftime("%Y-%m-%d %H:%M")])
    log_action("Document", rid, "Status changed", status)
    flash("Document status updated.", "success")
    return redirect(url_for("documents"))

@app.route("/capa", methods=["GET", "POST"])
def capa():
    if request.method == "POST":
        keys = ["title","linked_defect","root_cause","corrective_action","preventive_action","owner","due_date"]
        vals = [request.form.get(k, "").strip() for k in keys]
        if not vals[0] or not vals[2] or not vals[3] or not vals[4] or not vals[5]:
            flash("Title, root cause, corrective/preventive action, and owner are required.", "error")
        else:
            rid = insert("capa", keys + ["status","verification_notes","created_at"],
                         vals + ["Open", "", datetime.now().strftime("%Y-%m-%d %H:%M")])
            log_action("CAPA", rid, "Created", vals[0])
            flash("Corrective/preventive action recorded.", "success")
        return redirect(url_for("capa"))
    defect_map = {d["id"]: dict(d) for d in rows("SELECT id, title, severity, status FROM defects")}
    today = date.today().isoformat()
    records = []
    for r in rows("SELECT * FROM capa ORDER BY id DESC"):
        r = dict(r)
        r["overdue"] = bool(r["due_date"]) and r["due_date"] < today and r["status"] != "Closed"
        r["defect_id"] = defect_id_from_ref(r["linked_defect"])
        r["defect"] = defect_map.get(r["defect_id"])
        records.append(r)
    prefill = None
    from_defect = request.args.get("from_defect", type=int)
    if from_defect and from_defect in defect_map:
        d = rows("SELECT * FROM defects WHERE id=?", (from_defect,))[0]
        prefill = {"title": f"Corrective action: {d['title']}", "linked_defect": f"DEF-{d['id']:03d}",
                   "root_cause": d["root_cause"]}
    return render_template("capa.html", page_title="CAPA & Improvement", records=records, prefill=prefill)

@app.post("/capa/<int:rid>/update")
def capa_update(rid):
    status = request.form.get("status")
    if status not in ["Open", "In Progress", "Pending Verification", "Closed"]:
        abort(400)
    require("capa", rid)
    notes = request.form.get("verification_notes", "").strip()
    if status == "Closed":
        flash("Use Verify & Close to close a CAPA.", "warning")
        return redirect(url_for("capa"))
    update("capa", "status", status, rid, ["verification_notes"], [notes])
    log_action("CAPA", rid, "Updated", status)
    flash("CAPA updated.", "success")
    return redirect(url_for("capa"))

@app.post("/capa/<int:rid>/verify")
def capa_verify(rid):
    record = rows("SELECT * FROM capa WHERE id=?", (rid,))
    if not record:
        abort(404)
    verified_by = request.form.get("verified_by", "").strip()
    notes = request.form.get("verification_notes", "").strip()
    if not verified_by or not notes:
        flash("Verification notes and verifier are required.", "error")
        return redirect(url_for("capa"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    update("capa", "status", "Closed", rid, ["verification_notes","verified_by","verified_at"], [notes, verified_by, now])
    log_action("CAPA", rid, "Effectiveness verified and closed", verified_by)
    flash("CAPA effectiveness recorded and action closed.", "success")
    return redirect(url_for("capa"))

@app.route("/metrics")
def metrics():
    d_from = valid_date(request.args.get("from", "").strip())
    d_to = valid_date(request.args.get("to", "").strip())
    if (request.args.get("from") and not d_from) or (request.args.get("to") and not d_to):
        flash("Dates must use the YYYY-MM-DD format; the invalid date was ignored.", "warning")
    if d_from and d_to and d_from > d_to:
        d_from, d_to = d_to, d_from
        flash("The start date was after the end date, so the two were swapped.", "warning")
    s = snapshot(d_from, d_to)
    charts = {
        "tests": series(s["tests_by_result"]),
        "severity": severity_series(s["defects_by_severity"]),
        "reviews": series(s["reviews_by_decision"]),
        "plans": series(s["plans_by_status"]),
        "capa": series(s["capa_by_status"]),
        "docs": series(s["docs_by_status"]),
    }
    return render_template("metrics.html", page_title="Metrics & Reports", s=s, charts=charts,
                           audit=rows("SELECT * FROM audit_log ORDER BY id DESC LIMIT 12"),
                           filtered=bool(d_from or d_to))

@app.route("/release", methods=["GET"])
def release():
    rel = build_release()
    return render_template("release.html", page_title="Release Readiness", checks=rel["checks"], ready=rel["ready"],
                           rel=rel, s=snapshot(),
                           requirements=rows("SELECT * FROM requirements ORDER BY id"))

@app.post("/release/<int:rid>")
def release_update(rid):
    status = request.form.get("status")
    if status not in ["Pending", "Pass", "Fail", "Not Applicable"]:
        abort(400)
    require("release_checks", rid)
    evidence = request.form.get("evidence", "").strip()
    checked_by = request.form.get("checked_by", "").strip()
    if status == "Pass" and (not evidence or not checked_by):
        flash("Evidence and reviewer are required to mark a check as Pass.", "error")
        return redirect(url_for("release"))
    update("release_checks", "status", status, rid, ["evidence","checked_by","updated_at"], [evidence, checked_by, datetime.now().strftime("%Y-%m-%d %H:%M")])
    log_action("Release Check", rid, "Updated", f"{status}: {evidence}")
    flash("Release check updated.", "success")
    return redirect(url_for("release"))

@app.post("/requirements/<int:rid>/status")
def requirement_status(rid):
    """Added in the redesign: the original app read requirements (they drive a release gate)
    but offered no way to approve them, so that gate could never pass from the UI."""
    status = request.form.get("status")
    if status not in CHOICES["requirement_status"]:
        abort(400)
    require("requirements", rid)
    update("requirements", "status", status, rid)
    log_action("Requirement", rid, "Status changed", status)
    flash("Requirement status updated.", "success")
    return redirect(url_for("release") + "#requirements")

# CSV exports -----------------------------------------------------------------
EXPORTS = {
    "tests": ("test_cases", "hospital_qms_tests.csv", ["id","requirement_ref","title","test_type","expected_result","actual_result","result","tester","created_at"]),
    "reviews": ("reviews", "hospital_qms_reviews.csv", ["id","item_type","item_ref","reviewer","decision","comments","review_date","created_at"]),
    "plans": ("quality_plans", "hospital_qms_plans.csv", ["id","title","objective","owner","target_date","status","created_at"]),
    "documents": ("documents", "hospital_qms_documents.csv", ["id","title","doc_type","version","owner","status","location","updated_at"]),
    "capa": ("capa", "hospital_qms_capa.csv", ["id","title","linked_defect","root_cause","corrective_action","preventive_action","owner","due_date","status","verification_notes","verified_by","verified_at","created_at"]),
    "audit": ("audit_log", "hospital_qms_audit_log.csv", ["id","entity_type","entity_id","action","details","actor","created_at"]),
}

@app.route("/export")
def export():
    # CSV export of defects (original endpoint), using Python's csv module and safe text output.
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Title","Category","Severity","Priority","Owner","Status","Created","Verified By","Verified At"])
    for d in rows("SELECT * FROM defects ORDER BY id"):
        writer.writerow([d["id"], csv_cell(d["title"]), d["category"], d["severity"], d["priority"], csv_cell(d["owner"]), d["status"], d["created_at"], csv_cell(d["verified_by"]), d["verified_at"]])
    return Response(output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=hospital_qms_defects.csv"})

@app.route("/export/<dataset>")
def export_dataset(dataset):
    if dataset not in EXPORTS:
        abort(404)
    table, filename, cols = EXPORTS[dataset]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cols)
    for r in rows(f"SELECT {', '.join(cols)} FROM {table} ORDER BY id"):
        writer.writerow([csv_cell(r[c]) for c in cols])
    return Response(output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"})

# Global search ---------------------------------------------------------------
SEARCH_SPEC = [
    # endpoint, label, icon, table, id-prefix, title expr, subtitle expr, status column, searchable columns
    ("plans", "Quality plans", "clipboard-list", "quality_plans", "PLAN", "title", "owner", "status", ["title", "objective", "owner", "status"]),
    ("reviews", "Reviews", "file-check", "reviews", "REV", "item_ref", "item_type || ' · ' || reviewer", "decision", ["item_type", "item_ref", "reviewer", "decision", "comments"]),
    ("tests", "Test cases", "flask-conical", "test_cases", "TC", "title", "test_type || ' · ' || requirement_ref", "result", ["title", "requirement_ref", "test_type", "tester", "expected_result", "actual_result", "result"]),
    ("defects", "Defects", "bug", "defects", "DEF", "title", "category || ' · ' || severity", "status", ["title", "description", "category", "severity", "owner", "status", "root_cause", "fix_notes"]),
    ("documents", "Documents", "files", "documents", "DOC", "title", "doc_type || ' v' || version", "status", ["title", "doc_type", "version", "owner", "status", "location"]),
    ("capa", "CAPA", "refresh-cw", "capa", "CAPA", "title", "owner", "status", ["title", "linked_defect", "root_cause", "corrective_action", "preventive_action", "owner", "status"]),
]
ID_QUERY = re.compile(r"^(PLAN|REV|TC|DEF|DOC|CAPA)[-\s]*0*(\d+)$", re.I)

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()[:80]
    groups, total = [], 0
    if len(q) >= 2:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        m = ID_QUERY.match(q)
        for endpoint, label, icon, table, prefix, title, sub, status, cols in SEARCH_SPEC:
            where = " OR ".join(f"{c} LIKE ? ESCAPE '\\'" for c in cols)
            params = [like] * len(cols)
            if m and m.group(1).upper() == prefix:
                where += " OR id = ?"
                params.append(int(m.group(2)))
            found = rows(f"SELECT id, {title} AS title, {sub} AS sub, {status} AS status FROM {table} WHERE {where} ORDER BY id DESC LIMIT 8", params)
            if found:
                total += len(found)
                groups.append({"endpoint": endpoint, "label": label, "icon": icon, "prefix": prefix, "rows": found})
    return render_template("search.html", page_title="Search", q=q, result_groups=groups, total=total)


# --------------------------------------------------------------------------
# Error pages (no stack traces are shown to users when debug mode is off)
# --------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", page_title="Not found", code=404, message="The requested QMS record or page was not found."), 404

@app.errorhandler(400)
def bad_request(e):
    if getattr(e, "description", "") == "csrf":
        return render_template("error.html", page_title="Security check failed", code=400,
                               message="The form's security token was missing or expired. Reload the page and submit the form again."), 400
    return render_template("error.html", page_title="Invalid request", code=400, message="The submitted value was invalid. Please review the form and try again."), 400

@app.errorhandler(405)
def method_not_allowed(_):
    return render_template("error.html", page_title="Method not allowed", code=405, message="That action isn't available at this address."), 405

@app.errorhandler(413)
def too_large(_):
    return render_template("error.html", page_title="Request too large", code=413, message="The submitted form was larger than this prototype accepts."), 413

@app.errorhandler(500)
def server_error(_):
    return render_template("error.html", page_title="Something went wrong", code=500,
                           message="The QMS hit an unexpected error. Your records were not changed by this page load. Check the terminal for details."), 500

init_db()

if __name__ == "__main__":
    # Debug mode is OFF unless you opt in (set FLASK_DEBUG=1 while developing).
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
