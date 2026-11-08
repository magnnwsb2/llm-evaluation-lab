"""SDD-001 §5.13: offline cross-model report comparison without live inference."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from llm_eval.contracts import Assertion, Case, ContractError, load_experiment
from llm_eval.model_comparison import (
    COMPARISON_KIND, _destination, _source_folder, compare_models,
    main, suite_fingerprint,
)
from llm_eval.run_evaluation import build_report
from llm_eval.scoring import grade

ROOT = Path(__file__).resolve().parents[1]
REVISION_A = "a" * 40
REVISION_B = "b" * 40
TIMESTAMP = "2026-11-08T20:15:27+00:00"
MODEL_B = "@offline/fictional-second-model-for-unit-tests-only"


class MatchedModelComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = load_experiment("experiments/advanced-001.json", ROOT)
        # A future model identifier is a TEST FIXTURE ONLY, not in the
        # production model allowlist, manifests or workflow_dispatch choices.
        cls.alternative = replace(cls.original, model=MODEL_B,
                                  experiment_id="advanced-002")
        cls.correct = (
            '{"ticket":"INC-042","priority":"high","retries":3}',
            "ESCALATE", "ESCALATE",
        )

    def record(self, experiment, replies=None, *, run_id="30001",
               revision=REVISION_A, latencies=(10, 20, 30)):
        if replies is None:
            replies = self.correct
        results = [
            grade(case, reply, latency_ms=latencies[i])
            for i, (case, reply) in enumerate(zip(experiment.cases, replies))
        ]
        return build_report(
            experiment, results, run_id=run_id,
            revision=revision, timestamp_utc=TIMESTAMP,
        )

    def matched(self, left=None, right=None, exp_a=None, exp_b=None):
        a = self.original if exp_a is None else exp_a
        b = self.alternative if exp_b is None else exp_b
        left_doc, left_md = left if left is not None else self.record(a)
        right_doc, right_md = right if right is not None else self.record(
            b, replies=(self.correct[0], "MONITOR", "ESCALATE"),
            run_id="30002", revision=REVISION_B, latencies=(15, 25, 35),
        )
        return compare_models(a, left_doc, left_md, b, right_doc, right_md)

    def test_trusted_matched_cases_allow_only_descriptive_difference(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            output = self.matched()
        self.assertEqual(output["kind"], COMPARISON_KIND)
        self.assertEqual(output["schema_version"], "1.0")
        self.assertEqual(output["case_count"], 3)
        self.assertEqual(output["suite_sha256"], suite_fingerprint(self.original))
        self.assertEqual(output["suite_sha256"], suite_fingerprint(self.alternative))
        self.assertEqual([r["model"] for r in output["runs"]],
                         [self.original.model, MODEL_B])
        self.assertEqual([r["run_id"] for r in output["runs"]],
                         ["30001", "30002"])
        self.assertEqual([r["summary"]["passed"] for r in output["runs"]],
                         [3, 2])
        self.assertEqual([r["summary"]["failed"] for r in output["runs"]],
                         [0, 1])
        self.assertEqual([r["mean_http_latency_ms"] for r in output["runs"]],
                         [20, 25])
        self.assertEqual([r["observed_http_latencies"] for r in output["runs"]],
                         [3, 3])
        self.assertEqual(output["case_observations"][1], {
            "id": "decision-001", "left_status": "pass", "right_status": "fail"
        })
        self.assertEqual(output["interpretation"],
                         "descriptive_only_not_a_model_ranking")

    def test_serialized_observation_is_response_free_and_static(self):
        report = self.matched()
        text = json.dumps(report, ensure_ascii=False, allow_nan=False)
        for disallowed in (
            '"response"', '"prompt"', '"expected"', '"temperature"',
            '"api_token"', "CLOUDFLARE_API_TOKEN",
            "INC-042", "ESCALATE", "MONITOR", "Here is",
            '"token_usage"', "Neurons", '"billing"',
        ):
            with self.subTest(disallowed=disallowed):
                self.assertNotIn(disallowed, text)

    def test_suite_fingerprint_is_sensitive_to_full_contract(self):
        original = self.original
        self.assertEqual(suite_fingerprint(original),
                         suite_fingerprint(replace(original, model=MODEL_B)))
        cases = list(original.cases)
        modifications = (
            replace(cases[0], prompt=cases[0].prompt + "!"),
            replace(cases[0], assertion=Assertion(
                cases[0].assertion.type, '{"ticket":"X","priority":"high","retries":3}'
            )),
            replace(cases[0], id="altered-case-001"),
        )
        for item in modifications:
            altered = replace(original, cases=(item, *cases[1:]))
            with self.subTest(modification=item.id + str(len(item.prompt))):
                self.assertNotEqual(suite_fingerprint(original),
                                    suite_fingerprint(altered))
        self.assertNotEqual(suite_fingerprint(original),
                            suite_fingerprint(replace(
                                original, cases=tuple(reversed(cases))
                            )))

    def test_changed_prompt_case_order_or_scoring_prevents_comparison(self):
        other = self.alternative
        first = other.cases[0]
        changes = (
            replace(other, cases=(
                replace(first, prompt=first.prompt + " unreviewed"), *other.cases[1:]
            )),
            replace(other, cases=tuple(reversed(other.cases))),
            replace(other, cases=(
                replace(first, assertion=Assertion("contains", "INC-042")),
                *other.cases[1:]
            )),
            replace(other, cases=other.cases[:2]),
        )
        for changed in changes:
            with self.subTest(length=len(changed.cases)):
                with self.assertRaises(ContractError):
                    self.matched(exp_b=changed)

    def test_changed_budgets_or_provider_are_rejected(self):
        original = self.alternative
        for variant in (
            replace(original, provider="unapproved-provider"),
            replace(original, cases_file="cases/other.json"),
            replace(original, temperature=0.4),
            replace(original, max_cases=2),
            replace(original, repetitions=2),
            replace(original, max_output_tokens=63),
        ):
            with self.subTest(change=str(variant.max_output_tokens)+variant.provider):
                with self.assertRaises(ContractError):
                    self.matched(exp_b=variant)

    def test_same_model_is_not_a_cross_model_comparison(self):
        clone = replace(self.original, experiment_id="advanced-clone")
        with self.assertRaises(ContractError):
            self.matched(exp_b=clone)

    def test_different_suite_real_historical_runs_are_not_comparable(self):
        smoke = load_experiment("experiments/smoke-001.json", ROOT)
        different = replace(smoke, model=MODEL_B)
        # Evidence is internally valid for each suite; distinct prompts/IDs
        # cannot be turned into a cross-model ranking.
        left = self.record(self.original)
        replies = ("OK", "SUNRISE", "123")
        right = self.record(different, replies, run_id="30002", revision=REVISION_B)
        with self.assertRaises(ContractError):
            self.matched(left=left, right=right, exp_b=different)

    def test_forged_report_grade_and_canonical_md_are_rejected(self):
        legitimate = self.record(self.original)
        forged = copy.deepcopy(legitimate[0])
        forged["cases"][0]["status"] = "fail"
        with self.assertRaises(ContractError):
            self.matched(left=(forged, legitimate[1]))
        with self.assertRaises(ContractError):
            self.matched(left=(legitimate[0], legitimate[1] + "\nFake pass rate"))

    def test_forged_sha_model_identity_or_run_id_is_rejected(self):
        real = self.record(self.original)
        for key, value in (
            ("run_id", "not-numeric"),
            ("revision_sha", "not-a-sha"),
            ("model", "@cf/fake-model"),
            ("experiment_id", "invalid-name"),
        ):
            forged = copy.deepcopy(real[0])
            forged[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.matched(left=(forged, real[1]))

    def test_provider_errors_have_observed_only_latencies(self):
        a = self.original
        b = self.alternative
        error_results_a = [
            grade(case, None, latency_ms=(98 if i == 0 else None),
                  error_category="quota") for i, case in enumerate(a.cases)
        ]
        error_results_b = [
            grade(case, None, error_category="quota") for case in b.cases
        ]
        left = build_report(a, error_results_a, run_id="30001",
                            revision=REVISION_A, timestamp_utc=TIMESTAMP)
        right = build_report(b, error_results_b, run_id="30002",
                             revision=REVISION_B, timestamp_utc=TIMESTAMP)
        doc = self.matched(left=left, right=right)
        self.assertEqual([r["summary"]["errors"] for r in doc["runs"]], [3, 3])
        self.assertEqual([r["observed_http_latencies"] for r in doc["runs"]], [1, 0])
        self.assertEqual([r["mean_http_latency_ms"] for r in doc["runs"]], [98, None])
        self.assertEqual(doc["case_observations"][0]["left_status"], "error")
        self.assertEqual(doc["case_observations"][0]["right_status"], "error")
        self.assertIsNone(doc["runs"][0]["cases"][1]["latency_ms"])

    def test_duplicated_run_identity_is_not_a_pair(self):
        a = self.original
        b = self.alternative
        first = self.record(a)
        second = self.record(b, run_id="30001", revision=REVISION_A)
        with self.assertRaises(ContractError):
            self.matched(left=first, right=second)

    def test_cli_rejects_unapproved_model_execution_and_never_calls_network(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            with self.assertRaises(SystemExit) as cm:
                main([])
            self.assertEqual(cm.exception.code, 2)
            self.assertEqual(main([
                "--left-experiment", "advanced-001",
                "--right-experiment", "../unapproved",
                "--left-folder", "tests", "--right-folder", "tests",
            ]), 2)
        self.assertNotIn(MODEL_B, str(ROOT / "experiments/advanced-001.json"))

    def test_path_guard_denies_traversal_public_dirs_and_symlinks(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            folder = Path(tmp)
            same = folder.name
            self.assertEqual(_source_folder(ROOT, same), folder.resolve())
            for bad in ("../private", "/tmp", "dashboard/approved",
                        "_site", "comparison-output", "some\\directory", "."):
                with self.subTest(path=bad), self.assertRaises(ContractError):
                    _source_folder(ROOT, bad)
            symlink = folder / "link"
            symlink.symlink_to("/tmp")
            with self.assertRaises(ContractError):
                _source_folder(ROOT, same + "/link")
            with self.assertRaises(ContractError):
                _destination(ROOT, "../bad.json")
            with self.assertRaises(ContractError):
                _destination(ROOT, "invalid.txt")

    def test_comparison_output_is_not_published_automatically(self):
        import inspect
        from llm_eval import model_comparison
        script = inspect.getsource(model_comparison)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", script)
        self.assertNotIn("urllib.request", script)
        self.assertNotIn("requests.post", script)
        self.assertNotIn("GenUI", script)
        self.assertIn('OUTPUT_FOLDER = "comparison-output"', script)
        workflow = (ROOT / ".github/workflows/offline-ci.yml").read_text()
        self.assertNotIn("llm_eval.model_comparison", workflow)


if __name__ == "__main__":
    unittest.main()
