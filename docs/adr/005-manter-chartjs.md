# ADR 005 — Manter Chart.js

Status: decisão proposta; gráficos atuais preservados.

Contexto: [V] Chart.js e vue-chartjs constam em [package.json:24](../../web-smart-fan-iot/frontend/package.json#L24).

Decisão: reutilizar Chart.js no histórico, scatter previsto/real e importância; agregação/limite de pontos fica na API.

Alternativas: ECharts atende ao escopo, mas migrar reabre comportamento de eixos, lacunas, tooltips e testes sem necessidade demonstrada.

Consequências: manter metadados brutos para energia/cobertura; não calcular métricas de ML com pontos reduzidos do gráfico.

Se remover Chart.js sem equivalente, perde-se visualização 2D obrigatória; não manter duas bibliotecas de gráficos.

Ver [frontend](../plano/03-arquitetura.md#9-frontend-tempo-real-e-cena-3d) e [ML](../plano/03-arquitetura.md#10-ml-datasets-e-modelos).
