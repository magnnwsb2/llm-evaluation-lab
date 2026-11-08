"""Offline integrity gate for manually produced evaluation artifacts.

SDD-001 §5.3. This module makes no provider requests and reads no secrets.
It validates consistency, not provider provenance or authenticity.
"""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contracts import ContractError, Experiment, load_experiment
from .run_evaluation import MANIFEST, build_report
from .scoring import CaseResult, ERROR_CATEGORIES, grade, summarize

MAX_REPORT_BYTES = 256 * 1024
_SHA = re.compile(r"[a-fA-F0-9]{40}\Z")
_RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")

_TOP_KEYS = {
    "schema_version", "experiment_id", "model", "run_id",
    "timestamp_utc", "revision_sha", "configuration", "summary", "cases",
}
_CONFIG_KEYS = {
    "provider", "cases_file", "max_cases", "repetitions",
    "max_output_tokens", "temperature",
}
_SUMMARY_KEYS = {"total", "passed", "failed", "errors", "pass_rate"}
_CASE_KEYS = {
    "id", "status", "assertion_type", "latency_ms", "response",
    "error_category",
}


def _fail() -> None:
    """Report errors are deliberately generic to avoid displaying response text."""
    raise ContractError("evaluation artifact failed integrity validation")


def _object(value: object, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        _fail()
    return value


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    output = {}
    for key, value in pairs:
        if key in output:
            _fail()
        output[key] = value
    return output


def _nonfinite(_: str) -> None:
    _fail()


def _read_report(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_REPORT_BYTES:
            _fail()
        content = path.read_text(encoding="utf-8")
        result = json.loads(
            content, object_pairs_hook=_no_duplicates,
            parse_constant=_nonfinite,
        )
    except (OSError, UnicodeError, ValueError, RecursionError):
        _fail()
    return _object(result, _TOP_KEYS)


def _validate_identity(
    document: dict, experiment: Experiment, *, run_id: str, revision: str
) -> None:
    if document["schema_version"] != "1.0":
        _fail()
    if document["experiment_id"] != experiment.experiment_id:
        _fail()
    if document["model"] != experiment.model:
        _fail()
    if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
        _fail()
    if type(revision) is not str or not _SHA.fullmatch(revision):
        _fail()
    if document["run_id"] != run_id or document["revision_sha"] != revision:
        _fail()
    value = document["timestamp_utc"]
    if type(value) is not str:
        _fail()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail()
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        _fail()


def _validate_configuration(document: dict, experiment: Experiment) -> None:
    expected = {
        "provider": experiment.provider,
        "cases_file": experiment.cases_file,
        "max_cases": experiment.max_cases,
        "repetitions": experiment.repetitions,
        "max_output_tokens": experiment.max_output_tokens,
        "temperature": experiment.temperature,
    }
    config = _object(document["configuration"], _CONFIG_KEYS)
    for key, value in expected.items():
        actual = config[key]
        if key in ("max_cases", "repetitions", "max_output_tokens"):
            if type(actual) is not int or actual != value:
                _fail()
        elif key == "temperature":
            if type(actual) not in (float, int) or not math.isfinite(actual) or actual != value:
                _fail()
        elif type(actual) is not str or actual != value:
            _fail()


def _validate_cases(document: dict, experiment: Experiment) -> list[CaseResult]:
    original = document["cases"]
    if type(original) is not list or len(original) != len(experiment.cases):
        _fail()
    result: list[CaseResult] = []
    stopped: str | None = None
    for data, case in zip(original, experiment.cases):
        entry = _object(data, _CASE_KEYS)
        if entry["id"] != case.id or entry["assertion_type"] != case.assertion.type:
            _fail()
        status, latency = entry["status"], entry["latency_ms"]
        response, category = entry["response"], entry["error_category"]
        if type(status) is not str or status not in ("pass", "fail", "error"):
            _fail()
        if latency is not None and (type(latency) is not int or latency < 0):
            _fail()
        if stopped is not None:
            if status != "error" or category != stopped or response is not None or latency is not None:
                _fail()
        elif status == "error":
            if (response is not None or type(category) is not str
                    or category not in ERROR_CATEGORIES):
                _fail()
            stopped = category
        else:
            if (type(response) is not str or not response.strip()
                    or category is not None):
                _fail()
            if grade(case, response, latency_ms=latency).status != status:
                _fail()
        result.append(CaseResult(
            case.id, status, case.assertion.type, latency, response, category
        ))
    return result


def validate_reports(
    experiment: Experiment,
    document: dict,
    markdown: str,
    *,
    run_id: str,
    revision: str,
) -> None:
    """Check contracts, independent grade/summary and exact canonical Markdown."""
    _object(document, _TOP_KEYS)
    _validate_identity(document, experiment, run_id=run_id, revision=revision)
    _validate_configuration(document, experiment)
    results = _validate_cases(document, experiment)
    summary = _object(document["summary"], _SUMMARY_KEYS)
    expected = summarize(results)
    counts = {
        "total": expected.total, "passed": expected.passed,
        "failed": expected.failed, "errors": expected.errors,
    }
    for key, amount in counts.items():
        if type(summary[key]) is not int or summary[key] != amount:
            _fail()
    rate = summary["pass_rate"]
    if type(rate) not in (int, float) or not math.isfinite(rate):
        _fail()
    if abs(rate - expected.pass_rate) > 1e-9:
        _fail()
    _, expected_markdown = build_report(
        experiment, results,
        run_id=run_id, revision=revision,
        timestamp_utc=document["timestamp_utc"],
    )
    if markdown != expected_markdown:
        _fail()


def validate_files(
    folder: Path, *, repo_root: Path, run_id: str, revision: str
) -> None:
    experiment = load_experiment(MANIFEST, repo_root)
    doc = _read_report(folder / "results.json")
    try:
        path = folder / "report.md"
        if path.stat().st_size > MAX_REPORT_BYTES:
            _fail()
        md = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        _fail()
    validate_reports(experiment, doc, md, run_id=run_id, revision=revision)


def main() -> int:
    import os

    try:
        validate_files(
            Path(os.environ.get("EVALUATION_OUTPUT_DIR", "evaluation-output")),
            repo_root=Path("."),
            run_id=os.environ.get("GITHUB_RUN_ID", ""),
            revision=os.environ.get("GITHUB_SHA", ""),
        )
    except (ContractError, OSError, ValueError, TypeError):
        print("Evaluation artifact validation failed.", file=sys.stderr)
        return 2
    print("Evaluation artifacts: internally consistent and contract-valid.")
    print("This check does not independently verify a real provider call.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
