"""
main.py
-------
NEHA Assistant project ka main entry point.
Milestone 3A: Groq AI Integration + Local Text-to-Speech (TTS).

Functions:
- Environment variable validation & credential guidance.
- Display welcome message with assistant identity, active model, and voice controls.
- Interactive terminal chat loop with input validation.
- Commands:
  - 'clear' : resets session history
  - '/voice on', '/voice off', '/voice status' : controls local text-to-speech
  - 'exit' / 'quit' : terminates session cleanly
- Graceful handling of Ctrl+C (KeyboardInterrupt) and EOF (EOFError).
- Safe cleanup of audio speech resources on exit.
- Response delegation to assistant.brain and spoken delivery via voice.tts.
"""

import sys
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
)


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
    voice_state = "ON" if is_voice_enabled() else "OFF"
    print(separator)
    print(WELCOME_MESSAGE)
    print(f"Active Model: {active_model}")
    print(f"Voice Output: {voice_state} (Type '/voice off' to mute, '/voice status' for details)")
    print(separator)
    print()

    # 3. Interactive Chat Loop
    try:
        while True:
            try:
                raw_input = input(f"{USER_NAME} > ")
            except KeyboardInterrupt:
                # Ctrl+C gracefully handled
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

            # Generate response via brain module (Groq API)
            response = get_response(clean_input)
            if response:
                # 4. Print each AI response before speaking it
                print(f"\n{ASSISTANT_NAME} > {response}\n")

                # 5. Speak only successful assistant responses (never read errors aloud)
                if not is_error_response(response):
                    try:
                        speak(response)
                    except KeyboardInterrupt:
                        stop_speech()
                        print(f"\n\nAlvida {USER_NAME}! NEHA session band ho raha hai.")
                        break

    finally:
        # 10. Ensure shutdown cleans up speech resources
        stop_speech()


if __name__ == "__main__":
    main()
