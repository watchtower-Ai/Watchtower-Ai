import http.client
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from wsgiref.simple_server import make_server, WSGIRequestHandler
from watchtower_web import Dashboard

TOKEN = "test-only-" + "z" * 40


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = []
        def analyst(event):
            self.calls.append(event)
            return {"status": "completed", "model": "MOCK_NOT_LIVE",
                    "assessment": {"risk": "unclear", "explanation": "Mock test response"}}
        self.app = Dashboard(TOKEN, Path(self.temp.name) / "events.sqlite3", analyst=analyst)
        self.event = {"tool": "demo.read", "arguments": {"resource": "sandbox"},
                      "source": "synthetic", "analyze": False}

    def request(self, method="GET", path="/api/events", value=None, token=TOKEN, key="request-key-0001", raw=None):
        body = raw if raw is not None else json.dumps(value or self.event).encode()
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
               "HTTP_AUTHORIZATION": "Bearer " + token, "HTTP_IDEMPOTENCY_KEY": key}
        status = []
        body = b"".join(self.app(env, lambda code, headers: status.append(int(code.split()[0]))))
        return status[0], body.decode() if path == "/" else json.loads(body)

    def test_interface_has_blue_eye_and_honest_states(self):
        status, html = self.request(path="/")
        self.assertEqual(status, 200)
        self.assertIn("protective blue eye", html)
        self.assertIn("Not deployed", html)
        self.assertIn("Not integrated", html)

    def test_unauthorized_event_read_denied(self):
        self.assertEqual(self.request(token="wrong")[0], 401)

    def test_unauthorized_submit_has_no_effect(self):
        self.assertEqual(self.request(method="POST", token="wrong")[0], 401)
        self.assertEqual(self.request()[1]["total"], 0)

    def test_synthetic_event_stored_without_ai_call(self):
        status, result = self.request(method="POST")
        self.assertEqual(status, 201)
        self.assertFalse(result["executed"])
        self.assertEqual(result["analysis"]["status"], "not_requested")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.request()[1]["total"], 1)

    def test_explicit_ai_request_uses_adapter(self):
        self.event["analyze"] = True
        status, result = self.request(method="POST")
        self.assertEqual(status, 201)
        self.assertEqual(result["analysis"]["model"], "MOCK_NOT_LIVE")
        self.assertEqual(len(self.calls), 1)

    def test_duplicate_request_does_not_call_ai_twice(self):
        self.event["analyze"] = True
        self.request(method="POST")
        self.assertEqual(self.request(method="POST")[0], 200)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.request()[1]["total"], 1)

    def test_changed_payload_cannot_reuse_key(self):
        self.request(method="POST")
        self.event["arguments"]["resource"] = "different"
        self.assertEqual(self.request(method="POST")[0], 409)

    def test_pending_event_survives_provider_failure(self):
        def unavailable(event):
            raise RuntimeError("Mock outage")
        self.app.analyst = unavailable
        self.event["analyze"] = True
        result = self.request(method="POST")[1]
        self.assertEqual(result["analysis"]["status"], "unavailable")
        self.assertEqual(self.request()[1]["total"], 1)

    def test_missing_model_is_not_success(self):
        self.app.analyst = lambda event: {"status": "not_configured", "assessment": None}
        self.event["analyze"] = True
        self.assertEqual(self.request(method="POST")[1]["analysis"]["status"], "not_configured")

    def test_events_survive_application_restart(self):
        self.request(method="POST")
        self.app = Dashboard(TOKEN, self.app.db, analyst=self.app.analyst)
        self.assertEqual(self.request()[1]["total"], 1)

    def test_nonfinite_number_rejected(self):
        raw = b'{"tool":"demo.read","arguments":{"n":1e999},"source":"synthetic","analyze":false}'
        self.assertEqual(self.request(method="POST", raw=raw)[0], 400)

    def test_duplicate_keys_rejected(self):
        raw = b'{"tool":"a","tool":"b","arguments":{},"source":"synthetic","analyze":false}'
        self.assertEqual(self.request(method="POST", raw=raw)[0], 400)

    def test_daily_requested_analysis_budget_enforced(self):
        self.app.daily_limit = 1
        self.event["analyze"] = True
        self.assertEqual(self.request(method="POST")[0], 201)
        self.assertEqual(self.request(method="POST", key="request-key-0002")[0], 429)
        self.assertEqual(len(self.calls), 1)

    def test_false_source_is_not_verified(self):
        result = self.request(method="POST")[1]
        self.assertFalse(result["source_verified"])

    def test_loopback_http_storage_and_listing(self):
        class Quiet(WSGIRequestHandler):
            def log_message(self, *args): pass
        server = make_server("127.0.0.1", 0, self.app, handler_class=Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("POST", "/api/events", json.dumps(self.event), {
                "Authorization": "Bearer " + TOKEN, "Content-Type": "application/json",
                "Idempotency-Key": "http-request-0001"})
            response = connection.getresponse()
            result = json.loads(response.read())
            connection.close()
            self.assertEqual(response.status, 201)
            self.assertFalse(result["executed"])
            self.assertEqual(self.request()[1]["total"], 1)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

if __name__ == "__main__":
    unittest.main()
