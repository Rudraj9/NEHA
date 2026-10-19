"""
voice/local_tts.py
------------------
Local offline Text-to-Speech (TTS) module using Windows SAPI5 and pyttsx3.
Preserved as an explicitly selectable offline fallback provider.

Features:
- Windows SAPI5 local engine (Zero API cost, zero network calls).
- State reset on every turn to prevent pyttsx3's single-speech lock bug.
- Dynamic voice selection with safe fallback.
- Explicit lifecycle control and resource cleanup.
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
        voices = engine.getProperty("voices")
        selected_voice_id = None
        selected_name = "System Default"

        if voices:
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


_is_custom_engine: bool = False


def set_custom_engine(engine: Optional[Any]) -> None:
    """Allows injecting a custom or mock engine for unit testing."""
    global _engine, _engine_available, _init_attempted, _voice_name, _is_custom_engine
    _engine = engine
    _engine_available = engine is not None
    _init_attempted = True
    _is_custom_engine = engine is not None
    if engine is not None:
        _voice_name = "Mock Voice"


def get_local_status() -> str:
    """
    Returns a human-readable status string for the local SAPI5 provider.
    """
    if not _init_attempted:
        init_engine()

    engine_state = "Ready" if _engine_available else "Unavailable (Text-only fallback)"
    rate_str = f"{get_configured_rate()} wpm"

    return (
        f"Engine: {engine_state} (Local Windows SAPI5 / pyttsx3)\n"
        f"Current Voice: {_voice_name}\n"
        f"Speech Rate: {rate_str}"
    )


def _reset_engine_loop_state(engine: Any) -> None:
    """
    Resets pyttsx3 internal loop and queue state to ensure reliable multi-turn speech.
    """
    if engine is None:
        return
    try:
        if hasattr(engine, "_inLoop"):
            engine._inLoop = False
        proxy = getattr(engine, "proxy", None)
        if proxy is not None:
            if hasattr(proxy, "_busy"):
                proxy._busy = True
            if hasattr(proxy, "_queue") and isinstance(proxy._queue, list):
                proxy._queue.clear()
            driver = getattr(proxy, "_driver", None)
            if driver is not None:
                if hasattr(driver, "_looping"):
                    driver._looping = False
                if hasattr(driver, "_speaking"):
                    driver._speaking = False
                if hasattr(driver, "_stopping"):
                    driver._stopping = False
    except Exception:
        pass


def speak_local(text: str) -> bool:
    """
    Speaks the given text using the local pyttsx3 TTS engine.
    Ensures that failures do not crash the assistant and gracefully fall back.

    Args:
        text (str): The response text to speak.

    Returns:
        bool: True if spoken and playback completed successfully, False otherwise.
    """
    if not _init_attempted:
        init_engine()

    if not _engine_available or _engine is None:
        return False

    speech_text = _clean_text_for_speech(text)
    if not speech_text:
        return False

    # Attach event listener to confirm actual playback completion on real pyttsx3 engines
    playback_completed = [True]  # Default to True for custom/mock engines without proxy
    token = None
    if not _is_custom_engine and hasattr(_engine, "connect") and callable(_engine.connect):
        try:
            playback_completed[0] = False

            def _on_finished(name=None, completed=True):
                playback_completed[0] = bool(completed)

            token = _engine.connect("finished-utterance", _on_finished)
        except Exception:
            token = None
            playback_completed[0] = True

    try:
        _reset_engine_loop_state(_engine)
        _engine.say(speech_text)
        _engine.runAndWait()
        return bool(playback_completed[0])
    except KeyboardInterrupt:
        stop_local_speech()
        raise
    except Exception as e:
        print(f"\n[Voice Warning]: Local audio playback error ({type(e).__name__}). Continuing in text-only mode.")
        _reset_engine_loop_state(_engine)
        return False
    finally:
        if token is not None and hasattr(_engine, "disconnect") and callable(_engine.disconnect):
            try:
                _engine.disconnect(token)
            except Exception:
                pass
        _reset_engine_loop_state(_engine)


def stop_local_speech() -> None:
    """Stops any active local speech playback and cleans up engine resources."""
    global _engine
    if _engine is not None:
        try:
            _engine.stop()
        except Exception:
            pass
        _reset_engine_loop_state(_engine)
