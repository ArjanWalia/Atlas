"""A small, dependency-free web UI for Atlas.

Serves a premium single-page front end and exposes the Atlas pipeline over HTTP:

    GET  /                -> the app shell (static files in `web_static/`)
    GET  /api/health      -> config + capability report (JSON)
    POST /api/command     -> run format -> Cursor -> summarize for one command (JSON)
    POST /api/tts         -> ElevenLabs speech for a piece of text (audio/mpeg)

Built on the standard-library `http.server`, so it adds no dependencies and runs
from the same virtualenv as the rest of Atlas. Bind to localhost only.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from . import speech
from .app import run_pipeline
from .config import Config
from .cursor_agent import cursor_available

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_static")
_MAX_BODY = 256 * 1024  # plenty for a typed command; rejects runaway uploads


class _Handler(BaseHTTPRequestHandler):
    server_version = "Atlas"
    # Injected by the server factory below.
    cfg: Config = None  # type: ignore[assignment]

    # --- helpers -----------------------------------------------------------

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Optional[dict]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > _MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        # Prevent path traversal: resolve and confirm it stays in the static dir.
        full = os.path.normpath(os.path.join(_STATIC_DIR, rel))
        if not full.startswith(_STATIC_DIR) or not os.path.isfile(full):
            self.send_error(404, "Not found")
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # --- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self._send_json(self._health())
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path == "/api/command":
            self._handle_command()
        elif path == "/api/tts":
            self._handle_tts()
        else:
            self.send_error(404, "Not found")

    def _health(self) -> dict:
        cfg = self.cfg
        return {
            "version": __import__("atlas").__version__,
            "anthropic": bool(cfg.anthropic_api_key),
            "cursor": cursor_available(cfg),
            "tts_backend": cfg.tts_backend,
            "elevenlabs": speech.elevenlabs_available(cfg),
            "model": cfg.model,
            "workdir": cfg.workdir,
        }

    def _handle_command(self) -> None:
        data = self._read_json()
        if not data or not isinstance(data.get("text"), str):
            self._send_json({"error": "Expected JSON: {\"text\": \"...\"}"}, 400)
            return
        text = data["text"].strip()
        if not text:
            self._send_json({"error": "Command was empty."}, 400)
            return
        if not self.cfg.anthropic_api_key:
            self._send_json({"error": "ANTHROPIC_API_KEY is not set."}, 503)
            return
        try:
            result = run_pipeline(text, self.cfg)
        except Exception as exc:  # noqa: BLE001 - report, never crash the server
            self._send_json({"error": f"Pipeline failed: {exc}"}, 500)
            return
        self._send_json(result)

    def _handle_tts(self) -> None:
        data = self._read_json()
        if not data or not isinstance(data.get("text"), str):
            self._send_json({"error": "Expected JSON: {\"text\": \"...\"}"}, 400)
            return
        text = speech.clean_for_speech(data["text"])
        if not text:
            self._send_json({"error": "Nothing to speak."}, 400)
            return
        try:
            audio = speech.synthesize_elevenlabs(text, self.cfg)
        except RuntimeError as exc:
            self._send_json({"error": str(exc)}, 503)
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def log_message(self, fmt: str, *args) -> None:  # quieter, prefixed logs
        print(f"[atlas-web] {self.address_string()} {fmt % args}")


def serve(cfg: Config, host: str = "127.0.0.1", port: int = 8000) -> int:
    """Start the Atlas web server (blocking). Returns a process exit code."""
    handler = type("BoundHandler", (_Handler,), {"cfg": cfg})
    httpd = ThreadingHTTPServer((host, port), handler)

    url = f"http://{host}:{port}"
    print(f"Atlas web UI running at {url}")
    print("Press Ctrl+C to stop.")

    # Best-effort: open the browser once the server is up (no hard dependency).
    def _open() -> None:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    threading.Timer(0.5, _open).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Atlas web UI.")
    finally:
        httpd.server_close()
    return 0
