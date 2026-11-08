# Stage 024 — Offline descriptive statistics and repeatability

**Specification:** [SDD-001 §5.14](../specs/001-llm-evaluation-lab.md).  
**Status:** implemented with synthetic offline test fixtures. **No repeated real multi-run campaign has been conducted or claimed.**

## Questions answered

1. **How variable were the observed HTTP latencies?** For each available source run and the permitted cohort, report count of measured timings, minimum, maximum, arithmetic mean, median and **sample** standard deviation. Missing timings and provider-error placeholders are not zeros. Sample standard deviation is **null** if fewer than two timings exist. These are HTTP round trips, not pure model-generation latencies.
2. **How often were strict objectives met?** For each case across runs, show counts of `pass`, `fail` and `error`, without suppressing errors or promoting incorrect answers.
3. **Were the replies identical across runs?** Count pairs of **non-error** responses whose text matches after trimming *only outer whitespace*. Record numerator, denominator and ratio, or **null** if no pair can be compared. A pair of **identically wrong** replies is an agreement but **not correctness**. Missing/error outputs do not count as agreeing or disagreeing pairs.
4. **Were distinct prompts repeated inside a run?** Reuse the already implemented `compare_identical_prompts` and include the `same`/`different`/`unavailable` outcome, never raw response strings.

A **single** run yields only latency statistics and a `not_measurable_single_run` repeatability designation. An observed 1/1 match is *not* evidence of determinism or general reliability; sample sizes here are intentionally tiny.

## Required evidence and constraints

- Inputs: one validated repository-controlled `Experiment` and **1–5** canonical `(results.json, report.md)` artifacts, each independently validated against the **same approved case suite, model, configuration, objective scoring rules, and GitHub revision**. Distinct numeric GitHub run IDs are mandatory. SHA drift is rejected rather than combined.
- Process: no APIs, no model judge, no generated new inference, no downloaded resources, no scheduling, no expanded request budgets. Preserve the **3 cases × 1 repetition × 64 max output tokens** limit per manually authorized run.
- Output: `descriptive-repeatability-observation` schema v1.0: source run IDs/revisions/timestamps, exact suite SHA-256, objective counts, descriptive HTTP timings and normalized response-agreement **counts only**. Exclude prompts, full responses, expected outputs, user data, credentials, token/Neuron/cost estimates, statistical tests, p-values, confidence intervals and rankings.
- Interpretation: a cohort with up to five runs of three cases is not a sufficiently representative sample for p95/p99, significance tests, general reliability or safety claims. Differences in network latency cannot be attributed to the model without controlled measurement.
- This module is **offline-only**, does not change `results.json` schema, prior run artifacts, SDD Stage 023's model-comparison logic, the provider allowlist, or the public GitHub Pages data. Real repeatability observations require separate authorized manual runs and artifact verification.

## Offline command

After existing manually reviewed artifacts have been downloaded and unpacked locally into ignored folders, run from the repository root:

```bash
PYTHONPATH=src python -m llm_eval.statistics_analysis \
  --experiment advanced-001 \
  --folders evaluation-artifacts/run-1 evaluation-artifacts/run-2 \
  --output-name repeatability.json
```

This is an **example**, not evidence that those source folders or repeat runs exist. The CLI uses `select_manifest` to restrict experiment IDs and `load_experiment` to enforce the approved model. It rejects traversal, paths outside the repo, public folders, symlinked report files, malformed JSON/Markdown, unexpected source identities and inconsistent revisions. Output is written once under the gitignored `comparison-output/repeatability.json`; it never updates Pages or performs a provider call.

## Roadmap

- **024:** offline descriptive metrics and cautious repeatability (this stage).
- **025:** expand strictly objective evaluation scenarios under separate SDD review.
- **026:** explicitly verify/authorize a currently eligible free-tier model, with no silent replacement or cost.
- **027:** final security, CI, architecture, documentation and portfolio consolidation.

The existing Cloudflare model's scheduled retirement (**2026-11-20**) remains a concern. If no longer available, avoid real inference until Stage 026's reviewed replacement. Offline analysis and CI remain usable without that model.
