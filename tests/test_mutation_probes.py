"""Stage 025 synthetic rule sensitivity: never real inference evidence."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from llm_eval.contracts import Assertion, Case, ContractError, load_experiment
from llm_eval.mutation_probes import (
    PROBE_IDS, _probe_texts, analyze_assertion_sensitivity, main,
)

ROOT = Path(__file__).resolve().parents[1]


class MutationProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = load_experiment("experiments/smoke-001.json", ROOT)

    def one(self, kind, expected):
        return replace(
            self.base, cases=(Case("synthetic-001", "Do not publish this prompt",
                                   Assertion(kind, expected)),),
        )

    def test_exact_is_whitespace_tolerant_but_case_and_suffix_strict(self):
        output = analyze_assertion_sensitivity(self.one("exact", "OK"))
        self.assertEqual(output["cases"][0]["baseline_status"], "pass")
        self.assertEqual(
            [item["status"] for item in output["cases"][0]["probes"]],
            ["pass", "fail", "fail"],
        )

    def test_contains_is_case_sensitive_and_suffix_tolerant(self):
        output = analyze_assertion_sensitivity(self.one("contains", "SUNRISE"))
        self.assertEqual(
            [item["status"] for item in output["cases"][0]["probes"]],
            ["pass", "fail", "pass"],
        )

    def test_regex_baseline_pattern_not_a_guaranteed_matching_sample(self):
        output = analyze_assertion_sensitivity(self.one("regex", r"^[0-9]{3}$"))
        self.assertFalse(output["cases"][0]["baseline_guaranteed"])
        self.assertEqual(output["cases"][0]["baseline_status"], "fail")
        self.assertEqual(output["probe_count"], 3)
        self.assertEqual(output["probe_failed"], 3)

    def test_regex_source_may_match_itself_without_becoming_guaranteed(self):
        output = analyze_assertion_sensitivity(self.one("regex", "OK"))
        self.assertFalse(output["cases"][0]["baseline_guaranteed"])
        self.assertEqual(output["cases"][0]["baseline_status"], "pass")

    def test_json_object_rejects_non_json_wrappers_and_extra_text(self):
        case = self.one("json_object", '{"ticket":"INC-042","retries":3}')
        output = analyze_assertion_sensitivity(case)
        self.assertTrue(output["cases"][0]["baseline_guaranteed"])
        self.assertEqual(output["cases"][0]["baseline_status"], "pass")
        self.assertEqual(
            [item["status"] for item in output["cases"][0]["probes"]],
            ["pass", "fail", "fail"],
        )

    def test_case_swap_changes_only_ascii_letters(self):
        self.assertEqual(_probe_texts("AbÇ-1")[1], "aBÇ-1")
        self.assertEqual(PROBE_IDS, (
            "outer-whitespace", "case-swap", "append-marker"
        ))

    def test_approved_experiments_have_fixed_three_probes_per_case(self):
        for manifest in (
            "experiments/smoke-001.json",
            "experiments/advanced-001.json",
            "experiments/robustness-001.json",
        ):
            with self.subTest(manifest=manifest):
                experiment = load_experiment(manifest, ROOT)
                with patch("socket.socket", side_effect=AssertionError("network forbidden")):
                    output = analyze_assertion_sensitivity(experiment)
                self.assertEqual(output["case_count"], len(experiment.cases))
                self.assertEqual(output["probe_count"], len(experiment.cases) * 3)
                self.assertEqual(
                    output["probe_passed"] + output["probe_failed"],
                    output["probe_count"],
                )
                self.assertEqual(output["schema_version"], "1.0")
                self.assertEqual(output["kind"], "synthetic-objective-assertion-probes")
                self.assertEqual(output["interpretation"],
                                 "synthetic_rule_sensitivity_not_model_performance")

    def test_sanitized_output_does_not_contain_expected_or_mutated_text(self):
        experiment = self.one("exact", "SENSITIVE_EXPECTED_VALUE")
        output = analyze_assertion_sensitivity(experiment)
        serialized = json.dumps(output, ensure_ascii=False)
        for secret in (
            "SENSITIVE_EXPECTED_VALUE", "Do not publish this prompt",
            "__PROBE__", '"response"', '"expected"', '"prompt"',
            "Bearer ", "CLOUDFLARE_API_TOKEN",
        ):
            with self.subTest(value=secret):
                self.assertNotIn(secret, serialized)

    def test_empty_and_excessive_case_counts_rejected(self):
        with self.assertRaises(ContractError):
            analyze_assertion_sensitivity(replace(self.base, cases=()))
        with self.assertRaises(ContractError):
            analyze_assertion_sensitivity(replace(
                self.base, cases=self.base.cases * 2,
            ))

    def test_cli_rejects_unapproved_experiments_and_bad_output(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            self.assertEqual(main(["--experiment", "../private"]), 2)
            self.assertEqual(main([
                "--experiment", "smoke-001",
                "--output-name", "../public.json",
            ]), 2)
            self.assertEqual(main([
                "--experiment", "smoke-001",
                "--output-name", "payload.html",
            ]), 2)

    def test_cli_creates_once_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="stage025-") as tmp:
            output = Path(tmp) / "probes.json"
            with patch("llm_eval.mutation_probes._destination", return_value=output):
                with patch("socket.socket", side_effect=AssertionError("network forbidden")):
                    args = ["--experiment", "smoke-001", "--output-name", "probes.json"]
                    self.assertEqual(main(args), 0)
                    self.assertEqual(main(args), 2)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["probe_count"], 9)
            self.assertNotIn('"response"', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
