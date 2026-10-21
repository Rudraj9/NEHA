"""
voice/ack.py
------------
Acknowledgment manager for NEHA Assistant.

Handles playing the immediate spoken response "Haan Rocky, bolo" upon wake-word detection.

Guarantees:
- Never calls Groq or any LLM chat model to generate this fixed acknowledgment.
- Locally caches pre-synthesized WAV audio in memory keyed by (tts_provider, voice_name).
- Automatically invalidates cache when TTS provider or voice persona is changed.
- If TTS synthesis fails or network is offline, generates a pleasant 180ms dual-tone
  activation chime locally using NumPy (zero external dependencies).
- When voice output is muted (VOICE_ENABLED=false), skips spoken playback without error,
  preserving microphone capture for the user's question.
- Guaranteed blocking playback ensures recording does NOT open while acknowledgment plays.
"""

import io
import math
import os
import wave
from typing import Dict, Tuple, Optional, Callable

try:
    import numpy as np
except ImportError:
    np = None

try:
    import winsound
except ImportError:
    winsound = None

from . import tts
from . import sarvam_tts
from . import local_tts

ACKNOWLEDGMENT_TEXT: str = "Haan Rocky, bolo."

# In-memory WAV cache: (provider, voice_id) -> bytes
_ack_audio_cache: Dict[Tuple[str, str], bytes] = {}

# Custom test hook to simulate or spy on acknowledgment playback
_custom_ack_player: Optional[Callable[[], bool]] = None


def set_custom_ack_player(player: Optional[Callable[[], bool]]) -> None:
    """Sets a custom acknowledgment playback hook for unit tests."""
    global _custom_ack_player
    _custom_ack_player = player


def invalidate_ack_cache() -> None:
    """Clears the in-memory cached acknowledgment audio."""
    global _ack_audio_cache
    _ack_audio_cache.clear()


def generate_local_chime_wav(sample_rate: int = 16000) -> bytes:
    """
    Generates a short, pleasant two-tone activation chime (C5 523Hz -> G5 784Hz)
    completely offline in memory as 16-bit PCM WAV.
    """
    duration = 0.18  # 180 ms total
    num_samples = int(sample_rate * duration)
    half = num_samples // 2

    if np is not None:
        t1 = np.linspace(0, duration / 2, half, endpoint=False)
        t2 = np.linspace(0, duration / 2, num_samples - half, endpoint=False)

        # Tone 1: 523 Hz (C5) with smooth envelope
        env1 = np.sin(np.pi * np.linspace(0, 1, half))
        tone1 = (np.sin(2 * np.pi * 523.25 * t1) * env1 * 12000).astype(np.int16)

        # Tone 2: 783.99 Hz (G5) with decaying envelope
        env2 = np.sin(np.pi * np.linspace(0, 1, num_samples - half))
        tone2 = (np.sin(2 * np.pi * 783.99 * t2) * env2 * 14000).astype(np.int16)

        samples = np.concatenate([tone1, tone2])
        pcm_bytes = samples.tobytes()
    else:
        # Fallback pure-python sine generation
        pcm_frames = bytearray()
        for i in range(num_samples):
            freq = 523.25 if i < half else 783.99
            t = (i % half) / sample_rate
            env = math.sin(math.pi * ((i % half) / half))
            val = int(math.sin(2 * math.pi * freq * t) * env * 12000)
            val = max(-32768, min(32767, val))
            pcm_frames.extend(val.to_bytes(2, byteorder="little", signed=True))
        pcm_bytes = bytes(pcm_frames)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

    return buf.getvalue()


def get_cached_ack_audio() -> Optional[bytes]:
    """
    Retrieves or synthesizes the acknowledgment WAV audio for the active voice setup.
    """
    provider = tts.get_active_provider()
    voice_key = (
        sarvam_tts.get_sarvam_voice()
        if provider == tts.PROVIDER_SARVAM
        else "local_sapi5"
    )
    cache_key = (provider, voice_key)

    if cache_key in _ack_audio_cache:
        return _ack_audio_cache[cache_key]

    wav_bytes = None
    if provider == tts.PROVIDER_SARVAM:
        # Check if Sarvam API key is configured
        if sarvam_tts.get_sarvam_api_key():
            try:
                wav_bytes = sarvam_tts.synthesize_chunk(ACKNOWLEDGMENT_TEXT)
            except Exception:
                wav_bytes = None

    if wav_bytes:
        _ack_audio_cache[cache_key] = wav_bytes
        return wav_bytes

    # If Sarvam is unavailable or local is active, generate fallback local chime
    chime_bytes = generate_local_chime_wav()
    _ack_audio_cache[cache_key] = chime_bytes
    return chime_bytes


def play_acknowledgment() -> bool:
    """
    Plays the wake-word acknowledgment ("Haan Rocky, bolo" or activation chime).
    Guarantees blocking execution until playback completes so the microphone stream
    does not capture its own acknowledgment sound.
    """
    if _custom_ack_player is not None:
        return _custom_ack_player()

    # If voice output is muted, return immediately (visual-only acknowledgment)
    if not tts.is_voice_enabled():
        return True

    provider = tts.get_active_provider()
    if provider == tts.PROVIDER_LOCAL:
        # pyttsx3 speaks synchronously
        try:
            return local_tts.speak_local(ACKNOWLEDGMENT_TEXT)
        except Exception:
            # Fall back to local chime
            pass

    wav_bytes = get_cached_ack_audio()
    if not wav_bytes:
        wav_bytes = generate_local_chime_wav()

    if winsound is not None:
        try:
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
            return True
        except Exception:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
                return True
            except Exception:
                return False

    return False
