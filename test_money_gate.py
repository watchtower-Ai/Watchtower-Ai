"""Money-limit decisions. Amounts are test fixtures. Nothing here moves money."""
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from money_gate import (
    DEFAULT_USER_MESSAGE,
    MoneyPolicy,
    StrictnessError,
    apply_patch,
    default_policy,
    is_money_action,
)
from watchtower_web import Dashboard

TOKEN = "test-only-" + "m" * 40
DAY = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


def ceiling(**overrides):
    values = dict(
        currency="USD",
        per_action_auto_allow=Decimal("50"),
        daily_customer_cap=Decimal("80"),
        daily_session_cap=Decimal("80"),
        daily_overall_cap=Decimal("200"),
        run_cap=Decimal("80"),
        end_user_message=DEFAULT_USER_MESSAGE,
    )
    values.update(overrides)
    return MoneyPolicy(**values)


class Clock:
    def __init__(self, moment=DAY):
        self.moment = moment

    def __call__(self):
        return self.moment


class MoneyLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.calls = []

        def analyst(event):
            self.calls.append(event)
            return {"status": "completed", "model": "MOCK_NOT_LIVE",
                    "assessment": {"risk": "unclear", "explanation": "Mock test response"}}

        self.analyst = analyst
        self.app = self.make()
        self.keys = 0

    def make(self, policy=None):
        return Dashboard(
            TOKEN,
            Path(self.temp.name) / "events.sqlite3",
            analyst=self.analyst,
            money_policy=ceiling() if policy is None else policy,
            clock=self.clock,
        )

    def request(self, method="POST", path="/api/v1/check", value=None, token=TOKEN, key=None, raw=None):
        body = raw if raw is not None else json.dumps(value if value is not None else {}).encode()
        if key is None:
            self.keys += 1
            key = f"money-key-{self.keys:04d}"
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
               "HTTP_AUTHORIZATION": "Bearer " + token, "HTTP_IDEMPOTENCY_KEY": key}
        if method == "POST":
            self.clock.moment += timedelta(microseconds=1)
        status = []
        payload = b"".join(self.app(env, lambda code, headers: status.append(int(code.split()[0]))))
        parsed = payload.decode() if path == "/" else json.loads(payload)
        return status[0], parsed

    def check(self, amount="30", customer="customer-1", run="job-1", session="session-1", key=None, **extra):
        body = {"tool": "refund", "action": "issue", "customerRef": customer, "runId": run, "sessionId": session}
        if amount is not None:
            body["amount"] = amount
        body.update(extra)
        return self.request(value=body, key=key)

    def decision(self, amount="30", **extra):
        status, record = self.check(amount, **extra)
        self.assertIn(status, (200, 201))
        return record["decision"]

    def test_default_ceiling_holds_every_refund(self):
        self.app = self.make(default_policy())
        decision = self.decision("5")
        self.assertEqual(decision["decision"], "hold_for_human")
        self.assertFalse(decision["proceed"])
        self.assertEqual(decision["brake"], "per_action_threshold")
        self.assertIn("does not", self.app.money_policy_view()["note"])

    def test_under_threshold_auto_allows(self):
        decision = self.decision("20")
        self.assertEqual(decision["decision"], "auto_allow")
        self.assertTrue(decision["proceed"])
        self.assertEqual(decision["status"], "allowed")
        self.assertIsNone(decision["brake"])
        self.assertTrue(decision["counted"])
        self.assertIn("does not mean the action is safe", decision["reason"])
        self.assertNotIn("100%", decision["reason"])
        self.assertIsNone(decision["user_message"])
        self.assertFalse(self.request(method="GET", path="/api/events")[1]["events"][0]["executed"])

    def test_amount_equal_to_threshold_auto_allows(self):
        self.assertEqual(self.decision("50")["decision"], "auto_allow")

    def test_over_threshold_holds_for_human(self):
        decision = self.decision("75")
        self.assertEqual(decision["decision"], "hold_for_human")
        self.assertFalse(decision["proceed"])
        self.assertEqual(decision["status"], "pending")
        self.assertEqual(decision["brake"], "per_action_threshold")
        self.assertEqual(decision["user_message"], DEFAULT_USER_MESSAGE)
        self.assertNotEqual(decision["reason"], decision["user_message"])
        self.assertFalse(decision["counted"])
        self.assertEqual(decision["totals"]["customer"]["after"], decision["totals"]["customer"]["before"])

    def test_over_threshold_does_not_consume_the_daily_cap(self):
        self.assertEqual(self.decision("75")["decision"], "hold_for_human")
        self.assertEqual(self.decision("30")["decision"], "auto_allow")

    def test_split_attempts_sum_past_the_customer_daily_cap(self):
        first = self.decision("30")
        second = self.decision("30")
        third = self.decision("30")
        self.assertEqual(first["decision"], "auto_allow")
        self.assertEqual(second["decision"], "auto_allow")
        self.assertEqual(second["totals"]["customer"]["after"], "60")
        self.assertEqual(third["decision"], "hold_for_human")
        self.assertEqual(third["brake"], "daily_customer_cap")
        self.assertIn("daily_customer_cap", third["brakes"])
        self.assertEqual(third["totals"]["customer"]["before"], "60")
        self.assertEqual(third["totals"]["customer"]["projected"], "90")
        self.assertEqual(third["totals"]["customer"]["after"], "60")
        self.assertEqual(third["totals"]["customer"]["cap"], "80")
        self.assertIn("customer-1", third["reason"])
        self.assertIn("90", third["reason"])
        self.assertFalse(third["counted"])

    def test_rotating_customers_in_one_job_hit_the_run_cap(self):
        self.app = self.make(ceiling(
            daily_customer_cap=Decimal("500"), daily_session_cap=Decimal("500"), daily_overall_cap=Decimal("500")))
        self.assertEqual(self.decision("30", customer="customer-a", session=None)["decision"], "auto_allow")
        self.assertEqual(self.decision("30", customer="customer-b", session=None)["decision"], "auto_allow")
        decision = self.decision("30", customer="customer-c", session=None)
        self.assertEqual(decision["brake"], "run_cap")
        self.assertEqual(decision["totals"]["run"]["projected"], "90")
        self.assertEqual(decision["totals"]["customer"]["before"], "0")

    def test_rotating_customer_and_job_hit_the_overall_cap(self):
        self.app = self.make(ceiling(
            daily_overall_cap=Decimal("80"), run_cap=Decimal("500"),
            daily_customer_cap=Decimal("500"), daily_session_cap=Decimal("500")))
        self.assertEqual(self.decision("30", customer="customer-a", run="job-a")["decision"], "auto_allow")
        self.assertEqual(self.decision("30", customer="customer-b", run="job-b")["decision"], "auto_allow")
        decision = self.decision("30", customer="customer-c", run="job-c")
        self.assertEqual(decision["brake"], "daily_overall_cap")
        self.assertEqual(decision["totals"]["overall"]["before"], "60")
        self.assertEqual(decision["totals"]["overall"]["projected"], "90")

    def test_same_customer_across_jobs_shares_the_daily_total(self):
        self.assertEqual(self.decision("30", run="job-a")["decision"], "auto_allow")
        self.assertEqual(self.decision("30", run="job-b")["decision"], "auto_allow")
        self.assertEqual(self.decision("30", run="job-c")["brake"], "daily_customer_cap")

    def test_session_cap_sums_when_no_customer_is_sent(self):
        self.app = self.make(ceiling(run_cap=Decimal("500"), daily_overall_cap=Decimal("500")))
        self.assertEqual(self.decision("40", customer=None, run=None)["decision"], "auto_allow")
        decision = self.decision("50", customer=None, run=None)
        self.assertEqual(decision["brake"], "daily_session_cap")

    def test_missing_amount_stays_hold_for_human_and_does_not_count(self):
        decision = self.decision(None)
        self.assertEqual(decision["decision"], "hold_for_human")
        self.assertEqual(decision["brake"], "missing_amount")
        self.assertFalse(decision["proceed"])
        self.assertIsNone(decision["amount"])
        self.assertFalse(decision["counted"])
        self.assertIn("not treated as zero", decision["reason"])
        self.assertEqual(self.decision("30")["decision"], "auto_allow")
        self.assertEqual(self.decision("30")["totals"]["customer"]["before"], "30")

    def test_replay_does_not_double_count(self):
        self.app = self.make(ceiling(daily_customer_cap=Decimal("70"), run_cap=Decimal("70"), daily_session_cap=Decimal("70")))
        status, first = self.check("30", key="same-refund-key")
        self.assertEqual(status, 201)
        status, replay = self.check("30", key="same-refund-key")
        self.assertEqual(status, 200)
        self.assertEqual(replay["id"], first["id"])
        self.assertEqual(self.decision("30")["decision"], "auto_allow")
        self.assertEqual(self.decision("30")["brake"], "daily_customer_cap")

    def test_next_utc_day_starts_a_new_total(self):
        self.assertEqual(self.decision("50")["decision"], "auto_allow")
        self.clock.moment = DAY + timedelta(days=1)
        decision = self.decision("50")
        self.assertEqual(decision["decision"], "auto_allow")
        self.assertEqual(decision["totals"]["customer"]["before"], "0")

    def test_settings_can_tighten_and_cannot_loosen(self):
        with self.assertRaises(StrictnessError):
            apply_patch(self.app.money_ceiling, self.app.money_ceiling, {"per_action_auto_allow": "51"})
        status, body = self.request(path="/api/v1/policy", value={"per_action_auto_allow": "80"})
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "settings_would_loosen")
        status, body = self.request(path="/api/v1/policy", value={"daily_customer_cap": "40", "run_cap": "40"})
        self.assertEqual(status, 200)
        self.assertEqual(body["effective"]["daily_customer_cap"], "40")
        self.assertEqual(self.decision("30")["decision"], "auto_allow")
        self.assertEqual(self.decision("30")["brake"], "daily_customer_cap")
        status, _ = self.request(path="/api/v1/policy", value={"daily_customer_cap": "60"})
        self.assertEqual(status, 409)
        self.assertEqual(self.request(method="GET", path="/api/v1/policy")[1]["effective"]["daily_customer_cap"], "40")

    def test_custom_user_message_is_what_the_end_user_sees(self):
        message = "Vi behöver att en person tittar på det här innan det går vidare."
        status, _ = self.request(path="/api/v1/policy", value={"end_user_message": message})
        self.assertEqual(status, 200)
        decision = self.decision(None)
        self.assertEqual(decision["user_message"], message)
        self.assertNotEqual(decision["reason"], message)
        self.assertIn("No amount was provided", decision["reason"])

    def test_model_from_caller_is_in_the_decision_log(self):
        decision = self.decision("20", model="grok-4")
        self.assertEqual(decision["model"], "grok-4")
        self.assertEqual(decision["model_source"], "caller")

    def test_model_from_analyst_is_recorded_when_caller_omits_it(self):
        status, record = self.request(path="/api/events", value={
            "tool": "refund", "arguments": {"action": "issue"}, "source": "synthetic",
            "analyze": True, "amount": "10", "customer_ref": "customer-1", "run_id": "job-9",
        })
        self.assertEqual(status, 201)
        self.assertEqual(record["decision"]["decision"], "auto_allow")
        self.assertEqual(record["decision"]["model"], "MOCK_NOT_LIVE")
        self.assertEqual(record["decision"]["model_source"], "analyst")
        self.assertEqual(record["analysis"]["model"], "MOCK_NOT_LIVE")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["arguments"]["amount"], "10")

    def test_caller_model_is_kept_when_the_analyst_also_answers(self):
        _, record = self.request(path="/api/events", value={
            "tool": "discount", "arguments": {}, "source": "user_submitted", "analyze": True,
            "amount": "10", "model": "shop-model", "customer_ref": "customer-1",
        })
        self.assertEqual(record["decision"]["model"], "shop-model")
        self.assertEqual(record["decision"]["model_source"], "caller")
        self.assertEqual(record["decision"]["analyst_model"], "MOCK_NOT_LIVE")

    def test_source_hint_is_recorded_on_a_risky_action(self):
        decision = self.decision(None, sourceHint={"kind": "email", "value": "buyer@example.com"})
        self.assertEqual(decision["source_hint"], {"kind": "email", "value": "buyer@example.com"})
        decision = self.decision("80", source_hint="https://shop.example/orders/9")
        self.assertEqual(decision["source_hint"]["kind"], "url")
        decision = self.decision("80", source_hint="/inbox/refunds")
        self.assertEqual(decision["source_hint"], {"kind": "page", "value": "/inbox/refunds"})
        stored = self.request(method="GET", path="/api/events")[1]["events"][0]
        self.assertEqual(stored["source_hint"]["kind"], "page")
        self.assertEqual(stored["decision"]["source_hint"]["kind"], "page")

    def test_currency_mismatch_is_held_and_not_added(self):
        decision = self.decision("10", currency="EUR")
        self.assertEqual(decision["brake"], "currency_mismatch")
        self.assertFalse(decision["counted"])
        self.assertEqual(self.decision("10")["totals"]["overall"]["before"], "0")

    def test_zero_amount_is_held(self):
        self.assertEqual(self.decision("0")["brake"], "non_positive_amount")

    def test_float_amount_is_rejected(self):
        raw = b'{"tool":"refund","action":"issue","amount":10.5}'
        self.assertEqual(self.request(raw=raw)[0], 400)

    def test_non_money_check_is_not_approved(self):
        status, record = self.request(value={"tool": "email", "action": "send", "amount": "10"})
        self.assertEqual(status, 201)
        self.assertEqual(record["decision"]["decision"], "not_applicable")
        self.assertFalse(record["decision"]["proceed"])
        self.assertFalse(record["executed"])

    def test_credit_card_read_is_not_a_money_action(self):
        self.assertFalse(is_money_action("credit_card", "read"))
        self.assertTrue(is_money_action("store_credit", "issue"))
        self.assertTrue(is_money_action("orders", "price_override"))
        status, record = self.check(None, tool="store_credit")
        self.assertEqual(status, 201)
        self.assertEqual(record["decision"]["brake"], "missing_amount")

    def test_check_can_be_read_back(self):
        _, record = self.check("20")
        status, stored = self.request(method="GET", path="/api/v1/checks/" + record["id"])
        self.assertEqual(status, 200)
        self.assertEqual(stored["decision"]["decision"], "auto_allow")
        self.assertEqual(self.request(method="GET", path="/api/v1/checks/not-an-id")[0], 404)

    def test_unauthorized_check_is_not_stored(self):
        self.assertEqual(self.request(token="nope")[0], 401)
        self.assertEqual(self.request(method="GET", path="/api/events")[1]["total"], 0)

    def resolve(self, check_id, outcome, amount=None):
        body = {"outcome": outcome}
        if amount is not None:
            body["amount"] = amount
        return self.request(path="/api/v1/checks/" + check_id + "/resolve", value=body)

    def test_approval_adds_the_held_amount_to_the_same_total(self):
        self.app = self.make(ceiling(
            per_action_auto_allow=Decimal("30"), daily_customer_cap=Decimal("50"),
            daily_session_cap=Decimal("50"), run_cap=Decimal("50"), daily_overall_cap=Decimal("50")))
        self.assertEqual(self.decision("20")["decision"], "auto_allow")
        self.assertEqual(self.decision("20")["decision"], "auto_allow")
        status, held = self.check("20")
        self.assertEqual(held["decision"]["brake"], "daily_customer_cap")
        status, approved = self.resolve(held["id"], "approve")
        self.assertEqual(status, 200)
        self.assertTrue(approved["decision"]["proceed"])
        self.assertEqual(approved["decision"]["decision"], "approved")
        self.assertEqual(approved["decision"]["totals"]["customer"]["after"], "60")
        self.assertIn("daily_customer_cap", approved["decision"]["approved_over_cap"])
        self.assertIn("does not mean the action is safe", approved["decision"]["reason"])
        again = self.resolve(held["id"], "approve")
        self.assertEqual(again[0], 200)
        self.assertEqual(self.decision("20")["totals"]["customer"]["before"], "60")

    def test_denied_hold_does_not_count_and_missing_amount_needs_one(self):
        status, held = self.check(None)
        self.assertEqual(self.resolve(held["id"], "approve")[0], 400)
        self.assertEqual(self.decision("30")["decision"], "auto_allow")
        status, denied = self.resolve(held["id"], "deny")
        self.assertEqual(status, 200)
        self.assertEqual(denied["decision"]["decision"], "denied")
        self.assertFalse(denied["decision"]["proceed"])
        self.assertEqual(self.resolve(held["id"], "approve")[0], 409)
        self.assertEqual(self.decision("30")["totals"]["customer"]["before"], "30")

    def test_page_does_not_claim_complete_protection(self):
        status, html = self.request(method="GET", path="/")
        self.assertEqual(status, 200)
        self.assertIn("do not stop every unwanted action", html)
        self.assertIn("Money limits", html)
        self.assertNotIn("100% secure", html)
        self.assertNotIn("100% protection", html)


if __name__ == "__main__":
    unittest.main()
