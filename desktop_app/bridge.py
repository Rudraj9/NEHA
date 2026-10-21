"""
desktop_app/bridge.py
---------------------
Thread-safe JavaScript-to-Python bridge controller for the NEHA Desktop UI.

Features:
- Pure pywebview JS-API bridge (window.pywebview.api).
- Hands-Free Voice Controller:
  * Local wake-word ("Hi NEHA") coordination with Picovoice Porcupine.
  * Voice Activity Detection (VAD) endpointing with pre-roll buffer.
  * Spoken acknowledgment ("Haan Rocky, bolo") without LLM calls.
  * Multi-turn follow-up listening window.
  * Single coordinated audio owner ensuring no overlapping microphone streams.
- Serialized turn processing: Prevents duplicate requests and history race conditions.
- Generation tracking: Discards late callbacks after a New Conversation or reset.
- Asynchronous execution: Heavy LLM inference, recording, STT, and speech synthesis
  run on managed background threads so the UI never freezes.
- Thread-safe event emission via window.evaluate_js with JSON-marshaled payloads.
- Clean COM initialization for local SAPI5 worker threads.
- Comprehensive session-only settings management without touching .env.
- Security boundary: External links are handed to the system default browser.
"""

import json
import logging
import os
import threading
import webbrowser
from typing import Any, Dict, List, Optional

from assistant.personality import ASSISTANT_NAME, USER_NAME, WELCOME_MESSAGE
from assistant.brain import (
    get_response,
    clear_history,
    get_configured_model,
    is_error_response,
)
import voice

logger = logging.getLogger("neha_desktop_bridge")


class DesktopBridge:
    """
    Exposed Python API methods for pywebview.
    Accessible from JavaScript via `window.pywebview.api.<method>()`.
    """

    def __init__(self, window: Optional[Any] = None) -> None:
        self._window: Optional[Any] = window
        self._lock = threading.RLock()
        self._conversation_generation: int = 0
        self._current_state: str = "hands_free_off"
        self._is_shutting_down: bool = False

        # Hands-free Coordinator
        self._handsfree = voice.HandsFreeCoordinator(
            on_state_change=self._on_handsfree_state_change,
            on_user_transcript=self._on_handsfree_transcript,
            on_assistant_turn=self._on_handsfree_turn,
        )

    def set_window(self, window: Any) -> None:
        """Sets the pywebview Window reference for JS event dispatch."""
        self._window = window

    def shutdown(self) -> None:
        """Cleans up active resources when the desktop window closes."""
        self._is_shutting_down = True
        self._conversation_generation += 1
        self._handsfree.stop()
        voice.stop_speech()
        voice.cancel_recording()

    def _emit(self, event_name: str, data: Any = None) -> None:
        """
        Thread-safely pushes structured events to the JavaScript frontend.
        Marshals data safely as JSON to prevent script injection.
        """
        if self._window is None or self._is_shutting_down:
            return

        payload = json.dumps({"event": event_name, "data": data})
        script = f"if (window.__neha_on_event) {{ window.__neha_on_event({payload}); }}"
        try:
            self._window.evaluate_js(script)
        except Exception as e:
            logger.debug("Failed to evaluate_js (%s): %s", type(e).__name__, e)

    def _set_state(self, new_state: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Updates internal application state and notifies the UI."""
        self._current_state = new_state
        payload = {"state": new_state}
        if extra:
            payload.update(extra)
        self._emit("state_change", payload)

    # --------------------------------------------------------------------------
    # Hands-Free Coordinator Callbacks
    # --------------------------------------------------------------------------

    def _on_handsfree_state_change(self, state_str: str, extra: Dict[str, Any]) -> None:
        """Forward hands-free coordinator state changes directly to the UI."""
        self._set_state(state_str, extra)

    def _on_handsfree_transcript(self, transcript: str) -> None:
        """Pushes user transcript into chat history drawer without requiring confirmation."""
        self._emit("user_message", {
            "role": "user",
            "content": transcript,
            "source": "voice_handsfree",
        })

    def _on_handsfree_turn(self, clean_text: str) -> None:
        """Executes LLM inference and spoken answer for hands-free speech turn."""
        gen = self._conversation_generation
        if gen != self._conversation_generation or self._is_shutting_down:
            return

        try:
            response = get_response(clean_text)
        except Exception as e:
            response = f"[Unexpected Error]: Chat model communication issue: {type(e).__name__}"

        if gen != self._conversation_generation or self._is_shutting_down:
            return

        is_err = is_error_response(response)
        self._emit("response_received", {
            "role": "assistant",
            "content": response,
            "is_error": is_err,
        })

        if not is_err and voice.is_voice_enabled():
            self._set_state(voice.HandsFreeState.SPEAKING.value, {
                "message": "Speaking response...",
                "mic_active": False,
            })
            # Windows SAPI5 COM initialization on worker thread
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            try:
                voice.speak(response)
            finally:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    # --------------------------------------------------------------------------
    # Public Bridge Methods (Callable from JavaScript)
    # --------------------------------------------------------------------------

    def get_initial_state(self) -> Dict[str, Any]:
        """Returns the initial identity, configuration, handsfree, and device status."""
        active_model = get_configured_model()
        stt_model = voice.get_stt_model()
        provider = voice.get_active_provider()
        voice_on = voice.is_voice_enabled()
        duration = voice.get_recording_duration()
        silence_thresh = voice.get_silence_threshold()
        mic_dev = voice.get_configured_mic_device()
        wake_status = voice.check_wake_word_availability()

        vad_settings = {
            "speech_start_timeout": voice.get_vad_setting("speech_start_timeout", 6.0),
            "silence_duration": voice.get_vad_setting("silence_duration", 1.3),
            "min_speech_duration": voice.get_vad_setting("min_speech_duration", 0.45),
            "max_utterance_duration": voice.get_vad_setting("max_utterance_duration", 20.0),
            "follow_up_timeout": voice.get_vad_setting("follow_up_timeout", 4.5),
        }

        return {
            "assistant_name": ASSISTANT_NAME,
            "user_name": USER_NAME,
            "welcome_message": WELCOME_MESSAGE,
            "active_model": active_model,
            "stt_model": stt_model,
            "voice_enabled": voice_on,
            "tts_provider": provider,
            "sarvam_voice": os.environ.get("SARVAM_TTS_VOICE", "neha"),
            "recording_duration": duration,
            "silence_threshold": silence_thresh,
            "mic_device": str(mic_dev) if mic_dev is not None else "",
            "state": self._current_state,
            "is_speaking": voice.is_speaking(),
            "is_recording": voice.is_recording(),
            "handsfree_active": self._handsfree.is_active(),
            "wake_word_status": wake_status,
            "vad_settings": vad_settings,
        }

    def check_wake_word_config(self) -> Dict[str, Any]:
        """Explicit check for wake-word configuration and setup readiness."""
        return voice.check_wake_word_availability()

    def toggle_handsfree(self, enable: bool) -> Dict[str, Any]:
        """
        Enables or disables hands-free wake-word listening.
        If enabling without proper setup, returns actionable failure checklist.
        """
        if enable:
            if voice.is_recording():
                voice.cancel_recording()

            success, message = self._handsfree.start()
            if not success:
                status = voice.check_wake_word_availability()
                return {
                    "status": "error",
                    "message": message,
                    "checklist": status.get("checklist", []),
                    "missing": status.get("missing", []),
                }
            return {"status": "ok", "message": "Hands-free mode active."}
        else:
            self._handsfree.stop()
            self._set_state("hands_free_off", {"message": "Hands-free disabled."})
            return {"status": "ok", "message": "Hands-free mode disabled."}

    def send_message(self, text: str) -> Dict[str, Any]:
        """
        Sends a typed user message into the Groq conversation flow.
        Runs asynchronously on a background worker thread.
        """
        clean_text = text.strip() if text else ""
        if not clean_text:
            return {"status": "error", "message": "Khali message send nahi kiya ja sakta."}

        # If speech is playing, stop it first
        if voice.is_speaking():
            voice.stop_speech()
            self._handsfree.interrupt_speech()

        gen = self._conversation_generation

        # Emit user message to session chat drawer
        self._emit("user_message", {
            "role": "user",
            "content": clean_text,
            "source": "typed",
        })

        def _worker():
            with self._lock:
                if gen != self._conversation_generation or self._is_shutting_down:
                    return

                self._set_state("thinking")
                try:
                    response = get_response(clean_text)
                except Exception as e:
                    response = f"[Unexpected Error]: Chat model communication issue: {type(e).__name__}"

                if gen != self._conversation_generation or self._is_shutting_down:
                    return

                is_err = is_error_response(response)
                self._emit("response_received", {
                    "role": "assistant",
                    "content": response,
                    "is_error": is_err,
                })

                if not is_err and voice.is_voice_enabled():
                    self._set_state("speaking")
                    try:
                        import pythoncom
                        pythoncom.CoInitialize()
                    except Exception:
                        pass

                    try:
                        voice.speak(response)
                    finally:
                        try:
                            import pythoncom
                            pythoncom.CoUninitialize()
                        except Exception:
                            pass

                if gen == self._conversation_generation and not self._is_shutting_down:
                    if self._handsfree.is_active():
                        self._set_state(voice.HandsFreeState.WAITING_FOR_WAKE.value, {
                            "message": "Waiting for 'Hi NEHA'...",
                            "mic_active": True,
                        })
                    else:
                        self._set_state("idle")

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return {"status": "ok"}

    def start_recording(self) -> Dict[str, Any]:
        """
        Begins on-demand manual microphone capture (Click-to-talk fallback).
        """
        if voice.is_speaking():
            voice.stop_speech()
            self._handsfree.interrupt_speech()

        if voice.is_recording():
            return {"status": "error", "message": "Recording already active."}

        # If handsfree is active, pause it during manual recording
        was_handsfree = self._handsfree.is_active()
        if was_handsfree:
            self._handsfree.stop()

        gen = self._conversation_generation
        duration = voice.get_recording_duration()

        def _record_worker():
            self._set_state("recording", {"duration": duration})

            try:
                wav_bytes, rms, is_silent = voice.record_audio(
                    duration=duration,
                )
            except Exception as err:
                if gen == self._conversation_generation and not self._is_shutting_down:
                    self._set_state("idle", {
                        "error": f"Microphone error: {err}"
                    })
                return

            if gen != self._conversation_generation or self._is_shutting_down:
                return

            if wav_bytes is None:
                self._set_state("idle", {"notice": "Recording cancel kar di gayi."})
                return

            if is_silent or not wav_bytes:
                thresh = voice.get_silence_threshold()
                self._set_state("idle", {
                    "notice": f"Audio bohot shaant tha ya aawaaz detect nahi hui (RMS: {rms:.1f} < {thresh:.1f})."
                })
                return

            self._set_state("transcribing")
            try:
                success, transcript = voice.transcribe_audio(wav_bytes)
            except Exception as err:
                success = False
                transcript = f"Transcription failure: {err}"

            if gen != self._conversation_generation or self._is_shutting_down:
                return

            if not success:
                self._set_state("idle", {"error": transcript})
                return

            clean_transcript = transcript.strip()
            if not clean_transcript:
                self._set_state("idle", {"notice": "Koi shabdon ki pehchan nahi hui (empty transcript)."})
                return

            self._set_state("reviewing", {"transcript": clean_transcript})

        thread = threading.Thread(target=_record_worker, daemon=True)
        thread.start()
        return {"status": "ok"}

    def stop_recording_early(self) -> Dict[str, Any]:
        """Finalizes active manual recording early."""
        voice.stop_recording_early()
        return {"status": "ok"}

    def cancel_recording(self) -> Dict[str, Any]:
        """Aborts active manual recording and discards audio."""
        voice.cancel_recording()
        return {"status": "ok"}

    def stop_speech(self) -> Dict[str, Any]:
        """Halts active audio playback immediately while preserving response text."""
        voice.stop_speech()
        self._handsfree.interrupt_speech()
        if not self._handsfree.is_active():
            self._set_state("idle")
        return {"status": "ok"}

    def new_conversation(self) -> Dict[str, Any]:
        """Resets conversational memory and invalidates pending generation tasks."""
        self._conversation_generation += 1
        voice.stop_speech()
        voice.cancel_recording()
        self._handsfree.reset_conversation()
        clear_history()

        if self._handsfree.is_active():
            self._set_state(voice.HandsFreeState.WAITING_FOR_WAKE.value, {
                "message": "Waiting for 'Hi NEHA'...",
                "mic_active": True,
            })
        else:
            self._set_state("hands_free_off")

        self._emit("conversation_cleared")
        return {"status": "ok"}

    def get_mic_devices(self) -> List[Dict[str, Any]]:
        """Returns the list of input-capable audio devices."""
        return voice.list_input_devices()

    def update_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies session-only settings. Does not touch or overwrite .env.
        """
        if "voice_enabled" in settings:
            voice.set_voice_enabled(bool(settings["voice_enabled"]))

        if "tts_provider" in settings:
            provider = str(settings["tts_provider"]).strip().lower()
            if provider in ("sarvam", "local"):
                voice.set_active_provider(provider)
                voice.invalidate_ack_cache()

        if "mic_device" in settings:
            voice.set_mic_device(settings["mic_device"])

        if "recording_duration" in settings:
            try:
                voice.set_recording_duration(float(settings["recording_duration"]))
            except (ValueError, TypeError):
                pass

        if "silence_threshold" in settings:
            try:
                voice.set_silence_threshold(float(settings["silence_threshold"]))
            except (ValueError, TypeError):
                pass

        # VAD Settings
        for vad_key in ("speech_start_timeout", "silence_duration", "min_speech_duration", "max_utterance_duration", "follow_up_timeout"):
            if vad_key in settings:
                try:
                    voice.set_vad_session_setting(vad_key, float(settings[vad_key]))
                except (ValueError, TypeError):
                    pass

        return self.get_initial_state()

    def open_external_url(self, url: str) -> Dict[str, Any]:
        """Opens external hyperlinks in the user's default web browser."""
        safe_url = url.strip()
        if safe_url.startswith(("http://", "https://")):
            webbrowser.open(safe_url)
            return {"status": "ok"}
        return {"status": "error", "message": "Invalid URL protocol."}
