# ADR-0002 — Free-plan model lifecycle, historical reproducibility and live selection

**Status:** Accepted for Stage 026 implementation.  
**Date:** 2026-11-08.  
**Related:** SDD-001 §5.16, ADR-0001, `src/llm_eval/contracts.py`, `src/llm_eval/run_evaluation.py`.

## Context

The three approved historical evaluations ran `@cf/meta/llama-3.1-8b-instruct-fp8` and are tied to immutable experiment IDs and GitHub artifacts. Cloudflare's [November 2026 deprecation notice](https://developers.cloudflare.com/changelog/product/workers-ai/) says that model will cease responding on November 20, 2026 (HTTP 410 / code 5028). Rewriting the historical manifests would invalidate the evidence. Continuing to offer them as new manual inference selections would be misleading.

Cloudflare documents `@cf/google/gemma-4-26b-a4b-it` as a newer hosted model with zero data retention and a chat completion response envelope. Cloudflare's [pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) describes a free 10,000-Neuron daily allocation and explicitly enumerates the restricted paid-only models. The selected Gemma is absent from that paid-only list and [was positively named as Workers Free-compatible](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/). This is documentation-level eligibility, **not real-account verification or proof that every call is free**.

## Decision

- **Preserve** all `*-001` manifests, raw evidence, reviewed snapshot hashes, scores and public Pages data. Keep the old model ID in the strict **offline validator** allowlist only for reproducibility of archived versioned runs.
- Create `smoke-002`, `advanced-002`, `robustness-002` with the new Gemma model while **reusing identical case files** and preserving 3 sequential calls × 1 repetition × 64 output/completion tokens per run. No new prompts, new secrets or spending.
- Separate `select_manifest` (offline/archived/all reviewed versioned manifests) from `select_live_manifest` (**Gemma-only**). Make the real GitHub Actions dropdown and both manual workflows use only the active model.
- For the Gemma REST request, cap `max_completion_tokens` at 64 rather than relying on the provider's default; parse the single `result.choices[0].message.content` form as well as legacy `result.response`. Reject empty, malformed or ambiguous responses with sanitized error; no retries or alternative paid-model fallback.
- CI remains credential-free and makes **zero** real inference requests. A fresh real Gemma run needs an **explicit manual dispatch** and separate artifact/provenance review; do not call it confirmed or publish its scores now.
- Stage 027 will audit the full project's behavior, security, references and portfolio presentation. Public snapshots never change solely due to this migration.

## Consequences and caveats

- Model free-tier limits, access, response shape and service health are external assumptions, subject to change. The newly supported envelope is **tested with offline fakes**, not proven by a real call.
- On a request failure for capacity, authentication, quota, payment restriction or HTTP 410, fail closed. **Do not** upgrade an account, use AI Gateway credits or silently switch models.
- A versioned cross-model comparison is only meaningful after both actual runs are independently verified; small synthetic suites do not establish statistically significant superiority.
- The historical model remains readable by offline tooling; its presence in the validator allowlist is **not authorization for new inference**.

## First real-run failure and compatibility follow-up (2026-11-08)

Manual `smoke-002` run [#42527009736](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527009736) produced one attempted HTTP inference (9,536 ms; `invalid_response`) followed by two intentionally skipped cases (null latencies), not three failed provider requests. The raw response was not saved, so **the exact cause is unknown**. Cloudflare's Gemma 4 guide documents `chat_template_kwargs.enable_thinking=false` for plain text generation. Disable this optional reasoning mode only for Gemma, preserving `max_completion_tokens=64`, fail-closed response handling, and one-request-only execution. This is a **testable hypothesis**, not evidence that the model is now working. Another manually authorized run is required; no automated retry.
