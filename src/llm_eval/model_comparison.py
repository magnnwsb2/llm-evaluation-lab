"""Offline foundation for matched-case, cross-model evaluation comparisons.

SDD-001 §5.13. This module NEVER invokes the model provider, changes the
model allowlist, publishes to Pages or makes a model-performance claim.
The caller must supply trusted experiment definitions, each matched to its
own validated version-1.0 evaluation artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import ContractError, Experiment, load_experiment
from .report_validation import MAX_REPORT_BYTES, _read_report, validate_reports
from .run_evaluation import select_manifest

OUTPUT_FOLDER = "comparison-output"
COMPARISON_SCHEMA = "1.0"
COMPARISON_KIND = "matched-suite-observation"


def _fail() -> None:
    raise ContractError("offline comparison: incompatible or invalid run evidence")


def suite_fingerprint(experiment: Experiment) -> str:
    """Hash exact ordered prompts, IDs and assertion contracts, NOT model names."""
    if not 1 <= len(experiment.cases) <= 3:
        _fail()
    records = [
        {
            "id": case.id,
            "prompt": case.prompt,
            "assertion": {
                "type": case.assertion.type,
                "expected": case.assertion.expected,
            },
        }
        for case in experiment.cases
    ]
    canonical = json.dumps(
        records, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _configuration(experiment: Experiment) -> tuple:
    return (
        experiment.provider, experiment.cases_file,
        experiment.max_cases, experiment.repetitions,
        experiment.max_output_tokens, experiment.temperature,
    )


def _run_summary(experiment: Experiment, document: dict) -> dict[str, Any]:
    cases = [
        {
            "id": case["id"],
            "status": case["status"],
            "latency_ms": case["latency_ms"],
        }
        for case in document["cases"]
    ]
    observed = [
        case["latency_ms"] for case in cases
        if case["latency_ms"] is not None
    ]
    return {
        "experiment_id": experiment.experiment_id,
        "model": experiment.model,
        "run_id": document["run_id"],
        "revision_sha": document["revision_sha"],
        "summary": dict(document["summary"]),
        "observed_http_latencies": len(observed),
        "mean_http_latency_ms": (
            round(sum(observed) / len(observed)) if observed else None
        ),
        "cases": cases,
    }


def compare_models(
    left_experiment: Experiment,
    left_document: dict,
    left_markdown: str,
    right_experiment: Experiment,
    right_document: dict,
    right_markdown: str,
) -> dict[str, Any]:
    """Validate BOTH complete source reports, then produce safe observations.

    The model IDs are expected to have been authorized by a trusted caller's
    load_experiment(). Offline unit tests may inject fictional model names,
    but neither those names nor this function enable model inference.
    """
    try:
        validate_reports(
            left_experiment, left_document, left_markdown,
            run_id=left_document["run_id"],
            revision=left_document["revision_sha"],
        )
        validate_reports(
            right_experiment, right_document, right_markdown,
            run_id=right_document["run_id"],
            revision=right_document["revision_sha"],
        )
    except (KeyError, TypeError, AttributeError, ValueError):
        _fail()

    left_suite = suite_fingerprint(left_experiment)
    right_suite = suite_fingerprint(right_experiment)
    if (
        left_experiment.model == right_experiment.model
        or left_suite != right_suite
        or _configuration(left_experiment) != _configuration(right_experiment)
        or (left_document["run_id"], left_document["revision_sha"])
           == (right_document["run_id"], right_document["revision_sha"])
    ):
        _fail()

    left = _run_summary(left_experiment, left_document)
    right = _run_summary(right_experiment, right_document)
    return {
        "schema_version": COMPARISON_SCHEMA,
        "kind": COMPARISON_KIND,
        "suite_sha256": left_suite,
        "cases_file": left_experiment.cases_file,
        "case_count": len(left_experiment.cases),
        "runs": [left, right],
        "case_observations": [
            {
                "id": lhs["id"],
                "left_status": lhs["status"],
                "right_status": rhs["status"],
            }
            for lhs, rhs in zip(left["cases"], right["cases"])
        ],
        "interpretation": "descriptive_only_not_a_model_ranking",
    }


def _source_folder(root: Path, relative: str) -> Path:
    if type(relative) is not str or "\\" in relative:
        _fail()
    posix = PurePosixPath(relative)
    if (
        posix.is_absolute() or not posix.parts or len(posix.parts) > 6
        or posix.as_posix() != relative
        or any(piece in (".", "..") for piece in relative.split("/"))
        or posix.parts[0] in ("_site", "dashboard", OUTPUT_FOLDER)
    ):
        _fail()
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        _fail()
    if not resolved.is_relative_to(root) or not resolved.is_dir():
        _fail()
    return resolved


def _read_markdown(folder: Path) -> str:
    path = folder / "report.md"
    try:
        if path.is_symlink() or not path.is_file():
            _fail()
        if path.stat().st_size > MAX_REPORT_BYTES:
            _fail()
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        _fail()


def _destination(root: Path, filename: str) -> Path:
    if (
        type(filename) is not str
        or not filename.endswith(".json")
        or not filename[:-5].replace("-", "").replace("_", "").isalnum()
        or len(filename) > 80
    ):
        _fail()
    folder = root / OUTPUT_FOLDER
    candidate = folder / filename
    if (
        not folder.resolve().is_relative_to(root)
        or not candidate.resolve().is_relative_to(root)
        or candidate.exists() or candidate.is_symlink()
    ):
        _fail()
    return candidate


def main(argv: list[str] | None = None) -> int:
    """Offline CLI; experiment choices inherit the *current* model allowlist."""
    parser = argparse.ArgumentParser(description="Offline matched-suite report comparison")
    parser.add_argument("--left-experiment", required=True)
    parser.add_argument("--right-experiment", required=True)
    parser.add_argument("--left-folder", required=True)
    parser.add_argument("--right-folder", required=True)
    parser.add_argument("--output-name", default="model-comparison.json")
    arguments = parser.parse_args(argv)
    try:
        root = Path(".").resolve(strict=True)
        first = load_experiment(select_manifest(arguments.left_experiment), root)
        second = load_experiment(select_manifest(arguments.right_experiment), root)
        first_folder = _source_folder(root, arguments.left_folder)
        second_folder = _source_folder(root, arguments.right_folder)
        # Downloads are untrusted input, not an excuse to follow symlinks.
        for source in (first_folder / "results.json", second_folder / "results.json"):
            if source.is_symlink() or not source.is_file():
                _fail()
        left = _read_report(first_folder / "results.json")
        right = _read_report(second_folder / "results.json")
        safe = compare_models(
            first, left, _read_markdown(first_folder),
            second, right, _read_markdown(second_folder),
        )
        dest = _destination(root, arguments.output_name)
        serialized = json.dumps(
            safe, indent=2, ensure_ascii=False, allow_nan=False,
        ) + "\n"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
    except (ContractError, OSError, ValueError, TypeError):
        print("Offline model comparison failed validation.", file=sys.stderr)
        return 2
    print(f"Sanitized comparison created under {OUTPUT_FOLDER}/ (no inference).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
