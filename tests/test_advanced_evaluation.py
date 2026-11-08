"""Stage 016: objective structured extraction and repeat observations, offline only."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from llm_eval.contracts import Assertion, Case, ContractError, load_experiment
from llm_eval.json_object import objects_match, parse_flat_object
from llm_eval.providers.cloudflare import InferenceResult, ProviderError
from llm_eval.report_validation import validate_files, validate_reports
from llm_eval.reproducibility import compare_identical_prompts
from llm_eval.run_evaluation import (
    build_report, evaluate, select_manifest, write_report,
)
from llm_eval.scoring import grade


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "16001"
REVISION = "f" * 40
TIMESTAMP = "2026-11-08T18:00:00+00:00"
EXPECTED = '{"ticket":"INC-042","priority":"high","retries":3}'


class AdvancedContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.experiment = load_experiment("experiments/advanced-001.json", ROOT)

    def test_advanced_is_bounded_and_reuses_approved_model(self):
        experiment = self.experiment
        self.assertEqual(experiment.experiment_id, "advanced-001")
        self.assertEqual(experiment.max_cases, 3)
        self.assertEqual(experiment.max_output_tokens, 64)
        self.assertEqual(experiment.repetitions, 1)
        self.assertEqual(len(experiment.cases), 3)
        self.assertEqual([x.assertion.type for x in experiment.cases],
                         ["json_object", "exact", "exact"])
        self.assertEqual(experiment.cases[1].prompt, experiment.cases[2].prompt)
        self.assertEqual(experiment.cases[1].assertion.expected, "ESCALATE")

    def test_allowlist_selector_only(self):
        self.assertEqual(select_manifest("smoke-001"), "experiments/smoke-001.json")
        self.assertEqual(select_manifest("advanced-001"), "experiments/advanced-001.json")
        for bad in ("", "experimental.json", "../cases/advanced.json", "ADVANCED-001",
                    "advanced-001/../smoke-001", None, 2, True):
            with self.subTest(value=repr(bad)), self.assertRaises(ContractError):
                select_manifest(bad)

    def test_bad_json_expected_is_rejected_before_inference(self):
        originals = json.loads((ROOT / "cases/advanced.json").read_text(encoding="utf-8"))
        manifest = (ROOT / "experiments/advanced-001.json").read_text(encoding="utf-8")
        bad = (
            "{}", "[]", "not JSON", '{"a":1,"a":2}', '{"a":[1]}',
            '{"a":{"b":2}}', '{"a":NaN}', '{"a":1.5}',
            '{"1bad":"x"}', '{"a": "x", "b": "y", "c": 1, "d": 2,'
            ' "e": 3, "f": 4, "g": 5, "h": 6, "i": 7}',
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "cases").mkdir()
            (root / "experiments").mkdir()
            (root / "experiments" / "advanced-001.json").write_text(
                manifest, encoding="utf-8"
            )
            for value in bad:
                with self.subTest(expected=value):
                    cases = copy.deepcopy(originals)
                    cases["cases"][0]["assertion"]["expected"] = value
                    (root / "cases" / "advanced.json").write_text(
                        json.dumps(cases), encoding="utf-8"
                    )
                    with self.assertRaises(ContractError):
                        load_experiment("experiments/advanced-001.json", root)


class JsonObjectScoringTests(unittest.TestCase):
    def setUp(self):
        self.case = Case("json-ticket-001", "synthetic input",
                         Assertion("json_object", EXPECTED))

    def test_valid_object_accepts_key_order_and_outer_whitespace(self):
        value = '  {"retries":3, "priority":"high", "ticket":"INC-042"}\n'
        self.assertTrue(objects_match(value, EXPECTED))
        self.assertEqual(grade(self.case, value, latency_ms=18).status, "pass")

    def test_noncompliance_is_fail_not_provider_error(self):
        examples = (
            "some explanation " + EXPECTED, " ```json\n" + EXPECTED + "\n``` ",
            '{"ticket":"INC-042","priority":"high","retries":"3"}',
            '{"ticket":"INC-042","priority":"high","retries":3,"extra":1}',
            '{"ticket":"INC-042","priority":"high"}',
            '{"ticket":"INC-042","priority":"high","retries":3,"retries":3}',
            '{"ticket":"INC-042","priority":"high","retries":NaN}',
            '{"ticket":"INC-042","priority":"high","retries":3.0}',
            '[{"ticket":"INC-042","priority":"high","retries":3}]',
            '', '{"ticket":', '{"ticket":"INC-043","priority":"high","retries":3}',
        )
        for value in examples:
            with self.subTest(length=len(value)):
                graded = grade(self.case, value)
                self.assertEqual(graded.status, "fail")
                self.assertIsNone(graded.error_category)

    def test_strict_bool_vs_int_and_json_scalars(self):
        self.assertFalse(objects_match('{"flag":true}', '{"flag":1}'))
        self.assertFalse(objects_match('{"flag":1}', '{"flag":true}'))
        self.assertTrue(objects_match('{"flag":true,"none":null}', '{"none":null,"flag":true}'))
        self.assertTrue(objects_match('{"negative":-2}', '{"negative":-2}'))
        with self.assertRaises(ContractError):
            parse_flat_object('{"bad":1.0}', max_chars=1000)

    def test_bounded_response_length(self):
        self.assertFalse(objects_match(EXPECTED + (" " * 5000), EXPECTED))


class RepeatedPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.experiment = load_experiment("experiments/advanced-001.json", ROOT)

    def fake_results(self, replies: list[str]):
        seen = []

        def inference(experiment, case, **kwargs):
            seen.append(case.id)
            return InferenceResult(replies[len(seen) - 1], 12)

        result = evaluate(self.experiment, account_id="a" * 32,
                          api_token="local-fixture-only", inference=inference)
        self.assertEqual(len(seen), 3)
        return result

    def report(self, results):
        return build_report(
            self.experiment, results, run_id=RUN_ID,
            revision=REVISION, timestamp_utc=TIMESTAMP,
        )

    def test_same_responses_and_canonical_integrity(self):
        results = self.fake_results([EXPECTED, "ESCALATE", " ESCALATE\n"])
        self.assertEqual([x.status for x in results], ["pass", "pass", "pass"])
        agreements = compare_identical_prompts(self.experiment, results)
        self.assertEqual(len(agreements), 1)
        self.assertEqual(agreements[0].outcome, "same")
        doc, md = self.report(results)
        self.assertIn("| decision-001 | decision-002 | same |", md)
        self.assertIn("Same does not imply correct", md)
        self.assertNotIn(EXPECTED, md)
        self.assertEqual(doc["summary"]["passed"], 3)
        self.assertEqual(doc["schema_version"], "1.0")
        self.assertNotIn("agreement", doc)
        validate_reports(self.experiment, doc, md, run_id=RUN_ID, revision=REVISION)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_report(folder, doc, md)
            validate_files(folder, repo_root=ROOT, run_id=RUN_ID,
                           revision=REVISION, manifest="experiments/advanced-001.json")

    def test_same_wrong_answers_are_not_misclassified_as_correct(self):
        results = self.fake_results([EXPECTED, "MONITOR", "MONITOR"])
        self.assertEqual([x.status for x in results], ["pass", "fail", "fail"])
        self.assertEqual(compare_identical_prompts(self.experiment, results)[0].outcome,
                         "same")

    def test_different_responses_are_distinct_from_objective_grade(self):
        results = self.fake_results([EXPECTED, "ESCALATE", "MONITOR"])
        self.assertEqual([x.status for x in results], ["pass", "pass", "fail"])
        self.assertEqual(compare_identical_prompts(self.experiment, results)[0].outcome,
                         "different")
        doc, md = self.report(results)
        validate_reports(self.experiment, doc, md, run_id=RUN_ID, revision=REVISION)

    def test_provider_error_makes_agreement_unavailable_and_stops(self):
        seen = []

        def inference(experiment, case, **kwargs):
            seen.append(case.id)
            if len(seen) == 2:
                raise ProviderError("quota", latency_ms=15)
            return InferenceResult(EXPECTED, 5)

        results = evaluate(self.experiment, account_id="a" * 32,
                           api_token="local-fixture-only", inference=inference)
        self.assertEqual(len(seen), 2)
        self.assertEqual([x.status for x in results], ["pass", "error", "error"])
        self.assertEqual(compare_identical_prompts(self.experiment, results)[0].outcome,
                         "unavailable")
        doc, md = self.report(results)
        self.assertIn("| decision-001 | decision-002 | unavailable |", md)
        validate_reports(self.experiment, doc, md, run_id=RUN_ID, revision=REVISION)

    def test_forged_advanced_grade_is_rejected(self):
        results = self.fake_results([EXPECTED, "ESCALATE", "MONITOR"])
        doc, md = self.report(results)
        altered = copy.deepcopy(doc)
        altered["cases"][2]["status"] = "pass"
        with self.assertRaises(ContractError):
            validate_reports(self.experiment, altered, md,
                             run_id=RUN_ID, revision=REVISION)

    def test_case_order_mismatch_rejected(self):
        results = self.fake_results([EXPECTED, "ESCALATE", "ESCALATE"])
        shuffled = [results[1], results[0], results[2]]
        with self.assertRaises(ContractError):
            compare_identical_prompts(self.experiment, shuffled)

    def test_legacy_manifest_has_no_repeated_prompt_section(self):
        legacy = load_experiment("experiments/smoke-001.json", ROOT)
        results = [
            grade(case, expected, latency_ms=12)
            for case, expected in zip(legacy.cases, ["OK", "SUNRISE", "123"])
        ]
        self.assertFalse(compare_identical_prompts(legacy, results))
        doc, md = build_report(legacy, results, run_id=RUN_ID,
                               revision=REVISION, timestamp_utc=TIMESTAMP)
        self.assertNotIn("Repeated-prompt agreement", md)
        validate_reports(legacy, doc, md, run_id=RUN_ID, revision=REVISION)


if __name__ == "__main__":
    unittest.main()
