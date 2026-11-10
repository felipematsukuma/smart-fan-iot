# M14 — Página Insights e histórico autorizado

[V] A [página](../../web-smart-fan-iot/frontend/src/aiot/pages/InsightsPage.vue)
usa somente frames do store WebSocket para saúde, RUL, tendência e comparação
entre dispositivos autorizados. Mostra horário/idade/sequência, qualidade,
relógio real 1×, unidade de calendário e a versão efetivamente usada na fonte.
Ativa/desejada no registro são metadados separados dessa versão.

[V] Idade >6 s, outro boot ou qualidade indisponível oculta os números atuais.
Compressor parado não aparece como saúde zero. Tendências preservam valores
nulos e abrem lacunas quando há troca de modelo/boot ou intervalo >6 s;
janela sem previsão válida apresenta estado vazio. São até 120 amostras live.

[V] Alertas são consultados pela API com filtros/paginação; transição WS solicita
atualização. Consulta periódica a cada dez segundos recupera notificações perdidas.
Não se inventa encerramento por falta de dados. Todos os papéis leem; só admin
edita a regra. O formulário preserva a revisão inicial enquanto aberto: alteração
concorrente causa 409 e exige recarregar/cancelar a edição antes de tentar salvar.

## Histórico, acesso e limites

[V] `GET /api/v1/devices/{id}/insights/history?hours=1&limit=120&before=<uuid>`
retorna previsões já registradas, sem reexecutar modelo. `hours` 1–24, `limit`
1–500, cursor `(sampled_at,source_event_id)` e dispositivo cadastrado obrigatório.
Fonte `historical_predictions`, `rul_unit=calendar_hours`, timestamp/boot/versão
originais e indisponibilidade nula. A UI consulta explicitamente e limita memória
a 1.000 registros; alertas a 300. Falhas/estados vazios têm mensagens próprias.

[V] A [projeção SQL](../../packages/smartfan_common/src/smartfan_common/reliability/migrations/versions/0017_insight_history.py)
concede SELECT só nos campos do histórico. API não lê payload bruto da inferência,
não escreve resultados e não transforma resposta REST em valor live. Consultas
usam o índice por dispositivo/horário. Após retenção dos payloads, a projeção deixa
de expor os registros removidos; o limite de consulta é coerente com 24 h.

## Verificação

[V] 238 Vitest e lint/tipos/formatação aprovados. Doze integrações reais abrangem
histórico/limites/papéis, proteção dos payloads brutos, sete casos de inferência e
cadastro. Playwright usa frames do serviço real, consulta histórico e interrompe
o simulador: números somem e linhas históricas permanecem. Screenshot de revisão
visual conferido localmente; artefato temporário não é versionado.

[N] Comparação com equipamento físico e confiabilidade de prognóstico não são
demonstradas pelo gerador. Injeção guiada de falha e carga/retencão/aceite completo
permanecem M18; esta tela não injeta falha nem treina modelos no navegador.
CI remoto/scan permanecem M17. A [estratégia de M13](../inference/README.md)
define quando previsão e alerta são considerados válidos.
