"""Offline-only CLI. Example: python -m llm_eval validate experiments/smoke-001.json"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .contracts import ContractError, load_experiment


def main() -> int:
    parser = argparse.ArgumentParser(prog="llm_eval")
    parser.add_argument("command", choices=["validate"])
    parser.add_argument("manifest", help="path under experiments/, relative to repository root")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        experiment = load_experiment(args.manifest, args.root)
    except ContractError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 2
    print(
        f"VALID {experiment.experiment_id}: {len(experiment.cases)} cases; "
        f"model={experiment.model}; max_output_tokens={experiment.max_output_tokens}"
    )
    print("Offline validation only; no Cloudflare API call made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
