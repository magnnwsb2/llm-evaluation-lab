# SDD-001 — LLM Evaluation Lab

**Status:** Initial baseline (v0.1)  
**Repository:** `magnnwsb2/llm-evaluation-lab`  
**Date:** 2026-11-08  
**Owner:** Repository maintainer  
**Scope:** MVP — reproducible, low-cost evaluation of hosted LLMs

## 1. Context and evidence

A manual GitHub Actions smoke test at `.github/workflows/cloudflare-smoke-test.yml` has already proved that GitHub Actions can authenticate to Cloudflare Workers AI REST and obtain a nonempty answer from `@cf/meta/llama-3.1-8b-instruct-fp8`.

**What is not yet proven:** exact prompt compliance, repeatability, evaluation scoring, network latency, unit consumption, output persistence, and public dashboard publication. A successful smoke test must not be represented as an evaluation benchmark.

The development policy derives from:
- `magnnwsb2/ai-engineering-skills/skills/spec-driven-development/SKILL.md`
- `magnnwsb2/ai-engineering-skills/skills/pre-commit-security/SKILL.md`
- `magnnwsb2/ai-engineering-skills/AGENTS.md`

## 2. Goal and user stories

**Goal:** build a reproducible LLM evaluation system for software-engineering experiments, with real hosted inference, objective checks, and inspectable evidence, entirely controlled through GitHub.

As a maintainer, I can:
1. Version prompts, test cases, model identifiers and expected outcomes in the repository.
2. Run **offline** checks on every code change without network access or model invocation.
3. Explicitly dispatch a **small real-inference** evaluation through GitHub Actions.
4. Compare outcomes by test case and experiment, preserving configuration and timestamps.
5. Publish only approved, sanitized summaries as a static dashboard on GitHub Pages, at a later milestone.

## 3. In scope / out of scope

### MVP in scope
- Python 3.12, standard-library first; deterministic unit tests.
- GitHub repository as source of truth; GitHub Actions as CI and explicit inference runner.
- Cloudflare Workers AI REST API as the real-inference provider.
- JSON experiment manifests, JSON test cases and structured JSON results.
- Rule-based grading for exact, substring and regex criteria.
- Human-readable Markdown summary and machine-readable JSON artifact.
- Cost guardrails, redacted errors, test evidence and documented decisions.

### Out of scope for MVP
- Paid cloud services, paid models, billing upgrades or workloads that require local devices.
- Automatically scheduled inference or LLM calls on PR/push.
- Autonomous changes to infrastructure, secrets, spending or production systems.
- Public dynamic backend, persistent hosted database, vector store, RAG or AI agents.
- A second LLM acting as judge; this requires a separate specification and budget.
- Guaranteeing exact model outputs or claiming the model is deterministic.

## 4. Architecture and data flow

```text
GitHub repository (specs / JSON cases / evaluation code)
                    |
                    +--> push / PR --> offline CI --> unittest + security gate
                    |
                    +--> manual workflow_dispatch
                              |
                        validate manifest
                              |
                       enforce local limits
                              |
                       Workers AI REST API
                              |
                      normalize response
                              |
                      evaluate objective rules
                              |
                     results.json + report.md
                              |
                     GitHub Actions artifacts
                              |
                (later) sanitized GitHub Pages
```

The GitHub Actions runner is ephemeral; **no persistent local machine** or paid host is required. Secrets are read at runtime, never stored in artifacts.

## 5. External interfaces and security

- `CLOUDFLARE_API_TOKEN`: GitHub Actions **repository secret**; used only in the `Authorization: Bearer` header, never logged.
- `CLOUDFLARE_ACCOUNT_ID`: GitHub Actions **repository variable**; non-secret account identifier.
- Endpoint: `POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}`
- Start with proven model `@cf/meta/llama-3.1-8b-instruct-fp8` while it remains free-plan eligible; model eligibility is checked before adding alternatives.
- Token must be account-scoped and minimally privileged.
- Never commit actual `.env`, secrets, proprietary prompts, personal data or raw third-party documents.
- CI permissions default to `contents: read`; write permissions require an explicit justified step.
- Error messages must exclude request headers, tokens and sensitive response content.
- No prompt/response bodies exposed on public Pages unless test data are specifically approved as public.

### 5.1 Provider adapter contract — Stage 011

The initial adapter lives in `src/llm_eval/providers/cloudflare.py`, with no automatic invocation on import and no credentials in code. It is called only by an explicitly authorized manual runner in a subsequent stage.

- Inputs: a previously validated `Experiment` and one of its `Case` objects, an account identifier and API token supplied at runtime by the caller.
- Defensively check the allowlisted model, provider, maximum 3 cases, exactly 1 repetition, maximum 64 output tokens, prompt size and case membership **again before network access**. Dataclasses constructed directly are not automatically trusted.
- Send a **single**, non-streaming JSON `POST` with `messages`, `max_tokens`, `temperature` and `stream: false`; no retries, fallback, parallelism or scheduled invocation.
- Use an allowlisted HTTPS host and strict account-ID syntax, reject HTTP redirects (do not forward Authorization), set a 45-second request timeout and cap response bytes at 64 KiB.
- Accept only the Cloudflare JSON envelope `{"success": true, "result": {"response": "<text>"}}` where the response is a nonempty string. Reject malformed or oversized replies. Never assume provider usage data are guaranteed.
- Return response text with **client-observed HTTP latency in milliseconds**; this is not token generation time.
- Raise a sanitized `ProviderError` with a category compatible with `scoring.ERROR_CATEGORIES` on failed calls; include optional measured latency but do **not** expose raw request headers, tokens, provider error bodies or arbitrary exception strings.
- Map HTTP 401/403 to `auth`, 429 with Cloudflare error code 3036 to `quota`, other 429 to `rate_limit`, 408/504 and socket timeouts to `timeout`, transport failures to `network`, malformed successful bodies to `invalid_response` and other HTTP failures to `provider`. A paid-model restriction (Cloudflare error 5035) is `provider`, not a prompt failure.
- All tests inject fake responses or local errors; GitHub push/PR workflows **must never** invoke real inference.
- No claim of full AC-04, AC-05, AC-08 or AC-09 until the later manual evaluation workflow provides real evidence.

**Model lifecycle:** Cloudflare's model documentation currently lists **2026-11-20** as the planned deprecation date of `@cf/meta/llama-3.1-8b-instruct-fp8`. Keep the current known-working model solely for this compatible adapter step; evaluate a free-eligible replacement and update the allowlist/spec **before** the deprecation, under a separately reviewed change. Never silently swap models.

### 5.2 Manual evaluation runner — Stage 012

- Entry point: `python -m llm_eval.run_evaluation`, invoked **only** from `.github/workflows/manual-evaluation.yml` with `workflow_dispatch` (no push, pull request, cron, retry, or matrix).
- The dispatch manifest is a fixed allowlisted repository path `experiments/smoke-001.json`. The workflow uses `contents: read`, `persist-credentials: false`, `timeout-minutes: 5`, `concurrency` with `cancel-in-progress: false`, and GitHub Actions secret/variable injected as environment variables.
- Runner validates all inputs before the first network request. For at most 3 cases, call the existing guarded adapter once per case and grade the actual response with `grade()`. On `auth`, `quota`, `rate_limit`, `network`, `timeout`, `provider` or `invalid_response`, mark the case `error` and **stop making further requests**; any remaining cases receive `error` with the same sanitized category, without an attempted call. No fallback or retries.
- Save `results.json` and `report.md` to a dedicated directory. Include schema version, experiment/model IDs, GitHub run ID, UTC timestamp, revision SHA, safe configuration, per-case status, measured latency, and the summary. Only public synthetic prompts and model responses may appear in these private-to-run artifacts; **do not publish them to GitHub Pages**. Responses are not echoed in CI logs.
- Reports are emitted even if provider inference fails; the CLI returns a nonzero exit code for provider errors, and the artifact upload uses `if: always()` with `if-no-files-found: error` and limited retention. A prompt compliance `fail` is an evaluation result, not a CI infrastructure error.
- Offline tests exercise success, prompt noncompliance, sanitized provider failure, request stopping and report serialization with fake transports; no real inference on CI.
- Stage 012's implementation and green offline CI do not by themselves establish AC-04, AC-05 or AC-08: one **explicitly dispatched** real workflow and inspected artifact are required.

### 5.3 Report-integrity gate — Stage 013

Before the manual-only evaluation workflow uploads any result artifact, an **offline validator** checks the produced `results.json` and `report.md` against the versioned experiment/case contracts. This is a compatible strengthening of SDD-001 §§5.2, 6–9, not permission to design or publish the Pages dashboard before a verified real experiment.

- Validator entry point: `python -m llm_eval.report_validation`; it does not import or call any real provider and receives **no Cloudflare token**. The original evaluation workflow remains `workflow_dispatch` only.
- Reject missing/oversized/malformed JSON, duplicate keys, unexpected fields, nonfinite numbers, inconsistent UTC timestamp, invalid or mismatched commit SHA/run ID, or configuration conflicting with the validated manifest.
- Enforce exact case order/IDs and assertion types, sanitize and strictly type status, error categories and latency, and independently **re-grade** each available response from its expected assertion. An `error` stops future inference: subsequent cases must have `error` with the same category, a null response and null latency.
- Recompute summary counts/pass rate from case records and compare the rendered Markdown against the canonical report generator; never accept external claims of successful evaluation without internally consistent evidence.
- A successful validation means a report is structurally internally consistent; **it does not prove** that the provider call really happened or that the data are trustworthy without inspecting the actual manual run and its logs. Never silently substitute synthetic fixture data for a real-run artifact.
- Validate after the inference step even if it exits with a provider error, before the upload step. The artifact upload remains limited to 7-day retention and should not expose response text in logs. Unit tests run on GitHub PR/push exclusively with fabricated responses.
- As specified in §12, no final dashboard layout or public publication decisions are made until a real graded manual-run artifact is available and inspected.

### 5.4 Public static dashboard — Stage 015

Stage 015 is authorized after inspecting **real** manually dispatched run [42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221), commit `61fd68ae0d51d646e33db13c8187f3b6351e8220`, UTC `2026-11-08T17:16:02+00:00`; its validated artifact contained 3 passes, 0 fails/errors and case latencies 492, 1133, 523 ms. This is **one small instruction-following sample**, not a general model performance benchmark.

- Commit only a reviewed, public-safe **summary snapshot** derived from the specific real run. It may include run ID, revision, UTC timestamp, experiment/model identifiers, counts, assertion categories, outcome and latencies. **Never include prompt text, model responses, credentials, account ID, raw provider output, original private artifact or unverified cost/token estimates.** Link back to the Actions run as provenance.
- Generate a self-contained static dashboard (HTML/CSS/JavaScript or standard-library Python build); no external APIs, client tracking, hosted DB, external JavaScript/CDN, fonts, or Cloudflare requests. Display sample size, pass/fail/error, pass rate and observed client roundtrip latency with clear methodology and limitations. Use text-only DOM insertion for data fields, never untrusted innerHTML.
- Require an **offline allowlist validator** for the snapshot, checking schema/fields/types, fixed public-approved provenance for the initial snapshot, consistent summary, case order, exact sample statistics and compatible manifest/case references. Reject leaked response/prompt fields. Test both rendering and rejection of malformed/sensitive snapshots in the normal no-inference CI.
- Publish only the generated static site directory through GitHub Pages Actions with a build job using `contents: read` and a separate deploy job using `pages: write` / `id-token: write` and `github-pages` environment. Publishing may trigger on a main-branch change **only because it makes zero model calls**; manual dispatch is also permitted. Avoid using automatic artifact downloads from private/manual inference runs for public deployment.
- GitHub Pages repository settings may require a maintainer to select **GitHub Actions** as the Pages source; do not assert the live URL works before a deployment completes. Keep the original manual inference workflow unchanged except separate maintenance fixes. Site build must run and be tested offline even if Pages is not yet enabled.
- **No refresh of the public snapshot automatically after later inference.** Each future snapshot requires manual review and an SDD-compatible approval step. No claims of paid usage, guaranteed free account balance or general benchmark performance.

### 5.5 Static dashboard visual regression remediation — Stage 015.1

The first deployed GitHub Pages dashboard displayed correct numerical results but the user's visual inspection identified invisible latency bars, joined statistic labels and cramped table columns. The root cause is an unclosed CSS `linear-gradient(` call in the inline stylesheet that can invalidate following CSS rules; this is a rendering defect, not a change in the underlying experiment.

- Correct CSS syntax and strengthen responsive two-column statistics, visible latency bars and legible tabular padding/headers at desktop and narrow widths.
- Add offline rendering regression checks that reject unbalanced CSS grouping, verify vital CSS/HTML structural hooks and preserve the reviewed source snapshot, counts, case latencies and GitHub Actions provenance.
- Remain compatible with §5.4: static Python standard-library generation; no external assets, scripts, new providers, inference, automatic snapshot updates, credentials or billing claims.
- Require the existing no-inference PR test/security checks and successful Pages build/deploy before declaring the visual fix published. Automated structural tests do **not** replace actual cross-device browser inspection.

### 5.6 Advanced objective evaluation — Stage 016

After verification of the public dashboard and Stage 015.1 rendering corrections, introduce a **second, explicitly selected** three-case experiment that exercises structured extraction, strict formatting and repeated-prompt agreement. The original smoke experiment, results schema `1.0`, public dashboard snapshot and all historical run evidence remain unchanged.

**Compatible contract addition (`schema_version: "1.0"`):**
- The assertion vocabulary gains `json_object`. As with existing assertions, `assertion.expected` remains a **string**: a serialized, flat JSON object with 1–8 unique, simple alphanumeric/underscore field names and values of type string, integer, boolean or null. Arrays, nested objects, floating-point/non-finite values, empty object, duplicate keys and unbounded objects are invalid. Validate expected values offline before calling a model.
- The model response must consist **only of a JSON object** (allow leading/trailing whitespace, but no Markdown fences or explanations). Parse with duplicate-key and non-finite rejection; require exactly the expected field set and type-strict value equality (`true` differs from `1`, extra fields fail). A malformed response is an objective `fail`, **not** an API transport error. Do not log raw response or exception text.
- The existing `exact`, `contains`, `regex` semantics and case/result dataclasses stay stable; all previously valid files, the old manual workflow default, the original dashboard and report validator continue to work. Do not silently introduce schema `2.0` or change existing evaluations.

**Second manual experiment:**
- Add `experiments/advanced-001.json` and `cases/advanced.json` with exactly three public synthetic cases: one extraction to strict JSON, then two **identical** rule-based classification prompts evaluated with `exact`. The repeated prompt is deliberately sent as two individual sequential cases, **not** an increase in the `repetitions` cap.
- `workflow_dispatch.inputs.experiment` must be a GitHub Actions **choice** with explicit allowed values `smoke-001` (default) and `advanced-001`. Runtime validation must independently reject any unknown selection **before credentials or network are used**, not accept arbitrary manifest paths, models, user prompts, output directories or case counts. Both the manual runner and the offline report-integrity gate use the same allowlisted selection. This is not an API for arbitrary remote inference.
- At most **3** sequential calls, **1** per declared case, **64** output tokens per call, **0** retries or parallelism, unchanged free-model allowlist, manual-only invocation and stop-on-first-provider-error. PR/push CI, dashboard builds and unit tests make **zero** real AI requests.
- In the human-readable `report.md`, compute a separate reproducibility observation for identical prompts: `same`, `different` or `unavailable` (if one or both calls received a provider error), comparing strings after trimming outer whitespace. Include number of observed pairs and a note that agreement is **not** correctness, statistical reproducibility, or guaranteed determinism. This is a small diagnostic, not a new benchmark. The JSON results contract remains unchanged and records each response and score as before; no responses are added to Markdown, Actions logs or public Pages.
- Independently validate any advanced report with the existing report-integrity gate and new negative offline tests (forged status, malformed JSON, duplicate keys, type confusion, case order, provider-error stop, manifest selection). Do not treat tested fakes as real model evidence. No new run is declared successful until an actual authorized `workflow_dispatch` is executed and the artifact inspected.
- Avoid publishing the new evaluation on GitHub Pages until its real run is inspected and a **separate reviewed, public-safe summary snapshot** is approved. The current Pages dashboard continues to show only the verified smoke run.
- Model `@cf/meta/llama-3.1-8b-instruct-fp8` is documented as scheduled for retirement on 2026-11-20. This stage does not silently change the model. Before a future manual run beyond its availability, review a **free-plan eligible** replacement under a separate SDD change. Do not use paid-only models or request billing setup.

**Stage 016 acceptance:** green credential-free CI with old and new manifest validation; deterministic tests for strict JSON extraction and same/different/unavailable repeat diagnostics; selector injection rejected offline; report-integrity regrading and cost ceilings preserved. Real inference and a public advanced-performance claim are separate evidence steps.

## 6. Versioned data contracts (proposed v1)

All JSON documents use UTF-8. Unknown required fields fail validation; optional fields must use the documented types. Never silently coerce types.

### Experiment manifest — `experiments/<id>.json`

```json
{
  "schema_version": "1.0",
  "experiment_id": "smoke-001",
  "description": "Basic instruction-following checks",
  "provider": "cloudflare-workers-ai",
  "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
  "cases_file": "cases/smoke.json",
  "max_cases": 3,
  "repetitions": 1,
  "max_output_tokens": 64,
  "temperature": 0
}
```

- `experiment_id`: unique slug (`[a-z0-9][a-z0-9-]{2,63}`); not a path.
- `cases_file`: relative allowlisted path under `cases/`; reject `..`, absolute paths and symlinks escaping the repository.
- `model`: explicit free-tier allowlist; never accept an arbitrary dispatch-provided model string.
- The above caps are **hard upper limits for MVP**; changing them requires a spec revision and cost review.

### Test cases — `cases/<name>.json`

```json
{
  "schema_version": "1.0",
  "cases": [
    {
      "id": "greeting-001",
      "prompt": "Reply with exactly: OK",
      "assertion": {
        "type": "exact",
        "expected": "OK"
      }
    }
  ]
}
```

- Case IDs are unique within a file; prompts must be public, synthetic and nonempty.
- `assertion.type`: `exact`, `contains`, `regex` or additive `json_object`; `expected` is a nonempty string (a serialized strict JSON object for `json_object`).
- `exact` compares after trimming leading/trailing whitespace; `contains` and `regex` use case-sensitive matching.
- Regular expressions use Python `re.search`; cap pattern length and reject invalid patterns before invoking a model.
- Prompt length cap: 1,000 Unicode characters; case count cap: 3 in MVP.
- Tests with unsuitable expected output must be flagged rather than automatically declared correct.

### Evaluation result — `results.json`

```json
{
  "schema_version": "1.0",
  "experiment_id": "smoke-001",
  "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
  "run_id": "github-actions-run-id",
  "timestamp_utc": "2026-11-08T00:00:00Z",
  "summary": {
    "total": 1,
    "passed": 1,
    "failed": 0,
    "errors": 0,
    "pass_rate": 1.0
  },
  "cases": [
    {
      "id": "greeting-001",
      "status": "pass",
      "assertion_type": "exact",
      "latency_ms": 1234,
      "response": "OK",
      "error_category": null
    }
  ]
}
```

**Important:** Values in this example are illustrative contract samples, **not measured results**. `latency_ms` records client-observed request/response time (not model-only latency) and can be `null` on error. `status` is one of `pass`, `fail`, `error`. `error_category` must be a sanitized machine code. `pass_rate` is `passed / total` when `total > 0` and must not hide errors. Raw token usage and neuron consumption must not be fabricated; report only if reliably provided by the API or verified from account telemetry.

## 7. Scoring and reproducibility

- Score each evaluated case as pass/fail/error independently.
- Only `pass` contributes to the pass numerator; errors count in the denominator.
- Store code revision SHA, experiment identifier, model identifier, UTC time, configuration and CI run ID.
- A `temperature` of zero improves repeatability but does **not** guarantee identical responses.
- No speculative "accuracy", "hallucination rate", provider token accounting or monetary amounts.
- Keep model outputs separate from expected answers and from evaluation assertions.

## 8. Cost and execution safety (non-negotiable)

- The user must **not be required to pay**. No paid-plan upgrade, billing method, paid-only model or paid AI Gateway credits.
- As of 2026-11-08, Cloudflare Workers AI's Free plan has a daily free allocation of **10,000 Neurons**; limits and eligibility can change. The free plan rejects excess usage; never automatically switch to Paid.
- The `@cf/moonshotai/kimi-k2.7-code` model shown in the Cloudflare onboarding example is **paid-plan restricted** and must not be used for this MVP.
- Real inference runs are **manual only**. No scheduled runs, automatic retries, parallel batches or loops beyond declared caps.
- Initial limit: max 3 cases × 1 repetition × 64 output tokens per manual run. One REST call per case, except a documented one-time retry for transient failures **only after a future approved revision**.
- On quota/rate-limit/auth failures, stop safely and report sanitized diagnostics; do not fall back to a billable model.
- Check Cloudflare model eligibility and free-tier quota before extending the allowlist.
- Offline CI must make zero real model requests.
- No evidence of a charge is not proof that a financial account can never incur one; monitor provider settings and usage.

Reference: https://developers.cloudflare.com/workers-ai/platform/pricing/ (checked 2026-11-08).

## 9. Testing and acceptance criteria

| ID | Criterion | Evidence required |
| --- | --- | --- |
| AC-01 | Valid manifests/cases pass schema validation; malformed or unsafe paths are rejected before network I/O | Unit tests |
| AC-02 | `exact`, `contains`, `regex` scoring is correct, including failed and error cases | Unit tests |
| AC-03 | Offline CI runs with no credentials or network/inference | CI logs |
| AC-04 | Manual workflow can execute one real Cloudflare inference using repository secret/variable | Manual run logs |
| AC-05 | Real response is graded (not just checked for being nonempty) | Result artifact |
| AC-06 | Caps limit cases, output tokens, retries and parallelism | Unit tests + workflow review |
| AC-07 | Logs and artifacts contain no token or private customer data | Security scan + human review |
| AC-08 | Each real run produces `results.json` and `report.md` with traceability to commit/run/model | GitHub Actions artifact |
| AC-09 | Failed auth, quota and API calls yield a controlled error without disclosing secrets | Tests with local stub/fake responses |
| AC-10 | Published Pages view contains only explicitly public, sanitized sample results | Static publish review (later milestone) |

**Completion definition:** AC-01 through AC-09 pass, with one manually inspected successful real-evaluation artifact. AC-10 belongs to the subsequent dashboard milestone.

## 10. Planned implementation sequence

1. **SDD baseline:** this specification and agent guidance.
2. **Contracts/tests:** build manifest validation, assertion evaluation and offline unit tests.
3. **Provider adapter:** one Workers AI REST request, timeout, safe error handling and cost guardrails.
4. **Manual workflow:** dispatch, evaluate, upload JSON/Markdown artifacts; do not enable automated inference.
5. **Reporting:** compare runs and create a static, sanitized GitHub Pages dashboard.
6. **Extensions:** more free-eligible models, robustness metrics and new evaluation strategies under separate approved decisions.

## 11. Skill integration and change control

- **spec-driven-development:** every change starts by reading this file and any ADR under `docs/adr/`; identify the clause and assess compatibility; update specification before incompatible implementation.
- **pre-commit-security:** run scanner from `magnnwsb2/ai-engineering-skills` against staged changes when supported, plus independent GitHub Actions security checks. Do not claim scans happened unless logs prove execution.
- When an automated CI workflow imports the external skills repository, pin to a reviewed commit SHA rather than an untrusted mutable branch.
- Never claim the two skills are mechanically enforced by this document alone; workflow integration is a separate implementation task.
- Record significant architecture decisions in `docs/adr/`; ask approval before breaking a documented constraint.
- Changes requiring paid services, secret disclosure or increased spending risk are **prohibited** unless the user explicitly revises the zero-cost constraint.

## 12. Known risks and open decisions

- Cloudflare may change free-tier quotas, model availability or API behavior.
- Model compliance varies even with temperature 0.
- GitHub Pages is public; publication must use sanitized, public-only results.
- Python regex can be expensive on malicious inputs; cap length and keep test cases trusted.
- Decide static dashboard layout only after real evaluation artifacts exist.
- No resource provisioning or actual inference is authorized merely by this specification.

**Evidence links:**
- Existing smoke workflow: `.github/workflows/cloudflare-smoke-test.yml`
- Cloudflare API: https://developers.cloudflare.com/api/resources/ai/methods/run/
- Cloudflare free tier: https://developers.cloudflare.com/workers-ai/platform/pricing/
