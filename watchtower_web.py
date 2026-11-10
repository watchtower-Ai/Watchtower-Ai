"""Watchtower private staging dashboard. Monitoring only; no tool execution.

Money-limit checks (0.28.0) decide whether a refund, discount, payout or
similar action is inside configured limits. The service still does not run
the action. An auto-allow means the limits fit, not that the action is safe.

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
from decimal import Decimal
from http import HTTPStatus
from pathlib import Path

from money_gate import (
    VERSION,
    MoneyPolicy,
    StrictnessError,
    apply_patch,
    clamp_to_ceiling,
    default_policy,
    evaluate,
    is_money_action,
    one_field,
    parse_amount,
    parse_currency,
    parse_identity,
    parse_limit,
    parse_message,
    parse_model,
    parse_source_hint,
    policy_from_mapping,
)

HERE = Path(__file__).resolve().parent
DB_DEFAULT = Path.home() / ".local/state/watchtower/dashboard.sqlite3"
EVENT_FIELDS = {"tool", "arguments", "source", "analyze"}
EVENT_OPTIONAL = {"amount", "currency", "customer_ref", "session_id", "run_id", "model", "source_hint"}
CHECK_FIELDS = {
    "agent", "tool", "action", "resource", "description", "amount", "currency",
    "customer_ref", "customerRef", "session_id", "sessionId", "run_id", "runId",
    "model", "source_hint", "sourceHint",
}
CHECK_TEXT = {"agent": 100, "action": 100, "resource": 200, "description": 2000}


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


def utc_day(moment):
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date().isoformat()


def policy_from_public(payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid stored policy")
    return MoneyPolicy(
        currency=parse_currency(payload.get("currency")) or "USD",
        per_action_auto_allow=parse_limit(payload["per_action_auto_allow"]),
        daily_customer_cap=parse_limit(payload["daily_customer_cap"]),
        daily_session_cap=parse_limit(payload["daily_session_cap"]),
        daily_overall_cap=parse_limit(payload["daily_overall_cap"]),
        run_cap=parse_limit(payload["run_cap"]),
        end_user_message=parse_message(payload["end_user_message"]),
    )


class Dashboard:
    def __init__(self, token, db=DB_DEFAULT, analyst=None, html=None, daily_limit=20, money_policy=None, clock=None):
        if not isinstance(token, str) or len(token) < 32 or not token.isascii():
            raise ValueError("Use a strong ASCII API token of at least 32 characters")
        if type(daily_limit) is not int or not 0 <= daily_limit <= 100:
            raise ValueError("Daily analysis-request limit must be 0-100")
        if money_policy is None:
            money_policy = default_policy()
        if not isinstance(money_policy, MoneyPolicy):
            raise ValueError("Invalid money policy")
        self.token, self.db, self.analyst = token, Path(db), analyst or provider
        self.html = (HERE / "web/index.html").read_bytes() if html is None else html
        self.daily_limit = daily_limit
        self.money_ceiling = money_policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS dashboard_events (id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, created TEXT NOT NULL, requested INTEGER NOT NULL, record TEXT NOT NULL)")
            connection.execute("""CREATE TABLE IF NOT EXISTS money_entries (
                idempotency_key TEXT PRIMARY KEY,
                day TEXT NOT NULL,
                currency TEXT NOT NULL,
                amount TEXT NOT NULL,
                customer_ref TEXT,
                session_id TEXT,
                run_id TEXT,
                decision TEXT NOT NULL)""")
            connection.execute("CREATE TABLE IF NOT EXISTS money_policy (id INTEGER PRIMARY KEY CHECK (id = 1), policy_json TEXT NOT NULL)")
        self.db.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.db, timeout=5)

    def _read_policy(self, connection):
        row = connection.execute("SELECT policy_json FROM money_policy WHERE id=1").fetchone()
        if not row:
            return self.money_ceiling
        return clamp_to_ceiling(self.money_ceiling, policy_from_public(json.loads(row[0])))

    def money_policy_view(self):
        with self.connect() as connection:
            current = self._read_policy(connection)
        return {
            "effective": current.public(),
            "ceiling": self.money_ceiling.public(),
            "stricter_only": True,
            "note": (
                "Settings can lower these limits and cannot raise them. "
                "proceed true means this amount fits the money limits. "
                "It does not mean the action is safe, and this service does not execute it."
            ),
        }

    def update_money_policy(self, patch):
        try:
            with self.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = self._read_policy(connection)
                updated = apply_patch(self.money_ceiling, current, patch)
                connection.execute(
                    "INSERT INTO money_policy (id, policy_json) VALUES (1, ?) "
                    "ON CONFLICT(id) DO UPDATE SET policy_json=excluded.policy_json",
                    (json.dumps(updated.public()),))
        except StrictnessError as error:
            return 409, {"error": "settings_would_loosen", "detail": str(error)}
        return 200, self.money_policy_view()

    def _sum(self, connection, day, currency, scope, identity):
        if scope == "overall":
            rows = connection.execute(
                "SELECT amount FROM money_entries WHERE day=? AND currency=? AND decision IN ('auto_allow', 'approved')",
                (day, currency)).fetchall()
        elif scope == "customer":
            rows = connection.execute(
                "SELECT amount FROM money_entries WHERE day=? AND currency=? AND decision IN ('auto_allow', 'approved') AND customer_ref=?",
                (day, currency, identity)).fetchall()
        elif scope == "session":
            rows = connection.execute(
                "SELECT amount FROM money_entries WHERE day=? AND currency=? AND decision IN ('auto_allow', 'approved') AND session_id=?",
                (day, currency, identity)).fetchall()
        elif scope == "run":
            rows = connection.execute(
                "SELECT amount FROM money_entries WHERE day=? AND currency=? AND decision IN ('auto_allow', 'approved') AND run_id=?",
                (day, currency, identity)).fetchall()
        else:
            raise ValueError("Invalid total")
        total = Decimal("0")
        for (raw,) in rows:
            total += Decimal(raw)
        return total

    def _money_inputs(self, value):
        arguments = value["arguments"]
        action = arguments.get("action") if isinstance(arguments.get("action"), str) else None
        if not is_money_action(value["tool"], action):
            return None
        if "amount" in value and "amount" in arguments:
            raise ValueError("Duplicate amount")
        raw_amount = value["amount"] if "amount" in value else arguments.get("amount")
        state, amount = parse_amount(raw_amount if ("amount" in value or "amount" in arguments) else None)
        if state == "invalid":
            raise ValueError("Invalid amount")
        if "currency" in value and "currency" in arguments:
            raise ValueError("Duplicate currency")
        raw_currency = value["currency"] if "currency" in value else arguments.get("currency") if "currency" in arguments else None
        currency = parse_currency(raw_currency) if raw_currency is not None else None
        customer = parse_identity(value["customer_ref"], "customer_ref") if "customer_ref" in value else None
        session = parse_identity(value["session_id"], "session_id") if "session_id" in value else None
        run = parse_identity(value["run_id"], "run_id") if "run_id" in value else None
        return {
            "action": action,
            "amount_state": state,
            "amount": amount,
            "currency": currency,
            "customer_ref": customer,
            "session_id": session,
            "run_id": run,
        }

    def _attach_analyst_model(self, record):
        decision = record.get("decision")
        analysis = record.get("analysis")
        if not isinstance(decision, dict) or not isinstance(analysis, dict):
            return
        model = analysis.get("model")
        if not isinstance(model, str):
            return
        model = model.strip()
        if not 1 <= len(model) <= 100 or any(ord(char) < 32 for char in model):
            return
        decision["analyst_model"] = model
        if not decision.get("model"):
            decision["model"] = model
            decision["model_source"] = "analyst"

    def submit(self, value, key, as_check=False):
        if not isinstance(value, dict) or not EVENT_FIELDS <= set(value) <= EVENT_FIELDS | EVENT_OPTIONAL:
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
        model = parse_model(value["model"]) if "model" in value else None
        hint = parse_source_hint(value["source_hint"]) if "source_hint" in value else None
        money = self._money_inputs(value)
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
        now = self.clock()
        if not isinstance(now, datetime):
            raise ValueError("Invalid clock")
        created = now.astimezone(timezone.utc).isoformat() if now.tzinfo else now.replace(tzinfo=timezone.utc).isoformat()
        day = utc_day(now)
        record = {"id": str(uuid.uuid4()), "created_at": created, "tool": tool,
                  "arguments": value["arguments"], "source_label": value["source"],
                  "source_verified": False, "executed": False, "version": VERSION,
                  "analysis": {"status": "pending" if value["analyze"] else "not_requested", "assessment": None}}
        if model:
            record["caller_model"] = model
        if hint:
            record["source_hint"] = hint
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT digest,record FROM dashboard_events WHERE key=?", (key,)).fetchone()
            if previous:
                if previous[0] != digest:
                    return 409, {"error": "idempotency_conflict"}
                return 200, json.loads(previous[1])
            if connection.execute("SELECT count(*) FROM dashboard_events").fetchone()[0] >= 5000:
                return 507, {"error": "development_storage_limit_reached"}
            today = day
            requested = connection.execute("SELECT count(*) FROM dashboard_events WHERE requested=1 AND substr(created,1,10)=?", (today,)).fetchone()[0]
            if value["analyze"] and requested >= self.daily_limit:
                return 429, {"error": "daily_analysis_request_limit_reached"}
            if money is not None:
                policy = self._read_policy(connection)
                ledger_currency = policy.currency
                totals = {
                    "customer": self._sum(connection, day, ledger_currency, "customer", money["customer_ref"]) if money["customer_ref"] else Decimal("0"),
                    "session": self._sum(connection, day, ledger_currency, "session", money["session_id"]) if money["session_id"] else Decimal("0"),
                    "run": self._sum(connection, day, ledger_currency, "run", money["run_id"]) if money["run_id"] else Decimal("0"),
                    "overall": self._sum(connection, day, ledger_currency, "overall", None),
                }
                decision = evaluate(policy, {
                    "tool": tool,
                    "action": money["action"],
                    "amount_state": money["amount_state"],
                    "amount": money["amount"],
                    "currency": money["currency"],
                    "customer_ref": money["customer_ref"],
                    "session_id": money["session_id"],
                    "run_id": money["run_id"],
                    "model": model,
                    "source_hint": hint,
                    "day": day,
                }, totals)
                record["decision"] = decision
                if decision["counted"]:
                    connection.execute(
                        "INSERT INTO money_entries (idempotency_key, day, currency, amount, customer_ref, session_id, run_id, decision) VALUES (?,?,?,?,?,?,?,?)",
                        (key, day, policy.currency, decision["amount"], money["customer_ref"], money["session_id"], money["run_id"], "auto_allow"))
            elif as_check:
                record["decision"] = {
                    "version": VERSION,
                    "decision": "not_applicable",
                    "proceed": False,
                    "status": "not_applicable",
                    "brake": None,
                    "brakes": [],
                    "reason": (
                        "This check only applies money limits for refunds, discounts, payouts, "
                        "store credit and price overrides. It does not approve other actions "
                        "and it does not execute anything."
                    ),
                    "user_message": None,
                    "counted": False,
                    "model": model,
                    "model_source": "caller" if model else None,
                    "source_hint": hint,
                    "limit_only": True,
                }
            connection.execute("INSERT INTO dashboard_events VALUES (?,?,?,?,?,?)", (
                record["id"], key, digest, created, int(value["analyze"]), json.dumps(record)))
        if value["analyze"]:
            try:
                analyst_arguments = dict(value["arguments"])
                for field in ("amount", "currency", "customer_ref", "session_id", "run_id"):
                    if field in value and field not in analyst_arguments:
                        analyst_arguments[field] = value[field]
                result = self.analyst({"tool": tool, "arguments": analyst_arguments})
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
            self._attach_analyst_model(record)
            with self.connect() as connection:
                connection.execute("UPDATE dashboard_events SET record=? WHERE id=?", (json.dumps(record), record["id"]))
        return 201, record

    def check_action(self, body, key):
        if not isinstance(body, dict) or not set(body) <= CHECK_FIELDS or "tool" not in body:
            raise ValueError("Invalid check")
        arguments = {}
        for name, limit in CHECK_TEXT.items():
            if name not in body or body[name] is None:
                continue
            text = body[name]
            if not isinstance(text, str) or not 1 <= len(text) <= limit or any(ord(char) < 32 for char in text):
                raise ValueError("Invalid " + name)
            arguments[name] = text
        value = {"tool": body["tool"], "arguments": arguments, "source": "user_submitted", "analyze": False}
        if "amount" in body:
            value["amount"] = body["amount"]
        currency = one_field(body, "currency")
        if currency is not None:
            value["currency"] = currency
        customer = one_field(body, "customer_ref", "customerRef")
        if customer is not None:
            value["customer_ref"] = customer
        session = one_field(body, "session_id", "sessionId")
        if session is not None:
            value["session_id"] = session
        run = one_field(body, "run_id", "runId")
        if run is not None:
            value["run_id"] = run
        model = one_field(body, "model")
        if model is not None:
            value["model"] = model
        hint = one_field(body, "source_hint", "sourceHint")
        if hint is not None:
            value["source_hint"] = hint
        return self.submit(value, key, as_check=True)

    def _scope_snapshot(self, identity, before, amount, cap, counted):
        if identity is None:
            return None
        projected = before + amount
        after = projected if counted else before
        return {
            "id": identity,
            "before": format(before, "f"),
            "projected": format(projected, "f"),
            "after": format(after, "f"),
            "cap": format(cap, "f"),
        }

    def resolve_check(self, check_id, body):
        """Record a person's yes or no. An approval is added to the same daily totals."""
        if not isinstance(body, dict) or set(body) - {"outcome", "amount"}:
            raise ValueError("Invalid resolution")
        outcome = body.get("outcome")
        if outcome not in ("approve", "deny"):
            raise ValueError("Invalid outcome")
        try:
            if str(uuid.UUID(check_id)) != check_id:
                return 404, {"error": "not_found"}
        except (ValueError, AttributeError):
            return 404, {"error": "not_found"}
        now = self.clock()
        if not isinstance(now, datetime):
            raise ValueError("Invalid clock")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT record FROM dashboard_events WHERE id=?", (check_id,)).fetchone()
            if not row:
                return 404, {"error": "not_found"}
            record = json.loads(row[0])
            decision = record.get("decision")
            if not isinstance(decision, dict) or decision.get("decision") in (None, "not_applicable"):
                return 409, {"error": "not_a_money_hold"}
            current = decision.get("decision")
            if current == "auto_allow":
                return 409, {"error": "already_allowed"}
            if current in ("approved", "denied"):
                same = (current == "approved" and outcome == "approve") or (current == "denied" and outcome == "deny")
                return (200, record) if same else (409, {"error": "already_resolved"})
            if current != "hold_for_human":
                return 409, {"error": "not_a_money_hold"}
            if outcome == "deny":
                decision["decision"] = "denied"
                decision["proceed"] = False
                decision["status"] = "denied"
                decision["counted"] = False
                decision["reason"] = "A person denied this amount. It was not added to the daily totals."
                record["decision"] = decision
                connection.execute("UPDATE dashboard_events SET record=? WHERE id=?", (json.dumps(record), check_id))
                return 200, record
            if decision.get("amount") is None:
                if "amount" not in body:
                    raise ValueError("Approval of a missing amount requires a positive amount")
                state, amount = parse_amount(body["amount"])
                if state != "present" or amount <= 0:
                    raise ValueError("Approval of a missing amount requires a positive amount")
            else:
                amount = Decimal(decision["amount"])
                if "amount" in body:
                    state, supplied = parse_amount(body["amount"])
                    if state != "present" or supplied != amount:
                        raise ValueError("Amount does not match the held check")
            policy = self._read_policy(connection)
            if decision.get("currency") not in (None, policy.currency):
                raise ValueError("Currency does not match the ledger")
            day = utc_day(now)
            customer = decision.get("customer_ref")
            session = decision.get("session_id")
            run = decision.get("run_id")
            totals = {
                "customer": self._sum(connection, day, policy.currency, "customer", customer) if customer else Decimal("0"),
                "session": self._sum(connection, day, policy.currency, "session", session) if session else Decimal("0"),
                "run": self._sum(connection, day, policy.currency, "run", run) if run else Decimal("0"),
                "overall": self._sum(connection, day, policy.currency, "overall", None),
            }
            over = []
            if customer and totals["customer"] + amount > policy.daily_customer_cap:
                over.append("daily_customer_cap")
            if session and totals["session"] + amount > policy.daily_session_cap:
                over.append("daily_session_cap")
            if run and totals["run"] + amount > policy.run_cap:
                over.append("run_cap")
            if totals["overall"] + amount > policy.daily_overall_cap:
                over.append("daily_overall_cap")
            connection.execute(
                "INSERT INTO money_entries (idempotency_key, day, currency, amount, customer_ref, session_id, run_id, decision) VALUES (?,?,?,?,?,?,?,?)",
                ("approval:" + check_id, day, policy.currency, format(amount, "f"), customer, session, run, "approved"))
            decision.update({
                "decision": "approved",
                "proceed": True,
                "status": "allowed",
                "counted": True,
                "amount": format(amount, "f"),
                "currency": policy.currency,
                "counted_day": day,
                "approved_over_cap": over,
                "user_message": None,
                "reason": (
                    "A person approved this amount and it was added to the daily totals. "
                    "This is only a money-limit record. It does not mean the action is safe."
                ),
                "totals": {
                    "currency": policy.currency,
                    "amount": format(amount, "f"),
                    "counted": True,
                    "customer": self._scope_snapshot(customer, totals["customer"], amount, policy.daily_customer_cap, True),
                    "session": self._scope_snapshot(session, totals["session"], amount, policy.daily_session_cap, True),
                    "run": self._scope_snapshot(run, totals["run"], amount, policy.run_cap, True),
                    "overall": self._scope_snapshot("org", totals["overall"], amount, policy.daily_overall_cap, True),
                },
            })
            record["decision"] = decision
            connection.execute("UPDATE dashboard_events SET record=? WHERE id=?", (json.dumps(record), check_id))
            return 200, record

    def get_check(self, check_id):
        try:
            if str(uuid.UUID(check_id)) != check_id:
                return None
        except (ValueError, AttributeError):
            return None
        with self.connect() as connection:
            row = connection.execute("SELECT record FROM dashboard_events WHERE id=?", (check_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def load_json(self, env):
        if env.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json" or env.get("HTTP_TRANSFER_ENCODING"):
            raise ValueError("JSON with Content-Length required")
        length = int(env.get("CONTENT_LENGTH", ""))
        if not 1 <= length <= 16384:
            return 413, {"error": "invalid_body_size"}
        raw = env["wsgi.input"].read(length)
        if len(raw) != length:
            raise ValueError("Incomplete body")
        return 0, parse_json(raw)

    def handle(self, env):
        path, method = env.get("PATH_INFO", ""), env.get("REQUEST_METHOD", "GET")
        if path == "/" and method == "GET":
            return 200, self.html, "text/html; charset=utf-8"
        if path == "/healthz" and method == "GET":
            return 200, {
                "service": "watchtower",
                "mode": "monitor_only",
                "version": VERSION,
                "money_limits": True,
            }, "application/json"
        if not hmac.compare_digest(env.get("HTTP_AUTHORIZATION", "").encode(), ("Bearer " + self.token).encode()):
            return 401, {"error": "unauthorized"}, "application/json"
        if path == "/api/v1/policy" and method == "GET":
            return 200, self.money_policy_view(), "application/json"
        if path == "/api/v1/policy" and method == "POST":
            status, body = self.load_json(env)
            if status:
                return status, body, "application/json"
            status, result = self.update_money_policy(body)
            return status, result, "application/json"
        if path == "/api/v1/check" and method == "POST":
            status, body = self.load_json(env)
            if status:
                return status, body, "application/json"
            status, record = self.check_action(body, env.get("HTTP_IDEMPOTENCY_KEY", ""))
            return status, record, "application/json"
        resolve_prefix = "/api/v1/checks/"
        if method == "POST" and path.startswith(resolve_prefix) and path.endswith("/resolve"):
            status, body = self.load_json(env)
            if status:
                return status, body, "application/json"
            check_id = path[len(resolve_prefix):-len("/resolve")]
            status, record = self.resolve_check(check_id, body)
            return status, record, "application/json"
        if method == "GET" and path.startswith("/api/v1/checks/"):
            record = self.get_check(path[len("/api/v1/checks/"):])
            if record is None:
                return 404, {"error": "not_found"}, "application/json"
            return 200, record, "application/json"
        if path == "/api/events" and method == "GET":
            with self.connect() as connection:
                rows = connection.execute("SELECT record FROM dashboard_events ORDER BY created DESC,id DESC LIMIT 50").fetchall()
                total = connection.execute("SELECT count(*) FROM dashboard_events").fetchone()[0]
            return 200, {"events": [json.loads(row[0]) for row in rows], "total": total,
                         "mode": "monitor_only", "ai_configured": bool(os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_MODEL")),
                         "image_analysis_integrated": False, "decoys_deployed": False,
                         "version": VERSION}, "application/json"
        if path != "/api/events" or method != "POST":
            return 404, {"error": "not_found"}, "application/json"
        status, body = self.load_json(env)
        if status:
            return status, body, "application/json"
        status, record = self.submit(body, env.get("HTTP_IDEMPOTENCY_KEY", ""))
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
                     daily_limit=int(os.environ.get("WATCHTOWER_DAILY_ANALYSIS_LIMIT", "20")),
                     money_policy=policy_from_mapping(os.environ))


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
    print("Money-limit checks: POST /api/v1/check. Version " + VERSION + ".")
    print("Monitor only. No autonomous collection or tool execution. An auto-allow is not a safety guarantee. Never expose this development server publicly.")
    with make_server("127.0.0.1", 8000, app, handler_class=Quiet) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
