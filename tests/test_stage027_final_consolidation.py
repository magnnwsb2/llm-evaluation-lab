"""Stage 027 final security and portfolio assertions, entirely offline."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_eval.contracts import (
    ACTIVE_INFERENCE_MODEL, HISTORICAL_MODEL, ContractError, load_experiment,
)
from llm_eval.model_comparison import suite_fingerprint
from llm_eval.providers.cloudflare import infer
from llm_eval.run_evaluation import LIVE_EXPERIMENTS, select_live_manifest
from llm_eval.scoring import grade

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ".github/workflows/manual-evaluation.yml"
SMOKE = ".github/workflows/cloudflare-smoke-test.yml"
PAGES = ".github/workflows/pages-dashboard.yml"
CI = ".github/workflows/offline-ci.yml"

HISTORICAL = ("smoke-001", "advanced-001", "robustness-001")
ACTIVE = ("smoke-002", "advanced-002", "robustness-002")
RUN_IDS = (
    "42504084221", "42511351245", "42519170795",
    "42527009736", "42527365653",
)
ZIP_SHA256 = (
    "9af4dc1ec2fa8d8fa79a8cc5837088a10413915db71da035f2f46492b88e25bd",
    "d53e422b0805c758dc761c61ae1b71f1a2a481cf53b792ed09ca196b4f303a3b",
    "01c1f896509b89ecff64346b4e29956f550bd6a6700975f0cc033aa3101ec7b3",
    "f556147b520ba22afbef0f50b6f9fa58384a2fecd99ca2c43f28c48fd6ae1cf8",
    "17ef418c22ce1009255735843d5a56b05fef66e1627521d288251eaa0214cc5a",
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class Stage027FinalConsolidationTests(unittest.TestCase):
    def test_real_transport_refuses_archived_model_before_any_http(self):
        historical = load_experiment("experiments/smoke-001.json", ROOT)
        self.assertEqual(historical.model, HISTORICAL_MODEL)
        with patch(
            "llm_eval.providers.cloudflare._post_json",
            side_effect=AssertionError("real provider transport forbidden"),
        ) as network, patch(
            "socket.socket", side_effect=AssertionError("no network allowed")
        ):
            with self.assertRaisesRegex(ContractError, "archived model"):
                infer(
                    historical, historical.cases[0],
                    account_id="a" * 32, api_token="synthetic-only",
                    # Critical: no injected transport, so enforce live guard.
                )
            network.assert_not_called()

    def test_old_model_offline_fake_transport_remains_for_archived_fixtures(self):
        historical = load_experiment("experiments/smoke-001.json", ROOT)
        seen = []
        def fake(*args):
            seen.append(args)
            return {"success": True, "result": {"response": "OK"}}
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            outcome = infer(historical, historical.cases[0],
                            account_id="a" * 32, api_token="synthetic",
                            transport=fake)
        self.assertEqual(outcome.text, "OK")
        self.assertEqual(len(seen), 1)

    def test_active_model_keeps_strict_token_budget_and_guarded_envelope(self):
        current = load_experiment("experiments/smoke-002.json", ROOT)
        sent = []
        def fake(url, token, body):
            sent.append((url, body))
            return {"success": True, "result": {
                "choices": [{"message": {"content": "OK"}}]
            }}
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            response = infer(current, current.cases[0],
                             account_id="a"*32, api_token="synthetic",
                             transport=fake)
        self.assertEqual(grade(current.cases[0], response.text).status, "pass")
        self.assertEqual(len(sent), 1)
        self.assertIn(ACTIVE_INFERENCE_MODEL, sent[0][0])
        body = sent[0][1]
        self.assertEqual(body["max_completion_tokens"], 64)
        self.assertNotIn("max_tokens", body)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})

    def test_both_manual_workflows_share_one_serial_execution_group(self):
        a = read(MANUAL)
        b = read(SMOKE)
        group = "  group: manual-workers-ai-inference"
        for source in (a, b):
            self.assertIn("  workflow_dispatch:", source)
            self.assertIn(group, source)
            self.assertIn("  cancel-in-progress: false", source)
            for forbidden in ("\n  push:", "\n  pull_request:", "\n  schedule:"):
                self.assertNotIn(forbidden, source)
        self.assertIn("retention-days: 7", a)
        self.assertIn("secrets.CLOUDFLARE_API_TOKEN", a)
        self.assertIn("vars.CLOUDFLARE_ACCOUNT_ID", a)
        self.assertNotIn("actions/cache@", a)

    def test_workflow_and_runner_reject_archived_or_unreviewed_live_inputs(self):
        script = read(MANUAL)
        self.assertEqual(LIVE_EXPERIMENTS, frozenset(ACTIVE))
        for old in HISTORICAL:
            self.assertNotIn("          - " + old, script)
            with self.assertRaises(ContractError):
                select_live_manifest(old)
        for new in ACTIVE:
            self.assertIn("          - " + new, script)
            self.assertEqual(select_live_manifest(new),
                             "experiments/" + new + ".json")
        self.assertIn("default: smoke-002", script)
        self.assertIn("select_live_manifest(", read("src/llm_eval/run_evaluation.py"))

    def test_versioned_legacy_and_current_suites_have_same_case_fingerprint(self):
        for old, new in zip(HISTORICAL, ACTIVE):
            historic = load_experiment("experiments/" + old + ".json", ROOT)
            current = load_experiment("experiments/" + new + ".json", ROOT)
            self.assertEqual(historic.model, HISTORICAL_MODEL)
            self.assertEqual(current.model, ACTIVE_INFERENCE_MODEL)
            self.assertEqual(historic.cases, current.cases)
            self.assertEqual(suite_fingerprint(historic), suite_fingerprint(current))
            self.assertEqual(historic.max_cases, 3)
            self.assertEqual(current.max_output_tokens, 64)
            self.assertEqual(current.repetitions, 1)

    def test_no_new_or_raw_model_snapshots_on_pages(self):
        folder = ROOT / "dashboard/approved"
        self.assertEqual(
            sorted(p.name for p in folder.glob("*.json")),
            ["advanced-001.json", "robustness-001.json", "smoke-001.json"],
        )
        forbidden = {"prompt", "response", "expected", "api_token", "secret"}
        def validate_keys(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden.isdisjoint(value))
                for child in value.values():
                    validate_keys(child)
            elif isinstance(value, list):
                for item in value:
                    validate_keys(item)
        for file in folder.glob("*.json"):
            validate_keys(json.loads(file.read_text(encoding="utf-8")))
        pages = read(PAGES)
        self.assertIn("actions/deploy-pages@v4", pages)
        self.assertNotIn("llm_eval.run_evaluation", pages)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", pages)

    def test_offline_ci_never_triggers_inference(self):
        ci = read(CI)
        self.assertIn("python -m unittest discover -s tests -v", ci)
        self.assertIn("python3 tools/security_check.py", ci)
        self.assertNotIn("llm_eval.run_evaluation", ci)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", ci)
        self.assertIn("permissions:\n  contents: read", ci)

    def test_sanitized_evidence_ledger_lists_actual_five_runs_and_zip_digests(self):
        ledger = read("docs/evidence/run-ledger-027.md")
        for run_id, digest in zip(RUN_IDS, ZIP_SHA256):
            with self.subTest(run_id=run_id):
                self.assertIn(run_id, ledger)
                self.assertIn(digest, ledger)
        self.assertIn("**9536, null, null**", ledger)
        self.assertIn("**765.67 ms**", ledger)
        self.assertIn("7-day retention", ledger)
        for forbidden in ("CLOUDFLARE_API_TOKEN=", '"response":', '"prompt":'):
            self.assertNotIn(forbidden, ledger)

    def test_readme_is_current_portfolio_entry_point_with_archived_history(self):
        readme = read("README.md")
        self.assertIn("Gemma 4", readme)
        self.assertIn("42527365653", readme)
        self.assertIn("42527009736", readme)
        self.assertIn("three independently reviewed historical", readme)
        self.assertIn("docs/reviews/final-audit-027.md", readme)
        self.assertIn("docs/history/readme-pre027-2026-11-08.md", readme)
        self.assertIn("SECURITY.md", readme)
        self.assertNotIn("no real Gemma result has been verified", readme)
        self.assertLess(len(readme), 16000)
        archived = read("docs/history/readme-pre027-2026-11-08.md")
        self.assertIn("Historical README archive", archived)
        self.assertGreater(len(archived), 28000)

    def test_public_artifact_boundary_and_skill_limitation_are_documented(self):
        security = read("SECURITY.md")
        agents = read("AGENTS.md")
        audit = read("docs/reviews/final-audit-027.md")
        self.assertIn("seven-day retention", security)
        self.assertIn("full synthetic model responses", security)
        self.assertIn("not executed", audit)
        self.assertIn("separate private", agents)
        self.assertIn("Workers Free", security)
        self.assertIn("Stage 027", read("docs/specs/001-llm-evaluation-lab.md"))


if __name__ == "__main__":
    unittest.main()
