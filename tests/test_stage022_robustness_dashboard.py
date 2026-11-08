"""Stage 022: audited third-run publication with strict fail-closed privacy gates."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_dashboard import SNAPSHOT, build, parse_snapshot, render
from tools.comparison import render_comparison
from tools.robustness_panel import ROBUSTNESS_CSS, render_robustness_details
from tools.validate_advanced_evidence import SOURCE as ADV_SOURCE, read_evidence
from tools.validate_robustness_evidence import (
    EXPECTED,
    SOURCE as ROB_SOURCE,
    RobustnessEvidenceError,
    read_robustness_evidence,
    validate_robustness_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


class ReviewedRobustnessPagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = parse_snapshot((ROOT / SNAPSHOT).read_bytes())
        cls.advanced = read_evidence(ROOT / ADV_SOURCE)
        cls.robustness = read_robustness_evidence(ROOT / ROB_SOURCE)

    def test_exact_source_identity_and_sha256(self):
        item = self.robustness
        self.assertEqual(item, EXPECTED)
        self.assertEqual(item["run_id"], "42519170795")
        self.assertEqual(item["revision_sha"],
                         "f7f98c3082f92508ef06a1cbc02b7a60c6acfe90")
        self.assertEqual(item["artifact_sha256"],
                         "01c1f896509b89ecff64346b4e29956f550bd6a6700975f0cc033aa3101ec7b3")
        self.assertEqual(item["summary"], {
            "total": 3, "passed": 1, "failed": 2,
            "errors": 0, "pass_rate": 1 / 3,
        })
        self.assertEqual([c["latency_ms"] for c in item["cases"]],
                         [5406, 443, 2108])

    def test_retrospective_diagnostics_never_change_strict_grade(self):
        items = self.robustness["cases"]
        self.assertEqual([c["status"] for c in items], ["fail", "pass", "fail"])
        self.assertEqual(
            items[0]["diagnostic"],
            {
                "content": "unknown",
                "format": "violation",
                "completion": "possible_incomplete",
                "reason": "exact_prose_possible_incomplete",
            },
        )
        self.assertNotIn("diagnostic", items[1])
        self.assertEqual(
            items[2]["diagnostic"],
            {
                "content": "mismatch",
                "format": "violation",
                "completion": "no_signal",
                "reason": "json_content_and_format",
            },
        )

    def test_approved_snapshot_refuses_forged_data_and_private_fields(self):
        mutations = (
            lambda x: x.update(run_id="42"),
            lambda x: x.update(artifact_sha256="0" * 64),
            lambda x: x.update(timestamp_utc="2026-11-08T00:00:00Z"),
            lambda x: x.update(token="hidden"),
            lambda x: x.update(prompt="do not publish"),
            lambda x: x.update(response="private"),
            lambda x: x["summary"].update(passed=3),
            lambda x: x["summary"].update(pass_rate=1.0),
            lambda x: x["summary"].update(failed=True),
            lambda x: x["cases"][0].update(status="pass"),
            lambda x: x["cases"][0].update(latency_ms=1),
            lambda x: x["cases"][0].update(response="private"),
            lambda x: x["cases"][0]["diagnostic"].update(content="match"),
            lambda x: x["cases"][0]["diagnostic"].update(completion="truncated"),
            lambda x: x["cases"][0]["diagnostic"].update(prompt="hidden"),
            lambda x: x["cases"][2]["diagnostic"].update(reason="json_format_only"),
            lambda x: x["cases"].reverse(),
        )
        for mutation in mutations:
            with self.subTest(mutation=str(mutation)):
                forged = copy.deepcopy(self.robustness)
                mutation(forged)
                with self.assertRaises(RobustnessEvidenceError):
                    validate_robustness_evidence(forged)
                with self.assertRaises(RobustnessEvidenceError):
                    render_comparison(self.smoke, self.advanced, forged)

    def test_duplicate_keys_nonfinite_bad_json_and_oversize_are_rejected(self):
        data = (
            '{"run_id":"one","run_id":"two"}',
            '{"summary":NaN}',
            'not JSON',
            '{"summary":Infinity}',
            "{}" * 5000,
        )
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "unreviewed.json"
            for text in data:
                with self.subTest(size=len(text)):
                    file.write_text(text, encoding="utf-8")
                    with self.assertRaises(RobustnessEvidenceError):
                        read_robustness_evidence(file)

    def test_three_run_site_contains_correct_historical_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "site"
            with patch("socket.socket", side_effect=AssertionError("network forbidden")):
                build(ROOT, out)
            self.assertEqual(sorted(f.name for f in out.iterdir()),
                             [".nojekyll", "index.html"])
            page = (out / "index.html").read_text(encoding="utf-8")
        self.assertEqual(page, render(self.smoke, self.advanced, self.robustness))
        self.assertIn("Três experimentos. Três evidências.", page)
        self.assertEqual(page.count('class="compare-card'), 3)
        for value in ("smoke-001", "advanced-001", "robustness-001",
                      "100%", "66,7%", "33,3%", "716 ms", "1.382 ms",
                      "2.652 ms", "5.406 ms", "443 ms", "2.108 ms"):
            self.assertIn(value, page)
        for run, commit in (
            ("42504084221", "61fd68ae0d51"),
            ("42511351245", "6f90b6a2e9ce"),
            ("42519170795", "f7f98c3082f9"),
        ):
            self.assertIn("/actions/runs/" + run, page)
            self.assertIn(commit, page)

    def test_robustness_explanations_are_specific_and_cautious(self):
        page = render(self.smoke, self.advanced, self.robustness)
        self.assertIn('id="robustez"', page)
        self.assertIn("Por que dois testes de robustez falharam?", page)
        self.assertIn("Possivelmente incompleta não significa truncamento confirmado", page)
        self.assertIn("erro de conteúdo e de formato", page)
        self.assertIn("selecionou os valores errados", page)
        self.assertIn("não demonstra proteção geral", page)
        self.assertIn("diagnósticos são análises posteriores", page)
        self.assertIn("2/3", page)  # previous advanced failure and methodology
        self.assertIn("Aprovou 1/3", page)
        self.assertIn("não é um teste A/B controlado", page)
        self.assertIn("revisados e estáticos", page)
        self.assertIn("Metodologia e limites", page)

    def test_site_does_not_embed_raw_outputs_secrets_or_api_calls(self):
        page = render(self.smoke, self.advanced, self.robustness)
        for private in (
            '"response":', '"prompt":', "CLOUDFLARE_API_TOKEN",
            "Bearer ", "Here is the extracted data",
            "## Step 1:", '{"status":"pending"', '{"ticket":',
            "token_usage", "finish_reason=", "<script", "fetch(",
            "https://fonts.googleapis.com",
        ):
            with self.subTest(private=private):
                self.assertNotIn(private, page)
        self.assertIn("default-src 'none'", page)

    def test_responsive_and_keyboard_accessible_markup(self):
        page = render(self.smoke, self.advanced, self.robustness)
        css = page.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertIn(ROBUSTNESS_CSS, css)
        self.assertIn(".compare-grid{display:grid;grid-template-columns:repeat(3", css)
        self.assertIn("@media(max-width:940px)", css)
        self.assertIn("@media(max-width:800px)", css)
        self.assertIn("@media(max-width:540px)", css)
        self.assertIn('href="#conteudo"', page)
        self.assertIn('href="#comparacao"', page)
        self.assertIn('tabindex="0"', page)
        self.assertIn('aria-labelledby="robust-heading"', page)
        self.assertIn('aria-label="Casos de robustez;', page)
        for open_char, close_char in (("(", ")"), ("{", "}")):
            self.assertEqual(css.count(open_char), css.count(close_char))

    def _copy_valid_inputs(self, root: Path):
        for source in (SNAPSHOT, ADV_SOURCE, ROB_SOURCE):
            dest = root / source
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / source).read_bytes())

    def test_rejects_missing_robustness_before_writing_public_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            self._copy_valid_inputs(root)
            (root / ROB_SOURCE).unlink()
            site = Path(temporary) / "site"
            with self.assertRaises((OSError, RobustnessEvidenceError)):
                build(root, site)
            self.assertFalse(site.exists())

    def test_rejects_bad_robustness_before_writing_public_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            self._copy_valid_inputs(root)
            fake = copy.deepcopy(self.robustness)
            fake["cases"][2]["response"] = "sensitive"
            (root / ROB_SOURCE).write_text(json.dumps(fake), encoding="utf-8")
            site = Path(temporary) / "site"
            with self.assertRaises(RobustnessEvidenceError):
                build(root, site)
            self.assertFalse(site.exists())

    def test_legacy_two_run_comparison_remains_supported(self):
        output = render(self.smoke, self.advanced)
        self.assertEqual(output.count('class="compare-card'), 2)
        self.assertIn("Dois experimentos. Duas evidências.", output)
        self.assertNotIn('id="robustez"', output)
        self.assertNotIn("robustness-001", output)


if __name__ == "__main__":
    unittest.main()
