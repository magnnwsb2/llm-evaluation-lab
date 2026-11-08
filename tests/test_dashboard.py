"""All static-dashboard tests run offline with synthetic or sanitized input."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.build_dashboard import (
    APPROVED_CASES, DashboardValidationError, SNAPSHOT,
    build, parse_snapshot, render, validate_snapshot,
)


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.snapshot = parse_snapshot((cls.root / SNAPSHOT).read_bytes())

    def test_approved_real_run_snapshot_is_valid(self):
        self.assertEqual(self.snapshot["run_id"], "42504084221")
        self.assertEqual(self.snapshot["summary"]["passed"], 3)
        self.assertEqual(len(self.snapshot["cases"]), len(APPROVED_CASES))

    def test_build_static_site_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            build(self.root, site)
            markup = (site / "index.html").read_text(encoding="utf-8")
            self.assertTrue((site / ".nojekyll").exists())
            self.assertIn("42504084221", markup)
            self.assertIn("100%", markup)
            self.assertIn("716 ms", markup)
            self.assertIn("492 ms", markup)
            self.assertIn("1133 ms", markup)
            self.assertIn("523 ms", markup)
            self.assertIn("github.com/magnnwsb2/llm-evaluation-lab", markup)
            self.assertNotIn("breathtaking", markup)
            self.assertNotIn('"response"', markup)
            self.assertNotIn("CLOUDFLARE_API_TOKEN", markup)
            self.assertNotIn("<script", markup.lower())
            self.assertNotIn("fetch(", markup)

    def test_visual_css_regressions(self):
        """A missing parenthesis in CSS hid charts and broke later layout rules."""
        markup = render(self.snapshot)
        stylesheet = markup.split("<style>", 1)[1].split("</style>", 1)[0]
        for opening, closing in (("(", ")"), ("{", "}")):
            with self.subTest(grouping=opening + closing):
                self.assertEqual(
                    stylesheet.count(opening), stylesheet.count(closing),
                    "A stylesheet grouping is unbalanced: rendering may fail.",
                )
        # Confirm the rendered stylesheet has its closed gradient and proper
        # structure after the previously broken .bar declaration.
        self.assertIn(
            "background:linear-gradient(90deg,var(--accent),var(--purple))",
            stylesheet,
        )
        self.assertIn(".stats{display:grid;", stylesheet)
        self.assertIn(".stat strong{display:block;", stylesheet)
        self.assertIn(".stat span{display:block;", stylesheet)
        self.assertIn(".table-wrap{overflow-x:auto;", stylesheet)
        self.assertIn("table{border-collapse:collapse;width:100%;min-width:560px;", stylesheet)
        self.assertIn("th,td{padding:18px 18px;", stylesheet)
        self.assertIn("@media(max-width:800px)", stylesheet)
        self.assertIn("@media(max-width:540px)", stylesheet)

    def test_chart_metrics_and_table_remain_populated(self):
        """HTML carries all reviewed values; CSS may not conceal them."""
        markup = render(self.snapshot)
        self.assertEqual(markup.count("class='bar'"), 3)
        self.assertEqual(markup.count("class='track'"), 3)
        self.assertEqual(markup.count('<div class="stat">'), 4)
        self.assertEqual(markup.count("<tr>"), 4)  # heading + three cases
        self.assertIn("716 ms", markup)
        self.assertIn("492 ms", markup)
        self.assertIn("1133 ms", markup)
        self.assertIn("523 ms", markup)
        self.assertIn("overflow-x:auto;", markup)

    def test_rejects_sensitive_and_unapproved_fields(self):
        for addition in (
            {"response": "some secret response"},
            {"prompt": "sensitive text"},
            {"token_usage": 100},
        ):
            with self.subTest(addition=addition):
                changed = copy.deepcopy(self.snapshot)
                changed["cases"][0].update(addition)
                with self.assertRaises(DashboardValidationError):
                    validate_snapshot(changed)

    def test_rejects_false_provenance_and_synthetic_substitution(self):
        tests = [
            ("run_id", "999"),
            ("timestamp_utc", "2026-11-08T00:00:00Z"),
            ("revision_sha", "0" * 40),
            ("model", "another-model"),
            ("visibility", "private"),
        ]
        for key, wrong in tests:
            with self.subTest(field=key):
                changed = copy.deepcopy(self.snapshot)
                changed[key] = wrong
                with self.assertRaises(DashboardValidationError):
                    validate_snapshot(changed)

    def test_rejects_forged_counts_and_latency(self):
        for section, field, value in (
            ("summary", "passed", 2), ("summary", "total", 5),
            ("summary", "pass_rate", 0.5),
            ("cases", "latency_ms", 1),
            ("cases", "status", "fail"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.snapshot)
                if section == "summary":
                    changed[section][field] = value
                else:
                    changed[section][0][field] = value
                with self.assertRaises(DashboardValidationError):
                    validate_snapshot(changed)

    def test_rejects_wrong_types_and_duplicate_keys(self):
        for section, field, value in (
            ("summary", "passed", True),
            ("summary", "pass_rate", float("nan")),
            ("cases", "latency_ms", True),
        ):
            changed = copy.deepcopy(self.snapshot)
            if section == "summary":
                changed["summary"][field] = value
            else:
                changed["cases"][0][field] = value
            with self.assertRaises(DashboardValidationError):
                validate_snapshot(changed)
        payload = (self.root / SNAPSHOT).read_text(encoding="utf-8")
        payload = payload.replace('"schema_version": "1.0",',
                                  '"schema_version": "1.0", "schema_version": "1.0",', 1)
        with self.assertRaises(DashboardValidationError):
            parse_snapshot(payload.encode())

    def test_rejects_excessive_or_invalid_json(self):
        for value in (b"x" * 8193, b"{broken", b"\xff"):
            with self.assertRaises(DashboardValidationError):
                parse_snapshot(value)

    def test_render_does_not_require_external_resources(self):
        markup = render(self.snapshot)
        self.assertIn("default-src 'none'", markup)
        self.assertNotIn("https://fonts", markup)
        self.assertNotIn("analytics", markup.lower())


if __name__ == "__main__":
    unittest.main()
