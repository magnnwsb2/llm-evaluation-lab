# LLM Evaluation Lab

**A zero-financial-cost, specification-driven laboratory for reproducible LLM evaluation.** Built with Python 3.12, GitHub Actions and Cloudflare Workers AI. It grades synthetic prompts with deterministic, auditable rules; validates the original evidence; and publishes only independently reviewed, sanitized summaries to a static GitHub Pages dashboard.

[**View the published dashboard**](https://magnnwsb2.github.io/llm-evaluation-lab/) · [**Technical SDD**](docs/specs/001-llm-evaluation-lab.md) · [**Final audit**](docs/reviews/final-audit-027.md) · [**Verified run ledger**](docs/evidence/run-ledger-027.md) · [**Security policy**](SECURITY.md)

## What is actually running?

| Part | Status and evidence |
|---|---|
| **Active model** | Cloudflare Workers AI **Gemma 4 26B A4B**, `@cf/google/gemma-4-26b-a4b-it`, manually dispatched only |
| **Verified real Gemma test** | [Actions #42527365653](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527365653): `smoke-002`, **3 pass / 0 fail / 0 provider errors**, one request per case, 1291 / 596 / 410 ms measured HTTP latency (mean **765.67 ms**) |
| **Prior Gemma integration failure** | [Actions #42527009736](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527009736): one `invalid_response` attempt; subsequent two cases skipped. After disabling Gemma reasoning mode, the next manually initiated run succeeded. **The precise original failure cause is not proven.** |
| **Historical model** | `@cf/meta/llama-3.1-8b-instruct-fp8`, preserved only for versioned offline validation, no longer available for new manual inference |
| **Public dashboard** | Exactly **three independently reviewed historical Llama `*-001` snapshots**. Gemma results are in the evidence ledger, **not on Pages** pending separate publication review |
| **CI and security** | Offline Python unit tests, independent project-local heuristic credential scanner and static Pages builder; **no inference on push or pull request** |

### Real observations (five inspected artifact ZIPs)

| Model / synthetic suite | Actions run | Strict passed | Failed | Provider errors |
|---|---|---:|---:|---:|
| Llama — `smoke-001` | [#42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221) | 3 | 0 | 0 |
| Llama — `advanced-001` | [#42511351245](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42511351245) | 2 | 1 | 0 |
| Llama — `robustness-001` | [#42519170795](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42519170795) | 1 | 2 | 0 |
| Gemma — `smoke-002`, initial integration | [#42527009736](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527009736) | 0 | 0 | 3 (only one request attempted) |
| Gemma — `smoke-002`, corrected adapter | [#42527365653](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527365653) | 3 | 0 | 0 |

The **same smoke questions** were used for the two models, but runs had different revisions, conditions and timestamps. The `advanced` and `robustness` suites have **different prompts** and cannot be treated as a controlled comparison. Three synthetic cases do **not** establish broad accuracy, safety, model superiority or statistical significance. HTTP latency is not pure model generation time. See the [source-and-hash ledger](docs/evidence/run-ledger-027.md).

## Architecture and boundaries

```text
cases/*.json + versioned experiment manifests (synthetic only)
   |
   +-- pull request / push --> offline tests + security checks --> no provider calls
   |
   +-- explicitly manual workflow_dispatch
         --> one shared execution queue (smoke and graded workflows)
         --> approved free-eligible Gemma 4, bounded REST calls
         --> objective grading + original report-integrity gate
         --> GitHub Actions artifact: results.json + report.md (7 days)
                |
                +-- separate human review / strict allowlist
                       --> sanitized dashboard/approved/*.json
                       --> static HTML/CSS GitHub Pages (no model calls)
```

**Defense in depth:** valid local manifests are not enough to initiate calls: the workflow dropdown allows only active `*-002` suites, the runner independently checks that selection, and the real HTTP adapter refuses the archived model. Both manual workflows share a concurrency group. Maximum **3 sequential calls × 1 repetition × 64 completion tokens**, no retries, redirects or paid fallback.

**The public repo is not a private data vault.** The manually uploaded `results.json` Actions artifact contains **full synthetic model responses** and has seven-day retention; repository viewers may be able to access those artifacts. The **Pages dashboard and job logs** intentionally do **not** expose those responses. Never put credentials, private documents, customer tickets or real personal data into test cases. Read [SECURITY.md](SECURITY.md).

## Run tests locally or in GitHub

Only Python 3.12 and the **standard library** are needed; no Python package installation, API token or Cloudflare account is required for the offline path.

```bash
# From repository root; no provider inference:
PYTHONPATH=src python -m unittest discover -s tests -v

# Validate the six versioned experiment contracts:
PYTHONPATH=src python -m llm_eval validate experiments/smoke-002.json
PYTHONPATH=src python -m llm_eval validate experiments/advanced-002.json
PYTHONPATH=src python -m llm_eval validate experiments/robustness-002.json

# Evaluate how synthetic alterations interact with the existing scoring rules:
PYTHONPATH=src python -m llm_eval.mutation_probes \
  --experiment smoke-002 --output-name objective-probes.json
```

You can also inspect the [offline CI workflow](.github/workflows/offline-ci.yml), which validates all **six** old/new manifests and checks the manually reviewed static evidence.

### Manual real inference (explicit opt-in)

On GitHub, open [Manual graded LLM evaluation](https://github.com/magnnwsb2/llm-evaluation-lab/actions/workflows/manual-evaluation.yml) and select **Run workflow** on **main**, with one reviewed experiment: `smoke-002` (default), `advanced-002` or `robustness-002`. All real inference runs consume Cloudflare's currently available Workers AI allocation and must remain within the **Workers Free** plan. Check your account's free quota and eligibility before running; this repository does not provision or upgrade billing.

The workflow builds canonical `results.json` and `report.md`, validates the report against the chosen original contract and stores the short-lived artifact. **A successful unit test is not a real model observation**, and a successful provider run does not automatically publish new data on Pages.

The older `*-001` manifests are preserved **only for offline historical report validation**. Do not use GitHub's **Re-run jobs** control on old inference workflow executions to attempt an archived model.

## Evaluation methods (objective, small-sample)

- **Scoring:** `exact`, `contains`, bounded `regex`, strict flat `json_object`; each case is `pass`, `fail`, or `error`. Provider errors never become passes.
- **Structured-output diagnostics:** distinguish strict format compliance from matching field values; no non-scoring diagnostic can promote a failed assertion.
- **Failure review:** conservative hints for format/content/possibly incomplete outputs; a truncated-looking answer does **not** establish provider `finish_reason`.
- **Matched-suite model comparison — [Stage 023](docs/experiments/model-comparison-023.md):** validates two complete original run artifacts, checks full prompt/assertion fingerprint and execution settings, and emits a **sanitized descriptive** comparison only.
- **Descriptive statistics — [Stage 024](docs/experiments/statistics-repeatability-024.md):** 1–5 already produced, same-suite/same-model/same-revision reports; observed HTTP latencies, sample standard deviation and raw-text pair agreement. A single run cannot establish repeatability.
- **Synthetic scorer mutation probes — [Stage 025](docs/experiments/objective-mutation-probes-025.md):** change reference outputs offline to test the scoring rules' sensitivity. These are **not LLM robustness or safety measurements**.

Offline tools write locally into ignored `comparison-output/` and do not send data to any provider or publish results.

## Decisions, costs and caveats

- **Architecture/SDD:** [SDD-001](docs/specs/001-llm-evaluation-lab.md), [ADR-0001 — independent public-CI scanner](docs/adr/0001-public-ci-security.md), [ADR-0002 — free-model lifecycle](docs/adr/0002-free-model-lifecycle.md).
- **Security:** [SECURITY.md](SECURITY.md), [AGENTS.md](AGENTS.md), [final risk review](docs/reviews/final-audit-027.md). The private `ai-engineering-skills` repository provides the canonical SDD and staged-scanning policies; the original private scanner is **not executed in public GitHub CI**. The project runs its own separate scanner.
- **Evidence/provenance:** [five inspected run artifacts, commits, grades, latency observations and ZIP SHA-256](docs/evidence/run-ledger-027.md). Raw Actions artifacts expire after **7 days** and may be publicly accessible.
- **Free-tier policy:** Cloudflare documents a Workers Free quota (currently 10,000 Neurons per day); free-plan compatibility and remaining quota can change. No paid-only models, subscriptions, credits, servers or billing upgrades are part of this project. **No statement here independently certifies the actual account's post-run invoice.**
- **History:** [Stage 001–026 chronological README (dated archive)](docs/history/readme-pre027-2026-11-08.md). It contains historical instructions and **must not be used instead of this current README**.

**Roadmap:** Stages **001–027** have been implemented with SDD change control; this is the final planned consolidation stage. Future model tests, larger benchmark datasets or an additional Gemma public dashboard snapshot require a **new explicit, reviewed scope**.

MIT License · Python 3.12 · GitHub-only CI and static publication · Synthetic data only.
