# All LangChain tools for the HR Assistant.
#
# Employee-specific tools automatically use the logged-in employee's ID
# (set via set_current_employee before each agent run). The agent never
# needs to ask for, and the LLM never needs to supply, an employee ID.

from langchain_core.tools import tool
from retriever import search_policy_chunks
import employee_db


# Current employee context

_current_employee_id: str | None = None


def set_current_employee(emp_id: str) -> None:
    """Set the logged-in employee's ID for the current request. Called by agent.py."""
    global _current_employee_id
    _current_employee_id = emp_id


def _get_current_employee_id() -> str:
    if not _current_employee_id:
        raise RuntimeError("No employee is currently logged in.")
    return _current_employee_id


# Pending action state (simple session-based confirmation tracking)
#
# Used so confirmation ("yes" / "ok" / "proceed" / "go ahead") reliably
# triggers the correct create_hr_ticket / create_grievance call without
# relying solely on the LLM remembering what it asked. Keyed by employee_id.
#
# Each pending action is: {"type": "ticket" | "grievance", "issue": str}

_pending_actions: dict[str, dict] = {}


def set_pending_action(emp_id: str, action_type: str, issue: str) -> None:
    """Record a pending action ('ticket' or 'grievance') awaiting confirmation."""
    _pending_actions[emp_id.upper().strip()] = {"type": action_type, "issue": issue}


def get_pending_action(emp_id: str) -> dict | None:
    """Return the pending action for emp_id, or None if there isn't one."""
    return _pending_actions.get(emp_id.upper().strip())


def clear_pending_action(emp_id: str) -> None:
    """Clear any pending action for emp_id."""
    _pending_actions.pop(emp_id.upper().strip(), None)


# 1. search_policy

@tool
def search_policy(query: str) -> str:
    """
    Search the HR policy knowledge base for any policy-related topic.

    Use for:
    - leave policy, WFH policy, attendance policy
    - resignation policy, notice period, exit process
    - benefits, salary, reimbursements, insurance
    - code of conduct, POSH
    - any general "what is our policy on X" question

    Always use this tool to search policy documents before answering any
    policy-related question. Never answer policy questions from memory.

    Input: a natural-language query describing the policy topic, e.g.
    "notice period for resignation", "work from home policy".
    """
    return search_policy_chunks(query, k=4)


# 2. get_employee_profile

@tool
def get_employee_profile(_: str = "") -> str:
    """
    Retrieve the logged-in employee's own profile.

    Use for:
    - "my profile"
    - "my manager" / "manager details" / "reporting manager"
    - "my department"
    - "my designation"
    - "my email" / "my joining date" / "my work location"

    Always use this when the employee asks about their own profile,
    department, designation, manager, joining date, or work location.
    This automatically uses the logged-in employee's ID - never ask for
    an employee ID.

    Input: not required (leave empty).
    """
    emp_id = _get_current_employee_id()
    result = employee_db.get_employee_profile(emp_id)
    if "error" in result:
        return result["error"]
    return "\n".join(f"{k}: {v}" for k, v in result.items())


# 3. get_leave_balance

@tool
def get_leave_balance(_: str = "") -> str:
    """
    Retrieve the logged-in employee's current leave balance.

    Use for:
    - "my leave balance"
    - "remaining leaves"
    - "available leave days"
    - "how many leaves do I have"

    Always use this when leave balance is requested. This automatically
    uses the logged-in employee's ID - never ask for an employee ID.

    Input: not required (leave empty).
    """
    emp_id = _get_current_employee_id()
    result = employee_db.get_leave_balance(emp_id)
    if "error" in result:
        return result["error"]
    return "\n".join(f"{k}: {v}" for k, v in result.items())


# 4. create_hr_ticket

@tool
def create_hr_ticket(issue: str) -> str:
    """
    Create an HR support ticket for the logged-in employee.

    Use ONLY after the employee has explicitly confirmed they want a ticket
    created (e.g. they said "yes", "ok", "proceed", "go ahead").

    Use for:
    - salary certificate requests
    - reimbursement issues
    - payroll problems
    - employment verification letters
    - benefits support
    - general HR service requests

    Do NOT use for harassment, discrimination, bullying, or grievances -
    use create_grievance instead.

    Input: a description of the employee's support request.
    """
    emp_id = _get_current_employee_id()

    is_duplicate, dup_message = employee_db.check_duplicate_ticket(emp_id, issue)
    if is_duplicate:
        clear_pending_action(emp_id)
        return (
            f"I can't create a new ticket for this. {dup_message} "
            f"Please wait for that ticket to be resolved, or let me know "
            f"if this is a different issue."
        )

    result = employee_db.create_ticket(emp_id, issue)
    clear_pending_action(emp_id)
    return (
        f"HR Support Ticket Created\n\n"
        f"Ticket ID    : {result['ticket_id']}\n"
        f"Type         : Support Request\n"
        f"Priority     : {result['priority']}\n"
        f"Status       : {result['status']}\n"
        f"Created At   : {result['created_at']}\n"
        f"Summary      : {issue[:200]}\n\n"
        f"An HR representative will follow up within 2 working days.\n"
        f"Please save your Ticket ID {result['ticket_id']} for reference."
    )


# 5. get_ticket_status

@tool
def get_ticket_status(ticket_id: str) -> str:
    """
    Check the status of a specific HR support ticket raised by the
    logged-in employee.

    Use for:
    - "what is the status of TKT-12345"
    - "check my ticket TKT-12345"
    - "has my ticket been resolved"

    Input: the ticket ID, e.g. "TKT-12345".
    """
    emp_id = _get_current_employee_id()
    result = employee_db.get_ticket_status(emp_id, ticket_id)
    if "error" in result:
        return result["error"]
    return "\n".join(f"{k}: {v}" for k, v in result.items())


# 6. list_my_tickets

@tool
def list_my_tickets(_: str = "") -> str:
    """
    List all HR support tickets raised by the logged-in employee.

    Use for:
    - "show my tickets"
    - "list all my support requests"
    - "what tickets have I raised"

    Input: not required (leave empty).
    """
    emp_id = _get_current_employee_id()
    tickets = employee_db.list_tickets(emp_id)
    if not tickets:
        return "You have not raised any HR support tickets."

    lines = []
    for t in tickets:
        lines.append(
            f"- {t.get('ticket_id')} | Category: {t.get('category')} | "
            f"Status: {t.get('status')} | Priority: {t.get('priority')} | "
            f"Created: {t.get('created_at')} | Description: {t.get('description')}"
        )
    return "\n".join(lines)


# 7. create_grievance

@tool
def create_grievance(issue: str) -> str:
    """
    Escalate a formal HR grievance for the logged-in employee.

    Use ONLY after the employee has explicitly confirmed they want to
    escalate (e.g. they said "yes", "ok", "proceed", "go ahead").

    Use for:
    - harassment, sexual harassment
    - bullying, discrimination, retaliation
    - manager misconduct, ethics complaints
    - hostile work environment, unsafe workplace

    Do NOT use for general service requests - use create_hr_ticket instead.

    Input: a description of the grievance or complaint.
    """
    emp_id = _get_current_employee_id()

    is_duplicate, dup_message = employee_db.check_duplicate_grievance(emp_id, issue)
    if is_duplicate:
        clear_pending_action(emp_id)
        return (
            f"I can't escalate this as a new grievance. {dup_message} "
            f"It is already being handled. Please let me know if this is a "
            f"different matter."
        )

    result = employee_db.create_grievance_record(emp_id, issue)
    clear_pending_action(emp_id)
    return (
        f"Formal HR Grievance Escalated\n\n"
        f"Case ID      : {result['case_id']}\n"
        f"Type         : Formal Grievance\n"
        f"Priority     : {result['priority']}\n"
        f"Status       : {result['status']}\n"
        f"Created At   : {result['created_at']}\n"
        f"Summary      : {issue[:200]}\n\n"
        f"This has been flagged as high priority and assigned to a senior HR representative.\n"
        f"You will be contacted within 1 working day. All communications are strictly confidential.\n"
        f"Please save your Case ID {result['case_id']} for reference."
    )


# 8. list_my_grievances

@tool
def list_my_grievances(_: str = "") -> str:
    """
    List all formal HR grievances filed by the logged-in employee.

    Use for:
    - "show my grievances"
    - "list my complaints"
    - "what is the status of my grievance"

    Input: not required (leave empty).
    """
    emp_id = _get_current_employee_id()
    grievances = employee_db.list_grievances(emp_id)
    if not grievances:
        return "You have not filed any HR grievances."

    lines = []
    for g in grievances:
        lines.append(
            f"- {g.get('grievance_id')} | Type: {g.get('grievance_type')} | "
            f"Status: {g.get('status')} | Priority: {g.get('priority')} | "
            f"Created: {g.get('created_at')} | Description: {g.get('description')}"
        )
    return "\n".join(lines)


# 9. create_leave_request

@tool
def create_leave_request(start_date: str, end_date: str, reason: str, leave_type: str = "Casual Leave") -> str:
    """
    Submit a leave request for the logged-in employee.

    Use for:
    - "apply for leave"
    - "I want to take leave from X to Y"
    - "request annual leave / sick leave / casual leave / maternity leave"

    Input:
    - start_date: leave start date, e.g. "2026-07-01"
    - end_date: leave end date, e.g. "2026-07-05"
    - reason: brief reason for the leave
    - leave_type: type of leave, e.g. "Casual Leave", "Sick Leave",
      "Annual Leave", "Maternity Leave", "Paternity Leave" (default "Casual Leave")

    This tool performs its own validation (dates, leave balance, overlapping
    requests) BEFORE creating any record. If validation fails, NO record is
    created and a clear message is returned - report that message to the
    employee as-is and do not call this tool again for the same request
    unless the employee gives new dates/details or explicitly confirms they
    want to proceed anyway.
    """
    emp_id = _get_current_employee_id()

    # 1. Validate dates (presence, format, end >= start)
    is_valid, date_error, total_days = employee_db.validate_leave_dates(start_date, end_date)
    if not is_valid:
        return f"I couldn't submit this leave request: {date_error}"

    # 2. Validate against available leave balance
    balance = employee_db.get_leave_balance_days(emp_id)
    if balance is not None and total_days > balance:
        return (
            f"Your available leave balance is {balance} days, but the "
            f"requested leave is {total_days} days. This request exceeds "
            f"your available balance, so I can't submit it. Please choose "
            f"fewer days, or contact HR if you believe this needs special "
            f"approval."
        )

    # 3. Check for overlapping Pending/Approved leave requests
    has_overlap, overlap_message = employee_db.check_overlapping_leave(emp_id, start_date, end_date)
    if has_overlap:
        return f"I couldn't submit this leave request: {overlap_message}"

    # All validations passed - create the record
    result = employee_db.create_leave_request(emp_id, start_date, end_date, reason, leave_type)
    return (
        f"Leave Request Submitted\n\n"
        f"Request ID   : {result['request_id']}\n"
        f"Leave Type   : {result['leave_type']}\n"
        f"Start Date   : {result['start_date']}\n"
        f"End Date     : {result['end_date']}\n"
        f"Total Days   : {result['total_days']}\n"
        f"Status       : {result['status']}\n"
        f"Applied At   : {result['applied_at']}\n\n"
        f"Your manager will review this request shortly."
    )


# 10. get_leave_history

@tool
def get_leave_history(_: str = "") -> str:
    """
    Retrieve the logged-in employee's leave request history.

    Use for:
    - "show my leave history"
    - "my past leave requests"
    - "what leaves have I applied for"

    Input: not required (leave empty).
    """
    emp_id = _get_current_employee_id()
    history = employee_db.get_leave_history(emp_id)
    if not history:
        return "You have no leave request history."

    lines = []
    for h in history:
        lines.append(
            f"- {h.get('request_id')} | {h.get('leave_type')} | "
            f"{h.get('start_date')} to {h.get('end_date')} ({h.get('total_days')} days) | "
            f"Status: {h.get('status')} | Applied: {h.get('applied_at')}"
        )
    return "\n".join(lines)


# 11. hr_contact

@tool
def hr_contact(query: str = "contact") -> str:
    """
    Provide HR department contact details.

    Use for:
    - "how do I contact HR"
    - "HR email" / "HR phone number"
    - "who do I reach out to in HR"

    Do NOT create tickets when this tool is used.
    """
    return (
        "HR Department Contact Details\n\n"
        "Email        : hr@company.com\n"
        "Phone        : +91-XXXXXXXXXX\n"
        "HR Helpdesk  : Available on the HRMS portal\n"
        "Working Hours: Monday - Friday, 9:00 AM - 6:00 PM\n\n"
        "For urgent matters, email hr@company.com with URGENT in the subject line."
    )


# Export

ALL_TOOLS = [
    search_policy,
    get_employee_profile,
    get_leave_balance,
    create_hr_ticket,
    get_ticket_status,
    list_my_tickets,
    create_grievance,
    list_my_grievances,
    create_leave_request,
    get_leave_history,
    hr_contact,
]