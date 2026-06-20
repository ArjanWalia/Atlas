"""Orchestration: tie the microphone, Claude agents, Cursor, and speech together."""

from __future__ import annotations

from typing import Optional

from . import speech
from .config import Config
from .cursor_agent import CursorError, run_cursor
from .formatter import format_command
from .summarizer import summarize_for_speech

GREETING = "Atlas is online and listening."
GOODBYE = "Goodbye. Atlas is shutting down."

# Intents for which Cursor is allowed to edit files / run terminal commands.
_ACTING_INTENTS = ("edit", "terminal")


def _decide_force(intent: str, cfg: Config) -> bool:
    """Whether to pass --force to Cursor for this request."""
    if cfg.cursor_force is not None:
        return cfg.cursor_force
    return intent in _ACTING_INTENTS


def run_pipeline(transcript: str, cfg: Config) -> dict:
    """Run one turn (format -> Cursor -> summarize) and return structured results.

    Unlike `process_command`, this never speaks or prints — it's the headless core
    used by the web UI. Returns a dict with keys: `transcript`, `intent`,
    `refined`, `output`, `summary`, `error` (None on success).
    """
    result = {
        "transcript": transcript,
        "intent": None,
        "refined": None,
        "output": None,
        "summary": None,
        "error": None,
    }

    try:
        intent, refined = format_command(transcript, cfg)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"Formatting failed: {exc}"
        return result
    result["intent"] = intent
    result["refined"] = refined

    force = _decide_force(intent, cfg)
    try:
        output = run_cursor(refined, cfg, force=force)
    except CursorError as exc:
        result["error"] = str(exc)
        return result
    result["output"] = output

    try:
        result["summary"] = summarize_for_speech(output, refined, cfg)
    except Exception as exc:  # noqa: BLE001
        result["summary"] = "Cursor finished, but I couldn't summarize the result."
        result["error"] = f"Summarizing failed: {exc}"

    return result


def process_command(transcript: str, cfg: Config, *, speak: bool = True) -> Optional[str]:
    """Run one full turn: format -> Cursor -> summarize -> speak.

    When `speak` is False (e.g. testing on a non-mac box) everything is printed
    instead of spoken. Returns the spoken summary, or None on failure.
    """
    print(f"\n🗣  Heard: {transcript}")

    # 1. Claude formats the spoken command into a clean Cursor prompt.
    try:
        intent, refined = format_command(transcript, cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Formatting failed: {exc}")
        speech.speak("I couldn't process that command.", cfg, force_print=not speak)
        return None

    print(f"🧠 Intent: {intent}")
    print(f"➡  Cursor prompt: {refined}")

    if speak and cfg.speak_preface:
        speech.speak("Working on it.", cfg)

    # 2. Cursor ("Voice Cursor") does the actual work.
    force = _decide_force(intent, cfg)
    try:
        output = run_cursor(refined, cfg, force=force)
    except CursorError as exc:
        print(f"❌ {exc}")
        speech.speak(
            "Cursor ran into a problem. " + str(exc), cfg, force_print=not speak
        )
        return None

    print(f"\n📄 Cursor output:\n{output}\n")

    # 3. Claude summarizes Cursor's output for the spoken reply.
    try:
        summary = summarize_for_speech(output, refined, cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Summarizing failed: {exc}")
        summary = "Cursor finished, but I couldn't summarize the result."

    print(f"📝 Summary: {summary}")
    speech.speak(summary, cfg, force_print=not speak)
    return summary


def run_loop(cfg: Config) -> None:
    """Continuous voice loop: listen, act, speak, repeat."""
    from .voice_input import VoiceInputError, VoiceListener

    try:
        listener = VoiceListener(cfg)
    except VoiceInputError as exc:
        print(f"❌ {exc}")
        return

    speech.speak(GREETING, cfg)
    print(
        "\nAtlas is listening. Speak a command after the beep of silence.\n"
        "Say 'exit atlas' to quit, or press Ctrl+C.\n"
    )

    while True:
        try:
            print("🎧 Listening… (speak now)")
            transcript = listener.listen_once()
            if not transcript:
                print("   …didn't catch that — try again.")
                continue
            if transcript.strip().lower().rstrip(".!?") in cfg.exit_phrases:
                speech.speak(GOODBYE, cfg)
                break
            process_command(transcript, cfg, speak=True)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            speech.speak(GOODBYE, cfg)
            break
        except Exception as exc:  # noqa: BLE001 - keep the loop alive on any error
            print(f"⚠  Error: {exc}")
            try:
                speech.speak("Sorry, something went wrong. Please try again.", cfg)
            except Exception:  # noqa: BLE001
                pass
