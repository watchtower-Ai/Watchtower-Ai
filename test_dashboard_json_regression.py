"""Unambiguous JSON rejection regressions for the Render dashboard backend.
Run in watchtower-Ai/Watchtower-Ai, branch watchtower-backend-v2:
    python -m unittest -v test_dashboard_json_regression.py
No network or model providers; isolated temporary SQLite databases.
"""
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from watchtower_web import Dashboard, parse_json

VALID = b'{"tool":"synthetic.scenario","arguments":{"value":1},"source":"synthetic","analyze":false}'
DUPLICATES = {
    "top_level": b'{"tool":"synthetic.scenario","tool":"synthetic.scenario","arguments":{"value":1},"source":"synthetic","analyze":false}',
    "nested": b'{"tool":"synthetic.scenario","arguments":{"value":1,"value":1},"source":"synthetic","analyze":false}',
}


def nonfinite_payload(token):
    return (b'{"tool":"synthetic.scenario","arguments":{"value":' + token +
            b'},"source":"synthetic","analyze":false}')


NONFINITE = {name: nonfinite_payload(name.encode()) for name in ("NaN", "Infinity", "-Infinity", "1e400")}


class ParserRegressionTests(unittest.TestCase):
    def test_valid_control(self):
        value = parse_json(VALID)
        self.assertEqual(set(value), {"tool", "arguments", "source", "analyze"})
        self.assertEqual(value["arguments"], {"value": 1})

    def test_duplicate_keys_raise_specific_parser_error(self):
        for label, raw in DUPLICATES.items():
            with self.subTest(label=label):
                # A conventional parser accepts this as exactly the valid request.
                self.assertEqual(json.loads(raw), json.loads(VALID))
                with self.assertRaisesRegex(ValueError, r"^Duplicate key$"):
                    parse_json(raw)

    def test_nonfinite_values_raise_specific_parser_error(self):
        for label, raw in NONFINITE.items():
            with self.subTest(label=label):
                self.assertEqual(set(json.loads(raw)), set(json.loads(VALID)))
                with self.assertRaisesRegex(ValueError, r"^Non-finite (value|number)$"):
                    parse_json(raw)

    def test_benign_lookalikes_are_accepted(self):
        for value in (0, -1, 1.25, 1e100, "NaN", "Infinity", None):
            with self.subTest(value=value):
                body = json.loads(VALID)
                body["arguments"]["value"] = value
                raw = json.dumps(body, allow_nan=False).encode()
                self.assertEqual(parse_json(raw), body)


class WSGIRegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.token = "synthetic-test-token-" + "x" * 32
        self.analyst = Mock(side_effect=AssertionError("No analysis permitted"))
        self.app = Dashboard(self.token, Path(self.directory.name)/"events.sqlite3",
                             analyst=self.analyst, html=b"", daily_limit=0)
        self.counter = 0

    def snapshot(self):
        with sqlite3.connect(self.app.db) as connection:
            return connection.execute("SELECT id,key,digest,created,requested,record FROM dashboard_events ORDER BY id").fetchall()

    def submit(self, raw):
        self.counter += 1
        captured = {}
        env = {"PATH_INFO": "/api/events", "REQUEST_METHOD": "POST",
               "HTTP_AUTHORIZATION": "Bearer " + self.token,
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
               "HTTP_IDEMPOTENCY_KEY": f"json-regression-{self.counter:04d}",
               "wsgi.input": io.BytesIO(raw)}
        def start(status, headers):
            captured["status"] = int(status.split()[0])
        body = b"".join(self.app(env, start))
        return captured["status"], json.loads(body)

    def check_rejections(self, cases):
        # Prove that schema, authentication, headers and storage work first.
        self.assertEqual(self.submit(VALID)[0], 201)
        for label, raw in cases.items():
            with self.subTest(label=label):
                before = self.snapshot()
                status, body = self.submit(raw)
                self.assertEqual(status, 400)
                self.assertEqual(body, {"error": "invalid_request"})
                self.assertEqual(self.snapshot(), before)
                self.analyst.assert_not_called()
                # A valid request still succeeds immediately after the rejection.
                self.assertEqual(self.submit(VALID)[0], 201)
                self.analyst.assert_not_called()

    def test_duplicate_keys_rejected_without_side_effects(self):
        self.check_rejections(DUPLICATES)

    def test_nonfinite_values_rejected_without_side_effects(self):
        self.check_rejections(NONFINITE)


if __name__ == "__main__":
    unittest.main()
