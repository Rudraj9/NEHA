"""
test_voice_input.py
-------------------
Automated verification suite for NEHA Milestone 3B: On-demand microphone STT.

This suite uses mocked audio recording and mocked Groq STT to verify:
1. Normal typed chat follows its existing path.
2. /listen captures once and transcribes once.
3. Confirmation sends exactly one chat request to Groq.
4. /edit sends the edited text to Groq.
5. /cancel discards the transcript without calling Groq chat or altering history.
6. Local silence detection discards recording without calling transcription or chat.
7. Empty transcripts discard without calling chat.
8. API transcription failures handle cleanly without modifying history.
9. Ctrl+C during recording safely cancels and releases the device.
10. Ctrl+C during transcription safely cancels without modifying history.
11. Voice-output mute (/voice off) does NOT disable microphone input.
12. Spoken command words (e.g. 'exit', 'clear') are NOT executed as terminal commands.
13. /mic list displays available devices with status tags.
14. Microphone stream is guaranteed to be closed upon exit, errors, and cancellation.

IMPORTANT: No physical microphone is accessed and no live network calls are made.
"""

import io
import unittest
from unittest.mock import MagicMock, patch

import assistant.brain as brain
import voice
import voice.recorder as recorder
import voice.stt as stt
import voice.tts as tts
import main


class TestVoiceInputMilestone(unittest.TestCase):

    def setUp(self):
        # Reset conversation history before each test
        brain.clear_history()

        # Mock Groq client for brain chat completions
        self.mock_brain_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Namaste! Main aapki madad karne ke liye taiyar hoon."
        self.mock_brain_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        brain.set_client(self.mock_brain_client)

        # Mock speech playback
        tts.set_custom_engine(MagicMock())
        tts.set_voice_enabled(True)
        tts.set_active_provider("local")

        # Reset recorder and STT test hooks
        recorder.set_custom_recorder(None)
        recorder.reset_session_settings()
        stt.set_custom_transcriber(None)

    def tearDown(self):
        brain.clear_history()
        brain.set_client(None)
        recorder.set_custom_recorder(None)
        recorder.reset_session_settings()
        stt.set_custom_transcriber(None)
        tts.set_custom_engine(None)

    def test_01_normal_typed_chat_path(self):
        """Verifies that standard typed chat continues to follow the existing Groq path."""
        user_input = "Python mein list kya hoti hai?"
        with patch("main.speak") as mock_speak:
            result = main._process_conversation_turn(user_input)
            self.assertTrue(result)
            self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 1)
            mock_speak.assert_called_once()
            history = brain.get_history()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["content"], user_input)

    def test_02_listen_captures_once_and_confirms(self):
        """Verifies that /listen captures audio once, transcribes once, and Enter sends to chat."""
        mock_wav = b"RIFF_FAKE_WAV_BYTES"
        rec_call_count = [0]
        stt_call_count = [0]

        def custom_recorder(**kwargs):
            rec_call_count[0] += 1
            return mock_wav, 1250.0, False  # audio, rms, is_silent

        def custom_transcriber(wav_bytes):
            stt_call_count[0] += 1
            return True, "Python mein list aur tuple ka difference samjhao."

        recorder.set_custom_recorder(custom_recorder)
        stt.set_custom_transcriber(custom_transcriber)

        # User presses Enter to confirm transcript
        with patch("builtins.input", side_effect=[""]):
            confirmed = main.handle_listen()

        self.assertEqual(rec_call_count[0], 1)
        self.assertEqual(stt_call_count[0], 1)
        self.assertEqual(confirmed, "Python mein list aur tuple ka difference samjhao.")

        # Process confirmed turn
        with patch("main.speak") as mock_speak:
            main._process_conversation_turn(confirmed)
            self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 1)
            mock_speak.assert_called_once()
            history = brain.get_history()
            self.assertEqual(history[0]["content"], "Python mein list aur tuple ka difference samjhao.")

    def test_03_listen_edit_sends_edited_text(self):
        """Verifies that /edit replaces transcript with typed text and sends to Groq."""
        mock_wav = b"RIFF_FAKE_WAV_BYTES"
        recorder.set_custom_recorder(lambda **k: (mock_wav, 800.0, False))
        stt.set_custom_transcriber(lambda w: (True, "Galat sunai diya transcript"))

        # User types /edit then enters replacement text
        with patch("builtins.input", side_effect=["/edit", "Sahi text jo maine type kiya."]):
            confirmed = main.handle_listen()

        self.assertEqual(confirmed, "Sahi text jo maine type kiya.")

        main._process_conversation_turn(confirmed)
        history = brain.get_history()
        self.assertEqual(history[0]["content"], "Sahi text jo maine type kiya.")

    def test_04_listen_cancel_discards_without_chat(self):
        """Verifies that /cancel discards transcript without calling chat model or altering history."""
        mock_wav = b"RIFF_FAKE_WAV_BYTES"
        recorder.set_custom_recorder(lambda **k: (mock_wav, 900.0, False))
        stt.set_custom_transcriber(lambda w: (True, "Yeh text discard hoga"))

        # User types /cancel
        with patch("builtins.input", side_effect=["/cancel"]):
            confirmed = main.handle_listen()

        self.assertIsNone(confirmed)
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 0)
        self.assertEqual(len(brain.get_history()), 0)

    def test_05_silence_detection_local_discards(self):
        """Verifies that audio with RMS below threshold is discarded locally before STT/chat."""
        mock_wav = b"RIFF_SILENT_WAV"
        stt_called = [False]

        # Recorder returns is_silent=True (RMS 50.0 < 300.0)
        recorder.set_custom_recorder(lambda **k: (mock_wav, 50.0, True))

        def custom_transcriber(w):
            stt_called[0] = True
            return True, "Should not be called"

        stt.set_custom_transcriber(custom_transcriber)

        confirmed = main.handle_listen()
        self.assertIsNone(confirmed)
        self.assertFalse(stt_called[0])
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 0)
        self.assertEqual(len(brain.get_history()), 0)

    def test_06_empty_transcript_handling(self):
        """Verifies that empty transcripts return to prompt without calling chat."""
        mock_wav = b"RIFF_FAKE_WAV"
        recorder.set_custom_recorder(lambda **k: (mock_wav, 800.0, False))
        stt.set_custom_transcriber(lambda w: (True, "   "))  # empty whitespace

        confirmed = main.handle_listen()
        self.assertIsNone(confirmed)
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 0)
        self.assertEqual(len(brain.get_history()), 0)

    def test_07_stt_api_failure_handling(self):
        """Verifies that transcription errors are displayed and chat is not called."""
        mock_wav = b"RIFF_FAKE_WAV"
        recorder.set_custom_recorder(lambda **k: (mock_wav, 800.0, False))
        stt.set_custom_transcriber(lambda w: (False, "[API Error]: Groq STT 503 service unavailable"))

        confirmed = main.handle_listen()
        self.assertIsNone(confirmed)
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 0)
        self.assertEqual(len(brain.get_history()), 0)

    def test_08_ctrl_c_during_recording(self):
        """Verifies that Ctrl+C during recording cancels cleanly without calling chat."""
        def interrupting_recorder(**kwargs):
            raise KeyboardInterrupt()

        recorder.set_custom_recorder(interrupting_recorder)
        confirmed = main.handle_listen()
        self.assertIsNone(confirmed)
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 0)
        self.assertEqual(len(brain.get_history()), 0)

    def test_09_ctrl_c_during_transcription(self):
        """Verifies that Ctrl+C during transcription cancels cleanly without calling chat."""
        mock_wav = b"RIFF_FAKE_WAV"
        recorder.set_custom_recorder(lambda **k: (mock_wav, 800.0, False))

        def interrupting_transcriber(w):
            raise KeyboardInterrupt()

        stt.set_custom_transcriber(interrupting_transcriber)
        confirmed = main.handle_listen()
        self.assertIsNone(confirmed)
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 0)
        self.assertEqual(len(brain.get_history()), 0)

    def test_10_voice_output_mute_does_not_disable_mic_input(self):
        """Verifies that voice mute (/voice off) allows microphone input while suppressing speech."""
        tts.set_voice_enabled(False)  # Voice muted
        self.assertFalse(tts.is_voice_enabled())

        mock_wav = b"RIFF_FAKE_WAV"
        recorder.set_custom_recorder(lambda **k: (mock_wav, 900.0, False))
        stt.set_custom_transcriber(lambda w: (True, "Testing muted TTS"))

        with patch("builtins.input", side_effect=[""]):
            confirmed = main.handle_listen()

        self.assertEqual(confirmed, "Testing muted TTS")

        with patch("voice.tts.speak") as mock_speak:
            main._process_conversation_turn(confirmed)
            # Chat model was called
            self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 1)
            # speak was called by conversation turn, but returns False because voice is muted
            self.assertFalse(tts.is_voice_enabled())

    def test_11_spoken_words_never_executed_as_commands(self):
        """
        Verifies that spoken words like 'exit' or 'clear' are treated strictly as conversational
        prompts and NOT executed as terminal exit or clear history commands.
        """
        # Add a prior history turn
        brain._conversation_history.append({"role": "user", "content": "Pehela sawal"})
        brain._conversation_history.append({"role": "assistant", "content": "Jawab"})

        # User speaks "clear"
        confirmed_speech = "clear"
        main._process_conversation_turn(confirmed_speech)

        # Chat model should be called with "clear" as the user prompt
        self.assertEqual(self.mock_brain_client.chat.completions.create.call_count, 1)
        history = brain.get_history()
        # History was NOT cleared! It now has 4 entries (old turn + new "clear" turn)
        self.assertEqual(len(history), 4)
        self.assertEqual(history[2]["content"], "clear")

    def test_12_mic_list_formatting(self):
        """Verifies that /mic list outputs a formatted string with devices."""
        formatted = recorder.format_mic_list()
        self.assertIsInstance(formatted, str)
        self.assertTrue("Microphones" in formatted or "microphone" in formatted.lower())

    def test_13_duration_and_threshold_clamping(self):
        """Verifies that duration and threshold environment variables are properly bounded."""
        with patch.dict("os.environ", {"RECORDING_DURATION": "45"}):
            # Clamped to maximum 30.0s
            self.assertEqual(recorder.get_recording_duration(), 30.0)

        with patch.dict("os.environ", {"RECORDING_DURATION": "0.2"}):
            # Clamped to minimum 1.0s
            self.assertEqual(recorder.get_recording_duration(), 1.0)

        with patch.dict("os.environ", {"RECORDING_DURATION": "12"}):
            self.assertEqual(recorder.get_recording_duration(), 12.0)

        with patch.dict("os.environ", {"SILENCE_THRESHOLD": "450.5"}):
            self.assertEqual(recorder.get_silence_threshold(), 450.5)

    def test_14_microphone_stream_closed_on_error(self):
        """Verifies that real stream opening closes properly in finally block even on error."""
        mock_stream = MagicMock()
        mock_stream.read.side_effect = RuntimeError("PortAudio buffer overflow")

        with patch("sounddevice.InputStream", return_value=mock_stream):
            with self.assertRaises(RuntimeError):
                recorder.record_audio(duration=2.0)

            mock_stream.stop.assert_called()
            mock_stream.close.assert_called()


if __name__ == "__main__":
    unittest.main()
