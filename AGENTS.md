# Agent instructions — LLM Evaluation Lab

## Source of truth and authority

This is a **public** and **zero-financial-cost** GitHub-based LLM evaluation project. Read in order:

1. [SDD-001](docs/specs/001-llm-evaluation-lab.md), including **Stage 027 §5.17**;
2. All applicable `docs/adr/`, especially ADR-0001 (independent public-CI scan) and ADR-0002 (active/free model and archive);
3. [SECURITY.md](SECURITY.md), [run evidence ledger](docs/evidence/run-ledger-027.md) and [final audit](docs/reviews/final-audit-027.md);
4. Canonical skills in the separate private `magnnwsb2/ai-engineering-skills` repository: `skills/spec-driven-development/SKILL.md`, `skills/pre-commit-security/SKILL.md`, associated references and `SECURITY.md`.

**Skills are policy, not proof of execution.** A GitHub connector-only commit cannot execute the original skill's staged pre-commit scanner on a local Git index. This public repo uses an **independent** scanner at `tools/security_check.py` in CI; do not claim the private scanner ran. Do not disclose or make the skills repository public to work around its limited accessibility.

## Change procedure

- Read the SDD and relevant ADRs first; describe whether the change is compatible. Update SDD **before code** for new behaviors, evidence/publishing contracts or security changes.
- Prefer the smallest compatible change; add deterministic tests and static documentation. Do all GitHub work that connector permissions allow, and request user action only for an actual required manual action.
- Inspect PR diffs for credentials, sensitive filenames, unauthorized inference triggers, output disclosures, cost regressions and fake claims. Require **passing actual** GitHub Actions tests + project-local scanner before merge.
- Verify post-merge `main` checks and Pages deployment when triggered. A passing CI test proves the tested code path, **not** actual model availability, usage/billing status or provenance of an API call.
- Record important decisions and run evidence without storing raw model responses in public documentation. Never silently revise historical reviewed snapshots or original result artifacts.

## Hard limits

- **Never** request or log the content of `CLOUDFLARE_API_TOKEN`; only `secrets.CLOUDFLARE_API_TOKEN` in Actions. Account ID is provided through `vars.CLOUDFLARE_ACCOUNT_ID`; do not commit concrete values.
- Real inference is **explicit `workflow_dispatch` only**, not push, PR, cron, triggered test code, automatic retry, or unrestricted API call. Both manual workflows share the same concurrency group.
- Only the **active model** `@cf/google/gemma-4-26b-a4b-it` is permitted for **real** provider transport (Stage 026/027). The old `@cf/meta/llama-3.1-8b-instruct-fp8` is recognized **offline only** for archived `*-001` evidence and fixture tests.
- The three live `*-002` experiment IDs use their approved old case files; maximum 3 sequential requests × 1 repetition × 64 completion tokens; temperature 0, no retries, no redirects, no parallel inference. The one-call smoke workflow is narrower.
- **Workers Free only.** No paid-plan upgrade, credit card, new cloud servers, paid-only models, extra usage or auto-paid fallback. The provider's eligibility and quota may change externally; failure must stop safely.
- Use **synthetic prompts and answers only**. Do not put real customer information or credentials in any fixture. The public GitHub Pages site uses reviewed sanitized snapshots without raw text, but **public repository Actions artifacts can contain original synthetic responses** (current retention: 7 days). Never describe these ZIPs as private.
- Scoring is objective (`exact`, `contains`, `regex`, `json_object`). Diagnostics do not change strict results. Never claim broad accuracy, prompt-injection resistance, deterministic output, statistical significance, guaranteed free billing or provider token usage from tiny samples.

## Current evidence baseline (2026-11-08)

- Historical Llama runs: [smoke #42504084221](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221) 3/3, [advanced #42511351245](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42511351245) 2/3, [robustness #42519170795](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42519170795) 1/3. Their **three manually reviewed summaries** are the only current public Pages results.
- First Gemma `smoke-002` [#42527009736](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527009736) returned `invalid_response` on the first request; the last two requests were **not sent**. The exact cause is not proven.
- Corrected Gemma `smoke-002` [#42527365653](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527365653) completed **3 pass / 0 fail / 0 error**, latencies 1291 / 596 / 410 ms, commit `2d1de4086836542a92ae965515232a0411a5a073`. This is a real manually dispatched case-limited result, **not** simulated and **not** yet a Pages snapshot.
- GitHub Actions artifacts and their reproduced SHA-256 values are recorded in `docs/evidence/run-ledger-027.md`. The evidence is limited by ZIP expiration, synthetic prompts, and GitHub's public repository trust model.
- Stages **001–027** form the approved original project roadmap. Further model tests, other benchmarks, additional public results or architectural changes require **new user-approved scope** rather than implied background work.
