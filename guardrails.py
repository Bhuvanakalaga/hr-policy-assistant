# guardrails.py
# Pre-agent guardrails for the HR Assistant.
#
# Runs BEFORE the agent is invoked. If a check trips, returns a professional
# HR response and the agent is never called for that turn.

import re

BLOCKED_RESPONSE = (
    "I'm sorry, but I can't help with that request. "
    "I can assist you with HR policies, your profile, leave balance, "
    "tickets, grievances, and leave requests. "
    "Please let me know how I can help with one of these."
)

UNAUTHORIZED_ACCESS_RESPONSE = (
    "For privacy and security reasons, I can only access information "
    "for your own account. I'm not able to look up or share records "
    "for other employees. Let me know if you'd like help with your "
    "own profile, leave balance, tickets, or grievances."
)

# Prompt Injection
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions?",
    r"ignore\s+(the\s+)?system\s+prompt",
    r"forget\s+(your|all|previous)\s+instructions?",
    r"disregard\s+(your|all|previous)\s+instructions?",
    r"act\s+as\s+(an?other|a\s+different)\s+(assistant|ai|model|bot)",
    r"pretend\s+(to\s+be|you\s+are)\s+(an?other|a\s+different)",
    r"you\s+are\s+now\s+(an?other|a\s+different|no\s+longer)",
    r"new\s+instructions?\s*[:\-]",
    r"override\s+(your\s+)?instructions?",
    r"bypass\s+(security|safety|guardrails?|restrictions?|filters?)",
    r"jailbreak",
    r"developer\s+mode",
    r"dan\s+mode",
]

# Prompt Extraction
_EXTRACTION_PATTERNS = [
    r"show\s+(me\s+)?(the\s+)?system\s+prompt",
    r"reveal\s+(your\s+)?(hidden\s+)?(instructions?|system\s+prompt)",
    r"what\s+(are|is)\s+your\s+(system\s+prompt|instructions?)",
    r"print\s+your\s+(system\s+prompt|instructions?)",
    r"reveal\s+(your\s+)?chain\s+of\s+thought",
    r"show\s+(me\s+)?(your\s+)?chain\s+of\s+thought",
    r"show\s+(me\s+)?your\s+(internal\s+)?reasoning",
    r"repeat\s+(the\s+)?(system\s+)?prompt",
]

# Unauthorized Access (other employees / bulk data)
_UNAUTHORIZED_ACCESS_PATTERNS = [
    r"\b(profile|details|info|information|record)s?\s+(of|for)\s+emp\d+",
    r"\bleave\s+balance\s+(of|for)\s+emp\d+",
    r"\b(show|get|fetch|list)\s+all\s+employee",
    r"\ball\s+employee\s+records?",
    r"\bdump\s+(the\s+)?database",
    r"\bdump\s+(all\s+)?(employee|user)?\s*data",
    r"\bexport\s+all\s+employees?",
    r"\bevery\s+employee'?s?\s+(profile|leave|record|data)",
    r"\bemp\d+'?s\s+(profile|leave|salary|details|record)",
]

_ALL_PATTERNS = (
    [(p, "injection") for p in _INJECTION_PATTERNS]
    + [(p, "extraction") for p in _EXTRACTION_PATTERNS]
    + [(p, "unauthorized") for p in _UNAUTHORIZED_ACCESS_PATTERNS]
)

_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), category) for p, category in _ALL_PATTERNS]


def check_input(user_input: str) -> tuple[bool, str | None]:
    """
    Check user input against guardrail rules.

    Returns:
        (is_safe, blocked_response)
        - is_safe = True  -> input may proceed to the agent, blocked_response is None
        - is_safe = False -> input is blocked, blocked_response holds the message to show
    """
    text = user_input.strip()

    for pattern, category in _COMPILED_PATTERNS:
        if pattern.search(text):
            if category == "unauthorized":
                return False, UNAUTHORIZED_ACCESS_RESPONSE
            return False, BLOCKED_RESPONSE

    return True, None