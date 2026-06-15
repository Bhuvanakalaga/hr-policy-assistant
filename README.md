# HR Policy Assistant

A production-inspired HR chatbot built with **Python**, **Streamlit**, **LangGraph**, **LangChain**, **FAISS**, **SQLite**, and **Groq**.

---

## Features

| Feature | Details |
|---|---|
| **Login & Auth** | Streamlit login page with session management |
| **SQLite Database** | All data stored in `hr.db` (employees, tickets, grievances, leave_requests) |
| **RAG Pipeline** | `policy.txt` → chunked → FAISS index → top-k retrieval |
| **LangGraph ReAct Agent** | Multi-step tool calling with conversation memory |
| **11 LangChain Tools** | See tool list below |
| **Multi-Tool Reasoning** | Handles complex queries requiring multiple tools |
| **Guardrails** | Blocks prompt injection, data dumping, unauthorised access |
| **Validators** | Input validation before guardrails |
| **Pre-Tool Checks** | Auth + parameter validation before each tool runs |
| **Post-Tool Checks** | Output sanitisation, error to friendly message conversion |
| **Confirmation Manager** | Ask before creating tickets or grievances |
| **Audit Logging** | Every interaction logged to `data/audit_logs.csv` |

---

## Tools (11 Total)

| Tool | Purpose |
|---|---|
| `search_policy` | RAG search over HR policy document |
| `get_employee_profile` | Logged-in employee profile |
| `get_leave_balance` | Logged-in employee leave balance |
| `create_hr_ticket` | Create HR support ticket (after confirmation) |
| `get_ticket_status` | Status of a specific ticket |
| `list_my_tickets` | All tickets for logged-in employee |
| `create_grievance` | Formal grievance escalation (after confirmation) |
| `list_my_grievances` | All grievances for logged-in employee |
| `hr_contact` | HR department contact details |
| `create_leave_request` | Apply for leave |
| `get_leave_history` | Past leave requests |

---

## Project Structure

```
hr_assistant/
├── app.py                  # Streamlit UI (login + chat)
├── agent.py                # LangGraph ReAct agent
├── tools.py                # All 11 LangChain tools (SQLite-backed)
├── prompts.py              # Dynamic system prompt with employee context
├── retriever.py            # FAISS vector store (RAG)
├── employee_db.py          # Employee DB queries (SQLite)
├── database.py             # SQLite schema creation
├── import_data.py          # CSV → SQLite importer
├── create_vector_db.py     # One-time FAISS index builder
├── validators.py           # Input validation
├── guardrails.py           # Injection / access control
├── pre_tool_checks.py      # Pre-execution checks
├── post_tool_checks.py     # Output sanitisation
├── confirmation_manager.py # Confirmation workflow state
├── audit_logger.py         # Audit logging to CSV
├── .env
│
└── data/
    ├── policy.txt
    ├── employees.csv
    ├── tickets.csv
    ├── grievances.csv
    ├── leave_requests.csv
    ├── audit_logs.csv
    ├── hr.db               # Created by import_data.py
    └── faiss_index/        # Created by create_vector_db.py
```

---

## Setup

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

### 2. Add Groq API key

```
# .env
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Create the SQLite database

```bash
python import_data.py
```

### 4. Build the FAISS vector index

```bash
python create_vector_db.py
```

### 5. Run the app

```bash
streamlit run app.py
```

---

## Demo Accounts

| Username | Password | Employee |
|---|---|---|
| employee1 | password123 | Ankit Mehta (EMP001) |
| employee2 | password123 | Jyoti Sethi (EMP002) |
| employee3 | password123 | EMP003 |

---

## Architecture

```
User Input
    ↓
Validators        (validators.py)
    ↓
Guardrails        (guardrails.py)
    ↓
Confirmation Mgr  (confirmation_manager.py)
    ↓
LangGraph Agent   (agent.py)
    ↓
Tools             (tools.py)
    ↓
Pre-Tool Checks   (pre_tool_checks.py)
    ↓
SQLite / FAISS    (database.py / retriever.py)
    ↓
Post-Tool Checks  (post_tool_checks.py)
    ↓
Audit Logger      (audit_logger.py)
    ↓
Response → Streamlit UI
```

---

## Multi-Tool Reasoning Example

**Query:** "I want to resign. Tell me my notice period, leave balance, manager details, and exit process."

**Agent calls:**
1. `search_policy` → notice period + exit process policy
2. `get_employee_profile` → manager details
3. `get_leave_balance` → remaining leave days

**Result:** One combined, coherent answer.

---

## Tech Stack

- Python 3.10+, Streamlit, LangChain, LangGraph, LangChain-Groq
- FAISS, HuggingFace Embeddings (`all-MiniLM-L6-v2`)
- SQLite, Groq (`llama-3.3-70b-versatile`), python-dotenv