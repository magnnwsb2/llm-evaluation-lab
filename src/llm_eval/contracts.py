"""Strict, offline JSON contract validation for SDD-001.

No provider calls, tokens, third-party dependencies or side effects beyond reading
the requested repository files.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "1.0"
PROVIDER = "cloudflare-workers-ai"
FREE_MODEL_ALLOWLIST = frozenset({"@cf/meta/llama-3.1-8b-instruct-fp8"})
MAX_CASES = 3
MAX_REPETITIONS = 1
MAX_OUTPUT_TOKENS = 64
MAX_PROMPT_CHARS = 1000
MAX_PATTERN_CHARS = 128
MAX_JSON_BYTES = 128 * 1024

_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
_FILENAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]*\.json\Z")


class ContractError(ValueError):
    """Invalid or unsafe experiment input; messages must not echo secrets."""


@dataclass(frozen=True, slots=True)
class Assertion:
    type: str
    expected: str


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    prompt: str
    assertion: Assertion


@dataclass(frozen=True, slots=True)
class Experiment:
    experiment_id: str
    description: str
    provider: str
    model: str
    cases_file: str
    max_cases: int
    repetitions: int
    max_output_tokens: int
    temperature: float
    cases: tuple[Case, ...]


def _fields(data: Any, required: set[str], context: str) -> dict[str, Any]:
    if type(data) is not dict:
        raise ContractError(f"{context}: expected JSON object")
    missing = required - data.keys()
    extra = data.keys() - required
    if missing or extra:
        raise ContractError(
            f"{context}: unexpected or missing fields "
            f"(missing={sorted(missing)}, extra={sorted(extra)})"
        )
    return data


def _string(value: Any, name: str, max_chars: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > max_chars:
        raise ContractError(f"{name}: expected nonempty string (max {max_chars} chars)")
    return value


def _slug(value: Any, name: str) -> str:
    value = _string(value, name, 64)
    if not _SLUG.fullmatch(value):
        raise ContractError(f"{name}: invalid identifier")
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError(f"{name}: expected integer between {minimum} and {maximum}")
    return value


def _temperature(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ContractError("temperature: expected finite number between 0 and 1")
    return float(value)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ContractError("JSON: duplicate object key")
        output[key] = value
    return output


def _reject_nonfinite(_: str) -> None:
    raise ContractError("JSON: non-finite numeric value")


def _repo_json_path(raw: str, repo_root: Path, folder: str) -> Path:
    if type(raw) is not str or "\\" in raw:
        raise ContractError("path: expected a repository-relative POSIX path")
    value = PurePosixPath(raw)
    if (value.is_absolute() or len(value.parts) != 2 or
            value.parts[0] != folder or
            value.as_posix() != raw or
            not _FILENAME.fullmatch(value.parts[1])):
        raise ContractError(f"path: expected {folder}/<filename>.json")
    root = repo_root.resolve(strict=True)
    try:
        resolved = (root / raw).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ContractError("path: file missing or inaccessible") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ContractError("path: file must remain inside repository")
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ContractError("JSON: file exceeds maximum size")
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("JSON: file cannot be read or parsed") from exc
    if type(data) is not dict:
        raise ContractError("JSON: top level must be an object")
    return data


def _validate_cases(data: dict[str, Any], max_cases: int) -> tuple[Case, ...]:
    _fields(data, {"schema_version", "cases"}, "cases")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ContractError("cases: unsupported schema version")
    raw_cases = data["cases"]
    if type(raw_cases) is not list or not 1 <= len(raw_cases) <= max_cases:
        raise ContractError(f"cases: expected 1 to {max_cases} items")
    seen: set[str] = set()
    cases: list[Case] = []
    for item in raw_cases:
        _fields(item, {"id", "prompt", "assertion"}, "case")
        identifier = _slug(item["id"], "case.id")
        if identifier in seen:
            raise ContractError("case.id: duplicate identifier")
        seen.add(identifier)
        prompt = _string(item["prompt"], "case.prompt", MAX_PROMPT_CHARS)
        assertion = _fields(item["assertion"], {"type", "expected"}, "assertion")
        kind = assertion["type"]
        if type(kind) is not str or kind not in ("exact", "contains", "regex", "json_object"):
            raise ContractError("assertion.type: unsupported objective rule")
        expected = _string(assertion["expected"], "assertion.expected", MAX_PROMPT_CHARS)
        if kind == "regex":
            if len(expected) > MAX_PATTERN_CHARS:
                raise ContractError("assertion.expected: regex too long")
            try:
                re.compile(expected)
            except re.error as exc:
                raise ContractError("assertion.expected: invalid regex") from exc
        if kind == "json_object":
            # Deferred import avoids a circular module dependency: the parser
            # reuses ContractError but has no network or file side effects.
            from .json_object import parse_flat_object
            parse_flat_object(expected, max_chars=MAX_PROMPT_CHARS)
        cases.append(Case(identifier, prompt, Assertion(kind, expected)))
    return tuple(cases)


def load_experiment(manifest_path: str, repo_root: Path) -> Experiment:
    """Validate a repository-local experiment and its cases before network I/O."""
    root = Path(repo_root)
    data = _read_json(_repo_json_path(manifest_path, root, "experiments"))
    required = {
        "schema_version", "experiment_id", "description", "provider", "model",
        "cases_file", "max_cases", "repetitions", "max_output_tokens", "temperature",
    }
    _fields(data, required, "experiment")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ContractError("experiment: unsupported schema version")
    experiment_id = _slug(data["experiment_id"], "experiment_id")
    description = _string(data["description"], "description", 240)
    if data["provider"] != PROVIDER:
        raise ContractError("provider: unsupported provider")
    if type(data["model"]) is not str or data["model"] not in FREE_MODEL_ALLOWLIST:
        raise ContractError("model: not in approved free-plan allowlist")
    max_cases = _integer(data["max_cases"], "max_cases", 1, MAX_CASES)
    repetitions = _integer(data["repetitions"], "repetitions", 1, MAX_REPETITIONS)
    max_output_tokens = _integer(data["max_output_tokens"], "max_output_tokens", 1, MAX_OUTPUT_TOKENS)
    temperature = _temperature(data["temperature"])
    path = _repo_json_path(data["cases_file"], root, "cases")
    cases = _validate_cases(_read_json(path), max_cases)
    return Experiment(
        experiment_id=experiment_id, description=description,
        provider=PROVIDER, model=data["model"], cases_file=data["cases_file"],
        max_cases=max_cases, repetitions=repetitions,
        max_output_tokens=max_output_tokens, temperature=temperature, cases=cases,
    )
