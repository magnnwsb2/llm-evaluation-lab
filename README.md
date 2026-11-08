# LLM Evaluation Lab

A specification-driven, GitHub-first lab for evaluating LLM instruction-following and output quality using **real hosted inference** and deterministic, auditable scoring.

**Current stage:** SDD contracts, offline scoring and a guarded Cloudflare Workers AI adapter are implemented. The original manual smoke test succeeded; a manual-only graded evaluation runner and GitHub Actions artifacts are implemented, but **no real graded run has been verified yet**. GitHub Pages remains future work.

## What works now

- Validates versioned JSON experiment manifests and synthetic test cases.
- Enforces strict field types, schema versions, safe repository paths, an explicit model allowlist and maximum execution budgets.
- Rejects oversized inputs, unknown fields, duplicate JSON keys/IDs and malformed regular expressions.
- Grades provided responses with three case-sensitive objective rules:
  - **exact**: trims outer whitespace, then compares equality.
  - **contains**: substring matching without case folding.
  - **regex**: Python `re.search` (patterns validated and length-limited).
- Distinguishes `pass`, `fail` and `error` and includes errors in pass-rate denominator.
- Provides a guarded Cloudflare Workers AI adapter (`src/llm_eval/providers/cloudflare.py`) with one request, 45-second timeout, 64 KiB response cap, no redirects or retries, sanitized failure categories, and measured client-observed latency. **No automatic inference is enabled.**
- Runs offline unit tests and an independent, project-local security gate in GitHub Actions. The development policy follows the separately maintained `ai-engineering-skills` repository (see ADR-0001); the private scanner is not fetched by public CI.

## Project structure

```text
.github/workflows/
  cloudflare-smoke-test.yml  # manual, small real inference; no scoring yet
  offline-ci.yml             # push/PR tests + security scan; no inference
  manual-evaluation.yml      # manual real inference + scored artifacts
AGENTS.md                    # project development policy
docs/specs/001-llm-evaluation-lab.md
src/llm_eval/
  __init__.py
  __main__.py
  contracts.py               # strict JSON validation
  scoring.py                 # objective answer evaluation
  providers/
    cloudflare.py             # guarded real-inference adapter; explicit call only
  run_evaluation.py          # manual runner, grading, JSON/Markdown reports
experiments/smoke-001.json
cases/smoke.json
tests/test_contracts.py
tests/test_scoring.py
tests/test_cloudflare_provider.py
tests/test_run_evaluation.py
```

## Running entirely through GitHub

1. Open [Actions / Offline contracts and security](https://github.com/magnnwsb2/llm-evaluation-lab/actions/workflows/offline-ci.yml).
2. Review automatic checks from pushes and pull requests, or choose **Run workflow** to trigger manually.
3. The example contract is validated without Cloudflare API credentials or model requests.

If working in an ephemeral development environment, the equivalent offline commands are:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m llm_eval validate experiments/smoke-001.json
```

No local workstation is required for normal project operation.

## Manual real-inference flow

```text
manually dispatch experiment
  -> validate capped manifest and cases
  -> call approved free-eligible Cloudflare Workers AI model using the tested adapter
  -> grade responses
  -> upload results.json and report.md as GitHub Actions artifacts
  -> (later) publish sanitized, public-only dashboard on GitHub Pages
```

**Caution:** The original smoke test verifies a nonempty response only. The new workflow is implemented but has **not yet been manually dispatched and validated against Cloudflare**. Only an actual manual run and artifact inspection can establish real scoring evidence.

To run a graded experiment: open [Manual graded LLM evaluation](https://github.com/magnnwsb2/llm-evaluation-lab/actions/workflows/manual-evaluation.yml), select **Run workflow** on `main`, and inspect the `graded-evaluation-<run_id>` artifact. The workflow is never triggered by a push or pull request; it makes up to three sequential real inference calls and uploads `results.json` plus `report.md` (7-day retention).

**Model lifecycle:** Cloudflare lists **2026-11-20** as the planned deprecation of `@cf/meta/llama-3.1-8b-instruct-fp8`. Re-evaluate the free-model allowlist before that date; do not silently replace the model in a versioned experiment.

## Cost and security

- All hosted inference must be **manual** and remain within the Cloudflare free-plan allocation. Free-tier eligibility can change. Do not enable paid usage or auto-upgrade.
- CI never makes a Cloudflare model request.
- Store Cloudflare credentials exclusively in GitHub Actions **Secrets** (`CLOUDFLARE_API_TOKEN`) and the nonsecret account identifier in **Variables** (`CLOUDFLARE_ACCOUNT_ID`).
- The independent project security gate is heuristic and does not replace the canonical private skill, review or credential rotation. Only synthetic, non-private examples belong in public source files.

## Specifications and acceptance criteria

See [SDD-001](docs/specs/001-llm-evaluation-lab.md) for contracts, risk controls, step sequence and acceptance criteria. Follow [AGENTS.md](AGENTS.md), [ADR-0001](docs/adr/0001-public-ci-security.md), and the canonical **spec-driven-development** and **pre-commit-security** policies before changes.
