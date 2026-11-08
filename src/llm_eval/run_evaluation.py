"""Manual-only evaluation runner (SDD-001 §5.2). Never invoked by CI on push/PR."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .contracts import ContractError, Experiment, load_experiment
from .providers.cloudflare import InferenceResult, ProviderError, infer
from .scoring import CaseResult, grade, summarize
from .reproducibility import compare_identical_prompts

MANIFEST = "experiments/smoke-001.json"  # Backward-compatible default.
APPROVED_EXPERIMENTS = {
    "smoke-001": MANIFEST,
    "advanced-001": "experiments/advanced-001.json",
}


def select_manifest(selection: str) -> str:
    """Only reviewed, repository-controlled experiment choices can run inference."""
    if type(selection) is not str or selection not in APPROVED_EXPERIMENTS:
        raise ContractError("evaluation: unapproved experiment selection")
    return APPROVED_EXPERIMENTS[selection]

SAFE_ERROR_CATEGORIES = frozenset({
    "auth", "quota", "rate_limit", "network", "timeout", "provider", "invalid_response",
})


def evaluate(
    experiment: Experiment,
    *,
    account_id: str,
    api_token: str,
    inference: Callable[..., InferenceResult] = infer,
) -> list[CaseResult]:
    """Evaluate sequentially; never send more requests after a provider error."""
    results: list[CaseResult] = []
    stopped_category: str | None = None
    for case in experiment.cases:
        if stopped_category is not None:
            results.append(grade(case, None, error_category=stopped_category))
            continue
        try:
            result = inference(
                experiment, case, account_id=account_id, api_token=api_token
            )
            results.append(grade(case, result.text, latency_ms=result.latency_ms))
        except ProviderError as exc:
            stopped_category = exc.category
            results.append(grade(
                case, None, latency_ms=exc.latency_ms,
                error_category=stopped_category,
            ))
    return results


def build_report(
    experiment: Experiment,
    results: list[CaseResult],
    *,
    run_id: str,
    revision: str,
    timestamp_utc: str,
) -> tuple[dict, str]:
    summary = summarize(results)
    document = {
        "schema_version": "1.0",
        "experiment_id": experiment.experiment_id,
        "model": experiment.model,
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "revision_sha": revision,
        "configuration": {
            "provider": experiment.provider,
            "cases_file": experiment.cases_file,
            "max_cases": experiment.max_cases,
            "repetitions": experiment.repetitions,
            "max_output_tokens": experiment.max_output_tokens,
            "temperature": experiment.temperature,
        },
        "summary": asdict(summary),
        "cases": [asdict(item) for item in results],
    }
    lines = [
        f"# LLM evaluation: {experiment.experiment_id}",
        "",
        f"- Model: `{experiment.model}`",
        f"- GitHub Actions run: `{run_id}`",
        f"- Revision: `{revision}`",
        f"- UTC: `{timestamp_utc}`",
        f"- Pass rate: {summary.passed}/{summary.total} ({summary.pass_rate:.1%})",
        f"- Failed assertions: {summary.failed}; provider errors: {summary.errors}",
        "",
        "| Case | Status | Assertion | Latency (ms) | Error category |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for item in results:
        latency = str(item.latency_ms) if item.latency_ms is not None else "—"
        lines.append(
            f"| {item.id} | {item.status} | {item.assertion_type} | "
            f"{latency} | {item.error_category or '—'} |"
        )
    agreements = compare_identical_prompts(experiment, results)
    if agreements:
        lines.extend([
            "",
            "## Repeated-prompt agreement (diagnostic only)",
            "",
            "| First case | Second case | Outcome |",
            "| --- | --- | --- |",
        ])
        for item in agreements:
            lines.append(
                f"| {item.first_id} | {item.second_id} | {item.outcome} |"
            )
        lines.extend([
            "",
            "Agreement compares response text after trimming outer whitespace.",
            "Same does not imply correct; different does not prove an error.",
            "Unavailable means at least one model call returned a provider error.",
            "This small sample does not estimate statistical reproducibility.",
        ])
    lines += [
        "", "Results are based on objective rules, not a second LLM judge.",
        "Response text is kept only in results.json; no prompts or responses are logged.",
        "Token usage, Neurons and monetary cost are not estimated.",
        "",
    ]
    return document, "\n".join(lines)


def write_report(directory: Path, document: dict, markdown: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "results.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (directory / "report.md").write_text(markdown, encoding="utf-8")


def main() -> int:
    """Entrypoint intentionally has no dynamic model/manifest CLI parameters."""
    output_dir = Path(os.environ.get("EVALUATION_OUTPUT_DIR", "evaluation-output"))
    try:
        selection = os.environ.get("EVALUATION_EXPERIMENT", "smoke-001")
        experiment = load_experiment(select_manifest(selection), Path("."))
        if experiment.experiment_id != selection:
            raise ContractError("evaluation: experiment identity mismatch")
    except ContractError:
        print("Experiment contract validation failed.", file=sys.stderr)
        return 2
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not account_id or not api_token:
        print("Cloudflare runtime configuration missing.", file=sys.stderr)
        return 2
    try:
        results = evaluate(
            experiment, account_id=account_id, api_token=api_token
        )
        document, markdown = build_report(
            experiment, results,
            run_id=os.environ.get("GITHUB_RUN_ID", "manual"),
            revision=os.environ.get("GITHUB_SHA", "unknown"),
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        write_report(output_dir, document, markdown)
    except (ContractError, OSError, ValueError):
        print("Evaluation could not produce a valid report.", file=sys.stderr)
        return 2
    summary = document["summary"]
    print(
        f"Evaluation complete: total={summary['total']} "
        f"pass={summary['passed']} fail={summary['failed']} "
        f"error={summary['errors']}; reports saved."
    )
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
