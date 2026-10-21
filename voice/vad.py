"""
voice/vad.py
------------
Voice Activity Detection (VAD) and endpointing engine for NEHA Assistant.

Features:
- Pure NumPy-based frame energy analysis with dynamic noise floor tracking.
- Pre-roll circular audio buffer to preserve the initial word/consonant onset.
- Configurable speech start timeout, silence hangover endpointing, and duration clamping.
- Rejection of short noise impulses (below min_speech_duration) and silent captures.
- Clean cancellation and early stop support.
- Fully compatible with Python 3.13 on 64-bit Windows (no external C++ compiled binaries).
"""

import collections
import os
import time
from typing import List, Optional, Tuple, Callable

try:
    import numpy as np
except ImportError:
    np = None

# VAD Configuration Defaults
DEFAULT_FRAME_MS: int = 30  # 30ms frames @ 16kHz = 480 samples
DEFAULT_SAMPLE_RATE: int = 16000
DEFAULT_SPEECH_START_TIMEOUT: float = 6.0  # seconds to wait for initial speech
DEFAULT_SILENCE_DURATION: float = 1.3  # silence duration (hangover) after speech to finalize
DEFAULT_MIN_SPEECH_DURATION: float = 0.45  # minimum speech to avoid tiny clicks
DEFAULT_MAX_UTTERANCE_DURATION: float = 20.0  # maximum recording window
DEFAULT_FOLLOW_UP_TIMEOUT: float = 4.5  # follow-up listening window

# Session override storage (in-memory, no .env pollution)
_session_vad_settings = {
    "speech_start_timeout": None,
    "silence_duration": None,
    "min_speech_duration": None,
    "max_utterance_duration": None,
    "follow_up_timeout": None,
}


def get_vad_setting(name: str, default: float) -> float:
    """Reads a VAD setting from session override, environment, or default."""
    session_val = _session_vad_settings.get(name)
    if session_val is not None:
        return float(session_val)
    env_name = f"VAD_{name.upper()}"
    env_val = os.environ.get(env_name)
    if env_val:
        try:
            return float(env_val.strip())
        except (ValueError, TypeError):
            pass
    return default


def set_vad_session_setting(name: str, value: Optional[float]) -> None:
    """Sets a session-only VAD setting."""
    if name in _session_vad_settings:
        _session_vad_settings[name] = float(value) if value is not None else None


class VoiceActivityDetector:
    """
    Maintains streaming VAD state for a single recording turn.
    Processes audio chunk by chunk (16-bit PCM @ 16kHz mono).
    """

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        frame_ms: int = DEFAULT_FRAME_MS,
        speech_start_timeout: Optional[float] = None,
        silence_duration: Optional[float] = None,
        min_speech_duration: Optional[float] = None,
        max_utterance_duration: Optional[float] = None,
        pre_roll_ms: int = 450,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_samples = int((sample_rate * frame_ms) / 1000)
        self.pre_roll_frames_count = max(1, int(pre_roll_ms / frame_ms))

        self.speech_start_timeout = (
            speech_start_timeout
            if speech_start_timeout is not None
            else get_vad_setting("speech_start_timeout", DEFAULT_SPEECH_START_TIMEOUT)
        )
        self.silence_duration = (
            silence_duration
            if silence_duration is not None
            else get_vad_setting("silence_duration", DEFAULT_SILENCE_DURATION)
        )
        self.min_speech_duration = (
            min_speech_duration
            if min_speech_duration is not None
            else get_vad_setting("min_speech_duration", DEFAULT_MIN_SPEECH_DURATION)
        )
        self.max_utterance_duration = (
            max_utterance_duration
            if max_utterance_duration is not None
            else get_vad_setting("max_utterance_duration", DEFAULT_MAX_UTTERANCE_DURATION)
        )

        # Pre-roll ring buffer storing raw frames before speech starts
        self._pre_roll = collections.deque(maxlen=self.pre_roll_frames_count)

        # Captured frames for the utterance
        self._captured_frames: List[np.ndarray] = []

        # Internal state
        self._start_time = time.time()
        self._speech_started = False
        self._speech_start_time: Optional[float] = None
        self._last_speech_time: Optional[float] = None
        self._noise_floor: float = 150.0  # Initial baseline estimate
        self._total_speech_frames: int = 0
        self._is_completed = False
        self._completion_reason = ""  # 'endpoint', 'timeout_no_speech', 'max_duration', 'cancelled', 'empty'

    @property
    def speech_started(self) -> bool:
        """Returns True if user voice activity has been triggered."""
        return self._speech_started

    @property
    def is_completed(self) -> bool:
        """Returns True if the utterance detection cycle is finished."""
        return self._is_completed

    @property
    def completion_reason(self) -> str:
        """Returns the termination status reason."""
        return self._completion_reason

    def compute_frame_energy(self, frame: "np.ndarray") -> float:
        """Computes Root Mean Square (RMS) amplitude of a single audio frame."""
        if np is None or frame is None or len(frame) == 0:
            return 0.0
        flat = frame.astype(np.float64).flatten()
        return float(np.sqrt(np.mean(flat ** 2)))

    def process_frame(self, frame: "np.ndarray") -> bool:
        """
        Ingests a single audio frame.
        Returns True if processing should continue, False if recording has completed/ended.
        """
        if self._is_completed:
            return False

        now = time.time()
        elapsed_total = now - self._start_time
        energy = self.compute_frame_energy(frame)

        # Dynamic speech threshold: adapts to background noise floor
        # Margin of 220 + 2.5x noise floor, clamped to reasonable minimum
        dynamic_threshold = max(280.0, self._noise_floor * 2.2 + 180.0)
        is_speech_frame = energy >= dynamic_threshold

        if not self._speech_started:
            # 1. Waiting for user to start speaking
            if is_speech_frame:
                self._speech_started = True
                self._speech_start_time = now
                self._last_speech_time = now
                self._total_speech_frames += 1

                # Flush pre-roll buffer to captured frames so opening syllables are preserved
                for pr_frame in self._pre_roll:
                    self._captured_frames.append(pr_frame)
                self._captured_frames.append(frame)
            else:
                # Still silence/ambient background: update noise floor estimate
                alpha = 0.05  # Slow adaptation rate
                self._noise_floor = (1 - alpha) * self._noise_floor + alpha * energy
                self._pre_roll.append(frame)

                # Check if speech start timeout exceeded
                if elapsed_total >= self.speech_start_timeout:
                    self._is_completed = True
                    self._completion_reason = "timeout_no_speech"
                    return False
        else:
            # 2. In active speech utterance
            self._captured_frames.append(frame)

            if is_speech_frame:
                self._last_speech_time = now
                self._total_speech_frames += 1
            else:
                # Silence after speech started: check endpointing hangover duration
                silence_elapsed = now - (self._last_speech_time or now)
                speech_duration = now - (self._speech_start_time or now)

                if silence_elapsed >= self.silence_duration:
                    # Speech endpoint reached!
                    if speech_duration < self.min_speech_duration:
                        # Too brief (e.g. transient noise or click)
                        self._is_completed = True
                        self._completion_reason = "noise_rejected"
                        return False

                    self._is_completed = True
                    self._completion_reason = "endpoint"
                    return False

            # Check maximum utterance ceiling
            utterance_duration = now - (self._speech_start_time or now)
            if utterance_duration >= self.max_utterance_duration:
                self._is_completed = True
                self._completion_reason = "max_duration"
                return False

        return True

    def get_captured_audio(self) -> Optional["np.ndarray"]:
        """
        Concatenates all captured frames into a single 1D numpy array.
        Returns None if no speech was captured or if noise was rejected.
        """
        if np is None or not self._captured_frames or not self._speech_started:
            return None
        if self._completion_reason == "noise_rejected":
            return None
        return np.concatenate(self._captured_frames, axis=0)
