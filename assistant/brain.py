"""
assistant/brain.py
------------------
NEHA ka central intelligence aur conversation engine, powered by the official Groq Python SDK.

Features:
- Configurable model using GROQ_MODEL (default: llama-3.3-70b-versatile).
- Session conversation history in memory with bounded recent turns.
- System prompt preservation for personality and behavioral boundaries.
- Graceful error handling for authentication, rate limits, timeouts, and network issues.
- Clean isolation: Failed requests never leave incomplete turns in conversation history.
- Reset support via clear_history().
"""

import os
from typing import Any, List, Dict, Optional, Tuple
from dotenv import load_dotenv

# Official Groq SDK imports
from groq import (
    Groq,
    APIConnectionError,
    APIStatusError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
)

from .personality import SYSTEM_PROMPT

# Load environment variables from local .env file (if present)
load_dotenv()

# Configuration constants
DEFAULT_MODEL: str = "llama-3.3-70b-versatile"
DEFAULT_TIMEOUT: float = 30.0  # seconds
DEFAULT_MAX_RETRIES: int = 2
DEFAULT_MAX_TURNS: int = 10  # 10 turns = 10 user + 10 assistant messages

# In-memory session history (list of role/content dicts)
# System prompt is prepended dynamically so it is always preserved.
_conversation_history: List[Dict[str, str]] = []

# Optional custom client for testing/mocking
_custom_client: Optional[Any] = None


def get_configured_model() -> str:
    """Returns the configured model name from environment or default."""
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_max_turns() -> int:
    """Returns the maximum conversation turns to keep in memory."""
    try:
        val = int(os.environ.get("MAX_CONVERSATION_TURNS", str(DEFAULT_MAX_TURNS)))
        return max(1, val)
    except ValueError:
        return DEFAULT_MAX_TURNS


def set_client(client: Optional[Any]) -> None:
    """Sets a custom/mock client (primarily used for automated verification)."""
    global _custom_client
    _custom_client = client


def get_client() -> Groq:
    """
    Initializes and returns the Groq client.
    Uses custom client if provided, otherwise creates official Groq client.
    """
    if _custom_client is not None:
        return _custom_client

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    return Groq(
        api_key=api_key,
        timeout=DEFAULT_TIMEOUT,
        max_retries=DEFAULT_MAX_RETRIES,
    )


def validate_credentials() -> Tuple[bool, str]:
    """
    Checks if a valid-looking GROQ_API_KEY is present in the environment.

    Returns:
        (is_valid, message): Boolean flag and guidance string.
    """
    api_key = os.environ.get("GROQ_API_KEY", "").strip()

    if not api_key:
        return False, (
            "GROQ_API_KEY environment variable nahi mili!\n"
            "Kaise configure karein:\n"
            "  1. Groq Console se free API key lein: https://console.groq.com/keys\n"
            "  2. Project folder mein '.env' file banayein (.env.example ko copy karke):\n"
            "     Copy-Item .env.example .env\n"
            "  3. '.env' file ke andar GROQ_API_KEY=gsk_your_key_here likhein.\n"
            "Dhyan rahe: Apni real key chat mein na daalein aur Git par commit na karein!"
        )

    if "your_groq_api_key_here" in api_key.lower():
        return False, (
            "GROQ_API_KEY abhi bhi placeholder value par set hai!\n"
            "Kripya '.env' file kholein aur 'gsk_your_groq_api_key_here' ki jagah apni\n"
            "actual Groq API key (https://console.groq.com/keys) daalein."
        )

    return True, "Credentials found."


def clear_history() -> None:
    """Resets all conversation turns while retaining system prompt."""
    global _conversation_history
    _conversation_history.clear()


def get_history() -> List[Dict[str, str]]:
    """Returns a copy of the current conversation history turns."""
    return list(_conversation_history)


def _trim_history() -> None:
    """Ensures conversation history does not exceed MAX_CONVERSATION_TURNS pairs."""
    global _conversation_history
    max_messages = get_max_turns() * 2  # user + assistant pair per turn
    if len(_conversation_history) > max_messages:
        _conversation_history = _conversation_history[-max_messages:]


def get_response(message: str) -> str:
    """
    Sends the user message along with session history to Groq and returns the response.

    Guarantees:
    - Retains system prompt at index 0.
    - Sends recent conversation history for multi-turn context.
    - Bounded history (trims oldest turns when limit is reached).
    - If the API call fails, the turn is NOT added to history (no corrupt/half turns).
    - Clear, friendly error messages without sensitive credential leakage.
    """
    clean_message = message.strip()
    if not clean_message:
        return ""

    # Construct messages payload: System prompt + historical turns + new user message
    messages_payload: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    messages_payload.extend(_conversation_history)
    messages_payload.append({"role": "user", "content": clean_message})

    model_name = get_configured_model()

    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages_payload,
        )

        reply_text = completion.choices[0].message.content or ""
        reply_clean = reply_text.strip()

        # SUCCESS: Only now commit the complete turn to session history
        _conversation_history.append({"role": "user", "content": clean_message})
        _conversation_history.append({"role": "assistant", "content": reply_clean})
        _trim_history()

        return reply_clean

    except AuthenticationError:
        # Invalid API Key or Unauthorized
        return (
            "[Authentication Error]: Groq API key invalid ya unauthorized hai.\n"
            "Kripya apni key verify karein: https://console.groq.com/keys\n"
            "Aur '.env' file mein GROQ_API_KEY check karein."
        )

    except RateLimitError:
        # Rate limit hit (RPM / TPM exceeded)
        return (
            "[Rate Limit Notice]: Groq API ki rate limit reach ho gayi hai.\n"
            "Kripya kuch seconds wait karein aur dobara apna message bhejein."
        )

    except NotFoundError:
        # Model not found or deprecated
        return (
            f"[Model Error]: Configured model '{model_name}' Groq par nahi mila ya unavailable hai.\n"
            "Kripya '.env' mein GROQ_MODEL ko check karein (e.g., llama-3.3-70b-versatile ya llama-3.1-8b-instant)."
        )

    except APIConnectionError:
        # Network unreachable, DNS failure, or request timeout
        return (
            "[Network/Timeout Error]: Groq server se connect nahi ho paya ya request timeout ho gayi.\n"
            "Kripya apna internet connection check karein aur dobara try karein."
        )

    except APIStatusError as e:
        # HTTP status code errors (4xx / 5xx)
        return (
            f"[API Error]: Groq service ne error return kiya (Status {e.status_code}).\n"
            "Kripya thodi der baad dobara koshish karein."
        )

    except Exception as e:
        # Unexpected errors (without leaking sensitive data)
        return (
            f"[Unexpected Error]: Ek unexpected issue aaya: {type(e).__name__}.\n"
            "Aap naya message bhej kar dobara try kar sakte hain."
        )


ERROR_PREFIXES: Tuple[str, ...] = (
    "[Authentication Error]",
    "[Rate Limit Notice]",
    "[Model Error]",
    "[Network/Timeout Error]",
    "[API Error]",
    "[Unexpected Error]",
)


def is_error_response(response: str) -> bool:
    """
    Checks if a response string represents an error or failure notice.
    Used to prevent speaking errors or secret-containing messages aloud.
    """
    if not response:
        return True
    trimmed = response.strip()
    return any(trimmed.startswith(prefix) for prefix in ERROR_PREFIXES)

