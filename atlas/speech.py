"""Text-to-speech output.

Atlas can speak through ElevenLabs or the macOS `say` command. If speech output is
unavailable, the text is printed so the rest of the pipeline still works.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import tempfile
from urllib import error, request

from .config import Config


def _ssl_context() -> ssl.SSLContext:
    """Build an SSL context with a valid CA bundle.

    Stock python.org builds on macOS often ship without trusted roots, which
    makes HTTPS fail with CERTIFICATE_VERIFY_FAILED. Prefer `certifi`'s bundle
    so ElevenLabs works without the user running "Install Certificates".
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - fall back to the system default
        return ssl.create_default_context()


_SSL_CONTEXT = _ssl_context()

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


def _afplay_available() -> bool:
    """True if macOS can play generated audio files."""
    return platform.system() == "Darwin" and shutil.which("afplay") is not None


def elevenlabs_available(cfg: Config) -> bool:
    """True if ElevenLabs TTS is configured (used by the web UI / browser)."""
    return bool(cfg.elevenlabs_api_key)


def synthesize_elevenlabs(text: str, cfg: Config) -> bytes:
    """Return MP3 audio bytes for `text` from ElevenLabs.

    Raises RuntimeError if the key is missing or the request fails — callers
    decide how to degrade (play locally, stream to the browser, or print).
    """
    if not cfg.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set.")

    payload = {
        "text": text,
        "model_id": cfg.elevenlabs_model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    url = (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        f"{cfg.elevenlabs_voice_id}?output_format=mp3_44100_128"
    )
    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": cfg.elevenlabs_api_key,
        },
    )

    try:
        with request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as response:
            return response.read()
    except (OSError, error.URLError, error.HTTPError) as exc:
        raise RuntimeError(f"ElevenLabs request failed: {exc}") from exc


def _speak_with_elevenlabs(text: str, cfg: Config) -> bool:
    """Generate speech with ElevenLabs and play it locally."""
    if not cfg.elevenlabs_api_key:
        print("[atlas] ELEVENLABS_API_KEY is missing; printing instead.")
        return False
    if not _afplay_available():
        print("[atlas] afplay is unavailable; printing instead.")
        return False

    try:
        audio = synthesize_elevenlabs(text, cfg)
    except RuntimeError as exc:
        msg = str(exc)
        if "402" in msg:
            hint = "ElevenLabs account is out of credits (HTTP 402)."
        elif "401" in msg:
            hint = "ElevenLabs API key is invalid (HTTP 401)."
        elif "429" in msg:
            hint = "ElevenLabs rate limit hit (HTTP 429)."
        else:
            hint = msg
        print(f"[atlas] Voice unavailable — {hint} Falling back to macOS `say`.")
        # Last resort: speak with the built-in macOS voice so output is still heard.
        if say_available():
            cmd = ["say"]
            if cfg.tts_voice:
                cmd += ["-v", cfg.tts_voice]
            if cfg.tts_rate:
                cmd += ["-r", str(cfg.tts_rate)]
            cmd.append(text)
            try:
                subprocess.run(cmd, check=False)
                return True
            except Exception:  # noqa: BLE001
                pass
        return False

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(audio)
        path = tmp.name
    try:
        subprocess.run(["afplay", path], check=False)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return True


def speak(text: str, cfg: Config, *, force_print: bool = False) -> None:
    """Speak `text` aloud, or print it as a fallback."""
    text = clean_for_speech(text)
    if not text:
        return

    if force_print:
        print(f"\n🔊 {text}\n")
        return

    if cfg.tts_backend == "elevenlabs":
        if _speak_with_elevenlabs(text, cfg):
            return
        print(f"\n🔊 {text}\n")
        return

    if not say_available():
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
