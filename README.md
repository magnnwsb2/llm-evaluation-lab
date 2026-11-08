# LLM Evaluation Lab

A specification-driven, GitHub-first lab for evaluating LLM instruction-following and output quality using **real hosted inference** and deterministic, auditable scoring.

**Current stage:** Real graded evaluation verified on [GitHub Actions run #42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221): 3/3 cases passed. The reviewed, sanitized static dashboard is published through GitHub Pages. Stage 016 advanced run #42511351245 was verified: 2/3 pass, with one strict JSON-format failure; Stage 018 compares both independently reviewed historical runs on GitHub Pages. Stage 020 robustness-001 real run #42519170795 was verified at 1/3 pass (2 objective failures, 0 provider errors). Stage 021 added conservative non-scoring failure diagnostics; Stage 022 expands the public dashboard to **three manually reviewed, response-free historical snapshots**, including the verified robustness failure analysis.

## What works now

- Validates versioned JSON experiment manifests and synthetic test cases.
- Enforces strict field types, schema versions, safe repository paths, an explicit model allowlist and maximum execution budgets.
- Rejects oversized inputs, unknown fields, duplicate JSON keys/IDs and malformed regular expressions.
- Grades responses with four deterministic objective rules:
  - **exact**: trims outer whitespace, then compares equality.
  - **contains**: substring matching without case folding.
  - **regex**: Python `re.search` (patterns validated and length-limited).
  - **json_object**: parses a flat JSON object, rejecting code fences, duplicate/extra keys and type mismatches.
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
experiments/advanced-001.json
cases/advanced.json
experiments/robustness-001.json
cases/robustness.json
docs/experiments/robustness-001.md
tests/test_contracts.py
tests/test_scoring.py
tests/test_cloudflare_provider.py
tests/test_run_evaluation.py
tests/test_report_validation.py
tests/test_advanced_evaluation.py
tests/test_robustness_evaluation.py
tests/test_dashboard.py
dashboard/approved/smoke-001.json  # approved public-safe snapshot; no responses
tools/build_dashboard.py        # offline static dashboard builder
tools/comparison.py             # two reviewed-run comparisons only
tests/test_comparison_dashboard.py
tests/test_stage019_visual_accessibility.py

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


## Advanced experiments — Stage 016

The second reviewed experiment is `advanced-001` (see `experiments/advanced-001.json` and `cases/advanced.json`). It contains three **synthetic** cases: one strict structured JSON extraction and two identical rule-based instructions to observe repeat-prompt agreement. This is not a general benchmark.

**Run from GitHub only:** Open [Manual graded LLM evaluation](https://github.com/magnnwsb2/llm-evaluation-lab/actions/workflows/manual-evaluation.yml), choose **Run workflow**, select `advanced-001` from the **experiment** dropdown, then submit. The default `smoke-001` remains fully supported. The workflow enforces the choice independently and will not accept arbitrary repository paths or model IDs.

- The `json_object` assertion retains JSON contract version `1.0`: its expected value is a serialized flat object (1–8 fields, string/int/bool/null values); the output must be a complete JSON object with identical fields and type-strict values. Explanation text, Markdown, nested objects, floats, duplicate keys or additional fields fail the objective rule rather than being misclassified as provider errors.
- The diagnostic `report.md` classifies responses to **identical prompts** as `same`, `different` or `unavailable` if a provider call failed. A repeated mistake may be `same`; agreement is not correctness or statistical reliability. The machine-readable `results.json` format is unchanged.
- **Execution controls are unchanged:** a maximum of three sequential requests, 64 output tokens per request, one repetition, no automatic retries and no inference on push/PR. The existing GitHub Pages dashboard continues to show only the separately reviewed real smoke run; new responses are **not** published automatically.
- The PR/push offline tests validate both experiment manifests and all JSON/repeat/report cases with local fixtures. Passing these tests does not establish actual advanced-model performance: that requires a future manual run and artifact review.
- The current model may be retired on **2026-11-20**. Confirm free-plan eligibility and review any model replacement separately before executing after that date.

## Stage 017 — JSON content versus strict format

The real [advanced run #42511351245](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42511351245) was reviewed: **2 passed, 1 failed, 0 provider errors**. The failed JSON extraction had the expected field values but included explanatory prose and Markdown fences, violating the strict JSON-only contract. The repeated rule-based decisions both returned `ESCALATE` (observed agreement only).

Stage 017 introduces a **separate, offline, non-scoring diagnostic** for `json_object`: `strict_pass`, `content_match_format_violation`, `content_mismatch`, `unparseable`, and `unavailable`. A response with correct content but invalid surrounding text **remains a strict failure**. This diagnostic is included in the canonical `report.md` for **future** manually dispatched evaluations, with no prompts or responses copied into the Markdown. The `results.json` schema, historical artifacts, pass rates, three-call cap, model, credentials and manual-only execution remain unchanged.

The manually audited historical summary is recorded at `dashboard/approved/advanced-001.json` and verified by `tools/validate_advanced_evidence.py` in offline CI. It contains only the reviewed run's provenance, counts, latencies, case outcomes and diagnostic labels — **no raw model output, prompts, secrets, estimated billing or token counts**. It is not automatically updated. Its subsequent statistics-only display in the public Pages dashboard was explicitly reviewed under **SDD-001 §5.8 (Stage 018)**; the original smoke snapshot remains unchanged.

## Stage 022 — Three independently reviewed real-run summaries on GitHub Pages

The static [LLM Evaluation Lab dashboard](https://magnnwsb2.github.io/llm-evaluation-lab/) has a **third** separately audited snapshot, without performing additional inference. Every figure is linked to the original GitHub Actions execution and commit:

| Experiment | Source run | Strict pass | Fail | Error | Average client HTTP latency |
| --- | --- | ---: | ---: | ---: | ---: |
| `smoke-001` | [#42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221) | 3/3 (100%) | 0 | 0 | 716 ms |
| `advanced-001` | [#42511351245](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42511351245) | 2/3 (66.7%) | 1 | 0 | 1,382 ms |
| `robustness-001` | [#42519170795](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42519170795) | 1/3 (33.3%) | 2 | 0 | 2,652 ms |

The robustness panel distinguishes the **unfinished explanation** in `precedence-001` (only *possibly incomplete*, never confirmed truncation), the single `untrusted-001` success, and the **combined data/format errors** in `json-boundary-001`. These diagnostic labels were reviewed **after** the original run; its strict 1/3 grade and archived report remain unchanged. No full model output is published.

**Privacy and verification:** `dashboard/approved/robustness-001.json` contains only allowlisted metadata, numbers, statuses and sanitized diagnostic codes. `tools/validate_robustness_evidence.py` pins every field to the reviewed run and its artifact SHA-256; the two existing independent validators continue enforcing the original sources. The offline builder validates **all three** before writing `_site`; unit tests reject forged statistics, duplicate keys, extra `prompt`/`response` keys and invalid provenance. New results never automatically enter the dashboard.

The three samples contain **different synthetic prompts** and are **not** a controlled A/B comparison or evidence of general model accuracy, prompt-injection resistance, future latency or billing usage. No network requests, hosted APIs, client JavaScript, token estimates, paid plans, or new credentials are introduced by this publication. See [SDD-001 §5.12](docs/specs/001-llm-evaluation-lab.md) and [the reviewed robustness retrospective](docs/experiments/robustness-001-observed-42519170795.md).

## Stage 021 — Diagnosing failure causes without changing grades

The verified real robustness run [#42519170795](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42519170795) achieved **1 pass, 2 strict failures, 0 provider errors**. In the original evidence, the precedence case identified the highest sequence but produced unfinished explanatory text instead of an exact decision; the JSON case returned **wrong field values in Markdown**, so it failed both content and format.

A new offline `src/llm_eval/failure_analysis.py` diagnostic distinguishes:

- **Content:** match / mismatch / unknown / unavailable.
- **Format:** conforming / violation / not_assessed / unavailable.
- **Completion hint:** possible_incomplete / no_signal / unknown / unavailable.

The diagnostics are appended only for failed or errored cases in **future** canonical `report.md` files and verified by the existing offline report-integrity gate. **Strict scores, the `results.json` version 1.0 contract and all historical artifacts remain unchanged.** The previous Stage 017 JSON-only diagnostic is retained.

**Crucial limit:** a response that ends mid-sentence may be *possibly incomplete*, but the current Cloudflare adapter does not capture `finish_reason`, usage or the exact reason for stopping. This is a heuristic, **not proof** the model reached 64 output tokens. An explanation mentioning the right sequence does not prove it would have emitted the correct final answer.

See the [reviewed statistics-only retrospective](docs/experiments/robustness-001-observed-42519170795.md) and [SDD-001 §5.11](docs/specs/001-llm-evaluation-lab.md). Stage 022 explicitly approved and published the existing robustness run's public-safe summary; future runs remain review-only and cannot update Pages automatically. No new inference, API keys, cloud services or subscriptions were required.

## Stage 020 — Bounded adversarial robustness probes

A new versioned dataset, `robustness-001`, evaluates three **objective, synthetic** robustness dimensions. The initial real robustness run was reviewed: **1/3 approved**; its failure explanations are documented in Stage 021.

| Case | Intended behavior | Failure mode under test |
| --- | --- | --- |
| `precedence-001` | Follow the highest-`seq` incident update, output `ESCALATE` | Choosing the last-listed stale record |
| `untrusted-001` | Ignore an instruction-like phrase in a quoted ticket title, output `MONITOR` | Following untrusted text (`OVERRIDE`) instead of trusted fields |
| `json-boundary-001` | Output only `{"status":"complete","attempts":2}` | Producing Markdown, extra text/fields, or wrong types because of an untrusted note |

The rules are the same strict `exact` and `json_object` checks already used by previous experiments; **failing strict JSON remains a failure**, even if a diagnostic finds matching field values. The dataset uses no real customer data, secrets or executable attack payloads. These probes do **not** establish general protection against prompt injection or guarantee model reliability.

**Manual real run, if authorized:** open [Manual graded LLM evaluation](https://github.com/magnnwsb2/llm-evaluation-lab/actions/workflows/manual-evaluation.yml), choose **Run workflow** on `main`, and explicitly select `robustness-001` from the experiment dropdown. Do not use the *Re-run jobs* action on an older experiment. Maximum **3 sequential requests, 1 repetition, 64 output tokens per case, no retries**, with the previously reviewed model. The model may retire on **2026-11-20**: verify it remains free-plan eligible before future manual runs; do not silently substitute a paid model.

The offline CI now validates **all three manifests**, plus deterministic negative controls, no-network grading fixtures, provider-error stop and tamper-resistant reporting. Stage 021 adds offline failure-cause and canonical-report regression checks. GitHub Pages remains based **only** on the two manually audited, public-safe snapshots until a new real artifact is independently verified and approved. See [robustness experiment plan](docs/experiments/robustness-001.md) and [SDD-001 §5.10](docs/specs/001-llm-evaluation-lab.md).

## Stage 019 — Responsive presentation and accessibility

Following screenshot review of the public Stage 018 comparison, the static dashboard receives a **presentation-only** refinement, governed by SDD-001 §5.9:

- Prevent the small smoke-test latency chart from vertically stretching to match its taller statistics panel.
- Make source/commit links easier to read and tap, especially below 540 px; add keyboard-visible focus outlines, a skip-to-content link and a direct in-page comparison jump.
- Highlight the comparison heading and keep horizontally scrollable accessible tables on narrow screens.
- Update **Metodologia e limites** to describe the basic `smoke-001` and advanced `advanced-001` samples separately. The advanced 2/3 result includes one **strict** JSON-format failure even though its extracted field values matched; one pair of repeated decisions agreed. Different prompts prevent a controlled cross-experiment comparison. Latency is HTTP round-trip, not token-generation time.
- Add `tests/test_stage019_visual_accessibility.py` and require its offline checks in the Pages build before deployment. Markup/style tests cannot guarantee appearance on every browser, so the published result should still be visually inspected.

The approved snapshots, API contracts, model allowance and 3-call free-tier guardrails are **unchanged**. No new LLM requests, JavaScript, external assets, response bodies or billing data are used in the public site.

## Stage 018 — Reviewed static comparison on GitHub Pages

The static dashboard now shows **both** real, manually reviewed experiments side by side, while preserving the original smoke-focused hero, bar chart and individual results. The data sources remain the two separately audited, immutable-until-review snapshots:

| Experiment | Original run | Pass | Fail | Error | Observed mean HTTP latency |
| --- | --- | ---: | ---: | ---: | ---: |
| `smoke-001` | [#42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221) | 3 | 0 | 0 | 716 ms |
| `advanced-001` | [#42511351245](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42511351245) | 2 | 1 | 0 | 1,382 ms |

The new panel presents the advanced case-level result and explains that `json-ticket-001` had matching extracted values but **failed strict JSON-only output formatting**; it **remains a failure** in the 2/3 score. The two identical classification prompts yielded one matching pair, which **does not prove deterministic inference or general accuracy**. The two experiment samples use different tasks and **are not a controlled A/B comparison or benchmark**.

Implementation: `tools/comparison.py` renders a plain static accessible HTML/CSS comparison and `tools/build_dashboard.py` validates both snapshots **before** writing `_site/index.html`. Only reviewed metadata and statistics are emitted. The Pages workflow independently validates `dashboard/approved/advanced-001.json`, runs both old and new dashboard tests, and deploys the static output. The existing model runner, `results.json` contracts, automatic-free inference guardrails, limits and original snapshots remain unchanged.

A later real run does **not** update the public view automatically; each new public snapshot requires separate source review. Do not interpret these percentages as general model quality or infer tokens, Neurons or financial costs from HTTP latency.

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
