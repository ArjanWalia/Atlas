"""The formatting agent: turns a raw voice transcription into a clean Cursor prompt.

Runs on Claude Opus 4.8. Returns a detected `intent` (so Atlas can decide whether
Cursor may make edits / run commands), a polished `refined_prompt`, and an optional
`target_workdir` when the user wants to switch to / build in another project. Recent
history (from Convex) is passed in as context so references like "my last build" or
"the other project" resolve.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional

import anthropic

from .config import Config


@dataclass
class Formatted:
    """Result of the formatting agent."""

    intent: str
    refined_prompt: str
    target_workdir: Optional[str] = None


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

Context handling:
- You may be given "Context from earlier sessions" with recent runs and known
  directories. Use it to resolve references such as "my last build", "the same
  project", or "the other repo" — fold the resolved meaning into refined_prompt.
- target_workdir: if the user asks to work in, switch to, open, or build in a specific
  project or directory, set target_workdir to that path (e.g. "~/projects/foo"). If
  they reference a previous project, use that project's directory from the context.
  Otherwise set target_workdir to an empty string.

Classify the request into exactly one intent, choose target_workdir, and produce the
refined prompt."""

# JSON Schema for structured output (preferred path).
_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["plan", "explain", "edit", "terminal", "navigate", "other"],
        },
        "refined_prompt": {"type": "string"},
        "target_workdir": {
            "type": "string",
            "description": "Directory/project to switch to if the user asks; otherwise an empty string.",
        },
    },
    "required": ["intent", "refined_prompt", "target_workdir"],
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


def _parse(text: str, fallback_prompt: str) -> Formatted:
    """Parse the model output into a Formatted result, tolerating code fences."""
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
            target = (data.get("target_workdir") or "").strip() or None
            if refined:
                return Formatted(intent, refined, target)
        except json.JSONDecodeError:
            pass

    # Could not parse structured output — fall back to the raw transcript.
    return Formatted("other", fallback_prompt, None)


def _context_block(
    history: Optional[List[dict]],
    active_workdir: Optional[str],
    known_dirs: Optional[List[str]],
) -> str:
    lines: List[str] = []
    if active_workdir:
        lines.append(f"Active project directory: {active_workdir}")
    if known_dirs:
        lines.append("Known directories: " + ", ".join(known_dirs))
    if history:
        lines.append("Recent runs (most recent first):")
        for h in history[:8]:
            intent = h.get("intent", "?")
            wd = h.get("workdir", "?")
            prompt = (h.get("refinedPrompt") or "").replace("\n", " ")[:160]
            lines.append(f"  - [{intent}] dir={wd} :: {prompt}")
    return "\n".join(lines)


def format_command(
    transcript: str,
    cfg: Config,
    *,
    history: Optional[List[dict]] = None,
    active_workdir: Optional[str] = None,
    known_dirs: Optional[List[str]] = None,
) -> Formatted:
    """Return a Formatted result (intent, refined_prompt, target_workdir)."""
    client = _client(cfg)

    context = _context_block(history, active_workdir, known_dirs)
    user = f"Raw voice transcription:\n\n{transcript}"
    if context:
        user = (
            "Context from earlier sessions (resolve references like 'my last build' or "
            "'the other project', and use it to choose target_workdir):\n"
            f"{context}\n\n{user}"
        )

    base = dict(
        model=cfg.model,
        max_tokens=cfg.format_max_tokens,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
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
            + "\n\nRespond with ONLY a JSON object of the form "
            + '{"intent": "<one of plan|explain|edit|terminal|navigate|other>", '
            + '"refined_prompt": "<the cleaned-up instruction>", '
            + '"target_workdir": "<dir to switch to, or empty string>"}.'
        )
        resp = client.messages.create(**fallback)
        return _parse(_first_text(resp), transcript)
