"""Stage 026: offline-only Gemma 4 migration and archive preservation tests.

No Cloudflare access, real API keys, or provider performance claims.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from llm_eval.contracts import (
    ACTIVE_INFERENCE_MODEL, FREE_MODEL_ALLOWLIST, HISTORICAL_MODEL,
    ContractError, load_experiment,
)
from llm_eval.model_comparison import compare_models, suite_fingerprint
from llm_eval.providers.cloudflare import ProviderError, infer
from llm_eval.run_evaluation import (
    APPROVED_EXPERIMENTS, LIVE_EXPERIMENTS, build_report,
    main as runner_main, select_live_manifest, select_manifest,
)
from llm_eval.report_validation import validate_reports
from llm_eval.scoring import grade

ROOT = Path(__file__).resolve().parents[1]
OLD = ("smoke-001", "advanced-001", "robustness-001")
NEW = ("smoke-002", "advanced-002", "robustness-002")
REV_A = "a" * 40
REV_B = "b" * 40


class GemmaModelMigrationTests(unittest.TestCase):
    def test_six_versioned_manifests_and_identical_historical_suites(self):
        self.assertEqual(len(FREE_MODEL_ALLOWLIST), 2)
        self.assertIn(HISTORICAL_MODEL, FREE_MODEL_ALLOWLIST)
        self.assertIn(ACTIVE_INFERENCE_MODEL, FREE_MODEL_ALLOWLIST)
        self.assertEqual(LIVE_EXPERIMENTS, frozenset(NEW))
        self.assertEqual(set(APPROVED_EXPERIMENTS), set(OLD + NEW))
        for old_id, new_id in zip(OLD, NEW):
            with self.subTest(experiment=new_id):
                historical = load_experiment(select_manifest(old_id), ROOT)
                live = load_experiment(select_live_manifest(new_id), ROOT)
                self.assertEqual(historical.model, HISTORICAL_MODEL)
                self.assertEqual(live.model, ACTIVE_INFERENCE_MODEL)
                self.assertEqual(historical.cases, live.cases)
                self.assertEqual(suite_fingerprint(historical), suite_fingerprint(live))
                self.assertEqual(historical.cases_file, live.cases_file)
                self.assertEqual(historical.provider, live.provider)
                self.assertEqual(historical.temperature, live.temperature)
                self.assertEqual(historical.max_cases, live.max_cases)
                self.assertEqual(live.repetitions, 1)
                self.assertEqual(live.max_output_tokens, 64)

    def test_only_new_experiments_can_be_selected_for_real_calls(self):
        for old_id in OLD:
            self.assertTrue(select_manifest(old_id).startswith("experiments/"))
            with self.subTest(old=old_id), self.assertRaises(ContractError):
                select_live_manifest(old_id)
        for invalid in ("", "../private", "smoke-002 ", "SMOKE-002", None, False, 2):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ContractError):
                select_live_manifest(invalid)

    def test_live_workflows_only_dispatch_new_models_and_never_auto_run(self):
        manual = (ROOT / ".github/workflows/manual-evaluation.yml").read_text(
            encoding="utf-8"
        )
        legacy_smoke = (ROOT / ".github/workflows/cloudflare-smoke-test.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("  workflow_dispatch:", manual)
        self.assertIn("  workflow_dispatch:", legacy_smoke)
        self.assertIn("default: smoke-002", manual)
        for new_id in NEW:
            self.assertIn(f"          - {new_id}", manual)
        for old_id in OLD:
            self.assertNotIn(f"          - {old_id}", manual)
        for workflow in (manual, legacy_smoke):
            self.assertNotIn("\n  push:", workflow)
            self.assertNotIn("\n  pull_request:", workflow)
            self.assertNotIn("\n  schedule:", workflow)
        self.assertIn('select_live_manifest("smoke-002")', legacy_smoke)
        self.assertNotIn('model = "@cf/meta/llama-', legacy_smoke)
        self.assertNotIn("urllib.request.urlopen", legacy_smoke)
        self.assertIn("python -m llm_eval.run_evaluation", manual)
        self.assertIn("secrets.CLOUDFLARE_API_TOKEN", manual)

    def test_real_runner_defaults_to_current_model_and_rejects_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {
                "EVALUATION_EXPERIMENT": "smoke-001",
                "EVALUATION_OUTPUT_DIR": folder,
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                "CLOUDFLARE_API_TOKEN": "synthetic-test-value",
            }):
                with patch("socket.socket", side_effect=AssertionError("network forbidden")):
                    with contextlib.redirect_stderr(io.StringIO()) as errors:
                        self.assertEqual(runner_main(), 2)
                self.assertIn("contract validation failed", errors.getvalue())
                self.assertNotIn("synthetic-test-value", errors.getvalue())

    def test_gemma_adapter_uses_explicit_new_completion_cap_one_request(self):
        exp = load_experiment("experiments/smoke-002.json", ROOT)
        seen = []
        def fake(url, token, body):
            seen.append((url, token, body))
            return {
                "success": True,
                "result": {"choices": [{
                    "message": {"role": "assistant", "content": " OK "},
                    "finish_reason": "stop",
                }]},
            }
        ticks = iter([4.0, 4.03])
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = infer(exp, exp.cases[0], account_id="a"*32,
                           api_token="synthetic-not-a-real-token",
                           transport=fake, clock=lambda: next(ticks))
        self.assertEqual(result.text, " OK ")
        self.assertEqual(result.latency_ms, 30)
        self.assertEqual(len(seen), 1)
        url, token, payload = seen[0]
        self.assertTrue(url.endswith("/ai/run/" + ACTIVE_INFERENCE_MODEL))
        self.assertEqual(token, "synthetic-not-a-real-token")
        self.assertEqual(payload["max_completion_tokens"], 64)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertIs(payload["stream"], False)
        self.assertEqual(grade(exp.cases[0], result.text).status, "pass")

    def test_legacy_archived_adapter_does_not_inject_gemma_only_thinking_flag(self):
        exp = load_experiment("experiments/smoke-001.json", ROOT)
        seen = []
        result = infer(
            exp, exp.cases[0], account_id="a"*32,
            api_token="synthetic",
            transport=lambda url, token, body: (
                seen.append(body) or {"success": True, "result": {"response": "OK"}}
            ),
        )
        self.assertEqual(result.text, "OK")
        self.assertEqual(len(seen), 1)
        self.assertNotIn("chat_template_kwargs", seen[0])
        self.assertEqual(seen[0]["max_tokens"], 64)

    def test_empty_gemma_answer_still_fails_closed_without_retry(self):
        exp = load_experiment("experiments/smoke-002.json", ROOT)
        requests = []
        def fake(url, token, body):
            requests.append(body)
            return {"success": True, "result": {
                "choices": [{"message": {"role": "assistant", "content": ""}}]
            }}
        with self.assertRaises(ProviderError) as failure:
            infer(exp, exp.cases[0], account_id="a"*32,
                  api_token="synthetic", transport=fake)
        self.assertEqual(failure.exception.category, "invalid_response")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["max_completion_tokens"], 64)
        self.assertEqual(requests[0]["chat_template_kwargs"], {"enable_thinking": False})

    def test_validated_new_envelopes_legacy_response_and_chat_choice(self):
        exp = load_experiment("experiments/smoke-002.json", ROOT)
        for result_payload in (
            {"response": "OK"},
            {"choices": [{"message": {"content": "OK"}}]},
        ):
            with self.subTest(keys=list(result_payload)):
                result = infer(
                    exp, exp.cases[0],
                    account_id="a"*32, api_token="synthetic",
                    transport=lambda *_: {"success": True, "result": result_payload}
                )
                self.assertEqual(result.text, "OK")

    def test_malformed_or_ambiguous_payloads_fail_closed(self):
        exp = load_experiment("experiments/smoke-002.json", ROOT)
        payloads = (
            {"response": "OK", "choices": [{"message": {"content": "OK"}}]},
            {"choices": []},
            {"choices": [{"message": {"content": "OK"}}, {"message": {"content": "NO"}}]},
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": [{"text": "OK"}]}}]},
            {"choices": [{"message": {"content": None}}]},
            {"choices": [{"message": 123}]},
            {"choices": "unexpected"},
            {"response": ""},
            {"response": 42},
            {},
        )
        for item in payloads:
            with self.subTest(payload_type=list(item)):
                with self.assertRaises(ProviderError) as err:
                    infer(
                        exp, exp.cases[0],
                        account_id="a"*32, api_token="synthetic",
                        transport=lambda *_: {"success": True, "result": item}
                    )
                self.assertEqual(err.exception.category, "invalid_response")
                self.assertNotIn(str(item), str(err.exception))

    def test_nonfree_model_is_rejected_before_any_transport(self):
        exp = load_experiment("experiments/smoke-002.json", ROOT)
        for illegal in (
            "@cf/moonshotai/kimi-k2.7-code",
            "@cf/zai-org/glm-5.3",
            "@cf/unknown/model",
        ):
            with self.subTest(illegal=illegal):
                with self.assertRaises(ContractError):
                    infer(
                        replace(exp, model=illegal), exp.cases[0],
                        account_id="a"*32, api_token="synthetic",
                        transport=lambda *_: self.fail("provider must not be called"),
                    )

    def test_new_report_validates_and_matching_history_comparison_is_offline(self):
        old = load_experiment("experiments/smoke-001.json", ROOT)
        new = load_experiment("experiments/smoke-002.json", ROOT)
        responses = [case.assertion.expected for case in new.cases]
        results_old = [grade(c, answer, latency_ms=10) for c, answer in zip(old.cases, responses)]
        results_new = [grade(c, answer, latency_ms=12) for c, answer in zip(new.cases, responses)]
        prev = build_report(
            old, results_old, run_id="100001", revision=REV_A,
            timestamp_utc="2026-11-08T00:00:00Z"
        )
        current = build_report(
            new, results_new, run_id="100002", revision=REV_B,
            timestamp_utc="2026-11-08T00:00:00Z"
        )
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            validate_reports(old, prev[0], prev[1],
                             run_id="100001", revision=REV_A)
            validate_reports(new, current[0], current[1],
                             run_id="100002", revision=REV_B)
            compared = compare_models(old, *prev, new, *current)
        self.assertEqual(compared["case_count"], 3)
        self.assertEqual(compared["suite_sha256"], suite_fingerprint(old))
        self.assertEqual([r["model"] for r in compared["runs"]],
                         [HISTORICAL_MODEL, ACTIVE_INFERENCE_MODEL])


if __name__ == "__main__":
    unittest.main()
