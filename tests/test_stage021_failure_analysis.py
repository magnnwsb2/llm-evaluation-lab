"""Stage 021: offline non-scoring cause analysis and canonical report checks."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_eval.contracts import ContractError, load_experiment
from llm_eval.failure_analysis import assess_failure
from llm_eval.report_validation import validate_files, validate_reports
from llm_eval.run_evaluation import build_report, write_report
from llm_eval.scoring import CaseResult, grade

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "42519170795"
SHA = "f7f98c3082f92508ef06a1cbc02b7a60c6acfe90"
UTC = "2026-11-08T20:15:27+00:00"
MANIFEST = "experiments/robustness-001.json"
FENCE = chr(96) * 3

# Representative local fixtures, not copies of the complete real responses.
INCOMPLETE = (
    "Step 1: choose highest seq. It is seq=12.\n"
    "Step 2: check severity and retries for this row,"
)
WRAPPED_WRONG = FENCE + 'json\n{"status":"pending","attempts":1}\n' + FENCE
WRAPPED_CORRECT = FENCE + 'json\n{"status":"complete","attempts":2}\n' + FENCE
EXPECTED = '{"status":"complete","attempts":2}'


class FailureAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.experiment = load_experiment(MANIFEST, ROOT)
        cls.precedence, cls.untrusted, cls.json_case = cls.experiment.cases

    def _check(self, case, reply, status):
        result = grade(case, reply, latency_ms=9)
        self.assertEqual(result.status, status)
        return assess_failure(case, result)

    def test_explanation_ends_mid_clausule_without_proving_truncation(self):
        x = self._check(self.precedence, INCOMPLETE, "fail")
        self.assertEqual((x.content, x.format, x.completion, x.reason),
                         ("unknown", "violation", "possible_incomplete",
                          "exact_prose_possible_incomplete"))

    def test_long_prose_is_not_automatically_a_truncation(self):
        x = self._check(self.precedence,
                        "The last record has lower priority. End of response.", "fail")
        self.assertEqual((x.content, x.format, x.completion),
                         ("unknown", "violation", "no_signal"))

    def test_wrong_uppercase_decision_is_content_mismatch(self):
        x = self._check(self.precedence, "MONITOR", "fail")
        self.assertEqual((x.content, x.format, x.reason),
                         ("mismatch", "conforming", "exact_wrong_token"))

    def test_extra_punctuation_is_format_only(self):
        x = self._check(self.precedence, "ESCALATE.", "fail")
        self.assertEqual((x.content, x.format, x.reason),
                         ("match", "violation", "exact_extra_punctuation"))

    def test_untrusted_title_case_remains_approved(self):
        x = self._check(self.untrusted, " MONITOR\n", "pass")
        self.assertEqual((x.content, x.format, x.reason),
                         ("match", "conforming", "strict_pass"))

    def test_json_wrapped_wrong_content_fails_both_dimensions(self):
        x = self._check(self.json_case, WRAPPED_WRONG, "fail")
        self.assertEqual(
            (x.content, x.format, x.completion, x.reason),
            ("mismatch", "violation", "no_signal", "json_content_and_format"),
        )

    def test_json_wrapped_correct_content_fails_format_only(self):
        x = self._check(self.json_case, WRAPPED_CORRECT, "fail")
        self.assertEqual((x.content, x.format, x.reason),
                         ("match", "violation", "json_format_only"))

    def test_json_standalone_wrong_content_is_content_only(self):
        x = self._check(self.json_case, '{"status":"pending","attempts":1}', "fail")
        self.assertEqual((x.content, x.format, x.reason),
                         ("mismatch", "conforming", "json_content_only"))

    def test_unsafe_or_ambiguous_json_does_not_prove_content(self):
        cases = (
            ('{"status":"complete","attempts":', "possible_incomplete"),
            ("not JSON", "no_signal"),
            ('{"status":"complete","attempts":2,"attempts":2}', "no_signal"),
            (EXPECTED + " " + EXPECTED, "no_signal"),
            ('{"status":{"a":1},"attempts":2}', "no_signal"),
        )
        for reply, completion in cases:
            with self.subTest(input_size=len(reply)):
                x = self._check(self.json_case, reply, "fail")
                self.assertEqual((x.content, x.format, x.completion, x.reason),
                                 ("unknown", "violation", completion,
                                  "json_unparseable"))

    def test_contains_and_regex_failures_use_only_original_rule(self):
        experiment = load_experiment("experiments/smoke-001.json", ROOT)
        for case in experiment.cases:
            if case.assertion.type in ("contains", "regex"):
                x = self._check(case, "NO MATCH", "fail")
                self.assertEqual((x.reason, x.format),
                                 ("objective_rule_not_met", "not_assessed"))

    def test_provider_error_does_not_invent_content(self):
        result = grade(self.json_case, None, error_category="quota", latency_ms=8)
        x = assess_failure(self.json_case, result)
        self.assertEqual((x.content, x.format, x.completion, x.reason),
                         ("unavailable", "unavailable", "unavailable",
                          "provider_error"))

    def test_identity_and_forged_grades_are_rejected(self):
        wrong = grade(self.precedence, "MONITOR")
        with self.assertRaises(ContractError):
            assess_failure(self.untrusted, wrong)
        forged = CaseResult(wrong.id, "pass", wrong.assertion_type,
                            wrong.latency_ms, wrong.response, None)
        with self.assertRaises(ContractError):
            assess_failure(self.precedence, forged)

    def _fixture_results(self):
        return [
            grade(self.precedence, INCOMPLETE, latency_ms=5406),
            grade(self.untrusted, "MONITOR", latency_ms=443),
            grade(self.json_case, WRAPPED_WRONG, latency_ms=2108),
        ]

    def test_results_unchanged_and_canonical_report_valid(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            document, markdown = build_report(
                self.experiment, self._fixture_results(), run_id=RUN_ID,
                revision=SHA, timestamp_utc=UTC,
            )
        self.assertEqual(document["summary"], {
            "total": 3, "passed": 1, "failed": 2,
            "errors": 0, "pass_rate": 1 / 3,
        })
        self.assertIn("## Failure causes (diagnostic only; scores unchanged)", markdown)
        self.assertIn("| precedence-001 | unknown | violation | possible_incomplete | exact_prose_possible_incomplete |", markdown)
        self.assertIn("| json-boundary-001 | mismatch | violation | no_signal | json_content_and_format |", markdown)
        self.assertNotIn("| untrusted-001 | match |", markdown)
        self.assertNotIn("Step 1:", markdown)
        self.assertNotIn(WRAPPED_WRONG, markdown)
        self.assertEqual([item["status"] for item in document["cases"]],
                         ["fail", "pass", "fail"])
        self.assertNotIn("diagnostics", document)
        validate_reports(self.experiment, document, markdown,
                         run_id=RUN_ID, revision=SHA)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            write_report(output, document, markdown)
            validate_files(output, repo_root=ROOT, run_id=RUN_ID,
                           revision=SHA, manifest=MANIFEST)

    def test_tampering_with_diagnoses_cannot_pass_integrity(self):
        document, markdown = build_report(
            self.experiment, self._fixture_results(), run_id=RUN_ID,
            revision=SHA, timestamp_utc=UTC,
        )
        for bad in (
            markdown.replace("possible_incomplete", "no_signal"),
            markdown.replace("json_content_and_format", "json_format_only"),
            markdown.replace("mismatch | violation", "match | violation"),
        ):
            with self.subTest(length=len(bad)):
                with self.assertRaises(ContractError):
                    validate_reports(self.experiment, document, bad,
                                     run_id=RUN_ID, revision=SHA)
        forged = copy.deepcopy(document)
        forged["cases"][2]["status"] = "pass"
        with self.assertRaises(ContractError):
            validate_reports(self.experiment, forged, markdown,
                             run_id=RUN_ID, revision=SHA)

    def test_previous_manifests_and_caps_are_unchanged(self):
        for name in ("smoke-001", "advanced-001", "robustness-001"):
            exp = load_experiment(f"experiments/{name}.json", ROOT)
            self.assertEqual(exp.experiment_id, name)
        self.assertEqual(self.experiment.max_cases, 3)
        self.assertEqual(self.experiment.max_output_tokens, 64)
        self.assertEqual(self.experiment.repetitions, 1)


if __name__ == "__main__":
    unittest.main()
