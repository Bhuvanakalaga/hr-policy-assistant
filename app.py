import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage
from agent import run_agent
import employee_db
import confirmation_manager

st.set_page_config(
    page_title="HR Policy Assistant",
    page_icon="🏢",
    layout="centered",
)


# Session state init

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []   # LangChain message objects for agent memory

if "messages" not in st.session_state:
    st.session_state.messages = []


# Login page

def show_login():
    st.title("🏢 HR Policy Assistant")
    st.subheader("Login")

    st.info(
        "**Demo accounts**\n\n"
        "- `employee1` / `password123`\n"
        "- `employee2` / `password123`\n"
        "- `employee3` / `password123`"
    )

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log In")

    if submitted:
        record = employee_db.get_employee_by_username(username.strip())

        if record and record.get("password") == password:
            emp_id = record["emp_id"]

            st.session_state.logged_in = True
            st.session_state.employee_id = emp_id
            st.session_state.employee_name = record["full_name"]
            st.session_state.department = record["department"]
            st.session_state.role = record["designation"]
            st.rerun()
        else:
            st.error("Invalid username or password.")


# Main chat app

def show_chat():
    st.title("🏢 HR Policy Assistant")
    st.caption(
        f"Welcome, {st.session_state.employee_name} "
        f"({st.session_state.department} - {st.session_state.role})"
    )
    st.divider()

    # Render existing messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("tools_used"):
                tools_str = " · ".join(f"`{t}`" for t in msg["tools_used"])
                st.caption(f"🛠️ Tools used: {tools_str}")

    # Chat input
    user_input = st.chat_input("Ask about policies, your profile, leave, tickets, or grievances…")

    if user_input:

        with st.chat_message("user"):
            st.markdown(user_input)

        st.session_state.messages.append({
            "role": "user",
            "content": user_input,
        })

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                response = run_agent(
                    user_input=user_input,
                    chat_history=st.session_state.chat_history,
                    employee_id=st.session_state.employee_id,
                )

            answer     = response["answer"]
            tools_used = response["tools_used"]

            st.markdown(answer)
            if tools_used:
                tools_str = " · ".join(f"`{t}`" for t in tools_used)
                st.caption(f"🛠️ Tools used: {tools_str}")

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "tools_used": tools_used,
        })

        # Update LangChain memory
        st.session_state.chat_history.append(HumanMessage(content=user_input))
        st.session_state.chat_history.append(AIMessage(content=answer))

    # Sidebar
    with st.sidebar:
        st.header("Account")
        st.markdown(f"**Name:** {st.session_state.employee_name}")
        st.markdown(f"**Employee ID:** {st.session_state.employee_id}")
        st.markdown(f"**Department:** {st.session_state.department}")
        st.markdown(f"**Designation:** {st.session_state.role}")

        st.divider()

        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.messages     = []
            confirmation_manager.clear_pending()
            st.rerun()

        if st.button("🚪 Log Out", use_container_width=True):
            confirmation_manager.clear_pending()
            for key in ["logged_in", "employee_id", "employee_name", "department",
                        "role", "chat_history", "messages"]:
                st.session_state.pop(key, None)
            st.rerun()

        st.divider()
        st.markdown("**What you can ask:**")
        st.markdown(
            "- What is the work-from-home (WFH) policy?\n"
            "- How many leave days do I have remaining?\n"
            "-  I want to apply for leave from today until next Friday\n"
            "- My salary has not been credited.\n"
            "-Show my profile details\n"
            "-Check the status of my ticket.\n"
            "- Show my leave history.\n"
            "- I am resigning today. Can I adjust my leave balance against my notice period?\n"
            "- Show my open HR tickets.\n"
            "- My manager is harassing me. I want to file a grievance"
        )


# Router

if not st.session_state.logged_in:
    show_login()
else:
    show_chat()