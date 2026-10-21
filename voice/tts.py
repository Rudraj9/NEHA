"""
voice/tts.py
------------
NEHA Assistant unified Text-to-Speech (TTS) manager and router.

Supports two configurable TTS providers:
1. 'sarvam' (Default if SARVAM_API_KEY is present or TTS_PROVIDER=sarvam):
   Cloud-based Sarvam AI Bulbul TTS with natural Hindi/Hinglish pronunciation.
2. 'local' (Configurable via TTS_PROVIDER=local):
   Windows SAPI5 / pyttsx3 offline speech synthesis.

Guarantees:
- If voice is disabled (/voice off), zero audio requests are made.
- If Sarvam fails, shows a short notice and continues text chat without silently
  falling back to the English-accent local voice.
- Provider dependencies (e.g. pyttsx3 COM) are initialized only when requested.
- Clean cancellation and Ctrl+C shutdown.
"""

import os
from typing import Optional, Any

from .local_tts import (
    speak_local,
    stop_local_speech,
    get_local_status,
    init_engine,
    set_custom_engine,
)
from .sarvam_tts import (
    speak_sarvam,
    stop_sarvam_speech,
    get_sarvam_status,
    get_sarvam_api_key,
)

# Providers
PROVIDER_SARVAM: str = "sarvam"
PROVIDER_LOCAL: str = "local"


def _get_env_voice_enabled() -> bool:
    val = os.environ.get("VOICE_ENABLED", "true").strip().lower()
    return val in ("true", "1", "yes", "on")


def _get_default_provider() -> str:
    env_provider = os.environ.get("TTS_PROVIDER", "").strip().lower()
    if env_provider in (PROVIDER_SARVAM, PROVIDER_LOCAL):
        return env_provider
    # If SARVAM_API_KEY is configured, default to Sarvam; otherwise local SAPI5
    if get_sarvam_api_key():
        return PROVIDER_SARVAM
    return PROVIDER_LOCAL


# Module state
_voice_enabled: bool = _get_env_voice_enabled()
_active_provider: str = _get_default_provider()
_is_speaking: bool = False


def is_voice_enabled() -> bool:
    """Returns True if voice output is currently enabled."""
    return _voice_enabled


def set_voice_enabled(enabled: bool) -> None:
    """Enables or disables voice output."""
    global _voice_enabled
    _voice_enabled = enabled


def is_speaking() -> bool:
    """Returns True if speech playback is currently active."""
    return _is_speaking


def get_active_provider() -> str:
    """Returns the name of the currently active TTS provider ('sarvam' or 'local')."""
    return _active_provider


def set_active_provider(provider: str) -> None:
    """Switches the active TTS provider ('sarvam' or 'local')."""
    global _active_provider
    normalized = provider.strip().lower()
    if normalized in (PROVIDER_SARVAM, PROVIDER_LOCAL):
        _active_provider = normalized
    else:
        raise ValueError(f"Unknown TTS provider '{provider}'. Must be 'sarvam' or 'local'.")


def get_voice_status() -> str:
    """
    Returns a human-readable status string for the /voice status command.
    Includes active provider, model/voice configuration, and mute state without exposing secrets.
    """
    status_str = "ON (Active)" if _voice_enabled else "OFF (Muted)"
    provider_title = "Sarvam AI Bulbul (Cloud)" if _active_provider == PROVIDER_SARVAM else "Local SAPI5 (Offline)"

    provider_details = (
        get_sarvam_status() if _active_provider == PROVIDER_SARVAM else get_local_status()
    )

    return (
        f"Voice Output: {status_str}\n"
        f"Active Provider: {provider_title}\n"
        f"{provider_details}"
    )


def speak(text: str) -> bool:
    """
    Speaks the given text using the active TTS provider.
    Ensures that failures do not crash the assistant and gracefully fall back to text chat.

    Args:
        text (str): The response text to speak.

    Returns:
        bool: True if spoken successfully, False otherwise.
    """
    global _is_speaking

    # 1. When voice is disabled, make no requests (neither Sarvam nor local)
    if not _voice_enabled:
        return False

    clean_text = text.strip() if text else ""
    if not clean_text:
        return False

    _is_speaking = True
    try:
        # 2. Delegate to active provider
        if _active_provider == PROVIDER_SARVAM:
            try:
                return speak_sarvam(clean_text)
            except KeyboardInterrupt:
                stop_speech()
                raise
            except Exception as e:
                print(f"\n[Voice Warning]: Sarvam TTS error ({type(e).__name__}). Continuing in text-only mode.")
                return False

        elif _active_provider == PROVIDER_LOCAL:
            try:
                return speak_local(clean_text)
            except KeyboardInterrupt:
                stop_speech()
                raise
            except Exception as e:
                print(f"\n[Voice Warning]: Local TTS error ({type(e).__name__}). Continuing in text-only mode.")
                return False

        return False
    finally:
        _is_speaking = False


def stop_speech() -> None:
    """Stops any active speech playback across both providers."""
    global _is_speaking
    _is_speaking = False
    stop_sarvam_speech()
    stop_local_speech()
