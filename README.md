# HR Policy Assistant

A conversational HR chatbot built with **Python**, **Streamlit**, **LangGraph**, **LangChain**, **FAISS**, **HuggingFace Embeddings**, **SQLite**, and **Groq**.

---

## Features

| Feature | Details |
|---|---|
| Login | Data-driven login from `employees.csv`; chatbot auto-knows the logged-in employee |
| RAG Pipeline | Chunks `policy.txt` → embeds with `all-MiniLM-L6-v2` → FAISS → top-k retrieval |
| Guardrails | Blocks prompt injection, extraction, unauthorized access, and jailbreak attempts |
| 11 LangChain Tools | See Tools section below |
| Leave Validation | Date range, leave balance, and overlap checks before any record is created |
| Duplicate Prevention | Blocks duplicate open tickets and active grievances |
| Confirmation Flow | Deterministic application-driven confirmation via `confirmation_manager.py` |
| Audit Logging | Every turn logged to `audit_logs` table in `hr.db` |
| Dynamic Date | Today's date injected into system prompt on every request |
| LLM | `openai/gpt-oss-120b` via Groq API |

---

## Project Structure

```
hr_assistant/
├── app.py                    # Streamlit UI: login + chat
├── agent.py                  # LangGraph ReAct agent + confirmation flow
├── tools.py                  # 11 LangChain tools
├── confirmation_manager.py   # Ticket/grievance confirmation state (st.session_state)
├── guardrails.py             # Pre-agent input safety checks
├── prompts.py                # Dynamic system prompt (date-injected)
├── employee_db.py            # All database read/write + validation helpers
├── database.py               # SQLite connection helper
├── retriever.py              # FAISS vector store loader and search
├── create_vector_db.py       # One-time script: builds FAISS index from policy.txt
├── import_data.py            # One-time script: imports CSVs into hr.db
├── validators.py             # Basic input validation helpers
├── requirements.txt
├── .env
│
└── data/
    ├── policy.txt            # HR policy document (source for RAG)
    ├── employees.csv         # Employee master (source of truth)
    ├── tickets.csv           # HR support tickets
    ├── leave_requests.csv    # Leave requests
    ├── grievances.csv        # Formal grievances
    ├── audit_logs.csv        # Audit log seed data
    ├── hr.db                 # SQLite database (built by import_data.py)
    └── faiss_index/          # FAISS index (built by create_vector_db.py)
```

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Add your Groq API key
```
# .env
GROQ_API_KEY=your_actual_key_here
```
Get a free key at https://console.groq.com

### 3. Build the SQLite database
```bash
python import_data.py
```
Reads your existing CSV files from `data/` into `hr.db`. Re-run whenever CSVs change.

### 4. Build the FAISS vector index
```bash
python create_vector_db.py
```
Reads `data/policy.txt`, creates chunks, embeds them, and saves to `data/faiss_index/`. Re-run whenever `policy.txt` changes.

### 5. Start the app
```bash
streamlit run app.py
```

---

## Login

Credentials are read from `employees.csv` (`username` / `password` columns).

| Username | Password | Employee |
|---|---|---|
| `employee1` | `password123` | EMP001 |
| `employee2` | `password123` | EMP002 |
| `employee3` | `password123` | EMP003 |

After login the chatbot automatically knows the employee's ID, name, department, and designation. It never asks for an employee ID.

---

## Tools

| Tool | Purpose |
|---|---|
| `search_policy` | RAG search over `policy.txt` |
| `get_employee_profile` | Profile, manager, department, designation |
| `get_leave_balance` | Available leave days |
| `create_hr_ticket` | Initiates ticket request → sets pending confirmation |
| `get_ticket_status` | Status of a specific ticket |
| `list_my_tickets` | All tickets for the logged-in employee |
| `create_grievance` | Initiates grievance → sets pending confirmation |
| `list_my_grievances` | All grievances for the logged-in employee |
| `create_leave_request` | Submits leave with full validation |
| `get_leave_history` | Past leave requests |
| `hr_contact` | HR email, phone, helpdesk |

---

## Confirmation Flow

Ticket and grievance creation use a **deterministic, application-driven confirmation flow** — the system never inspects or parses the LLM's own generated text to determine workflow state.

```
Employee: "I need a salary certificate."
    │
    ▼
LLM calls create_hr_ticket("salary certificate request")
    │
    ▼
create_hr_ticket checks for duplicates
  → if duplicate: returns error message, no record created
  → if clean: calls confirmation_manager.set_pending("ticket", issue)
              returns "I can create an HR support ticket for this.
                       Would you like me to proceed?"
    │
    ▼                               ▼
Employee: "yes" / "ok" / ...     Employee: "no" / "cancel" / ...
    │                               │
    ▼                               ▼
agent.py reads confirmation_manager.get_pending()
Calls _execute_ticket_creation(issue)    confirmation_manager.clear_pending()
Creates ticket in hr.db                 Returns cancellation message
confirmation_manager.clear_pending()
Returns ticket details
```

The same flow applies to `create_grievance` / `_execute_grievance_creation`.

`confirmation_manager.py` stores state in `st.session_state["pending_action"]`, scoped to the logged-in user's browser session.

---

## Leave Request Validation

`create_leave_request` runs three checks in order before writing any record:

1. **Date validation** — both dates present, valid `YYYY-MM-DD` format, end date ≥ start date.
2. **Balance check** — requested days must not exceed available leave balance.
3. **Overlap check** — no existing Pending or Approved leave request can overlap the requested range.

If any check fails, a clear message is returned and **no database record is created**.

---

## Guardrails

`guardrails.py` runs before every agent invocation and blocks:

- **Prompt injection** — "ignore previous instructions", "act as another assistant", etc.
- **Prompt extraction** — "show system prompt", "reveal chain of thought", etc.
- **Unauthorized access** — "show profile of EMP001", "dump the database", etc.
- **Jailbreak** — "override instructions", "bypass security", "developer mode", etc.

---

## Architecture

```
Streamlit UI (app.py)
        │
        ▼
confirmation_manager.py   ←── is this a confirmation/denial for a pending action?
        │  YES → execute directly (agent never invoked)
        │  NO  ↓
        ▼
guardrails.py             ←── block unsafe input before agent runs
        │
        ▼
agent.py → LangGraph ReAct → Groq LLM
        │                         │
        │                    picks tool(s)
        │
        ├── search_policy         → FAISS (retriever.py)
        ├── get_employee_profile  → employees.csv
        ├── get_leave_balance     → employees.csv
        ├── create_leave_request  → validates → hr.db: leave_requests
        ├── get_leave_history     → hr.db: leave_requests
        ├── create_hr_ticket      → duplicate check → set_pending → confirmation Q
        ├── get_ticket_status     → hr.db: tickets
        ├── list_my_tickets       → hr.db: tickets
        ├── create_grievance      → duplicate check → set_pending → confirmation Q
        ├── list_my_grievances    → hr.db: grievances
        └── hr_contact            → static contact info
        │
        ▼
audit_logs table (hr.db)  ←── every turn logged
```

---

## Tech Stack

- **Python 3.10+**
- **Streamlit** — Chat UI with login
- **LangGraph** — ReAct agent orchestration
- **LangChain + LangChain Groq** — Tool framework and LLM integration
- **FAISS** — Vector similarity search
- **HuggingFace Embeddings** — `sentence-transformers/all-MiniLM-L6-v2`
- **SQLite** — Tickets, grievances, leave requests, audit logs
- **Groq** — Fast LLM inference

---

## Notes

- All employee data comes from your existing CSV files — none are generated.
- Policy answers are grounded in `data/policy.txt` — the LLM never invents policy content.
- Re-run `import_data.py` whenever your CSV files change.
- Re-run `create_vector_db.py` whenever `policy.txt` changes.
- `hr.db` is derived from the CSVs; your CSVs remain the source of truth.