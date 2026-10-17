"""Watchtower private staging dashboard. Monitoring only; no tool execution.
Local start: python watchtower_web.py (prints a temporary dashboard access token).
Hosted start requires WATCHTOWER_API_TOKEN and reviewed HTTPS/access configuration.
No model calls occur unless an authenticated request explicitly sets analyze=true.
"""
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_DEFAULT = Path.home() / ".local/state/watchtower/dashboard.sqlite3"


def parse_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Non-finite number")
        return result
    def constant(value):
        raise ValueError("Non-finite value")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def provider(event):
    from backend import assess
    return assess(event)


class Dashboard:
    def __init__(self, token, db=DB_DEFAULT, analyst=None, html=None, daily_limit=20):
        if not isinstance(token, str) or len(token) < 32 or not token.isascii():
            raise ValueError("Use a strong ASCII API token of at least 32 characters")
        if type(daily_limit) is not int or not 0 <= daily_limit <= 100:
            raise ValueError("Daily analysis-request limit must be 0-100")
        self.token, self.db, self.analyst = token, Path(db), analyst or provider
        self.html = (HERE / "web/index.html").read_bytes() if html is None else html
        self.daily_limit = daily_limit
        self.db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS dashboard_events (id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, created TEXT NOT NULL, requested INTEGER NOT NULL, record TEXT NOT NULL)")
        self.db.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.db, timeout=5)

    def submit(self, value, key):
        if not isinstance(value, dict) or set(value) != {"tool", "arguments", "source", "analyze"}:
            raise ValueError("Expected tool, arguments, source and analyze")
        tool = value["tool"]
        if not isinstance(tool, str) or not 1 <= len(tool) <= 100 or not tool.isascii() or not all(c.isalnum() or c in "._-" for c in tool):
            raise ValueError("Invalid tool")
        if not isinstance(value["arguments"], dict) or type(value["analyze"]) is not bool:
            raise ValueError("Invalid arguments or analyze flag")
        if value["source"] not in ("synthetic", "user_submitted"):
            raise ValueError("Invalid source label")
        if not isinstance(key, str) or not 8 <= len(key) <= 100 or not key.isascii() or not all(c.isalnum() or c in "-_" for c in key):
            raise ValueError("Invalid Idempotency-Key")
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        record = {"id": str(uuid.uuid4()), "created_at": now, "tool": tool,
                  "arguments": value["arguments"], "source_label": value["source"],
                  "source_verified": False, "executed": False,
                  "analysis": {"status": "pending" if value["analyze"] else "not_requested", "assessment": None}}
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT digest,record FROM dashboard_events WHERE key=?", (key,)).fetchone()
            if previous:
                if previous[0] != digest:
                    return 409, {"error": "idempotency_conflict"}
                return 200, json.loads(previous[1])
            if connection.execute("SELECT count(*) FROM dashboard_events").fetchone()[0] >= 5000:
                return 507, {"error": "development_storage_limit_reached"}
            today = now[:10]
            requested = connection.execute("SELECT count(*) FROM dashboard_events WHERE requested=1 AND substr(created,1,10)=?", (today,)).fetchone()[0]
            if value["analyze"] and requested >= self.daily_limit:
                return 429, {"error": "daily_analysis_request_limit_reached"}
            connection.execute("INSERT INTO dashboard_events VALUES (?,?,?,?,?,?)", (
                record["id"], key, digest, now, int(value["analyze"]), json.dumps(record)))
        if value["analyze"]:
            try:
                result = self.analyst({"tool": tool, "arguments": value["arguments"]})
                if not isinstance(result, dict) or result.get("status") not in ("completed", "not_configured", "unavailable"):
                    raise ValueError("Invalid analyst result")
                if result["status"] == "completed":
                    assessment = result.get("assessment")
                    if not isinstance(assessment, dict) or assessment.get("risk") not in ("suspicious", "unclear", "no_obvious_risk") or not isinstance(assessment.get("explanation"), str) or not 1 <= len(assessment["explanation"]) <= 2000:
                        raise ValueError("Invalid assessment")
                json.dumps(result, allow_nan=False)
                record["analysis"] = result
            except Exception:
                record["analysis"] = {"status": "unavailable", "assessment": None}
            with self.connect() as connection:
                connection.execute("UPDATE dashboard_events SET record=? WHERE id=?", (json.dumps(record), record["id"]))
        return 201, record

    def handle(self, env):
        path, method = env.get("PATH_INFO", ""), env.get("REQUEST_METHOD", "GET")
        if path == "/" and method == "GET":
            return 200, self.html, "text/html; charset=utf-8"
        if path == "/healthz" and method == "GET":
            return 200, {"service": "watchtower", "mode": "monitor_only"}, "application/json"
        if not hmac.compare_digest(env.get("HTTP_AUTHORIZATION", "").encode(), ("Bearer " + self.token).encode()):
            return 401, {"error": "unauthorized"}, "application/json"
        if path == "/api/events" and method == "GET":
            with self.connect() as connection:
                rows = connection.execute("SELECT record FROM dashboard_events ORDER BY created DESC,id DESC LIMIT 50").fetchall()
                total = connection.execute("SELECT count(*) FROM dashboard_events").fetchone()[0]
            return 200, {"events": [json.loads(row[0]) for row in rows], "total": total,
                         "mode": "monitor_only", "ai_configured": bool(os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_MODEL")),
                         "image_analysis_integrated": False, "decoys_deployed": False}, "application/json"
        if path != "/api/events" or method != "POST":
            return 404, {"error": "not_found"}, "application/json"
        if env.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json" or env.get("HTTP_TRANSFER_ENCODING"):
            raise ValueError("JSON with Content-Length required")
        length = int(env.get("CONTENT_LENGTH", ""))
        if not 1 <= length <= 16384:
            return 413, {"error": "invalid_body_size"}, "application/json"
        raw = env["wsgi.input"].read(length)
        if len(raw) != length:
            raise ValueError("Incomplete body")
        status, record = self.submit(parse_json(raw), env.get("HTTP_IDEMPOTENCY_KEY", ""))
        return status, record, "application/json"

    def __call__(self, environ, start_response):
        try:
            status, result, content_type = self.handle(environ)
        except (ValueError, TypeError, KeyError, RecursionError):
            status, result, content_type = 400, {"error": "invalid_request"}, "application/json"
        except (OSError, sqlite3.Error):
            status, result, content_type = 503, {"error": "storage_unavailable; submission_may_have_been_recorded"}, "application/json"
        body = result if isinstance(result, bytes) else json.dumps(result, allow_nan=False).encode()
        start_response(f"{status} {HTTPStatus(status).phrase}", [
            ("Content-Type", content_type), ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")])
        return [body]


def create_app():
    return Dashboard(os.environ.get("WATCHTOWER_API_TOKEN", ""),
                     os.environ.get("WATCHTOWER_DASHBOARD_DB", str(DB_DEFAULT)),
                     daily_limit=int(os.environ.get("WATCHTOWER_DAILY_ANALYSIS_LIMIT", "20")))


if __name__ == "__main__":
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    class Quiet(WSGIRequestHandler):
        def log_message(self, *args):
            pass
    if not os.environ.get("WATCHTOWER_API_TOKEN"):
        os.environ["WATCHTOWER_API_TOKEN"] = secrets.token_urlsafe(32)
    app = create_app()
    print("Open http://127.0.0.1:8000. Local dashboard token:")
    print(os.environ["WATCHTOWER_API_TOKEN"])
    print("Monitor only. No autonomous collection or tool execution. Never expose this development server publicly.")
    with make_server("127.0.0.1", 8000, app, handler_class=Quiet) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
