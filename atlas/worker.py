"""Background worker: run remote (iMessage) commands from the Convex queue.

Launch with ``python -m atlas --worker``. It subscribes to pending commands in Convex,
transcribes any attached voice memo, runs the normal Atlas pipeline (which speaks the
result aloud on this Mac), and writes the summary back so the Spectrum gateway can text
it to the user. This must run on the Mac, where transcription, Cursor, speech, and your
secrets live — Convex only brokers the work.
"""

from __future__ import annotations

import os
import tempfile
import urllib.request

from .app import process_command
from .cloud import CloudStore
from .config import Config
from .voice_input import transcribe_file


def _download(url: str, suffix: str = ".m4a") -> str:
    """Download a URL to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    urllib.request.urlretrieve(url, path)  # noqa: S310 - trusted Convex storage URL
    return path


def _resolve_transcript(client, cmd: dict, cfg: Config) -> str:
    """Turn a command into text: transcribe its voice memo, or use its typed text."""
    storage_id = cmd.get("audioStorageId")
    if storage_id:
        url = client.query("files:getUrl", {"storageId": storage_id})
        if not url:
            raise RuntimeError("the voice memo is no longer available in storage")
        audio_path = _download(url)
        try:
            text = transcribe_file(audio_path, cfg)
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        if not text:
            raise RuntimeError("I couldn't make out that voice memo")
        return text

    text = (cmd.get("text") or "").strip()
    if not text:
        raise RuntimeError("the message had no voice memo and no text")
    return text


def _handle(client, cloud: CloudStore, cmd: dict, cfg: Config) -> None:
    """Claim, run, and report one command. Never raises (one bad command != worker down)."""
    cmd_id = cmd["_id"]
    # Exactly-once: only the caller that wins the atomic claim runs the command.
    if not client.mutation("commands:claim", {"id": cmd_id}):
        return

    print(f"\n📥 Claimed {cmd.get('channel', 'remote')} command {cmd_id}")
    try:
        transcript = _resolve_transcript(client, cmd, cfg)
        result = process_command(
            transcript, cfg, speak=True, channel=cmd.get("channel", "imessage"), cloud=cloud
        )
        summary = result.summary or "Done."
        client.mutation(
            "commands:complete",
            {"id": cmd_id, "summary": summary, "status": result.status},
        )
    except Exception as exc:  # noqa: BLE001 - one bad command must not kill the worker
        msg = f"Atlas hit a problem: {exc}"
        print(f"❌ {msg}")
        try:
            client.mutation("commands:fail", {"id": cmd_id, "summary": msg})
        except Exception:  # noqa: BLE001
            pass
    finally:
        # Tidy up the stored voice memo so blobs don't accumulate.
        storage_id = cmd.get("audioStorageId")
        if storage_id:
            try:
                client.mutation("files:remove", {"storageId": storage_id})
            except Exception:  # noqa: BLE001
                pass


def run(cfg: Config) -> int:
    """Subscribe to the Convex command queue and process commands until interrupted."""
    if not cfg.convex_url:
        print(
            "❌ The worker needs Convex. Set CONVEX_URL in your .env "
            "(see backend/README.md)."
        )
        return 1
    try:
        from convex import ConvexClient  # type: ignore
    except ImportError:
        print("❌ The `convex` package is required for the worker: pip install convex")
        return 1

    client = ConvexClient(cfg.convex_url)
    if cfg.convex_token:
        client.set_auth(cfg.convex_token)
    cloud = CloudStore(cfg)

    print("🛰️  Atlas worker online — waiting for iMessage commands. Press Ctrl+C to stop.")
    try:
        # Convex's Python subscribe() is a blocking generator: it yields the current
        # pending list now and again on every change (e.g. after we claim one).
        for pending in client.subscribe("commands:pending", {}):
            for cmd in pending or []:
                _handle(client, cloud, cmd, cfg)
    except KeyboardInterrupt:
        print("\nWorker stopped.")
        return 0
