# Etapa 1 — Inventário do estado atual

Referência: 08/11/2026; código-base `346f7de`, obtido de `origin/main` após `git fetch origin`. Branch documental: `docs/plano-etapa-1-inventario`. Este documento descreve o código-base, não funcionalidades propostas como se estivessem implementadas.

## 1. Método, decisões e limites

| Selo | Significado |
|---|---|
| [V] | Verificado por leitura ou comando; referência de arquivo com linha, ou comando e resultado |
| [I] | Inferência, com sua base explícita |
| [N] | Não confirmado; não equivale a ausência nem a funcionamento |

Decisões do usuário nesta sessão: planejar ar-condicionado split residencial convencional, preservar a história do ventilador, usar a mesma máquina e consolidar toda a documentação antes de implementar. A autorização desta etapa abrange somente este inventário e a conversão do plano anterior em índice. Não autoriza implementação, push ou PR.

Justificativa de domínio: manter redução de desperdício e acompanhamento de consumo, ampliando para manutenção preditiva do compressor. O ar-condicionado oferece relações entre carga térmica, corrente, vibração e temperaturas para os insights exigidos. Isso não significa que ventiladores não possam ter manutenção preditiva. Drenagem de condensado e umidade ficam como possibilidades de evolução, não como sensores já existentes.

[V] A proposta original é residencial e centrada no ventilador ([README.md:3](../../README.md#L3)); o código operacional ainda usa esse domínio ([main.py:80](../../web-smart-fan-iot/backend/app/main.py#L80)). [V] O núcleo M00 já contempla HVAC, conforme seções 6 e 9. [I] Portanto, existem uma aplicação operacional legada e contratos antecipados da evolução; a integração entre elas não pode ser presumida.

Não foram instaladas ferramentas, iniciados containers, modificados dados ou reexecutados testes nesta etapa documental. As execuções anteriores desta mesma sessão são identificadas separadamente na seção 8.

## 2. Árvore comentada — profundidade 3

[V] Inventário obtido por `git ls-files`: 103 arquivos rastreados no código-base. A árvore agrupa arquivos abaixo da profundidade 3; caches, ambientes locais e dependências não são componentes versionados.

```text
smart-fan-iot/
├── README.md                         # problema, arquitetura e execução existentes
├── .gitignore                        # ambientes, builds, dados locais e IDE
├── docs/
│   ├── PLANO-BIMESTRE-2.md            # plano anterior; convertido em índice nesta etapa
│   ├── implementacao-2026-10-26.md    # registro histórico de validação
│   └── revisao-tecnica-2026-10-26.md  # diagnóstico histórico
├── esp32-simulador/
│   ├── src/main.cpp                  # firmware Arduino/ESP32
│   ├── diagram.json                  # circuito Wokwi
│   ├── platformio.ini                # toolchain e bibliotecas
│   ├── wokwi.toml                    # referência ao firmware compilado
│   ├── .vscode/                      # tarefas e extensões
│   └── include/, lib/, test/         # arquivos README de estrutura
├── packages/
│   └── smartfan_common/              # pacote Python instalável M00
│       # pyproject.toml, README, src/, tests/, schema/ e fixtures/
├── tools/
│   ├── export_contracts_v1.py         # exporta schema e fixtures para frontend
│   └── verify_wokwi.py               # ferramenta de verificação do legado
└── web-smart-fan-iot/
    ├── docker-compose.yml            # cinco serviços da aplicação atual
    ├── .env.example                  # nomes e exemplos de configuração
    ├── README.md                     # contratos e operação atuais
    ├── backend/                      # app/, tests/, manifestos e Dockerfile
    ├── frontend/                     # src/, public/, scripts/, manifestos e Dockerfile
    └── mosquitto/                    # config/mosquitto.conf
```

### Entrypoints

| Componente | Entrada e responsabilidade | Evidência |
|---|---|---|
| Firmware | `setup`/`loop`: rede, leitura, comando e proteção local | [V] [main.cpp:285](../../esp32-simulador/src/main.cpp#L285) |
| Backend | `app.main:app`; lifespan inicializa banco, MQTT e scheduler | [V] [main.py:94](../../web-smart-fan-iot/backend/app/main.py#L94), [Dockerfile:18](../../web-smart-fan-iot/backend/Dockerfile#L18) |
| Frontend | Vite carrega `main.ts`, que monta `App.vue` | [V] [main.ts:1](../../web-smart-fan-iot/frontend/src/main.ts#L1) |
| Infraestrutura | Compose declara Mosquitto, PostgreSQL, InfluxDB, backend e frontend | [V] [docker-compose.yml:1](../../web-smart-fan-iot/docker-compose.yml#L1) |
| Núcleo M00 | Biblioteca importável, sem daemon ou servidor próprio | [V] [pyproject.toml:5](../../packages/smartfan_common/pyproject.toml#L5) |

## 3. Stack e dependências reais

As versões abaixo são declarações/locks lidos, não comprovação de versões instaladas ou de imagens já construídas.

| Área | Declaração observada | Evidência |
|---|---|---|
| Backend | Python 3.11-slim; Uvicorn com reload | [V] [Dockerfile:1](../../web-smart-fan-iot/backend/Dockerfile#L1) |
| Dependências Python | FastAPI 0.162.0, Uvicorn 0.54.0, SQLAlchemy 2.0.55, psycopg2-binary 2.9.13 | [V] [requirements.lock:8](../../web-smart-fan-iot/backend/requirements.lock#L8) |
| Validação e IoT | Pydantic 2.14.1, pydantic-settings 2.16.1, influxdb-client 1.50.0, paho-mqtt 1.6.1, APScheduler 3.11.3 | [V] [requirements.lock:5](../../web-smart-fan-iot/backend/requirements.lock#L5) |
| Resolução Python | Requisitos diretos com ranges e constraints do lock; SQLAlchemy limitado a 2.0.x | [V] [requirements.txt:1](../../web-smart-fan-iot/backend/requirements.txt#L1) |
| Frontend | Vue ^3.5.42, Chart.js ^4.5.1, vue-chartjs ^5.3.4, Axios ^1.20.0, AJV ^8.20.0 | [V] [package.json:20](../../web-smart-fan-iot/frontend/package.json#L20) |
| Ferramentas frontend | TypeScript ~6.0.2, Vite ^8.3.5, Vitest ^5.0.5, vue-tsc ^3.3.11; Node >=24 e <25 | [V] [package.json:29](../../web-smart-fan-iot/frontend/package.json#L29) |
| Lock frontend | `package-lock.json` rastreado; Docker executa `npm ci` | [V] `git ls-files`; [Dockerfile:5](../../web-smart-fan-iot/frontend/Dockerfile#L5) |
| Dados e broker | Mosquitto 2.0, PostgreSQL 15-alpine, InfluxDB 2.7-alpine; tags sem digest | [V] [docker-compose.yml:3](../../web-smart-fan-iot/docker-compose.yml#L3) |
| ESP32 | espressif32 6.12.0, ArduinoJson ^6.21.3, PubSubClient ^2.8 | [V] [platformio.ini:1](../../esp32-simulador/platformio.ini#L1) |
| Pacote compartilhado | smartfan-common 0.1.0, Python >=3.11, Pydantic >=2.14.1 e <3 | [V] [pyproject.toml:5](../../packages/smartfan_common/pyproject.toml#L5) |
| Qualidade Python | pytest 9.1.1 no lock; Ruff 0.17.2, mypy 2.4.0, pip-audit 2.10.1 em desenvolvimento | [V] [requirements.lock:26](../../web-smart-fan-iot/backend/requirements.lock#L26), [requirements-dev.txt:1](../../web-smart-fan-iot/backend/requirements-dev.txt#L1) |

[V] Não há declaração de scikit-learn, NumPy, cliente AMQP ou serviço Ollama nos manifestos operacionais lidos. [V] Não há Three.js, Vue Router ou Pinia nas dependências diretas do frontend ([package.json:20](../../web-smart-fan-iot/frontend/package.json#L20)). Isso identifica lacunas; não é proposta automática de adicionar todos esses pacotes.

## 4. Contratos operacionais atuais

### 4.1 MQTT e dispositivo

| Tópico | Origem → destino | Payload e entrega |
|---|---|---|
| `devices/{id}/telemetry` | ESP32 → backend | `device_id`, `is_on`, `voltage_rms`, `current_a`, `power_w`, `timestamp`; opcionais de estado/contadores. Firmware QoS 0, sem retain |
| `devices/{id}/state` | ESP32 → backend | Estado observado, configuração e contadores; retained, publicação QoS 0 |
| `devices/{id}/config` | ESP32 → backend | `device_id`, `auto_mode`, `shutdown_time`; retained, publicação QoS 0 |
| `devices/{id}/command` | Backend → ESP32 | `action: ON/OFF`; QoS 1 e sem retain por padrão |
| `devices/{id}/config/set` | Backend → ESP32 | `auto_mode`, `shutdown_time`; QoS 1 e retained |

[V] Evidências: tópicos do firmware em [main.cpp:22](../../esp32-simulador/src/main.cpp#L22), publicação de estado em [main.cpp:149](../../esp32-simulador/src/main.cpp#L149), telemetria em [main.cpp:322](../../esp32-simulador/src/main.cpp#L322), assinatura QoS 1 em [main.cpp:274](../../esp32-simulador/src/main.cpp#L274) e publicação backend em [mqtt_service.py:221](../../web-smart-fan-iot/backend/app/mqtt_service.py#L221). Assinar com QoS 1 não eleva o QoS 0 do publicador.

[V] O backend limita payload a 2048 bytes, verifica identidade do tópico e valida Pydantic ([mqtt_service.py:61](../../web-smart-fan-iot/backend/app/mqtt_service.py#L61)); os modelos rejeitam campos extras ([schemas.py:43](../../web-smart-fan-iot/backend/app/schemas.py#L43)). O comando REST aceita apenas ON/OFF ([schemas.py:13](../../web-smart-fan-iot/backend/app/schemas.py#L13)).

Exemplo ilustrativo do formato legado, sem representar uma leitura real:

```json
{"device_id":"esp32_fan_01","is_on":true,"voltage_rms":127.0,"current_a":0.4,"power_w":45.72,"timestamp":20000}
```

[V] `timestamp` é uptime em milissegundos; `device_epoch_s` é opcional. Há uma entrada analógica de corrente e um relé; tensão e fator de potência são constantes, potência é derivada ([main.cpp:30](../../esp32-simulador/src/main.cpp#L30), [main.cpp:322](../../esp32-simulador/src/main.cpp#L322)). [I] Três campos elétricos não comprovam três sensores independentes.

[V] Não há ID de comando correlacionado no contrato operacional; a resposta REST `published` confirma publicação, não aplicação no atuador ([main.py:151](../../web-smart-fan-iot/backend/app/main.py#L151)). O firmware publica estado após comandos. Não há LWT no `client.connect(device_id)` lido ([main.cpp:273](../../esp32-simulador/src/main.cpp#L273)).

### 4.2 Persistência e energia

| Banco | Modelo observado | Evidência |
|---|---|---|
| PostgreSQL | Tabela `devices`: PK `id`, `device_id` único/indexado, nome, estado observado, tarifa, horário e habilitação de desligamento | [V] [models.py:9](../../web-smart-fan-iot/backend/app/models.py#L9) |
| Inicialização relacional | `create_all` e criação de dispositivo padrão; não migração Alembic | [V] [main.py:43](../../web-smart-fan-iot/backend/app/main.py#L43), `git ls-files` sem estrutura Alembic |
| InfluxDB | Measurement `electrical_measurement`; tag `device_id`; fields `is_on` inteiro, `current_a`, `power_w`, `voltage_rms`, `device_epoch_s` opcional | [V] [mqtt_service.py:95](../../web-smart-fan-iot/backend/app/mqtt_service.py#L95) |
| Timestamp persistido | UTC de recepção no backend; bucket definido por `INFLUXDB_BUCKET` | [V] [mqtt_service.py:101](../../web-smart-fan-iot/backend/app/mqtt_service.py#L101) |
| Escrita | Síncrona com fronteira de espera limitada; falha gera evento live `persisted: false`, sem fila durável | [V] [database.py:25](../../web-smart-fan-iot/backend/app/database.py#L25), [mqtt_service.py:114](../../web-smart-fan-iot/backend/app/mqtt_service.py#L114) |
| Histórico | Consulta Flux por dispositivo e potência; janela máxima 168 h, teto de 400 mil amostras; redução padrão a 240 pontos | [V] [main.py:268](../../web-smart-fan-iot/backend/app/main.py#L268) |
| Energia | Integração trapezoidal com limite de lacunas de 80 s; metadados calculados antes da redução | [V] [energy.py:30](../../web-smart-fan-iot/backend/app/energy.py#L30), [main.py:335](../../web-smart-fan-iot/backend/app/main.py#L335) |

[N] Retenção efetiva do bucket, volumes ativos, cardinalidade medida e capacidade com 1 milhão de leituras não foram consultadas. A documentação histórica não substitui inspeção do banco atual.

### 4.3 REST e WebSocket

Todas as rotas da tabela são [V], lidas em [main.py:119](../../web-smart-fan-iot/backend/app/main.py#L119); não há prefixo `/api/v1`.

| Método | Rota | Contrato/limites |
|---|---|---|
| GET | `/health` | Estado do processo e conexão MQTT; não comprova prontidão dos bancos |
| GET / POST | `/api/devices` | Listar / cadastrar `device_id` e `name`; duplicado 409 |
| GET | `/api/device/{device_id}` | Cadastro, estado observado e configurações; 404 se ausente |
| POST | `/api/device/{device_id}/command` | ON/OFF; retorna `published` ou 503 |
| PUT | `/api/device/{device_id}/schedule` | Horário, habilitação e tarifa |
| PUT | `/api/device/{device_id}/auto-shutdown` | Hora HH:MM e habilitação booleana |
| PUT | `/api/device/{device_id}/tariff` | Tarifa não negativa e finita |
| GET | `/api/device/{device_id}/metrics` | `range_hours` ou `start/end`, `max_points`; energia, histórico e cobertura |
| WS | `/ws` | Payload legado acrescido de `event: telemetry/state/config`; telemetria inclui `persisted` |

[V] WS verifica Origin quando fornecido, mas não exige login/ticket; clientes entram no mesmo conjunto de conexões ([main.py:362](../../web-smart-fan-iot/backend/app/main.py#L362), [mqtt_service.py:205](../../web-smart-fan-iot/backend/app/mqtt_service.py#L205)). O filtro por dispositivo está no cliente, não é autorização ([useWebSocket.ts:30](../../web-smart-fan-iot/frontend/src/composables/useWebSocket.ts#L30)). Erros REST usam `HTTPException/detail`, não envelope RFC 7807 dedicado. Cadastro não tem paginação na consulta lida ([main.py:127](../../web-smart-fan-iot/backend/app/main.py#L127)).

[V] O scheduler verifica horário a cada 30 s e solicita OFF enquanto observa ligado; não implementa termostato nem prognóstico ([scheduler.py:17](../../web-smart-fan-iot/backend/app/scheduler.py#L17)).

## 5. Frontend atual

| Parte | Comportamento no código | Evidência |
|---|---|---|
| Composição | Aplicação montada diretamente em `App.vue`; sem roteador declarado | [V] [main.ts:1](../../web-smart-fan-iot/frontend/src/main.ts#L1), [package.json:20](../../web-smart-fan-iot/frontend/package.json#L20) |
| Identidade | `?device=ID` ou variável de build; seletor troca contexto da aplicação | [V] [api.ts:4](../../web-smart-fan-iot/frontend/src/lib/api.ts#L4), [App.vue:85](../../web-smart-fan-iot/frontend/src/App.vue#L85) |
| Componentes | Brand, StatusCard, ScheduleCard, TariffCard, MetricCard, PeriodSelector, PowerChart e ThemeToggle | [V] [App.vue:1](../../web-smart-fan-iot/frontend/src/App.vue#L1) e `git ls-files` |
| REST | Axios, timeout 10 s; consulta dispositivo, lista e histórico | [V] [api.ts:11](../../web-smart-fan-iot/frontend/src/lib/api.ts#L11) |
| Tempo real | Valida JSON em runtime, filtra ID, reconecta após 3 s; somente telemetria renova presença | [V] [useWebSocket.ts:21](../../web-smart-fan-iot/frontend/src/composables/useWebSocket.ts#L21) |
| Histórico | Consulta periódica separada do WS; gráfico recebe histórico e não adiciona live automaticamente | [V] [App.vue:373](../../web-smart-fan-iot/frontend/src/App.vue#L373), [App.vue:653](../../web-smart-fan-iot/frontend/src/App.vue#L653) |
| Estados visuais | Há feedback de comando, loading, histórico antigo, persistência incerta e cobertura parcial | [V] [App.vue:641](../../web-smart-fan-iot/frontend/src/App.vue#L641) |
| Acessibilidade | Há `aria-label`, `role=status/alert` em controles e mensagens | [V] [App.vue:400](../../web-smart-fan-iot/frontend/src/App.vue#L400), [App.vue:641](../../web-smart-fan-iot/frontend/src/App.vue#L641) |

[N] Navegação completa por teclado, contraste e leitores de tela não foram avaliados. [V] Não foram encontradas páginas 3D, Mensageria, Lab, Treinamento, Insights, Assistente ou administração no conjunto rastreado; a aplicação lida é um dashboard único. [I] Ausência de login e roteador implica necessidade de planejar navegação e autorização; não exige trocar Vue.

## 6. Núcleo M00 e diferença para o operacional

| Entrega existente | Evidência e limite |
|---|---|
| Envelope tipado | [V] [contracts.py:66](../../packages/smartfan_common/src/smartfan_common/contracts.py#L66): versão, identidade, timestamp e correlação; nomenclatura existente deve ser conciliada com o pedido na etapa 3 |
| Cinco sensores HVAC | [V] [contracts.py:91](../../packages/smartfan_common/src/smartfan_common/contracts.py#L91): corrente, temperatura da carcaça, vibração, temperatura interna e externa |
| Dois atuadores | [V] [contracts.py:104](../../packages/smartfan_common/src/smartfan_common/contracts.py#L104): compressor e ventilador da condensadora |
| Comando, ACK, insight, alertas e jobs | [V] [contracts.py:200](../../packages/smartfan_common/src/smartfan_common/contracts.py#L200); tipos não executam regras nem treinam modelos |
| Features compartilhadas | [V] [features.py:16](../../packages/smartfan_common/src/smartfan_common/features.py#L16): 18 features e versão; janela causal com limites; batch e online compartilham implementação |
| Topologia declarativa | [V] [topology.py:19](../../packages/smartfan_common/src/smartfan_common/topology.py#L19): writer, controle, inferência, gateway, API e jobs; DLQ declarada; não provisiona RabbitMQ |
| JSON Schema e TypeScript | [V] [contracts-v1.ts:1](../../web-smart-fan-iot/frontend/src/lib/contracts-v1.ts#L1): AJV sem coerção; schema e tipos gerados disponíveis |
| Integração atual | [V] Backend operacional importa schemas legados e frontend WS usa `isRealtimeMessage`, não o validador M00 ([mqtt_service.py:15](../../web-smart-fan-iot/backend/app/mqtt_service.py#L15), [useWebSocket.ts:3](../../web-smart-fan-iot/frontend/src/composables/useWebSocket.ts#L3)) |

[I] Reutilizar M00 reduz duplicação de contratos, mas exige uma migração explícita de produtores, armazenamento e consumidores. Não contar filas, sensores ou previsões declarados como requisitos já atendidos em execução.

## 7. Git, documentação, infraestrutura e segredos

### 7.1 Git e documentação

| Consulta | Resultado observado |
|---|---|
| `git status --porcelain=v1` antes da etapa | [V] Vazio; nenhuma alteração pendente |
| `git fetch origin` | [V] Concluído sem erro; branch criada de `origin/main` em `346f7de` |
| `git branch -a` no código-base | [V] `main`, `feature/dashboard-energy-v2`, `backup/pre-review-20261026`; refs remotas main/energia e HEAD |
| `git log -8` | [V] `346f7de` mergeia PR #1 da energia; `b02fadd` implementa M00; `ee5e534` registra plano anterior |
| `git shortlog -sn HEAD` no código-base | [V] 24 commits com identidade `felipematsukuma`, 1 com `Felipe Matsuguma`; identidades distintas não comprovam pessoas distintas |
| `git shortlog -sn --all` antes dos novos commits | [V] 62 e 1 respectivamente, incluindo refs de backup; não confundir com contribuições mergeadas |
| README e documentação | [V] README raiz, aplicação, firmware e pacote; duas revisões históricas rastreadas; [README.md:35](../../README.md#L35) |
| CI, pre-commit, instruções locais | [V] `git ls-files` não encontrou workflows `.github`, configuração pre-commit, gitleaks ou AGENTS.md rastreados |
| Proteção de branch, PRs e equipe | [N] Configuração remota e lista de integrantes não consultadas; não há comprovação de histórico de todos os integrantes |

### 7.2 Configuração e exposição

[V] `.env.example` rastreado contém nomes POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, INFLUXDB_USERNAME, INFLUXDB_PASSWORD, INFLUXDB_ORG, INFLUXDB_BUCKET, INFLUXDB_TOKEN, APP_TIMEZONE, VITE_API_URL, VITE_WS_URL, VITE_DEVICE_ID e CORS_ORIGINS. Valores não são reproduzidos. [V] O ambiente real é carregado por caminho ancorado em [config.py:6](../../web-smart-fan-iot/backend/app/config.py#L6); senha PostgreSQL e token Influx são obrigatórios. [V] [.gitignore:1](../../.gitignore#L1) exclui ambientes, credenciais locais, builds e volumes, permitindo `.env.example`.

[V] Compose publica todas as cinco portas em loopback, não apenas o frontend; PostgreSQL, InfluxDB e backend têm healthchecks; Mosquitto usa `service_started` e frontend não tem healthcheck ([docker-compose.yml:1](../../web-smart-fan-iot/docker-compose.yml#L1)). [V] Backend e frontend não declaram `USER`, usam builds de desenvolvimento e não são multi-stage ([Dockerfile backend:1](../../web-smart-fan-iot/backend/Dockerfile#L1), [Dockerfile frontend:1](../../web-smart-fan-iot/frontend/Dockerfile#L1)). [V] Mosquitto permite acesso anônimo ([mosquitto.conf:3](../../web-smart-fan-iot/mosquitto/config/mosquitto.conf#L3)).

### 7.3 Verificação de segredos sem exposição de valores

| Escopo | Resultado e limite |
|---|---|
| Arquivos atuais rastreados | [V] `git ls-files`: nenhum `.env` real, diretório secrets ou chave `.pem/.key` identificado por nome |
| Histórico de caminhos | [V] `git log --all --name-only`: nenhum caminho de ambiente real/chave identificado pelo mesmo filtro |
| Conteúdo de todas as refs locais | [V] 221 blobs únicos examinados via `git rev-list --objects --all` e `git cat-file`, antes dos commits documentais; heurística inicial sinalizou somente exemplo de credenciais |
| Busca dirigida em configuração histórica | [V] `git show 3786a80:web-smart-fan-iot/backend/app/config.py`: POSTGRES_PASSWORD na linha 6 e INFLUXDB_TOKEN na linha 13 tinham atribuições literais; também presentes em `d0382b0` |
| Correção posterior | [V] `git show fe6d525:.../config.py` e versão atual exigem variáveis de ambiente; a remoção do arquivo atual não remove conteúdo histórico |
| Ferramentas dedicadas | [V] `Get-Command gitleaks,pre-commit` não encontrou executáveis no PATH; não foram instalados nesta etapa |
| Validade das credenciais | [N] Rotação/revogação não foi confirmada em serviços reais; documentação anterior não é evidência operacional atual |

Conclusão: [V] há literais históricos que exigem tratamento como exposição potencial; [N] não há certificação de ausência de outros segredos. A heurística não cobre todos os formatos, inclusive atribuições com anotações de tipo, razão pela qual a inspeção dirigida foi necessária. Não se reescreveu histórico nem se testaram credenciais. Nenhum valor é incluído neste documento.

## 8. Qualidade e evidências de execução

| Verificação | Evidência |
|---|---|
| Testes backend | [V] Executado anteriormente nesta sessão, no mesmo código-base: `.venv/Scripts/python.exe -m pytest -q` no backend; 153 passaram, 1 aviso de depreciação Starlette/httpx |
| Testes M00 | [V] Executado anteriormente nesta sessão: pytest com PYTHONPATH do pacote; 65 passaram |
| Testes frontend | [V] Executado anteriormente nesta sessão: `npm test`; 154 passaram em 7 arquivos |
| Build frontend | [V] Executado anteriormente nesta sessão: `npm run build`; vue-tsc e Vite concluíram com exit code 0 |
| Lint/tipos configurados | [V] Ruff/mypy/pytest em [pyproject.toml:1](../../web-smart-fan-iot/backend/pyproject.toml#L1); lint/typecheck/format em [package.json:6](../../web-smart-fan-iot/frontend/package.json#L6); mypy strict no pacote |
| Lint, cobertura, vulnerabilidades | [N] Não reexecutados nesta etapa; resultados registrados no plano anterior são históricos, não certificação atual |
| Integração e firmware | [N] Sem nova execução Wokwi, Compose, testes de falha ou Playwright nesta etapa |
| Conteúdo dos testes | [V] Arquivos rastreados cobrem API, energia, schemas, scheduler, MQTT, fronteira de I/O, contratos/features e utilitários frontend; `git ls-files` |

Os testes citados verificam partes existentes com suas condições e dublês; não demonstram a cadeia AIoT futura. Não há relatório de cobertura medido nesta análise.

## 9. Classificação de reaproveitamento

Classificações são recomendações de planejamento, não autorização para alterar os itens.

| Parte | Destino proposto | Justificativa e evidência |
|---|---|---|
| FastAPI/Pydantic | Adaptar | [V] REST existe; acrescentar auth, versão, jobs e erros; [main.py:108](../../web-smart-fan-iot/backend/app/main.py#L108) |
| Energia, lacunas e downsample | Reaproveitar | [V] Domínio isolado; validar nova potência/cadência; [energy.py:30](../../web-smart-fan-iot/backend/app/energy.py#L30) |
| Fronteira de I/O | Adaptar | [V] Limita espera, não oferece durabilidade; [io_boundary.py:10](../../web-smart-fan-iot/backend/app/io_boundary.py#L10) |
| MQTT acoplado à API | Substituir no fluxo-alvo | [V] Hoje grava e transmite diretamente; separar gateway e consumidores; [mqtt_service.py:95](../../web-smart-fan-iot/backend/app/mqtt_service.py#L95) |
| Modelo Device e acesso SQL | Adaptar | [V] Reaproveitar identidade; ampliar entidades e migrar schema; [models.py:9](../../web-smart-fan-iot/backend/app/models.py#L9) |
| Schema Influx elétrico | Adaptar | [V] Preservar histórico legado; definir telemetria HVAC separadamente; [mqtt_service.py:101](../../web-smart-fan-iot/backend/app/mqtt_service.py#L101) |
| Scheduler de desligamento | Adaptar | [V] Regra por horário existente; não é termostato; [scheduler.py:17](../../web-smart-fan-iot/backend/app/scheduler.py#L17) |
| Vue e Chart.js | Reaproveitar | [V] Dependências e componentes existentes; [package.json:20](../../web-smart-fan-iot/frontend/package.json#L20) |
| App.vue e composable WS | Adaptar | [V] Dashboard único e mensagens legadas; incluir páginas, papéis e novo contrato; [useWebSocket.ts:30](../../web-smart-fan-iot/frontend/src/composables/useWebSocket.ts#L30) |
| M00: schemas/features/topologia | Reaproveitar com revisão de compatibilidade | [V] Já direcionado a HVAC; resolver nomes/unidades na etapa 3; [contracts.py:91](../../packages/smartfan_common/src/smartfan_common/contracts.py#L91) |
| ESP32, circuito e ferramentas Wokwi | Substituir na execução; preservar como legado | [V] Código Arduino será substituído por simulador Python; não apagar firmware/diagram.json; [platformio.ini:1](../../esp32-simulador/platformio.ini#L1) |
| Compose e Dockerfiles | Adaptar | [V] Cinco serviços de desenvolvimento; faltam serviços e endurecimento; [docker-compose.yml:1](../../web-smart-fan-iot/docker-compose.yml#L1) |
| Configuração anônima MQTT | Descartar na configuração-alvo | [V] Conflita com segurança exigida; preservar arquivo nesta etapa; [mosquitto.conf:3](../../web-smart-fan-iot/mosquitto/config/mosquitto.conf#L3) |
| Testes existentes | Reaproveitar/adaptar | [V] Suítes presentes; ampliar integração sem apagar evidências do legado; `git ls-files` |
| READMEs e revisões | Preservar e atualizar futuramente | [V] Registram domínio original; índice novo diferencia história e proposta; [README.md:35](../../README.md#L35) |

## 10. Premissas e itens não verificados

| Tipo | Registro |
|---|---|
| Decisão do usuário | Toda documentação deve ser consolidada antes da implementação; confirmação entre etapas; merge é do usuário |
| Decisão do usuário | Mesma máquina; ar-condicionado como evolução do problema de desperdício residencial |
| Proposta a detalhar | Compressor automático; ventilador da condensadora controlável com intertravamentos; cinco sensores do M00 |
| [V] Máquina | Consulta CIM: aproximadamente 15,7 GiB RAM; Intel Core i5-12450H, 8 núcleos e 12 processadores lógicos |
| [N] Recursos efetivos | Limites atuais Docker/WSL2, disco disponível, RAM livre e desempenho Ollama/treino não medidos |
| [N] Operação | Bancos/brokers ativos, retenção real, backup/restore, latências e recuperação sem perda não confirmados |
| [N] Segurança | Revogação histórica, scanner dedicado, imagens, permissões remotas e proteção de branch pendentes |
| [N] Equipe | Lista de integrantes e identidade de contribuições não confirmadas; não fabricar autoria |
| [N] Aceitação acadêmica | Continuidade ventilador → ar-condicionado aprovada pelo usuário; aceitação pelo professor não confirmada |

Próxima entrega documental, dependente de aprovação: análise de lacunas dos 20 requisitos, assinaturas de falha, sensores/atuadores e impacto do novo domínio nos dados. Nenhum módulo de implementação será iniciado por esta entrega.
