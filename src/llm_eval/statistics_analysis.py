"""Offline descriptive latency statistics and repeated-output observations.

SDD-001 §5.14. No provider calls, credentials, statistical significance
claims, probability forecasts, raw responses or public Pages publication.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

from .contracts import ContractError, Experiment, load_experiment
from .model_comparison import (
    _destination, _read_markdown, _source_folder, suite_fingerprint,
)
from .report_validation import _read_report, validate_reports
from .reproducibility import compare_identical_prompts
from .run_evaluation import select_manifest
from .scoring import CaseResult

MAX_RUNS = 5
ANALYSIS_KIND = "descriptive-repeatability-observation"


def _reject() -> None:
    raise ContractError("offline statistics: invalid or inconsistent source evidence")


def latency_statistics(values: list[int | None]) -> dict[str, int | float | None]:
    """Population of *observed HTTP timings*; sample deviation for n >= 2."""
    if type(values) is not list or any(
        value is not None and (type(value) is not int or value < 0)
        for value in values
    ):
        _reject()
    observed = sorted(value for value in values if value is not None)
    count = len(observed)
    return {
        "observed_count": count,
        "minimum_ms": observed[0] if count else None,
        "maximum_ms": observed[-1] if count else None,
        "mean_ms": round(statistics.mean(observed), 3) if count else None,
        "median_ms": round(statistics.median(observed), 3) if count else None,
        "sample_stddev_ms": round(statistics.stdev(observed), 3) if count >= 2 else None,
    }


def analyze_runs(
    experiment: Experiment,
    sources: list[tuple[dict, str]],
) -> dict[str, Any]:
    """Analyze 1–5 independently validated reports from identical code+suite.

    One-run latency figures can be descriptive; repeatability is not measurable
    with only one run. Raw outputs are used *only* for equality counting.
    """
    if type(sources) is not list or not 1 <= len(sources) <= MAX_RUNS:
        _reject()

    checked: list[tuple[dict, list[CaseResult]]] = []
    known_ids: set[str] = set()
    common_revision: str | None = None
    for source in sources:
        if (
            type(source) is not tuple or len(source) != 2
            or type(source[0]) is not dict or type(source[1]) is not str
        ):
            _reject()
        document, markdown = source
        try:
            run_id = document["run_id"]
            revision = document["revision_sha"]
            validate_reports(
                experiment, document, markdown, run_id=run_id, revision=revision
            )
        except (KeyError, TypeError, AttributeError, ValueError, RecursionError):
            _reject()
        if run_id in known_ids:
            _reject()
        known_ids.add(run_id)
        if common_revision is None:
            common_revision = revision
        elif common_revision != revision:
            _reject()
        results = [
            CaseResult(
                record["id"], record["status"], record["assertion_type"],
                record["latency_ms"], record["response"], record["error_category"]
            )
            for record in document["cases"]
        ]
        checked.append((document, results))

    run_summaries = []
    all_latencies: list[int | None] = []
    for document, results in checked:
        observed = [case.latency_ms for case in results]
        all_latencies.extend(observed)
        same_prompt = compare_identical_prompts(experiment, results)
        run_summaries.append({
            "run_id": document["run_id"],
            "timestamp_utc": document["timestamp_utc"],
            "revision_sha": document["revision_sha"],
            "summary": dict(document["summary"]),
            "latency": latency_statistics(observed),
            "identical_prompt_pairs": [
                {
                    "first_id": pair.first_id,
                    "second_id": pair.second_id,
                    "outcome": pair.outcome,
                }
                for pair in same_prompt
            ],
        })

    case_observations = []
    for index, case in enumerate(experiment.cases):
        observations = [results[index] for _, results in checked]
        valid_responses = [
            result.response.strip()
            for result in observations
            if result.status != "error" and result.response is not None
        ]
        comparable_pairs = 0
        agreeing_pairs = 0
        for first, second in combinations(valid_responses, 2):
            comparable_pairs += 1
            if first == second:
                agreeing_pairs += 1
        case_observations.append({
            "id": case.id,
            "pass": sum(result.status == "pass" for result in observations),
            "fail": sum(result.status == "fail" for result in observations),
            "error": sum(result.status == "error" for result in observations),
            "latency": latency_statistics([r.latency_ms for r in observations]),
            "comparable_response_pairs": comparable_pairs,
            "agreeing_response_pairs": agreeing_pairs,
            "response_pair_agreement_rate": (
                round(agreeing_pairs / comparable_pairs, 6)
                if comparable_pairs else None
            ),
        })

    return {
        "schema_version": "1.0",
        "kind": ANALYSIS_KIND,
        "experiment_id": experiment.experiment_id,
        "model": experiment.model,
        "suite_sha256": suite_fingerprint(experiment),
        "revision_sha": common_revision,
        "run_count": len(checked),
        "repeatability": (
            "not_measurable_single_run" if len(checked) == 1
            else "observed_pairs_only_not_general_reliability"
        ),
        "runs": run_summaries,
        "latency": latency_statistics(all_latencies),
        "cases": case_observations,
        "interpretation": "descriptive_only_small_sample_no_significance",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline descriptive statistics of existing graded LLM reports"
    )
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--folders", nargs="+", required=True)
    parser.add_argument("--output-name", default="statistics-observation.json")
    options = parser.parse_args(argv)
    try:
        if not 1 <= len(options.folders) <= MAX_RUNS:
            _reject()
        root = Path(".").resolve(strict=True)
        experiment = load_experiment(select_manifest(options.experiment), root)
        sources = []
        for relative in options.folders:
            folder = _source_folder(root, relative)
            report_file = folder / "results.json"
            if report_file.is_symlink() or not report_file.is_file():
                _reject()
            sources.append((_read_report(report_file), _read_markdown(folder)))
        report = analyze_runs(experiment, sources)
        destination = _destination(root, options.output_name)
        payload = json.dumps(
            report, indent=2, ensure_ascii=False, allow_nan=False
        ) + "\n"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as target:
            target.write(payload)
    except (ContractError, OSError, ValueError, TypeError):
        print("Offline statistical analysis failed validation.", file=sys.stderr)
        return 2
    print("Sanitized statistical observation written to ignored local output (no inference).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
