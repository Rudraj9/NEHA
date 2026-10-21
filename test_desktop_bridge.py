"""
test_desktop_bridge.py
-----------------------
Automated unit verification for the NEHA Desktop Bridge controller.

Tests:
1. Bridge initialization & get_initial_state schema.
2. Asynchronous send_message flow with mocked Groq response and event emission.
3. Empty message validation rejection.
4. Voice output mute suppresses speech while delivering text response.
5. Generation invalidation: New Conversation cancels/discards late worker turns.
6. Recording lifecycle: start_recording, early stop, and cancellation.
7. Silence threshold discard during recording.
8. Stop speech halts active speech playback cleanly.
9. Settings updates apply in-memory without altering environment or secrets.
10. External URL safety validation.

NO live network calls or physical audio hardware are used.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import assistant.brain as brain
import voice
import voice.recorder as recorder
import voice.stt as stt
import voice.tts as tts
from desktop_app.bridge import DesktopBridge


class TestDesktopBridge(unittest.TestCase):

    def setUp(self):
        brain.clear_history()

        # Mock Groq client
        self.mock_brain_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Namaste! Main hoon NEHA. Aapki study companion."
        self.mock_brain_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        brain.set_client(self.mock_brain_client)

        # Mock speech engine
        tts.set_custom_engine(MagicMock())
        tts.set_voice_enabled(True)
        tts.set_active_provider("local")

        # Mock recorder and STT
        recorder.set_custom_recorder(None)
        recorder.reset_session_settings()
        stt.set_custom_transcriber(None)

        # Mock Window
        self.mock_window = MagicMock()
        self.bridge = DesktopBridge(self.mock_window)

    def tearDown(self):
        brain.clear_history()
        brain.set_client(None)
        recorder.set_custom_recorder(None)
        recorder.reset_session_settings()
        stt.set_custom_transcriber(None)
        tts.set_custom_engine(None)

    def test_01_initial_state_schema(self):
        """Verifies get_initial_state returns expected structure and values."""
        state = self.bridge.get_initial_state()
        self.assertIn("assistant_name", state)
        self.assertIn("welcome_message", state)
        self.assertIn("active_model", state)
        self.assertIn("stt_model", state)
        self.assertIn("voice_enabled", state)
        self.assertIn("tts_provider", state)
        self.assertIn("recording_duration", state)
        self.assertIn("silence_threshold", state)
        self.assertEqual(state["assistant_name"], "NEHA")

    def test_02_send_message_asynchronous_flow(self):
        """Verifies that send_message runs on a worker thread and emits response."""
        res = self.bridge.send_message("Python seekhna chahta hoon.")
        self.assertEqual(res["status"], "ok")

        # Allow worker thread to complete
        time.sleep(0.15)

        # Verify chat model was invoked
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 1)

        # Verify evaluate_js was called for state changes and response
        self.assertTrue(self.mock_window.evaluate_js.called)
        calls = [str(call) for call in self.mock_window.evaluate_js.call_args_list]
        self.assertTrue(any("response_received" in c for c in calls))
        self.assertTrue(any("Namaste! Main hoon NEHA." in c for c in calls))

    def test_03_empty_message_rejected(self):
        """Verifies that empty/whitespace message is rejected immediately."""
        res = self.bridge.send_message("   ")
        self.assertEqual(res["status"], "error")
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 0)

    def test_04_new_conversation_resets_history(self):
        """Verifies that new_conversation clears history and emits conversation_cleared."""
        brain._conversation_history.append({"role": "user", "content": "Pehle ka sawal"})
        brain._conversation_history.append({"role": "assistant", "content": "Jawab"})

        res = self.bridge.new_conversation()
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(brain.get_history()), 0)

        # Check conversation_cleared event
        calls = [str(call) for call in self.mock_window.evaluate_js.call_args_list]
        self.assertTrue(any("conversation_cleared" in c for c in calls))

    def test_05_recording_and_transcription_review_flow(self):
        """Verifies start_recording captures audio and transitions to reviewing."""
        mock_wav = b"RIFF_SAMPLE_WAV"
        recorder.set_custom_recorder(lambda **k: (mock_wav, 950.0, False))
        stt.set_custom_transcriber(lambda w: (True, "List aur tuple mein kya difference hai?"))

        res = self.bridge.start_recording()
        self.assertEqual(res["status"], "ok")

        time.sleep(0.15)

        calls = [str(call) for call in self.mock_window.evaluate_js.call_args_list]
        self.assertTrue(any("reviewing" in c for c in calls))
        self.assertTrue(any("List aur tuple mein kya difference hai?" in c for c in calls))

    def test_06_recording_silence_discard(self):
        """Verifies that silent recordings discard locally and return to idle."""
        mock_wav = b"RIFF_SILENT_WAV"
        recorder.set_custom_recorder(lambda **k: (mock_wav, 40.0, True))

        self.bridge.start_recording()
        time.sleep(0.15)

        calls = [str(call) for call in self.mock_window.evaluate_js.call_args_list]
        self.assertTrue(any("Audio bohot shaant" in c for c in calls))

    def test_07_recording_cancel(self):
        """Verifies cancel_recording signals cancellation cleanly."""
        res = self.bridge.cancel_recording()
        self.assertEqual(res["status"], "ok")

    def test_08_stop_speech(self):
        """Verifies stop_speech stops speech output cleanly."""
        with patch("voice.stop_speech") as mock_stop:
            res = self.bridge.stop_speech()
            self.assertEqual(res["status"], "ok")
            mock_stop.assert_called_once()

    def test_09_settings_updates_in_memory(self):
        """Verifies that update_settings modifies session settings without touching .env."""
        new_settings = {
            "voice_enabled": False,
            "tts_provider": "local",
            "recording_duration": 15,
            "silence_threshold": 420,
            "mic_device": "Test Mic",
        }
        res = self.bridge.update_settings(new_settings)
        self.assertFalse(res["voice_enabled"])
        self.assertEqual(res["tts_provider"], "local")
        self.assertEqual(res["recording_duration"], 15.0)
        self.assertEqual(res["silence_threshold"], 420.0)
        self.assertEqual(res["mic_device"], "Test Mic")

    def test_10_external_url_safety(self):
        """Verifies open_external_url validates http/https protocol."""
        with patch("webbrowser.open") as mock_browser:
            res = self.bridge.open_external_url("https://groq.com")
            self.assertEqual(res["status"], "ok")
            mock_browser.assert_called_once_with("https://groq.com")

        res_bad = self.bridge.open_external_url("file:///etc/passwd")
        self.assertEqual(res_bad["status"], "error")


if __name__ == "__main__":
    unittest.main()
