# LLM Evaluation Lab

A specification-driven, GitHub-first lab for evaluating LLM instruction-following and output quality using **real hosted inference** and deterministic, auditable scoring.

**Current stage:** Real graded evaluation verified on [GitHub Actions run #42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221): 3/3 cases passed. A reviewed, sanitized, offline-built static dashboard is implemented; public Pages availability depends on successful deployment and repository settings.

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
- Validates evaluation artifact integrity offline before upload: recomputes grades and summary, checks run/commit identity, and rejects tampered or inconsistent JSON/Markdown. This is not proof of a real provider call.
- Runs offline unit tests and an independent, project-local security gate in GitHub Actions. The development policy follows the separately maintained `ai-engineering-skills` repository (see ADR-0001); the private scanner is not fetched by public CI.

## Project structure

```text
.github/workflows/
  cloudflare-smoke-test.yml  # manual, small real inference; no scoring yet
  offline-ci.yml             # push/PR tests + security scan; no inference
  manual-evaluation.yml      # manual real inference + scored artifacts
  pages-dashboard.yml        # static Pages build/deploy; no model requests
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
  report_validation.py       # offline artifact integrity gate
experiments/smoke-001.json
cases/smoke.json
tests/test_contracts.py
tests/test_scoring.py
tests/test_cloudflare_provider.py
tests/test_run_evaluation.py
tests/test_report_validation.py
tests/test_dashboard.py
dashboard/approved/smoke-001.json  # approved public-safe snapshot; no responses
tools/build_dashboard.py        # offline static dashboard generator
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
  -> publish only a separately reviewed sanitized summary on GitHub Pages
```

**Real-run evidence:** [Manual graded evaluation run #42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221), reviewed on 2026-11-08: 3 pass, 0 fail/error; measured latencies 492, 1133, 523 ms. This single small sample does not establish general LLM accuracy.

To run a graded experiment: open [Manual graded LLM evaluation](https://github.com/magnnwsb2/llm-evaluation-lab/actions/workflows/manual-evaluation.yml), select **Run workflow** on `main`, and inspect the `graded-evaluation-<run_id>` artifact. The workflow is never triggered by a push or pull request; it makes up to three sequential real inference calls and uploads `results.json` plus `report.md` (7-day retention).

**Model lifecycle:** Cloudflare lists **2026-11-20** as the planned deprecation of `@cf/meta/llama-3.1-8b-instruct-fp8`. Re-evaluate the free-model allowlist before that date; do not silently replace the model in a versioned experiment.

## Report integrity and evidence

The manual workflow runs an additional **offline report-validation step** after generation (including provider-error runs) and before upload. It rejects mismatched run IDs, revisions, altered scores, malformed case records and inconsistent Markdown. The test suite uses synthetic responses only. That real-run evidence has now been inspected; subsequent automatic unit tests remain offline.

The Pages dashboard uses only a manually approved summary snapshot of that run. It never publishes prompt/response bodies, credentials or estimated usage. A new run does **not** automatically refresh the public dashboard.


## Public dashboard — Stage 015

- Reviewed source: `dashboard/approved/smoke-001.json` (run #42504084221, real metrics only, no responses).
- Static builder: `python tools/build_dashboard.py` writes `_site/index.html` and `.nojekyll` using Python standard library; zero external requests and no credentials.
- On an approved `main` change affecting the dashboard, `.github/workflows/pages-dashboard.yml` builds offline and attempts GitHub Pages deployment. It does **not** invoke any LLM. It can also run via `workflow_dispatch`.
- Intended Pages URL, **only after deployment succeeds**: `https://magnnwsb2.github.io/llm-evaluation-lab/`.
- If Pages deploy is unavailable, open **Settings → Pages → Build and deployment → Source → GitHub Actions**, then run `Publish reviewed static dashboard` again. Do not claim the website is live until deployment is confirmed.
- The published 100% pass rate refers to **3 elementary instruction-following checks in one run**, not general model capability. No actual Neuron/token usage or monetary expense was measured.

## Cost and security

- All hosted inference must be **manual** and remain within the Cloudflare free-plan allocation. Free-tier eligibility can change. Do not enable paid usage or auto-upgrade.
- CI never makes a Cloudflare model request.
- Store Cloudflare credentials exclusively in GitHub Actions **Secrets** (`CLOUDFLARE_API_TOKEN`) and the nonsecret account identifier in **Variables** (`CLOUDFLARE_ACCOUNT_ID`).
- The independent project security gate is heuristic and does not replace the canonical private skill, review or credential rotation. Only synthetic, non-private examples belong in public source files.

## Specifications and acceptance criteria

See [SDD-001](docs/specs/001-llm-evaluation-lab.md) for contracts, risk controls, step sequence and acceptance criteria. Follow [AGENTS.md](AGENTS.md), [ADR-0001](docs/adr/0001-public-ci-security.md), and the canonical **spec-driven-development** and **pre-commit-security** policies before changes.
