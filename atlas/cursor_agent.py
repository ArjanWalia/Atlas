"""Drive the Cursor IDE agent through its headless CLI (`cursor-agent`).

This is the "Voice Cursor" backend: it receives a clean, Claude-formatted prompt
and runs Cursor non-interactively, returning Cursor's final text output.

Reference: Cursor headless CLI — `cursor-agent -p "<prompt>" --output-format text
--no-stream [--model <id>] [--force]`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Optional

from .config import Config


class CursorError(RuntimeError):
    """Raised when the Cursor CLI is missing, times out, or exits non-zero."""


# The Cursor CLI installs as `cursor-agent`; some installs also expose `agent`.
_FALLBACK_NAMES = ("cursor-agent", "agent")
# Common install locations that may not be on PATH yet (esp. fresh installs).
_EXTRA_DIRS = ("~/.local/bin", "~/.cursor/bin")


def _candidate_names(cfg: Config) -> List[str]:
    names: List[str] = []
    if cfg.cursor_command:
        names.append(cfg.cursor_command)
    for name in _FALLBACK_NAMES:
        if name not in names:
            names.append(name)
    return names


def resolve_cursor_command(cfg: Config) -> Optional[str]:
    """Return an absolute path to the Cursor CLI, or None if not found.

    Tries the configured command first, then the well-known names (`cursor-agent`,
    `agent`), searching the PATH *and* common install dirs (`~/.local/bin`,
    `~/.cursor/bin`) — so Atlas still works right after a fresh install, before the
    user has added `~/.local/bin` to their PATH.
    """
    # Honor an explicit path in ATLAS_CURSOR_COMMAND (e.g. /opt/bin/cursor-agent).
    configured = cfg.cursor_command
    if configured and ("/" in configured or os.sep in configured):
        expanded = os.path.expanduser(configured)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded

    names = _candidate_names(cfg)

    # 1) Anything already on PATH.
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    # 2) Common install dirs that may not be exported on PATH.
    for directory in (os.path.expanduser(d) for d in _EXTRA_DIRS):
        for name in names:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

    return None


def cursor_available(cfg: Config) -> bool:
    """True if the Cursor CLI can be located (PATH or common install dirs)."""
    return resolve_cursor_command(cfg) is not None


def build_command(executable: str, prompt: str, cfg: Config, *, force: bool) -> List[str]:
    """Assemble the Cursor CLI argument list for a single prompt."""
    cmd = [executable, "-p", prompt,
           "--output-format", cfg.cursor_output_format]
    if cfg.cursor_no_stream:
        cmd.append("--no-stream")
    if cfg.cursor_model:
        cmd += ["--model", cfg.cursor_model]
    if force:
        # Lets Cursor make edits / run terminal commands without prompting.
        cmd.append("--force")
    return cmd


def run_cursor(prompt: str, cfg: Config, *, force: bool) -> str:
    """Run Cursor headlessly and return its final text output.

    `force` should be True for edit/terminal requests (so Cursor may act without
    confirmation) and False for plan/explain/navigation requests.
    """
    executable = resolve_cursor_command(cfg)
    if executable is None:
        raise CursorError(
            f"The Cursor CLI ('{cfg.cursor_command}') could not be found.\n"
            "Install it from https://cursor.com/cli, then add it to your PATH:\n"
            "    echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.zshrc && source ~/.zshrc\n"
            "Authenticate once with `cursor-agent login` (or set CURSOR_API_KEY). "
            "If your binary is named `agent`, set ATLAS_CURSOR_COMMAND=agent."
        )

    env = os.environ.copy()
    if cfg.cursor_api_key:
        env["CURSOR_API_KEY"] = cfg.cursor_api_key

    cmd = build_command(executable, prompt, cfg, force=force)

    try:
        proc = subprocess.run(
            cmd,
            cwd=cfg.workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=cfg.cursor_timeout,
        )
    except subprocess.TimeoutExpired:
        raise CursorError(
            f"Cursor did not finish within {cfg.cursor_timeout}s "
            "(raise ATLAS_CURSOR_TIMEOUT for longer tasks)."
        )
    except FileNotFoundError as exc:  # race: removed after resolution
        raise CursorError(f"Could not start '{executable}': {exc}") from exc

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if proc.returncode != 0:
        detail = err or out or f"exit code {proc.returncode}"
        raise CursorError(f"Cursor agent failed: {detail}")

    return out or err or "(Cursor produced no output.)"
