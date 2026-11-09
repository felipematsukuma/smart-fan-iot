# Gravador e histórico HVAC — M05

O writer consome `q.telemetry.writer` com ACK manual e prefetch 32. Usa somente suas
credenciais PostgreSQL/RabbitMQ e um token InfluxDB que escreve no bucket `live`.
O token administrativo permanece no bootstrap. O serviço roda como UID 10001,
sem porta publicada, com limite de 256 MiB e uma CPU.

## Persistência e identidade

1. Exige contrato de telemetria, rota e message ID coerentes. O publicador deve ser
   `gateway`; eventos anteriores a M04 sem `user_id` só são admitidos quando o hash
   corresponde exatamente ao registro durável do gateway.
2. Grava a inbox antes de confirmar a entrega RabbitMQ.
3. Reserva no PostgreSQL a chave `(measurement, tags, timestamp)` e os hashes do
   evento e da linha. Outro ID usando o mesmo ponto é falha permanente preservada.
4. Escreve `hvac_telemetry` com timestamp original em nanossegundos, sem aritmética
   de ponto flutuante. Nulos omitem fields e qualidade é preservada; não viram zero.
5. Somente após HTTP 204 do InfluxDB conclui a inbox e grava o evento
   `telemetry.persisted`/outbox na mesma transação PostgreSQL.
6. Publica a outbox com mandatory/confirms. Falha entre Influx e PG regrava bytes
   idênticos; falha após confirmação AMQP permite reentrega idempotente.

O InfluxDB combina fields ao receber pontos com a mesma identidade; por isso o UUID
em field não substitui a reserva relacional. Referência: [duplicatas no InfluxDB OSS 2](https://docs.influxdata.com/influxdb/v2/write-data/best-practices/duplicate-points/).

Falhas classificadas de dependência mantêm a inbox pendente mesmo após cinco
tentativas, com backoff limitado; uma indisponibilidade do banco não deve descartar
telemetria válida. Falhas de conteúdo/identidade permanecem na quarentena/DLQ.
Readiness verifica dependências; liveness é independente de sua disponibilidade.

## Consultas compartilhadas

O [cliente compartilhado](../../packages/smartfan_common/src/smartfan_common/influx_v2.py)
fornece histórico bruto paginado por timestamp/zona/tipo, limite de 1000 linhas,
intervalo máximo de 31 dias, validação de IDs e orçamento de resposta de 8 MiB.
Consultas de gráficos agregam no banco e retornam no máximo 1000 pontos. Campos
numéricos usam filtro estático para permitir pushdown; pivot antecede group para
não misturar tipos booleanos, floats e strings na coluna `_value`.

A [integração de energia](../../packages/smartfan_common/src/smartfan_common/energy_v2.py)
usa potência bruta e trapézios, quebra em amostras faltantes, mudança de boot e gaps
acima de seis segundos. Gráfico agregado não é entrada de contabilidade energética.
A API e a apresentação de cobertura ficam para M06/M07; o legado continua preservado.

## Verificação local

`tools/bootstrap/test-writer.ps1` executa mapping, contratos e integrações reais.
`tools/bootstrap/benchmark-influx.ps1` gera um bucket descartável separado de live/lab,
confere um milhão de vetores e mede consultas; remove somente esse bucket ao terminar.

| Ensaio na mesma máquina | Resultado observado |
|---|---|
| Capacidade: 1 M vetores, dez equipamentos, batches de 5000 | 30,001 s; contagem exata |
| Consulta de 24 h, um equipamento, seis canais agregados | Primeira consulta 0,060 s; p95 de 20 repetições 0,123 s |
| Limite de gráfico | Máximo observado 994 pontos |
| Processo gerador do ensaio | Pico RSS 42,61 MiB; não representa RAM do InfluxDB/Compose |
| Interrupções de writer e InfluxDB | Fila/inbox crescem e escoam na retomada; nenhum persisted novo enquanto InfluxDB indisponível |

Medição em Docker local, com demais serviços ligados; cache do sistema operacional
não foi limpo. A primeira consulta não representa um ensaio de cache frio. A capacidade
acima mede InfluxDB diretamente, não certifica a taxa do fluxo completo AMQP/PG/writer.
Treino, inferência, benchmark integrado, CI remoto e scan das imagens permanecem pendentes.
Reservas de pontos preservam o mínimo de 31 dias; limpeza operacional e backup/restore
serão consolidados em M18 sem remover pendências.

Remover este serviço interrompe a persistência histórica e a confirmação que habilita
inferência e frames em tempo real.
