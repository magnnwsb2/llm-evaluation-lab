# SDD-001 — Stage 023: offline matched-model comparison

**Status:** comparison foundation implemented with offline fixtures; **no second model has been authorized or executed**.

## What the comparison actually means

A fair descriptive **two-model** observation requires the **exact same** ordered prompts, case IDs, assertion types, expected answers, provider, cases file, temperature, repetition and output-token budget. The comparison's SHA-256 suite fingerprint covers the complete ordered prompt/assertion contract, not just case IDs.

The previously published `smoke-001`, `advanced-001` and `robustness-001` runs all used the **same model** on **different suites**. They are **not** a valid model A/B comparison. Neither does a matched 3-case experiment establish statistical significance, superior reasoning, model safety or a controlled latency benchmark.

The new `src/llm_eval/model_comparison.py` first validates the **complete original** `results.json` and canonical `report.md` of each run with the existing `validate_reports()`, independently bound to its trusted `Experiment`. It rejects altered statuses, mismatched source SHAs, changed prompts, reordered cases, extra fields and forged Markdown. It then refuses comparisons unless the model IDs differ and the full suite and execution settings are identical.

**Evidence limitation:** internal validation establishes structural consistency with trusted manifests, but cannot independently prove that a real API call occurred. Actual provenance still requires manually inspecting both GitHub Actions run logs and original artifacts.

## Sanitized output contract

The `matched-suite-observation` JSON includes only:

- `schema_version`, `kind`, `suite_sha256`, `cases_file`, `case_count`;
- For each model: run ID, revision SHA, experiment ID, model ID, strict pass/fail/error summary, number of observed HTTP latencies, mean of observed client HTTP round trips (or null if none) and case IDs/status/latency;
- Case-by-case paired statuses, plus `interpretation: descriptive_only_not_a_model_ranking`.

It includes **no** prompts, model responses, expected answers, full Markdown, keys, tokens, Neurons, cost or ranking. Provider errors remain errors, with null unmeasured latency and a count of HTTP latencies actually observed.

## Offline CLI (after Stage 026 approves a second model)

Example *future* usage from the repository root, after downloading two **manually reviewed** artifacts and unpacking them into local ignored folders:

```bash
PYTHONPATH=src python -m llm_eval.model_comparison \
  --left-experiment approved-model-a \
  --left-folder evaluation-artifacts/model-a \
  --right-experiment approved-model-b \
  --right-folder evaluation-artifacts/model-b \
  --output-name observation.json
```

These model-specific experiment selections above are **illustrative placeholders**, not implemented dispatch options. The CLI currently accepts only explicitly approved experiment IDs from `select_manifest()`, with model IDs restricted by `load_experiment()`. Because all currently authorized manifests use the **same** model, any attempted real two-model comparison **must fail safely until Stage 026** authorizes a second model and its manifest.

The CLI reads existing local files only, refuses traversal/symlink escapes and extra/public Pages paths, writes once into ignored `comparison-output/observation.json`, and never downloads files or calls Cloudflare. Do not commit local report folders; `evaluation-artifacts/` and `comparison-output/` are ignored.

## Roadmap and approvals

1. **023 (this stage):** build offline model comparison; use fictional model names **only in unit tests**.
2. **024:** add carefully scoped offline statistical/repeatability analyses; do not increase the inference cap without new approval.
3. **025:** additional deterministic quality and robustness criteria.
4. **026:** verify a presently free-eligible replacement/second model and adapt the allowlist under a separate SDD/security approval; only then run manually within the existing limits.
5. **027:** final comprehensive documentation, security, CI/CD, source evidence and public portfolio review.

The previously approved Cloudflare model is documented as scheduled for retirement on **2026-11-20**. If it becomes unavailable before Stage 026, **do not run inference or silently switch**. Offline functionality can continue. All stages retain zero financial cost and Github-only public publishing.
