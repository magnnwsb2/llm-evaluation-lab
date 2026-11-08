"""Synthetic, offline sensitivity probes for existing objective grading rules.

SDD-001 §5.15. Probe results are NOT actual model responses or a quality
score. No network calls, provider access, public dashboard updates or secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .contracts import ContractError, Experiment, load_experiment
from .model_comparison import _destination, suite_fingerprint
from .run_evaluation import select_manifest
from .scoring import grade

PROBE_IDS = ("outer-whitespace", "case-swap", "append-marker")
_ASCII_CASE_SWAP = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
)


def _probe_texts(baseline: str) -> tuple[str, str, str]:
    return (
        f" {baseline} ",
        baseline.translate(_ASCII_CASE_SWAP),
        baseline + "__PROBE__",
    )


def analyze_assertion_sensitivity(experiment: Experiment) -> dict[str, Any]:
    """Regrade bounded synthetic variants, never any real model responses."""
    if not 1 <= len(experiment.cases) <= 3:
        raise ContractError("mutation probes: invalid case count")
    cases: list[dict[str, Any]] = []
    passed = failed = 0
    for case in experiment.cases:
        baseline = case.assertion.expected
        baseline_result = grade(case, baseline)
        outcomes = []
        for name, variant in zip(PROBE_IDS, _probe_texts(baseline)):
            result = grade(case, variant)
            if result.status == "pass":
                passed += 1
            elif result.status == "fail":
                failed += 1
            else:
                raise ContractError("mutation probes: synthetic scorer returned error")
            outcomes.append({"probe": name, "status": result.status})
        cases.append({
            "id": case.id,
            "assertion_type": case.assertion.type,
            "baseline_guaranteed": case.assertion.type != "regex",
            "baseline_status": baseline_result.status,
            "probes": outcomes,
        })
    return {
        "schema_version": "1.0",
        "kind": "synthetic-objective-assertion-probes",
        "experiment_id": experiment.experiment_id,
        "model": experiment.model,
        "suite_sha256": suite_fingerprint(experiment),
        "case_count": len(cases),
        "probe_count": len(cases) * len(PROBE_IDS),
        "probe_passed": passed,
        "probe_failed": failed,
        "cases": cases,
        "interpretation": "synthetic_rule_sensitivity_not_model_performance",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline synthetic probes of objective assertion sensitivity"
    )
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--output-name", default="objective-probes.json")
    options = parser.parse_args(argv)
    try:
        root = Path(".").resolve(strict=True)
        experiment = load_experiment(select_manifest(options.experiment), root)
        document = analyze_assertion_sensitivity(experiment)
        destination = _destination(root, options.output_name)
        payload = json.dumps(
            document, indent=2, ensure_ascii=False, allow_nan=False
        ) + "\n"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    except (ContractError, OSError, ValueError, TypeError):
        print("Offline mutation probes failed validation.", file=sys.stderr)
        return 2
    print("Synthetic rule-sensitivity report written to ignored local output (no inference).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
