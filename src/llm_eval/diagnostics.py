"""Offline, non-scoring explanation of strict JSON-object failures (SDD §5.7).

This module never changes grades or the machine-readable results contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .contracts import Case, ContractError
from .json_object import MAX_RESPONSE_CHARS, objects_match, parse_flat_object
from .scoring import CaseResult

DIAGNOSTIC_LABELS = frozenset({
    "strict_pass", "content_match_format_violation", "content_mismatch",
    "unparseable", "unavailable",
})


@dataclass(frozen=True, slots=True)
class JsonDiagnostic:
    case_id: str
    outcome: str


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise ValueError("nonfinite JSON value")


def _extract_unique_object(response: str) -> dict[str, object] | None:
    """Find exactly one bounded flat object; surrounding prose is diagnostic-only."""
    if type(response) is not str or not 1 <= len(response) <= MAX_RESPONSE_CHARS:
        return None
    start = response.find("{")
    if start < 0:
        return None
    prefix = response[:start]
    if "{" in prefix or "}" in prefix:
        return None
    try:
        decoder = json.JSONDecoder(
            object_pairs_hook=_unique_pairs, parse_constant=_nonfinite
        )
        parsed, end_offset = decoder.raw_decode(response[start:])
        end = start + end_offset
        suffix = response[end:]
        if "{" in suffix or "}" in suffix:
            return None
        # Only zero or one paired Markdown code-fence block is supported.
        # Do not normalize a second fenced block or an ambiguous partial fence.
        before_fences = prefix.count("```")
        after_fences = suffix.count("```")
        if before_fences != after_fences or before_fences > 1:
            return None
        if before_fences == 1:
            if not prefix.rstrip().endswith(("```", "```json", "```JSON")):
                return None
            if not suffix.lstrip().startswith("```"):
                return None
        if type(parsed) is not dict:
            return None
        # The strict parser also enforces field count, key patterns, type and
        # scalar bounds. Use its canonical rules instead of maintaining a fork.
        return parse_flat_object(
            response[start:end], max_chars=MAX_RESPONSE_CHARS
        )
    except (ValueError, ContractError, RecursionError, UnicodeError):
        return None


def diagnose_json_object(case: Case, result: CaseResult) -> JsonDiagnostic:
    """Explain JSON failures without ever promoting a failed grade to pass."""
    if case.assertion.type != "json_object":
        raise ContractError("diagnostic: requires json_object assertion")
    if case.id != result.id or result.assertion_type != "json_object":
        raise ContractError("diagnostic: mismatched case/result")
    if result.status == "error" or result.response is None:
        return JsonDiagnostic(case.id, "unavailable")
    if result.status == "pass":
        if not objects_match(result.response, case.assertion.expected):
            raise ContractError("diagnostic: inconsistent strict pass")
        return JsonDiagnostic(case.id, "strict_pass")
    if result.status != "fail":
        raise ContractError("diagnostic: invalid case status")
    if objects_match(result.response, case.assertion.expected):
        raise ContractError("diagnostic: inconsistent strict fail")
    extracted = _extract_unique_object(result.response)
    if extracted is None:
        return JsonDiagnostic(case.id, "unparseable")
    expected = parse_flat_object(case.assertion.expected, max_chars=1000)
    if set(extracted) == set(expected) and all(
        type(extracted[key]) is type(expected[key])
        and extracted[key] == expected[key]
        for key in expected
    ):
        return JsonDiagnostic(case.id, "content_match_format_violation")
    return JsonDiagnostic(case.id, "content_mismatch")
