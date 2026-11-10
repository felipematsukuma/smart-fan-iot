# M13 — Inferência e alertas preditivos

[V] Serviço Python permanente, usuário não-root, 640 MiB/1 CPU e uma thread BLAS.
Consome `q.inference` com identidade AMQP própria, prefetch 32 e ACK depois do
recebimento durável. Não treina, não altera rótulos e não comanda atuadores.

## Origem, janela e idempotência

[V] [Worker](./worker.py) confere produtor autenticado, rota, ID e receipt original
do gateway: dispositivo, boot, sequência, horário observado e digest das leituras.
Somente amostras com idade de até seis segundos produzem resultados live. Backlog
antigo recebe dedupe durável com payload nulo; já está no InfluxDB e não vira
previsão atual. Timestamp da fonte e `observed_at` nunca são atualizados no replay.

[V] [Janelas](./window.py) recuperam somente os 60 segundos anteriores à amostra,
do mesmo boot, com limite de 1.000 linhas. A amostra atual é excluída da consulta.
Falha na recuperação inicia aquecimento; o cálculo usa o mesmo kernel causal
instalável do treino. Sem modelo, janela válida ou compressor ativo, os números
ficam nulos e o status explica a abstenção.

[V] `inference_results` reserva um resultado por evento-fonte. Frame e insight,
inbox concluída e outbox são transacionais; IDs derivados são determinísticos.
Retry reutiliza os bytes já calculados/commitados, incluindo versão e origem.
O cache de tentativa é limitado a 256 fontes e não substitui o registro durável.

## Ativação de modelos

[V] [ModelRuntime](./models.py) trata `model.available` como aviso. A autoridade
é o registro PostgreSQL: candidato completo, aprovado, desired, revisão e hash.
Verifica manifesto, bundle de até 64 MiB, features/unidades e previsão de fumaça
antes da troca. Não há upload de pickle nem caminho fornecido pelo navegador.

[V] Após carregar, bloqueia a mesma seleção usada pela promoção e confere novamente
aprovação, hash e revisão. Troca a referência sob lock e registra ativação, auditoria
e outbox. Enquanto o commit não estiver confirmado, nenhuma previsão usa o novo
ponteiro. Reconciliação a cada segundo resolve resposta de commit perdida sem
duplicar a ativação. Artefato inválido preserva o modelo anterior aprovado;
revogação da aprovação retira o modelo de uso.

## Qualidade e alertas

[V] Saúde fica em 0–100; RUL usa **horas de calendário**, sem conversão implícita.
Referências de drift são p1/p99 do treino: fração de features fora do intervalo,
1.000 vetores por avaliação, limite 20%, três avaliações ruins para bloquear e
três boas para liberar. Não há retreino automático. Mudança de modelo reinicia
contadores, preservando o bloqueio até recuperação comprovada.

[V] [Controle](../control/alerts.py) valida o receipt do insight e a versão ativa.
Regra padrão: saúde <40 ou RUL <24 h em três previsões válidas consecutivas gera
alerta; saúde >45 e RUL >30 h em dez previsões consecutivas encerra. Ausência,
stale, mudança de boot/modelo/regra ou intervalo >6 s zera candidatos e preserva
alerta ativo. Alertas e transições AMQP/auditoria são transacionais.

[V] Todos os papéis autenticados consultam histórico e metadados em
`GET /api/v1/alerts`, `/insights/status` e `/devices/{id}/predictive-rule`.
Somente administrador altera regra com `PATCH`, revisão esperada, histórico
append-only e auditoria. Dados live e previsões chegam exclusivamente pelo WS.

## Verificação e limites

[V] [Script de teste](../../tools/bootstrap/test-inference.ps1) executa bancos
descartáveis, pipeline real e navegador. Foram aprovados 221 testes Python da
evolução, 153 legados, 231 Vitest, 51 integrações do ensaio completo e sete testes
focados após ampliar a cobertura de revogação e permissões. Fixtures assinadas de
DummyRegressor testam transações e histerese; não certificam qualidade preditiva.
O pipeline real usa os regressores treinados no M12, com origem mantida até o WS.

[N] Carga/p95 integrado, limpeza periódica dos payloads/resultados e ensaio completo
de recuperação são M18. Histórico de insights, apresentação e tendência são M14.
CI remoto e scan são M17. Bons resultados sintéticos não validam manutenção de
equipamento físico. O healthcheck indica dependências/loop vivos, não modelo
aprovado nem previsão disponível; estes têm status próprios.
