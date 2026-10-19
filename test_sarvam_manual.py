"""
test_sarvam_manual.py
---------------------
Manual listening test script for Sarvam AI Bulbul Text-to-Speech integration.
Loads credentials directly from local .env without printing secrets.
Tests three sequential listening samples without consuming Groq LLM tokens.
"""

import os
import sys
import time
from dotenv import load_dotenv

# 1. Load environment variables from local .env
load_dotenv()

from voice import (
    speak,
    set_voice_enabled,
    set_active_provider,
    get_voice_status,
)

SAMPLE_SENTENCES = [
    "Rocky, tumhara code sahi hai. Bas function ko call karo.",
    "Pehle virtual environment activate karo, phir application run karo.",
    "Namaste Rocky, main NEHA hoon. Aaj hum kya seekhenge?",
]


def main():
    print("=" * 65)
    print("NEHA - Sarvam AI Bulbul Manual Listening Test")
    print("=" * 65)

    api_key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not api_key:
        print("\n[Notice]: SARVAM_API_KEY aapke '.env' file mein nahi mili!")
        print("  Kripya '.env' file mein SARVAM_API_KEY add karein:")
        print("    SARVAM_API_KEY=your_actual_sarvam_key_here\n")
        print("Settings status:")
        print(get_voice_status())
        return

    # Configure Sarvam provider
    set_voice_enabled(True)
    set_active_provider("sarvam")

    print("\nCurrent Active Voice Configuration:")
    print(get_voice_status())
    print("\n" + "=" * 65)
    print("3 Listening Samples ko baari-baari speak kiya jayega...")
    print("=" * 65 + "\n")

    for idx, sentence in enumerate(SAMPLE_SENTENCES, 1):
        print(f"Sample {idx}: \"{sentence}\"")
        print("  -> Requesting Sarvam Bulbul audio & playing...")
        t0 = time.time()
        success = speak(sentence)
        elapsed = time.time() - t0

        if success:
            print(f"  -> Playback complete ({elapsed:.2f}s)\n")
        else:
            print(f"  -> Playback failed or was interrupted ({elapsed:.2f}s)\n")

        # Brief pause between samples
        time.sleep(0.5)

    print("=" * 65)
    print("Manual listening test sequence complete!")
    print("Agar voice ya pace customize karni ho, to .env mein change karein:")
    print("  SARVAM_TTS_VOICE=neha   (ya ritu, shubh, aditya, etc.)")
    print("  SARVAM_TTS_PACE=1.0    (0.5 se 2.0 tak)")
    print("=" * 65)


if __name__ == "__main__":
    main()
