"""Offline report-integrity tests; all example responses are synthetic."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from llm_eval.contracts import ContractError, load_experiment
from llm_eval.report_validation import validate_files, validate_reports
from llm_eval.run_evaluation import build_report, write_report
from llm_eval.scoring import grade

REVISION = "a" * 40
RUN_ID = "12345"
TIMESTAMP = "2026-11-08T10:15:30+00:00"


class ReportIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.experiment = load_experiment("experiments/smoke-001.json", cls.root)

    def setUp(self):
        answers = [" OK ", "The SUNRISE is beautiful.", "123"]
        scored = [
            grade(case, answer, latency_ms=10 + i)
            for i, (case, answer) in enumerate(zip(self.experiment.cases, answers))
        ]
        self.document, self.markdown = build_report(
            self.experiment, scored, run_id=RUN_ID,
            revision=REVISION, timestamp_utc=TIMESTAMP,
        )

    def verify(self, document=None, markdown=None):
        return validate_reports(
            self.experiment, self.document if document is None else document,
            self.markdown if markdown is None else markdown,
            run_id=RUN_ID, revision=REVISION,
        )

    def test_valid_synthetic_artifact(self):
        self.verify()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            write_report(path, self.document, self.markdown)
            validate_files(path, repo_root=self.root, run_id=RUN_ID, revision=REVISION)

    def test_rejects_modified_case_grade(self):
        changed = copy.deepcopy(self.document)
        changed["cases"][0]["status"] = "fail"
        with self.assertRaises(ContractError):
            self.verify(changed)

    def test_rejects_forged_pass_rate_and_totals(self):
        for name, value in (
            ("total", 999), ("passed", 0), ("failed", True),
            ("pass_rate", 0.0), ("pass_rate", float("nan")),
        ):
            with self.subTest(key=name):
                changed = copy.deepcopy(self.document)
                changed["summary"][name] = value
                with self.assertRaises(ContractError):
                    self.verify(changed)

    def test_rejects_invalid_case_order_and_injected_fields(self):
        for modification in ("swap", "extra", "assertion", "boolean_latency"):
            with self.subTest(modification=modification):
                changed = copy.deepcopy(self.document)
                if modification == "swap":
                    changed["cases"][0], changed["cases"][1] = changed["cases"][1], changed["cases"][0]
                elif modification == "extra":
                    changed["cases"][0]["unexpected"] = 123
                elif modification == "assertion":
                    changed["cases"][0]["assertion_type"] = "regex"
                else:
                    changed["cases"][0]["latency_ms"] = True
                with self.assertRaises(ContractError):
                    self.verify(changed)

    def test_rejects_inconsistent_stop_after_error(self):
        changed = copy.deepcopy(self.document)
        first = changed["cases"][0]
        first.update(status="error", response=None, error_category="quota", latency_ms=10)
        for follow in changed["cases"][1:]:
            follow.update(status="error", response=None, error_category="quota", latency_ms=None)
        changed["summary"].update(passed=0, failed=0, errors=3, pass_rate=0.0)
        _, md = build_report(
            self.experiment,
            [grade(case, None, latency_ms=10 if i == 0 else None, error_category="quota")
             for i, case in enumerate(self.experiment.cases)],
            run_id=RUN_ID, revision=REVISION, timestamp_utc=TIMESTAMP,
        )
        self.verify(changed, md)
        changed["cases"][2]["latency_ms"] = 99
        with self.assertRaises(ContractError):
            self.verify(changed, md)

    def test_rejects_unapproved_error_category(self):
        changed = copy.deepcopy(self.document)
        changed["cases"][0].update(status="error", response=None,
                                  error_category="arbitrary-private-text")
        with self.assertRaises(ContractError):
            self.verify(changed)

    def test_rejects_forged_identity_and_untrusted_config(self):
        for section, key, value in (
            ("root", "run_id", "9999"),
            ("root", "revision_sha", "b" * 40),
            ("root", "timestamp_utc", "2026-11-08T10:15:30"),
            ("root", "schema_version", "2.0"),
            ("configuration", "max_output_tokens", 1000),
            ("configuration", "model", "alternate"),
        ):
            with self.subTest(section=section, key=key):
                changed = copy.deepcopy(self.document)
                if section == "root":
                    changed[key] = value
                else:
                    changed["configuration"][key] = value
                with self.assertRaises(ContractError):
                    self.verify(changed)

    def test_rejects_changed_markdown(self):
        with self.assertRaises(ContractError):
            self.verify(markdown=self.markdown + "\nAdditional, unreviewed content")

    def test_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            write_report(path, self.document, self.markdown)
            raw = (path / "results.json").read_text(encoding="utf-8")
            raw = raw.replace('"schema_version": "1.0",', '"schema_version": "1.0", "schema_version": "1.0",', 1)
            (path / "results.json").write_text(raw, encoding="utf-8")
            with self.assertRaises(ContractError):
                validate_files(path, repo_root=self.root, run_id=RUN_ID, revision=REVISION)

    def test_rejects_missing_result_files(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ContractError):
                validate_files(Path(folder), repo_root=self.root,
                               run_id=RUN_ID, revision=REVISION)

    def test_rejects_invalid_revision_or_run_id(self):
        for run_id, revision in (
            ("not-numeric", REVISION), (RUN_ID, "not-a-sha"),
            ("0", REVISION),
        ):
            with self.subTest(run_id=run_id, revision=revision):
                with self.assertRaises(ContractError):
                    validate_reports(
                        self.experiment, self.document, self.markdown,
                        run_id=run_id, revision=revision,
                    )


if __name__ == "__main__":
    unittest.main()
