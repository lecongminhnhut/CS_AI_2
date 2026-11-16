"""Local HTTP transport and session routing for the Griductive GUI."""

from __future__ import annotations

from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4
import json
import mimetypes

from .team_session import TeamSession


WEB = Path(__file__).resolve().with_name("web")
POST_FIELDS = {"/api/load": {"puzzle_id"}, "/api/restart": set(), "/api/hint": set(),
               "/api/verdict": {"cell_id", "status"}, "/api/step": set()}


class GriductiveServer(ThreadingHTTPServer):
    """Host a case catalog with independent game sessions for each browser."""

    def __init__(self, address: tuple[str, int], cases: dict[str, dict[str, Any]]) -> None:
        """Bind the local address and keep the validated team puzzle catalog."""
        self.cases = cases
        self.sessions: dict[str, GameSession] = {}
        self.sessions_lock = Lock()
        super().__init__(address, Request)

    def session(self, key: str | None) -> tuple[str, GameSession]:
        """Retrieve the browser's session or create one for a new cookie."""
        with self.sessions_lock:
            if key not in self.sessions:
                key = uuid4().hex
                if len(self.sessions) >= 128:
                    self.sessions.pop(next(iter(self.sessions)))
                self.sessions[key] = GameSession(next(iter(self.cases.values())))
            return key, self.sessions[key]


class GameSession:
    """Wrap a browser session with a request lock and a replaceable case."""

    def __init__(self, case: dict[str, Any]) -> None:
        """Construct the first game and create the lock used by HTTP requests."""
        self.game = TeamSession(case)
        self.lock = Lock()

    def dispatch(self, path: str, data: dict[str, str],
                 cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Handle one validated game request under the session lock."""
        if path == "/api/load":
            case = cases.get(data["puzzle_id"])
            if case is None:
                raise ValueError("Choose a case from the list")
            self.game = TeamSession(case)
            result = "LOADED"
        elif path == "/api/restart":
            self.game.restart()
            result = "RESTARTED"
        elif path == "/api/hint":
            return {**self.game.hint(), "state": self.game.snapshot()}
        elif path == "/api/verdict":
            result = self.game.submit(data["cell_id"], data["status"])
        elif path == "/api/step":
            result = self.game.step()
        else:
            result = "READY"
        return {"result": result, "state": self.game.snapshot()}


class Request(BaseHTTPRequestHandler):
    """Serve GUI assets and validated JSON requests for the current browser."""

    def reply(self, status: int, content: bytes, content_type: str, cookie: str | None = None) -> None:
        """Send a response with optional session cookie and no client-side caching."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", f"griductive={cookie}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(content)

    def json_reply(self, status: int, value: dict[str, Any], cookie: str | None = None) -> None:
        """Serialize a response as standard JSON."""
        self.reply(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8", cookie)

    def do_GET(self) -> None:
        """Serve the public catalog, session state, trace, or a GUI asset."""
        path = urlsplit(self.path).path
        if path == "/api/puzzles":
            puzzles = [{key: case[key] for key in ("id", "title", "size")}
                       for case in self.server.cases.values()]
            self.json_reply(200, {"puzzles": puzzles})
        elif path in ("/api/state", "/api/trace"):
            self.game_request(path, {})
        else:
            self.serve_asset(path)

    def serve_asset(self, path: str) -> None:
        """Serve a file only if it resolves within the browser's asset directory."""
        if path == "/":
            path = "/index.html"
        asset = (WEB / path.lstrip("/")).resolve()
        if not asset.is_relative_to(WEB) or not asset.is_file():
            self.send_error(404)
            return
        kind = mimetypes.guess_type(asset)[0] or "application/octet-stream"
        if asset.suffix == ".js":
            kind = "text/javascript"
        self.reply(200, asset.read_bytes(), kind)

    def do_POST(self) -> None:
        """Validate the body and forward an allowed game operation."""
        path = urlsplit(self.path).path
        if path not in POST_FIELDS:
            self.send_error(404)
            return
        try:
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Expected JSON")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or any(not isinstance(v, str) for v in data.values()):
                raise ValueError("Expected JSON object with string fields")
            if data.keys() != POST_FIELDS[path]:
                raise ValueError(f"Expected fields: {', '.join(sorted(POST_FIELDS[path])) or '(none)'}")
        except ValueError as exc:
            self.json_reply(400, {"error": str(exc)})
            return
        self.game_request(path, data)

    def game_request(self, path: str, data: dict[str, str]) -> None:
        """Serialize game operations per browser and translate request errors into HTTP errors."""
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            key = cookies["griductive"].value if "griductive" in cookies else None
        except CookieError:
            key = None
        key, session = self.server.session(key)
        try:
            with session.lock:
                if path == "/api/trace":
                    content = "".join(json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n"
                                      for entry in session.game.trace_entries)
                    self.reply(200, content.encode("utf-8"), "application/x-ndjson; charset=utf-8", key)
                    return
                response = session.dispatch(path, data, self.server.cases)
            self.json_reply(200, response, key)
        except ValueError as exc:
            self.json_reply(400, {"error": str(exc)}, key)
        except RuntimeError as exc:
            self.log_error("%s", exc)
            self.json_reply(500, {"error": "The game could not complete the operation."}, key)
