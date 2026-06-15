# validators.py

import re


def validate_user_input(question: str):

    # Empty input
    if not question.strip():
        return False, "Please enter a valid question."

    # Exit
    if question.lower() == "exit":
        return False, "exit"

    # Greetings
    if question.lower() in ["hi", "hello", "hey"]:
        return False, "Hello! How can I help you today?"

    # Very long input
    if len(question) > 500:
        return False, (
            "Question is too long. "
            "Please keep it under 500 characters."
        )

    # Numbers only
    if question.isdigit():
        return False, (
            "Please enter a meaningful "
            "policy-related question."
        )

    # Special characters only
    if not re.search(r"[a-zA-Z]", question):
        return False, (
            "Please enter a meaningful question."
        )

    return True, None