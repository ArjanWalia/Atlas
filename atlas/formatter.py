"""The formatting agent: turns a raw voice transcription into a clean Cursor prompt.

Runs on Claude Opus 4.8. Returns a detected `intent` (so Atlas can decide whether
Cursor is allowed to make edits / run commands) and a polished `refined_prompt`
that reads as if a thoughtful engineer had typed it.
"""

from __future__ import annotations

import json
import re
from typing import Tuple

import anthropic

from .config import Config

_SYSTEM = """You are the prompt-formatting layer for "Atlas", a voice-controlled \
coding assistant that drives the Cursor IDE agent.

The user speaks naturally; their speech has been transcribed and may contain filler \
words, false starts, mishearings, or run-on phrasing. Turn that raw transcription \
into a single, clean, high-quality instruction the Cursor agent can act on directly \
— as if a thoughtful engineer had typed it.

Rules:
- Preserve the user's actual intent. Never invent requirements they did not ask for.
- Remove filler ("um", "uh", "like", "you know") and fix obvious transcription errors
  (e.g. "pie thon" -> "Python", "depf" -> "def").
- Make it self-contained and unambiguous — Cursor cannot ask follow-up questions.
- Choose framing based on intent:
    * plan      -> ask Cursor to produce a plan / design and NOT make edits yet.
    * explain   -> ask Cursor to explain the topic, code, or error clearly and briefly.
    * edit      -> state exactly what to change and where (file/function) if known.
    * terminal  -> tell Cursor to run the command; describe it precisely.
    * navigate  -> tell Cursor which file or symbol to open / focus.
    * other     -> anything that doesn't fit the above.
- Keep it concise: one short paragraph or a short list. No greeting or preamble.
- Write in the imperative, the way an engineer phrases a request to a coding agent.

Classify the request into exactly one intent and produce the refined prompt."""

# JSON Schema for structured output (preferred path).
_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["plan", "explain", "edit", "terminal", "navigate", "other"],
        },
        "refined_prompt": {"type": "string"},
    },
    "required": ["intent", "refined_prompt"],
    "additionalProperties": False,
}

_VALID_INTENTS = {"plan", "explain", "edit", "terminal", "navigate", "other"}
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _client(cfg: Config) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=cfg.anthropic_api_key)


def _first_text(resp) -> str:
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


def _parse(text: str, fallback_prompt: str) -> Tuple[str, str]:
    """Parse the model output into (intent, refined_prompt), tolerating fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = re.sub(r"^\s*json\s*", "", text, flags=re.IGNORECASE).strip()

    match = _JSON_RE.search(text)
    if match:
        try:
            data = json.loads(match.group(0))
            intent = str(data.get("intent", "other")).lower().strip()
            if intent not in _VALID_INTENTS:
                intent = "other"
            refined = (data.get("refined_prompt") or "").strip()
            if refined:
                return intent, refined
        except json.JSONDecodeError:
            pass

    # Could not parse structured output — fall back to the raw transcript.
    return "other", fallback_prompt


def format_command(transcript: str, cfg: Config) -> Tuple[str, str]:
    """Return (intent, refined_prompt) for a raw voice transcription."""
    client = _client(cfg)
    base = dict(
        model=cfg.model,
        max_tokens=cfg.format_max_tokens,
        system=_SYSTEM,
        messages=[
            {"role": "user", "content": f"Raw voice transcription:\n\n{transcript}"}
        ],
    )
    if cfg.format_thinking:
        base["thinking"] = {"type": "adaptive"}

    # Preferred path: structured outputs guarantee schema-valid JSON.
    try:
        output_config = {"format": {"type": "json_schema", "schema": _SCHEMA}}
        if cfg.format_thinking:
            output_config["effort"] = cfg.effort
        resp = client.messages.create(output_config=output_config, **base)
        return _parse(_first_text(resp), transcript)
    except (TypeError, AttributeError, anthropic.BadRequestError):
        # Older SDK or unsupported parameter — ask for JSON in the prompt instead.
        fallback = dict(base)
        fallback["system"] = (
            _SYSTEM
            + '\n\nRespond with ONLY a JSON object of the form '
            + '{"intent": "<one of plan|explain|edit|terminal|navigate|other>", '
            + '"refined_prompt": "<the cleaned-up instruction>"}.'
        )
        resp = client.messages.create(**fallback)
        return _parse(_first_text(resp), transcript)
