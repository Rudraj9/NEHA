"""
voice/tts.py
------------
NEHA Assistant ka local Text-to-Speech (TTS) module.
Windows SAPI5 aur pyttsx3 use karke spoken responses generate karta hai.

Features:
- Windows SAPI5 local engine (Zero API cost, zero network calls).
- Single engine initialization with safe fallback if audio/driver is unavailable.
- Configurable enabled flag (VOICE_ENABLED) and speaking speed (VOICE_RATE).
- Safe dynamic voice selection (uses available installed voices without assuming Hindi or gender).
- Graceful error recovery (audio playback issue aane par bina crash kiye text mode continue karta hai).
- Terminal voice commands support (/voice on, /voice off, /voice status).
- Ctrl+C cleanup support.
"""

import os
import re
from typing import Optional, Any

# Global engine state
_engine: Optional[Any] = None
_init_attempted: bool = False
_engine_available: bool = False
_voice_name: str = "Unknown"
_voice_rate: int = 175

# Default voice enabled status (configurable via env var, defaults to True)
def _get_env_voice_enabled() -> bool:
    val = os.environ.get("VOICE_ENABLED", "true").strip().lower()
    return val in ("true", "1", "yes", "on")

_voice_enabled: bool = _get_env_voice_enabled()


def _clean_text_for_speech(text: str) -> str:
    """
    Cleans markdown formatting, code fences, and symbols to make speech sound natural.
    """
    # Remove code blocks ```...```
    cleaned = re.sub(r"```[\s\S]*?```", " [code block omitted] ", text)
    # Remove inline code `...`
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Remove markdown links [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    # Remove bold/italic markers (* or _)
    cleaned = re.sub(r"[*_~#]", " ", cleaned)
    # Normalize multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def get_configured_rate() -> int:
    """Returns configured voice speed in words per minute."""
    global _voice_rate
    try:
        val = int(os.environ.get("VOICE_RATE", "175").strip())
        _voice_rate = max(100, min(300, val))
    except (ValueError, TypeError):
        _voice_rate = 175
    return _voice_rate


def init_engine() -> bool:
    """
    Initializes the local pyttsx3 speech engine once.
    Safely discovers installed voices and configures speech properties.

    Returns:
        bool: True if engine is ready, False if initialization failed.
    """
    global _engine, _init_attempted, _engine_available, _voice_name

    if _init_attempted:
        return _engine_available

    _init_attempted = True

    try:
        import pyttsx3

        # SAPI5 driver for Windows
        engine = pyttsx3.init()
        rate = get_configured_rate()
        engine.setProperty("rate", rate)

        # Inspect and select an available installed voice
        # We do NOT assume any particular voice, gender, or Hindi pack exists.
        voices = engine.getProperty("voices")
        selected_voice_id = None
        selected_name = "System Default"

        if voices:
            # Prefer female voice like Zira if present, otherwise safely pick first installed voice
            for v in voices:
                v_name = (v.name or "").lower()
                if "zira" in v_name or "female" in v_name:
                    selected_voice_id = v.id
                    selected_name = v.name or "Female Voice"
                    break

            if not selected_voice_id and len(voices) > 0:
                selected_voice_id = voices[0].id
                selected_name = voices[0].name or "Default Voice"

            if selected_voice_id:
                engine.setProperty("voice", selected_voice_id)

        _voice_name = selected_name
        _engine = engine
        _engine_available = True
        return True

    except Exception as e:
        _engine = None
        _engine_available = False
        print(f"\n[Voice Notice]: Local Windows text-to-speech initialize nahi ho saka ({e}).")
        print("  NEHA text-only mode mein normal tarike se kaam karti rahegi.\n")
        return False


def set_custom_engine(engine: Optional[Any]) -> None:
    """Allows injecting a custom or mock engine for unit testing."""
    global _engine, _engine_available, _init_attempted, _voice_name
    _engine = engine
    _engine_available = engine is not None
    _init_attempted = True
    if engine is not None:
        _voice_name = "Mock Voice"


def is_voice_enabled() -> bool:
    """Returns True if voice output is enabled by user/config."""
    return _voice_enabled


def set_voice_enabled(enabled: bool) -> None:
    """Enables or disables voice output."""
    global _voice_enabled
    _voice_enabled = enabled


def get_voice_status() -> str:
    """
    Returns a human-readable status string for the /voice status command.
    """
    if not _init_attempted:
        init_engine()

    status_str = "ON (Active)" if _voice_enabled else "OFF (Muted)"
    engine_state = "Ready" if _engine_available else "Unavailable (Text-only fallback)"
    rate_str = f"{get_configured_rate()} wpm"

    return (
        f"Voice Output: {status_str}\n"
        f"Engine: {engine_state} (Local Windows SAPI5)\n"
        f"Current Voice: {_voice_name}\n"
        f"Speech Rate: {rate_str}"
    )


def speak(text: str) -> bool:
    """
    Speaks the given text using the local TTS engine.
    Ensures that failures do not crash the assistant and gracefully fall back.

    Args:
        text (str): The response text to speak.

    Returns:
        bool: True if spoken successfully, False otherwise.
    """
    if not _voice_enabled:
        return False

    if not _init_attempted:
        init_engine()

    if not _engine_available or _engine is None:
        return False

    speech_text = _clean_text_for_speech(text)
    if not speech_text:
        return False

    try:
        _engine.say(speech_text)
        _engine.runAndWait()
        return True
    except KeyboardInterrupt:
        # User pressed Ctrl+C during speech - stop audio immediately and re-raise
        stop_speech()
        raise
    except Exception as e:
        print(f"\n[Voice Warning]: Audio playback error ({type(e).__name__}). Continuing in text-only mode.")
        return False


def stop_speech() -> None:
    """Stops any active speech playback and cleans up engine resources."""
    global _engine
    if _engine is not None:
        try:
            _engine.stop()
        except Exception:
            pass
