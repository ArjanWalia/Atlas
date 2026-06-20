"""Text-to-speech output via the macOS `say` command.

On non-macOS systems (or when `say` is unavailable) the text is printed instead,
so the rest of the pipeline still works for development and testing.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess

from .config import Config

# Patterns used to make Claude/Cursor text sound natural when read aloud.
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_MD_TOKENS = re.compile(r"[*_#>~|]")
_MULTISPACE = re.compile(r"\s+")


def clean_for_speech(text: str) -> str:
    """Strip markdown / code so a TTS voice reads it smoothly."""
    if not text:
        return ""
    text = _CODE_FENCE.sub(" (code omitted) ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _MD_TOKENS.sub("", text)
    text = _MULTISPACE.sub(" ", text)
    return text.strip()


def say_available() -> bool:
    """True if the macOS `say` command can be used."""
    return platform.system() == "Darwin" and shutil.which("say") is not None


def speak(text: str, cfg: Config, *, force_print: bool = False) -> None:
    """Speak `text` aloud with macOS `say`, or print it as a fallback."""
    text = clean_for_speech(text)
    if not text:
        return

    if force_print or not say_available():
        print(f"\n🔊 {text}\n")
        return

    cmd = ["say"]
    if cfg.tts_voice:
        cmd += ["-v", cfg.tts_voice]
    if cfg.tts_rate:
        cmd += ["-r", str(cfg.tts_rate)]
    cmd.append(text)

    try:
        subprocess.run(cmd, check=False)
    except Exception as exc:  # noqa: BLE001 - never let TTS crash the loop
        print(f"[atlas] speech failed ({exc}); printing instead:\n🔊 {text}\n")
