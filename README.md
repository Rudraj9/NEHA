# NEHA — Personal AI Assistant

A modular Python-based terminal AI assistant designed for study, coding assistance, and conceptual guidance. NEHA combines cloud-based large language model (LLM) inference via the Groq API with flexible speech synthesis (Sarvam AI Bulbul & Windows SAPI5) and **on-demand microphone input with multilingual Speech-to-Text (STT)** powered by Groq Whisper.

---

## 1. Project Overview

NEHA is an interactive terminal assistant built to provide conversational guidance for programming, computer science studies, and daily problem-solving in natural, beginner-friendly Roman Hinglish.

Key architectural characteristics:
- **Terminal Interface**: Operates via a clean interactive command-line loop.
- **Hosted Cloud Inference**: Uses the official Groq Python SDK to interface with hosted open-weight models (e.g., Llama and GPT-OSS families) with low latency.
- **On-Demand Speech-to-Text (STT)**: Captures audio on-demand with `/listen`, evaluates silence locally using an RMS threshold, transcribes via Groq Whisper (`whisper-large-v3-turbo`), and provides interactive review ([Enter], `/edit`, `/cancel`) before submitting to the chat loop.
- **Dual Text-to-Speech Architecture**:
  - **Sarvam AI Bulbul (Primary / Cloud)**: Generates natural, fluent Indian voice synthesis with native Hindi and code-mixed Hinglish pronunciation.
  - **Windows SAPI5 (Offline Fallback)**: Delivers offline speech synthesis via `pyttsx3` when internet access is unavailable or offline operation is explicitly chosen.
- **Scoped Operational Boundaries**: NEHA is strictly a conversational assistant. It opens the microphone only when `/listen` is explicitly invoked (never at startup or continuously), does not run background keyboard hooks, and does not execute recognized spoken words as terminal commands.

---

## 2. Key Features

- **Multi-Turn Contextual Dialogue**: Maintains conversational context across turns within an active session, allowing follow-up questions and iterative explanations.
- **On-Demand Microphone Capture (`/listen`)**: Records voice input on demand for a configurable duration (default 8s, max 30s) and releases the audio hardware immediately upon completion or cancellation.
- **Multilingual Speech Recognition**: Transcribes spoken Hindi, English, and mixed Hindi-English (Hinglish) faithfully using Groq's `whisper-large-v3-turbo` model without forced translation.
- **Local Silence Pre-Screening**: Evaluates root-mean-square (RMS) audio volume locally before uploading; silent recordings are discarded immediately without wasting STT tokens or calling the chat model.
- **Interactive Transcript Review**: Presents the recognized text with three clear choices:
  - `[Enter]`: Confirm and send transcript directly to NEHA.
  - `/edit`: Replace or refine the transcript with typed text.
  - `/cancel`: Discard the transcript and cleanly return to the chat prompt.
- **Microphone Device Enumeration (`/mic list`)**: Inspects and lists all available audio input devices, identifying system defaults and facilitating custom selection via `MIC_DEVICE`.
- **Bounded Session Memory**: Employs an in-memory history window (configurable via `MAX_CONVERSATION_TURNS`) to retain recent message pairs while discarding older turns to manage context size.
- **Zero-State History Isolation**: Failed, silent, or cancelled voice operations never leave incomplete turns in session memory.
- **High-Fidelity Indian Text-to-Speech (TTS)**: Leverages Sarvam AI's Bulbul models for natural Hinglish pronunciation while keeping terminal responses rendered in clean Roman script.
- **Offline Fallback Voice**: Preserves local Windows SAPI5 (`pyttsx3`) as an explicitly selectable offline provider (`TTS_PROVIDER=local` or `/voice local`).
- **Runtime Voice Controls**: Allows toggling audio on or off (`/voice on`, `/voice off`), switching providers (`/voice sarvam`, `/voice local`), and inspecting speech engine diagnostics (`/voice status`) during an active session without interrupting conversation state.

---

## 3. Architecture

The application is structured into decoupled packages separating the terminal loop, LLM communication, personality configuration, audio recording, and audio synthesis:

```mermaid
flowchart TD
    User([User Terminal]) -->|Text Input / Commands| Main[main.py: Interactive Loop]
    
    %% Local Commands
    Main -->|Local Command: clear| BrainMemory[(assistant/brain.py: Session History)]
    Main -->|Local Command: /voice| TTSConfig[voice/tts.py: Voice Settings]
    Main -->|Local Command: /mic list| MicListing[voice/recorder.py: Device Enumeration]
    Main -->|Exit Command: quit / Ctrl+C| Shutdown[Safe Cleanup & Exit]
    
    %% Speech-to-Text Path
    Main -->|Voice Command: /listen| Recorder[voice/recorder.py: Audio Capture]
    Recorder -->|Open Stream| MicHardware([Microphone])
    MicHardware -->|16-bit PCM Audio Frames| Recorder
    Recorder -->|Close Stream Immediately| MicHardware
    Recorder -->|Local Silence Check: RMS < Threshold?| SilenceCheck{Is Silent?}
    SilenceCheck -->|Yes: Discard Audio| Main
    SilenceCheck -->|No: In-Memory WAV Bytes| STTClient[voice/stt.py: Groq STT Client]
    
    STTClient -->|HTTPS Multipart: audio.wav| GroqSTTAPI["Groq Whisper STT API (whisper-large-v3-turbo)"]
    GroqSTTAPI -->|JSON Transcript| STTClient
    STTClient -->|Recognized Text| ReviewPrompt{Review: Enter / /edit / /cancel}
    ReviewPrompt -->|/cancel: Discard| Main
    ReviewPrompt -->|/edit: Typed Replacement| ConfirmedText[Confirmed Query Text]
    ReviewPrompt -->|Enter: Keep Transcript| ConfirmedText
    
    %% Conversation Brain Path
    ConfirmedText --> Brain[assistant/brain.py: Conversation Engine]
    Main -->|Normal Typed Chat| Brain
    SystemPrompt[assistant/personality.py: System Prompt] -->|Prepend Persona| Brain
    BrainMemory <-->|Retrieve / Update Turns| Brain
    
    Brain -->|HTTPS Payload: System + History + Query| GroqChatAPI["Groq Cloud API (Remote Inference)"]
    GroqChatAPI -->|Generated Completion| Brain
    
    Brain -->|Clean Response Text| Main
    Main -->|Print Roman Hinglish to Console| User
    
    %% Text-to-Speech Path
    Main -->|Check if Error| VoiceFilter{is_error_response?}
    VoiceFilter -->|Yes: Suppress Audio| Main
    VoiceFilter -->|No: Pass Clean Text| TTSRouter[voice/tts.py: TTS Router]
    
    TTSRouter -->|TTS_PROVIDER = sarvam| SarvamMod[voice/sarvam_tts.py]
    TTSRouter -->|TTS_PROVIDER = local| LocalMod[voice/local_tts.py]
    
    SarvamMod -->|HTTPS REST Request| SarvamAPI["Sarvam AI Bulbul API (Cloud TTS)"]
    SarvamAPI -->|Base64 WAV Audio| SarvamMod
    SarvamMod -->|In-Memory Playback (winsound)| Speaker([Speakers / Headphones])
    
    LocalMod -->|Windows COM SAPI5| Speaker
```

### Data Flow & Network Requirements

1. **Microphone Recording (100% Local & On-Demand)**:
   - Microphone hardware is opened **only** when `/listen` is typed.
   - Captured at 16,000 Hz (or device native rate), 1-channel mono, 16-bit PCM.
   - Audio is buffered entirely in memory. Zero audio files are saved to disk.
   - The microphone stream is closed before silence checking and transcription begin.
2. **Local Silence Pre-Screening (100% Local)**:
   - Root Mean Square (RMS) volume is computed across all audio samples.
   - If `RMS < SILENCE_THRESHOLD` (default: 300), the recording is deemed silent and discarded immediately. No network requests are made.
3. **Speech-to-Text Transcription (Remote HTTPS)**:
   - Non-silent WAV bytes are transmitted in-memory over HTTPS to Groq's transcription endpoint (`client.audio.transcriptions.create`).
   - Transcription uses `whisper-large-v3-turbo` by default.
   - Language is auto-detected to preserve mixed Hindi-English (Hinglish) as spoken.
4. **Interactive Review (100% Local)**:
   - The transcript is displayed to the user for review.
   - Only confirmed text enters the conversation flow. Spoken command words (such as "exit" or "clear") are treated strictly as conversational text, never as terminal commands.
5. **Chat Completion & Speech Output**:
   - The confirmed query is passed to Groq Chat API (`assistant/brain.py`).
   - The assistant's response is printed to the terminal, and spoken aloud via the active TTS engine (`voice/tts.py`).

---

## 4. Technology Stack

| Technology | Role | Purpose |
| :--- | :--- | :--- |
| **Python** | Core Language | Application logic, session state management, and command handling |
| **groq** (`>=0.18.0`) | LLM & STT Client SDK | Official SDK for chat completions and Whisper Speech-to-Text transcription |
| **sounddevice** (`>=0.5.0`) | Audio Capture | Windows-compatible PortAudio wrapper for on-demand microphone recording |
| **numpy** (`>=1.26.0`) | Audio Processing | Vectorized RMS volume calculation for local silence pre-screening |
| **pywebview** (`>=6.0.0`) | Native Desktop GUI | Native Windows desktop wrapper powered by Microsoft Edge WebView2 |
| **HTML5 / CSS3 / Vanilla JS** | UI Presentation | Sci-fi translucent glassmorphic interface, Canvas 2D abstract AI presence |
| **python-dotenv** (`>=1.0.0`) | Configuration | Securely loads environment configuration from a local `.env` file |
| **requests** (`>=2.31.0`) | HTTP Client | REST API communication with Sarvam AI Bulbul Text-to-Speech service |
| **Sarvam AI Bulbul** | Cloud TTS API | Neural Indian text-to-speech providing native Hindi & Hinglish pronunciation |
| **pyttsx3** (`>=2.90`) | Offline Text-to-Speech | Local cross-platform TTS library wrapping native system audio engines |
| **pywin32** (`>=300`) | OS Integration | Python COM extensions providing interface bindings for the Windows SAPI5 driver |
| **Windows SAPI5 / winsound** | Native Windows Services | Built-in Windows audio playback (`winsound`) and offline speech backend (`SAPI5`) |

---

## 5. Project Structure

```text
NEHA/
├── desktop.py                  # Native Desktop GUI launcher (pywebview / WebView2)
├── main.py                     # Terminal CLI interactive loop and command router
├── desktop_app/                # Desktop application package
│   ├── __init__.py             # Public module interface exports
│   └── bridge.py               # Thread-safe JS-to-Python bridge controller
├── ui/                         # Desktop user interface assets
│   ├── index.html              # Clean semantic HTML5 desktop structure
│   ├── styles.css              # Deep midnight sci-fi glassmorphic styling
│   ├── orb.js                  # Canvas 2D abstract AI presence with reactive states
│   └── app.js                  # Frontend state machine, review card, and event bindings
├── assistant/                  # Conversational intelligence package
│   ├── __init__.py             # Public module interface exports
│   ├── brain.py                # Groq chat client, bounded history buffer, and error handling
│   └── personality.py          # Assistant identity, system prompt, and welcome banner
├── voice/                      # Audio input & output package
│   ├── __init__.py             # Public voice interface exports (record, transcribe, speak, controls)
│   ├── recorder.py             # Microphone capture, early-stop, device enumeration, RMS silence
│   ├── stt.py                  # Groq Whisper transcription client and error handling
│   ├── tts.py                  # Unified TTS routing and playback management
│   ├── sarvam_tts.py           # Sarvam AI Bulbul cloud TTS integration and chunking
│   └── local_tts.py            # Windows SAPI5 / pyttsx3 offline speech engine
├── test_desktop_bridge.py      # Automated verification suite for desktop bridge controller
├── test_voice_input.py         # Mocked automated test suite for STT and recording workflows
├── requirements.txt            # Python package dependencies
├── .env.example                # Configuration template with placeholder variable declarations
├── .gitignore                  # Exclusion rules for virtual environments, secrets (.env), and bytecode
└── README.md                   # Technical project documentation and setup guide
```

---

## 6. Getting Started

### Prerequisites
- **Operating System**: Windows 10 or Windows 11.
- **Python**: Python 3.8+ (tested and verified with Python 3.13).
- **Microsoft Edge WebView2**: Preinstalled on Windows 10/11 (powers native pywebview desktop window).
- **Microphone**: Any functional built-in microphone, USB headset, or virtual audio device.
- **Groq API Key**: A free or paid API key obtained from the [Groq Console](https://console.groq.com/keys).

### Installation & Setup (Windows PowerShell)

1. **Navigate to the repository:**
   ```powershell
   Set-Location c:\Users\ASUS\OneDrive\Desktop\NEHA
   ```

2. **Activate the virtual environment:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Create `.env` from `.env.example` if not already present:
   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   ```

5. **Set your API credentials:**
   Open `.env` in any text editor and populate `GROQ_API_KEY`:
   ```ini
   GROQ_API_KEY=gsk_your_actual_groq_api_key_here
   ```

6. **Launch the Desktop Application (Recommended):**
   ```powershell
   .\.venv\Scripts\python.exe desktop.py
   ```
   *(To run in a local web browser fallback, use: `.\.venv\Scripts\python.exe desktop.py --browser`)*

7. **Or launch the Classic Terminal Interface:**
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

---

## 7. Configuration

All configuration is loaded automatically from `.env` at startup:

### Core & LLM Settings
| Variable | Required | Default | Example | Description |
| :--- | :---: | :--- | :--- | :--- |
| `GROQ_API_KEY` | **Yes** | None | `gsk_...` | Groq API key used for both Chat Completions and Whisper STT. |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | `llama-3.3-70b-versatile` | Model identifier for conversational answers. |
| `MAX_CONVERSATION_TURNS` | No | `10` | `10` | Maximum dialogue turns retained in memory. |

### Speech-to-Text (STT) & Microphone Settings
| Variable | Required | Default | Example | Description |
| :--- | :---: | :--- | :--- | :--- |
| `GROQ_STT_MODEL` | No | `whisper-large-v3-turbo` | `whisper-large-v3-turbo` | Groq Whisper model ID (`whisper-large-v3-turbo` or `whisper-large-v3`). |
| `GROQ_STT_LANGUAGE` | No | *(empty / auto-detect)* | `hi` or `en` | Optional ISO-639-1 code. Empty enables multilingual auto-detect for Hinglish. |
| `RECORDING_DURATION` | No | `8` | `8` | Recording length in seconds (clamped between `1` and `30`). |
| `SILENCE_THRESHOLD` | No | `300` | `300` | RMS volume threshold. Audio below this level is discarded locally. |
| `MIC_DEVICE` | No | *(empty / default)* | `1` or `Realtek` | Device index number or name substring from `/mic list`. |

### Text-to-Speech (TTS) Settings
| Variable | Required | Default | Example | Description |
| :--- | :---: | :--- | :--- | :--- |
| `VOICE_ENABLED` | No | `true` | `true` | Enables or disables speech output on launch (`true`/`false`). |
| `TTS_PROVIDER` | No | `sarvam` (if key set) else `local` | `sarvam` | Active speech provider: `sarvam` or `local`. |
| `SARVAM_API_KEY` | Conditional | None | `your_key_here` | Required when using Sarvam Bulbul TTS. |
| `SARVAM_TTS_MODEL` | No | `bulbul:v3` | `bulbul:v3` | Bulbul model identifier. |
| `SARVAM_TTS_VOICE` | No | `neha` | `neha` | Speaker persona ID. |
| `SARVAM_TTS_LANGUAGE` | No | `hi-IN` | `hi-IN` | BCP-47 language code. |
| `SARVAM_TTS_PACE` | No | `1.0` | `1.0` | Speech playback speed multiplier (`0.5` - `2.0`). |
| `VOICE_RATE` | No | `175` | `175` | Local SAPI5 speech rate in words per minute (`100` - `300`). |

---

## 8. Usage & Commands

### Terminal Commands

| Command | Action |
| :--- | :--- |
| `/listen` *(or `listen`)* | Starts on-demand microphone recording for the configured duration. |
| `/mic list` *(or `mic list`)* | Displays all input-capable audio devices and highlights the active microphone. |
| `<user text>` | Sends typed message to Groq; prints and speaks the response. |
| `/voice on` | Enables spoken audio responses. |
| `/voice off` | Mutes spoken audio responses (text-only mode). Microphone input remains active. |
| `/voice status` | Displays current voice settings without exposing sensitive credentials. |
| `/voice sarvam` | Switches TTS provider to Sarvam AI Bulbul (Cloud). |
| `/voice local` | Switches TTS provider to Local Windows SAPI5 (Offline). |
| `clear` | Clears conversation memory history. |
| `exit` *(or `quit`)* | Stops any active audio and exits cleanly. |
| `Ctrl + C` | During recording: cancels capture and returns to prompt. At prompt: exits cleanly. |

### The `/listen` Interaction Flow

```text
Rocky > /listen

[NEHA Recording]: Microphone initialize ho raha hai...
[NEHA Recording]: Microphone active hai! Kripya boliye... (8s limit, Press Ctrl+C to cancel)
[NEHA]: Recording complete. Microphone band ho gaya.
[NEHA Transcribing]: Audio Groq STT model 'whisper-large-v3-turbo' par transcribe ho raha hai...

-----------------------------------------------------------------
[NEHA Review Transcript]:
"NEHA, Python mein list aur tuple ka difference samjhao."

Options:
  [Enter]  : Send transcript to NEHA
  /edit    : Replace or edit with typed text
  /cancel  : Discard transcript and return to chat
-----------------------------------------------------------------
Action > 

Rocky (Voice) > NEHA, Python mein list aur tuple ka difference samjhao.

NEHA > Python mein list mutable hoti hai (items change kiye ja sakte hain) jabki tuple immutable hota hai (create hone ke baad change nahi hota).
```

---

## 9. Limitations & Troubleshooting

### Troubleshooting

1. **Silence Warning / Transcript Discarded**:
   - *Message*: `Audio bohot shaant (silent) tha ya aawaaz detect nahi hui (RMS: ... < threshold: 300.0)`.
   - *Cause*: Microphone input volume is low, muted, or speaker was too far away.
   - *Fix*: Check Windows Microphone volume (`Settings > System > Sound > Input`). Lower `SILENCE_THRESHOLD` in `.env` (e.g. `SILENCE_THRESHOLD=150`).
2. **Missing Microphone or Permission Denied**:
   - *Message*: `Microphone capture error: [PaErrorCode -9996] Invalid device`.
   - *Fix*: Verify microphone is plugged in. Check Windows Privacy (`Settings > Privacy & Security > Microphone`) to ensure desktop apps have microphone access. Run `/mic list` to find the correct device index.
3. **Transcription Rate Limit or Model Error**:
   - *Message*: `[Rate Limit Notice]` or `[Model Error]`.
   - *Fix*: Wait a few seconds before retrying `/listen`. Verify `GROQ_STT_MODEL` is set to `whisper-large-v3-turbo` in `.env`.
4. **Cancellation During Transcription**:
   - Pressing `Ctrl+C` during transcription aborts local waiting immediately. Note that if Groq's cloud endpoint already received the request, it may still process it server-side.

---

## 10. Privacy & Audio Safety

- **Ephemeral In-Memory Audio**: Audio captured from the microphone is buffered in memory as WAV bytes. It is **never** written to local disk, stored in temporary files, or retained after transcription completes.
- **No Continuous Listening**: The microphone is opened **only** during `/listen` and is explicitly closed before transcription begins. There are no background listeners or wake words.
- **Credential Protection**: API keys are loaded via `.env` and never logged or exposed.
- **Separate API Accounting**: STT transcription and LLM chat completions are distinct API operations with separate Groq usage and token accounting.

---

## 11. Verification

### Automated Verification (Mocked)

Run the automated test suite inside `.venv`:
```powershell
.\.venv\Scripts\python.exe test_voice_input.py
```
This runs 14 automated tests covering:
- Normal typed chat path preservation.
- Single capture and transcription per `/listen`.
- Confirmation, `/edit`, and `/cancel` behaviors.
- Local silence threshold discard.
- Empty transcripts and API failure handling.
- Safe device release on `Ctrl+C`.
- Voice mute independence.
- Spoken words protection (never executed as commands).
- Stream lifecycle closure guarantees.

### Manual Verification Checklist (Real Hardware)

1. Launch NEHA: `.\.venv\Scripts\python.exe main.py`
2. Check available microphones: type `/mic list`
3. Test recording and confirmation:
   - Type `/listen`
   - When `Microphone active hai!` appears, speak: *"NEHA, Python mein list aur tuple ka difference samjhao."*
   - Wait for recording to complete (8 seconds).
   - Verify transcript is displayed accurately.
   - Press Enter to send.
   - Verify NEHA responds in Roman Hinglish and speaks the response aloud.
4. Test `/edit`: Type `/listen`, speak anything, at the review prompt type `/edit`, enter a new question, and verify the edited question is sent.
5. Test `/cancel`: Type `/listen`, speak anything, at the review prompt type `/cancel`, verify returned to prompt without calling chat.
6. Test silence discard: Type `/listen` and remain completely silent. Verify silence notice is displayed and chat model is not called.
7. Test `Ctrl+C`: Type `/listen` and immediately press `Ctrl+C`. Verify recording is cancelled cleanly.

---

## 11. Hands-Free Voice-First Experience & Desktop UI

NEHA features a futuristic, hands-free voice experience centered around a luminous animated Canvas AI orb.

### Desired Hands-Free Flow
1. User enables **Hands-free** mode using the centerpiece toggle button.
2. Say: **“Hi NEHA”**.
3. The orb pulses with a vivid activation aura.
4. NEHA immediately acknowledges: **“Haan Rocky, bolo.”** (blocking, pre-cached audio, zero LLM calls).
5. Voice Activity Detection (VAD) opens with pre-roll buffering and captures your question naturally.
6. Recording ends automatically when you finish speaking.
7. Audio is transcribed via Whisper and sent through the Groq conversation flow.
8. NEHA speaks its response using Sarvam Bulbul or local SAPI5.
9. A short follow-up listening window opens (default: 4.5s). If you ask another question, it continues the conversation; if you remain silent, it returns to waiting for “Hi NEHA” without making any cloud calls.

### Audio Stream Ownership & Safety
- **Single Coordinated Owner**: Wake-word spotter and microphone recording stream never run concurrently.
- **Echo Suppression**: Microphone capture is strictly paused and closed while NEHA is acknowledging, generating, or speaking answers.
- **Pre-Roll Audio Preservation**: A 450ms circular ring buffer ensures the opening syllables/words of the question are never clipped.
- **Debounce Protection**: Wake detection applies a cooldown to avoid double triggers.

### Picovoice Porcupine Setup for "Hi NEHA"
Local wake-word detection runs on-device using Picovoice Porcupine (Windows x86_64). Because "Hi NEHA" is a custom keyword, it requires:
1. **Picovoice AccessKey**: Sign up for free at [https://console.picovoice.ai/](https://console.picovoice.ai/) and copy your AccessKey.
2. **Custom Model File**:
   - Go to *Porcupine > Custom Wake Word*.
   - Type keyword: `Hi Neha`.
   - Select Platform: **Windows**.
   - Download the generated `.ppn` model file (e.g. `Hi-Neha_en_windows_v3_0_0.ppn`).
3. **Configure `.env`**:
   ```env
   PICOVOICE_ACCESS_KEY=your_picovoice_access_key
   WAKE_WORD_MODEL_PATH=path/to/Hi-Neha_en_windows_v3_0_0.ppn
   ```
*Note: If unconfigured, the UI clearly displays a setup checklist modal when Hands-Free is clicked, and manual Click-to-Talk remains fully operational.*

### Desktop Launch & Verification
```powershell
# Launch Desktop UI
.\.venv\Scripts\python.exe desktop.py

# Run Automated Test Suite (39 tests)
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
```

### Manual Verification Checklist (Microphone & Headset)
1. **Click-to-Talk Fallback**: Click the circular mic button, speak a question, and verify transcript review or response.
2. **Hands-Free Setup Modal**: With missing `.ppn` model, click "Enable Hands-Free" and verify the setup checklist appears cleanly.
3. **Hands-Free Wake Word**: Configure keys in `.env`, enable Hands-Free, verify the indicator changes to green "MIC ON (LISTENING)". Say *"Hi NEHA"*, verify acknowledgment *"Haan Rocky, bolo"*, and verify immediate listening.
4. **Endpointing (VAD)**: Speak naturally with a normal short pause; verify it does not cut you off early. Finish sentence, verify recording ends after ~1.3s of silence.
5. **Follow-Up Multi-Turn**: After NEHA answers, wait for the follow-up window (blue indicator). Ask another question immediately without saying "Hi NEHA". Verify it captures and answers seamlessly.
6. **Chat History Drawer**: Click "Chat History" to view the slide-out drawer. Verify past user questions and assistant answers are visible. Type a question and click Send.
7. **Stop Speech**: While NEHA is speaking, click the Stop Speech button. Verify audio halts immediately and returns safely to wake waiting.
8. **Disable Hands-Free**: Click "Hands-Free Active" toggle; verify it turns OFF immediately and releases all audio hardware.

---

## 12. Author & License

- **Author**: Rudra Narayan Jena
- **License**: All rights reserved.

