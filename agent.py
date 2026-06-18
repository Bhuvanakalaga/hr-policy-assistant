import os
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from tools import ALL_TOOLS, set_current_employee, _execute_ticket_creation, _execute_grievance_creation
from prompts import get_system_prompt
from guardrails import check_input
import confirmation_manager
import employee_db

load_dotenv()

MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"

# Agent built once per process
_agent = None


def _get_agent():
    global _agent
    if _agent is not None:
        return _agent

    llm = ChatGroq(
        model=MODEL_NAME,
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0,
        max_tokens=1024,
    )

    # prompt is a callable so today's date is always current,
    # even across long-running Streamlit sessions.
    _agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=lambda state: [
            {"role": "system", "content": get_system_prompt()},
            *state["messages"],
        ],
    )

    print("[Agent] LangGraph ReAct agent initialised.")
    return _agent


def run_agent(user_input: str, chat_history: list, employee_id: str) -> dict:
    """
    Run one user turn.

    Args:
        user_input   : The employee's raw message.
        chat_history : Prior LangChain message objects for the session.
        employee_id  : Logged-in employee ID (e.g. "EMP001").

    Returns:
        {"answer": str, "tools_used": list[str]}
    """

    # Guardrails 
    is_safe, blocked_response = check_input(user_input)
    if not is_safe:
        employee_db.log_audit_event(
            emp_id=employee_id,
            intent="Intent.BLOCKED",
            query=user_input,
            tools_used=[],
            status="blocked",
        )
        return {"answer": blocked_response, "tools_used": []}

    # Make logged-in employee available to all tools
    set_current_employee(employee_id)

    # Confirmation flow (driven by confirmation_manager, not LLM text)
    pending = confirmation_manager.get_pending()

    if pending:
        if confirmation_manager.is_confirmation(user_input):
            action_type = pending["type"]
            issue       = pending["issue"]
            confirmation_manager.clear_pending()

            if action_type == "ticket":
                answer     = _execute_ticket_creation(issue)
                tools_used = ["create_hr_ticket"]
            else:
                answer     = _execute_grievance_creation(issue)
                tools_used = ["create_grievance"]

            employee_db.log_audit_event(
                emp_id=employee_id,
                intent=f"Intent.CONFIRMED({action_type})",
                query=user_input,
                tools_used=tools_used,
                status="success",
            )
            return {"answer": answer, "tools_used": tools_used}

        if confirmation_manager.is_denial(user_input):
            confirmation_manager.clear_pending()
            employee_db.log_audit_event(
                emp_id=employee_id,
                intent="Intent.DENIED",
                query=user_input,
                tools_used=[],
                status="cancelled",
            )
            return {
                "answer": "Understood. I've cancelled the request. Let me know if there's anything else I can help you with.",
                "tools_used": [],
            }

    # Agent invocation
    agent    = _get_agent()
    messages = [*chat_history, HumanMessage(content=user_input)]

    try:
        result = agent.invoke({"messages": messages})

    except Exception as e:
        err_str = str(e)

        # Groq rejects responses where the model narrates a plan instead of
        # cleanly calling a tool. Retry once with a corrective nudge.
        if "tool_use_failed" in err_str:
            nudge = HumanMessage(
                content=(
                    "Reminder: call exactly one tool now. "
                    "No explanatory text, headings, or step descriptions."
                )
            )
            try:
                result = agent.invoke({"messages": [*messages, nudge]})
            except Exception:
                employee_db.log_audit_event(
                    emp_id=employee_id,
                    intent="Intent.ERROR",
                    query=user_input,
                    tools_used=[],
                    status="error",
                )
                return {
                    "answer": (
                        "Sorry, I had trouble processing that request. "
                        "Could you try rephrasing it as a single question?"
                    ),
                    "tools_used": [],
                }
        else:
            employee_db.log_audit_event(
                emp_id=employee_id,
                intent="Intent.ERROR",
                query=user_input,
                tools_used=[],
                status="error",
            )
            return {"answer": f"Sorry, I encountered an error: {e}", "tools_used": []}

    # Extract answer and tool names
    answer     = result["messages"][-1].content
    tools_used = []
    for msg in result["messages"]:
        name = getattr(msg, "name", None)
        if name and name not in tools_used:
            tools_used.append(name)

    # Audit log
    intent = f"Intent.TOOLS({','.join(tools_used)})" if tools_used else "Intent.GENERAL"
    employee_db.log_audit_event(
        emp_id=employee_id,
        intent=intent,
        query=user_input,
        tools_used=tools_used,
        status="success",
    )

    return {"answer": answer, "tools_used": tools_used}