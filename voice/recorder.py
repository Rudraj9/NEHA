"""
voice/recorder.py
-----------------
Microphone capture and local audio processing module for NEHA Assistant.

Features:
- Maintained Windows-compatible recording via sounddevice (PortAudio).
- Device enumeration and optional device selection via MIC_DEVICE configuration.
- Configurable recording duration (default: 8.0s, clamped between 1.0s and 30.0s).
- Explicit 16-bit PCM WAV generation completely in memory (zero disk persistence).
- Local silence detection using configurable RMS threshold before uploading.
- Safe lifecycle: Microphone stream is opened only on-demand during /listen and
  guaranteed closed immediately after recording, error, or cancellation (Ctrl+C).
- Test hook (set_custom_recorder) to enable isolated automated verification without hardware.
"""

import io
import os
import time
import wave
from typing import List, Dict, Any, Optional, Tuple, Union, Callable

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import numpy as np
except ImportError:
    np = None

# Configuration Defaults
DEFAULT_RECORDING_DURATION: float = 8.0  # seconds
MIN_RECORDING_DURATION: float = 1.0
MAX_RECORDING_DURATION: float = 30.0
DEFAULT_SILENCE_THRESHOLD: float = 300.0  # RMS threshold for 16-bit PCM
DEFAULT_SAMPLE_RATE: int = 16000  # 16kHz standard for Whisper STT

# Custom recorder hook for automated tests: (duration, device, sample_rate) -> (wav_bytes, rms, is_silent)
_custom_recorder: Optional[Callable[..., Tuple[bytes, float, bool]]] = None

# Active recording control state
_is_recording_active: bool = False
_early_stop_flag: bool = False
_cancel_flag: bool = False


def stop_recording_early() -> None:
    """Signals the active recording loop to finalize early and proceed with captured audio."""
    global _early_stop_flag
    _early_stop_flag = True


def cancel_recording() -> None:
    """Signals the active recording loop to immediately abort and discard audio."""
    global _cancel_flag
    _cancel_flag = True


def is_recording() -> bool:
    """Returns True if the microphone is currently actively capturing audio."""
    return _is_recording_active


def set_custom_recorder(recorder: Optional[Callable[..., Tuple[bytes, float, bool]]]) -> None:
    """Sets a custom recorder function for testing without physical audio devices."""
    global _custom_recorder
    _custom_recorder = recorder


# Session override settings (in-memory only, does not modify .env)
_session_recording_duration: Optional[float] = None
_session_silence_threshold: Optional[float] = None
_session_mic_device: Optional[Union[int, str]] = None


def set_recording_duration(duration: float) -> None:
    """Sets in-memory recording duration for the current session."""
    global _session_recording_duration
    _session_recording_duration = max(MIN_RECORDING_DURATION, min(MAX_RECORDING_DURATION, float(duration)))


def set_silence_threshold(threshold: float) -> None:
    """Sets in-memory silence threshold for the current session."""
    global _session_silence_threshold
    _session_silence_threshold = max(0.0, float(threshold))


def set_mic_device(device: Optional[Union[int, str]]) -> None:
    """Sets in-memory microphone device selection for the current session."""
    global _session_mic_device
    if device is None or str(device).strip() == "" or str(device).lower() == "default":
        _session_mic_device = None
    else:
        try:
            _session_mic_device = int(device)
        except (ValueError, TypeError):
            _session_mic_device = str(device).strip()


def reset_session_settings() -> None:
    """Resets all in-memory session settings overrides to defaults."""
    global _session_recording_duration, _session_silence_threshold, _session_mic_device
    _session_recording_duration = None
    _session_silence_threshold = None
    _session_mic_device = None




def get_recording_duration() -> float:
    """
    Returns configured recording duration in seconds.
    Prefers in-memory session override, falling back to RECORDING_DURATION env var.
    Guarantees duration is bounded between 1.0s and 30.0s (default: 8.0s).
    """
    if _session_recording_duration is not None:
        return _session_recording_duration
    raw_val = os.environ.get("RECORDING_DURATION", "").strip()
    if not raw_val:
        return DEFAULT_RECORDING_DURATION
    try:
        val = float(raw_val)
        return max(MIN_RECORDING_DURATION, min(MAX_RECORDING_DURATION, val))
    except (ValueError, TypeError):
        return DEFAULT_RECORDING_DURATION


def get_silence_threshold() -> float:
    """
    Returns configured RMS silence threshold.
    Prefers in-memory session override, falling back to SILENCE_THRESHOLD env var.
    Audio segments with RMS below this threshold are treated as silent.
    """
    if _session_silence_threshold is not None:
        return _session_silence_threshold
    raw_val = os.environ.get("SILENCE_THRESHOLD", "").strip()
    if not raw_val:
        return DEFAULT_SILENCE_THRESHOLD
    try:
        val = float(raw_val)
        return max(0.0, val)
    except (ValueError, TypeError):
        return DEFAULT_SILENCE_THRESHOLD


def get_configured_mic_device() -> Optional[Union[int, str]]:
    """
    Returns the configured microphone device ID or name substring.
    Prefers in-memory session override, falling back to MIC_DEVICE env var.
    Returns None if unset (system default input will be used).
    """
    if _session_mic_device is not None:
        return _session_mic_device
    val = os.environ.get("MIC_DEVICE", "").strip()
    if not val:
        return None
    # If integer, parse as device index
    try:
        return int(val)
    except ValueError:
        return val


def list_input_devices() -> List[Dict[str, Any]]:
    """
    Queries and returns all available input-capable audio devices.
    Returns empty list if sounddevice is not available or query fails.
    """
    if sd is None:
        return []

    try:
        devices = sd.query_devices()
        try:
            hostapis = sd.query_hostapis()
        except Exception:
            hostapis = []

        default_input = sd.default.device[0] if hasattr(sd, "default") and sd.default.device else None

        input_devices: List[Dict[str, Any]] = []
        for idx, dev in enumerate(devices):
            max_in = dev.get("max_input_channels", 0)
            if max_in > 0:
                hostapi_idx = dev.get("hostapi", 0)
                hostapi_name = (
                    hostapis[hostapi_idx].get("name", "Unknown")
                    if hostapis and hostapi_idx < len(hostapis)
                    else "Unknown"
                )
                input_devices.append({
                    "index": idx,
                    "name": dev.get("name", f"Audio Device {idx}"),
                    "hostapi": hostapi_name,
                    "channels": max_in,
                    "default_samplerate": int(dev.get("default_samplerate", DEFAULT_SAMPLE_RATE)),
                    "is_default": (idx == default_input),
                })
        return input_devices
    except Exception:
        return []


def format_mic_list() -> str:
    """
    Returns a human-readable list of available microphones for the /mic list command.
    """
    devices = list_input_devices()
    if not devices:
        return (
            "System par koi input-capable microphone detect nahi hua!\n"
            "Kripya check karein ki microphone properly connected hai aur Windows\n"
            "Privacy Settings (Settings > Privacy & Security > Microphone) mein app access enabled hai."
        )

    configured = get_configured_mic_device()
    lines = [
        "Available Audio Input Devices (Microphones):",
        f"{'Index':<6} | {'Device Name':<35} | {'Host API':<15} | {'Channels':<8} | Status",
        "-" * 78,
    ]

    for dev in devices:
        status_parts = []
        if dev["is_default"]:
            status_parts.append("[System Default]")
        if configured is not None:
            if isinstance(configured, int) and dev["index"] == configured:
                status_parts.append("<-- Active (.env)")
            elif isinstance(configured, str) and configured.lower() in dev["name"].lower():
                status_parts.append("<-- Active (.env)")

        status_str = " ".join(status_parts) if status_parts else ""
        dev_name = dev["name"][:35]
        lines.append(f"{dev['index']:<6} | {dev_name:<35} | {dev['hostapi']:<15} | {dev['channels']:<8} | {status_str}")

    lines.append("-" * 78)
    active_desc = f"MIC_DEVICE={configured}" if configured is not None else "System Default"
    lines.append(f"Active Selection: {active_desc}")
    lines.append("Tip: Kisi specific mic ko select karne ke liye '.env' mein 'MIC_DEVICE=<index ya name>' set karein.")

    return "\n".join(lines)


def resolve_device(device_spec: Optional[Union[int, str]]) -> Optional[Union[int, str]]:
    """
    Resolves the device index or name against available input devices.
    Returns valid index or substring, or None for system default.
    """
    if device_spec is None:
        return None

    if sd is None:
        return device_spec

    devices = list_input_devices()
    if not devices:
        return None

    # Check if integer index exists
    if isinstance(device_spec, int):
        for dev in devices:
            if dev["index"] == device_spec:
                return device_spec
        # Not found, fallback
        return None

    # String match
    spec_lower = str(device_spec).lower()
    for dev in devices:
        if spec_lower in dev["name"].lower():
            return dev["index"]

    return None


def compute_rms(audio_samples: "np.ndarray") -> float:
    """
    Computes the Root Mean Square (RMS) amplitude of 16-bit PCM audio samples.
    """
    if np is None or audio_samples is None or len(audio_samples) == 0:
        return 0.0

    # Cast to float64 to avoid integer overflow during squaring
    flat = audio_samples.astype(np.float64).flatten()
    if len(flat) == 0:
        return 0.0
    return float(np.sqrt(np.mean(flat ** 2)))


def audio_to_wav_bytes(audio_samples: "np.ndarray", sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    """
    Encodes 16-bit PCM audio samples into a standard in-memory WAV byte buffer.
    """
    if np is None or audio_samples is None or len(audio_samples) == 0:
        return b""

    # Squeeze to 1D mono
    flat_samples = audio_samples.astype(np.int16).flatten()
    pcm_bytes = flat_samples.tobytes()

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)      # Mono
        wf.setsampwidth(2)      # 16-bit PCM = 2 bytes per sample
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

    return buffer.getvalue()


def record_audio(
    duration: Optional[float] = None,
    device: Optional[Union[int, str]] = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    on_start: Optional[Callable[[], None]] = None,
    is_stopped: Optional[Callable[[], bool]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> Tuple[Optional[bytes], float, bool]:
    """
    Captures on-demand audio from the microphone for the specified duration.

    Guarantees:
    - Opens microphone ONLY when this function is called.
    - Releases and closes the microphone stream immediately upon completion,
      error, or cancellation (Ctrl+C / KeyboardInterrupt).
    - Returns in-memory WAV bytes without any file persistence on disk.
    - Computes RMS volume and evaluates silence against SILENCE_THRESHOLD.
    - Gracefully handles missing microphone, permission errors, and invalid settings.
    - Supports early termination (stop button) and cancellation (discard button).

    Args:
        duration: Optional recording duration in seconds (defaults to env or 8.0s, max 30s).
        device: Optional device index or name (defaults to MIC_DEVICE or system default).
        sample_rate: Audio sampling frequency in Hz (default: 16000).
        on_start: Optional callback triggered when the recording stream actually starts.
        is_stopped: Optional predicate checked each chunk to finalize recording early.
        is_cancelled: Optional predicate checked each chunk to discard recording immediately.

    Returns:
        (wav_bytes, rms, is_silent):
        - wav_bytes: In-memory WAV audio bytes, or None if recording was cancelled/failed.
        - rms: Computed audio volume level (float).
        - is_silent: True if RMS < SILENCE_THRESHOLD, False otherwise.

    Raises:
        KeyboardInterrupt: Re-raised if the user presses Ctrl+C during recording,
                           after safely releasing the microphone hardware.
    """
    global _is_recording_active, _early_stop_flag, _cancel_flag
    _early_stop_flag = False
    _cancel_flag = False

    # Check custom test hook first
    if _custom_recorder is not None:
        rec_duration = duration if duration is not None else get_recording_duration()
        rec_device = device if device is not None else get_configured_mic_device()
        if on_start:
            on_start()
        return _custom_recorder(duration=rec_duration, device=rec_device, sample_rate=sample_rate)

    if sd is None or np is None:
        raise RuntimeError(
            "sounddevice ya numpy package installed nahi hai. Kripya requirements.txt install karein."
        )

    # 1. Resolve duration and silence threshold
    if duration is None:
        duration = get_recording_duration()
    else:
        duration = max(MIN_RECORDING_DURATION, min(MAX_RECORDING_DURATION, float(duration)))

    silence_thresh = get_silence_threshold()

    # 2. Resolve audio device
    if device is None:
        device = get_configured_mic_device()
    resolved_device = resolve_device(device)

    # 3. Check sample rate compatibility with selected device
    chosen_sample_rate = sample_rate
    try:
        sd.check_input_settings(
            device=resolved_device,
            samplerate=chosen_sample_rate,
            channels=1,
            dtype="int16",
        )
    except Exception:
        # Fall back to device default sample rate if 16000 is not supported
        try:
            dev_info = sd.query_devices(resolved_device, "input")
            chosen_sample_rate = int(dev_info.get("default_samplerate", 44100))
        except Exception:
            chosen_sample_rate = 44100

    # 4. Open microphone stream and record
    audio_frames: List[np.ndarray] = []
    chunk_size = 1024

    stream = None
    _is_recording_active = True
    try:
        stream = sd.InputStream(
            samplerate=chosen_sample_rate,
            channels=1,
            dtype="int16",
            device=resolved_device,
        )
        stream.start()

        # Stream is active; notify callback that recording has officially begun
        if on_start:
            on_start()

        start_time = time.time()
        while time.time() - start_time < duration:
            # Check for cancellation
            if _cancel_flag or (is_cancelled and is_cancelled()):
                return None, 0.0, True

            # Check for early stop (manual mic click to finish)
            if _early_stop_flag or (is_stopped and is_stopped()):
                break

            data, overflowed = stream.read(chunk_size)
            audio_frames.append(data.copy())

    except KeyboardInterrupt:
        # User pressed Ctrl+C to cancel recording
        raise
    except Exception as e:
        # Device failure, permission error, or disconnected microphone
        raise RuntimeError(f"Microphone capture error ({type(e).__name__}): {e}") from e
    finally:
        _is_recording_active = False
        # CRITICAL: Always stop and close stream before proceeding to transcription
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    if _cancel_flag or (is_cancelled and is_cancelled()):
        return None, 0.0, True

    if not audio_frames:
        return b"", 0.0, True

    # 5. Process audio in memory
    concatenated = np.concatenate(audio_frames, axis=0)
    rms = compute_rms(concatenated)
    is_silent = rms < silence_thresh
    wav_bytes = audio_to_wav_bytes(concatenated, sample_rate=chosen_sample_rate)

    return wav_bytes, rms, is_silent
