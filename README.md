# 🤖 NEHA - Personal AI Assistant (Milestone 3A)

**NEHA** ek Jarvis-inspired personal assistant project hai jise Rocky ke study, coding, conceptual guidance aur daily productivity ke liye develop kiya ja raha hai.

**Milestone 3A Update:** NEHA ab text response generate karne ke baad **aawaz mein bolkar bhi sunati hai (Text-to-Speech)**! Yeh local Windows SAPI5 speech engine (`pyttsx3`) ka upayog karti hai — iske liye kisi extra API key ya internet data ki zaroorat nahi hoti.

---

## 🌟 Milestone 3A Ki Nayi Khasiyat (Features)

1. **Local Offline Text-to-Speech (TTS)**:
   - Windows ke built-in **SAPI5** system ka upayog karta hai.
   - **Zero Cost & Zero Extra API Keys**: Kisi paid voice API ki zaroorat nahi hai.
2. **Text Print Pehle, Aawaz Baad Mein**:
   - NEHA pehle poora text response terminal par print karti hai, fir use bolkar sunati hai.
3. **Smart Voice Safety (Errors Not Spoken)**:
   - Sirf successful AI responses bole jaate hain. API errors, rate limit notices, ya setup warnings ko aawaz mein nahi padha jata.
4. **Clean Terminal Voice Controls**:
   - `/voice on` : Spoken responses chalu karein.
   - `/voice off` : Spoken responses mute karein (text-only mode).
   - `/voice status` : Current voice output settings aur selected voice ki detail dekhein.
   *(Yeh commands locally handle hote hain aur Groq API ko nahi bheje jaate).*
5. **Enabled By Default**:
   - Spoken responses by default ON rehte hain, ek standard natural speed par (~175 wpm).
6. **Graceful Fallback**:
   - Agar kisi system par audio driver ya hardware available na ho, toh NEHA crash nahi hoti; ek chota friendly notice dekar silent text mode mein kaam jari rakhti hai.
7. **Clean Exit & Resource Cleanup**:
   - `Ctrl+C`, `exit`, ya `quit` karne par audio playback turant ruk jaata hai aur system resources safely release ho jaate hain.

---

## 🗣️ Hinglish Pronunciation Ke Baare Mein Ek Zaroori Note

NEHA Windows par pehle se installed voices (jaise *Microsoft Zira* ya *Microsoft David*) use karti hai.
- Yeh voices standard English phonetics par train hoti hain.
- Isliye jab yeh Hinglish (Hindi words English script mein) bolti hain, toh pronunciation thoda accented ya robotic lag sakta hai.
- Aane wale advanced milestones mein hum dedicated natural Indian neural voices explore karenge. Abhi ke liye yeh local, free, zero-latency foundation hai.

---

## 📂 Updated Project Structure

```text
NEHA/
│
├── main.py                  # Terminal loop, input handling, aur voice command execution
├── assistant/               # Assistant intelligence package
│   ├── __init__.py          # Exports aur module linkage
│   ├── brain.py             # Groq API client, session history & error classification
│   └── personality.py       # System prompt, NEHA identity aur welcome message
│
├── voice/                   # Naya: Local text-to-speech package (Milestone 3A)
│   ├── __init__.py          # Voice controls export (speak, toggle, status)
│   └── tts.py               # pyttsx3 SAPI5 engine, voice discovery & playback
│
├── requirements.txt         # Dependencies: groq, python-dotenv, pyttsx3, pywin32
├── .env.example             # Safe template with placeholder values & voice settings
├── .gitignore               # .env aur .venv ko Git se safe rakhne ke liye
└── README.md                # Complete documentation aur setup guide
```

---

## 💻 Windows PowerShell Setup & Run Instructions

Apne Windows PowerShell mein yeh steps follow karein:

### Step 1: Project Folder Mein Jaayein
```powershell
cd c:\Users\ASUS\OneDrive\Desktop\NEHA
```

### Step 2: Dependencies Install Karein (pyttsx3 & pywin32)
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Step 3: NEHA Run Karein!
```powershell
.\.venv\Scripts\python.exe main.py
```

---

## 🎮 Terminal Commands (NEHA Ke Sath Chat Karte Waqt)

| Command | Action |
| :--- | :--- |
| *Koi bhi sawal* | NEHA se prompt puchein — text aayega aur aawaz sunai degi. |
| `/voice off` | Spoken voice band karein (silent text mode). |
| `/voice on` | Spoken voice wapas chalu karein. |
| `/voice status` | Dekhein ki voice ON hai ya OFF, speed kitni hai, aur kaunsi voice selected hai. |
| `clear` | Session memory reset karke naya topic shuru karein. |
| `exit` ya `quit` | NEHA session ko peacefully close karein. |
| `Ctrl + C` | Current speech aur session ko immediately safely band karein. |

---

## 🔊 Manually Confirm Kaise Karein Ki Voice Kaam Kar Rahi Hai

1. Terminal mein application start karein:
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```
2. Welcome message par dekhein:
   `Voice Output: ON (Type '/voice off' to mute, '/voice status' for details)`
3. Ek simple sawal puchein:
   `Rocky > Hello NEHA, kaise ho aap?`
4. Dekhein:
   - Pehle terminal par `NEHA > ...` text print hoga.
   - Uske turant baad aapke computer ke speakers/headphones se aawaz aayegi.
5. Voice mute test karein:
   `Rocky > /voice off`
   Fir agla sawal puchein. Ab NEHA sirf text mein reply karegi bina kisi aawaz ke.
