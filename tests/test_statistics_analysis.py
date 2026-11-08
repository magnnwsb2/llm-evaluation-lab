"""Stage 024: descriptive statistics and repeatability are strictly offline."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from llm_eval.contracts import ContractError, load_experiment
from llm_eval.run_evaluation import build_report, write_report
from llm_eval.scoring import grade
from llm_eval.statistics_analysis import (
    MAX_RUNS, analyze_runs, latency_statistics, main,
)

ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 40
SHA_B = "b" * 40
DATE = "2026-11-08T20:15:27+00:00"
RESPONSES = ('{"ticket":"INC-042","priority":"high","retries":3}',
             "ESCALATE", "ESCALATE")


class Stage024StatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.experiment = load_experiment("experiments/advanced-001.json", ROOT)

    def report(self, run="80001", *, sha=SHA_A, texts=RESPONSES,
               latency=(10, 20, 30), error_at=None):
        if error_at is None:
            scores = [
                grade(case, reply, latency_ms=latency[index])
                for index, (case, reply) in enumerate(
                    zip(self.experiment.cases, texts)
                )
            ]
        else:
            scores = []
            for index, case in enumerate(self.experiment.cases):
                if index < error_at:
                    scores.append(grade(case, texts[index],
                                        latency_ms=latency[index]))
                else:
                    scores.append(grade(
                        case, None, error_category="quota",
                        latency_ms=latency[index] if index == error_at else None,
                    ))
        return build_report(
            self.experiment, scores, run_id=run,
            revision=sha, timestamp_utc=DATE,
        )

    def test_known_latency_distribution_and_sample_stddev(self):
        numbers = latency_statistics([10, None, 20, 30])
        self.assertEqual(numbers, {
            "observed_count": 3,
            "minimum_ms": 10, "maximum_ms": 30,
            "mean_ms": 20, "median_ms": 20,
            "sample_stddev_ms": 10,
        })
        self.assertEqual(latency_statistics([100, 101])["sample_stddev_ms"], 0.707)
        self.assertEqual(latency_statistics([None, None]), {
            "observed_count": 0,
            "minimum_ms": None, "maximum_ms": None,
            "mean_ms": None, "median_ms": None,
            "sample_stddev_ms": None,
        })
        self.assertEqual(latency_statistics([17])["sample_stddev_ms"], None)
        with self.assertRaises(ContractError):
            latency_statistics([True, 12])
        with self.assertRaises(ContractError):
            latency_statistics([-1])

    def test_one_run_is_descriptive_not_repeatability(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = analyze_runs(self.experiment, [self.report()])
        self.assertEqual(result["kind"], "descriptive-repeatability-observation")
        self.assertEqual(result["run_count"], 1)
        self.assertEqual(result["repeatability"], "not_measurable_single_run")
        self.assertEqual(result["latency"]["mean_ms"], 20)
        self.assertEqual(result["latency"]["observed_count"], 3)
        self.assertEqual(result["runs"][0]["summary"]["passed"], 3)
        self.assertEqual(result["cases"][0]["comparable_response_pairs"], 0)
        self.assertIsNone(result["cases"][0]["response_pair_agreement_rate"])
        self.assertEqual(result["runs"][0]["identical_prompt_pairs"], [
            {"first_id": "decision-001", "second_id": "decision-002",
             "outcome": "same"}
        ])

    def test_two_run_repeatability_agreement_is_not_accuracy(self):
        wrong = ("not JSON", "WRONG", "WRONG")
        result = analyze_runs(
            self.experiment,
            [self.report("80001", texts=wrong),
             self.report("80002", texts=wrong)],
        )
        self.assertEqual(result["run_count"], 2)
        self.assertEqual(result["repeatability"],
                         "observed_pairs_only_not_general_reliability")
        for item in result["cases"]:
            self.assertEqual(item["pass"], 0)
            self.assertEqual(item["fail"], 2)
            self.assertEqual(item["comparable_response_pairs"], 1)
            self.assertEqual(item["agreeing_response_pairs"], 1)
            self.assertEqual(item["response_pair_agreement_rate"], 1.0)
        self.assertEqual(result["runs"][0]["identical_prompt_pairs"][0]["outcome"],
                         "same")

    def test_different_responses_keep_disagreement_distinct_from_grade(self):
        data = analyze_runs(
            self.experiment,
            [self.report("80001"),
             self.report("80002", texts=(RESPONSES[0], "WRONG", "WRONG"))],
        )
        self.assertEqual(data["cases"][0]["agreeing_response_pairs"], 1)
        self.assertEqual(data["cases"][1]["agreeing_response_pairs"], 0)
        self.assertEqual(data["cases"][1]["response_pair_agreement_rate"], 0.0)
        self.assertEqual((data["cases"][1]["pass"], data["cases"][1]["fail"]),
                         (1, 1))

    def test_three_run_pair_denominator_and_population_sample_separation(self):
        records = [
            self.report("80001", latency=(10, 20, 30)),
            self.report("80002", latency=(20, 30, 40)),
            self.report("80003", latency=(30, 40, 50)),
        ]
        result = analyze_runs(self.experiment, records)
        self.assertEqual(result["latency"]["observed_count"], 9)
        self.assertEqual(result["latency"]["minimum_ms"], 10)
        self.assertEqual(result["latency"]["maximum_ms"], 50)
        self.assertEqual(result["latency"]["mean_ms"], 30)
        self.assertEqual(result["cases"][0]["latency"]["median_ms"], 20)
        self.assertEqual(result["cases"][0]["comparable_response_pairs"], 3)
        self.assertEqual(result["cases"][0]["agreeing_response_pairs"], 3)

    def test_error_only_latencies_are_null_not_fake_zero(self):
        sample_a = self.report("80001", error_at=0, latency=(98, None, None))
        sample_b = self.report("80002", error_at=0, latency=(None, None, None))
        result = analyze_runs(self.experiment, [sample_a, sample_b])
        self.assertEqual(result["latency"]["observed_count"], 1)
        self.assertEqual(result["latency"]["mean_ms"], 98)
        self.assertIsNone(result["latency"]["sample_stddev_ms"])
        self.assertEqual(result["runs"][1]["latency"]["observed_count"], 0)
        self.assertIsNone(result["runs"][1]["latency"]["median_ms"])
        self.assertEqual(result["cases"][0]["error"], 2)
        self.assertEqual(result["cases"][0]["comparable_response_pairs"], 0)
        self.assertIsNone(result["cases"][0]["response_pair_agreement_rate"])
        self.assertEqual(result["runs"][0]["identical_prompt_pairs"][0]["outcome"],
                         "unavailable")

    def test_mixed_provider_failure_does_not_invent_pairs(self):
        sample = analyze_runs(
            self.experiment,
            [self.report("80001"), self.report("80002", error_at=1)],
        )
        self.assertEqual(sample["cases"][0]["comparable_response_pairs"], 1)
        self.assertEqual(sample["cases"][1]["comparable_response_pairs"], 0)
        self.assertEqual(sample["cases"][2]["comparable_response_pairs"], 0)
        self.assertEqual(sample["cases"][2]["error"], 1)

    def test_repeated_runs_require_unique_ids_and_same_commit(self):
        original = self.report("80001")
        for records in (
            [original, original],
            [original, self.report("80002", sha=SHA_B)],
        ):
            with self.subTest(run_count=len(records)):
                with self.assertRaises(ContractError):
                    analyze_runs(self.experiment, records)

    def test_forged_summary_response_status_or_md_is_rejected(self):
        original = self.report("80001")
        for key, bad in (
            ("summary", lambda d: d["summary"].update(passed=0)),
            ("status", lambda d: d["cases"][0].update(status="fail")),
            ("model", lambda d: d.update(model="other")),
            ("prompt", lambda d: d["cases"][0].update(prompt="private")),
            ("revision", lambda d: d.update(revision_sha="bad")),
            ("run_id", lambda d: d.update(run_id="invalid")),
        ):
            modified = copy.deepcopy(original[0])
            bad(modified)
            with self.subTest(key=key), self.assertRaises(ContractError):
                analyze_runs(self.experiment, [(modified, original[1])])
        with self.assertRaises(ContractError):
            analyze_runs(self.experiment, [(original[0], original[1] + " forged")])

    def test_other_suite_or_model_cannot_be_passed_as_this_experiment(self):
        smoke = load_experiment("experiments/smoke-001.json", ROOT)
        sample = self.report("80001")
        with self.assertRaises(ContractError):
            analyze_runs(smoke, [sample])
        with self.assertRaises(ContractError):
            analyze_runs(replace(self.experiment, model="unapproved-model"), [sample])

    def test_invalid_input_count_and_types(self):
        sample = self.report("80001")
        for value in ([], [sample] * (MAX_RUNS + 1), None, "raw"):
            with self.subTest(value=str(type(value))):
                with self.assertRaises(ContractError):
                    analyze_runs(self.experiment, value)
        with self.assertRaises(ContractError):
            analyze_runs(self.experiment, [("not JSON", "markdown")])

    def test_sanitized_output_excludes_prompts_and_provider_content(self):
        output = analyze_runs(self.experiment, [self.report("80001")])
        serialized = json.dumps(output, ensure_ascii=False, allow_nan=False)
        for forbidden in (
            '"prompt"', '"expected"', '"response"', "INC-042", "ESCALATE",
            "CLOUDFLARE_API_TOKEN", "Bearer ", "token_usage",
            '"raw_markdown"', "Neurons", '"confidence_interval"',
            '"significance"', '"p95"', "ranking",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_offline_cli_reads_approved_artifact_without_network(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="stage024-") as temporary:
            folder = Path(temporary)
            sub = folder / "run"
            first = self.report("80001")
            write_report(sub, first[0], first[1])
            result_file = folder / "output.json"
            relative = folder.name + "/run"
            with patch("llm_eval.statistics_analysis._destination",
                       return_value=result_file):
                with patch("socket.socket", side_effect=AssertionError("network forbidden")):
                    rc = main([
                        "--experiment", "advanced-001",
                        "--folders", relative,
                        "--output-name", "observation.json",
                    ])
            self.assertEqual(rc, 0)
            data = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertEqual(data["run_count"], 1)
            self.assertNotIn('"response"', result_file.read_text(encoding="utf-8"))

    def test_cli_refuses_unreviewed_selection_and_noncanonical_folder(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.assertEqual(main([
                "--experiment", "unapproved",
                "--folders", "tests",
            ]), 2)
            self.assertEqual(main([
                "--experiment", "advanced-001",
                "--folders", "../private",
            ]), 2)
            self.assertEqual(main([
                "--experiment", "advanced-001",
                "--folders", "dashboard/approved",
            ]), 2)
            self.assertEqual(main([
                "--experiment", "advanced-001",
                "--folders", *["tests"] * 6,
            ]), 2)

    def test_cli_rejects_symlinked_results_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="stage024-") as temporary:
            folder = Path(temporary)
            (folder / "results.json").symlink_to("/etc/hosts")
            (folder / "report.md").write_text("invalid", encoding="utf-8")
            with self.assertRaises(ContractError):
                # Core parser guard is explicit, not only the report validator.
                from llm_eval.statistics_analysis import _reject
                _reject()
            self.assertEqual(main([
                "--experiment", "advanced-001",
                "--folders", folder.name,
            ]), 2)


if __name__ == "__main__":
    unittest.main()
