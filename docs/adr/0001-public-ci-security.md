# ADR-0001 — Security scanning for a public GitHub Actions runner

**Status:** Accepted for MVP implementation  
**Date:** 2026-11-08  
**Related:** SDD-001 sections 5, 9 and 11; `AGENTS.md`

## Context

The project consumes the policies of the separately maintained `magnnwsb2/ai-engineering-skills` repository, including `pre-commit-security`. The initial public Actions workflow tried to check out this repository at reviewed SHA `daa9a20410ae4fe1b088d6d422ecbae88eecbace`, but GitHub Actions returned **Repository not found**. Its default scoped token cannot fetch a private repository from a different repository.

## Decision

- **Do not** expose or alter visibility of the skills repository.
- **Do not** ask for a broad GitHub token, additional paid service or GitHub Actions secret just to run public CI.
- Keep `ai-engineering-skills` as the canonical policy source for agents and human staged pre-commit scans where access is available.
- Implement an **independent, project-local security gate** under `tools/security_check.py` using original code that checks tracked file names and suspicious credential/private-key patterns.
- Add deterministic tests for the project-local gate and run it in public, credential-free GitHub Actions.
- The local implementation must **not** be advertised as executing or embedding the original private skill's scanner. It is an independent second line of defense.

## Consequences

- No cross-repository token is necessary; the policy preserves zero cost and private repository boundaries.
- CI scanner coverage is heuristic and may differ from the canonical skill. Review, rotation and staged checks remain necessary.
- If authenticated cross-repository access becomes approved later, reconsider direct skill execution under a separate reviewed change.
