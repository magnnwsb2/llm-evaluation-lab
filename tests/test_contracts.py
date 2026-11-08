"""Offline contract tests: no token, hosted model, or network access required."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_eval.contracts import ContractError, load_experiment


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "experiments").mkdir()
        (self.root / "cases").mkdir()
        self.manifest = {
            "schema_version": "1.0",
            "experiment_id": "smoke-001",
            "description": "Public synthetic experiment",
            "provider": "cloudflare-workers-ai",
            "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
            "cases_file": "cases/smoke.json",
            "max_cases": 3,
            "repetitions": 1,
            "max_output_tokens": 64,
            "temperature": 0,
        }
        self.cases = {
            "schema_version": "1.0",
            "cases": [
                {
                    "id": "case-001",
                    "prompt": "Reply with OK",
                    "assertion": {"type": "exact", "expected": "OK"},
                }
            ],
        }
        self.persist()

    def persist(self):
        (self.root / "experiments" / "smoke-001.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        (self.root / "cases" / "smoke.json").write_text(
            json.dumps(self.cases), encoding="utf-8"
        )

    def load(self):
        return load_experiment("experiments/smoke-001.json", self.root)

    def test_valid_manifest_and_cases(self):
        config = self.load()
        self.assertEqual(config.experiment_id, "smoke-001")
        self.assertEqual(config.model, "@cf/meta/llama-3.1-8b-instruct-fp8")
        self.assertEqual(len(config.cases), 1)

    def test_load_never_uses_network(self):
        with patch("socket.socket", side_effect=AssertionError("network is forbidden")):
            self.assertEqual(len(self.load().cases), 1)

    def test_disallowed_provider_or_model(self):
        self.manifest["model"] = "@cf/example/paid-only"
        self.persist()
        with self.assertRaisesRegex(ContractError, "allowlist"):
            self.load()
        self.manifest["model"] = "@cf/meta/llama-3.1-8b-instruct-fp8"
        self.manifest["provider"] = "not-cloudflare"
        self.persist()
        with self.assertRaises(ContractError):
            self.load()

    def test_rejects_over_budget_and_boolean_numeric_values(self):
        for key, bad in [
            ("max_cases", 4), ("max_cases", True),
            ("repetitions", 2), ("max_output_tokens", 65),
            ("max_output_tokens", 0), ("temperature", True),
            ("temperature", 1.1), ("temperature", float("nan")),
        ]:
            with self.subTest(key=key, bad=bad):
                self.manifest[key] = bad
                self.persist()
                with self.assertRaises(ContractError):
                    self.load()
                self.setUp_safe_manifest()

    def setUp_safe_manifest(self):
        self.manifest.update({
            "max_cases": 3, "repetitions": 1,
            "max_output_tokens": 64, "temperature": 0,
        })

    def test_rejects_missing_and_extra_manifest_fields(self):
        self.manifest.pop("cases_file")
        self.persist()
        with self.assertRaises(ContractError):
            self.load()
        self.manifest["cases_file"] = "cases/smoke.json"
        self.manifest["unknown"] = "not allowed"
        self.persist()
        with self.assertRaises(ContractError):
            self.load()

    def test_rejects_path_traversal_and_windows_paths(self):
        for bad in (
            "../cases/smoke.json",
            "cases/../cases/smoke.json",
            "/tmp/smoke.json",
            "cases\\smoke.json",
            "cases//smoke.json",
            "cases/smoke.txt",
        ):
            with self.subTest(path=bad):
                self.manifest["cases_file"] = bad
                self.persist()
                with self.assertRaises(ContractError):
                    self.load()

    def test_rejects_manifest_outside_expected_directory(self):
        with self.assertRaises(ContractError):
            load_experiment("cases/smoke.json", self.root)
        with self.assertRaises(ContractError):
            load_experiment("../smoke.json", self.root)

    def test_rejects_symlink_escaping_repo(self):
        outside = Path(self.tmp.name).parent / (Path(self.tmp.name).name + "-outside.json")
        outside.write_text(json.dumps(self.cases), encoding="utf-8")
        self.addCleanup(outside.unlink)
        link = self.root / "cases" / "external.json"
        link.symlink_to(outside)
        self.manifest["cases_file"] = "cases/external.json"
        self.persist()
        with self.assertRaises(ContractError):
            self.load()

    def test_rejects_duplicate_ids(self):
        self.cases["cases"].append(dict(self.cases["cases"][0]))
        self.persist()
        with self.assertRaisesRegex(ContractError, "duplicate"):
            self.load()

    def test_rejects_excessive_cases(self):
        template = self.cases["cases"][0]
        self.cases["cases"] = [
            {**template, "id": f"case-{i:03d}"} for i in range(4)
        ]
        self.persist()
        with self.assertRaises(ContractError):
            self.load()

    def test_rejects_empty_and_long_prompts(self):
        for prompt in ("", " " * 5, "x" * 1001):
            with self.subTest(length=len(prompt)):
                self.cases["cases"][0]["prompt"] = prompt
                self.persist()
                with self.assertRaises(ContractError):
                    self.load()

    def test_rejects_bad_assertion(self):
        for assertion in (
            {"type": "unknown", "expected": "OK"},
            {"type": "regex", "expected": "("},
            {"type": "regex", "expected": "x" * 129},
            {"type": "exact", "expected": ""},
            {"type": "contains", "expected": "OK", "extra": 1},
        ):
            with self.subTest(assertion_type=assertion.get("type")):
                self.cases["cases"][0]["assertion"] = assertion
                self.persist()
                with self.assertRaises(ContractError):
                    self.load()

    def test_rejects_duplicate_json_keys(self):
        (self.root / "cases" / "smoke.json").write_text(
            '{"schema_version": "1.0", "schema_version": "1.0", "cases": []}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ContractError, "duplicate"):
            self.load()

    def test_rejects_large_files(self):
        (self.root / "cases" / "smoke.json").write_text(
            " " * (128 * 1024 + 1), encoding="utf-8"
        )
        with self.assertRaisesRegex(ContractError, "size"):
            self.load()

    def test_rejects_wrong_schema_versions(self):
        self.manifest["schema_version"] = "2.0"
        self.persist()
        with self.assertRaises(ContractError):
            self.load()
        self.manifest["schema_version"] = "1.0"
        self.cases["schema_version"] = "2.0"
        self.persist()
        with self.assertRaises(ContractError):
            self.load()


if __name__ == "__main__":
    unittest.main()
