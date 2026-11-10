"""Money-limit gate for refund and discount checks. Version 0.28.0.

A single call can look small while the job adds up. This module decides
whether a money action is inside the configured limits. It does not move
money, execute a tool, or claim that an allowed action is safe.

Org configuration is a ceiling. A later settings change may lower a limit.
It may not raise one. A missing amount stays on hold and is not stored as zero.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

VERSION = "0.28.0"

# Exact tool or action names, after splitting on punctuation. "credit card" is not
# included: reading a card is not the same thing as giving credit.
MONEY_EXACT = frozenset({
    "refund", "discount", "payout", "credit", "store credit",
    "price override", "partial refund",
})
MONEY_TOKENS = frozenset({"refund", "discount", "payout"})
LIMIT_FIELDS = (
    "per_action_auto_allow",
    "daily_customer_cap",
    "daily_session_cap",
    "daily_overall_cap",
    "run_cap",
)
DEFAULT_USER_MESSAGE = "A person needs to review this before it can go ahead."
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_AMOUNT_RE = re.compile(r"^\d{1,12}(\.\d{1,4})?$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class StrictnessError(ValueError):
    """A settings change would allow more money than the current ceiling."""


@dataclass(frozen=True)
class MoneyPolicy:
    currency: str
    per_action_auto_allow: Decimal
    daily_customer_cap: Decimal
    daily_session_cap: Decimal
    daily_overall_cap: Decimal
    run_cap: Decimal
    end_user_message: str

    def public(self):
        return {
            "version": VERSION,
            "currency": self.currency,
            "per_action_auto_allow": format(self.per_action_auto_allow, "f"),
            "daily_customer_cap": format(self.daily_customer_cap, "f"),
            "daily_session_cap": format(self.daily_session_cap, "f"),
            "daily_overall_cap": format(self.daily_overall_cap, "f"),
            "run_cap": format(self.run_cap, "f"),
            "end_user_message": self.end_user_message,
        }


def default_policy():
    """Hold every known money amount until an operator sets a ceiling."""
    return MoneyPolicy(
        currency="USD",
        per_action_auto_allow=Decimal("0"),
        daily_customer_cap=Decimal("0"),
        daily_session_cap=Decimal("0"),
        daily_overall_cap=Decimal("0"),
        run_cap=Decimal("0"),
        end_user_message=DEFAULT_USER_MESSAGE,
    )


def parse_limit(value):
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Money limits must be decimal strings or integers, not floats")
    text = format(value, "f") if isinstance(value, Decimal) else str(value).strip()
    if not _AMOUNT_RE.fullmatch(text):
        raise ValueError("Invalid money limit")
    amount = Decimal(text)
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid money limit")
    return amount


def parse_message(value):
    if not isinstance(value, str):
        raise ValueError("End-user message must be text")
    text = value.strip()
    if not 1 <= len(text) <= 400 or any(ord(char) < 32 for char in text):
        raise ValueError("End-user message must be 1-400 characters without control characters")
    return text


def parse_amount(value):
    """Return (state, amount). state is missing, present, or invalid."""
    if value is None:
        return "missing", None
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int, Decimal)):
        return "invalid", None
    text = format(value, "f") if isinstance(value, Decimal) else str(value).strip()
    if not _AMOUNT_RE.fullmatch(text):
        return "invalid", None
    amount = Decimal(text)
    if not amount.is_finite():
        return "invalid", None
    return "present", amount


def parse_identity(value, label):
    if value is None:
        return None
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError("Invalid " + label)
    return value


def parse_model(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid model")
    text = value.strip()
    if not 1 <= len(text) <= 100 or any(ord(char) < 32 for char in text):
        raise ValueError("Invalid model")
    return text


def parse_currency(value):
    if value is None:
        return None
    if not isinstance(value, str) or not _CURRENCY_RE.fullmatch(value.strip()):
        raise ValueError("Invalid currency")
    return value.strip()


def parse_source_hint(value):
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or len(text) > 500 or any(ord(char) < 32 for char in text):
            raise ValueError("Invalid source hint")
        if "@" in text and "://" not in text and " " not in text:
            kind = "email"
        elif text.startswith("https://") or text.startswith("http://"):
            kind = "url"
        elif text.startswith("/"):
            kind = "page"
        else:
            raise ValueError("Source hint must be an email, an http(s) URL, a page path, or kind plus value")
        return {"kind": kind, "value": text}
    if not isinstance(value, dict) or set(value) != {"kind", "value"}:
        raise ValueError("Invalid source hint")
    kind = value["kind"]
    text = value["value"]
    if kind not in ("email", "page", "url") or not isinstance(text, str):
        raise ValueError("Invalid source hint")
    text = text.strip()
    if not 1 <= len(text) <= 500 or any(ord(char) < 32 for char in text):
        raise ValueError("Invalid source hint")
    return {"kind": kind, "value": text}


def is_money_action(tool, action):
    for part in (tool, action):
        if not isinstance(part, str):
            continue
        tokens = _TOKEN_RE.findall(part.lower())
        if set(tokens) & MONEY_TOKENS:
            return True
        compact = " ".join(tokens)
        if compact in MONEY_EXACT:
            return True
    return False


def apply_patch(ceiling, current, patch):
    if not isinstance(patch, dict) or not patch:
        raise ValueError("Expected a policy patch")
    if set(patch) - ({*LIMIT_FIELDS, "end_user_message"}):
        raise ValueError("Unknown or unsupported policy field")
    values = {
        "currency": current.currency,
        "per_action_auto_allow": current.per_action_auto_allow,
        "daily_customer_cap": current.daily_customer_cap,
        "daily_session_cap": current.daily_session_cap,
        "daily_overall_cap": current.daily_overall_cap,
        "run_cap": current.run_cap,
        "end_user_message": current.end_user_message,
    }
    for field in LIMIT_FIELDS:
        if field in patch:
            values[field] = parse_limit(patch[field])
    if "end_user_message" in patch:
        values["end_user_message"] = parse_message(patch["end_user_message"])
    proposed = MoneyPolicy(**values)
    for field in LIMIT_FIELDS:
        if getattr(proposed, field) > getattr(ceiling, field) or getattr(proposed, field) > getattr(current, field):
            raise StrictnessError(field + " would make the money limit looser")
    if proposed.currency != ceiling.currency or proposed.currency != current.currency:
        raise StrictnessError("currency is fixed by the org policy")
    return proposed


def clamp_to_ceiling(ceiling, stored):
    """Keep the stricter of the stored policy and the configured ceiling."""
    return MoneyPolicy(
        currency=ceiling.currency,
        per_action_auto_allow=min(ceiling.per_action_auto_allow, stored.per_action_auto_allow),
        daily_customer_cap=min(ceiling.daily_customer_cap, stored.daily_customer_cap),
        daily_session_cap=min(ceiling.daily_session_cap, stored.daily_session_cap),
        daily_overall_cap=min(ceiling.daily_overall_cap, stored.daily_overall_cap),
        run_cap=min(ceiling.run_cap, stored.run_cap),
        end_user_message=stored.end_user_message or ceiling.end_user_message,
    )


def _scope(identity, before, cap, amount, counted):
    if identity is None:
        return None
    projected = before + amount if amount is not None else before
    after = projected if counted else before
    return {
        "id": identity,
        "before": format(before, "f"),
        "projected": format(projected, "f"),
        "after": format(after, "f"),
        "cap": format(cap, "f"),
    }


def evaluate(policy, check, totals):
    """Decide one money check from totals already committed for this UTC day.

    `check` keys: tool, action, amount_state, amount, currency, customer_ref,
    session_id, run_id, model, source_hint, day.
    `totals` maps customer, session, run, overall to Decimal sums of amounts
    that were auto-allowed. Held and missing amounts are not in those sums.
    """
    if not isinstance(policy, MoneyPolicy):
        raise ValueError("Invalid policy")
    amount_state = check.get("amount_state")
    amount = check.get("amount")
    currency = check.get("currency") or policy.currency
    customer = check.get("customer_ref")
    session = check.get("session_id")
    run = check.get("run_id")
    day = check.get("day")
    if not isinstance(day, str) or len(day) != 10:
        raise ValueError("Invalid day")

    def finish(decision, status, proceed, brake, brakes, counted, user_message):
        known_amount = amount if amount_state == "present" else None
        return {
            "version": VERSION,
            "decision": decision,
            "proceed": proceed,
            "status": status,
            "brake": brake,
            "brakes": brakes,
            "reason": _reason(policy, decision, brake, known_amount, currency, day, totals, customer, session, run),
            "user_message": user_message,
            "counted": counted,
            "day": day,
            "amount": format(known_amount, "f") if known_amount is not None else None,
            "currency": currency,
            "customer_ref": customer,
            "session_id": session,
            "run_id": run,
            "model": check.get("model"),
            "model_source": "caller" if check.get("model") else None,
            "source_hint": check.get("source_hint"),
            "totals": {
                "currency": policy.currency,
                "amount": format(known_amount, "f") if known_amount is not None else None,
                "counted": counted,
                "customer": _scope(customer, totals.get("customer", Decimal("0")), policy.daily_customer_cap, known_amount, counted),
                "session": _scope(session, totals.get("session", Decimal("0")), policy.daily_session_cap, known_amount, counted),
                "run": _scope(run, totals.get("run", Decimal("0")), policy.run_cap, known_amount, counted),
                "overall": _scope("org", totals.get("overall", Decimal("0")), policy.daily_overall_cap, known_amount, counted),
            },
            "limit_only": True,
        }

    if amount_state == "invalid":
        raise ValueError("Invalid amount")
    if amount_state == "missing" or amount is None:
        return finish("hold_for_human", "pending", False, "missing_amount", ["missing_amount"], False, policy.end_user_message)
    if check.get("currency") and check["currency"] != policy.currency:
        return finish("hold_for_human", "pending", False, "currency_mismatch", ["currency_mismatch"], False, policy.end_user_message)
    if amount <= 0:
        return finish("hold_for_human", "pending", False, "non_positive_amount", ["non_positive_amount"], False, policy.end_user_message)

    brakes = []
    if amount > policy.per_action_auto_allow:
        brakes.append("per_action_threshold")
    if customer is not None and totals.get("customer", Decimal("0")) + amount > policy.daily_customer_cap:
        brakes.append("daily_customer_cap")
    if session is not None and totals.get("session", Decimal("0")) + amount > policy.daily_session_cap:
        brakes.append("daily_session_cap")
    if run is not None and totals.get("run", Decimal("0")) + amount > policy.run_cap:
        brakes.append("run_cap")
    if totals.get("overall", Decimal("0")) + amount > policy.daily_overall_cap:
        brakes.append("daily_overall_cap")
    if brakes:
        return finish("hold_for_human", "pending", False, brakes[0], brakes, False, policy.end_user_message)
    return finish(
        "auto_allow", "allowed", True, None, [], True, None,
    )


def _money(amount):
    return format(amount, "f") if isinstance(amount, Decimal) else "0"


def _reason(policy, decision, brake, amount, currency, day, totals, customer, session, run):
    if decision == "auto_allow":
        return (
            "At or under the per-action threshold, and the daily customer, session, "
            "job and overall totals still fit. The amount was added to those totals. "
            "This is only a money-limit check. It does not mean the action is safe."
        )
    if brake == "missing_amount":
        return (
            "No amount was provided, so this refund or discount waits for a person. "
            "A missing amount is not treated as zero and is not added to the daily total."
        )
    if brake == "currency_mismatch":
        return (
            "The currency does not match the ledger currency (" + policy.currency +
            "), so this waits for a person. Amounts are not converted or added together."
        )
    if brake == "non_positive_amount":
        return "The amount is zero, so this waits for a person and is not added to the daily total."
    if brake == "per_action_threshold":
        return (
            "This amount is above the per-action auto-allow threshold of "
            + _money(policy.per_action_auto_allow) + " " + policy.currency
            + ", so it waits for a person. It was not added to the daily total."
        )
    labels = {
        "daily_customer_cap": ("customer", customer, policy.daily_customer_cap),
        "daily_session_cap": ("session", session, policy.daily_session_cap),
        "run_cap": ("job", run, policy.run_cap),
        "daily_overall_cap": ("organization", "org", policy.daily_overall_cap),
    }
    label, identity, cap = labels[brake]
    before = totals.get(
        {"daily_customer_cap": "customer", "daily_session_cap": "session", "run_cap": "run", "daily_overall_cap": "overall"}[brake],
        Decimal("0"),
    )
    projected = before + (amount or Decimal("0"))
    return (
        "The " + label + " total for " + str(identity) + " on " + day
        + " would be " + _money(projected) + " " + currency
        + ", above the cap of " + _money(cap) + " " + policy.currency
        + ". This attempt waits for a person and was not added to the total."
    )


def policy_from_mapping(mapping):
    """Build a ceiling. Decimal strings only. Absent limits stay at zero (hold)."""
    base = default_policy()
    if mapping is None:
        return base

    def pick(*names):
        for name in names:
            if name in mapping and mapping[name] not in (None, ""):
                return mapping[name]
        return None

    currency = pick("WATCHTOWER_MONEY_CURRENCY", "currency") or base.currency
    if not isinstance(currency, str) or not _CURRENCY_RE.fullmatch(currency):
        raise ValueError("Invalid currency")
    message = pick("WATCHTOWER_END_USER_MESSAGE", "end_user_message")
    return MoneyPolicy(
        currency=currency,
        per_action_auto_allow=parse_limit(pick("WATCHTOWER_MONEY_AUTO_ALLOW", "per_action_auto_allow") or "0"),
        daily_customer_cap=parse_limit(pick("WATCHTOWER_MONEY_DAILY_CUSTOMER_CAP", "daily_customer_cap") or "0"),
        daily_session_cap=parse_limit(pick("WATCHTOWER_MONEY_DAILY_SESSION_CAP", "daily_session_cap") or "0"),
        daily_overall_cap=parse_limit(pick("WATCHTOWER_MONEY_DAILY_OVERALL_CAP", "daily_overall_cap") or "0"),
        run_cap=parse_limit(pick("WATCHTOWER_MONEY_RUN_CAP", "run_cap") or "0"),
        end_user_message=parse_message(message) if message else base.end_user_message,
    )


def one_field(body, *names):
    found = [name for name in names if name in body]
    if len(found) > 1:
        raise ValueError("Duplicate field " + names[0])
    if not found:
        return None
    return body[found[0]]
