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

> **Run from the repo root.** Every command below assumes you're in the folder that
> contains `requirements.txt` and `run.py` — not the `atlas/` subfolder. macOS is
> case-insensitive, so `cd Atlas` can drop you inside the lowercase `atlas/` package
> by mistake; if `requirements.txt` isn't in your current folder, you're one level too
> deep. (`python run.py ...` sidesteps this — it works from any directory.)

> **macOS microphone dependency:** PyAudio needs PortAudio. If `pip install` fails on PyAudio, run `brew install portaudio` first, then re-run the install.

### 2. Add your Anthropic key

```bash
cp .env.example .env
# open .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Install & authenticate the Cursor CLI ("Voice Cursor")

```bash
# Install the Cursor CLI (drops `cursor-agent` into ~/.local/bin)
curl https://cursor.com/install -fsS | bash

# Add ~/.local/bin to your PATH so the command is found (zsh shown):
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
cursor-agent --version    # confirm it's on PATH

# Authenticate once (opens your browser), or set CURSOR_API_KEY in .env
cursor-agent login
```

> Atlas auto-searches `~/.local/bin` and accepts a binary named either `cursor-agent`
> or `agent`, so it works even before you fix PATH. If yours is named `agent`, set
> `ATLAS_CURSOR_COMMAND=agent` in `.env`.

**To make Voice Cursor run on Opus 4.8:** inside the Cursor app, add your Anthropic
API key and select **Opus 4.8** as the model — the CLI uses that configuration.
Alternatively, set `ATLAS_CURSOR_MODEL` in `.env` to the exact model id your Cursor
exposes for Opus 4.8.

### 4. Verify everything

```bash
python run.py --check      # works from any directory
```

You'll get a checklist for your API key, the Cursor CLI, `say`, and the microphone —
plus a reminder if you're not running from the repo root.

---

## Running it

Run `python run.py` from **any** directory, or `python -m atlas` when you're in the
repo root (the folder with `requirements.txt`):

```bash
# Full voice loop — speak your commands (works from any directory)
python run.py

# or, if you're in the repo root:
python -m atlas
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

## Cloud history & directory memory (Convex)

Optional. With a Convex deployment, Atlas stores **every run** and remembers your
**active project directory** — so from any session you can say *"build on my last
project"* or *"switch to ~/projects/foo and add a test"* and it sticks across projects.

```bash
cd backend
npm install
npx convex dev        # creates a deployment, prints a URL like https://xxx.convex.cloud
```

Put the URL in your repo-root `.env`:

```
CONVEX_URL=https://your-project-123.convex.cloud
```

Runs now persist and directory switches are remembered. Without `CONVEX_URL`, Atlas
works exactly as before (history just disabled). Details: `backend/README.md`.

> Your `ANTHROPIC_API_KEY` and Cursor auth stay on your Mac — Convex only stores
> commands, results, and the active directory, never your keys.

## Troubleshooting

- **`No module named atlas`** — you're not in the repo root. `cd` to the folder containing `requirements.txt` and `run.py` (on macOS, `cd Atlas` can land you in the lowercase `atlas/` package), or just use `python run.py`, which works from anywhere.
- **`cursor-agent: command not found`** — it's installed in `~/.local/bin`, which isn't on your PATH yet. Run `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc`, then `cursor-agent --version`. If the binary is named `agent`, set `ATLAS_CURSOR_COMMAND=agent` in `.env`. (Atlas also auto-searches `~/.local/bin` and tries both names.)
- **PyAudio won't install (macOS)** — `brew install portaudio`, then `pip install -r requirements.txt` again.
- **It's not picking up my voice** — run `python run.py --mic-test`. On macOS this is almost always microphone permission: System Settings → Privacy & Security → Microphone → enable your terminal (Terminal, iTerm, or VS Code), then fully quit and reopen it. Also confirm the right input device with `ATLAS_MIC_INDEX`, and lower `ATLAS_ENERGY_THRESHOLD` if your mic is quiet.
- **It mishears me** — speak a beat after you start; try `STT_BACKEND=whisper` for accuracy, or set a fixed `ATLAS_ENERGY_THRESHOLD`.
- **No sound** — `say` is macOS-only; on other systems summaries are printed. Check `ATLAS_TTS_VOICE` is a real voice (`say -v ?`).
- **Cursor edits things I only wanted explained** — Atlas only passes `--force` for edit/terminal intents. To be extra safe, set `ATLAS_CURSOR_FORCE=0` (Cursor will never act without confirmation).

---

## Safety note

When you ask for an edit or a terminal command, Atlas runs Cursor with `--force`, so
Cursor can change files and run commands without asking. That's the point of a
hands-free assistant — but run it on projects you trust, and use version control.
Set `ATLAS_CURSOR_FORCE=0` to require confirmation for everything.
