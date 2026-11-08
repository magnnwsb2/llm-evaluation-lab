"""Static, response-free presentation of a single audited robustness experiment.

This is a retrospective explanation of the real strict grades, not a new
automated evaluation or evidence of general prompt-injection immunity.
"""

from __future__ import annotations

import html

if __package__:
    from .validate_robustness_evidence import validate_robustness_evidence
else:
    from validate_robustness_evidence import validate_robustness_evidence


ROBUSTNESS_CSS = """
/* Stage 022: compact third-run details with accessible responsive tables */
.compare-card.robustness{border-color:#76556b}
.compare-percent.robustness-percent{color:#dfb4f5}
.robust-section{margin-top:36px;border-top:1px solid var(--line);padding-top:27px}
.robust-section>h3{margin:8px 0 12px;font-size:clamp(1.17rem,2.5vw,1.5rem)}
.robust-section>.compare-intro{margin-bottom:20px}
.robust-result-table table{min-width:760px}
.robust-result-table td,.robust-result-table th{white-space:normal;min-width:92px}
.robust-result-table th:first-child{min-width:155px}
.robust-result-table td:last-child{min-width:230px}
.robust-reason{color:var(--fg);font-weight:600;font-size:.86rem}
.robust-status{color:var(--muted);font-size:.85rem}
.robust-footnotes{margin:16px 0 0;display:grid;gap:11px}
.robust-footnotes p{border-left:3px solid var(--accent);background:var(--surface2);padding:14px 16px;border-radius:0 9px 9px 0;margin:0;color:var(--muted);font-size:.9rem}
.robust-footnotes p strong{color:var(--fg)}
@media(max-width:800px){.robust-section{margin-top:27px}.robust-result-table{overflow-x:auto}}
@media(max-width:540px){.robust-footnotes p{padding:12px}.robust-section>h3{font-size:1.2rem}}
"""


def render_robustness_details(document: dict) -> str:
    """Validate a reviewed record and publish only controlled, safe labels."""
    validate_robustness_evidence(document)
    escape = lambda text: html.escape(str(text), quote=True)
    status_labels = {
        "pass": '<span class="passed">Aprovado</span>',
        "fail": '<span class="status-fail">Reprovado</span>',
        "error": '<span class="robust-status">Erro técnico</span>',
    }
    causes = {
        "exact_prose_possible_incomplete":
            "Explicação em vez da resposta exata; possivelmente incompleta",
        "json_content_and_format":
            "Valores incorretos e Markdown no lugar de JSON puro",
    }
    rows = []
    for case in document["cases"]:
        diagnostic = case.get("diagnostic")
        label = causes[diagnostic["reason"]] if diagnostic else "Instrução não confiável ignorada neste teste"
        rows.append(
            f'<tr><th scope="row"><code>{escape(case["id"])}</code></th>'
            f'<td><code>{escape(case["assertion_type"])}</code></td>'
            f'<td>{status_labels[case["status"]]}</td>'
            f'<td class="number">{case["latency_ms"]:,} ms</td>'.replace(",", ".")
            f'<td class="robust-reason">{escape(label)}</td></tr>'
        )

    return f"""<section class="robust-section" id="robustez" aria-labelledby="robust-heading">
<div class="eyebrow">Evidência real · robustez sintética</div>
<h3 id="robust-heading">Por que dois testes de robustez falharam?</h3>
<p class="compare-intro">Três instruções sintéticas, julgadas por regras estritas.
O teste de dados não confiáveis passou, mas isso não demonstra proteção geral
contra prompt injection. Os outros dois casos permaneceram reprovados.</p>
<div class="table-wrap robust-result-table" role="region" tabindex="0"
aria-label="Casos de robustez; role horizontalmente para ver todos os diagnósticos">
<table>
<caption>Casos e causas revisadas · execução #{escape(document["run_id"])}</caption>
<thead><tr><th scope="col">Caso</th><th scope="col">Critério</th>
<th scope="col">Resultado</th><th scope="col" class="number">Latência</th>
<th scope="col">Diagnóstico retrospectivo</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table></div>
<div class="robust-footnotes">
<p><strong>Precedência:</strong> a resposta mencionou corretamente o registro de maior sequência,
mas não emitiu a decisão exata exigida. Terminou em meio a uma explicação.
<strong>Possivelmente incompleta não significa truncamento confirmado.</strong>
O provedor não forneceu ao relatório original o motivo de parada nem o uso de tokens.</p>
<p><strong>JSON:</strong> o modelo selecionou os valores errados e adicionou
delimitadores Markdown. Portanto ocorreram <strong>erro de conteúdo e de formato</strong>.
Remover o Markdown não corrigiria a seleção dos dados.</p>
<p><strong>Integridade:</strong> os diagnósticos são análises posteriores à execução,
não campos do artefato original e nunca transformam falhas em aprovações.
Nenhuma resposta completa nem prompt é publicado.</p>
</div>
</section>"""
