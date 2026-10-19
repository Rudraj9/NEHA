# NEHA — Personal AI Assistant

A modular Python-based terminal AI assistant designed for study, coding assistance, and conceptual guidance. NEHA combines cloud-based large language model (LLM) inference via the Groq API with flexible speech synthesis: expressive cloud-based Indian voice generation powered by **Sarvam AI Bulbul**, alongside local, offline fallback synthesis powered by **Windows SAPI5**.

---

## 1. Project Overview

NEHA is an interactive terminal assistant built to provide conversational guidance for programming, computer science studies, and daily problem-solving in natural, beginner-friendly Roman Hinglish.

Key architectural characteristics:
- **Terminal Interface**: Operates via a clean interactive command-line loop.
- **Hosted Cloud Inference**: Uses the official Groq Python SDK to interface with hosted open-weight models (e.g., Llama and GPT-OSS families) with low latency.
- **Dual Text-to-Speech Architecture**:
  - **Sarvam AI Bulbul (Primary / Cloud)**: Generates natural, fluent Indian voice synthesis with native Hindi and code-mixed Hinglish pronunciation.
  - **Windows SAPI5 (Offline Fallback)**: Delivers offline speech synthesis via `pyttsx3` when internet access is unavailable or offline operation is explicitly chosen.
- **Scoped Operational Boundaries**: NEHA is strictly a conversational assistant. It does not execute arbitrary shell commands, inspect or edit files, browse the live web, or perform operating system automation.

---

## 2. Key Features

- **Multi-Turn Contextual Dialogue**: Maintains conversational context across turns within an active session, allowing follow-up questions and iterative explanations.
- **Bounded Session Memory**: Employs an in-memory history window (configurable via `MAX_CONVERSATION_TURNS`) to retain recent message pairs while discarding older turns to manage context size.
- **Zero-State History Isolation**: Failed API calls (such as rate limits or connection timeouts) are caught before committing, preventing incomplete or corrupt turns from polluting session memory.
- **Configurable Intelligence & Persona**: Decouples the assistant's tone, instructions, and target audience through a centralized system prompt, with runtime model selection via environment variables.
- **High-Fidelity Indian Text-to-Speech (TTS)**: Leverages Sarvam AI's Bulbul models for natural Hinglish pronunciation while keeping terminal responses rendered in clean Roman script.
- **Offline Fallback Voice**: Preserves local Windows SAPI5 (`pyttsx3`) as an explicitly selectable offline provider (`TTS_PROVIDER=local` or `/voice local`).
- **Runtime Voice Controls**: Allows toggling audio on or off (`/voice on`, `/voice off`), switching providers (`/voice sarvam`, `/voice local`), and inspecting speech engine diagnostics (`/voice status`) during an active session without interrupting conversation state.
- **Safe Error Handling & Fallbacks**: Categorizes authentication, rate-limiting, missing models, and network failures with user-friendly notices. Error strings are screened to prevent the speech engine from reading error messages aloud. If Sarvam audio generation encounters an issue, the assistant informs the user and cleanly continues in text mode without silently switching to the English-accent local voice.

---

## 3. Architecture

The application is structured into decoupled packages separating the terminal loop, LLM communication, personality configuration, and audio synthesis:

```mermaid
flowchart TD
    User([User Terminal]) -->|Text Input| Main[main.py: Interactive Loop]
    
    Main -->|Local Command: clear| BrainMemory[(assistant/brain.py: Session History)]
    Main -->|Local Command: /voice| TTSConfig[voice/tts.py: Voice Settings]
    Main -->|Exit Command: quit / Ctrl+C| Shutdown[Safe Cleanup & Exit]
    
    Main -->|User Prompt| Brain[assistant/brain.py: Conversation Engine]
    SystemPrompt[assistant/personality.py: System Prompt] -->|Prepend Persona| Brain
    BrainMemory <-->|Retrieve / Update Turns| Brain
    
    Brain -->|HTTPS Payload: System + History + Input| GroqAPI["Groq Cloud API (Remote Inference)"]
    GroqAPI -->|Generated Completion| Brain
    
    Brain -->|Clean Response Text| Main
    Main -->|Print Roman Hinglish to Console| User
    
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

### Inference vs. Speech Execution
- **Remote Cloud Inference**: The conversation engine (`assistant/brain.py`) compiles the system prompt, retained history, and current user message, then transmits them securely over HTTPS to Groq's infrastructure.
- **Speech Generation & Local Playback**: 
  - When configured for **Sarvam AI**, the generated assistant response text is transmitted to Sarvam's Bulbul API over HTTPS (`/text-to-speech`). The returned WAV audio is decoded and played directly from memory via Windows `winsound.PlaySound` (blocking sequentially to prevent overlapping audio).
  - When configured for **Local SAPI5**, audio synthesis runs entirely on-device using the native Windows SAPI5 engine.
  - In both modes, speech playback is synchronous: the terminal displays the complete text output before audio playback begins.


---

## 4. Technology Stack

| Technology | Role | Purpose |
| :--- | :--- | :--- |
| **Python** | Core Language | Application logic, session state management, and command handling |
| **groq** (`>=0.18.0`) | LLM Client SDK | Official SDK for low-latency chat completion inference via the Groq cloud platform |
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
├── main.py                     # Application entry point, interactive REPL loop, and command router
├── assistant/                  # Conversational intelligence package
│   ├── __init__.py             # Public module interface exports
│   ├── brain.py                # Groq API client, bounded history buffer, and error classifier
│   └── personality.py          # Assistant identity, user configuration, and system prompt definition
├── voice/                      # Audio synthesis package
│   ├── __init__.py             # Public voice interface exports (speak, toggle, status, provider)
│   ├── tts.py                  # Unified TTS manager and routing layer
│   ├── sarvam_tts.py           # Sarvam AI Bulbul cloud TTS integration, chunking, and playback
│   └── local_tts.py            # Windows SAPI5 / pyttsx3 offline speech engine and loop management
├── requirements.txt            # Explicit third-party Python package dependencies
├── .env.example                # Configuration template with placeholder variable declarations
├── .gitignore                  # Exclusion rules for virtual environments, secrets (.env), and bytecode
└── README.md                   # Technical project documentation and setup guide
```

---

## 6. Getting Started

### Prerequisites
- **Operating System**: Windows 10 or Windows 11 (required for SAPI5 speech synthesis support).
- **Python**: Python 3.8+ (tested and verified with Python 3.10+ / 3.13).
- **Groq API Key**: A free or paid API key obtained from the [Groq Console](https://console.groq.com/keys).

### Installation & Setup (Windows PowerShell)

1. **Clone or navigate to the repository:**
   ```powershell
   git clone https://github.com/Rudraj9/NEHA.git
   Set-Location NEHA
   ```
   *(If working from an existing download, navigate directly into the project directory).*

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Create `.env` from the provided `.env.example` template without overwriting an existing `.env`:
   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   ```

5. **Set your API credentials:**
   Open `.env` in any text editor and populate `GROQ_API_KEY`:
   ```ini
   GROQ_API_KEY=gsk_your_actual_groq_api_key_here
   ```

6. **Launch the assistant:**
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

---

## 7. Configuration

Environment variables are loaded automatically from `.env` at startup using `python-dotenv`:

### Core & LLM Settings
| Variable | Required | Code Default | Example / Recommended | Description |
| :--- | :---: | :--- | :--- | :--- |
| `GROQ_API_KEY` | **Yes** | None | `gsk_...` | Authentication key for accessing the Groq Chat Completions API. |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | `openai/gpt-oss-20b` | Model identifier passed to Groq completions. *(See note below).* |
| `MAX_CONVERSATION_TURNS` | No | `10` | `10` | Maximum number of dialogue turns (user + assistant pairs) retained in memory. |

### Text-to-Speech (TTS) Settings
| Variable | Required | Code Default | Example / Recommended | Description |
| :--- | :---: | :--- | :--- | :--- |
| `VOICE_ENABLED` | No | `true` | `true` | Controls whether text-to-speech output is activated on launch (`true`/`false`). |
| `TTS_PROVIDER` | No | `sarvam` (if key set) else `local` | `sarvam` | Active speech provider: `sarvam` (Cloud Bulbul) or `local` (Offline Windows SAPI5). |
| `SARVAM_API_KEY` | Conditional | None | `your_key_here` | Required when using Sarvam TTS. Obtain from [Sarvam AI Dashboard](https://dashboard.sarvam.ai). |
| `SARVAM_TTS_MODEL` | No | `bulbul:v3` | `bulbul:v3` | Bulbul model identifier (`bulbul:v3` or `bulbul:v4-flash`). |
| `SARVAM_TTS_VOICE` | No | `neha` | `neha` | Speaker / voice persona ID (e.g., `neha`, `ritu`, `shubh` for `bulbul:v3`). |
| `SARVAM_TTS_LANGUAGE` | No | `hi-IN` | `hi-IN` | BCP-47 language code (`hi-IN` for Hindi/Hinglish, `en-IN` for Indian English). |
| `SARVAM_TTS_PACE` | No | `1.0` | `1.0` | Speech playback rate multiplier (clamped between `0.5` and `2.0`). |
| `VOICE_RATE` | No | `175` | `175` | Local SAPI5 speech rate in words per minute (clamped between `100` and `300`). |

> [!NOTE]
> **Model vs. Voice Selection**:
> - **Model (`SARVAM_TTS_MODEL`)**: Refers to the synthesis architecture. `bulbul:v3` is the stable model with rich prosody; `bulbul:v4-flash` is optimized for ultra-low latency.
> - **Speaker / Voice (`SARVAM_TTS_VOICE`)**: Refers to the individual voice persona (timbre, tone, gender). Speaker IDs are **model-specific**: for example, `neha`, `ritu`, and `shubh` belong to `bulbul:v3`, whereas `v4-flash` uses names like `shubh_enhi_ads` or `ishita_hi_ads`. Do not mix voices across model generations.

> [!NOTE]
> **Roman Hinglish Display Policy**:
> NEHA preserves screen responses in natural **Roman Hinglish** (e.g., *"Rocky, tumhara code sahi hai. Bas function ko call karo."*). Text output in the terminal is never converted to Devanagari script. The original response text is sent directly to Sarvam AI for natural Hindi/Hinglish audio generation without artificial translation or secondary LLM rewriting.

---

## 8. Usage

### Supported Commands

All local control commands are handled client-side without sending messages to the LLM API or recording turns into conversation history:

| Command | Action |
| :--- | :--- |
| `<user text>` | Sends message and retained history to the Groq API; prints text reply and plays audio (if enabled). |
| `/voice on` *(or `voice on`)* | Enables speech output for subsequent responses. |
| `/voice off` *(or `voice off`)* | Mutes speech output; assistant continues responding in text-only mode (zero TTS requests). |
| `/voice status` *(or `voice status`)* | Displays active provider, model, voice persona, language, and enabled status without leaking secrets. |
| `/voice sarvam` *(or `voice sarvam`)* | Switches the active speech provider to Sarvam AI Bulbul (Cloud). |
| `/voice local` *(or `voice local`)* | Switches the active speech provider to Local Windows SAPI5 (Offline). |
| `clear` | Clears all stored conversation turns, resetting the multi-turn session. |
| `exit` *(or `quit`)* | Stops any active audio and exits the application cleanly. |
| `Ctrl + C` / `EOF` | Catches interrupt signals, halts ongoing speech immediately, and closes the session safely. |

### Illustrative Terminal Session

*(The following transcript is an illustrative example of session interaction, not a test execution log):*

```text
=================================================================
Namaste Rocky! Main hoon NEHA, aapka personal AI assistant.
Status: Milestone 3A - Powered by Groq AI & Local Text-to-Speech
Commands:
  - Sawal puchein : Message type karein aur Enter dabayein.
  - '/voice on'   : Spoken responses enable karein.
  - '/voice off'  : Spoken responses mute karein (text-only mode).
  - '/voice status': Current voice output settings aur status dekhein.
  - 'clear'       : Conversation history reset karke naya session shuru karein.
  - 'exit'/'quit' : Session samapt karke bahar nikalein.
Active Model: openai/gpt-oss-20b
Voice Output: ON (Type '/voice off' to mute, '/voice status' for details)
=================================================================

Rocky > Python mein list aur tuple mein kya antar hai?

NEHA > List mutable hoti hai (aap elements modify kar sakte hain) jabki tuple immutable hota hai (create hone ke baad change nahi hota).

Rocky > /voice off

[NEHA]: Spoken voice responses band (OFF) kar diye gaye hain. NEHA ab sirf text mode mein reply karegi.

Rocky > clear

[NEHA]: Conversation memory reset ho gayi hai. Hum naye topic par baat shuru kar sakte hain!

Rocky > exit

Alvida Rocky! NEHA terminal session samapt hua. Have a great day!
```

---

## 9. Design Decisions & Limitations

- **Modular Decoupling**: Application control (`main.py`), inference and history state (`assistant/brain.py`), persona configuration (`assistant/personality.py`), and audio playback (`voice/tts.py`, `voice/sarvam_tts.py`, `voice/local_tts.py`) are strictly separated to maintain code clarity and enable targeted testing.
- **Volatile In-Memory Session Storage**: Conversation history is maintained exclusively in volatile Python memory (`list`). Terminating or restarting the program clears all context. No local SQLite database or file-based caching is currently implemented.
- **Turn-Bounded vs. Token-Bounded Trimming**: Memory is bounded by message turns (`MAX_CONVERSATION_TURNS`), not token counts. If individual turns contain very large blocks of text or code, token consumption can still increase significantly within the allowable turn window.
- **Network & Provider Dependencies**:
  - LLM inference depends on the Groq API.
  - Cloud speech generation depends on Sarvam AI Bulbul (`https://api.sarvam.ai/text-to-speech`).
  - Request quotas, concurrency limits, and costs are governed by respective provider terms (see [Groq Console](https://console.groq.com) and [Sarvam AI Dashboard](https://dashboard.sarvam.ai)).
- **Text Length & Chunking**: Sarvam AI REST endpoints support up to 2,500 characters per request. NEHA automatically chunks responses exceeding 2,000 characters at natural sentence boundaries (`।`, `.`, `?`, `!`, `\n`) and synthesizes them in order.
- **In-Memory Audio Playback & Cancellation**: Audio bytes received from Sarvam AI are decoded and played directly from memory via Windows `winsound.PlaySound` without retaining audio recordings on disk. If playback is interrupted via `Ctrl+C` or `/voice off`, `winsound.SND_PURGE` stops active audio immediately and remaining chunks are cancelled.
- **Pronunciation Characteristics & Limitations**:
  - **Sarvam Bulbul**: Delivers natural Indian prosody and Hindi/Hinglish pronunciation. Complex technical jargon, code blocks, or uncommon English acronyms are cleaned where possible, but may occasionally exhibit minor phonetic nuances.
  - **Local SAPI5**: Relies on system-installed English acoustic models (*Microsoft Zira* or *David*), which may sound accented or robotic on Hindi phrases.
- **System Tooling Boundaries**: The assistant currently does not support microphone audio capture (STT), continuous background listening, wake-word triggering, web scraping, or operating system command execution.

---

## 10. Privacy & Configuration Safety

- **Data Transmission**:
  - **Groq API**: Prompts and active conversation history are transmitted securely via HTTPS to the Groq API for response generation.
  - **Sarvam AI**: When `TTS_PROVIDER=sarvam` is active, the assistant's generated response text is transmitted over HTTPS to Sarvam AI for audio generation. No user microphone data or system telemetry is sent.
  - When `TTS_PROVIDER=local` is active, audio synthesis runs 100% on-device via Windows SAPI5 without network communication.
- **Ephemeral Audio**: Generated audio is played from volatile memory and is never permanently written to or retained on the local disk.
- **Credential Protection**: API keys (`GROQ_API_KEY`, `SARVAM_API_KEY`) are loaded via environment variables and must never be committed to source control.
- **Version Control Exclusions**: The repository's [`.gitignore`](file:///.gitignore) explicitly excludes `.env` and `.env*.local` while allowing tracking of the safe template [`.env.example`](file:///.env.example).

---

## 11. Verification

The repository does not currently include an automated test suite (`pytest` or `unittest` test files are not committed). Dependency injection methods (`set_client()` in `assistant/brain.py` and `set_custom_engine()` in `voice/tts.py`) are implemented to facilitate programmatic mocking.

### Manual Verification Checklist

1. **Credential Validation**:
   - Rename `.env` temporarily or set `GROQ_API_KEY` to empty.
   - Run `python main.py` and verify that the application detects missing credentials, prints setup guidance, and exits cleanly with exit code `0`.
2. **End-to-End Chat & Speech**:
   - Restore valid credentials in `.env` and launch `python main.py`.
   - Submit a prompt; confirm that the text response appears in the terminal and audible playback begins immediately through system speakers.
3. **Session Memory & Reset**:
   - Ask a question (e.g., "Mera naam Rocky hai"). Follow up with "Mera naam kya hai?" and verify that the model remembers context.
   - Enter `clear` and verify that subsequent questions treat the conversation as a new session.
4. **Voice Command Controls**:
   - Enter `/voice off` and submit a prompt; confirm that text prints without audio playback.
   - Enter `/voice status` and verify that speech status reports as muted (`OFF`).
   - Enter `/voice on` and confirm that audio synthesis resumes on subsequent turns.
5. **Error Containment**:
   - Configure an invalid model name in `GROQ_MODEL`.
   - Submit a prompt and confirm that a formatted `[Model Error]` is returned without crashing the terminal loop or reading the error text aloud.

---

## 12. Roadmap

The following capabilities represent planned iterations:

- [ ] **Push-to-Talk Speech Input**: Integrate local or API-based speech-to-text (STT) for hands-free queries.
- [ ] **Enhanced Audio Synthesis**: Integrate natural Indian/Hinglish neural voice models for more fluent pronunciation.
- [ ] **Persistent Configuration Profiles**: Store user preferences and custom prompts across application sessions.
- [ ] **Document-Grounded Assistance**: Add local document ingestion (e.g., PDF and Markdown notes) for study assistance.
- [ ] **Controlled Desktop Actions**: Implement safely sandboxed local tool execution for specific programming tasks.

---

## 13. Author & License

- **Author**: Rudra Narayan Jena
- **License**: No open-source license is currently specified for this repository. All rights are reserved by the author.

