"""Non-scoring, bounded cause analysis for objective LLM evaluation failures.

SDD-001 §5.11. A suspected incomplete response is NOT a confirmed provider
finish_reason or proof of token exhaustion. No inference or score changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .contracts import Case, ContractError
from .diagnostics import _extract_unique_object
from .json_object import MAX_RESPONSE_CHARS, parse_flat_object
from .scoring import CaseResult, grade

_UPPER_TOKEN = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_UNFINISHED_END = (",", ":", ";", "(", "[", "{", "=")
_FENCE = chr(96) * 3


@dataclass(frozen=True, slots=True)
class FailureAssessment:
    case_id: str
    content: str       # match / mismatch / unknown / unavailable
    format: str        # conforming / violation / not_assessed / unavailable
    completion: str    # possible_incomplete / no_signal / unknown / unavailable
    reason: str        # allowlisted machine code, never response text


def _possible_incomplete(response: str, *, json_document: bool = False) -> bool:
    """Specific structural hints only; cannot establish a truncated response."""
    value = response.rstrip()
    if not value or len(value) > MAX_RESPONSE_CHARS:
        return False
    if value.count(_FENCE) % 2:
        return True
    if json_document and value.count("{") > value.count("}"):
        return True
    # A trailing comma/colon can be intentional; hence POSSIBLE, not certain.
    return len(value) >= 30 and value.endswith(_UNFINISHED_END)


def _json_content(candidate: dict[str, Any], expected: str) -> str:
    reference = parse_flat_object(expected, max_chars=1000)
    if set(candidate) != set(reference):
        return "mismatch"
    equal = all(
        type(candidate[key]) is type(reference[key])
        and candidate[key] == reference[key]
        for key in reference
    )
    return "match" if equal else "mismatch"


def assess_failure(case: Case, result: CaseResult) -> FailureAssessment:
    """Diagnose one scored case. Fail closed on mismatched/forged grades."""
    if case.id != result.id or case.assertion.type != result.assertion_type:
        raise ContractError("failure assessment: inconsistent case identity")
    if result.status not in {"pass", "fail", "error"}:
        raise ContractError("failure assessment: unsupported status")
    if result.status == "error":
        if result.response is not None:
            raise ContractError("failure assessment: error cannot include response")
        return FailureAssessment(
            case.id, "unavailable", "unavailable", "unavailable", "provider_error"
        )
    if type(result.response) is not str:
        raise ContractError("failure assessment: expected response string")
    checked = grade(case, result.response)
    if checked.status != result.status:
        raise ContractError("failure assessment: inconsistent strict grade")
    if result.status == "pass":
        return FailureAssessment(
            case.id, "match", "conforming", "no_signal", "strict_pass"
        )

    response = result.response.strip()
    kind = case.assertion.type
    if kind == "json_object":
        candidate = _extract_unique_object(response)
        if candidate is None:
            return FailureAssessment(
                case.id, "unknown", "violation",
                "possible_incomplete" if _possible_incomplete(
                    response, json_document=True
                ) else "no_signal",
                "json_unparseable",
            )
        content = _json_content(candidate, case.assertion.expected)
        try:
            parse_flat_object(response, max_chars=MAX_RESPONSE_CHARS)
            standalone = True
        except ContractError:
            standalone = False
        fmt = "conforming" if standalone else "violation"
        reason = (
            "json_content_and_format" if content == "mismatch" and fmt == "violation"
            else "json_content_only" if content == "mismatch"
            else "json_format_only"
        )
        return FailureAssessment(case.id, content, fmt, "no_signal", reason)

    if kind == "exact":
        expected = case.assertion.expected.strip()
        if _UPPER_TOKEN.fullmatch(expected):
            if _UPPER_TOKEN.fullmatch(response):
                return FailureAssessment(
                    case.id, "mismatch", "conforming", "no_signal",
                    "exact_wrong_token",
                )
            if response in (expected + ".", expected + "!", expected + "?"):
                return FailureAssessment(
                    case.id, "match", "violation", "no_signal",
                    "exact_extra_punctuation",
                )
        if not response:
            return FailureAssessment(
                case.id, "unknown", "violation", "unknown", "exact_empty"
            )
        incomplete = _possible_incomplete(response)
        return FailureAssessment(
            case.id, "unknown", "violation",
            "possible_incomplete" if incomplete else "no_signal",
            "exact_prose_possible_incomplete" if incomplete else "exact_extra_text",
        )

    if kind in {"contains", "regex"}:
        return FailureAssessment(
            case.id, "mismatch", "not_assessed", "no_signal",
            "objective_rule_not_met",
        )
    raise ContractError("failure assessment: unknown objective rule")
