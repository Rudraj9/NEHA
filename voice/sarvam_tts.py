"""
voice/sarvam_tts.py
-------------------
Sarvam AI Bulbul Text-to-Speech (TTS) integration module.
Generates expressive Indian voice synthesis for Hindi/Hinglish responses.

Features:
- REST API integration with Sarvam Bulbul models (e.g. bulbul:v3, bulbul:v4-flash).
- Configurable model, speaker/voice persona, and target language.
- Clean text preprocessing to remove code blocks and markdown symbols.
- Sentence-boundary chunking for long responses respecting provider limits.
- In-memory WAV playback via Windows winsound (zero disk persistence).
- Safe temporary file fallback with proper Windows handle closing and cleanup.
- Clean cancellation support (Ctrl+C and stop_speech).
- Bounded retries and friendly non-intrusive warning messages.
"""

import os
import re
import base64
import tempfile
import time
from typing import Optional, List, Dict, Any, Callable

try:
    import winsound
except ImportError:
    winsound = None  # Non-Windows environments

import requests

# API Defaults & Constants
DEFAULT_SARVAM_ENDPOINT: str = "https://api.sarvam.ai/text-to-speech"
DEFAULT_MODEL: str = "bulbul:v3"
DEFAULT_VOICE: str = "neha"
DEFAULT_LANGUAGE: str = "hi-IN"
DEFAULT_PACE: float = 1.0
MAX_CHUNK_CHARS: int = 2000
DEFAULT_TIMEOUT: tuple = (5.0, 25.0)  # (connect_timeout, read_timeout)
MAX_RETRIES: int = 2

# Internal state
_playback_cancelled: bool = False
_custom_requester: Optional[Callable[[Dict[str, Any], Dict[str, str]], requests.Response]] = None


def get_sarvam_api_key() -> str:
    """Returns the configured Sarvam API subscription key from environment."""
    return os.environ.get("SARVAM_API_KEY", "").strip()


def get_sarvam_model() -> str:
    """Returns the configured Bulbul model ID."""
    return os.environ.get("SARVAM_TTS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_sarvam_voice() -> str:
    """Returns the configured speaker/voice persona ID."""
    return os.environ.get("SARVAM_TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE


def get_sarvam_language() -> str:
    """Returns the configured BCP-47 language code."""
    return os.environ.get("SARVAM_TTS_LANGUAGE", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE


def get_sarvam_pace() -> float:
    """Returns the configured speaking speed pace (0.5 to 2.0)."""
    try:
        val = float(os.environ.get("SARVAM_TTS_PACE", str(DEFAULT_PACE)).strip())
        return max(0.5, min(2.0, val))
    except (ValueError, TypeError):
        return DEFAULT_PACE


def set_custom_requester(requester: Optional[Callable[[Dict[str, Any], Dict[str, str]], requests.Response]]) -> None:
    """Allows injecting a custom or mock HTTP requester for testing."""
    global _custom_requester
    _custom_requester = requester


def clean_text_for_speech(text: str) -> str:
    """
    Cleans markdown formatting, code fences, and symbols to make speech sound natural.
    Does NOT translate, transliterate, or rewrite Roman Hinglish.
    """
    if not text:
        return ""
    # Remove code blocks ```...```
    cleaned = re.sub(r"```[\s\S]*?```", " [code block omitted] ", text)
    # Remove inline code `...`
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Remove markdown links [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    # Remove bold/italic/header markers (*, _, ~, #)
    cleaned = re.sub(r"[*_~#]", " ", cleaned)
    # Normalize multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """
    Splits long text into ordered chunks at sensible sentence boundaries.
    Respects provider text limits without losing or repeating content.
    """
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    # Split by sentence-ending delimiters while capturing delimiters
    raw_sentences = re.split(r"(?<=[।\n.?!])\s+", cleaned)
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for sentence in raw_sentences:
        sent = sentence.strip()
        if not sent:
            continue

        # If a single sentence is abnormally long, split by commas or words
        if len(sent) > max_chars:
            # Flush existing accumulated chunk first
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0

            sub_parts = re.split(r"(?<=[,;:])\s+", sent)
            for part in sub_parts:
                part_clean = part.strip()
                if not part_clean:
                    continue
                if len(part_clean) > max_chars:
                    # Hard word-level split as last resort
                    words = part_clean.split()
                    temp_part: List[str] = []
                    temp_len = 0
                    for word in words:
                        if temp_len + len(word) + 1 > max_chars:
                            if temp_part:
                                chunks.append(" ".join(temp_part))
                            temp_part = [word]
                            temp_len = len(word)
                        else:
                            temp_part.append(word)
                            temp_len += len(word) + 1
                    if temp_part:
                        chunks.append(" ".join(temp_part))
                else:
                    if current_len + len(part_clean) + 1 > max_chars:
                        chunks.append(" ".join(current_chunk))
                        current_chunk = [part_clean]
                        current_len = len(part_clean)
                    else:
                        current_chunk.append(part_clean)
                        current_len += len(part_clean) + 1
            continue

        if current_len + len(sent) + 1 > max_chars:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sent]
            current_len = len(sent)
        else:
            current_chunk.append(sent)
            current_len += len(sent) + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def play_audio_bytes(wav_bytes: bytes) -> bool:
    """
    Plays WAV audio bytes locally on Windows.
    Prefers in-memory playback with winsound.
    Falls back to temporary file with safe handle closure and cleanup.
    Blocks until playback completes to avoid audio overlap.
    """
    global _playback_cancelled
    if winsound is None:
        print("\n[Voice Warning]: Local Windows audio playback (winsound) is not available.")
        return False

    if _playback_cancelled:
        return False

    # 1. Primary: In-memory playback
    try:
        # winsound.PlaySound blocks until playback finishes
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
        return True
    except KeyboardInterrupt:
        # Halt audio instantly on Ctrl+C
        winsound.PlaySound(None, winsound.SND_PURGE)
        raise
    except Exception as mem_err:
        # 2. Fallback: Safe temporary file playback
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                temp_path = tf.name
                tf.write(wav_bytes)
                tf.flush()
            # File handle is closed BEFORE PlaySound on Windows!
            winsound.PlaySound(temp_path, winsound.SND_FILENAME)
            return True
        except KeyboardInterrupt:
            winsound.PlaySound(None, winsound.SND_PURGE)
            raise
        except Exception as file_err:
            print(f"\n[Voice Warning]: Audio playback failed ({file_err or mem_err}).")
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def synthesize_chunk(text: str) -> Optional[bytes]:
    """
    Sends a single text chunk to Sarvam AI Bulbul TTS API and returns decoded WAV bytes.
    Handles authentication, error status codes, retries, and rate limits gracefully.
    """
    api_key = get_sarvam_api_key()
    if not api_key:
        print("\n[Sarvam Voice Notice]: SARVAM_API_KEY environment variable nahi mili.")
        print("  Sarvam voice use karne ke liye '.env' mein SARVAM_API_KEY set karein.")
        print("  NEHA text mode mein normal tarike se continue karegi.\n")
        return None

    model = get_sarvam_model()
    voice = get_sarvam_voice()
    language = get_sarvam_language()
    pace = get_sarvam_pace()

    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model": model,
        "speaker": voice,
        "language_code": language,
        "output_audio_codec": "wav",
        "pace": pace,
    }

    last_error_msg = ""
    for attempt in range(1, MAX_RETRIES + 1):
        if _playback_cancelled:
            return None

        try:
            if _custom_requester is not None:
                response = _custom_requester(payload, headers)
            else:
                response = requests.post(
                    DEFAULT_SARVAM_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=DEFAULT_TIMEOUT,
                )

            status = response.status_code

            if status == 200:
                data = response.json()
                audios = data.get("audios", [])
                if not audios or not audios[0]:
                    print("\n[Sarvam Voice Warning]: Sarvam API ne empty audio array return kiya.")
                    return None
                return base64.b64decode(audios[0])

            elif status == 401:
                print("\n[Sarvam Voice Warning]: SARVAM_API_KEY invalid ya unauthorized hai.")
                print("  Kripya '.env' mein apni valid Sarvam API key verify karein.")
                return None

            elif status == 429:
                print("\n[Sarvam Voice Warning]: Sarvam TTS rate limit reach ho gayi hai.")
                return None

            elif status == 400:
                err_detail = ""
                try:
                    err_json = response.json()
                    err_detail = err_json.get("message") or err_json.get("detail") or str(err_json)
                except Exception:
                    err_detail = response.text[:200]
                print(f"\n[Sarvam Voice Warning]: Invalid request parameters (Status 400: {err_detail}).")
                print(f"  Configured: model='{model}', voice='{voice}', language='{language}'.")
                return None

            elif status >= 500:
                last_error_msg = f"Server Error (Status {status})"
                if attempt < MAX_RETRIES:
                    time.sleep(1.0 * attempt)
                    continue

            else:
                print(f"\n[Sarvam Voice Warning]: Sarvam API returned status {status}: {response.text[:200]}")
                return None

        except requests.exceptions.Timeout:
            last_error_msg = "Request timeout"
            if attempt < MAX_RETRIES:
                time.sleep(1.0 * attempt)
                continue
        except requests.exceptions.ConnectionError:
            last_error_msg = "Network connection failure"
            if attempt < MAX_RETRIES:
                time.sleep(1.0 * attempt)
                continue
        except Exception as e:
            last_error_msg = f"Unexpected error ({type(e).__name__})"
            break

    if last_error_msg:
        print(f"\n[Sarvam Voice Warning]: {last_error_msg}. Continuing in text-only mode.")
    return None


def speak_sarvam(text: str) -> bool:
    """
    Main entry point for Sarvam speech generation.
    Splits text into chunks, synthesizes each, and plays in order.
    Stops remaining chunks if cancelled or if an error occurs.
    """
    global _playback_cancelled
    _playback_cancelled = False

    cleaned_text = clean_text_for_speech(text)
    if not cleaned_text:
        return False

    chunks = chunk_text(cleaned_text, max_chars=MAX_CHUNK_CHARS)
    if not chunks:
        return False

    for chunk in chunks:
        if _playback_cancelled:
            return False

        wav_bytes = synthesize_chunk(chunk)
        if not wav_bytes:
            # Synthesis failed; stop remaining chunks and continue text chat
            return False

        if _playback_cancelled:
            return False

        success = play_audio_bytes(wav_bytes)
        if not success:
            return False

    return True


def stop_sarvam_speech() -> None:
    """Immediately stops audio playback and cancels remaining speech chunks."""
    global _playback_cancelled
    _playback_cancelled = True
    if winsound is not None:
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


def get_sarvam_status() -> str:
    """
    Returns a human-readable status string for the /voice status command.
    Never exposes API secrets.
    """
    key = get_sarvam_api_key()
    cred_status = "Configured" if bool(key) else "Not Set (Required for Sarvam speech)"
    model = get_sarvam_model()
    voice = get_sarvam_voice()
    lang = get_sarvam_language()
    pace = f"{get_sarvam_pace()}x"

    return (
        f"Engine: Sarvam AI Bulbul (Cloud Text-to-Speech)\n"
        f"Model: {model}\n"
        f"Speaker/Voice: {voice}\n"
        f"Language Code: {lang}\n"
        f"Pace: {pace}\n"
        f"Credentials: {cred_status}"
    )
