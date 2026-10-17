"""Reviewed scenario retrieval. No model training, tool execution, or threat generation.
This library does not authenticate reviewers. A separate authorized operator workflow
must control review_status and production promotion. All text is untrusted data.
"""
import json
from pathlib import Path

EVIDENCE = {"hypothetical", "test_demonstrated", "observed"}
REVIEW = {"draft", "approved", "rejected"}
FIELDS = {"id", "title", "risk_category", "description", "evidence_status",
          "sources", "assumptions", "warning_signs", "expected_control",
          "safe_test", "false_positive_examples", "review_status", "reviewer"}


def nonempty(value, limit=4000):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def validate(record):
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError("Missing or unexpected scenario fields")
    for field in ("id", "title", "risk_category", "description", "expected_control", "safe_test"):
        if not nonempty(record[field]):
            raise ValueError("Invalid " + field)
    if not isinstance(record["evidence_status"], str) or record["evidence_status"] not in EVIDENCE:
        raise ValueError("Invalid evidence status")
    if not isinstance(record["review_status"], str) or record["review_status"] not in REVIEW:
        raise ValueError("Invalid review status")
    for field in ("sources", "assumptions", "warning_signs", "false_positive_examples"):
        values = record[field]
        if not isinstance(values, list) or len(values) > 30 or not all(nonempty(v) for v in values):
            raise ValueError("Invalid " + field)
    if not record["warning_signs"] or not record["false_positive_examples"]:
        raise ValueError("Warning signs and benign counterexamples are required")
    if record["evidence_status"] != "hypothetical" and not record["sources"]:
        raise ValueError("Non-hypothetical claims require evidence references")
    if record["reviewer"] is not None and not nonempty(record["reviewer"], 200):
        raise ValueError("Invalid reviewer")
    if record["review_status"] == "approved" and not record["reviewer"]:
        raise ValueError("Approval requires a recorded reviewer")
    return json.loads(json.dumps(record))


def load(path):
    path = Path(path)
    if path.stat().st_size > 1_000_000:
        raise ValueError("Scenario file exceeds development limit")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    records = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    if not isinstance(records, list) or len(records) > 500:
        raise ValueError("Expected at most 500 scenario records")
    result = [validate(record) for record in records]
    if len({record["id"] for record in result}) != len(result):
        raise ValueError("Duplicate scenario IDs")
    return result


def retrieve(records, query, limit=3):
    """Transparent lexical retrieval, not a learned risk classifier or probability."""
    import re
    if not isinstance(query, str) or len(query) > 16000:
        raise ValueError("Invalid query")
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Invalid limit")
    terms = set(re.findall(r"[a-z0-9_]+", query.lower()))
    matches = []
    for original in records:
        record = validate(original)
        if record["review_status"] != "approved":
            continue
        text = " ".join([record["title"], record["description"], *record["warning_signs"]])
        words = set(re.findall(r"[a-z0-9_]+", text.lower()))
        overlap = len(terms & words)
        if overlap:
            matches.append((overlap, record["id"], record))
    matches.sort(key=lambda item: (-item[0], item[1]))
    return [{"scenario": row[2], "matched_terms": row[0],
             "notice": "Relevance only; not evidence of an incident, intent, or safety."}
            for row in matches[:limit]]
