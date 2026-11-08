"""Stage 017: offline failure analysis and reviewed evidence. No inference."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from llm_eval.contracts import load_experiment
from llm_eval.diagnostics import diagnose_json_object
from llm_eval.report_validation import validate_reports
from llm_eval.run_evaluation import build_report
from llm_eval.scoring import grade
from tools.validate_advanced_evidence import (
    EXPECTED, EvidenceError, SOURCE, read_evidence, validate_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
REVISION = "6f90b6a2e9cea68e9d6f4087cb2662ba562e734b"
RUN_ID = "42511351245"
TIMESTAMP = "2026-11-08T18:42:51+00:00"
WRAPPED_REAL = (
    "Here is the extracted data in JSON format:\n\n"
    "```\n{\n  \"ticket\": \"INC-042\",\n"
    "  \"priority\": \"high\",\n  \"retries\": 3\n}\n```"
)
CORRECT = '{"ticket":"INC-042","priority":"high","retries":3}'


class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.experiment = load_experiment("experiments/advanced-001.json", ROOT)
        cls.case = cls.experiment.cases[0]

    def diagnostic(self, response: str | None, *, error_category=None):
        result = grade(self.case, response, error_category=error_category)
        return result, diagnose_json_object(self.case, result).outcome

    def test_real_observed_wrapped_json_fails_strict_but_content_matches(self):
        result, outcome = self.diagnostic(WRAPPED_REAL)
        self.assertEqual(result.status, "fail")
        self.assertEqual(outcome, "content_match_format_violation")

    def test_strict_json_passes_without_promotion(self):
        result, outcome = self.diagnostic(CORRECT)
        self.assertEqual(result.status, "pass")
        self.assertEqual(outcome, "strict_pass")

    def test_unique_wrong_json_is_content_mismatch(self):
        for response in (
            '{"ticket":"INC-043","priority":"high","retries":3}',
            '{"ticket":"INC-042","priority":"high","retries":"3"}',
            '{"ticket":"INC-042","priority":"high","retries":3,"extra":1}',
            "The data: " + '{"ticket":"INC-042","priority":"low","retries":3}',
        ):
            with self.subTest(response=response):
                result, outcome = self.diagnostic(response)
                self.assertEqual(result.status, "fail")
                self.assertEqual(outcome, "content_mismatch")

    def test_ambiguous_invalid_or_unsafe_json_is_unparseable(self):
        for response in (
            "nothing to parse", "{}", "prefix {broken",
            CORRECT + "\n" + CORRECT,
            CORRECT + "\n```\n" + CORRECT + "\n```",
            '{"ticket":"INC-042","priority":"high","retries":3,"retries":3}',
            '{"ticket":"INC-042","priority":"high","retries":NaN}',
            '{"ticket":"INC-042","priority":"high","retries":3.0}',
            '{"ticket":"INC-042","priority":"high","retries":[3]}',
            '{"ticket":"INC-042","priority":"high","retries":{"x":3}}',
            "{" * 5000,
        ):
            with self.subTest(length=len(response), prefix=response[:24]):
                result, outcome = self.diagnostic(response)
                self.assertEqual(result.status, "fail")
                self.assertEqual(outcome, "unparseable")

    def test_provider_error_is_unavailable(self):
        result, outcome = self.diagnostic(None, error_category="quota")
        self.assertEqual(result.status, "error")
        self.assertEqual(outcome, "unavailable")

    def test_real_case_report_is_canonical_and_score_is_unchanged(self):
        results = [
            grade(case, response, latency_ms=latency)
            for case, response, latency in zip(
                self.experiment.cases,
                [WRAPPED_REAL, "ESCALATE", "ESCALATE"],
                [2760, 670, 717],
            )
        ]
        document, markdown = build_report(
            self.experiment, results, run_id=RUN_ID,
            revision=REVISION, timestamp_utc=TIMESTAMP,
        )
        self.assertEqual(document["summary"], {
            "total": 3, "passed": 2, "failed": 1,
            "errors": 0, "pass_rate": 2 / 3,
        })
        self.assertIn("| json-ticket-001 | content_match_format_violation |", markdown)
        self.assertIn("| decision-001 | decision-002 | same |", markdown)
        self.assertNotIn("Here is the extracted", markdown)
        self.assertNotIn(CORRECT, markdown)
        validate_reports(self.experiment, document, markdown,
                         run_id=RUN_ID, revision=REVISION)
        with self.assertRaises(Exception):
            validate_reports(self.experiment, document,
                             markdown.replace("content_match_format_violation", "strict_pass"),
                             run_id=RUN_ID, revision=REVISION)


class ApprovedEvidenceTests(unittest.TestCase):
    def test_real_approved_snapshot_exact(self):
        document = read_evidence(ROOT / SOURCE)
        self.assertEqual(document, EXPECTED)
        self.assertEqual(document["run_id"], RUN_ID)
        self.assertEqual(document["cases"][0]["diagnostic"],
                         "content_match_format_violation")
        self.assertNotIn("response", json.dumps(document))
        self.assertNotIn("prompt", json.dumps(document))

    def test_rejects_forged_metadata_metrics_and_sensitive_fields(self):
        for field, value in (
            ("run_id", "0"),
            ("model", "unreviewed"),
            ("summary", {"total": 3, "passed": 3, "failed": 0,
                         "errors": 0, "pass_rate": 1.0}),
            ("response", "private raw text"),
            ("prompt", "sensitive"),
            ("token", "secret"),
        ):
            with self.subTest(field=field):
                altered = copy.deepcopy(EXPECTED)
                altered[field] = value
                with self.assertRaises(EvidenceError):
                    validate_evidence(altered)

    def test_rejects_forged_case_and_type_confusion(self):
        for change in (
            lambda x: x["cases"][0].update(latency_ms=1),
            lambda x: x["cases"][0].update(status="pass"),
            lambda x: x["cases"][0].update(response=CORRECT),
            lambda x: x["cases"][0].update(diagnostic="strict_pass"),
            lambda x: x["summary"].update(total=True),
            lambda x: x["summary"].update(pass_rate=float("nan")),
            lambda x: x["cases"].reverse(),
        ):
            altered = copy.deepcopy(EXPECTED)
            change(altered)
            with self.assertRaises(EvidenceError):
                validate_evidence(altered)

    def test_rejects_duplicate_keys_and_malformed_json(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "evidence.json"
            for data in (
                '{"run_id":"1","run_id":"2"}',
                '{"summary":NaN}',
                "not JSON",
                "{}" * 5000,
            ):
                with self.subTest(size=len(data)):
                    file.write_text(data, encoding="utf-8")
                    with self.assertRaises(EvidenceError):
                        read_evidence(file)


if __name__ == "__main__":
    unittest.main()
