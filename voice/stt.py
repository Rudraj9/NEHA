"""
voice/stt.py
------------
Speech-to-Text (STT) module for NEHA Assistant using the official Groq API.

Features:
- Uses Groq's official client.audio.transcriptions.create endpoint.
- Verified Multilingual Models:
  - 'whisper-large-v3-turbo' (Default): Ultra-fast, cost-efficient, multilingual (Hindi & English).
  - 'whisper-large-v3': High accuracy, multilingual (Hindi & English).
- Language support:
  - Configurable via GROQ_STT_LANGUAGE (e.g., 'hi', 'en', or None/empty for auto-detect).
  - Auto-detection preserves mixed Hindi-English (Hinglish) and Devanagari Hindi as spoken.
- Pure transcription (preserves original spoken language, never translates to English).
- Independent configuration: GROQ_STT_MODEL is completely decoupled from chat GROQ_MODEL.
- In-memory transmission: Sends WAV byte buffers directly via tuple ("recording.wav", wav_bytes).
- Robust error handling: Catches authentication, rate limits, model errors, timeouts, and network issues.
- Test hook (set_custom_transcriber) for fast, isolated unit and integration verification.
"""

import os
from typing import Optional, Tuple, Any, Callable
from dotenv import load_dotenv

# Groq official SDK imports
from groq import (
    Groq,
    APIConnectionError,
    APIStatusError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
)

load_dotenv()

# Defaults
DEFAULT_STT_MODEL: str = "whisper-large-v3-turbo"
DEFAULT_TIMEOUT: float = 30.0  # seconds
DEFAULT_MAX_RETRIES: int = 2

# Test hooks
_custom_client: Optional[Any] = None
_custom_transcriber: Optional[Callable[[bytes], Tuple[bool, str]]] = None


def set_client(client: Optional[Any]) -> None:
    """Sets a custom Groq client for STT mocking."""
    global _custom_client
    _custom_client = client


def set_custom_transcriber(transcriber: Optional[Callable[[bytes], Tuple[bool, str]]]) -> None:
    """Sets a custom transcription function for automated testing."""
    global _custom_transcriber
    _custom_transcriber = transcriber


def get_stt_model() -> str:
    """
    Returns the configured Speech-to-Text model name from GROQ_STT_MODEL.
    Defaults to 'whisper-large-v3-turbo'.
    """
    return os.environ.get("GROQ_STT_MODEL", DEFAULT_STT_MODEL).strip() or DEFAULT_STT_MODEL


def get_stt_language() -> Optional[str]:
    """
    Returns the optional ISO-639-1 language code from GROQ_STT_LANGUAGE.
    If empty or unset, returns None to allow Whisper's automatic language detection,
    which best supports mixed Hindi-English (Hinglish) speech.
    """
    lang = os.environ.get("GROQ_STT_LANGUAGE", "").strip().lower()
    return lang if lang else None


def get_groq_client() -> Groq:
    """
    Initializes and returns the Groq client for transcription.
    Reuses existing GROQ_API_KEY from environment.
    """
    if _custom_client is not None:
        return _custom_client

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    return Groq(
        api_key=api_key,
        timeout=DEFAULT_TIMEOUT,
        max_retries=DEFAULT_MAX_RETRIES,
    )


def transcribe_audio(
    wav_bytes: bytes,
    filename: str = "recording.wav",
    temperature: float = 0.0,
) -> Tuple[bool, str]:
    """
    Transcribes in-memory WAV audio bytes using Groq's official Whisper API.

    Guarantees:
    - Pure transcription, preserving original spoken Hindi/English/Hinglish language.
    - Zero temporary files on disk: Passes in-memory bytes tuple to Groq SDK.
    - Independent model configuration (GROQ_STT_MODEL).
    - Clear, descriptive error messages without leaking secrets or credentials.

    Args:
        wav_bytes: In-memory 16-bit PCM WAV audio bytes.
        filename: Label for the virtual file (default: "recording.wav").
        temperature: Sampling temperature (default: 0.0 for deterministic transcription).

    Returns:
        (success, result_or_error):
        - If success is True, result_or_error contains the recognized transcript text.
        - If success is False, result_or_error contains a user-friendly error message.

    Raises:
        KeyboardInterrupt: If user cancels during the transcription request.
    """
    if _custom_transcriber is not None:
        return _custom_transcriber(wav_bytes)

    if not wav_bytes:
        return True, ""

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key or "your_groq_api_key_here" in api_key.lower():
        return (
            False,
            "[Authentication Error]: GROQ_API_KEY valid nahi hai ya placeholder par set hai.\n"
            "Kripya '.env' file mein apni Groq API key configure karein.",
        )

    model_name = get_stt_model()
    language = get_stt_language()

    try:
        client = get_groq_client()

        # Build parameters for client.audio.transcriptions.create
        kwargs = {
            "file": (filename, wav_bytes),
            "model": model_name,
            "response_format": "json",
            "temperature": temperature,
        }
        if language:
            kwargs["language"] = language

        # Make official transcription API call
        transcription = client.audio.transcriptions.create(**kwargs)

        text = getattr(transcription, "text", "") or ""
        return True, text.strip()

    except KeyboardInterrupt:
        # User pressed Ctrl+C during transcription
        raise

    except AuthenticationError:
        return (
            False,
            "[Authentication Error]: Groq API key invalid ya unauthorized hai.\n"
            "Kripya '.env' mein GROQ_API_KEY verify karein.",
        )

    except RateLimitError:
        return (
            False,
            "[Rate Limit Notice]: Groq Speech-to-Text API ki rate limit reach ho gayi hai.\n"
            "Kripya kuch seconds wait karein aur dobara '/listen' try karein.",
        )

    except NotFoundError:
        return (
            False,
            f"[Model Error]: Configured STT model '{model_name}' Groq par nahi mila ya unavailable hai.\n"
            "Kripya '.env' mein GROQ_STT_MODEL check karein (e.g. whisper-large-v3-turbo).",
        )

    except APIConnectionError:
        return (
            False,
            "[Network/Timeout Error]: Groq transcription server se connect nahi ho paya ya request timeout ho gayi.\n"
            "Kripya internet connection check karein aur dobara koshish karein.",
        )

    except APIStatusError as e:
        return (
            False,
            f"[API Error]: Groq transcription service ne error diya (Status {e.status_code}).\n"
            "Kripya thodi der baad dobara try karein.",
        )

    except Exception as e:
        return (
            False,
            f"[Transcription Error]: Audio transcribe karte samay issue aaya: {type(e).__name__}.",
        )
