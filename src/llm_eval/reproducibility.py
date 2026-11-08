"""Offline repeated-prompt agreement diagnostic; not a quality or accuracy score."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .contracts import ContractError, Experiment
from .scoring import CaseResult


@dataclass(frozen=True, slots=True)
class PromptAgreement:
    first_id: str
    second_id: str
    outcome: str  # same, different, unavailable


def compare_identical_prompts(
    experiment: Experiment, results: list[CaseResult] | tuple[CaseResult, ...]
) -> tuple[PromptAgreement, ...]:
    """Compare distinct calls with exactly the same original prompt.

    Provider errors make the comparison unavailable. A repeated wrong answer
    may count as 'same': agreement is deliberately independent of correctness.
    """
    if len(results) != len(experiment.cases):
        raise ContractError("repeat analysis: case/result count mismatch")
    for case, result in zip(experiment.cases, results):
        if case.id != result.id:
            raise ContractError("repeat analysis: case/result order mismatch")
    observations: list[PromptAgreement] = []
    for left, right in combinations(range(len(experiment.cases)), 2):
        if experiment.cases[left].prompt != experiment.cases[right].prompt:
            continue
        first, second = results[left], results[right]
        if (
            first.status == "error" or second.status == "error"
            or first.response is None or second.response is None
        ):
            outcome = "unavailable"
        elif first.response.strip() == second.response.strip():
            outcome = "same"
        else:
            outcome = "different"
        observations.append(PromptAgreement(first.id, second.id, outcome))
    return tuple(observations)
