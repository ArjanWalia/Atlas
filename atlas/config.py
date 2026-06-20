"""Configuration for Atlas, loaded from environment variables / a `.env` file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; env vars still work without it.
    load_dotenv = None


# --- small env-parsing helpers ---------------------------------------------

def _str(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v in (None, ""):
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "y")


def _opt_bool(name: str) -> Optional[bool]:
    """Tri-state flag: returns None when unset so callers can pick a default."""
    v = os.getenv(name)
    if v in (None, ""):
        return None
    return v.strip().lower() in ("1", "true", "yes", "on", "y")


def _int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v in (None, ""):
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _opt_int(name: str) -> Optional[int]:
    v = os.getenv(name)
    if v in (None, ""):
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _opt_float(name: str, default: Optional[float]) -> Optional[float]:
    v = os.getenv(name)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except ValueError:
        return default


DEFAULT_EXIT_PHRASES = (
    "exit atlas",
    "exit, atlas",
    "atlas exit",
    "quit atlas",
    "stop atlas",
    "atlas stop",
    "goodbye atlas",
    "shut down atlas",
)


@dataclass
class Config:
    """All tunable settings for an Atlas run."""

    # Anthropic / Claude agents
    anthropic_api_key: Optional[str]
    model: str = "claude-opus-4-8"
    format_thinking: bool = False
    effort: str = "medium"
    format_max_tokens: int = 1024
    summary_max_tokens: int = 512

    # Cursor ("Voice Cursor") CLI agent
    cursor_command: str = "cursor-agent"
    cursor_model: Optional[str] = None
    cursor_force: Optional[bool] = None  # None => decide automatically from intent
    cursor_no_stream: bool = True
    cursor_output_format: str = "text"
    cursor_api_key: Optional[str] = None
    workdir: str = "."
    cursor_timeout: int = 600

    # Speech-to-text
    stt_backend: str = "google"  # "google" | "whisper"
    whisper_model: str = "base.en"
    energy_threshold: Optional[int] = None
    mic_index: Optional[int] = None
    pause_threshold: float = 0.8
    phrase_time_limit: Optional[float] = 30.0
    listen_timeout: Optional[float] = None

    # Text-to-speech (macOS `say`)
    tts_voice: Optional[str] = None
    tts_rate: Optional[int] = None
    speak_preface: bool = True

    exit_phrases: tuple = field(default_factory=lambda: DEFAULT_EXIT_PHRASES)

    @classmethod
    def load(cls) -> "Config":
        """Build a Config from the environment (loading `.env` if present)."""
        if load_dotenv is not None:
            load_dotenv()
        return cls(
            anthropic_api_key=_str("ANTHROPIC_API_KEY"),
            model=_str("ATLAS_MODEL", "claude-opus-4-8"),
            format_thinking=_bool("ATLAS_FORMAT_THINKING", False),
            effort=_str("ATLAS_EFFORT", "medium"),
            format_max_tokens=_int("ATLAS_FORMAT_MAX_TOKENS", 1024),
            summary_max_tokens=_int("ATLAS_SUMMARY_MAX_TOKENS", 512),
            cursor_command=_str("ATLAS_CURSOR_COMMAND", "cursor-agent"),
            cursor_model=_str("ATLAS_CURSOR_MODEL"),
            cursor_force=_opt_bool("ATLAS_CURSOR_FORCE"),
            cursor_no_stream=_bool("ATLAS_CURSOR_NO_STREAM", True),
            cursor_output_format=_str("ATLAS_CURSOR_OUTPUT_FORMAT", "text"),
            cursor_api_key=_str("CURSOR_API_KEY"),
            workdir=_str("ATLAS_WORKDIR", os.getcwd()),
            cursor_timeout=_int("ATLAS_CURSOR_TIMEOUT", 600),
            stt_backend=(_str("STT_BACKEND", "google") or "google").lower(),
            whisper_model=_str("ATLAS_WHISPER_MODEL", "base.en"),
            energy_threshold=_opt_int("ATLAS_ENERGY_THRESHOLD"),
            mic_index=_opt_int("ATLAS_MIC_INDEX"),
            pause_threshold=_float("ATLAS_PAUSE_THRESHOLD", 0.8),
            phrase_time_limit=_opt_float("ATLAS_PHRASE_TIME_LIMIT", 30.0),
            listen_timeout=_opt_float("ATLAS_LISTEN_TIMEOUT", None),
            tts_voice=_str("ATLAS_TTS_VOICE"),
            tts_rate=_opt_int("ATLAS_TTS_RATE"),
            speak_preface=_bool("ATLAS_SPEAK_PREFACE", True),
        )

    def validate(self) -> None:
        """Raise ValueError if required settings are missing."""
        if not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key "
                "(get one at https://console.anthropic.com/)."
            )
