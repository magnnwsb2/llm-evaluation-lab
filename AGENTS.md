# Agent instructions — LLM Evaluation Lab

## Authority and repository context
- Read `docs/specs/001-llm-evaluation-lab.md` **before** changing code, CI, data contracts or architecture.
- Consult `docs/adr/` if present; this project currently uses the initial SDD baseline as its canonical decision record.
- Read the canonical skills from `magnnwsb2/ai-engineering-skills`:
  - `skills/spec-driven-development/SKILL.md`
  - `skills/pre-commit-security/SKILL.md`
  - `AGENTS.md` and `SECURITY.md`
- Treat the remote skills as project policy, not as automatically installed or automatically executed. Any CI wiring must be explicit and pinned to a reviewed commit.

## Working procedure
1. Cite the relevant SDD section and state whether a requested change conforms to it.
2. Update the spec first when behavior/contracts change; never overwrite a prior approved ADR silently.
3. Make the smallest compatible implementation change and write offline tests.
4. Before committing, inspect the diff for credentials and sensitive data. If executing via git, run the canonical staged security scanner and relevant tests. For connector-only commits, explicitly report which local staged scans were **not** executed; add CI verification in a follow-on step.
5. Distinguish observed checks from planned ones; cite a GitHub Actions run when claiming a pass.
6. Do not ask the user to perform actions possible via the connected GitHub tools; require user action for UI-only secrets/approval steps.

## Hard safety constraints
- Never disclose, echo, commit or print `CLOUDFLARE_API_TOKEN`.
- Use only `secrets.CLOUDFLARE_API_TOKEN` and `vars.CLOUDFLARE_ACCOUNT_ID` in GitHub Actions.
- Do not trigger LLM inference on push, pull_request, cron or untrusted forks.
- Keep model inference manual and within SDD-001 caps; never select paid-only models.
- Never silently upgrade a Cloudflare plan, incur charges or request a credit card.
- Offline CI may use local fake responses for unit tests; **never** present mocks as real inference evidence.
- Static public reports must contain only sanitized synthetic data.
- If instructions conflict with cost, security or SDD constraints, stop the conflicting part and explain the decision.

## Current observed baseline
- `.github/workflows/cloudflare-smoke-test.yml` performs a manual real inference, and the user confirmed one successful run.
- The offline JSON contracts, objective grading functions and offline CI/security workflow are implemented in `src/llm_eval/`, `tests/` and `.github/workflows/offline-ci.yml`.
- A guarded Cloudflare provider adapter exists at `src/llm_eval/providers/cloudflare.py`; it is import-safe and is covered by offline fakes, but it does not automatically run inference.
- Real manual graded evaluation **has been verified**: GitHub Actions run `42504084221`, commit `61fd68ae0d51d646e33db13c8187f3b6351e8220`, 3 pass, 0 fail/error; latencies 492, 1133 and 523 ms.
- The manual workflow validates report integrity offline before uploading artifacts (`src/llm_eval/report_validation.py`); internal consistency is not evidence of a real provider call.
- A public-summary-only Pages dashboard is implemented with offline builder, strict allowlist and manually reviewed snapshot. Do not assert that GitHub Pages is publicly live unless the deploy job succeeded.
- Never publish the raw `results.json`, responses, prompts, the Cloudflare token or inferred billing metrics. Future results require separate review before updating the public snapshot.
- Stage 015 and 015.1 have succeeded in GitHub Actions Pages deployment; live dashboard is based on the reviewed run #42504084221 only.
- Stage 016 adds a strictly allowlisted optional manual `advanced-001` experiment, structured `json_object` scoring, and repeat-prompt diagnostic, without increasing caps or publishing new model responses. Real advanced run #42511351245 was inspected: 2 pass, 1 strict JSON-format fail, 0 provider errors. Stage 017 adds non-scoring JSON diagnostics and a separately reviewed statistics-only snapshot; never reinterpret the failure as a pass.
- Stage 018 SDD §5.8 authorizes displaying **only two manually reviewed** real-run summaries on static GitHub Pages, with original smoke chart retained and advanced comparison/JSON-format cause shown. No raw outputs, automatic snapshot updates or model inference in the site builder. After merges, verify Pages deploy success before describing the new site as publicly deployed.
- Stage 019 SDD §5.9 is a static visual/accessibility-only improvement: compact chart layout, more readable mobile provenance links, keyboard navigation and methodology for **both** audited experiments. It does not regrade, rerun, replace approved snapshots, or introduce unreviewed public data. Preserve offline visual regression tests; require CI and Pages deploy verification plus visual inspection.
- Stage 020 SDD §5.10 adds a third **manual-only** synthetic robustness experiment (`robustness-001`) for record precedence, untrusted ticket-title instructions and strict JSON formatting. Keep the model/case/token caps, report schemas and original two audited Pages snapshots unchanged; offline tests are NOT real inference evidence. Actual run #42519170795 has now been reviewed: 1 pass, 2 strict failures, 0 provider errors; do not generalize model performance from three synthetic prompts.
- Stage 021 SDD §5.11 adds conservative **non-scoring** failure diagnostics for content, format and **possible** incomplete responses in future canonical Markdown reports. No model termination reason was captured, so an unfinished answer must NOT be called confirmed token truncation. Existing results.json, strictly graded status, audited original artifacts and two public Pages snapshots are unchanged; only offline CI fixtures and reviewed retrospective explanations are added.
- Stage 022 SDD §5.12 **separately approved** public display of the previously audited robustness-001 run #42519170795 with strict 1/3 grade, after adding a third exact-allowlisted, response-free summary and independent fail-closed validator. Public Pages can now compare three manually reviewed runs, but **never** automatically ingest newer artifacts. Completion is only possible, not confirmed truncation. Preserve the previous two snapshots, original scoring, privacy and offline-only Pages builder.

- Stage 023 SDD §5.13 prepares an **offline-only** matched-suite comparison of two validated reports from **different** models, with full prompt/assertion suite SHA-256, generation-config equality, report regrading and no raw outputs in generated summaries. Model B exists **only in unit-test fixtures** until Stage 026 permits a real, verified free-plan eligible model. Do not loosen `FREE_MODEL_ALLOWLIST`, workflow inputs or Pages publication in Stage 023. Store downloaded artifacts/output only under ignored local directories.
- User-approved future order: 024 statistical/consistency methods, 025 new objective evaluation strategies, 026 model replacement after functionality is stable, 027 final security/CI/docs/portfolio consolidation. A retired model must cause a safe halt, not a paid or unapproved automatic replacement.

- Stage 025 SDD §5.15 adds **offline synthetic** assertion mutation probes (`outer-whitespace`, `case-swap`, `append-marker`) against the unchanged `grade()` semantics. These measure objective **rule sensitivity**, not model robustness, accuracy, safety or real inference. Never publish synthetic probes as model evidence, raw prompts/expected values or mutate the historical Pages snapshots. Keep Stage 026 for reviewed model authorization and Stage 027 for final consolidation.
- Stage 024 SDD §5.14 adds **offline-only** descriptive HTTP latency statistics and conservative run-to-run response agreement over 1–5 independently canonical-validated reports with **identical model, suite, configuration and revision**. One run does not establish repeatability; missing/error responses do not create agreement; matching wrong responses do not mean correctness. No p95/p99, significance claims, confidence intervals, provider inference, new API credentials or public Pages ingestion. Generated observations stay in ignored `comparison-output/`. Never claim test fixtures represent real repeated inference.
