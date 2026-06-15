import os
import re
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from tools import (
    ALL_TOOLS,
    set_current_employee,
    get_pending_action,
    set_pending_action,
    clear_pending_action,
    create_hr_ticket,
    create_grievance,
)
from prompts import get_system_prompt
from guardrails import check_input
import employee_db

load_dotenv()

MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"

# agent built once per process
_agent = None

# Simple confirmation phrases (case-insensitive, whole message)
_CONFIRMATION_PATTERN = re.compile(
    r"^\s*(yes|yeah|yep|ok|okay|sure|proceed|go ahead|please do|confirm|"
    r"confirmed|do it)\.?\s*$",
    re.IGNORECASE,
)

# Simple keyword lists for classifying the EMPLOYEE'S OWN message as a
# grievance vs a general support request. This is plain application logic
# (not parsing the assistant's reply) and only decides what TYPE of pending
# action to remember when the agent asks for confirmation.
_GRIEVANCE_KEYWORDS = [
    "harass", "bully", "bullying", "discrimina", "retaliat",
    "misconduct", "hostile", "unsafe", "abuse", "abusive",
]


def _is_confirmation(text: str) -> bool:
    return bool(_CONFIRMATION_PATTERN.match(text.strip()))


def _looks_like_grievance(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in _GRIEVANCE_KEYWORDS)


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

    # create_react_agent handles
    # LLM -> tool call -> observe result -> LLM -> ... -> final answer
    # prompt is a callable so the injected "today's date" is always
    # fresh, even across long-running sessions.
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
    Run the LangGraph ReAct agent for one user turn.

    Args:
        user_input   : The employee's message.
        chat_history : Prior conversation messages (LangChain message objects).
        employee_id  : The logged-in employee's ID (e.g. "EMP001"). Automatically
                        used by employee-specific tools - never exposed to the LLM
                        as something it needs to provide.

    Returns:
        answer     : Final response text.
        tools_used : List of tool names that were called.
    """

    # Run guardrails BEFORE the agent is invoked
    is_safe, blocked_response = check_input(user_input)
    if not is_safe:
        employee_db.log_audit_event(
            emp_id=employee_id,
            intent="Intent.BLOCKED",
            query=user_input,
            tools_used=[],
            status="blocked",
        )
        return {
            "answer": blocked_response,
            "tools_used": [],
        }

    # Make the logged-in employee's ID available to employee-specific tools
    set_current_employee(employee_id)

    # Pending-action shortcut: if the employee just confirmed ("yes",
    # "proceed", etc.) and we have a pending ticket/grievance, execute it
    # directly instead of relying on the LLM to re-derive it from history.
    if _is_confirmation(user_input):
        pending = get_pending_action(employee_id)
        if pending:
            action_type = pending["type"]
            issue = pending["issue"]
            clear_pending_action(employee_id)

            if action_type == "ticket":
                answer = create_hr_ticket.invoke({"issue": issue})
                tools_used = ["create_hr_ticket"]
            else:
                answer = create_grievance.invoke({"issue": issue})
                tools_used = ["create_grievance"]

            employee_db.log_audit_event(
                emp_id=employee_id,
                intent=f"Intent.CONFIRMED({action_type})",
                query=user_input,
                tools_used=tools_used,
                status="success",
            )
            return {"answer": answer, "tools_used": tools_used}

    agent = _get_agent()

    # Build message list: history + current user message
    messages = [*chat_history, HumanMessage(content=user_input)]

    try:
        result = agent.invoke({"messages": messages})
    except Exception as e:
        err_str = str(e)

        # The Groq/gpt-oss model occasionally emits narrated, multi-step
        # text instead of a clean tool call, which the API rejects as
        # tool_use_failed. Retry once with a corrective nudge.
        if "tool_use_failed" in err_str:
            nudge = HumanMessage(
                content=(
                    "Reminder: call exactly one tool now, with no "
                    "explanatory text, headings, or step descriptions. "
                    "Do not write out a plan."
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
                        "Could you try rephrasing it, perhaps as a "
                        "simpler, single question?"
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
            return {
                "answer": f"Sorry, I encountered an error: {e}",
                "tools_used": [],
            }

    # The last message in result["messages"] is the final AI response
    final_message = result["messages"][-1]
    answer = final_message.content

    # Collect tool names from all ToolMessage entries in the result
    tools_used = []
    for msg in result["messages"]:
        # LangGraph marks tool call messages with a "name" attribute
        name = getattr(msg, "name", None)
        if name and name not in tools_used:
            tools_used.append(name)

    if "create_hr_ticket" in tools_used or "create_grievance" in tools_used:
        # The LLM completed the action itself - clear any stale pending state.
        clear_pending_action(employee_id)
    elif not tools_used:
        # No tool was called this turn. The agent likely asked for
        # confirmation before raising a ticket or grievance. Remember the
        # employee's own message as the pending action so a follow-up
        # "yes" can be executed directly. The TYPE is decided from the
        # employee's message, not from the assistant's reply.
        action_type = "grievance" if _looks_like_grievance(user_input) else "ticket"
        set_pending_action(employee_id, action_type, user_input)

    # Audit log
    intent = f"Intent.TOOLS({','.join(tools_used)})" if tools_used else "Intent.GENERAL"
    employee_db.log_audit_event(
        emp_id=employee_id,
        intent=intent,
        query=user_input,
        tools_used=tools_used,
        status="success",
    )

    return {
        "answer": answer,
        "tools_used": tools_used,
    }