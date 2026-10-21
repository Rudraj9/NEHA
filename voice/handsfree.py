"""
voice/handsfree.py
------------------
Hands-free voice coordinator and state machine for NEHA Assistant.

State Machine:
  HANDS_FREE_OFF -> WAITING_FOR_WAKE -> ACKNOWLEDGING -> LISTENING ->
  RECORDING -> TRANSCRIBING -> GENERATING -> SPEAKING -> FOLLOW_UP ->
  (back to LISTENING or WAITING_FOR_WAKE)

Coordinated Audio Stream:
- Single audio owner: Mic is opened only when listening/waiting, and strictly
  PAUSED/MUTED during acknowledgment, transcription, generation, and speech playback.
- Prevents self-triggering or echo from assistant's own voice.
- Preserves pre-roll audio so initial words are never clipped.
- Enforces single active conversation turn with thread-safe cancellation.
"""

import enum
import logging
import threading
import time
from typing import Optional, Callable, Dict, Any, Tuple

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except ImportError:
    sd = None

from . import recorder
from . import stt
from . import tts
from . import ack
from . import vad
from . import wake

logger = logging.getLogger("neha_handsfree")


class HandsFreeState(str, enum.Enum):
    HANDS_FREE_OFF = "hands_free_off"
    WAITING_FOR_WAKE = "waiting_for_wake"
    ACKNOWLEDGING = "acknowledging"
    LISTENING = "listening"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    GENERATING = "generating"
    SPEAKING = "speaking"
    FOLLOW_UP = "follow_up"
    ERROR = "error"


class HandsFreeCoordinator:
    """
    Manages background hands-free listening, wake-word detection,
    automatic voice activity detection, and conversation handoff.
    """

    def __init__(
        self,
        on_state_change: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_user_transcript: Optional[Callable[[str], None]] = None,
        on_assistant_turn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._state = HandsFreeState.HANDS_FREE_OFF
        self._lock = threading.RLock()
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._turn_generation: int = 0
        self._wake_debounce_time: float = 0.0

        # Event callbacks
        self._on_state_change = on_state_change
        self._on_user_transcript = on_user_transcript
        self._on_assistant_turn = on_assistant_turn

        # Audio stream control
        self._current_stream = None
        self._detector: Optional[wake.PorcupineWakeDetector] = None

    @property
    def state(self) -> HandsFreeState:
        with self._lock:
            return self._state

    def is_active(self) -> bool:
        with self._lock:
            return self._state != HandsFreeState.HANDS_FREE_OFF

    def _set_state(self, new_state: HandsFreeState, extra: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._state = new_state
            logger.info("HandsFree state: %s", new_state.value)

        if self._on_state_change:
            payload = {"state": new_state.value}
            if extra:
                payload.update(extra)
            try:
                self._on_state_change(new_state.value, payload)
            except Exception as e:
                logger.error("Error in on_state_change callback: %s", e)

    def start(self) -> Tuple[bool, str]:
        """
        Enables hands-free mode.
        Validates wake-word configuration and starts background coordinator.
        """
        with self._lock:
            if self._state != HandsFreeState.HANDS_FREE_OFF:
                return True, "Hands-free already running."

            # Verify wake-word readiness
            availability = wake.check_wake_word_availability()
            if not availability["available"]:
                checklist_msg = "\n".join(availability.get("checklist", []))
                return False, f"Wake word unavailable: {'; '.join(availability.get('missing', []))}\n{checklist_msg}"

            self._stop_event.clear()
            self._turn_generation += 1
            self._set_state(HandsFreeState.WAITING_FOR_WAKE, {
                "message": "Waiting for 'Hi NEHA'...",
                "mic_active": True,
            })
            self._worker_thread = threading.Thread(
                target=self._run_coordinator_loop,
                name="NehaHandsFreeWorker",
                daemon=True,
            )
            self._worker_thread.start()
            return True, "Hands-free enabled."

    def stop(self) -> None:
        """
        Disables hands-free mode immediately and releases audio resources.
        """
        with self._lock:
            self._stop_event.set()
            self._turn_generation += 1

            if self._current_stream is not None:
                try:
                    self._current_stream.stop()
                    self._current_stream.close()
                except Exception:
                    pass
                self._current_stream = None

            if self._detector is not None:
                try:
                    self._detector.close()
                except Exception:
                    pass
                self._detector = None

            self._set_state(HandsFreeState.HANDS_FREE_OFF, {"message": "Hands-free disabled."})

    def interrupt_speech(self) -> None:
        """Stops assistant speech and safely transitions to waiting state."""
        with self._lock:
            tts.stop_speech()
            if self._state in (HandsFreeState.SPEAKING, HandsFreeState.GENERATING):
                self._turn_generation += 1
                if self.is_active():
                    self._set_state(HandsFreeState.WAITING_FOR_WAKE, {"notice": "Speech interrupted."})

    def reset_conversation(self) -> None:
        """Invalidates pending turn and returns to wake-word waiting."""
        with self._lock:
            self._turn_generation += 1
            tts.stop_speech()
            if self.is_active():
                self._set_state(HandsFreeState.WAITING_FOR_WAKE, {"notice": "Conversation reset."})

    # --------------------------------------------------------------------------
    # Main Coordinator Execution Loop
    # --------------------------------------------------------------------------

    def _run_coordinator_loop(self) -> None:
        """Continuous supervisor loop running on the worker thread."""
        logger.info("HandsFree worker thread started.")
        gen = self._turn_generation

        while not self._stop_event.is_set():
            try:
                # 1. WAITING_FOR_WAKE
                self._set_state(HandsFreeState.WAITING_FOR_WAKE, {
                    "message": "Waiting for 'Hi NEHA'...",
                    "mic_active": True,
                })

                wake_detected = self._listen_for_wake_word(gen)
                if not wake_detected or self._stop_event.is_set() or gen != self._turn_generation:
                    continue

                # Debounce check (1.5s)
                now = time.time()
                if now - self._wake_debounce_time < 1.5:
                    time.sleep(0.3)
                    continue
                self._wake_debounce_time = now

                # 2. Wake detected -> Enter conversation turn
                self._execute_conversation_turn(gen, is_follow_up=False)

            except Exception as e:
                logger.exception("Unexpected error in HandsFree loop: %s", e)
                if not self._stop_event.is_set():
                    self._set_state(HandsFreeState.ERROR, {"error": str(e)})
                    time.sleep(2.0)

        logger.info("HandsFree worker thread exited.")

    def _listen_for_wake_word(self, gen: int) -> bool:
        """
        Opens microphone stream and processes audio with Porcupine wake-word spotter.
        Returns True when 'Hi NEHA' is recognized.
        """
        try:
            detector = wake.PorcupineWakeDetector()
            self._detector = detector
        except Exception as e:
            logger.error("Failed to create PorcupineWakeDetector: %s", e)
            self._set_state(HandsFreeState.ERROR, {"error": f"Wake engine init error: {e}"})
            time.sleep(2.0)
            return False

        frame_len = detector.frame_length
        sample_rate = detector.sample_rate
        device_spec = recorder.get_configured_mic_device()
        resolved_dev = recorder.resolve_device(device_spec)

        detected_flag = [False]

        def _audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug("SoundDevice status: %s", status)
            if self._stop_event.is_set() or gen != self._turn_generation:
                return

            pcm = indata[:, 0]
            if detector.process(pcm):
                detected_flag[0] = True

        try:
            if sd is not None:
                with sd.InputStream(
                    samplerate=sample_rate,
                    blocksize=frame_len,
                    device=resolved_dev,
                    channels=1,
                    dtype="int16",
                    callback=_audio_callback,
                ) as stream:
                    self._current_stream = stream
                    while not self._stop_event.is_set() and gen == self._turn_generation:
                        if detected_flag[0]:
                            return True
                        time.sleep(0.04)
            else:
                # Fallback for environments without sounddevice
                time.sleep(0.5)
        except Exception as e:
            logger.error("Microphone stream error in wake-word detection: %s", e)
            self._set_state(HandsFreeState.ERROR, {"error": f"Microphone error: {e}"})
            time.sleep(2.0)
            return False
        finally:
            self._current_stream = None
            if self._detector:
                self._detector.close()
                self._detector = None

        return False

    def _execute_conversation_turn(self, gen: int, is_follow_up: bool = False) -> None:
        """
        Executes a single conversational turn:
        Acknowledgment -> VAD Listening -> STT -> Groq Chat -> TTS -> Follow-up Window.
        """
        # Step A: Acknowledgment (only on initial wake detection, not follow-up)
        if not is_follow_up:
            self._set_state(HandsFreeState.ACKNOWLEDGING, {
                "message": "Haan Rocky, bolo.",
                "mic_active": False,
            })
            # Play fixed acknowledgment synchronously. Audio stream is CLOSED.
            try:
                ack.play_acknowledgment()
            except Exception as e:
                logger.warning("Acknowledgment playback error: %s", e)

        if self._stop_event.is_set() or gen != self._turn_generation:
            return

        # Step B: VAD Speech Capture
        self._set_state(
            HandsFreeState.LISTENING if not is_follow_up else HandsFreeState.FOLLOW_UP,
            {
                "message": "Listening for your question..." if not is_follow_up else "Listening for follow-up...",
                "mic_active": True,
            },
        )

        speech_wav = self._capture_speech_with_vad(gen, is_follow_up=is_follow_up)
        if self._stop_event.is_set() or gen != self._turn_generation:
            return

        # If silence or noise was rejected
        if not speech_wav:
            if is_follow_up:
                # Follow-up expired with silence: return quietly to waiting for "Hi NEHA"
                return
            else:
                self._set_state(HandsFreeState.WAITING_FOR_WAKE, {
                    "notice": "Koi aawaaz detect nahi hui. Waiting for 'Hi NEHA'...",
                })
                return

        # Step C: Transcribing Speech
        self._set_state(HandsFreeState.TRANSCRIBING, {
            "message": "Transcribing speech...",
            "mic_active": False,
        })

        try:
            success, transcript = stt.transcribe_audio(speech_wav)
        except Exception as e:
            success = False
            transcript = f"Transcription error: {e}"

        if self._stop_event.is_set() or gen != self._turn_generation:
            return

        if not success or not transcript.strip():
            self._set_state(HandsFreeState.WAITING_FOR_WAKE, {
                "notice": "Transcript khali tha ya samajh nahi aaya.",
            })
            return

        clean_transcript = transcript.strip()
        logger.info("Recognized HandsFree transcript: %s", clean_transcript)

        # Notify UI of user transcript
        if self._on_user_transcript:
            self._on_user_transcript(clean_transcript)

        # Step D: Generating LLM Response & Speaking
        self._set_state(HandsFreeState.GENERATING, {
            "message": "Thinking...",
            "mic_active": False,
        })

        # Delegate turn execution to controller callback
        if self._on_assistant_turn:
            self._on_assistant_turn(clean_transcript)

        # Step E: Follow-Up Window
        if not self._stop_event.is_set() and gen == self._turn_generation:
            follow_up_timeout = vad.get_vad_setting("follow_up_timeout", vad.DEFAULT_FOLLOW_UP_TIMEOUT)
            self._set_state(HandsFreeState.FOLLOW_UP, {
                "message": f"Follow-up window ({follow_up_timeout:.1f}s)...",
                "mic_active": True,
            })
            # Re-enter turn with follow-up mode
            self._execute_conversation_turn(gen, is_follow_up=True)

    def _capture_speech_with_vad(self, gen: int, is_follow_up: bool = False) -> Optional[bytes]:
        """
        Streams microphone input through the VoiceActivityDetector until endpointing
        or timeout is reached.
        """
        sample_rate = 16000
        frame_ms = 30
        frame_len = int((sample_rate * frame_ms) / 1000)  # 480 samples

        start_timeout = (
            vad.get_vad_setting("follow_up_timeout", vad.DEFAULT_FOLLOW_UP_TIMEOUT)
            if is_follow_up
            else vad.get_vad_setting("speech_start_timeout", vad.DEFAULT_SPEECH_START_TIMEOUT)
        )

        detector = vad.VoiceActivityDetector(
            sample_rate=sample_rate,
            frame_ms=frame_ms,
            speech_start_timeout=start_timeout,
        )

        device_spec = recorder.get_configured_mic_device()
        resolved_dev = recorder.resolve_device(device_spec)

        audio_chunks = []
        is_done = [False]
        speech_started_ui = [False]

        def _vad_callback(indata, frames, time_info, status):
            if self._stop_event.is_set() or gen != self._turn_generation:
                return

            pcm_frame = indata[:, 0]
            continue_recording = detector.process_frame(pcm_frame)

            if detector.speech_started and not speech_started_ui[0]:
                speech_started_ui[0] = True
                self._set_state(HandsFreeState.RECORDING, {
                    "message": "Recording your question...",
                    "mic_active": True,
                })

            if not continue_recording:
                is_done[0] = True

        try:
            if sd is not None:
                with sd.InputStream(
                    samplerate=sample_rate,
                    blocksize=frame_len,
                    device=resolved_dev,
                    channels=1,
                    dtype="int16",
                    callback=_vad_callback,
                ) as stream:
                    self._current_stream = stream
                    while not is_done[0] and not self._stop_event.is_set() and gen == self._turn_generation:
                        time.sleep(0.03)
        except Exception as e:
            logger.error("VAD microphone stream failure: %s", e)
            return None
        finally:
            self._current_stream = None

        captured = detector.get_captured_audio()
        if captured is None or len(captured) == 0:
            return None

        # Encode to standard 16-bit PCM WAV in memory
        return recorder.audio_to_wav_bytes(captured, sample_rate=sample_rate)
