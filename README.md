# Atlas 🎙️ → 🧭

**Talk to Cursor. Hear it talk back.**

Atlas is a hands-free voice bridge to the [Cursor](https://cursor.com) IDE agent.
You speak a request; Atlas cleans it up with Claude, hands it to Cursor to do the
work (plan architecture, explain errors, edit files, run terminal commands), then
speaks a natural summary of what Cursor did back to you through your computer's
speakers.

```
🎙  your voice
     │   (microphone capture + transcription)
     ▼
🧠  Claude Opus 4.8  ── formats your words into a clean, high-quality Cursor prompt
     │                   and detects intent (plan / explain / edit / terminal / navigate)
     ▼
🧭  Cursor agent (CLI) ── "Voice Cursor": plans, explains, edits files, runs commands
     │
     ▼
🧠  Claude Opus 4.8  ── summarizes Cursor's output into natural spoken English
     │
     ▼
🔊  macOS `say`  ── reads the summary aloud
```

You never touch a setting mid-task. Atlas detects whether you want a **plan**, an
**explanation**, an **edit**, a **terminal command**, or **navigation**, and frames
the prompt — and Cursor's permissions — accordingly.

---

## What you can say

- *"Plan out the architecture for a REST API with users and posts."* → Cursor returns a plan (no edits).
- *"Why am I getting an index out of range error in main dot pie?"* → Cursor explains.
- *"Open the config file and add a timeout setting of thirty seconds."* → Cursor edits the file.
- *"Run the tests and tell me what fails."* → Cursor runs the command.
- *"Go to the parse function in utils."* → Cursor navigates there.
- *"Exit Atlas."* → quits.

---

## Requirements

| Need | Why |
|------|-----|
| **macOS** | Speech output uses the built-in `say` command. (Atlas still runs elsewhere — it prints summaries instead of speaking.) |
| **Python 3.9+** | The app itself. |
| **An Anthropic API key** | Powers both Claude agents (formatting + summary), and — when you configure Cursor to use it — the "Voice Cursor" model (Opus 4.8). |
| **The Cursor CLI** (`cursor-agent`) | The agent that actually does the work. Install from <https://cursor.com/cli>. |
| **A microphone** | To hear you. |

---

## Setup

### 1. Clone & install

```bash
git clone <your-repo-url> Atlas
cd Atlas
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

> **macOS microphone dependency:** PyAudio needs PortAudio. If `pip install` fails on PyAudio, run `brew install portaudio` first, then re-run the install.

### 2. Add your Anthropic key

```bash
cp .env.example .env
# open .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Install & authenticate the Cursor CLI ("Voice Cursor")

```bash
# Install the Cursor CLI
curl https://cursor.com/install -fsS | bash

# Authenticate once (opens your browser), or set CURSOR_API_KEY in .env
cursor-agent login
```

**To make Voice Cursor run on Opus 4.8:** inside the Cursor app, add your Anthropic
API key and select **Opus 4.8** as the model — the CLI uses that configuration.
Alternatively, set `ATLAS_CURSOR_MODEL` in `.env` to the exact model id your Cursor
exposes for Opus 4.8.

### 4. Verify everything

```bash
python -m atlas --check
```

You'll get a checklist for your API key, the Cursor CLI, `say`, and the microphone.

---

## Running it

From your project folder (the code you want Cursor to work on):

```bash
# Full voice loop — speak your commands
python -m atlas

# or, equivalently
python run.py
```

Atlas greets you, then listens. Speak a command, pause, and it goes to work. Say
**"exit atlas"** (or press Ctrl+C) to stop.

> Tip: set `ATLAS_WORKDIR` in `.env` to point Cursor at a specific project folder,
> otherwise it works in the directory you launched Atlas from.

### Try it without a microphone

Great for testing the pipeline (and works on any OS):

```bash
# Type one command; print the result instead of speaking it
python -m atlas --text "Explain what this project does" --no-speak
```

---

## Running from VS Code

Open the folder in VS Code and pick a launch config from the Run panel
(`.vscode/launch.json` is included):

- **Atlas: voice loop** — the full experience
- **Atlas: environment check** — runs `--check`
- **Atlas: single text command** — prompts you for one command to send

All run in the integrated terminal so the microphone and `say` work.

---

## How it works

| Stage | File | What it does |
|-------|------|--------------|
| Listen | `atlas/voice_input.py` | Captures a phrase from the mic and transcribes it (Google Web Speech or local Whisper). |
| Format | `atlas/formatter.py` | Claude Opus 4.8 rewrites the messy transcription into a precise Cursor prompt and detects intent. |
| Act | `atlas/cursor_agent.py` | Runs `cursor-agent` headlessly. Edits/terminal requests get `--force` so Cursor may act; plans/explanations don't. |
| Summarize | `atlas/summarizer.py` | Claude Opus 4.8 turns Cursor's output into a short, spoken-style reply. |
| Speak | `atlas/speech.py` | Reads the summary aloud with macOS `say` (prints it elsewhere). |
| Orchestrate | `atlas/app.py` | The listen → format → act → summarize → speak loop. |

### The two Claude agents and one API key

Your single `ANTHROPIC_API_KEY` powers:

1. **The formatting agent** — quality-checks and rewrites your voice command so it
   meets Cursor's (and your) expectations before anything runs.
2. **The summary agent** — turns Cursor's text output into natural speech.

The same key also powers **Voice Cursor (Opus 4.8)** once you add it inside the
Cursor app, so the whole experience runs on Opus 4.8 end to end.

---

## Configuration

Everything is set in `.env` (see `.env.example` for the full list). Highlights:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic key. |
| `ATLAS_MODEL` | `claude-opus-4-8` | Model for the Claude agents. |
| `ATLAS_FORMAT_THINKING` | `0` | `1` = let Claude think before formatting (higher quality, slower). |
| `ATLAS_CURSOR_MODEL` | _(Cursor default)_ | Force a specific Cursor model id (e.g. Opus 4.8). |
| `ATLAS_CURSOR_FORCE` | _(auto)_ | `1`/`0` to always/never let Cursor act; blank = decide from intent. |
| `ATLAS_WORKDIR` | current dir | Project folder Cursor works in. |
| `STT_BACKEND` | `google` | `google` (zero-setup, online) or `whisper` (offline, private). |
| `ATLAS_TTS_VOICE` | system default | A `say` voice, e.g. `Samantha`. List them with `say -v ?`. |
| `ATLAS_TTS_RATE` | system default | Speech rate in words per minute. |

### Offline / private transcription

By default Atlas uses Google's free Web Speech API for transcription. For a fully
local, private pipeline (only text — never audio — leaves your machine):

```bash
pip install openai-whisper   # also needs ffmpeg: brew install ffmpeg
# then in .env:
STT_BACKEND=whisper
ATLAS_WHISPER_MODEL=base.en
```

---

## Troubleshooting

- **`'cursor-agent' was not found`** — install the Cursor CLI (<https://cursor.com/cli>) and make sure it's on your PATH; run `cursor-agent login`.
- **PyAudio won't install (macOS)** — `brew install portaudio`, then `pip install -r requirements.txt` again.
- **It mishears me** — speak a beat after you start; try `STT_BACKEND=whisper` for accuracy, or set a fixed `ATLAS_ENERGY_THRESHOLD`.
- **No sound** — `say` is macOS-only; on other systems summaries are printed. Check `ATLAS_TTS_VOICE` is a real voice (`say -v ?`).
- **Cursor edits things I only wanted explained** — Atlas only passes `--force` for edit/terminal intents. To be extra safe, set `ATLAS_CURSOR_FORCE=0` (Cursor will never act without confirmation).

---

## Safety note

When you ask for an edit or a terminal command, Atlas runs Cursor with `--force`, so
Cursor can change files and run commands without asking. That's the point of a
hands-free assistant — but run it on projects you trust, and use version control.
Set `ATLAS_CURSOR_FORCE=0` to require confirmation for everything.
