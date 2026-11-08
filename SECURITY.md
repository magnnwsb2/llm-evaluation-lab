# Security policy — LLM Evaluation Lab

## Scope and supported use

This is a **public, educational LLM evaluation laboratory with synthetic test cases only**. It is not a service for private documents, confidential business data, credentials, production tickets or customer records. Do **not** add real customer data to `cases/`, prompts, assertions, local artifacts or GitHub Actions logs.

The public GitHub Pages dashboard intentionally contains only manually reviewed, strict allowlisted results without prompt/response text. **This does not mean every GitHub Actions artifact is private:** the `Manual graded LLM evaluation` job uploads `results.json` (including full synthetic model responses) and a response-free `report.md` to a **public repository** with seven-day retention. Repository Actions artifacts may be accessible via GitHub. Use synthetic inputs only.

## Credentials and billing

- Cloudflare account ID is read from GitHub Actions variable `CLOUDFLARE_ACCOUNT_ID`; the API token is read from secret `CLOUDFLARE_API_TOKEN`. Do not place real values in files, PRs, logs, comments or screenshots.
- Requests are allowed **only** through manually dispatched workflows; no cron, push/PR inference, parallel batches or retries. Both manual workflows use a shared concurrency group.
- The real provider transport refuses archived models; only the explicitly reviewed current model is eligible. Each evaluation is limited to 3 sequential calls × 1 repetition × 64 completion tokens; the one-call smoke is narrower.
- Workers AI usage must remain within the free allowance. **Do not upgrade the Cloudflare account, use paid-only models, credits or payment methods.** Provider limits and eligibility may change. A successful test is not proof of future zero cloud charges.

## Contribution and disclosure

- Read `AGENTS.md`, [SDD-001](docs/specs/001-llm-evaluation-lab.md), [ADR-0001](docs/adr/0001-public-ci-security.md), and [ADR-0002](docs/adr/0002-free-model-lifecycle.md) before changing code/contracts.
- Offline CI runs unit tests and a **project-local, independent** scanner at `tools/security_check.py`. The canonical `pre-commit-security` policy is stored separately in a **private** `ai-engineering-skills` repository; public CI does **not** execute that original staged scanner. Both checks are heuristic and neither validates all historical commits.
- Never submit a sensitive issue or public PR containing a discovered secret. Report potential security vulnerabilities privately to the repository owner via GitHub's **Private vulnerability reporting** feature if enabled; otherwise contact the maintainer through a private channel. Do not publish exploit details or credentials.
- If a token is exposed, **revoke/rotate it immediately** and review commit history and GitHub Actions logs/artifacts. A commit removing the token is insufficient if the secret was already made public.

## Trust boundaries and limits

- Verified report structure, grades and artifact ZIP hashes are **not independent cryptographic attestation of a hosted provider call**.
- Synthetic repeated-prompt agreement and small-sample scores are not evidence of model determinism, general safety or predictive accuracy.
- Public dashboard results are manually allowlisted; creating a run does **not** automatically publish a new dashboard card.
- GitHub Actions artifacts expire (seven days currently), and responses in the artifact are not anonymized. Never rely on this retention period as a privacy mechanism.

See [the final audit](docs/reviews/final-audit-027.md) and [the sanitized run ledger](docs/evidence/run-ledger-027.md).
