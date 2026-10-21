"""
voice package initialization.
Exports speech synthesis (TTS), microphone capture (recorder), speech-to-text (STT),
voice activity detection (VAD), wake-word detection, acknowledgment, and hands-free coordination.
"""

from .tts import (
    speak,
    is_voice_enabled,
    set_voice_enabled,
    get_voice_status,
    stop_speech,
    init_engine,
    set_custom_engine,
    get_active_provider,
    set_active_provider,
    is_speaking,
)

from .recorder import (
    record_audio,
    list_input_devices,
    format_mic_list,
    get_configured_mic_device,
    get_recording_duration,
    get_silence_threshold,
    set_custom_recorder,
    stop_recording_early,
    cancel_recording,
    is_recording,
    set_recording_duration,
    set_silence_threshold,
    set_mic_device,
    audio_to_wav_bytes,
    compute_rms,
)

from .stt import (
    transcribe_audio,
    get_stt_model,
    get_stt_language,
    set_custom_transcriber,
)

from .vad import (
    VoiceActivityDetector,
    get_vad_setting,
    set_vad_session_setting,
)

from .wake import (
    check_wake_word_availability,
    PorcupineWakeDetector,
    set_custom_wake_detector,
)

from .ack import (
    play_acknowledgment,
    invalidate_ack_cache,
    set_custom_ack_player,
)

from .handsfree import (
    HandsFreeCoordinator,
    HandsFreeState,
)

__all__ = [
    # Speech synthesis (TTS)
    "speak",
    "is_voice_enabled",
    "set_voice_enabled",
    "get_voice_status",
    "stop_speech",
    "init_engine",
    "set_custom_engine",
    "get_active_provider",
    "set_active_provider",
    "is_speaking",
    # Microphone capture (Recorder)
    "record_audio",
    "list_input_devices",
    "format_mic_list",
    "get_configured_mic_device",
    "get_recording_duration",
    "get_silence_threshold",
    "set_custom_recorder",
    "stop_recording_early",
    "cancel_recording",
    "is_recording",
    "set_recording_duration",
    "set_silence_threshold",
    "set_mic_device",
    "audio_to_wav_bytes",
    "compute_rms",
    # Speech-to-text (STT)
    "transcribe_audio",
    "get_stt_model",
    "get_stt_language",
    "set_custom_transcriber",
    # Voice Activity Detection (VAD)
    "VoiceActivityDetector",
    "get_vad_setting",
    "set_vad_session_setting",
    # Wake Word
    "check_wake_word_availability",
    "PorcupineWakeDetector",
    "set_custom_wake_detector",
    # Acknowledgment
    "play_acknowledgment",
    "invalidate_ack_cache",
    "set_custom_ack_player",
    # Hands-free Coordinator
    "HandsFreeCoordinator",
    "HandsFreeState",
]
