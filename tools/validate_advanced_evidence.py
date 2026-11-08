"""Validate a manually reviewed, statistics-only advanced real-run snapshot.

The snapshot is NOT generated automatically from Actions artifacts and is not
published by the existing Pages dashboard. Any new run requires a new review.
"""

from __future__ import annotations

import json
from pathlib import Path

SOURCE = Path("dashboard/approved/advanced-001.json")
MAX_BYTES = 8192

# Reviewed against real artifact graded-evaluation-42511351245.
EXPECTED = {
    "schema_version": "1.0",
    "experiment_id": "advanced-001",
    "run_id": "42511351245",
    "revision_sha": "6f90b6a2e9cea68e9d6f4087cb2662ba562e734b",
    "timestamp_utc": "2026-11-08T18:42:51+00:00",
    "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
    "visibility": "reviewed-public-statistics-only",
    "summary": {
        "total": 3, "passed": 2, "failed": 1,
        "errors": 0, "pass_rate": 2 / 3,
    },
    "cases": [
        {
            "id": "json-ticket-001", "status": "fail",
            "assertion_type": "json_object", "latency_ms": 2760,
            "diagnostic": "content_match_format_violation",
        },
        {
            "id": "decision-001", "status": "pass",
            "assertion_type": "exact", "latency_ms": 670,
        },
        {
            "id": "decision-002", "status": "pass",
            "assertion_type": "exact", "latency_ms": 717,
        },
    ],
    "repeated_prompt": {
        "first_id": "decision-001", "second_id": "decision-002",
        "outcome": "same",
    },
}


class EvidenceError(ValueError):
    """Public snapshot violates reviewed allowlist or provenance."""


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise EvidenceError("nonfinite JSON value")


def validate_evidence(document: object) -> None:
    """Exact approved statistics; no unreviewed or sensitive keys can escape."""
    if type(document) is not dict:
        raise EvidenceError("invalid evidence document")
    try:
        serialized = json.dumps(document, sort_keys=True, allow_nan=False)
        reference = json.dumps(EXPECTED, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise EvidenceError("evidence contains invalid JSON values") from None
    if serialized != reference:
        raise EvidenceError("evidence differs from manually reviewed run")
    # JSON comparison alone considers True == 1; reject type confusion recursively.
    def types_match(left: object, right: object) -> bool:
        if type(left) is not type(right):
            return False
        if type(left) is dict:
            return left.keys() == right.keys() and all(
                types_match(left[key], right[key]) for key in right
            )
        if type(left) is list:
            return len(left) == len(right) and all(
                types_match(a, b) for a, b in zip(left, right)
            )
        return left == right

    if not types_match(document, EXPECTED):
        raise EvidenceError("invalid evidence value type")


def read_evidence(path: Path) -> dict:
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_BYTES:
            raise EvidenceError("evidence exceeds maximum size")
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
        validate_evidence(document)
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError) as exc:
        raise EvidenceError("evidence validation failed") from None
    return document


if __name__ == "__main__":
    read_evidence(SOURCE)
    print("Advanced reviewed evidence: valid, statistics-only, no network calls.")
