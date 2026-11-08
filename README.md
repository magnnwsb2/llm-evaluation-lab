# LLM Evaluation Lab

A specification-driven, GitHub-first lab for evaluating LLM instruction-following and output quality using **real hosted inference** and deterministic, auditable scoring.

**Current stage:** SDD contracts, offline Python validation and objective scoring are implemented. The Cloudflare Workers AI smoke test has run successfully; the full real-inference evaluation runner, persisted reports and GitHub Pages dashboard are **not yet implemented**.

## What works now

- Validates versioned JSON experiment manifests and synthetic test cases.
- Enforces strict field types, schema versions, safe repository paths, an explicit model allowlist and maximum execution budgets.
- Rejects oversized inputs, unknown fields, duplicate JSON keys/IDs and malformed regular expressions.
- Grades provided responses with three case-sensitive objective rules:
  - **exact**: trims outer whitespace, then compares equality.
  - **contains**: substring matching without case folding.
  - **regex**: Python `re.search` (patterns validated and length-limited).
- Distinguishes `pass`, `fail` and `error` and includes errors in pass-rate denominator.
- Runs offline unit tests and an independent, project-local security gate in GitHub Actions. The development policy follows the separately maintained `ai-engineering-skills` repository (see ADR-0001); the private scanner is not fetched by public CI.

## Project structure

```text
.github/workflows/
  cloudflare-smoke-test.yml  # manual, small real inference; no scoring yet
  offline-ci.yml             # push/PR tests + security scan; no inference
AGENTS.md                    # project development policy
docs/specs/001-llm-evaluation-lab.md
src/llm_eval/
  __init__.py
  __main__.py
  contracts.py               # strict JSON validation
  scoring.py                 # objective answer evaluation
experiments/smoke-001.json
cases/smoke.json
tests/test_contracts.py
tests/test_scoring.py
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

## Future real-inference flow

```text
manually dispatch experiment
  -> validate capped manifest and cases
  -> call approved free-eligible Cloudflare Workers AI model
  -> grade responses
  -> upload results.json and report.md as GitHub Actions artifacts
  -> (later) publish sanitized, public-only dashboard on GitHub Pages
```

**Caution:** The existing manual smoke test verifies a successful nonempty response only; it does **not** measure prompt compliance or publish an evaluation artifact.

## Cost and security

- All hosted inference must be **manual** and remain within the Cloudflare free-plan allocation. Free-tier eligibility can change. Do not enable paid usage or auto-upgrade.
- CI never makes a Cloudflare model request.
- Store Cloudflare credentials exclusively in GitHub Actions **Secrets** (`CLOUDFLARE_API_TOKEN`) and the nonsecret account identifier in **Variables** (`CLOUDFLARE_ACCOUNT_ID`).
- The independent project security gate is heuristic and does not replace the canonical private skill, review or credential rotation. Only synthetic, non-private examples belong in public source files.

## Specifications and acceptance criteria

See [SDD-001](docs/specs/001-llm-evaluation-lab.md) for contracts, risk controls, step sequence and acceptance criteria. Follow [AGENTS.md](AGENTS.md), [ADR-0001](docs/adr/0001-public-ci-security.md), and the canonical **spec-driven-development** and **pre-commit-security** policies before changes.
