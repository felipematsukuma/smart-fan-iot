# ADR 007 — Separar live, lab e legado

Status: decisão proposta; não altera buckets/retencões existentes.

Contexto: [V] O legado usa electrical_measurement e tag device_id em [mqtt_service.py:101](../../web-smart-fan-iot/backend/app/mqtt_service.py#L101).

Decisão: preservar legado; buckets live/lab separados, measurements hvac_telemetry/hvac_insight/hvac_lab_sample e tipos fixos; rótulos só em artefatos de laboratório.

Retenção proposta: live 30 dias, lab 7 dias, sem mudar retenção legada automaticamente; amostra lab <=100 mil/dataset e <=300 mil global.

Tags de cardinalidade limitada: device_id/zone/equipment_type; IDs de evento/boot/modelo/dataset em fields. Dedupe usa chave de ponto determinística e registro PG.

Alternativas: um bucket mistura massa de treino com prognóstico; tag por evento explode cardinalidade; guardar milhão de registros somente no browser não atende geração massiva.

Consequências: consultas distintas por domínio e migração incremental; medir ingestão/consulta com massa isolada; backup antes de mudar retenção.

Ver [arquitetura, seção 6](../plano/03-arquitetura.md#6-postgresql-influxdb-e-modelo-inicial).
