"""The summary agent: turns Cursor's text output into a short spoken reply.

Runs on Claude Opus 4.8. The result is read aloud by macOS `say`, so it must be
plain, natural, spoken-style English — no markdown, no code, no long paths.
"""

from __future__ import annotations

import anthropic

from .config import Config

# Cursor output is usually short, but cap it so a runaway log doesn't blow up cost.
_MAX_OUTPUT_CHARS = 24_000

_SYSTEM = """You are the voice-output layer for "Atlas", a voice-controlled coding \
assistant. The Cursor IDE agent has just acted on the user's request and produced \
the text shown to you. Convert it into a short, natural spoken summary that a \
text-to-speech voice will read aloud.

Rules:
- Speak in the first person as the assistant ("I added...", "I found...", "I ran...").
- Be concise: 1-4 sentences. The user is listening, not reading.
- Lead with the outcome — what happened, what changed, or what you found.
- Mention key files changed, commands run, or the core of an explanation.
- Do NOT read code, diffs, long file paths, or markdown aloud — describe them in words.
- Plain spoken sentences only: no markdown, no bullet symbols, no emoji.
- If Cursor asked a question or got blocked, say so clearly and briefly.
- Respond with ONLY the spoken summary — no preamble, no quotes, nothing else."""


def _truncate(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    head = _MAX_OUTPUT_CHARS // 4
    tail = _MAX_OUTPUT_CHARS - head
    return text[:head] + "\n...[output truncated]...\n" + text[-tail:]


def summarize_for_speech(cursor_output: str, refined_prompt: str, cfg: Config) -> str:
    """Produce a spoken-style summary of Cursor's output."""
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    user = (
        f"The user asked Cursor to:\n{refined_prompt}\n\n"
        f"Cursor's full text output was:\n\n{_truncate(cursor_output)}\n\n"
        "Now give the short spoken summary."
    )
    resp = client.messages.create(
        model=cfg.model,
        max_tokens=cfg.summary_max_tokens,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    return "Cursor finished, but I couldn't read its response."
