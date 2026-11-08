"""Stage 018: offline public dashboard comparison and privacy regressions."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.build_dashboard import (
    DashboardValidationError, SNAPSHOT, build, parse_snapshot, render
)
from tools.comparison import COMPARISON_CSS, render_comparison
from tools.validate_advanced_evidence import (
    SOURCE as ADVANCED_SNAPSHOT, EvidenceError, read_evidence
)
from tools.validate_robustness_evidence import (
    SOURCE as ROBUSTNESS_SNAPSHOT, read_robustness_evidence
)

ROOT = Path(__file__).resolve().parents[1]


class ComparativeDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = parse_snapshot((ROOT / SNAPSHOT).read_bytes())
        cls.advanced = read_evidence(ROOT / ADVANCED_SNAPSHOT)
        cls.robustness = read_robustness_evidence(ROOT / ROBUSTNESS_SNAPSHOT)

    def test_both_observed_experiments_have_exact_trusted_values(self):
        self.assertEqual(self.smoke["run_id"], "42504084221")
        self.assertEqual(self.advanced["run_id"], "42511351245")
        self.assertEqual(self.smoke["summary"], {
            "total": 3, "passed": 3, "failed": 0, "errors": 0,
            "pass_rate": 1
        })
        self.assertEqual(self.advanced["summary"], {
            "total": 3, "passed": 2, "failed": 1, "errors": 0,
            "pass_rate": 2 / 3
        })
        self.assertEqual([c["latency_ms"] for c in self.smoke["cases"]],
                         [492, 1133, 523])
        self.assertEqual([c["latency_ms"] for c in self.advanced["cases"]],
                         [2760, 670, 717])

    def test_generated_site_has_three_independently_attributed_experiments(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"
            build(ROOT, target)
            markup = (target / "index.html").read_text(encoding="utf-8")
            self.assertTrue((target / ".nojekyll").is_file())
            self.assertEqual(sorted(p.name for p in target.iterdir()),
                             [".nojekyll", "index.html"])
            self.assertIn('id="comparacao"', markup)
            self.assertIn("Três experimentos. Três evidências.", markup)
            self.assertIn("robustness-001", markup)
            self.assertIn("33,3%", markup)
            self.assertIn("2.652 ms", markup)
            self.assertIn("5.406 ms", markup)
            self.assertIn("smoke-001", markup)
            self.assertIn("advanced-001", markup)
            self.assertIn("100%", markup)
            self.assertIn("66,7%", markup)
            self.assertIn("716 ms", markup)
            self.assertIn("1.382 ms", markup)
            self.assertIn("2.760 ms", markup)
            self.assertIn("Reprovado", markup)
            self.assertIn("Conteúdo correto; formato inválido", markup)
            self.assertIn("A falha estrita permanece uma reprovação", markup)
            self.assertIn("Iguais · 1 par observado", markup)
            self.assertIn("diferentes", markup.lower())
            for run_id, revision in (
                ("42504084221", "61fd68ae0d51"),
                ("42511351245", "6f90b6a2e9ce"),
                ("42519170795", "f7f98c3082f9"),
            ):
                with self.subTest(run=run_id):
                    self.assertIn(f"/actions/runs/{run_id}", markup)
                    self.assertIn(revision, markup)
            self.assertEqual(markup.count('class="compare-card'), 3)
            self.assertEqual(markup.count('class="compare-table'), 1)
            self.assertEqual(markup.count('class="repeat-observation"'), 1)
            self.assertIn('aria-labelledby="compare-heading"', markup)
            self.assertIn('aria-label="Tabela comparativa', markup)
            self.assertIn('tabindex="0"', markup)

    def test_comparison_is_read_only_and_contains_no_private_payloads(self):
        markup = render(self.smoke, self.advanced)
        for unwanted in (
            '"response":', '"prompt":', "Here is the extracted data",
            '{"ticket":', '"CLOUDFLARE_API_TOKEN"',
            "Bearer ", "<script", "fetch(", "https://fonts.googleapis.com",
            "/client/v4/accounts/"
        ):
            with self.subTest(value=unwanted):
                self.assertNotIn(unwanted, markup)
        self.assertIn("não constituem uma comparação controlada", markup)
        self.assertIn("não demonstra determinismo", markup)
        self.assertIn("não inferem", markup)

    def test_previous_smoke_only_render_path_remains_compatible(self):
        old_page = render(self.smoke)
        self.assertNotIn('id="comparacao"', old_page)
        self.assertEqual(old_page.count("class='bar'"), 3)
        self.assertEqual(old_page.count('<div class="stat">'), 4)
        self.assertIn("492 ms", old_page)
        self.assertIn("1133 ms", old_page)
        self.assertIn("523 ms", old_page)
        self.assertIn("Metodologia e limites", old_page)

    def test_tampered_advanced_data_cannot_enter_rendered_page(self):
        for change in (
            lambda d: d["summary"].update(passed=3),
            lambda d: d["cases"][0].update(status="pass"),
            lambda d: d["cases"][0].update(response="raw-private-value"),
            lambda d: d["cases"][0].update(diagnostic="strict_pass"),
            lambda d: d["repeated_prompt"].update(outcome="different"),
            lambda d: d.update(run_id="999"),
            lambda d: d["summary"].update(total=True),
            lambda d: d["cases"].reverse(),
        ):
            with self.subTest(case=str(change)):
                tampered = copy.deepcopy(self.advanced)
                change(tampered)
                with self.assertRaises(EvidenceError):
                    render_comparison(self.smoke, tampered)
                with self.assertRaises(EvidenceError):
                    render(self.smoke, tampered)

    def test_tampered_smoke_data_cannot_enter_rendered_page(self):
        forged = copy.deepcopy(self.smoke)
        forged["cases"][0]["latency_ms"] = 0
        with self.assertRaises(DashboardValidationError):
            render(forged, self.advanced)

    def test_missing_advanced_evidence_stops_before_site_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / SNAPSHOT).parent.mkdir(parents=True)
            (root / SNAPSHOT).write_bytes((ROOT / SNAPSHOT).read_bytes())
            out = Path(tmp) / "site"
            with self.assertRaises(EvidenceError):
                build(root, out)
            self.assertFalse(out.exists())

    def test_invalid_advanced_evidence_stops_before_site_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / SNAPSHOT).parent.mkdir(parents=True)
            (root / SNAPSHOT).write_bytes((ROOT / SNAPSHOT).read_bytes())
            forged = copy.deepcopy(self.advanced)
            forged["cases"][0]["response"] = "do not publish"
            (root / ADVANCED_SNAPSHOT).write_text(
                json.dumps(forged), encoding="utf-8"
            )
            out = Path(tmp) / "site"
            with self.assertRaises(EvidenceError):
                build(root, out)
            self.assertFalse(out.exists())

    def test_comparison_css_balanced_and_responsive(self):
        page = render(self.smoke, self.advanced)
        stylesheet = page.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertIn(COMPARISON_CSS, stylesheet)
        for start, end in (("{", "}"), ("(", ")")):
            with self.subTest(brackets=start + end):
                self.assertEqual(stylesheet.count(start), stylesheet.count(end))
        self.assertIn("@media(max-width:540px)", stylesheet)
        self.assertIn(".compare-grid{display:grid;", stylesheet)
        self.assertIn(".compare-table table{min-width:710px}", stylesheet)
        self.assertIn(".bar{height:100%;", stylesheet)


if __name__ == "__main__":
    unittest.main()
