"""
main.py
-------
NEHA Assistant project ka main entry point.
Milestone 3B: Groq AI Integration + Multi-provider TTS + On-demand STT Microphone Input.

Features:
- Environment variable validation & credential guidance.
- Display welcome message with assistant identity, active LLM model, STT model, and voice controls.
- Interactive terminal chat loop with input validation.
- Commands:
  - 'clear' : resets session history
  - '/voice on', '/voice off', '/voice status' : controls text-to-speech
  - '/voice sarvam', '/voice local' : switches TTS engine
  - '/mic list' : lists available input microphones
  - '/listen' : on-demand speech recording with Groq transcription & review
  - 'exit' / 'quit' : terminates session cleanly
- Graceful handling of Ctrl+C (KeyboardInterrupt) and EOF (EOFError).
- Safe cleanup of audio speech resources on exit.
- Clean separation: Spoken words are never executed as terminal commands.
"""

import sys
from typing import Optional

from assistant.personality import ASSISTANT_NAME, USER_NAME, WELCOME_MESSAGE
from assistant.brain import (
    get_response,
    clear_history,
    validate_credentials,
    get_configured_model,
    is_error_response,
)
from voice import (
    speak,
    set_voice_enabled,
    get_voice_status,
    stop_speech,
    is_voice_enabled,
    set_active_provider,
    is_speaking,
    record_audio,
    list_input_devices,
    format_mic_list,
    transcribe_audio,
    get_recording_duration,
    get_silence_threshold,
    get_stt_model,
)


def _process_conversation_turn(user_text: str) -> bool:
    """
    Sends confirmed user input to the Groq brain and delivers the spoken response.
    Returns False if interrupted by user (Ctrl+C), True otherwise.
    """
    clean_text = user_text.strip()
    if not clean_text:
        return True

    response = get_response(clean_text)
    if response:
        # 1. Print AI response before speaking it
        print(f"\n{ASSISTANT_NAME} > {response}\n")

        # 2. Speak only successful responses (never read error prefixes aloud)
        if not is_error_response(response):
            try:
                speak(response)
            except KeyboardInterrupt:
                stop_speech()
                print(f"\n\nAlvida {USER_NAME}! NEHA session band ho raha hai.")
                return False
    return True


def handle_listen() -> Optional[str]:
    """
    Orchestrates the on-demand microphone input flow:
    1. Stops any active TTS playback to prevent audio feedback.
    2. Opens microphone and records audio for configurable duration (default 8s, max 30s).
    3. Closes microphone immediately after recording.
    4. Evaluates silence locally using RMS threshold.
    5. Transcribes speech using Groq's official Whisper API.
    6. Displays transcript for interactive review ([Enter] send, /edit, /cancel).
    7. Returns confirmed transcript text or None if cancelled/discarded.
    """
    # 1. Stop any ongoing speech playback before opening the microphone
    if is_speaking():
        stop_speech()
    stop_speech()

    duration = get_recording_duration()
    print(f"\n[{ASSISTANT_NAME} Recording]: Microphone initialize ho raha hai...")

    def on_recording_start() -> None:
        print(f"[{ASSISTANT_NAME} Recording]: Microphone active hai! Kripya boliye... ({int(duration)}s limit, Press Ctrl+C to cancel)")

    # 2. Record audio
    try:
        wav_bytes, rms, is_silent = record_audio(duration=duration, on_start=on_recording_start)
    except KeyboardInterrupt:
        print(f"\n[{ASSISTANT_NAME}]: Recording radd (cancelled) kar di gayi.\n")
        return None
    except Exception as err:
        print(f"\n[{ASSISTANT_NAME} Mic Error]: Microphone se audio capture nahi ho saka: {err}\n")
        return None

    print(f"[{ASSISTANT_NAME}]: Recording complete. Microphone band ho gaya.")

    # 3. Local Silence Check
    if is_silent or not wav_bytes:
        thresh = get_silence_threshold()
        print(
            f"\n[{ASSISTANT_NAME} Notice]: Audio bohot shaant (silent) tha ya aawaaz detect nahi hui (RMS: {rms:.1f} < threshold: {thresh:.1f}).\n"
            f"  Transcript discard kiya gaya. Kripya thoda tez boliye ya mic volume check karein.\n"
            f"  (Note: Yeh silence check approximate hai; '.env' mein SILENCE_THRESHOLD adjust kar sakte hain.)\n"
        )
        return None

    # 4. Transcribe via Groq Whisper API
    stt_model = get_stt_model()
    print(f"[{ASSISTANT_NAME} Transcribing]: Audio Groq STT model '{stt_model}' par transcribe ho raha hai...")
    try:
        success, transcript = transcribe_audio(wav_bytes)
    except KeyboardInterrupt:
        print(f"\n[{ASSISTANT_NAME}]: Transcription request cancel kar di gayi.\n")
        return None

    if not success:
        print(f"\n{transcript}\n")
        return None

    clean_transcript = transcript.strip()
    if not clean_transcript:
        print(f"\n[{ASSISTANT_NAME} Notice]: Koi shabdon ki pehchan nahi hui (empty transcript). Discard kiya gaya.\n")
        return None

    # 5. Interactive Transcript Review
    separator = "-" * 65
    print(f"\n{separator}")
    print(f"[{ASSISTANT_NAME} Review Transcript]:")
    print(f'"{clean_transcript}"')
    print()
    print("Options:")
    print("  [Enter]  : Send transcript to NEHA")
    print("  /edit    : Replace or edit with typed text")
    print("  /cancel  : Discard transcript and return to chat")
    print(f"{separator}")

    while True:
        try:
            action = input("Action > ").strip()
        except KeyboardInterrupt:
            print(f"\n[{ASSISTANT_NAME}]: Transcript discard kar diya gaya.\n")
            return None
        except EOFError:
            return None

        action_lower = action.lower()

        # Enter or confirmation
        if action == "" or action_lower in ("enter", "send", "yes", "y", "ok"):
            return clean_transcript

        # Cancel option
        if action_lower in ("/cancel", "cancel"):
            print(f"\n[{ASSISTANT_NAME}]: Voice transcript discard kar diya gaya.\n")
            return None

        # Edit option
        if action_lower in ("/edit", "edit"):
            try:
                edited = input("Edit text > ").strip()
            except KeyboardInterrupt:
                print(f"\n[{ASSISTANT_NAME}]: Voice input cancel kar diya gaya.\n")
                return None
            except EOFError:
                return None

            if not edited:
                print(f"\n[{ASSISTANT_NAME}]: Khali (empty) text enter kiya gaya. Discard kiya gaya.\n")
                return None
            return edited

        print("Kripya valid option select karein: [Enter] to send, '/edit' to change text, ya '/cancel' to discard.")


def main() -> None:
    """
    Main entry point for NEHA chat loop.
    """
    separator = "=" * 65

    # 1. Startup Credential Validation
    is_valid, cred_message = validate_credentials()
    if not is_valid:
        print(separator)
        print(f"Namaste {USER_NAME}! Main hoon {ASSISTANT_NAME}.")
        print(separator)
        print()
        print("[Setup Required]:")
        print(cred_message)
        print()
        print(separator)
        sys.exit(0)

    # 2. Display Welcome Message
    active_model = get_configured_model()
    stt_model = get_stt_model()
    voice_state = "ON" if is_voice_enabled() else "OFF"
    print(separator)
    print(WELCOME_MESSAGE)
    print(f"Chat Model  : {active_model}")
    print(f"STT Model   : {stt_model}")
    print(f"Voice Output: {voice_state} (Type '/voice off' to mute, '/voice status' for details)")
    print("Speech Input: Ready (Type '/listen' to speak, '/mic list' to view microphones)")
    print(separator)
    print()

    # 3. Interactive Chat Loop
    try:
        while True:
            try:
                raw_input = input(f"{USER_NAME} > ")
            except KeyboardInterrupt:
                # Ctrl+C gracefully handled at terminal prompt
                stop_speech()
                print(f"\n\nAlvida {USER_NAME}! (KeyboardInterrupt mila) NEHA session band ho raha hai.")
                break
            except EOFError:
                # End-of-input / Ctrl+Z gracefully handled
                stop_speech()
                print(f"\n\nAlvida {USER_NAME}! (End-of-input) NEHA session band ho raha hai.")
                break

            # Check for empty or whitespace-only messages
            clean_input = raw_input.strip()
            if not clean_input:
                continue

            clean_lower = clean_input.lower()

            # Case-insensitive exit / quit commands
            if clean_lower in ("exit", "quit"):
                stop_speech()
                print(f"\nAlvida {USER_NAME}! NEHA terminal session samapt hua. Have a great day!")
                break

            # Microphone List Command
            if clean_lower in ("/mic list", "mic list"):
                print(f"\n{format_mic_list()}\n")
                continue

            # On-Demand Speech-to-Text Command
            if clean_lower in ("/listen", "listen"):
                confirmed_text = handle_listen()
                if confirmed_text:
                    print(f"{USER_NAME} (Voice) > {confirmed_text}")
                    # Process confirmed text as conversation turn (never as a terminal command)
                    if not _process_conversation_turn(confirmed_text):
                        break
                continue

            # Local Voice Control Commands (Handled locally without Groq or history)
            if clean_lower in ("/voice on", "voice on"):
                set_voice_enabled(True)
                print(f"\n[{ASSISTANT_NAME}]: Spoken voice responses chalu (ON) kar diye gaye hain.\n")
                continue

            if clean_lower in ("/voice off", "voice off"):
                stop_speech()
                set_voice_enabled(False)
                print(f"\n[{ASSISTANT_NAME}]: Spoken voice responses band (OFF) kar diye gaye hain. NEHA ab sirf text mode mein reply karegi.\n")
                continue

            if clean_lower in ("/voice status", "voice status"):
                print(f"\n[{ASSISTANT_NAME} Voice Settings]:\n{get_voice_status()}\n")
                continue

            if clean_lower in ("/voice sarvam", "voice sarvam"):
                set_active_provider("sarvam")
                print(f"\n[{ASSISTANT_NAME}]: Voice provider Sarvam AI Bulbul (Cloud) par set kar diya gaya hai.\n")
                continue

            if clean_lower in ("/voice local", "voice local"):
                set_active_provider("local")
                print(f"\n[{ASSISTANT_NAME}]: Voice provider Local Windows SAPI5 (Offline) par set kar diya gaya hai.\n")
                continue

            # Case-insensitive clear command (resets session history)
            if clean_lower == "clear":
                clear_history()
                print(f"\n[{ASSISTANT_NAME}]: Conversation memory reset ho gayi hai. Hum naye topic par baat shuru kar sakte hain!\n")
                continue

            # Normal typed chat: Process conversation turn via Groq API
            if not _process_conversation_turn(clean_input):
                break

    finally:
        # Ensure shutdown cleans up speech resources
        stop_speech()


if __name__ == "__main__":
    main()
