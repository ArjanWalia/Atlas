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
from typing import List

from .config import Config


class CursorError(RuntimeError):
    """Raised when the Cursor CLI is missing, times out, or exits non-zero."""


def cursor_available(cfg: Config) -> bool:
    """True if the configured Cursor CLI command is on PATH."""
    return shutil.which(cfg.cursor_command) is not None


def build_command(prompt: str, cfg: Config, *, force: bool) -> List[str]:
    """Assemble the `cursor-agent` argument list for a single prompt."""
    cmd = [cfg.cursor_command, "-p", prompt,
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
    if not cursor_available(cfg):
        raise CursorError(
            f"'{cfg.cursor_command}' was not found on your PATH.\n"
            "Install the Cursor CLI from https://cursor.com/cli and authenticate once "
            "with `cursor-agent login` (or set CURSOR_API_KEY)."
        )

    env = os.environ.copy()
    if cfg.cursor_api_key:
        env["CURSOR_API_KEY"] = cfg.cursor_api_key

    cmd = build_command(prompt, cfg, force=force)

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
    except FileNotFoundError as exc:  # race: removed from PATH after the check
        raise CursorError(f"Could not start '{cfg.cursor_command}': {exc}") from exc

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if proc.returncode != 0:
        detail = err or out or f"exit code {proc.returncode}"
        raise CursorError(f"Cursor agent failed: {detail}")

    return out or err or "(Cursor produced no output.)"
