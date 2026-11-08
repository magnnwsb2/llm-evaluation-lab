# Stage 025 — Synthetic objective-assertion mutation probes

**Status:** offline-only methodology tooling, **not real LLM inference**. SDD-001 §5.15.

This stage adds a deterministic *sensitivity test of the laboratory's objective scoring rules*. For each validated case, the tool takes the **reference expected text** (not a real model answer), evaluates that baseline and applies exactly three synthetic output changes:

| Probe | Deterministic change | Interpretation |
|---|---|---|
| `outer-whitespace` | Add one space before and after | Whether the rule tolerates exterior whitespace |
| `case-swap` | Swap ASCII uppercase/lowercase | Whether the rule distinguishes casing |
| `append-marker` | Append fixed `__PROBE__` suffix | Whether extra trailing content is accepted |

The existing `grade()` function scores all synthetic variants. **Passing a probe does not imply a vulnerability**: for example, the `contains` rule intentionally accepts extra text, while `exact` intentionally strips outer whitespace. The `regex` expected value is a **pattern**, not a guaranteed matching output; the baseline is marked `baseline_guaranteed=false` for that reason.

Output `synthetic-objective-assertion-probes` v1.0 contains only experiment/model identifiers, full ordered suite SHA-256, assertion type, case IDs, baseline status, probe IDs and pass/fail statuses, counts, and the explicit `synthetic_rule_sensitivity_not_model_performance` caveat. No prompts, expected strings, mutated texts, provider replies, tokens or monetary figures are exported.

### Offline command

From the repository root:

```bash
PYTHONPATH=src python -m llm_eval.mutation_probes \
  --experiment advanced-001 \
  --output-name objective-probes.json
```

The CLI accepts only repository-reviewed experiment IDs and model allowlists, makes **zero** provider/network requests and writes exclusively once to the ignored `comparison-output/` directory. It never modifies the actual scoring contract, manually approved model, inference workflow or public GitHub Pages. The synthetic output must **not** be presented as a real LLM robustness evaluation.

### Remaining roadmap

- **026:** independently verify a free-eligible replacement model, update the SDD/allowlist only after explicit approval and run a bounded real manual evaluation if available.
- **027:** consolidate architecture, SDD, tests, security, reproducibility, public portfolio and documentation.

Original inference cap remains 3 sequential cases × 1 repetition × 64 output tokens per manual run; no paid services, credentials, new Actions permissions or automatic inference.
