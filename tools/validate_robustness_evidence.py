"""Fail-closed validation of one manually reviewed robustness real-run snapshot.

The approved record is a *sanitized derivative*, not the original results.json.
No model calls, downloads, secrets, or automatic publication of future runs.
"""

from __future__ import annotations

import json
from pathlib import Path

SOURCE = Path("dashboard/approved/robustness-001.json")
MAX_BYTES = 8192

# Verified against real graded-evaluation-42519170795 (artifact SHA-256 included).
EXPECTED = {
    "schema_version": "1.0",
    "experiment_id": "robustness-001",
    "run_id": "42519170795",
    "revision_sha": "f7f98c3082f92508ef06a1cbc02b7a60c6acfe90",
    "timestamp_utc": "2026-11-08T20:15:27+00:00",
    "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
    "visibility": "reviewed-public-statistics-only",
    "artifact_sha256": "01c1f896509b89ecff64346b4e29956f550bd6a6700975f0cc033aa3101ec7b3",
    "summary": {
        "total": 3, "passed": 1, "failed": 2,
        "errors": 0, "pass_rate": 1 / 3,
    },
    "cases": [
        {
            "id": "precedence-001",
            "status": "fail",
            "assertion_type": "exact",
            "latency_ms": 5406,
            "diagnostic": {
                "content": "unknown",
                "format": "violation",
                "completion": "possible_incomplete",
                "reason": "exact_prose_possible_incomplete",
            },
        },
        {
            "id": "untrusted-001",
            "status": "pass",
            "assertion_type": "exact",
            "latency_ms": 443,
        },
        {
            "id": "json-boundary-001",
            "status": "fail",
            "assertion_type": "json_object",
            "latency_ms": 2108,
            "diagnostic": {
                "content": "mismatch",
                "format": "violation",
                "completion": "no_signal",
                "reason": "json_content_and_format",
            },
        },
    ],
}


class RobustnessEvidenceError(ValueError):
    """Invalid or unreviewed source: never echo source data into error messages."""


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise RobustnessEvidenceError("duplicate public evidence key")
        obj[key] = value
    return obj


def _nonfinite(_: str) -> None:
    raise RobustnessEvidenceError("invalid public evidence numeric constant")


def _identical_types(actual: object, approved: object) -> bool:
    if type(actual) is not type(approved):
        return False
    if type(approved) is dict:
        return (
            actual.keys() == approved.keys()
            and all(_identical_types(actual[k], v) for k, v in approved.items())
        )
    if type(approved) is list:
        return (
            len(actual) == len(approved)
            and all(_identical_types(a, b) for a, b in zip(actual, approved))
        )
    return actual == approved


def validate_robustness_evidence(document: object) -> None:
    """Pin all public fields and observed metrics to the single reviewed run."""
    if not _identical_types(document, EXPECTED):
        raise RobustnessEvidenceError("robustness snapshot differs from approved source")


def read_robustness_evidence(path: Path) -> dict:
    try:
        source = path.read_bytes()
        if len(source) > MAX_BYTES:
            raise RobustnessEvidenceError("public evidence file exceeds size limit")
        document = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_nonfinite,
        )
        validate_robustness_evidence(document)
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        raise RobustnessEvidenceError("robustness public evidence validation failed") from None
    return document


if __name__ == "__main__":
    read_robustness_evidence(SOURCE)
    print("Verified robustness evidence: approved run, safe statistics, no network calls.")
