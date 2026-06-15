import os
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from tools import ALL_TOOLS, set_current_employee
from prompts import get_system_prompt
from guardrails import check_input
import employee_db

load_dotenv()

MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"

# agent built once per process
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

    # create_react_agent handles
    # LLM -> tool call -> observe result -> LLM -> ... -> final answer
    # state_modifier is a callable so the injected "today's date" is always
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
            except Exception as e2:
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