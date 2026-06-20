"""Orchestration: tie the microphone, Claude agents, Cursor, speech, and Convex."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from . import speech
from .cloud import CloudStore
from .config import Config
from .cursor_agent import CursorError, run_cursor
from .formatter import format_command
from .summarizer import summarize_for_speech

GREETING = "Atlas is online and listening."
GOODBYE = "Goodbye. Atlas is shutting down."

# Intents for which Cursor is allowed to edit files / run terminal commands.
_ACTING_INTENTS = ("edit", "terminal")


@dataclass
class CommandResult:
    """Structured outcome of one command — consumed by the mic loop and the worker."""

    transcript: str
    intent: str
    refined_prompt: str
    workdir: str
    cursor_output: str = ""
    summary: str = ""
    status: str = "done"  # "done" | "error"
    error: Optional[str] = None


def _decide_force(intent: str, cfg: Config) -> bool:
    """Whether to pass --force to Cursor for this request."""
    if cfg.cursor_force is not None:
        return cfg.cursor_force
    return intent in _ACTING_INTENTS


def _resolve_workdir(
    target: Optional[str], active_workdir: Optional[str], cfg: Config, cloud: Optional[CloudStore]
) -> str:
    """Pick the directory this run executes in, persisting an explicit switch."""
    # 1. The user explicitly asked to switch to / build in a directory.
    if target:
        expanded = os.path.expanduser(target)
        if os.path.isdir(expanded):
            if cloud and cloud.enabled:
                cloud.set_workdir(expanded)
            return expanded
        print(f"[atlas] ⚠ requested directory {target!r} doesn't exist; keeping current.")
    # 2. The remembered active directory from a previous session.
    if active_workdir:
        expanded = os.path.expanduser(active_workdir)
        if os.path.isdir(expanded):
            return expanded
    # 3. The configured default.
    return cfg.workdir


def _record(cloud, channel, transcript, refined, intent, output, summary, workdir, status):
    if cloud and cloud.enabled:
        cloud.record_run(
            channel=channel,
            transcript=transcript,
            refined_prompt=refined,
            intent=intent,
            cursor_output=output,
            summary=summary,
            workdir=workdir,
            status=status,
        )


def process_command(
    transcript: str,
    cfg: Config,
    *,
    speak: bool = True,
    channel: str = "mic",
    cloud: Optional[CloudStore] = None,
) -> CommandResult:
    """Run one full turn: (history-aware) format -> Cursor -> summarize -> speak.

    When `speak` is False everything is printed instead of spoken. Records the run to
    Convex when `cloud` is enabled. Returns a structured CommandResult.
    """
    print(f"\n🗣  Heard: {transcript}")

    # Pull cross-session context (history + active directory) from Convex.
    history = []
    active_workdir = None
    known_dirs = None
    if cloud and cloud.enabled:
        history = cloud.recent_history()
        cfg_doc = cloud.get_config() or {}
        active_workdir = cfg_doc.get("activeWorkdir")
        known_dirs = cfg_doc.get("knownDirs")

    # 1. Claude formats the spoken command (resolving "my last build", directory, …).
    try:
        fmt = format_command(
            transcript,
            cfg,
            history=history,
            active_workdir=active_workdir,
            known_dirs=known_dirs,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Formatting failed: {exc}")
        speech.speak("I couldn't process that command.", cfg, force_print=not speak)
        return CommandResult(
            transcript=transcript, intent="other", refined_prompt="",
            workdir=cfg.workdir, status="error", error=str(exc),
        )

    intent, refined, target = fmt.intent, fmt.refined_prompt, fmt.target_workdir
    print(f"🧠 Intent: {intent}")
    print(f"➡  Cursor prompt: {refined}")

    workdir = _resolve_workdir(target, active_workdir, cfg, cloud)
    if target:
        print(f"📁 Working in: {workdir}")

    if speak and cfg.speak_preface:
        speech.speak("Working on it.", cfg)

    # 2. Cursor ("Voice Cursor") does the actual work in the chosen directory.
    force = _decide_force(intent, cfg)
    try:
        output = run_cursor(refined, cfg, force=force, workdir=workdir)
    except CursorError as exc:
        print(f"❌ {exc}")
        speech.speak("Cursor ran into a problem. " + str(exc), cfg, force_print=not speak)
        _record(cloud, channel, transcript, refined, intent, "", "", workdir, "error")
        return CommandResult(
            transcript=transcript, intent=intent, refined_prompt=refined,
            workdir=workdir, status="error", error=str(exc),
        )

    print(f"\n📄 Cursor output:\n{output}\n")

    # 3. Claude summarizes Cursor's output for the spoken reply.
    try:
        summary = summarize_for_speech(output, refined, cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Summarizing failed: {exc}")
        summary = "Cursor finished, but I couldn't summarize the result."

    print(f"📝 Summary: {summary}")
    speech.speak(summary, cfg, force_print=not speak)

    _record(cloud, channel, transcript, refined, intent, output, summary, workdir, "done")
    return CommandResult(
        transcript=transcript, intent=intent, refined_prompt=refined, workdir=workdir,
        cursor_output=output, summary=summary, status="done",
    )


def run_loop(cfg: Config) -> None:
    """Continuous voice loop: listen, act, speak, repeat."""
    from .voice_input import VoiceInputError, VoiceListener

    try:
        listener = VoiceListener(cfg)
    except VoiceInputError as exc:
        print(f"❌ {exc}")
        return

    cloud = CloudStore(cfg)
    if cloud.enabled:
        print("📚 History: connected to Convex.")
    elif cloud.error:
        print(f"📚 {cloud.error}")

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
            process_command(transcript, cfg, speak=True, channel="mic", cloud=cloud)
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
