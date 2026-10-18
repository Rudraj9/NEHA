"""
assistant package initialization.
Exports personality constants and brain interface functions.
"""

from .personality import (
    ASSISTANT_NAME,
    USER_NAME,
    WELCOME_MESSAGE,
    PERSONALITY_DESCRIPTION,
    SYSTEM_PROMPT,
)
from .brain import (
    get_response,
    clear_history,
    get_history,
    validate_credentials,
    get_configured_model,
    set_client,
    is_error_response,
)

__all__ = [
    "ASSISTANT_NAME",
    "USER_NAME",
    "WELCOME_MESSAGE",
    "PERSONALITY_DESCRIPTION",
    "SYSTEM_PROMPT",
    "get_response",
    "clear_history",
    "get_history",
    "validate_credentials",
    "get_configured_model",
    "set_client",
    "is_error_response",
]
