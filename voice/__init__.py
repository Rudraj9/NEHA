"""
voice package initialization.
Exports local text-to-speech engine controls and status functions.
"""

from .tts import (
    speak,
    is_voice_enabled,
    set_voice_enabled,
    get_voice_status,
    stop_speech,
    init_engine,
    set_custom_engine,
)

__all__ = [
    "speak",
    "is_voice_enabled",
    "set_voice_enabled",
    "get_voice_status",
    "stop_speech",
    "init_engine",
    "set_custom_engine",
]
