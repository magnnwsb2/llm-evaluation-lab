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
- The real-inference evaluation workflow, persisted report artifacts and Pages dashboard have **not** been implemented yet.
