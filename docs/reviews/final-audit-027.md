# Final technical audit — Stage 027

**Date:** 2026-11-08  
**Repository:** [magnnwsb2/llm-evaluation-lab](https://github.com/magnnwsb2/llm-evaluation-lab) (public, Python 3.12, MIT).  
**Source of truth:** SDD-001 §5.17; ADR-0001 and ADR-0002.  
**Scope:** inspect current main tree, all four Actions workflows, provider adapter, versioned contracts, scoring, report integrity, offline comparison/statistics/mutation tools, approved dashboard snapshots and evidence. This is a **bounded review**, not a penetration test or complete secret audit of all historical Git commits.

## Verified evidence, without interpretation inflation

- **Five actual manual run records and ZIP artifacts inspected:** three approved historical Llama experiments, one failed Gemma attempt and one successful Gemma smoke; all linked with commit SHA, strict outcomes and artifact digests in the [sanitized run ledger](../evidence/run-ledger-027.md).
- Gemma `smoke-002` run [#42527365653](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527365653) at revision `2d1de4086836542a92ae965515232a0411a5a073`: 3 pass / 0 fail / 0 provider errors, measured latencies 1291, 596 and 410 ms; output `results.json` and `report.md` survived integrity validation and were uploaded. Previous Gemma run #42527009736 had **one** attempted `invalid_response` and two skipped requests, never 3 unsuccessful model answers.
- The three reviewed Pages snapshots remain pinned Llama-only, and [GitHub Pages](https://magnnwsb2.github.io/llm-evaluation-lab/) has a successful prior deployment, [#42527266690](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42527266690). Stage 027 changes **neither their values nor the site renderer**.
- [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) documents Workers Free allocation; plan and daily usage screenshots previously provided by the user confirmed Workers Free and 16.25 / 10,000 Neurons at that point. **No post-Gemma invoice or usage attestation was retrieved**: no-charge claims are limited to the project's configuration, not audited account billing.

## Architecture and execution boundaries

```text
Manually approved experiments (synthetic JSON + allowlisted model)
         |
         +--> GitHub PR / push -> offline Python unit tests
         |                     -> project-local secret heuristics
         |                     -> no provider request or billing
         |
         +--> GitHub Actions workflow_dispatch ONLY
                  -> shared concurrency group (one active manual run)
                  -> secrets/vars injected at runtime
                  -> strict case/model/temperature/call budget checks
                  -> Cloudflare Workers AI (Gemma 4; no retries)
                  -> grade: exact / contains / regex / json_object
                  -> validate canonical results.json + report.md
                  -> GitHub Actions artifact (7-day retention; raw synthetic responses)
                  |
                  +--> separate manual review + allowlisted sanitized snapshot
                        -> offline static Pages builder -> public HTML/CSS
```

Offline-only modules for **matched-case cross-model comparison** (Stage 023), **descriptive HTTP latency and response agreement** (Stage 024) and **synthetic scorer mutation probes** (Stage 025) do not trigger providers or update Pages. The public dashboard is a curated historical display, **not** an automatically refreshed telemetry stream.

## Final audit findings and controls

| Area | Finding | Stage 027 action / resolution |
|---|---|---|
| SDD/README drift | 30 KB chronological README contained stale claims that Gemma was untested and old workflow choices were still available; older sections also contradicted the three-snapshot Pages state | Archive full README as dated history and replace landing page with concise accurate current status, verified real Gemma run and sources |
| Archived model live guard | Old Llama remained in `FREE_MODEL_ALLOWLIST` for valid historical offline reports; adapter originally could use that model on real HTTP if called outside approved workflow selector | Refuse any non-active model when the adapter is using the real HTTP transport; retain archived fake-transport fixtures and offline validation |
| Cross-workflow concurrency | Manual 1-case smoke and 3-case graded workflow used separate concurrency groups | Use same `manual-workers-ai-inference` group with `cancel-in-progress: false`, serializing simultaneous manual launches |
| Provenance | GitHub Actions artifacts expire and prior public Pages published only three reviewed Llama results | Add exact run IDs, revision SHAs, inspected grades/latencies, artifact IDs and reproduced ZIP hashes to permanent public-safe ledger; **do not** publish Gemma Pages score without explicit separate approval |
| Artifact exposure | `results.json` contains raw model outputs in a public GitHub repository's 7-day artifact; Pages omits them | Add a clear `SECURITY.md` and README warning. **Use synthetic data only**; no misleading claim that uploaded Actions artifacts are private |
| Credentials | GitHub Actions token is a secret and account ID is a variable; no evidence in reviewed workflows of hardcoded production values | No secret values are committed; offline scanner and reviewed PR diff required. Not an assurance about all repo history |
| Security skills | Canonical `pre-commit-security` policy lives in a separate private repository; public CI has a standalone project-local heuristic scanner | Keep canonical skill as policy; the original staged scanner was **not executed** through connector-only commits; do not claim otherwise |
| Experiment integrity | Manifest allowlists, source-matched report recomputation, deterministic test fixtures and exact-pin Pages validators | Retain existing original v1.0 schemas, approved snapshots, scorer semantics and offline source validation without drift |
| Pricing | Workers Free usage ceiling is externally managed and free eligibility is not a contractual guarantee | No new provider calls; explicit no-upgrade/no-paid-fallback; monitor billing/quotas manually |

## Acceptance checklist and scope of verification

- [x] SDD §5.17 and previous ADRs reviewed **before implementation**; retain decision history.
- [x] All six manifest IDs, three original Pages snapshots, four workflows and relevant source modules reviewed as the current tree; no Pages data rewrite.
- [x] Five real run artifact ZIPs hashed; source metadata and outcomes documented without raw model text.
- [x] Stage 027 security hardening and documentation changes implemented on a separate reviewed PR.
- [x] Final reproducible security tests added to offline CI; no inference, cloud provision or model-change request.
- [x] PR #20 [offline CI #42528843377](https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42528843377): **207 Python tests passed**, all six manifests validated and **0 security blockers / 0 review items** in the independent scanner.
- **Required operational handoff after merge:** explicitly verify the new `main` CI and, if the SDD change triggers it, the Pages build/deployment. The final handoff message must cite the observed run IDs; this pre-merge audit does not guess future GitHub Actions run IDs or claim the deploy has already completed.

**Not certified by this audit:** zero secret exposure anywhere in all historic Git objects, real billing balance after Gemma, encryption or private access for GitHub artifact ZIPs, model determinism, statistically significant comparative performance, evaluation over real customer data, comprehensive prompt-injection defenses, or long-term availability of a free model.

**Disposition:** the roadmap is ready for closure **after** the PR is merged with green offline CI, independent security gate and final Pages verification where applicable. Future product expansion must use a new SDD change; it is **not implicitly part of Stage 027**.
