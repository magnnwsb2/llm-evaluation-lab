"""Objective, deterministic output evaluation for validated SDD-001 cases."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import Case, ContractError

ERROR_CATEGORIES = frozenset({
    "auth", "quota", "rate_limit", "network", "timeout",
    "provider", "invalid_response",
})


@dataclass(frozen=True, slots=True)
class CaseResult:
    id: str
    status: str
    assertion_type: str
    latency_ms: int | None
    response: str | None
    error_category: str | None


@dataclass(frozen=True, slots=True)
class Summary:
    total: int
    passed: int
    failed: int
    errors: int
    pass_rate: float


def grade(
    case: Case,
    response: str | None,
    *,
    latency_ms: int | None = None,
    error_category: str | None = None,
) -> CaseResult:
    """Grade one real or test response; never transform a provider error into a pass."""
    if latency_ms is not None and (type(latency_ms) is not int or latency_ms < 0):
        raise ContractError("latency_ms: expected nonnegative integer or null")
    if error_category is not None and (type(error_category) is not str or error_category not in ERROR_CATEGORIES):
        raise ContractError("error_category: unsupported sanitized category")
    if error_category is not None or response is None:
        return CaseResult(
            case.id, "error", case.assertion.type, latency_ms, None,
            error_category or "invalid_response",
        )
    if type(response) is not str:
        raise ContractError("response: expected string or null")
    assertion = case.assertion
    if assertion.type == "exact":
        passed = response.strip() == assertion.expected.strip()
    elif assertion.type == "contains":
        passed = assertion.expected in response
    elif assertion.type == "regex":
        passed = re.search(assertion.expected, response) is not None
    else:
        raise ContractError("assertion.type: unsupported")
    return CaseResult(
        case.id, "pass" if passed else "fail", assertion.type,
        latency_ms, response, None,
    )


def summarize(results: list[CaseResult] | tuple[CaseResult, ...]) -> Summary:
    if not results:
        raise ContractError("results: at least one case is required")
    statuses = [item.status for item in results]
    if any(status not in ("pass", "fail", "error") for status in statuses):
        raise ContractError("results: unsupported status")
    total = len(results)
    passed = statuses.count("pass")
    failed = statuses.count("fail")
    errors = statuses.count("error")
    return Summary(total, passed, failed, errors, passed / total)
