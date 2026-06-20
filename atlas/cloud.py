"""Optional Convex backend: global run history + active-directory memory.

If ``CONVEX_URL`` is unset (or the ``convex`` package isn't installed) every method
here is a safe no-op, so the core Atlas loop keeps working unchanged. Convex problems
never crash a run — they print a warning and degrade to "history disabled".
"""

from __future__ import annotations

from typing import List, Optional

from .config import Config


class CloudStore:
    """Thin wrapper over the Convex Python client (history + directory memory)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._client = None
        self.error: Optional[str] = None

        if not cfg.convex_url:
            return
        try:
            from convex import ConvexClient  # type: ignore

            self._client = ConvexClient(cfg.convex_url)
            if cfg.convex_token:
                self._client.set_auth(cfg.convex_token)
        except Exception as exc:  # noqa: BLE001 - never let cloud setup crash Atlas
            self.error = (
                f"Convex history disabled ({exc}). "
                "Install it with `pip install convex` and set CONVEX_URL to enable."
            )
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    # --- history ------------------------------------------------------------

    def record_run(
        self,
        *,
        channel: str,
        transcript: str,
        refined_prompt: str,
        intent: str,
        cursor_output: str,
        summary: str,
        workdir: str,
        status: str,
    ) -> None:
        if not self._client:
            return
        try:
            self._client.mutation(
                "runs:record",
                {
                    "channel": channel,
                    "transcript": transcript,
                    "refinedPrompt": refined_prompt,
                    "intent": intent,
                    "cursorOutput": (cursor_output or "")[:20000],
                    "summary": summary,
                    "workdir": workdir,
                    "status": status,
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[atlas] ⚠ could not record run to Convex: {exc}")

    def recent_history(self, limit: int = 8) -> List[dict]:
        if not self._client:
            return []
        try:
            return self._client.query("runs:recent", {"limit": limit}) or []
        except Exception as exc:  # noqa: BLE001
            print(f"[atlas] ⚠ could not read Convex history: {exc}")
            return []

    # --- active-directory memory -------------------------------------------

    def get_config(self) -> Optional[dict]:
        if not self._client:
            return None
        try:
            return self._client.query("config:get", {})
        except Exception as exc:  # noqa: BLE001
            print(f"[atlas] ⚠ could not read Convex config: {exc}")
            return None

    def set_workdir(self, workdir: str) -> None:
        if not self._client:
            return
        try:
            self._client.mutation("config:setWorkdir", {"workdir": workdir})
        except Exception as exc:  # noqa: BLE001
            print(f"[atlas] ⚠ could not update active directory in Convex: {exc}")
