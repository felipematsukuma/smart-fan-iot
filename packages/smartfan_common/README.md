# Núcleo compartilhado — M00

## Entrega durável opcional — M02

A versão 0.3.0 acrescenta o extra `smartfan-common[reliability]`, com migrações Alembic, inbox/outbox, retry/DLQ, RLS, leases, publicação AMQP confirmada e auxiliares de health/logs. [Operação, garantias e testes](./src/smartfan_common/reliability/README.md). Não altera a semântica dos contratos v1/v2 nem cria consumidores automaticamente.

## Contratos v2 — implementação local

A versão 0.2.0 acrescenta `contracts_v2`, `routing_v2` e `features_v2`, preservando os imports, schemas e fixtures v1. A aplicação operacional do ventilador ainda usa seus contratos anteriores; disponibilizar a biblioteca não migra o transporte.

- Envelope v2: `id`, `schema_version`, `timestamp`, `tipo`, `dispositivo`, `correlation_id`, `metadata`, `conteudo`; modelos fechados e datas UTC reais.
- RUL v2 é `rul_calendar_hours`; não existe alias/conversão da RUL de operação v1.
- Cinco sensores, dois atuadores, frames, insights, comandos/ACK, disponibilidade, receipts, alertas, jobs, modelos e quarentena têm conteúdos tipados. Comando com compressor ligado e ventilador desligado é recusado.
- `parse_event_v2` limita 16 KiB por evento normal e 32 KiB por quarentena. `serialize_event_v2` produz bytes para persistir uma vez; retries reutilizam esses bytes e seu SHA-256, sem enriquecer o mesmo ID.
- `clock_scale` só aceita 1. Frescor/expiração usam relógio UTC injetado; transporte deve acrescentar autorização, boot/revisão e registro confiável de recepção.
- Inteiros JSON matematicamente equivalentes (120 e 120.0) são aceitos, mas strings/booleanos não são convertidos. Schema e TypeScript compartilham fixtures incluindo microssegundos.
- Comparação de identidade do comando, origem do frame e progresso<=total são invariantes semânticas: usar o validador completo, não somente JSON Schema. O frontend aplica essas mesmas invariantes após AJV.
- As features v1/v2 alimentam um único kernel causal por `FeatureSample`; não há conversão de wire v2 em wire v1 nem cópia do algoritmo.
- `routing_v2` é topologia declarativa: não cria broker, filas, permissões nem serviços. Receipts são exclusivos de MQTT; eventos internos não possuem rota MQTT.

Na raiz, com o ambiente Python de desenvolvimento:

```powershell
web-smart-fan-iot/backend/.venv/Scripts/python.exe tools/export_contracts_v2.py
web-smart-fan-iot/backend/.venv/Scripts/python.exe tools/export_contracts_v2.py --check
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m pytest -c packages/smartfan_common/pyproject.toml packages/smartfan_common/tests -q
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m mypy --config-file packages/smartfan_common/pyproject.toml packages/smartfan_common/src
```

No frontend: `npm run contracts:v2:types`, `npm run contracts:v2:types:check`, `npm test`, `npm run typecheck`, `npm run lint`, `npm run format:check` e `npm run build`. Os geradores verificam conteúdo independentemente de LF/CRLF; a formatação respeita finais de linha do checkout.

Validação local desta entrega: 134 testes do pacote (incluindo v1), 216 testes frontend e 153 testes backend; Ruff/mypy, ESLint/vue-tsc, Prettier, geração e build frontend aprovados. CI remoto, provisionamento de brokers e aceite AIoT ponta a ponta ainda não executados. A biblioteca não possui serviço/healthcheck próprio.

## Entrega v1 preservada

Primeira implementação dos contratos do plano AIoT. Ainda não substitui a ingestão, API ou WebSocket do primeiro bimestre.

- Pydantic é a fonte dos contratos fechados: versão, identidade, UTC, cinco sensores, dois atuadores, comandos/ACK, previsões, alertas e jobs.
- JSON Schema exportado e tipos TypeScript gerados evitam manter dois contratos manualmente.
- Python e TypeScript usam as mesmas fixtures válidas/inválidas. Campos extras, rótulos, tipos coercíveis e números não finitos são rejeitados.
- As faixas numéricas são limites amplos do simulador, não especificações de fabricante.
- Validade estrutural não autoriza um comando: expiração, frescor, ACL e intertravamentos devem ser aplicados nos módulos consumidores.
- Features usam somente o passado, reiniciam após lacunas, boot ou transição do compressor e rejeitam duplicados/fora de ordem. Compressor desligado gera status `inactive`, sem vetor de prognóstico. Há limites de dispositivos e amostras em memória; `forget` libera explicitamente um dispositivo desativado. Faltantes não viram zero.
- A versão inicial tem 18 features: média, desvio populacional e inclinação por segundo dos cinco sensores; diferença térmica carcaça–exterior; taxa de resfriamento interno por minuto; cobertura mínima dos sensores.
- `iter_features` produz o batch em memória limitada usando a mesma implementação online. `extract_batch` é a conveniência que materializa a lista, indicada para testes/datasets pequenos. Uma otimização NumPy futura deverá preservar os resultados e a causalidade.

`coverage` no vetor é a menor fração de valores presentes dos cinco sensores entre as observações retidas, não cobertura temporal de uma consulta de histórico. Os parâmetros de janela devem acompanhar o artefato treinado, além da versão/ordem de features.

Os contratos incluem estado, disponibilidade e resultados distintos de comando (`applied`, `rejected`, `expired`). O ID do envelope identifica a solicitação; `command_id` no ACK aponta para esse ID. A solicitação inclui o boot esperado do dispositivo. Campos de ausentes devem corresponder exatamente aos sensores nulos, sem duplicações. RUL indisponível não pode conter uma previsão numérica.

[topology.py](./src/smartfan_common/topology.py) fecha exchanges, filas, bindings e prefetch; os testes verificam que cada exemplo válido possui consumidor. O helper MQTT não permite republicar jobs ou eventos derivados do backend nos tópicos do dispositivo. Autenticação do produtor continua sendo responsabilidade do transporte.

Na raiz do repositório, com o Python de desenvolvimento do backend:

```powershell
web-smart-fan-iot/backend/.venv/Scripts/python.exe tools/export_contracts_v1.py
web-smart-fan-iot/backend/.venv/Scripts/python.exe tools/export_contracts_v1.py --check
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m pytest -c packages/smartfan_common/pyproject.toml packages/smartfan_common/tests -q
```

No frontend, gere os tipos com `npm run contracts:types` e confira com `npm run contracts:types:check`, depois execute typecheck e testes. O gerador de tipos é ferramenta do frontend; o backend continua Python.

O exportador mantém cópias geradas do schema e fixtures dentro do contexto Docker do frontend. Elas são verificadas por `--check` e não devem ser editadas manualmente. A formatação JSON canônica é controlada pelo exportador, por isso esses dois arquivos estão excluídos do Prettier.

O timestamp de uma configuração MQTT Last Will não representa automaticamente o instante da desconexão. O gateway futuro deve construir o evento de disponibilidade com o tempo observado no recebimento e o boot correto. Disponibilidade não substitui frescor das leituras.

Os helpers de tempo recebem um relógio explícito. `command_expired` rejeita tanto expiração já atingida quanto prazo anterior à criação. `event_fresh` não aceita amostras futuras. Não há dependência de relógio real nos testes de contrato.
