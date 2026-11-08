"""Offline, allowlisted generation of the public GitHub Pages dashboard.

Only two approved historical snapshots. Never contacts Cloudflare or reads secrets.
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
from pathlib import Path

if __package__:
    from .comparison import COMPARISON_CSS, render_comparison
    from .validate_advanced_evidence import SOURCE as ADVANCED_SNAPSHOT, read_evidence
else:  # Supports python tools/build_dashboard.py directly on GitHub Actions.
    from comparison import COMPARISON_CSS, render_comparison
    from validate_advanced_evidence import SOURCE as ADVANCED_SNAPSHOT, read_evidence

SNAPSHOT = Path("dashboard/approved/smoke-001.json")
PROVENANCE = {
    "experiment_id": "smoke-001",
    "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
    "run_id": "42504084221",
    "revision_sha": "61fd68ae0d51d646e33db13c8187f3b6351e8220",
    "timestamp_utc": "2026-11-08T17:16:02+00:00",
}
RUN_URL = "https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/42504084221"
TOP_KEYS = {
    "schema_version", "visibility", "experiment_id", "model", "run_id",
    "revision_sha", "timestamp_utc", "summary", "cases",
}
SUMMARY_KEYS = {"total", "passed", "failed", "errors", "pass_rate"}
CASE_KEYS = {"id", "assertion_type", "status", "latency_ms"}
APPROVED_CASES = (
    ("greeting-001", "exact", "pass", 492),
    ("keyword-001", "contains", "pass", 1133),
    ("digits-001", "regex", "pass", 523),
)
MAX_SNAPSHOT_BYTES = 8192


class DashboardValidationError(ValueError):
    """Generic error: never echo untrusted snapshot content."""


def reject() -> None:
    raise DashboardValidationError("Dashboard snapshot failed public-data validation")


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            reject()
        result[key] = value
    return result


def parse_snapshot(data: bytes) -> dict:
    if len(data) > MAX_SNAPSHOT_BYTES:
        reject()
    try:
        doc = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=lambda _: reject(),
        )
    except (UnicodeError, ValueError, RecursionError):
        reject()
    return validate_snapshot(doc)


def validate_snapshot(doc: object) -> dict:
    if type(doc) is not dict or set(doc) != TOP_KEYS:
        reject()
    if doc["schema_version"] != "1.0" or doc["visibility"] != "public-sanitized-summary":
        reject()
    for key, value in PROVENANCE.items():
        if type(doc[key]) is not str or doc[key] != value:
            reject()
    summary = doc["summary"]
    if type(summary) is not dict or set(summary) != SUMMARY_KEYS:
        reject()
    expected = {"total": 3, "passed": 3, "failed": 0, "errors": 0}
    for key, value in expected.items():
        if type(summary[key]) is not int or summary[key] != value:
            reject()
    if type(summary["pass_rate"]) not in (float, int):
        reject()
    if not math.isfinite(summary["pass_rate"]) or summary["pass_rate"] != 1:
        reject()
    cases = doc["cases"]
    if type(cases) is not list or len(cases) != len(APPROVED_CASES):
        reject()
    for item, expected_case in zip(cases, APPROVED_CASES):
        if type(item) is not dict or set(item) != CASE_KEYS:
            reject()
        for key, val in zip(("id", "assertion_type", "status", "latency_ms"), expected_case):
            if type(item[key]) is not type(val) or item[key] != val:
                reject()
    return doc


def render(doc: dict, advanced: dict | None = None) -> str:
    doc = validate_snapshot(doc)
    comparison_html = render_comparison(doc, advanced) if advanced is not None else ""
    e = html.escape
    cases = doc["cases"]
    summary = doc["summary"]
    average = round(sum(item["latency_ms"] for item in cases) / len(cases))
    fastest = min(item["latency_ms"] for item in cases)
    slowest = max(item["latency_ms"] for item in cases)
    rows = "\n".join(
        "<tr>"
        f"<td><span class='case-id'>{e(item['id'])}</span></td>"
        f"<td>{e(item['assertion_type'])}</td>"
        "<td><span class='passed'>Aprovado</span></td>"
        f"<td class='number'>{item['latency_ms']:,} ms</td>"
        "</tr>".replace(",", ".")
        for item in cases
    )
    bars = "\n".join(
        "<div class='bar-row'>"
        f"<span>{e(item['id'])}</span>"
        "<div class='track'><div class='bar' "
        f"style='width:{max(2, item['latency_ms'] * 100 / slowest):.1f}%'></div></div>"
        f"<strong>{item['latency_ms']} ms</strong></div>"
        for item in cases
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="description" content="Resultados auditáveis de um pequeno experimento real com LLM, com dados públicos e métricas verificadas.">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<title>LLM Evaluation Lab · Resultados verificados</title>
<style>
:root{{--bg:#0a0e18;--surface:#141b2a;--surface2:#1a2536;--line:#29374a;--fg:#e8eef8;--muted:#a5b7cf;--accent:#74c5ff;--green:#70e3a7;--purple:#b6a5ff}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(ellipse at 80% 0%,#192746 0,transparent 36%),var(--bg);color:var(--fg);font-family:system-ui,-apple-system,Segoe UI,sans-serif;line-height:1.55}}
main{{max-width:1050px;margin:auto;padding:44px 22px 80px}}
nav{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:60px;flex-wrap:wrap}}
.logo{{font-weight:800;letter-spacing:.06em;font-size:.9rem}}.logo span{{color:var(--accent)}}
a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
.navlink{{font-size:.9rem}}
.eyebrow{{font-size:.8rem;letter-spacing:.16em;text-transform:uppercase;color:var(--green);font-weight:750}}
h1{{font-size:clamp(2.15rem,6vw,4.45rem);line-height:1.12;margin:16px 0;letter-spacing:-.055em;max-width:780px}}
.sub{{font-size:1.1rem;color:var(--muted);max-width:730px}}
.meta{{color:var(--muted);font-size:.87rem;margin:28px 0 42px;overflow-wrap:anywhere}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
.card,.panel{{min-width:0;border:1px solid var(--line);background:linear-gradient(145deg,var(--surface),#101725);border-radius:18px;padding:24px}}
.label{{color:var(--muted);font-size:.86rem}}.value{{font-size:2.3rem;letter-spacing:-.05em;font-weight:780;margin:5px 0 0}}
.value.good{{color:var(--green)}}.value.small{{font-size:1.8rem}}
section{{margin-top:40px}}.panel h2{{margin:0 0 22px;font-size:1.25rem}}.twocol{{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}}
.bar-row{{display:grid;grid-template-columns:minmax(100px,125px) minmax(60px,1fr) 74px;gap:12px;align-items:center;margin:21px 0;font-size:.85rem}}
.bar-row strong{{text-align:right;font-variant-numeric:tabular-nums}}
.track{{width:100%;height:11px;border-radius:8px;background:var(--surface2);overflow:hidden}}
.bar{{height:100%;min-width:4px;border-radius:8px;background:linear-gradient(90deg,var(--accent),var(--purple))}}
.stats{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.stat{{min-width:0;padding:16px 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface2)}}.stat strong{{display:block;font-size:clamp(1.15rem,2.4vw,1.6rem);line-height:1.25;letter-spacing:-.03em;font-variant-numeric:tabular-nums}}.stat span{{display:block;margin-top:7px;font-size:.82rem;color:var(--muted)}}
.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:12px}}table{{border-collapse:collapse;width:100%;min-width:560px;font-size:.91rem}}th,td{{padding:18px 18px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}thead{{background:var(--surface2)}}thead th{{color:var(--muted);font-size:.79rem;font-weight:700;letter-spacing:.02em}}tbody tr:last-child td{{border-bottom:0}}tbody tr:nth-child(2n){{background:#1b2536}}.number{{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}}.passed{{display:inline-block;border:1px solid #28694c;border-radius:999px;padding:4px 9px;background:#133a2b;color:var(--green);font-weight:650}}
.case-id{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.84rem}}
.note{{padding:20px;border-left:3px solid var(--accent);background:var(--surface);border-radius:0 10px 10px 0;color:var(--muted);font-size:.92rem;margin-top:26px}}
footer{{margin-top:50px;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:24px}}
code{{color:var(--fg);overflow-wrap:anywhere}}
@media(max-width:800px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.twocol{{grid-template-columns:1fr}}}}
@media(max-width:540px){{main{{padding:24px 16px 55px}}nav{{margin-bottom:38px}}.grid{{gap:10px}}.card,.panel{{padding:17px}}.value{{font-size:1.9rem}}.bar-row{{grid-template-columns:88px minmax(40px,1fr) 65px;gap:8px;font-size:.73rem}}}}
{COMPARISON_CSS}
</style>
</head>
<body>
<main>
<nav><div class="logo"><span>◇</span> LLM EVALUATION LAB</div><a class="navlink" href="{e(RUN_URL)}" rel="noopener noreferrer">Ver execução no GitHub ↗</a></nav>
<header>
<div class="eyebrow">Experimento real · Evidência verificada</div>
<h1>Qualidade medida.<br>Resultados rastreáveis.</h1>
<p class="sub">Uma avaliação objetiva e reproduzível de respostas de um modelo de linguagem. Métricas extraídas de uma execução real, sem estimativas inventadas.</p>
<p class="meta">Experimento <strong>{e(doc['experiment_id'])}</strong> · Modelo {e(doc['model'])} · {e(doc['timestamp_utc'])} · Execução #{e(doc['run_id'])}</p>
</header>
<div class="grid" aria-label="Resumo dos resultados">
<div class="card"><div class="label">Taxa de aprovação</div><div class="value good">{summary['pass_rate']:.0%}</div></div>
<div class="card"><div class="label">Casos avaliados</div><div class="value">{summary['total']}</div></div>
<div class="card"><div class="label">Falhas de critério</div><div class="value">{summary['failed']}</div></div>
<div class="card"><div class="label">Erros de execução</div><div class="value">{summary['errors']}</div></div>
</div>
<section class="twocol">
<div class="panel"><h2>Latência por teste</h2>{bars}</div>
<div class="panel"><h2>Tempos observados</h2>
<div class="stats"><div class="stat"><strong>{average} ms</strong><span>Média</span></div>
<div class="stat"><strong>{fastest} ms</strong><span>Mínimo</span></div>
<div class="stat"><strong>{slowest} ms</strong><span>Máximo</span></div>
<div class="stat"><strong>3 / 3</strong><span>Casos aprovados</span></div></div>
<div class="note">A latência reflete o tempo observado pela aplicação entre requisição e resposta HTTP; não equivale apenas ao tempo de geração dos tokens.</div>
</div>
</section>
<section class="panel"><h2>Resultados por caso</h2><div class="table-wrap">
<table><thead><tr><th>Caso</th><th>Critério</th><th>Status</th><th class="number">Latência</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
{comparison_html}
<section class="panel"><h2>Metodologia e limites</h2>
<p>Três casos sintéticos de instruções simples, avaliados com as regras determinísticas <strong>exact</strong>, <strong>contains</strong> e <strong>regex</strong>. Uma repetição por caso; temperatura zero. Aprovação significa atendimento à regra específica, não validação ampla de segurança, precisão ou raciocínio.</p>
<p>Essa amostra <strong>não</strong> representa um benchmark geral nem garante resultados futuros. Consumo de tokens, Neurons e custo financeiro não foram medidos. Nenhuma resposta completa ou prompt é publicado neste painel.</p>
<p>Fonte primária: <a href="{e(RUN_URL)}" rel="noopener noreferrer">GitHub Actions · execução {e(doc['run_id'])}</a> · Commit <code>{e(doc['revision_sha'])}</code>.</p>
</section>
<footer>LLM Evaluation Lab · Snapshot público revisado, estático e imutável até nova revisão · Sem chamadas à IA ao abrir esta página.</footer>
</main></body></html>
"""


def build(root: Path, output: Path) -> None:
    doc = parse_snapshot((root / SNAPSHOT).read_bytes())
    advanced = read_evidence(root / ADVANCED_SNAPSHOT)
    # Both source snapshots are validated before creating any public output.
    markup = render(doc, advanced)
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(markup, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")


def main() -> int:
    try:
        build(Path("."), Path("_site"))
    except (DashboardValidationError, OSError, UnicodeError, ValueError):
        print("Public dashboard build blocked: invalid approved snapshot.", file=sys.stderr)
        return 2
    print("Static public dashboard generated from two approved real-run summaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
