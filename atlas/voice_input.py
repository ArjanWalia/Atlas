"""Microphone capture + speech-to-text.

Uses the `SpeechRecognition` library for mic capture and voice-activity detection.
Transcription backend is selectable:
  * "google"  — Google Web Speech API (no setup, needs internet)
  * "whisper" — local OpenAI Whisper (offline & private; needs `openai-whisper`)
"""

from __future__ import annotations

import os
from typing import Optional

from .config import Config


class VoiceInputError(RuntimeError):
    """Raised when the microphone or speech backend cannot be used."""


def _import_sr():
    try:
        import speech_recognition as sr  # type: ignore
        return sr
    except ImportError as exc:
        raise VoiceInputError(
            "SpeechRecognition is not installed.\n"
            "Run: pip install -r requirements.txt\n"
            "On macOS the microphone also needs PortAudio: brew install portaudio"
        ) from exc


def list_microphones() -> list:
    """Return the names of available input devices (index = position in list)."""
    sr = _import_sr()
    try:
        return list(sr.Microphone.list_microphone_names())
    except Exception as exc:  # noqa: BLE001
        raise VoiceInputError(f"Could not list microphones: {exc}") from exc


class VoiceListener:
    """Captures spoken phrases from the default microphone and transcribes them."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.sr = _import_sr()
        self.recognizer = self.sr.Recognizer()
        self.recognizer.pause_threshold = cfg.pause_threshold

        if cfg.energy_threshold is not None:
            self.recognizer.energy_threshold = cfg.energy_threshold
            self.recognizer.dynamic_energy_threshold = False
        else:
            self.recognizer.dynamic_energy_threshold = True

        try:
            self.mic = self.sr.Microphone(device_index=cfg.mic_index)
        except Exception as exc:  # noqa: BLE001
            raise VoiceInputError(
                "Could not open a microphone. Make sure PyAudio/PortAudio is installed "
                f"and an input device is available.\nDetails: {exc}"
            ) from exc

        # Calibrate to the room's ambient noise once at startup.
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.6)

    def listen_once(self, timeout: Optional[float] = None) -> Optional[str]:
        """Block until a phrase is spoken, then return its transcription.

        `timeout` overrides the configured seconds-to-wait-for-speech-to-start.
        Returns None if it timed out or the audio was unintelligible.
        """
        sr = self.sr
        eff_timeout = timeout if timeout is not None else self.cfg.listen_timeout
        with self.mic as source:
            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=eff_timeout,
                    phrase_time_limit=self.cfg.phrase_time_limit,
                )
            except sr.WaitTimeoutError:
                return None
        return self._recognize(audio)

    def _recognize(self, audio) -> Optional[str]:
        return _recognize_audio(self.recognizer, self.sr, self.cfg, audio)


def _recognize_audio(recognizer, sr, cfg: Config, audio) -> Optional[str]:
    """Backend-agnostic recognition shared by the mic listener and file transcription."""
    if cfg.stt_backend == "whisper":
        try:
            text = recognizer.recognize_whisper(audio, model=cfg.whisper_model)
        except sr.UnknownValueError:
            return None
        except Exception as exc:  # noqa: BLE001 - whisper/import/runtime issues
            raise VoiceInputError(
                "Whisper transcription failed. Install it with "
                "`pip install openai-whisper` (plus ffmpeg), or set STT_BACKEND=google.\n"
                f"Details: {exc}"
            ) from exc
    else:
        try:
            text = recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as exc:
            raise VoiceInputError(
                f"Google speech recognition is unreachable: {exc}\n"
                "Check your internet connection or set STT_BACKEND=whisper."
            ) from exc

    text = (text or "").strip()
    return text or None


# Formats speech_recognition's AudioFile reads directly; others go through ffmpeg.
_NATIVE_AUDIO_FORMATS = (".wav", ".aiff", ".aif", ".aifc", ".flac")


def _convert_to_wav(path: str) -> str:
    """Convert any ffmpeg-readable audio file to a temp 16 kHz mono WAV; return its path."""
    import shutil
    import subprocess
    import tempfile

    if shutil.which("ffmpeg") is None:
        raise VoiceInputError(
            f"The audio file {os.path.basename(path)!r} needs converting, but ffmpeg "
            "was not found. Install it with `brew install ffmpeg`."
        )
    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-ar", "16000", "-ac", "1", out_path],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        if os.path.exists(out_path):
            os.remove(out_path)
        detail = exc.stderr.decode("utf-8", "ignore")[-400:] if exc.stderr else ""
        raise VoiceInputError(f"ffmpeg could not convert {path!r}: {detail}") from exc
    return out_path


def transcribe_file(path: str, cfg: Config) -> Optional[str]:
    """Transcribe an audio file using the configured STT backend.

    WAV/AIFF/FLAC are read directly; other formats (m4a, caf, mp3 — e.g. iMessage voice
    memos) are converted to WAV with ffmpeg first. Returns None if unintelligible.
    """
    sr = _import_sr()
    recognizer = sr.Recognizer()

    tmp_wav: Optional[str] = None
    try:
        src_path = path
        if os.path.splitext(path)[1].lower() not in _NATIVE_AUDIO_FORMATS:
            tmp_wav = _convert_to_wav(path)
            src_path = tmp_wav
        try:
            with sr.AudioFile(src_path) as source:
                audio = recognizer.record(source)
        except VoiceInputError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VoiceInputError(f"Could not read audio file {path!r}: {exc}") from exc
        return _recognize_audio(recognizer, sr, cfg, audio)
    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            try:
                os.remove(tmp_wav)
            except OSError:
                pass
