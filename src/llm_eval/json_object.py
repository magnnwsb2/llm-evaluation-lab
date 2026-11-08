"""Bounded, exact JSON-object assertions. Fully offline, no provider requests.

Only simple flat objects are supported: predictable comparisons and no ambiguity
from nested data, arrays, floats, duplicate keys or Python bool/int equivalence.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .contracts import ContractError

MAX_FIELDS = 8
MAX_RESPONSE_CHARS = 4096
_FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}\Z")


def _fail() -> None:
    raise ContractError("json_object: invalid flat object or unsupported value")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    _fail()


def parse_flat_object(value: str, *, max_chars: int) -> dict[str, Any]:
    """Strict JSON document: one flat object, exact keys and safe scalar types."""
    if type(value) is not str or not 1 <= len(value) <= max_chars:
        _fail()
    try:
        document = json.loads(
            value, object_pairs_hook=_unique_pairs, parse_constant=_nonfinite
        )
    except (ValueError, UnicodeError, RecursionError):
        _fail()
    if type(document) is not dict or not 1 <= len(document) <= MAX_FIELDS:
        _fail()
    for key, item in document.items():
        if type(key) is not str or not _FIELD_NAME.fullmatch(key):
            _fail()
        if type(item) not in (str, int, bool, type(None)):
            _fail()
        if type(item) is str and len(item) > 500:
            _fail()
        if type(item) is int and abs(item) > 10**12:
            _fail()
    return document


def objects_match(response: str, expected: str) -> bool:
    """Objective exact match; case/field order may vary, field set/types may not."""
    try:
        predicted = parse_flat_object(response, max_chars=MAX_RESPONSE_CHARS)
        reference = parse_flat_object(expected, max_chars=1000)
    except ContractError:
        return False
    if set(predicted) != set(reference):
        return False
    return all(
        type(predicted[key]) is type(reference[key])
        and predicted[key] == reference[key]
        for key in reference
    )
