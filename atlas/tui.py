"""A sleek, interactive terminal UI for Atlas.

A Claude-Code-style REPL for the terminal, branded with a blue cat. Type a
request (or speak one with `/mic`), watch Atlas refine it, run it through the
Cursor agent, and get a spoken-style summary — read aloud too, since Atlas is a
voice tool.

Dependency-free: built on raw ANSI escape codes (256-color for broad terminal
support, including macOS Terminal.app) so it adds nothing to requirements.
"""

from __future__ import annotations

import itertools
import os
import re
import shutil
import sys
import threading
import time
from typing import List, Optional

from . import speech
from .app import run_pipeline
from .config import Config
from .cursor_agent import cursor_available

# --- color palette (256-color, with graceful no-color fallback) -------------

_USE_COLOR = (
    sys.stdout.isatty()
    and os.environ.get("NO_COLOR") is None
    and os.environ.get("TERM") not in (None, "dumb")
)


def _c(code: str) -> str:
    return f"\033[{code}m" if _USE_COLOR else ""


RESET = _c("0")
BOLD = _c("1")
DIM = _c("2")
ITALIC = _c("3")

BLUE = _c("38;5;39")       # primary cat blue
SKY = _c("38;5;75")        # lighter blue
CYAN = _c("38;5;45")       # accent
ICE = _c("38;5;117")       # pale highlight
WHITE = _c("38;5;255")
GRAY = _c("38;5;245")
FAINT = _c("38;5;240")
GREEN = _c("38;5;42")
RED = _c("38;5;203")
GOLD = _c("38;5;215")

CAT = f"{BLUE}=^.^={RESET}"   # inline brand mark (the "blue cat") — narrow ASCII
PAW = f"{SKY}*{RESET}"

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _vlen(text: str) -> int:
    """Visible length of a string, ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub("", text))


def _width(maximum: int = 78) -> int:
    return min(shutil.get_terminal_size((80, 24)).columns, maximum)


# --- drawing helpers --------------------------------------------------------

def _box(lines: List[str], title: Optional[str] = None, color: str = BLUE,
         width: Optional[int] = None) -> str:
    """Render content inside a rounded box, returning the full string."""
    w = width or _width()
    inner = w - 4  # space between "│ " and " │"
    out: List[str] = []

    if title:
        t = f"{color}─ {RESET}{BOLD}{title}{RESET}{color} "
        dashes = w - 2 - _vlen(t)
        out.append(f"{color}╭{RESET}{t}{color}{'─' * max(dashes, 0)}╮{RESET}")
    else:
        out.append(f"{color}╭{'─' * (w - 2)}╮{RESET}")

    for line in lines:
        pad = inner - _vlen(line)
        out.append(f"{color}│{RESET} {line}{' ' * max(pad, 0)} {color}│{RESET}")

    out.append(f"{color}╰{'─' * (w - 2)}╯{RESET}")
    return "\n".join(out)


def _rule(label: str = "", color: str = FAINT) -> str:
    w = _width()
    if not label:
        return f"{color}{'─' * w}{RESET}"
    left = f"{color}── {RESET}{DIM}{label}{RESET} "
    return f"{left}{color}{'─' * max(w - _vlen(left), 0)}{RESET}"


def _wrap(text: str, indent: int = 0) -> List[str]:
    import textwrap

    w = _width() - indent
    pad = " " * indent
    out: List[str] = []
    for para in text.splitlines() or [""]:
        if not para.strip():
            out.append("")
            continue
        for chunk in textwrap.wrap(para, width=max(w, 20)) or [""]:
            out.append(pad + chunk)
    return out


# --- banner -----------------------------------------------------------------

_CAT_ART = [
    r"   /\_/\  ",
    r"  ( o.o ) ",
    r"   > ^ <  ",
]


def banner(cfg: Config) -> None:
    home = os.path.expanduser("~")
    cwd = cfg.workdir
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]

    art = [f"{BLUE}{line}{RESET}" for line in _CAT_ART]
    title = f"{BOLD}{WHITE}A T L A S{RESET}"
    sub = f"{DIM}voice cursor · in your terminal{RESET}"
    ver = f"{FAINT}v{__import__('atlas').__version__}{RESET}"

    print()
    print(f"{art[0]}")
    print(f"{art[1]}   {title}   {ver}")
    print(f"{art[2]}   {sub}")
    print()

    voice = "elevenlabs" if speech.elevenlabs_available(cfg) else (
        "say" if speech.say_available() else "off"
    )
    cur = f"{GREEN}ready{RESET}" if cursor_available(cfg) else f"{RED}missing{RESET}"

    info = [
        f"{GRAY}model{RESET}   {WHITE}{cfg.model}{RESET}",
        f"{GRAY}cursor{RESET}  {cur}",
        f"{GRAY}voice{RESET}   {WHITE}{voice}{RESET}",
        f"{GRAY}cwd{RESET}     {SKY}{cwd}{RESET}",
        "",
        f"{ICE}Just speak when you're ready — Atlas is listening.{RESET}",
        f"{DIM}Say \"exit atlas\" or press Ctrl+C to quit.{RESET}",
    ]
    print(_box(info, title=f"{CAT}  Atlas", color=BLUE))
    print()


def help_box() -> None:
    rows = [
        f"{BOLD}{WHITE}Just speak{RESET} — Atlas listens and replies aloud "
        f"automatically.",
        "",
        f"{DIM}When a microphone isn't available you can type instead:{RESET}",
        f"{CYAN}/say{RESET} TEXT  speak a line in the Atlas voice",
        f"{CYAN}/clear{RESET}    clear the screen",
        f"{CYAN}/help{RESET}     show this help",
        f"{CYAN}/exit{RESET}     quit (or say \"exit atlas\")",
        "",
        f"{DIM}Tips: edit/terminal requests let Cursor act; plans & "
        f"explanations don't.{RESET}",
    ]
    print(_box(rows, title=f"{PAW} help", color=SKY))
    print()


# --- spinner ----------------------------------------------------------------

class Spinner:
    """A small threaded braille spinner with a live label and elapsed timer."""

    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label: str = "Working") -> None:
        self.label = label
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start = 0.0

    def _run(self) -> None:
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            elapsed = int(time.time() - self._start)
            line = (
                f"\r{BLUE}{frame}{RESET} {WHITE}{self.label}{RESET}"
                f"{DIM} … {elapsed}s{RESET}{CAT_TRAIL}"
            )
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.08)

    def update(self, label: str) -> None:
        self.label = label

    def __enter__(self) -> "Spinner":
        self._start = time.time()
        if _USE_COLOR:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            print(f"{self.label} …")
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
            sys.stdout.write("\r" + " " * (_width()) + "\r")
            sys.stdout.flush()


CAT_TRAIL = f"   {FAINT}🐾{RESET}" if _USE_COLOR else ""


# --- result rendering -------------------------------------------------------

_INTENT_COLOR = {
    "plan": BLUE,
    "explain": CYAN,
    "edit": GOLD,
    "terminal": GOLD,
    "navigate": SKY,
    "other": GRAY,
}


def render(result: dict) -> None:
    if result.get("error") and not result.get("summary"):
        print(f"{RED}✗{RESET} {result['error']}\n")
        return

    intent = result.get("intent") or "other"
    color = _INTENT_COLOR.get(intent, GRAY)
    refined = result.get("refined") or ""

    badge = f"{color}▌{RESET} {color}{intent}{RESET}"
    print(f"\n{badge}")
    if refined:
        print(f"  {FAINT}refined{RESET}")
        for line in _wrap(refined, indent=2):
            print(f"  {DIM}{line.strip()}{RESET}")

    output = (result.get("output") or "").strip()
    if output:
        print("\n" + _rule("cursor output"))
        for line in _wrap(output):
            print(f"{GRAY}{line}{RESET}")

    summary = (result.get("summary") or "").strip()
    if summary:
        print("\n" + _rule())
        print(f"{CAT}  {BOLD}{WHITE}Atlas{RESET}")
        for line in _wrap(summary, indent=4):
            print(f"{ICE}{line}{RESET}")

    if result.get("error"):
        print(f"\n{GOLD}!{RESET} {DIM}{result['error']}{RESET}")
    print()


# --- interactive loop -------------------------------------------------------

def _prompt() -> str:
    return f"{BLUE}{BOLD}={RESET}{BLUE}^{RESET} "


def _read_command() -> Optional[str]:
    """Read one line of input. Returns None on EOF (Ctrl+D)."""
    try:
        return input(_prompt())
    except EOFError:
        return None


def _run_with_spinner(text: str, cfg: Config) -> dict:
    """Run the Atlas pipeline while narrating the stages on a spinner."""
    with Spinner("Refining your request") as sp:
        holder: dict = {}

        def _work() -> None:
            holder["r"] = run_pipeline(text, cfg)

        worker = threading.Thread(target=_work, daemon=True)
        worker.start()
        stages = [
            (0.0, "Refining your request"),
            (1.6, "Handing it to Cursor"),
            (4.0, "Summarizing the result"),
        ]
        start = time.time()
        idx = 0
        while worker.is_alive():
            el = time.time() - start
            while idx + 1 < len(stages) and el >= stages[idx + 1][0]:
                idx += 1
                sp.update(stages[idx][1])
            time.sleep(0.1)
        worker.join()
    return holder.get("r", {"error": "No result."})


def _is_exit(text: str, cfg: Config) -> bool:
    norm = text.strip().lower().rstrip(".!?,")
    if norm in cfg.exit_phrases:
        return True
    # Catch natural phrasings like "okay, exit atlas please".
    return any(p in norm for p in ("exit atlas", "quit atlas", "shut down atlas"))


def _voice_loop(cfg: Config, listener) -> int:
    """Voice-first loop: listen on the mic, act, and reply aloud — no setup."""
    from .voice_input import VoiceInputError

    greeting = (
        "Atlas is online and listening. Just speak your request. "
        "Say exit to quit."
    )
    print(f"{CAT}  {WHITE}{greeting}{RESET}\n")
    speech.speak(greeting, cfg)

    while True:
        try:
            with Spinner("Listening"):
                text = listener.listen_once()
        except KeyboardInterrupt:
            break
        except VoiceInputError as exc:
            print(f"{RED}!{RESET} {DIM}{exc}{RESET}\n")
            time.sleep(0.5)
            continue

        if not text:
            print(f"{DIM}…didn't catch that — keep talking.{RESET}")
            continue

        print(f"{FAINT}heard{RESET}  {WHITE}{text}{RESET}")
        if _is_exit(text, cfg):
            break

        try:
            result = _run_with_spinner(text, cfg)
        except KeyboardInterrupt:
            print(f"\n{DIM}cancelled.{RESET}\n")
            continue

        render(result)
        if result.get("summary"):
            speech.speak(result["summary"], cfg)

    bye = "Goodbye."
    speech.speak(bye, cfg)
    print(f"\n{CAT}  {DIM}goodbye.{RESET}\n")
    return 0


def _typed_loop(cfg: Config) -> int:
    """Fallback when no microphone is available: type commands, hear replies."""
    speak = speech.elevenlabs_available(cfg) or speech.say_available()

    while True:
        try:
            raw = _read_command()
        except KeyboardInterrupt:
            print(f"\n{DIM}(use /exit to quit){RESET}")
            continue

        if raw is None:  # Ctrl+D
            print()
            break

        text = raw.strip()
        if not text:
            continue

        low = text.lower()
        if low in ("/exit", "/quit", "/q", "exit atlas", "quit atlas"):
            break
        if low in ("/help", "/?", "help"):
            help_box()
            continue
        if low in ("/clear", "/cls"):
            os.system("cls" if os.name == "nt" else "clear")
            banner(cfg)
            continue
        if low.startswith("/say"):
            phrase = text[4:].strip()
            if phrase:
                speech.speak(phrase, cfg, force_print=not speak)
            continue
        if text.startswith("/"):
            print(f"{GOLD}?{RESET} unknown command {WHITE}{text}{RESET} "
                  f"{DIM}— try /help{RESET}\n")
            continue

        try:
            result = _run_with_spinner(text, cfg)
        except KeyboardInterrupt:
            print(f"\n{DIM}cancelled.{RESET}\n")
            continue

        render(result)
        if speak and result.get("summary"):
            speech.speak(result["summary"], cfg)

    print(f"\n{CAT}  {DIM}goodbye.{RESET}\n")
    return 0


def run_tui(cfg: Config) -> int:
    """Run the interactive Atlas terminal UI. Returns an exit code.

    Voice-first by default: it brings up the microphone and speaks replies with
    no manual setup, so you can just start talking. If no microphone is
    available, it falls back to a typed prompt.
    """
    os.system("")  # enable ANSI on some terminals; harmless elsewhere
    banner(cfg)

    listener = None
    try:
        from .voice_input import VoiceListener

        listener = VoiceListener(cfg)
    except Exception as exc:  # noqa: BLE001 - any mic/STT issue -> typed fallback
        print(f"{GOLD}!{RESET} {DIM}Microphone unavailable — "
              f"type your commands instead.{RESET}")
        print(f"{FAINT}  {str(exc).splitlines()[0]}{RESET}\n")

    if listener is not None:
        return _voice_loop(cfg, listener)
    return _typed_loop(cfg)
