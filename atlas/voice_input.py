"""Microphone capture + speech-to-text.

Uses the `SpeechRecognition` library for mic capture and voice-activity detection.
Transcription backend is selectable:
  * "google"  — Google Web Speech API (no setup, needs internet)
  * "whisper" — local OpenAI Whisper (offline & private; needs `openai-whisper`)
"""

from __future__ import annotations

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
        sr = self.sr
        if self.cfg.stt_backend == "whisper":
            try:
                text = self.recognizer.recognize_whisper(
                    audio, model=self.cfg.whisper_model
                )
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
                text = self.recognizer.recognize_google(audio)
            except sr.UnknownValueError:
                return None
            except sr.RequestError as exc:
                raise VoiceInputError(
                    f"Google speech recognition is unreachable: {exc}\n"
                    "Check your internet connection or set STT_BACKEND=whisper."
                ) from exc

        text = (text or "").strip()
        return text or None
