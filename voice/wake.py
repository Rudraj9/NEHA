"""
voice/wake.py
-------------
Local wake-word detection engine for NEHA Assistant.

Technology & Compliance:
- Provider: Picovoice Porcupine (Windows 64-bit on-device keyword spotter).
- Processing: 100% local, runs on device CPU. Zero cloud audio streaming or background uploads.
- Target Keyword: 'Hi NEHA' (requires custom trained Porcupine keyword model .ppn).
- Prerequisites:
  1. Picovoice AccessKey (Free tier from https://console.picovoice.ai/)
  2. Custom trained keyword model for 'Hi NEHA' (.ppn file for Windows x86_64)
- Clear Availability Check:
  If AccessKey or model file is missing, wake-word detection is explicitly marked
  as unavailable with an actionable setup checklist. It never silently substitutes
  an unrelated pretrained model (like 'Picovoice' or 'Porcupine') for 'Hi NEHA'.
- Fallback: Click-to-talk microphone button and typed chat remain fully active.
"""

import os
from typing import Dict, Any, Optional, Callable, Tuple

try:
    import pvporcupine
except ImportError:
    pvporcupine = None

# Custom detector hook for automated testing: (frame) -> bool (True if keyword detected)
_custom_wake_detector: Optional[Callable[[Any], bool]] = None


def set_custom_wake_detector(detector: Optional[Callable[[Any], bool]]) -> None:
    """Sets a custom wake-word detector function for unit tests."""
    global _custom_wake_detector
    _custom_wake_detector = detector


def get_picovoice_access_key() -> str:
    """Returns the Picovoice AccessKey from environment."""
    return os.environ.get("PICOVOICE_ACCESS_KEY", "").strip()


def get_wake_word_model_path() -> str:
    """Returns the custom Porcupine keyword model file path (.ppn)."""
    return os.environ.get("WAKE_WORD_MODEL_PATH", "").strip()


def get_wake_word_sensitivity() -> float:
    """Returns keyword detection sensitivity (0.0 to 1.0, default 0.5)."""
    try:
        val = float(os.environ.get("WAKE_WORD_SENSITIVITY", "0.5").strip())
        return max(0.0, min(1.0, val))
    except (ValueError, TypeError):
        return 0.5


def check_wake_word_availability() -> Dict[str, Any]:
    """
    Verifies if local wake-word detection is configured and ready.
    Returns status dict with actionable checklist if not ready.
    """
    if _custom_wake_detector is not None:
        return {
            "available": True,
            "configured": True,
            "provider": "Mock / Custom Test Detector",
            "keyword": "Hi NEHA",
            "missing": [],
        }

    if pvporcupine is None:
        return {
            "available": False,
            "configured": False,
            "provider": "Picovoice Porcupine",
            "keyword": "Hi NEHA",
            "missing": ["pvporcupine library not installed in .venv"],
            "checklist": [
                "1. Run: pip install pvporcupine",
            ],
        }

    access_key = get_picovoice_access_key()
    model_path = get_wake_word_model_path()
    missing = []
    checklist = []

    if not access_key:
        missing.append("PICOVOICE_ACCESS_KEY missing in .env")
        checklist.append(
            "1. Free Picovoice AccessKey prapt karein (https://console.picovoice.ai/) aur .env mein 'PICOVOICE_ACCESS_KEY=...' set karein."
        )

    if not model_path:
        missing.append("WAKE_WORD_MODEL_PATH missing in .env")
        checklist.append(
            "2. Picovoice Console par custom wake word 'Hi Neha' (Windows platform) train karein, .ppn download karein, aur .env mein 'WAKE_WORD_MODEL_PATH=path/to/Hi-Neha_en_windows_v3_0_0.ppn' set karein."
        )
    elif not os.path.isfile(model_path):
        missing.append(f"Model file not found at path: {model_path}")
        checklist.append(
            f"2. Specified .ppn model file path exist nahi karti: '{model_path}'. Kripya sahi file path verify karein."
        )

    if missing:
        return {
            "available": False,
            "configured": False,
            "provider": "Picovoice Porcupine (Local)",
            "keyword": "Hi NEHA",
            "missing": missing,
            "checklist": checklist,
            "message": "Local 'Hi NEHA' wake-word detection setup incomplete hai. Manual click-to-talk mic aur typed chat ready hain.",
        }

    return {
        "available": True,
        "configured": True,
        "provider": "Picovoice Porcupine (Local)",
        "keyword": "Hi NEHA",
        "model_path": model_path,
        "missing": [],
        "message": "Local wake-word engine 'Hi NEHA' ke liye ready hai.",
    }


class PorcupineWakeDetector:
    """
    Encapsulates a local Porcupine keyword detector instance.
    Processes 16kHz mono audio frames.
    """

    def __init__(self) -> None:
        self._porcupine = None
        self._is_ready = False
        self._frame_length = 512
        self._sample_rate = 16000

        if _custom_wake_detector is not None:
            self._is_ready = True
            return

        status = check_wake_word_availability()
        if not status["available"]:
            raise RuntimeError(
                f"Wake word detector cannot start: {'; '.join(status['missing'])}"
            )

        access_key = get_picovoice_access_key()
        model_path = get_wake_word_model_path()
        sensitivity = get_wake_word_sensitivity()

        try:
            self._porcupine = pvporcupine.create(
                access_key=access_key,
                keyword_paths=[model_path],
                sensitivities=[sensitivity],
            )
            self._frame_length = self._porcupine.frame_length
            self._sample_rate = self._porcupine.sample_rate
            self._is_ready = True
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Porcupine engine: {e}")

    @property
    def frame_length(self) -> int:
        """Required audio frame length in samples (typically 512 samples @ 16kHz)."""
        return self._frame_length

    @property
    def sample_rate(self) -> int:
        """Required sample rate (16000 Hz)."""
        return self._sample_rate

    def process(self, pcm_frame: Any) -> bool:
        """
        Processes a single frame of 16-bit PCM samples.
        Returns True if 'Hi NEHA' wake-word was detected in this frame.
        """
        if _custom_wake_detector is not None:
            return bool(_custom_wake_detector(pcm_frame))

        if not self._is_ready or self._porcupine is None:
            return False

        try:
            keyword_index = self._porcupine.process(pcm_frame)
            return keyword_index >= 0
        except Exception:
            return False

    def close(self) -> None:
        """Releases native Porcupine C engine resources."""
        if self._porcupine is not None:
            try:
                self._porcupine.delete()
            except Exception:
                pass
            self._porcupine = None
        self._is_ready = False
