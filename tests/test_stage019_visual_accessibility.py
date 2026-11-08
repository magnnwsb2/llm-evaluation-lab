"""Stage 019 visual/accessibility regression checks for offline static HTML.

Structural tests cannot prove rendering in a real mobile browser; the final
published Pages site still requires screenshot inspection.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build_dashboard import SNAPSHOT, build, parse_snapshot, render
from tools.comparison import COMPARISON_CSS
from tools.validate_advanced_evidence import SOURCE, read_evidence
from tools.validate_robustness_evidence import SOURCE as ROBUSTNESS_SOURCE, read_robustness_evidence


ROOT = Path(__file__).resolve().parents[1]


class Stage019AccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = parse_snapshot((ROOT / SNAPSHOT).read_bytes())
        cls.advanced = read_evidence(ROOT / SOURCE)
        cls.robustness = read_robustness_evidence(ROOT / ROBUSTNESS_SOURCE)
        cls.page = render(cls.smoke, cls.advanced, cls.robustness)
        cls.styles = cls.page.split("<style>", 1)[1].split("</style>", 1)[0]

    def test_chart_grid_no_longer_stretches_to_sibling_height(self):
        self.assertIn("align-items:start", self.styles)
        self.assertIn(".latency-chart{align-self:start}", self.styles)
        self.assertIn(".smoke-stats{align-self:start}", self.styles)
        self.assertIn('class="panel latency-chart"', self.page)
        self.assertIn('class="panel smoke-stats"', self.page)
        self.assertEqual(self.page.count("class='bar'"), 3)
        self.assertEqual(self.page.count("class='track'"), 3)
        for value in ("492 ms", "1133 ms", "523 ms", "716 ms"):
            self.assertIn(value, self.page)

    def test_keyboard_skip_link_and_comparison_jump_resolve(self):
        self.assertIn('<a class="skip-link" href="#conteudo">', self.page)
        self.assertIn('<main id="conteudo">', self.page)
        self.assertIn('href="#comparacao"', self.page)
        self.assertIn('id="comparacao"', self.page)
        self.assertIn('aria-label="Navegação do laboratório"', self.page)
        self.assertIn(".skip-link:focus{top:12px}", self.styles)
        self.assertIn("a:focus-visible{outline:3px solid var(--accent)", self.styles)
        self.assertIn(".table-wrap:focus-visible{outline:3px", self.styles)

    def test_original_standalone_smoke_render_has_no_broken_comparison_link(self):
        page = render(self.smoke)
        self.assertIn('href="#conteudo"', page)
        self.assertNotIn('href="#comparacao"', page)
        self.assertIn("Metodologia e limites", page)
        self.assertIn("smoke-001", page)
        self.assertNotIn("advanced-001:", page)

    def test_mobile_provenance_links_have_readable_labels_and_tap_targets(self):
        self.assertIn("min-height:44px", self.styles)
        self.assertIn(".compare-source code{font-size:.9rem", self.styles)
        self.assertIn(".compare-source a{display:inline-flex", self.styles)
        self.assertIn(".compare-source{display:grid;", self.styles)
        self.assertIn("font-size:.88rem", self.styles)
        self.assertIn("href=\"https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221\"", self.page)
        self.assertIn("href=\"https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42511351245\"", self.page)
        self.assertIn("61fd68ae0d51", self.page)
        self.assertIn("6f90b6a2e9ce", self.page)
        self.assertIn("f7f98c3082f9", self.page)

    def test_heading_hierarchy_and_methodology_cover_both_tasks(self):
        self.assertIn(".compare-section>h2{font-size:clamp(1.6rem", self.styles)
        self.assertIn('<h2 id="compare-heading">', self.page)
        self.assertIn('<section class="panel" id="metodologia">', self.page)
        self.assertIn("<strong>smoke-001:</strong>", self.page)
        self.assertIn("<strong>advanced-001:</strong>", self.page)
        self.assertIn("<strong>robustness-001:</strong>", self.page)
        self.assertIn("extração estruturada", self.page)
        self.assertIn("formato violou o contrato estrito de JSON", self.page)
        self.assertIn("não é um teste A/B controlado", self.page)
        self.assertIn("2/3", self.page)
        self.assertIn("Concordância", self.page)
        self.assertIn("Consumo de tokens, Neurons e custo financeiro não foram medidos", self.page)

    def test_small_screen_and_horizontal_table_rules_remain_present(self):
        self.assertIn("@media(max-width:540px)", self.styles)
        self.assertIn("@media(max-width:800px)", self.styles)
        self.assertIn(".compare-grid{grid-template-columns:1fr}", self.styles)
        self.assertIn("overflow-x:auto", self.styles)
        self.assertIn("tabindex=\"0\"", self.page)
        self.assertIn("min-width:710px", self.styles)
        self.assertIn(COMPARISON_CSS, self.styles)
        for opening, closing in (("{", "}"), ("(", ")")):
            with self.subTest(group=opening + closing):
                self.assertEqual(self.styles.count(opening),
                                 self.styles.count(closing))

    def test_published_page_preserves_privacy_and_reviewed_statistics(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "site"
            build(ROOT, output)
            page = (output / "index.html").read_text(encoding="utf-8")
            self.assertEqual(page, self.page)
            self.assertEqual([entry.name for entry in output.iterdir() if
                              entry.name != ".nojekyll"], ["index.html"])
        for value in ("100%", "66,7%", "2.760 ms", "1.382 ms",
                      "42511351245", "42504084221", "Reprovado"):
            self.assertIn(value, self.page)
        for private in ('"response":', '"prompt":', "Here is the extracted data",
                        "<script", "CLOUDFLARE_API_TOKEN",
                        "https://fonts.googleapis.com", "fetch("):
            with self.subTest(private=private):
                self.assertNotIn(private, self.page)

    def test_no_new_client_side_requests(self):
        self.assertIn("default-src 'none'", self.page)
        self.assertNotIn("<iframe", self.page)
        self.assertNotIn("<video", self.page)


if __name__ == "__main__":
    unittest.main()
