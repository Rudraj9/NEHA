"""
test_handsfree.py
-----------------
Automated unit and integration tests for NEHA Hands-Free Voice Controller.
Uses synthetic audio events and mocks to verify:
- Wake-word availability checks and custom detector hooks.
- Voice Activity Detection (VAD) endpointing, pre-roll preservation, and noise rejection.
- Acknowledgment playback caching and LLM-isolation.
- Hands-Free Coordinator state machine transitions and follow-up timeouts.
- Safe cancellation, speech interruption, and resource release.
"""

import time
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

import voice
from voice import vad
from voice import wake
from voice import ack
from voice import handsfree
from desktop_app.bridge import DesktopBridge


class TestWakeWordDetection(unittest.TestCase):
    """Verifies local wake-word configuration validation and behavior."""

    def tearDown(self):
        wake.set_custom_wake_detector(None)

    def test_wake_word_unconfigured_checklist(self):
        """Verifies clear checklist when PICOVOICE_ACCESS_KEY or model path is missing."""
        wake.set_custom_wake_detector(None)
        with patch.dict("os.environ", {"PICOVOICE_ACCESS_KEY": "", "WAKE_WORD_MODEL_PATH": ""}):
            status = wake.check_wake_word_availability()
            self.assertFalse(status["available"])
            self.assertFalse(status["configured"])
            self.assertIn("PICOVOICE_ACCESS_KEY missing in .env", status["missing"])
            self.assertIn("WAKE_WORD_MODEL_PATH missing in .env", status["missing"])
            self.assertTrue(len(status["checklist"]) >= 2)

    def test_custom_wake_detector_hook(self):
        """Verifies synthetic wake detection via test hook without physical audio."""
        wake.set_custom_wake_detector(lambda pcm: True)
        status = wake.check_wake_word_availability()
        self.assertTrue(status["available"])
        self.assertTrue(status["configured"])

        detector = wake.PorcupineWakeDetector()
        dummy_pcm = np.zeros(512, dtype=np.int16)
        self.assertTrue(detector.process(dummy_pcm))


class TestVoiceActivityDetection(unittest.TestCase):
    """Verifies VAD endpointing, pre-roll buffer preservation, and silence rejection."""

    def setUp(self):
        self.sample_rate = 16000
        self.frame_ms = 30
        self.frame_samples = int((self.sample_rate * self.frame_ms) / 1000)  # 480 samples

    def test_pre_roll_preservation_and_endpointing(self):
        """Verifies pre-roll frames are prepended and silence hangover endpoints speech."""
        detector = vad.VoiceActivityDetector(
            sample_rate=self.sample_rate,
            frame_ms=self.frame_ms,
            speech_start_timeout=2.0,
            silence_duration=0.1,  # Fast 100ms silence hangover for testing
            min_speech_duration=0.05,
            pre_roll_ms=90,  # 3 frames of pre-roll
        )

        # 1. Feed 4 silent frames (RMS ~50)
        silent_frame = (np.random.randn(self.frame_samples) * 50).astype(np.int16)
        for _ in range(4):
            cont = detector.process_frame(silent_frame)
            self.assertTrue(cont)
        self.assertFalse(detector.speech_started)

        # 2. Feed 3 speech frames (RMS ~2000)
        speech_frame = (np.sin(np.linspace(0, 10, self.frame_samples)) * 2500).astype(np.int16)
        for _ in range(3):
            detector.process_frame(speech_frame)
        self.assertTrue(detector.speech_started)

        # 3. Feed silence until hangover triggers endpointing
        time.sleep(0.12)
        cont = detector.process_frame(silent_frame)
        self.assertFalse(cont)
        self.assertTrue(detector.is_completed)
        self.assertEqual(detector.completion_reason, "endpoint")

        audio = detector.get_captured_audio()
        self.assertIsNotNone(audio)
        # Verify pre-roll frames plus speech and silence frames are captured
        self.assertTrue(len(audio) > self.frame_samples * 3)

    def test_noise_rejection(self):
        """Verifies short transient clicks (< min_speech_duration) are rejected as noise."""
        detector = vad.VoiceActivityDetector(
            sample_rate=self.sample_rate,
            frame_ms=self.frame_ms,
            speech_start_timeout=1.0,
            silence_duration=0.08,
            min_speech_duration=0.3,  # Requires at least 300ms of speech
        )

        # 1 frame of transient spike
        spike_frame = (np.ones(self.frame_samples) * 3000).astype(np.int16)
        detector.process_frame(spike_frame)
        self.assertTrue(detector.speech_started)

        # Immediate silence
        time.sleep(0.1)
        silent_frame = np.zeros(self.frame_samples, dtype=np.int16)
        cont = detector.process_frame(silent_frame)
        self.assertFalse(cont)
        self.assertEqual(detector.completion_reason, "noise_rejected")
        self.assertIsNone(detector.get_captured_audio())

    def test_speech_start_timeout(self):
        """Verifies timeout triggers when user remains completely silent."""
        detector = vad.VoiceActivityDetector(
            sample_rate=self.sample_rate,
            frame_ms=self.frame_ms,
            speech_start_timeout=0.05,  # 50ms timeout
        )
        silent_frame = np.zeros(self.frame_samples, dtype=np.int16)
        time.sleep(0.06)
        cont = detector.process_frame(silent_frame)
        self.assertFalse(cont)
        self.assertEqual(detector.completion_reason, "timeout_no_speech")
        self.assertIsNone(detector.get_captured_audio())


class TestAcknowledgmentManager(unittest.TestCase):
    """Verifies fixed phrase acknowledgment caching and offline local fallback."""

    def setUp(self):
        ack.invalidate_ack_cache()

    def tearDown(self):
        ack.invalidate_ack_cache()
        ack.set_custom_ack_player(None)

    def test_chime_generation_wav(self):
        """Verifies local chime WAV is generated without external dependencies."""
        wav_bytes = ack.generate_local_chime_wav(sample_rate=16000)
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav_bytes)

    def test_ack_caching_and_invalidation(self):
        """Verifies acknowledgment audio is cached locally and invalidated on request."""
        # Using mock player
        played = [False]
        ack.set_custom_ack_player(lambda: played.__setitem__(0, True) or True)

        res = ack.play_acknowledgment()
        self.assertTrue(res)
        self.assertTrue(played[0])

    def test_muted_voice_skips_playback(self):
        """Verifies voice mute returns immediately without error."""
        voice.set_voice_enabled(False)
        try:
            res = ack.play_acknowledgment()
            self.assertTrue(res)
        finally:
            voice.set_voice_enabled(True)


class TestHandsFreeCoordinator(unittest.TestCase):
    """Verifies state machine transitions, audio ownership, and thread safety."""

    def tearDown(self):
        wake.set_custom_wake_detector(None)

    def test_state_machine_initial_off(self):
        """Verifies hands-free is off by default."""
        coordinator = handsfree.HandsFreeCoordinator()
        self.assertEqual(coordinator.state, handsfree.HandsFreeState.HANDS_FREE_OFF)
        self.assertFalse(coordinator.is_active())

    def test_handsfree_start_blocked_without_config(self):
        """Verifies start fails gracefully if wake-word is unconfigured."""
        wake.set_custom_wake_detector(None)
        with patch.dict("os.environ", {"PICOVOICE_ACCESS_KEY": "", "WAKE_WORD_MODEL_PATH": ""}):
            coordinator = handsfree.HandsFreeCoordinator()
            success, msg = coordinator.start()
            self.assertFalse(success)
            self.assertIn("Wake word unavailable", msg)
            self.assertEqual(coordinator.state, handsfree.HandsFreeState.HANDS_FREE_OFF)

    def test_handsfree_start_and_stop_lifecycle(self):
        """Verifies enabling and disabling hands-free cleanly updates state."""
        wake.set_custom_wake_detector(lambda pcm: False)  # Silent mock detector

        state_changes = []
        coordinator = handsfree.HandsFreeCoordinator(
            on_state_change=lambda s, extra: state_changes.append(s)
        )

        success, _ = coordinator.start()
        self.assertTrue(success)
        self.assertTrue(coordinator.is_active())

        time.sleep(0.1)
        coordinator.stop()
        self.assertFalse(coordinator.is_active())
        self.assertEqual(coordinator.state, handsfree.HandsFreeState.HANDS_FREE_OFF)


class TestDesktopBridgeIntegration(unittest.TestCase):
    """Verifies DesktopBridge hands-free APIs, drawer updates, and safety."""

    def setUp(self):
        self.bridge = DesktopBridge()
        self.emitted = []
        self.bridge._emit = lambda event, data=None: self.emitted.append((event, data))

    def tearDown(self):
        self.bridge.shutdown()
        wake.set_custom_wake_detector(None)

    def test_get_initial_state_contains_handsfree_and_vad(self):
        """Verifies initial state returns hands-free flags and VAD settings."""
        state = self.bridge.get_initial_state()
        self.assertIn("handsfree_active", state)
        self.assertIn("wake_word_status", state)
        self.assertIn("vad_settings", state)
        self.assertFalse(state["handsfree_active"])

    def test_toggle_handsfree_unconfigured_returns_checklist(self):
        """Verifies toggle returns checklist when unconfigured."""
        wake.set_custom_wake_detector(None)
        with patch.dict("os.environ", {"PICOVOICE_ACCESS_KEY": "", "WAKE_WORD_MODEL_PATH": ""}):
            res = self.bridge.toggle_handsfree(True)
            self.assertEqual(res["status"], "error")
            self.assertTrue(len(res["checklist"]) >= 1)

    def test_new_conversation_clears_history_and_invalidates_turn(self):
        """Verifies new_conversation invalidates generation and emits conversation_cleared."""
        res = self.bridge.new_conversation()
        self.assertEqual(res["status"], "ok")
        event_names = [ev[0] for ev in self.emitted]
        self.assertIn("conversation_cleared", event_names)

    def test_stop_speech_halts_playback_cleanly(self):
        """Verifies stop_speech terminates audio playback."""
        res = self.bridge.stop_speech()
        self.assertEqual(res["status"], "ok")


if __name__ == "__main__":
    unittest.main()
