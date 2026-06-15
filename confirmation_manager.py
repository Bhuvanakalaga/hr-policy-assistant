"""
confirmation_manager.py
Tracks whether a ticket / grievance creation is waiting for user confirmation.
State is stored in Streamlit session_state under the key "pending_action".

pending_action = {
    "type": "ticket" | "grievance",
    "issue": "<original issue description>"
}
"""

import streamlit as st

# Words the user might say to confirm
_CONFIRM_WORDS = {
    "yes", "yeah", "yep", "yup", "ok", "okay", "sure",
    "proceed", "go ahead", "please do", "do it", "confirm",
    "alright", "of course", "absolutely", "create it", "raise it",
}

_DENY_WORDS = {
    "no", "nope", "cancel", "stop", "don't", "do not", "never mind",
    "forget it", "skip it",
}


def set_pending(action_type: str, issue: str):
    """Store a pending action awaiting confirmation."""
    st.session_state["pending_action"] = {
        "type": action_type,   # "ticket" or "grievance"
        "issue": issue,
    }


def get_pending() -> dict | None:
    return st.session_state.get("pending_action")


def clear_pending():
    st.session_state.pop("pending_action", None)


def is_confirmation(text: str) -> bool:
    return text.lower().strip().rstrip("!.") in _CONFIRM_WORDS


def is_denial(text: str) -> bool:
    return text.lower().strip().rstrip("!.") in _DENY_WORDS