"""Build the offline-only, response-free GitHub Pages dashboard (SDD-001 §5.4).

Never calls the Cloudflare provider, never reads credentials and never downloads
workflow artifacts. The initial public snapshot is allowlisted to one inspected,
real manual run; new runs require an explicit reviewed source-code change.
"""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any

from .contracts import ContractError

MAX_SNAPSHOT_BYTES = 16 * 1024

APPROVED_PROVENANCE = {
    "kind": "verified-manual-run",
    "run_id": "42504084221",
    "revision_sha": "61fd68ae0d51d646e33db13c8187f3b6351e8220",
    "timestamp_utc": "2026-11-08T17:16:02+00:00",
    "artifact_sha256": "9af4dc1ec2fa8d8fa79a8cc5837088a10413915db71da035f2f46492b88e25bd",
}

APPROVED_CASES = (
    ("greeting-001", "exact", "pass", 492),
    ("keyword-001", "contains", "pass", 1133),
    ("digits-001", "regex", "pass", 523),
)

RUN_URL_PREFIX = "https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/"
COMMIT_URL_PREFIX = "https://github.com/magnnwsb2/llm-evaluation-lab/commit/"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _reject() -> None:
    """Failure messages must not include unreviewed source content."""
    raise ContractError("public dashboard snapshot rejected by safety and integrity rules")


def _object(value: Any, expected: set[str]) -> dict:
    if type(value) is not dict or set(value) != expected:
        _reject()
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    output = {}
    for key, value in pairs:
        if key in output:
            _reject()
        output[key] = value
    return output


def _invalid_constant(_: str) -> None:
    _reject()


def read_public_snapshot(path: Path) -> dict:
    """Read only a small, duplicate-free JSON file and enforce the publication allowlist."""
    try:
        if path.stat().st_size > MAX_SNAPSHOT_BYTES:
            _reject()
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_invalid_constant,
        )
    except (OSError, UnicodeError, ValueError, RecursionError):
        _reject()
    validate_public_snapshot(data)
    return data


def validate_public_snapshot(data: Any) -> None:
    """Refuse unknown fields and any alteration of the reviewed real-run evidence."""
    data = _object(
        data, {"schema_version", "provenance", "experiment_id", "model",
               "summary", "cases"}
    )
    if (type(data["schema_version"]) is not str
            or data["schema_version"] != "1.0"
            or type(data["experiment_id"]) is not str
            or data["experiment_id"] != "smoke-001"
            or type(data["model"]) is not str
            or data["model"] != "@cf/meta/llama-3.1-8b-instruct-fp8"):
        _reject()

    provenance = _object(data["provenance"], set(APPROVED_PROVENANCE))
    for field, expected in APPROVED_PROVENANCE.items():
        if type(provenance[field]) is not type(expected) or provenance[field] != expected:
            _reject()

    cases = data["cases"]
    if type(cases) is not list or len(cases) != len(APPROVED_CASES):
        _reject()
    for case, approved in zip(cases, APPROVED_CASES):
        _object(case, {"id", "assertion_type", "status", "latency_ms"})
        observed = (
            case["id"], case["assertion_type"], case["status"], case["latency_ms"]
        )
        if any(type(value) is not type(expected) or value != expected
               for value, expected in zip(observed, approved)):
            _reject()

    summary = _object(
        data["summary"], {"total", "passed", "failed", "errors", "pass_rate"}
    )
    counts = {
        "total": len(cases),
        "passed": sum(case["status"] == "pass" for case in cases),
        "failed": sum(case["status"] == "fail" for case in cases),
        "errors": sum(case["status"] == "error" for case in cases),
    }
    for key, expected in counts.items():
        if type(summary[key]) is not int or summary[key] != expected:
            _reject()
    rate = summary["pass_rate"]
    if type(rate) is not float or not math.isfinite(rate):
        _reject()
    if rate != summary["passed"] / summary["total"]:
        _reject()


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_html(data: dict) -> str:
    """Render one responsive, fully static page from already validated public data."""
    validate_public_snapshot(data)
    summary = data["summary"]
    provenance = data["provenance"]
    times = [case["latency_ms"] for case in data["cases"]]
    latency_avg = round(mean(times))
    latency_median = round(median(times))
    longest = max(times)
    pass_rate = round(100 * summary["pass_rate"])
    rows = []
    chart_rows = []
    for case in data["cases"]:
        title, rule, status = (_escape(case[key]) for key in
                               ("id", "assertion_type", "status"))
        duration = case["latency_ms"]
        rows.append(
            f'<tr><th scope="row"><code>{title}</code></th>'
            f'<td><span class="rule">{rule}</span></td>'
            f'<td><span class="passed">Aprovado</span></td>'
            f'<td class="number">{duration:,} ms</td></tr>'
        )
        chart_rows.append(
            f'<div class="latency-row">'
            f'<div class="latency-meta"><code>{title}</code><strong>{duration:,} ms</strong></div>'
            f'<progress value="{duration}" max="{longest}" aria-label="Latência de {title}">'
            f'{duration} ms</progress></div>'
        )

    run_id = provenance["run_id"]
    sha = provenance["revision_sha"]
    run_link = _escape(RUN_URL_PREFIX + run_id)
    commit_link = _escape(COMMIT_URL_PREFIX + sha)
    model = _escape(data["model"])
    experiment = _escape(data["experiment_id"])
    timestamp = _escape(provenance["timestamp_utc"])
    source_digest = _escape(provenance["artifact_sha256"][:16] + "…")
    sha_short = _escape(sha[:12])
    case_rows = "\n".join(rows)
    bars = "\n".join(chart_rows)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="referrer" content="no-referrer">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; base-uri 'none'; form-action 'none';">
  <title>LLM Evaluation Lab — resultados verificáveis</title>
  <meta name="description" content="Resultados de uma avaliação real de LLM, com rastreabilidade até o GitHub Actions.">
  <link rel="stylesheet" href="./style.css">
</head>
<body>
  <div class="site">
    <header class="topline">
      <a href="https://github.com/magnnwsb2/llm-evaluation-lab" class="brand" rel="noopener noreferrer">
        <span class="mark" aria-hidden="true">◈</span><span>LLM EVALUATION LAB</span>
      </a>
      <span class="environment"><span class="dot" aria-hidden="true"></span> PUBLIC EVIDENCE / v1.0</span>
    </header>

    <main id="content">
      <section class="hero" aria-labelledby="heading">
        <div class="eyebrow"><span class="section-no">01 /</span> AI ENGINEERING · REAL INFERENCE</div>
        <h1 id="heading">Resultados que podem<br><em>ser auditados.</em></h1>
        <p class="intro">Um experimento real, três critérios objetivos e uma trilha de evidências.
           Sem benchmark inventado, sem respostas privadas e sem custo estimado.</p>
        <div class="hero-actions">
          <a href="{run_link}" class="primary-action" rel="noopener noreferrer">Examinar execução original <span aria-hidden="true">↗</span></a>
          <span class="annotation">Execução manual · 08 nov 2026</span>
        </div>
      </section>

      <section class="scoreboard" aria-label="Indicadores desta execução">
        <div class="metric metric-leading">
          <span class="metric-label">PASS RATE <span aria-hidden="true">↗</span></span>
          <span class="metric-value">{pass_rate}<small>%</small></span>
          <span class="metric-note">{summary['passed']} de {summary['total']} verificações aprovadas</span>
        </div>
        <div class="metric">
          <span class="metric-label">TOTAL DE CASOS</span>
          <span class="metric-value">{summary['total']:02d}</span>
          <span class="metric-note">Amostra pequena · instruções simples</span>
        </div>
        <div class="metric">
          <span class="metric-label">FALHAS / ERROS</span>
          <span class="metric-value">{summary['failed']}<span class="slash">/</span>{summary['errors']}</span>
          <span class="metric-note">Nenhum nesta execução</span>
        </div>
        <div class="metric">
          <span class="metric-label">LATÊNCIA MÉDIA</span>
          <span class="metric-value">{latency_avg}<small>ms</small></span>
          <span class="metric-note">Ida e volta HTTP no cliente</span>
        </div>
      </section>

      <section class="detail" aria-labelledby="results-heading">
        <div class="section-head">
          <div>
            <span class="eyebrow"><span class="section-no">02 /</span> RESULTADOS POR CASO</span>
            <h2 id="results-heading">Regras, não opiniões.</h2>
          </div>
          <span class="pill">● 3 verificações concluídas</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th scope="col">Caso</th><th scope="col">Critério</th>
              <th scope="col">Resultado</th><th scope="col" class="number">Latência</th></tr></thead>
            <tbody>{case_rows}</tbody>
          </table>
        </div>
        <p class="footnote"><strong>Regras:</strong> igualdade exata, presença de palavra-chave e padrão regex.
          A nota se refere somente às três entradas testadas, não à precisão geral do modelo.</p>
      </section>

      <section class="analysis-grid" aria-label="Latência e rastreabilidade">
        <div class="panel">
          <span class="eyebrow"><span class="section-no">03 /</span> LATÊNCIA OBSERVADA</span>
          <h2>Tempo de resposta.</h2>
          <p class="panel-copy">Tempo entre envio da requisição e leitura da resposta.
              Não é velocidade de geração de tokens.</p>
          <div class="latency-list">{bars}</div>
          <div class="panel-bottom"><span>Mediana</span><strong>{latency_median} ms</strong>
            <span class="divider-pipe">·</span><span>Máximo</span><strong>{longest} ms</strong></div>
        </div>
        <div class="panel panel-provenance">
          <span class="eyebrow"><span class="section-no">04 /</span> ORIGEM DOS DADOS</span>
          <h2>Uma fonte verificável.</h2>
          <dl>
            <div><dt>Experimento</dt><dd><code>{experiment}</code></dd></div>
            <div><dt>Modelo</dt><dd class="break"><code>{model}</code></dd></div>
            <div><dt>Workflow run</dt><dd><a href="{run_link}" rel="noopener noreferrer">#{run_id} ↗</a></dd></div>
            <div><dt>Commit</dt><dd><a href="{commit_link}" rel="noopener noreferrer"><code>{sha_short}</code> ↗</a></dd></div>
            <div><dt>UTC</dt><dd><time datetime="{timestamp}">{timestamp}</time></dd></div>
            <div><dt>SHA-256 do ZIP</dt><dd><code>{source_digest}</code></dd></div>
          </dl>
        </div>
      </section>

      <aside class="methodology" aria-labelledby="method-heading">
        <div><span class="eyebrow"><span class="section-no">05 /</span> METODOLOGIA</span>
          <h2 id="method-heading">Transparência sobre os limites.</h2></div>
        <p>Os dados acima foram extraídos de um <strong>único workflow manual executado com inferência real</strong>,
           validados por regras determinísticas e revisados antes da publicação.
           Não há atualização automática. Nenhum prompt, resposta integral, token de API
           ou identificador de conta está incluído neste site. Consumo de Neurons e custo
           financeiro não foram medidos e não são apresentados como zero.</p>
      </aside>
    </main>

    <footer class="footer">
      <span>MAGNNWS / AI ENGINEERING PORTFOLIO</span>
      <span>GitHub-only · Static · Sem rastreamento</span>
      <a href="{run_link}" rel="noopener noreferrer">Fonte original ↗</a>
    </footer>
  </div>
</body>
</html>
"""


def build_site(snapshot: Path, output_dir: Path, *, root: Path = REPO_ROOT) -> None:
    data = read_public_snapshot(snapshot)
    css = (root / "dashboard" / "style.css").read_text(encoding="utf-8")
    if "@import" in css.lower() or "url(" in css.lower():
        _reject()
    document = render_html(data)
    # The final static website never includes raw prompt/response properties.
    if any(f'"{key}"' in document for key in ("response", "prompt", "api_token")):
        _reject()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(document, encoding="utf-8")
    (output_dir / "style.css").write_text(css, encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline public dashboard builder")
    parser.add_argument("--source", type=Path, default=Path("dashboard/public-results.json"))
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args()
    try:
        build_site(args.source, args.out)
    except (ContractError, OSError, UnicodeError):
        print("Public dashboard build rejected: invalid reviewed data or local file.")
        return 2
    print("Public dashboard built offline from approved run 42504084221.")
    print("No model inference, secrets, third-party scripts or remote downloads used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
