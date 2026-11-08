"""Offline tests for manual evaluation orchestration; no Cloudflare calls."""

import json
import tempfile
import unittest
from pathlib import Path

from llm_eval.contracts import load_experiment
from llm_eval.providers.cloudflare import InferenceResult, ProviderError
from llm_eval.run_evaluation import build_report, evaluate, write_report


class ManualEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.experiment = load_experiment(
            "experiments/smoke-001.json", Path(__file__).resolve().parents[1]
        )

    def test_success_and_prompt_noncompliance(self):
        answers = ["OK", "The SUNRISE is bright.", "Not three digits"]
        seen = []
        def fake(experiment, case, **kwargs):
            seen.append(case.id)
            return InferenceResult(answers[len(seen) - 1], 12)
        results = evaluate(self.experiment, account_id="a" * 32,
                           api_token="synthetic-token", inference=fake)
        self.assertEqual([r.status for r in results], ["pass", "pass", "fail"])
        self.assertEqual(len(seen), 3)
        doc, md = build_report(
            self.experiment, results, run_id="123", revision="abc",
            timestamp_utc="2026-11-08T00:00:00Z",
        )
        self.assertEqual(doc["summary"], {
            "total": 3, "passed": 2, "failed": 1, "errors": 0, "pass_rate": 2 / 3
        })
        self.assertEqual(doc["run_id"], "123")
        self.assertEqual(doc["revision_sha"], "abc")
        self.assertIn("2/3", md)
        self.assertNotIn("Not three digits", md)
        with tempfile.TemporaryDirectory() as folder:
            write_report(Path(folder), doc, md)
            loaded = json.loads((Path(folder) / "results.json").read_text())
            self.assertEqual(loaded["cases"][2]["status"], "fail")
            self.assertEqual(loaded["cases"][2]["response"], "Not three digits")
            self.assertIn("LLM evaluation", (Path(folder) / "report.md").read_text())

    def test_stop_on_first_provider_error_without_retries(self):
        calls = []
        def fake(experiment, case, **kwargs):
            calls.append(case.id)
            raise ProviderError("quota", latency_ms=100)
        results = evaluate(self.experiment, account_id="a" * 32,
                           api_token="synthetic-token", inference=fake)
        self.assertEqual(len(calls), 1)
        self.assertEqual([r.status for r in results], ["error"] * 3)
        self.assertEqual([r.error_category for r in results], ["quota"] * 3)
        self.assertEqual(results[0].latency_ms, 100)
        self.assertIsNone(results[1].latency_ms)
        doc, md = build_report(
            self.experiment, results, run_id="1", revision="abc",
            timestamp_utc="2026-11-08T00:00:00Z",
        )
        self.assertEqual(doc["summary"]["errors"], 3)
        self.assertNotIn("synthetic-token", json.dumps(doc) + md)

    def test_no_requests_after_second_case_error(self):
        seen = []
        def fake(experiment, case, **kwargs):
            seen.append(case.id)
            if len(seen) == 2:
                raise ProviderError("auth", latency_ms=20)
            return InferenceResult("OK", 15)
        results = evaluate(self.experiment, account_id="a" * 32,
                           api_token="synthetic-token", inference=fake)
        self.assertEqual(len(seen), 2)
        self.assertEqual([r.status for r in results], ["pass", "error", "error"])
        self.assertEqual(results[2].error_category, "auth")


if __name__ == "__main__":
    unittest.main()
