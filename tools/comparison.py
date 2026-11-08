"""Static, reviewed multi-experiment comparison for public GitHub Pages.

No networking, runtime account information, inference, dynamic JavaScript, or
unreviewed artifacts. Historical runs use different prompts: this is NOT a
head-to-head benchmark and must not be used to claim model superiority.
"""

from __future__ import annotations

import html
from statistics import mean

if __package__:
    from .validate_advanced_evidence import validate_evidence
    from .validate_robustness_evidence import validate_robustness_evidence
    from .robustness_panel import ROBUSTNESS_CSS, render_robustness_details
else:  # python tools/build_dashboard.py (script execution)
    from validate_advanced_evidence import validate_evidence
    from validate_robustness_evidence import validate_robustness_evidence
    from robustness_panel import ROBUSTNESS_CSS, render_robustness_details


RUN_PREFIX = "https://github.com/magnnwsb2/llm-evaluation-lab/actions/runs/"
COMMIT_PREFIX = "https://github.com/magnnwsb2/llm-evaluation-lab/commit/"

# Deliberately plain CSS. It is embedded in an existing no-script static page.
COMPARISON_CSS = """
/* Stage 018: independently reviewed historical-run comparison */
.compare-section>h2{font-size:clamp(1.6rem,3.6vw,2.15rem);line-height:1.17;letter-spacing:-.025em;margin:8px 0 20px}
.compare-section>.eyebrow{font-size:.82rem}
.compare-intro{max-width:760px;color:var(--muted);font-size:.99rem;margin:12px 0 26px}
.compare-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.compare-card{border:1px solid var(--line);background:linear-gradient(155deg,var(--surface),#111c2d);border-radius:18px;padding:20px;min-width:0}
.compare-card.advanced{border-color:#735e3b}
.compare-topline{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.compare-tag{display:inline-flex;border:1px solid var(--line);border-radius:999px;padding:4px 10px;font-size:.75rem;color:var(--muted)}
.compare-card h3{margin:15px 0 6px;font-size:1.25rem}
.compare-percent{font-size:clamp(2.1rem,4vw,3rem);line-height:1.16;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-.045em}
.compare-percent.advanced-percent{color:#ffcd91}
.compare-numbers{display:flex;gap:14px;flex-wrap:wrap;margin:12px 0 15px;color:var(--muted);font-size:.84rem}
.compare-numbers strong{color:var(--fg);font-variant-numeric:tabular-nums}
.compare-source{display:flex;gap:8px 12px;flex-wrap:wrap;align-items:center;font-size:.9rem}
.compare-source code{font-size:.9rem;letter-spacing:.01em}
.compare-source a{display:inline-flex;align-items:center;min-height:44px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;text-decoration:underline;text-underline-offset:3px;overflow-wrap:anywhere}
.compare-source a:focus-visible{outline:2px solid var(--accent);outline-offset:4px}
.compare-notice{border-left:3px solid var(--accent);border-radius:0 10px 10px 0;background:var(--surface2);padding:14px 16px;color:var(--muted);font-size:.88rem;margin:21px 0 0}
.compare-table{margin-top:21px}
.compare-table table{min-width:710px}
.compare-table caption{text-align:left;caption-side:top;font-size:.9rem;font-weight:700;padding:0 0 12px}
.compare-table th,.compare-table td{white-space:nowrap}
.compare-table td a{text-decoration:underline;text-underline-offset:3px}
.compare-subheading{font-size:1.08rem;margin:28px 0 12px}
.status-fail{display:inline-block;color:#ffcd91;font-weight:750;background:#4b3320;border:1px solid #966c3d;border-radius:999px;padding:4px 9px}
.diagnostic-summary{margin-top:23px;padding:20px 21px;border:1px solid #7e6343;background:linear-gradient(125deg,#29231f,#1b2230);border-radius:14px}
.diagnostic-summary h3{font-size:1rem;color:#ffe1bb;margin:0 0 8px}
.diagnostic-summary p{margin:0;color:#d7cbbb;font-size:.9rem}
.repeat-observation{margin:20px 0 0;display:flex;gap:16px;flex-wrap:wrap;align-items:center;border:1px solid var(--line);border-radius:12px;padding:17px 20px;background:var(--surface2)}
.repeat-observation strong{color:var(--green)}
.repeat-observation span{color:var(--muted);font-size:.88rem}
.compare-footer{color:var(--muted);font-size:.86rem;line-height:1.7;margin:18px 0 0}
@media(max-width:940px){.compare-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:800px){.compare-grid{grid-template-columns:1fr}}
@media(max-width:540px){.compare-section>h2{font-size:1.6rem}.compare-card{padding:18px}.compare-percent{font-size:2.25rem}.compare-numbers{gap:8px 14px}.repeat-observation{align-items:flex-start;flex-direction:column;gap:5px}.compare-source{display:grid;grid-template-columns:minmax(0,1fr);align-items:stretch}.compare-source a{min-height:44px;width:100%;font-size:.9rem}.compare-source code{font-size:.88rem}}
""" + ROBUSTNESS_CSS


def _fmt_percent(rate: float) -> str:
    if rate == 1:
        return "100%"
    return f"{rate * 100:.1f}".replace(".", ",") + "%"


def _fmt_ms(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " ms"


def _run_link(run_id: str) -> str:
    return html.escape(RUN_PREFIX + run_id, quote=True)


def _commit_link(revision: str) -> str:
    return html.escape(COMMIT_PREFIX + revision, quote=True)


def render_comparison(smoke: dict, advanced: dict, robustness: dict | None = None) -> str:
    """Render using only pre-validated smoke data and strictly approved advanced.

    The calling builder has already checked the smoke record against its fixed
    provenance allowlist. This function independently validates advanced data.
    """
    validate_evidence(advanced)
    if robustness is not None:
        validate_robustness_evidence(robustness)
    e = lambda value: html.escape(str(value), quote=True)
    records = (smoke, advanced) if robustness is None else (smoke, advanced, robustness)
    cards = []
    table_rows = []
    for index, record in enumerate(records):
        is_advanced = index == 1
        is_robustness = index == 2
        experiment = e(record["experiment_id"])
        summary = record["summary"]
        cases = record["cases"]
        latency_average = round(mean(case["latency_ms"] for case in cases))
        run_id = record["run_id"]
        sha = record["revision_sha"]
        card_style = " robustness" if is_robustness else " advanced" if is_advanced else ""
        rate_style = " robustness-percent" if is_robustness else " advanced-percent" if is_advanced else ""
        card_title = ("Instruções conflitantes, dados não confiáveis e JSON"
                      if is_robustness else "Extração estruturada e classificação"
                      if is_advanced else "Instruções simples")
        tag = ("Robustez · 3 casos" if is_robustness else
               "Avançado · 3 casos" if is_advanced else "Básico · 3 casos")
        cards.append(
            f'<article class="compare-card{card_style}">'
            f'<div class="compare-topline"><span class="compare-tag">{tag}</span>'
            f'<span class="label">Execução real revisada</span></div>'
            f'<h3>{experiment}</h3>'
            f'<div class="label">{card_title}</div>'
            f'<div class="compare-percent{rate_style}">{_fmt_percent(summary["pass_rate"])}</div>'
            f'<div class="compare-numbers">'
            f'<span><strong>{summary["passed"]}</strong> '
            f'{"aprovado" if summary["passed"] == 1 else "aprovados"}</span>'
            f'<span><strong>{summary["failed"]}</strong> '
            f'{"reprovado" if summary["failed"] == 1 else "reprovados"}</span>'
            f'<span><strong>{summary["errors"]}</strong> erros</span>'
            f'</div>'
            f'<div class="compare-numbers">'
            f'<span><strong>{summary["total"]}</strong> casos</span>'
            f'<span><strong>{_fmt_ms(latency_average)}</strong> média HTTP</span>'
            f'</div>'
            f'<div class="compare-source">'
            f'<a href="{_run_link(run_id)}" rel="noopener noreferrer">'
            f'GitHub Actions #{e(run_id)} ↗</a>'
            f'<a href="{_commit_link(sha)}" rel="noopener noreferrer">'
            f'<code>{e(sha[:12])}</code> ↗</a>'
            f'</div></article>'
        )
        table_rows.append(
            f'<tr><th scope="row"><span class="case-id">{experiment}</span></th>'
            f'<td class="number">{summary["total"]}</td>'
            f'<td class="number">{summary["passed"]}</td>'
            f'<td class="number">{summary["failed"]}</td>'
            f'<td class="number">{summary["errors"]}</td>'
            f'<td class="number">{_fmt_percent(summary["pass_rate"])}</td>'
            f'<td class="number">{_fmt_ms(latency_average)}</td></tr>'
        )

    diag_labels = {
        "content_match_format_violation": "Conteúdo correto; formato inválido",
        "strict_pass": "JSON estritamente válido",
        "content_mismatch": "Conteúdo diferente do esperado",
        "unparseable": "JSON não interpretável com segurança",
        "unavailable": "Indisponível por erro do provedor",
    }
    advanced_rows = []
    for case in advanced["cases"]:
        case_name = e(case["id"])
        rule = e(case["assertion_type"])
        status = (
            '<span class="passed">Aprovado</span>'
            if case["status"] == "pass"
            else '<span class="status-fail">Reprovado</span>'
            if case["status"] == "fail"
            else '<span>Erro de execução</span>'
        )
        diag = case.get("diagnostic")
        detail = diag_labels[diag] if diag is not None else "—"
        advanced_rows.append(
            f'<tr><th scope="row"><span class="case-id">{case_name}</span></th>'
            f'<td>{rule}</td><td>{status}</td>'
            f'<td class="number">{_fmt_ms(case["latency_ms"])}</td>'
            f'<td>{e(detail)}</td></tr>'
        )

    robustness_section = (
        render_robustness_details(robustness)
        if robustness is not None else ""
    )
    comparison_title = (
        "Três experimentos. Três evidências."
        if robustness is not None else "Dois experimentos. Duas evidências."
    )
    comparison_description = (
        "Três amostras independentes do mesmo modelo, com tarefas diferentes."
        if robustness is not None else
        "Duas amostras independentes do mesmo modelo, com tarefas diferentes."
    )
    source_links = (
        f'e <a href="{_run_link(robustness["run_id"])}" rel="noopener noreferrer">'
        f'#{e(robustness["run_id"])}</a>'
        if robustness is not None else ""
    )
    record_count_word = "três" if robustness is not None else "dois"
    repeat = advanced["repeated_prompt"]
    repeat_text = (
        "Iguais" if repeat["outcome"] == "same"
        else "Diferentes" if repeat["outcome"] == "different"
        else "Indisponível"
    )
    return f"""<section class="panel compare-section" id="comparacao" aria-labelledby="compare-heading">
<div class="eyebrow">Resultados reais · Comparação descritiva</div>
<h2 id="compare-heading">{comparison_title}</h2>
<p class="compare-intro">{comparison_description}
As porcentagens mostram somente quantos critérios foram atendidos em cada execução:
não constituem uma comparação controlada, ranking ou benchmark geral.</p>
<div class="compare-grid">
{''.join(cards)}
</div>
<div class="compare-table table-wrap" role="region" tabindex="0" aria-label="Tabela comparativa; deslize horizontalmente em telas pequenas">
<table><caption>Indicadores por execução</caption>
<thead><tr><th scope="col">Experimento</th><th scope="col" class="number">Casos</th>
<th scope="col" class="number">Aprovados</th><th scope="col" class="number">Falhas</th>
<th scope="col" class="number">Erros</th><th scope="col" class="number">Aprovação</th>
<th scope="col" class="number">Latência média</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table>
</div>
<p class="compare-notice">As latências são tempos de ida e volta observados pela aplicação,
não apenas de geração de tokens. Médias por três chamadas; não inferem
consumo, faturamento ou desempenho futuro.</p>
<h3 class="compare-subheading">Experimento avançado · Caso a caso</h3>
<div class="table-wrap" role="region" tabindex="0" aria-label="Resultados do experimento avançado; deslize horizontalmente em telas pequenas">
<table><caption>Regras objetivas e diagnóstico sem alterar a nota</caption>
<thead><tr><th scope="col">Caso</th><th scope="col">Critério</th><th scope="col">Resultado</th>
<th scope="col" class="number">Latência</th><th scope="col">Diagnóstico</th></tr></thead>
<tbody>{''.join(advanced_rows)}</tbody></table>
</div>
<div class="diagnostic-summary" aria-labelledby="json-diagnosis-heading">
<h3 id="json-diagnosis-heading">Por que o JSON falhou?</h3>
<p>O caso <strong>json-ticket-001</strong> continha os três valores esperados, mas a
resposta incluiu uma introdução e delimitadores Markdown. O contrato exigia
exclusivamente um objeto JSON. <strong>A falha estrita permanece uma reprovação</strong>
na nota de 2/3. Nenhum texto integral da resposta é publicado aqui.</p>
</div>
<div class="repeat-observation">
<span>Prompt repetido: <code>{e(repeat["first_id"])}</code> e <code>{e(repeat["second_id"])}</code></span>
<strong>{e(repeat_text)} · 1 par observado</strong>
<span>Concordância de duas respostas não demonstra determinismo ou correção geral.</span>
</div>
{robustness_section}
<p class="compare-footer">Fontes históricas: execuções
<a href="{_run_link(smoke["run_id"])}" rel="noopener noreferrer">#{e(smoke["run_id"])}</a>
e <a href="{_run_link(advanced["run_id"])}" rel="noopener noreferrer">#{e(advanced["run_id"])}</a>
{source_links}.
Os {record_count_word} registros são revisados e estáticos. Atualizações de resultados exigem nova revisão;
nenhuma chamada à IA ocorre ao abrir a página.</p>
</section>"""
