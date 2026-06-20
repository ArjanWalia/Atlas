"""Command-line entry point:  `python -m atlas`  (or `python run.py`)."""

from __future__ import annotations

import argparse
import sys

from . import __version__, speech
from .config import Config


def _check(cfg: Config) -> int:
    """Print an environment / dependency report and return an exit code."""
    from .cursor_agent import cursor_available

    print(f"Atlas {__version__} — environment check")
    print("=" * 48)
    ok = True

    if cfg.anthropic_api_key:
        print("✅ ANTHROPIC_API_KEY is set")
    else:
        print("❌ ANTHROPIC_API_KEY is missing (add it to .env)")
        ok = False
    print(f"   Claude model (agents): {cfg.model}")

    if cursor_available(cfg):
        print(f"✅ Cursor CLI found: {cfg.cursor_command}")
    else:
        print(
            f"❌ Cursor CLI '{cfg.cursor_command}' not on PATH "
            "— install from https://cursor.com/cli"
        )
        ok = False
    print(f"   Cursor model: {cfg.cursor_model or '(Cursor default — set Opus 4.8 in Cursor)'}")

    if speech.say_available():
        print("✅ macOS `say` available for speech output")
    else:
        print("⚠  macOS `say` unavailable — summaries will be printed instead")

    try:
        import speech_recognition  # noqa: F401
        print("✅ SpeechRecognition installed")
    except ImportError:
        print("❌ SpeechRecognition not installed — run: pip install -r requirements.txt")
        ok = False
    print(f"   Speech-to-text backend: {cfg.stt_backend}")

    print("=" * 48)
    print("All checks passed ✅" if ok else "Some checks failed ❌ — see above")
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Atlas — a hands-free voice bridge to the Cursor IDE agent.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Check API key, Cursor CLI, microphone and `say`, then exit.",
    )
    parser.add_argument(
        "--text", metavar="COMMAND",
        help="Process a single typed command instead of using the microphone.",
    )
    parser.add_argument(
        "--no-speak", action="store_true",
        help="Print the summary instead of speaking it (useful for testing).",
    )
    parser.add_argument(
        "--version", action="version", version=f"Atlas {__version__}",
    )
    args = parser.parse_args(argv)

    cfg = Config.load()

    if args.check:
        return _check(cfg)

    try:
        cfg.validate()
    except ValueError as exc:
        print(f"❌ {exc}")
        return 1

    from .app import process_command, run_loop

    if args.text is not None:
        process_command(args.text, cfg, speak=not args.no_speak)
        return 0

    run_loop(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
