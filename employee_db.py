import os
import random
from datetime import datetime

import pandas as pd

from database import get_connection

# Path
CSV_PATH = os.path.join("data", "employees.csv")

_df: pd.DataFrame | None = None


def _get_df() -> pd.DataFrame:
    """Load the employees CSV once and cache it. Return the cached DataFrame."""
    global _df
    if _df is None:
        _df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        # Normalise emp_id to uppercase for case-insensitive lookups
        _df["emp_id"] = _df["emp_id"].str.upper().str.strip()
        print(f"[EmployeeDB] Loaded {len(_df)} employees from {CSV_PATH}")
    return _df


def get_employee_by_username(username: str) -> dict | None:
    """
    Look up an employee by their login username (employees.csv 'username' column).
    Returns the employee row as a dict, or None if not found / no credentials set.
    """
    df = _get_df()
    username = username.strip()
    row = df[(df["username"] == username) & (df["username"] != "")]
    if row.empty:
        return None
    return row.iloc[0].to_dict()

def get_employee_profile(emp_id: str) -> dict:
    """
    Return profile fields for a given employee ID.
    If the employee's manager also exists as an employee record, include
    the manager's email and department too. Only data present in
    employees.csv is used - nothing is invented.
    Returns a dict with employee details, or an error message.
    """
    df = _get_df()
    emp_id = emp_id.upper().strip()
    row = df[df["emp_id"] == emp_id]
    if row.empty:
        return {"error": f"Employee {emp_id} not found."}
    r = row.iloc[0]

    profile = {
        "Employee ID":   r["emp_id"],
        "Name":          r["full_name"],
        "Department":    r["department"],
        "Designation":   r["designation"],
        "Email":         r["email"],
        "Manager":       r["manager_name"],
        "Joining Date":  r["joining_date"],
        "Work Location": r["work_location"],
        "Status":        r["employment_status"],
    }

    # Try to find the manager as an employee record to enrich their details.
    # Only added if found - never fabricated.
    manager_name = r["manager_name"].strip()
    if manager_name:
        manager_row = df[df["full_name"] == manager_name]
        if not manager_row.empty:
            m = manager_row.iloc[0]
            profile["Manager Email"] = m["email"]
            profile["Manager Department"] = m["department"]

    return profile


def get_leave_balance(emp_id: str) -> dict:
    """
    Return leave balance for a given employee ID.
    """
    df = _get_df()
    emp_id = emp_id.upper().strip()
    row = df[df["emp_id"] == emp_id]
    if row.empty:
        return {"error": f"Employee {emp_id} not found."}
    r = row.iloc[0]
    return {
        "Employee ID":   r["emp_id"],
        "Name":          r["full_name"],
        "Leave Balance": r["leave_balance"] + " days",
        "Status":        r["employment_status"],
    }


def get_leave_balance_days(emp_id: str) -> int | None:
    """
    Return the employee's leave balance as an integer number of days,
    or None if the employee or balance value isn't found/valid.
    Used internally for leave-request validation.
    """
    df = _get_df()
    emp_id = emp_id.upper().strip()
    row = df[df["emp_id"] == emp_id]
    if row.empty:
        return None
    raw = row.iloc[0]["leave_balance"]
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return None


def check_overlapping_leave(emp_id: str, start_date: str, end_date: str) -> tuple[bool, str | None]:
    """
    Check whether the given date range overlaps with any existing Pending
    or Approved leave request for emp_id.

    Returns:
        (has_overlap, message)
        - has_overlap=True  -> message describes the conflicting request.
        - has_overlap=False -> message is None.
    """
    emp_id = emp_id.upper().strip()

    try:
        new_start = datetime.strptime(start_date.strip(), "%Y-%m-%d")
        new_end = datetime.strptime(end_date.strip(), "%Y-%m-%d")
    except ValueError:
        # Date format issues are handled by validate_leave_dates separately.
        return False, None

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT request_id, start_date, end_date, status
            FROM leave_requests
            WHERE employee_id = ? AND status IN ('Pending', 'Approved')
            """,
            (emp_id,),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        try:
            existing_start = datetime.strptime(row["start_date"].strip(), "%Y-%m-%d")
            existing_end = datetime.strptime(row["end_date"].strip(), "%Y-%m-%d")
        except (ValueError, AttributeError):
            continue

        # Overlap if ranges intersect
        if new_start <= existing_end and existing_start <= new_end:
            return True, (
                f"This overlaps with your existing {row['status'].lower()} leave "
                f"request {row['request_id']} ({row['start_date']} to {row['end_date']})."
            )

    return False, None


def check_duplicate_ticket(emp_id: str, issue: str) -> tuple[bool, str | None]:
    """
    Check whether emp_id already has an Open or In Review ticket with a
    similar description.

    Returns:
        (is_duplicate, message)
    """
    emp_id = emp_id.upper().strip()
    issue_normalised = issue.strip().lower()

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT ticket_id, description, status
            FROM tickets
            WHERE employee_id = ? AND status IN ('Open', 'In Review')
            """,
            (emp_id,),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        existing = (row["description"] or "").strip().lower()
        if existing and (existing == issue_normalised
                          or existing in issue_normalised
                          or issue_normalised in existing):
            return True, (
                f"You already have an open ticket ({row['ticket_id']}, "
                f"status: {row['status']}) for a similar issue: "
                f"\"{row['description']}\"."
            )

    return False, None


def check_duplicate_grievance(emp_id: str, issue: str) -> tuple[bool, str | None]:
    """
    Check whether emp_id already has a non-Closed grievance with a similar
    description.

    Returns:
        (is_duplicate, message)
    """
    emp_id = emp_id.upper().strip()
    issue_normalised = issue.strip().lower()

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT grievance_id, description, status
            FROM grievances
            WHERE employee_id = ? AND status != 'Closed'
            """,
            (emp_id,),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        existing = (row["description"] or "").strip().lower()
        if existing and (existing == issue_normalised
                          or existing in issue_normalised
                          or issue_normalised in existing):
            return True, (
                f"You already have an active grievance ({row['grievance_id']}, "
                f"status: {row['status']}) for a similar issue: "
                f"\"{row['description']}\"."
            )

    return False, None


# Tickets
# tickets.csv columns: ticket_id, employee_id, category, description, status, priority, created_at

def create_ticket(emp_id: str, issue: str) -> dict:
    """
    Create a support ticket for emp_id and persist it to the tickets table.
    Returns details of the created ticket.
    """
    emp_id = emp_id.upper().strip()
    ticket_id = f"TKT-{random.randint(10000, 99999)}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    category = "General HR Request"

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO tickets (ticket_id, employee_id, category, description, status, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, emp_id, category, issue, "Open", "Normal", timestamp),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ticket_id": ticket_id,
        "status": "Open",
        "priority": "Normal",
        "created_at": timestamp,
    }


def get_ticket_status(emp_id: str, ticket_id: str) -> dict:
    """
    Look up the status of a specific ticket, scoped to emp_id.
    """
    emp_id = emp_id.upper().strip()
    ticket_id = ticket_id.strip().upper()

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM tickets WHERE ticket_id = ? AND employee_id = ?",
            (ticket_id, emp_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"error": f"No ticket {ticket_id} found for your account."}

    return dict(row)


def list_tickets(emp_id: str) -> list[dict]:
    """
    Return all tickets raised by emp_id.
    """
    emp_id = emp_id.upper().strip()

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE employee_id = ? ORDER BY created_at DESC",
            (emp_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


# Grievances
# grievances.csv columns: grievance_id, employee_id, grievance_type, description, status, priority, created_at

def create_grievance_record(emp_id: str, issue: str) -> dict:
    """
    Create a grievance case for emp_id and persist it to the grievances table.
    """
    emp_id = emp_id.upper().strip()
    case_id = f"GRV-{random.randint(10000, 99999)}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    grievance_type = "General Grievance"

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO grievances (grievance_id, employee_id, grievance_type, description, status, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (case_id, emp_id, grievance_type, issue, "Escalated", "High", timestamp),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "case_id": case_id,
        "status": "Escalated",
        "priority": "High",
        "created_at": timestamp,
    }


def list_grievances(emp_id: str) -> list[dict]:
    """
    Return all grievances filed by emp_id.
    """
    emp_id = emp_id.upper().strip()

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM grievances WHERE employee_id = ? ORDER BY created_at DESC",
            (emp_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


# Leave Requests
# leave_requests.csv columns:
# request_id, employee_id, leave_type, start_date, end_date, total_days, status, applied_at

def validate_leave_dates(start_date: str, end_date: str) -> tuple[bool, str | None, int | None]:
    """
    Validate leave request dates.

    Returns:
        (is_valid, error_message, total_days)
        - is_valid=True  -> error_message is None, total_days is the
          inclusive number of days between start_date and end_date.
        - is_valid=False -> error_message explains the problem,
          total_days is None.

    Checks performed:
        - both dates present
        - both dates parseable as YYYY-MM-DD
        - end_date is not earlier than start_date
    """
    if not start_date or not end_date:
        return False, "Both a start date and an end date are required.", None

    try:
        d1 = datetime.strptime(start_date.strip(), "%Y-%m-%d")
    except ValueError:
        return False, f"'{start_date}' is not a valid date. Please use YYYY-MM-DD format.", None

    try:
        d2 = datetime.strptime(end_date.strip(), "%Y-%m-%d")
    except ValueError:
        return False, f"'{end_date}' is not a valid date. Please use YYYY-MM-DD format.", None

    if d2 < d1:
        return False, "End date cannot be earlier than start date.", None

    total_days = (d2 - d1).days + 1
    return True, None, total_days


def create_leave_request(emp_id: str, start_date: str, end_date: str, reason: str,
                          leave_type: str = "Casual Leave") -> dict:
    """
    Create a leave request for emp_id and persist it to the leave_requests table.
    `reason` is stored alongside leave_type in the description-style record.
    `total_days` is computed from start_date/end_date when possible.

    NOTE: This function performs the actual insert. Date validation and
    leave-balance checks are performed in tools.py BEFORE this is called.
    """
    emp_id = emp_id.upper().strip()
    request_id = f"LVR-{random.randint(10000, 99999)}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_days = ""
    try:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = str((d2 - d1).days + 1)
    except ValueError:
        pass

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO leave_requests
                (request_id, employee_id, leave_type, start_date, end_date, total_days, status, applied_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (request_id, emp_id, leave_type, start_date, end_date, total_days, "Pending", timestamp),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "request_id": request_id,
        "leave_type": leave_type,
        "start_date": start_date,
        "end_date": end_date,
        "total_days": total_days,
        "status": "Pending",
        "applied_at": timestamp,
    }


def get_leave_history(emp_id: str) -> list[dict]:
    """
    Return all leave requests filed by emp_id.
    """
    emp_id = emp_id.upper().strip()

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM leave_requests WHERE employee_id = ? ORDER BY applied_at DESC",
            (emp_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


# Audit Logs
# audit_logs.csv columns: timestamp, employee_id, intent, query, tools_used, status

def log_audit_event(emp_id: str, intent: str, query: str, tools_used: list[str], status: str) -> None:
    """
    Append an entry to the audit_logs table.
    Best-effort: failures are silently ignored so they never break the chat flow.
    """
    emp_id = emp_id.upper().strip()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tools_str = ", ".join(tools_used) if tools_used else ""

    try:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO audit_logs (timestamp, employee_id, intent, query, tools_used, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (timestamp, emp_id, intent, query, tools_str, status),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass