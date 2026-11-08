"""Offline scoring tests: all answers are synthetic fixtures, not model outputs."""

import unittest

from llm_eval.contracts import Assertion, Case, ContractError
from llm_eval.scoring import grade, summarize


class ScoringTests(unittest.TestCase):
    def case(self, kind="exact", expected="OK"):
        return Case("case-001", "Synthetic prompt", Assertion(kind, expected))

    def test_exact_trims_only_edges(self):
        self.assertEqual(grade(self.case(), " \nOK\t").status, "pass")
        self.assertEqual(grade(self.case(), "O K").status, "fail")
        self.assertEqual(grade(self.case(), "ok").status, "fail")

    def test_contains_is_case_sensitive(self):
        self.assertEqual(grade(self.case("contains", "SUNRISE"), "A SUNRISE appeared").status, "pass")
        self.assertEqual(grade(self.case("contains", "SUNRISE"), "sunrise").status, "fail")

    def test_regex_uses_search_semantics(self):
        self.assertEqual(grade(self.case("regex", r"[0-9]{3}"), "number: 123").status, "pass")
        self.assertEqual(grade(self.case("regex", r"^[0-9]{3}$"), "number: 123").status, "fail")

    def test_error_is_not_a_pass(self):
        err = grade(self.case(), "OK", error_category="quota", latency_ms=250)
        self.assertEqual(err.status, "error")
        self.assertIsNone(err.response)
        self.assertEqual(err.error_category, "quota")
        self.assertEqual(err.latency_ms, 250)

    def test_missing_response_is_error(self):
        result = grade(self.case(), None)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_category, "invalid_response")

    def test_cannot_insert_unsanitized_error(self):
        with self.assertRaises(ContractError):
            grade(self.case(), None, error_category="Bearer sensitive-token")
        with self.assertRaises(ContractError):
            grade(self.case(), "OK", latency_ms=True)
        with self.assertRaises(ContractError):
            grade(self.case(), 10)

    def test_summary_counts_failures_and_errors(self):
        results = [
            grade(self.case(), "OK"),
            grade(self.case(), "NO"),
            grade(self.case(), None, error_category="timeout"),
        ]
        summary = summarize(results)
        self.assertEqual((summary.total, summary.passed, summary.failed, summary.errors), (3, 1, 1, 1))
        self.assertAlmostEqual(summary.pass_rate, 1 / 3)

    def test_empty_summary_rejected(self):
        with self.assertRaises(ContractError):
            summarize([])


if __name__ == "__main__":
    unittest.main()
