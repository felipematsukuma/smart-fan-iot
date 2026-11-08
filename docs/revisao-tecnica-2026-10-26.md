# Revisão técnica — smart-fan-iot

Data: 26/10/2026. Branch: `feature/dashboard-energy-v2`. Código analisado: `b34bd43`, após preservação e saneamento autorizados. Este relatório não aplica o plano de ação.

## Parecer

A stack obrigatória está presente. O trecho **Mosquitto → Python → InfluxDB → API** foi executado com três publicações identificadas como revisão. O frontend atual abriu no navegador, consultou a API e renderizou o gráfico vazio. O firmware compilou. A execução integrada **ESP32/Wokwi → dashboard**, incluindo acionamento físico simulado, permanece **não verificada**.

A base pode continuar no segundo bimestre, mas há falhas concretas que impedem considerá-la plenamente validada: estado falso após falha de comando, ingestão MQTT sem validação efetiva, cobertura calculada sobre dados reamostrados e credenciais ativas no histórico. Os testes passam, mas alguns testes consolidam comportamentos incorretos.

## Fase 0 — Preservação

Foram executados `git status --short`, `git branch --show-current` e `git diff --stat` antes de qualquer alteração. A branch esperada foi confirmada. Havia mudanças em backend, frontend, documentação, ignore, testes novos e remoções de componentes/assets antigos.

Você confirmou que as credenciais estavam em uso e autorizou o saneamento. Os valores foram preservados no arquivo local de ambiente ignorado. As senhas/token deixaram de ter defaults no código e no Compose; o exemplo agora contém placeholders. A configuração Python lê o ambiente local por caminho ancorado no projeto, com variáveis de processo tendo precedência.

Commits criados, em ordem:

| Commit | Responsabilidade |
|---|---|
| `fe6d525` | `fix(security): externalize active service credentials` — ignore, configuração, Compose e exemplo de ambiente |
| `b88ea29` | `feat(backend): add energy analysis and synchronize device state` — alterações Python e testes previamente pendentes |
| `ec4d91d` | `feat(dashboard): add energy v2 dashboard and visualization tests` — dashboard, testes e dependências previamente pendentes |
| `b34bd43` | `docs: document simulator and energy dashboard workflows` — documentação previamente pendente e referência de credencial substituída |

Saída final de `git log --oneline -n 15` na Fase 0:

```text
b34bd43 docs: document simulator and energy dashboard workflows
ec4d91d feat(dashboard): add energy v2 dashboard and visualization tests
b88ea29 feat(backend): add energy analysis and synchronize device state
fe6d525 fix(security): externalize active service credentials
3786a80 initial stable baseline
```

A árvore ficou limpa e foi criada `backup/pre-review-20261026`, apontando para `b34bd43`. Nenhum push, rebase, reset ou alteração de histórico foi realizado. A cópia de segurança inclui o saneamento autorizado; o commit inicial continua acessível, com as credenciais antigas. O relatório será versionado em commit posterior, separado da preservação.

O [.gitignore](../.gitignore) agora cobre ambientes virtuais, builds, binários do firmware e diretórios locais de dados. Na conferência final foi corrigido, em commit próprio posterior à Fase 0, o alcance das regras da IDE para subdiretórios do monorepo. Há uma configuração de IntelliSense já rastreada em [c_cpp_properties.json](../esp32-simulador/.vscode/c_cpp_properties.json); ignore não retira arquivos previamente rastreados. Sua remoção do índice foi deixada como proposta. Tarefas, launch e recomendações de extensões podem ser configuração compartilhável; não devem ser removidos indiscriminadamente.

## Fase 1 — Mapeamento somente de leitura

### Árvore comentada, profundidade 3

Inventário dos componentes versionados, omitindo caches, dependências e dados locais:

- [.gitignore](../.gitignore) — exclusões locais e artefatos.
- [esp32-simulador/](../esp32-simulador/) — firmware e simulação.
  - [.vscode/](../esp32-simulador/.vscode/) — tarefas, depuração e extensões.
  - [src/](../esp32-simulador/src/)
    - [main.cpp](../esp32-simulador/src/main.cpp) — Wi-Fi, MQTT, ADC, relé, energia e relógio.
  - [include/](../esp32-simulador/include/), [lib/](../esp32-simulador/lib/), [test/](../esp32-simulador/test/) — scaffolding do PlatformIO; sem suíte útil de firmware.
  - [platformio.ini](../esp32-simulador/platformio.ini), [wokwi.toml](../esp32-simulador/wokwi.toml), [diagram.json](../esp32-simulador/diagram.json) — build e circuito.
  - [README.md](../esp32-simulador/README.md) — execução e diagnóstico.
- [web-smart-fan-iot/](../web-smart-fan-iot/) — aplicação web e serviços.
  - [backend/](../web-smart-fan-iot/backend/)
    - [app/](../web-smart-fan-iot/backend/app/) — API, MQTT, persistência, agendador e energia.
    - [tests/](../web-smart-fan-iot/backend/tests/) — testes com fronteiras de I/O substituídas.
    - [requirements.txt](../web-smart-fan-iot/backend/requirements.txt), [Dockerfile](../web-smart-fan-iot/backend/Dockerfile).
  - [frontend/](../web-smart-fan-iot/frontend/)
    - [src/](../web-smart-fan-iot/frontend/src/) — Vue, componentes, composables, tipos e regras testáveis.
    - [public/](../web-smart-fan-iot/frontend/public/), [.vscode/](../web-smart-fan-iot/frontend/.vscode/).
    - [package.json](../web-smart-fan-iot/frontend/package.json), [package-lock.json](../web-smart-fan-iot/frontend/package-lock.json), [Dockerfile](../web-smart-fan-iot/frontend/Dockerfile), [vite.config.ts](../web-smart-fan-iot/frontend/vite.config.ts), [vitest.config.ts](../web-smart-fan-iot/frontend/vitest.config.ts).
  - [mosquitto/](../web-smart-fan-iot/mosquitto/)
    - [config/](../web-smart-fan-iot/mosquitto/config/) — listener do broker.
  - [docker-compose.yml](../web-smart-fan-iot/docker-compose.yml), [.env.example](../web-smart-fan-iot/.env.example), [README.md](../web-smart-fan-iot/README.md).

Não há README de entrada na raiz nem roadmap explícito do segundo bimestre. A estrutura atual é compreensível; renomear todos os diretórios não é necessário para o aceite.

### Entrypoints e execução

| Componente | Entrypoint e comando | Portas/configuração |
|---|---|---|
| Firmware | [setup/loop](../esp32-simulador/src/main.cpp:276); executar `pio run` dentro do simulador; depois `Wokwi: Start Simulator` na IDE | Wi-Fi `Wokwi-GUEST`, senha vazia; MQTT `host.wokwi.internal:1883`; serial 115200; RFC2217 4000 |
| Backend | [FastAPI app](../web-smart-fan-iot/backend/app/main.py:122); no diretório backend, `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` | REST 8000, `/docs`, `/health`, WS `/ws`; o Docker usa `--reload` |
| Frontend | [main.ts](../web-smart-fan-iot/frontend/src/main.ts), [App.vue](../web-smart-fan-iot/frontend/src/App.vue:1); `npm install`, `npm run dev`; qualidade: `npm run typecheck`, `npm test`, `npm run build` | Vite 5173; `VITE_API_URL`, `VITE_WS_URL`; defaults locais |
| Infra | [Compose](../web-smart-fan-iot/docker-compose.yml:1); no diretório web, configurar o ambiente a partir do exemplo e executar `docker compose up -d --build` | Mosquitto 1883, PostgreSQL 5432, InfluxDB 8086, API 8000, frontend 5173 |

Execução Python fora do Docker requer sobrescrever `POSTGRES_HOST`, `INFLUXDB_URL` e `MQTT_BROKER` para hosts acessíveis localmente; os defaults são nomes de serviços Docker. O ambiente virtual criado nesta revisão fica ignorado no diretório backend.

Variáveis existentes em [Settings](../web-smart-fan-iot/backend/app/config.py:5): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`, `INFLUXDB_URL`, `INFLUXDB_TOKEN`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`, `MQTT_BROKER`, `MQTT_PORT`, `APP_TIMEZONE`. Inicialização Influx acrescenta `INFLUXDB_USERNAME` e `INFLUXDB_PASSWORD` no Compose. O [.env.example](../web-smart-fan-iot/.env.example) ainda não enumera todos os overrides para desenvolvimento fora do Docker. As URLs Vue estão fixadas no Compose, portanto mudar somente o exemplo/ambiente externo não parametriza esse bloco.

### Dependências declaradas

- [Python](../web-smart-fan-iot/backend/requirements.txt): FastAPI `>=0.110.0`, uvicorn `>=0.28.0`, SQLAlchemy `>=2.0.28,<2.1`, psycopg2-binary `>=2.9.9`, Pydantic `>=2.6.4`, pydantic-settings `>=2.2.1`, influxdb-client `>=1.41.0`, paho-mqtt `<2.0.0`, APScheduler `>=3.10.4`, python-dotenv `>=1.0.1`, pytest `>=8`, httpx `>=0.27`. Sem lock Python e sem separação de dependências de teste.
- [Frontend](../web-smart-fan-iot/frontend/package.json): Vue `^3.5.42`, Chart.js `^4.5.1`, vue-chartjs `^5.3.4`, axios `^1.20.0`, lucide-vue-next `^1.0.0`; TypeScript `~6.0.2`, Vite `^8.3.0`, plugin Vue `^6.0.8`, vue-tsc `^3.3.11`, Vitest/coverage `^2.1.9`, tipos Node `^24.13.3`, tsconfig Vue `^0.9.1`. Há lock npm.
- [PlatformIO](../esp32-simulador/platformio.ini:1): `espressif32@6.12.0`, board `esp32dev`, ArduinoJson `^6.21.3`, PubSubClient `^2.8`. Preferences/WiFi vêm do framework. [Wokwi](../esp32-simulador/wokwi.toml:1) aponta para os artefatos dessa mesma configuração. O [diagrama](../esp32-simulador/diagram.json:4) contém ESP32, relé, LED, resistor e potenciômetro.
- [Imagens](../web-smart-fan-iot/docker-compose.yml:1): `eclipse-mosquitto:2.0`, `postgres:15-alpine`, `influxdb:2.7-alpine`; bases `python:3.11-slim` e `node:20-alpine`. São tags explícitas, mas mutáveis, sem patch/digest fixo.

Node é usado para tooling e servidor de desenvolvimento do frontend. O backend continua integralmente Python.

### Contrato MQTT atual

Todos os payloads são JSON. Prefixo efetivo: `devices/{device_id}`, já hierárquico; não há necessidade de trocar por `smartfan` apenas por estética.

| Sufixo | Direção | Payload | QoS/retain efetivos |
|---|---|---|---|
| `/telemetry` | ESP32 → backend | `device_id`, `is_on`, `auto_mode`, `shutdown_time`, `voltage_rms` [V], `current_a` [A], `power_w` [W], `total_energy_wh` [Wh], `fan_on_time_ms` [ms], `timestamp` [ms desde boot] | Firmware publica QoS 0, sem retain; backend assina QoS 1, o que não eleva a garantia da origem |
| `/command` | Backend → ESP32 | API emite `action: ON/OFF`, `speed: 1..3` por default; firmware também aceita `AUTO/MANUAL`, `is_on`, `auto_mode`, `shutdown_time` | Backend QoS 1, sem retain; subscribe do firmware usa default QoS 0; `speed` é ignorado pelo firmware |
| `/config/set` | Backend → ESP32 | `auto_mode` boolean e `shutdown_time` `HH:MM` | Backend QoS 1, retained; subscribe firmware QoS 0 |
| `/state` | ESP32 → backend | Identidade, `is_on`, configuração, tempo ligado e energia acumulada | QoS 0, retained |
| `/config` | ESP32 → backend | Identidade, `auto_mode`, `shutdown_time` | QoS 0, retained |

Evidências: [constantes do firmware](../esp32-simulador/src/main.cpp:19), [publicação de telemetria](../esp32-simulador/src/main.cpp:323), [assinaturas Python](../web-smart-fan-iot/backend/app/mqtt_service.py:39), [publicações Python](../web-smart-fan-iot/backend/app/mqtt_service.py:204).

Não há versão do contrato, sequência de amostra, identificador de boot, ACK de aplicação correlacionado a comando nem LWT de presença. `timestamp` do firmware não é epoch UTC. A documentação chama a telemetria de QoS 1, mas o código publica QoS 0: [README](../web-smart-fan-iot/README.md:18).

### Schema InfluxDB e PostgreSQL

O [writer](../web-smart-fan-iot/backend/app/mqtt_service.py:85) usa bucket configurável, default `telemetry`, org default `iot_org`, measurement `electrical_measurement`, tag `device_id`; fields `is_on` como inteiro, `current_a`, `power_w`, `voltage_rms` como floats. Não grava `total_energy_wh`, `fan_on_time_ms`, configuração ou uptime. Não chama `Point.time`: o timestamp armazenado é atribuído pelo servidor na recepção. Isso evita interpretar uptime como epoch, mas não preserva o instante de medição nem atrasos do dispositivo.

Consulta real à API de buckets retornou `retentionRules: [{type: expire, everySeconds: 0, shardGroupDurationSeconds: 604800}]`: retenção sem expiração no bucket atual. O Compose não declara uma política explícita de retenção.

Há também PostgreSQL, além da stack mínima: [Device](../web-smart-fan-iot/backend/app/models.py:4) contém `id`, `device_id` único, `name`, `is_on`, `kwh_rate`, `auto_off_time`, `auto_off_enabled`. Sua função é configuração/estado, não substituir o InfluxDB. O banco é hoje dependência obrigatória do startup e dos comandos; não foi introduzido nesta revisão.

### API atual

| Método/rota | Entrada | Resposta e comportamento |
|---|---|---|
| `GET /health` | Nenhuma | `status`, `mqtt_connected`; não verifica disponibilidade de bancos |
| `GET /api/device/{device_id}` | ID validado por regex | Objeto Device; 404 se não cadastrado |
| `POST /api/device/{device_id}/command` | `action: ON/OFF` normalizado, `speed: 1..3` | `status: published`, identidade e comando; 503 se publicação não confirmada pelo broker; não confirma execução no relé |
| `PUT /api/device/{device_id}/schedule` | `auto_off_time`, `auto_off_enabled`, `kwh_rate >=0` | `status: updated`, configuração publicada; altera configuração e tarifa |
| `PUT /api/device/{device_id}/auto-shutdown` | Hora e boolean | Atualiza somente desligamento e publica configuração |
| `PUT /api/device/{device_id}/tariff` | `kwh_rate >=0` | Persiste tarifa e retorna valor |
| `GET /api/device/{device_id}/metrics` | `range_hours` 1..168, default 8; alternativamente `start` e `end` datetime, juntos, início anterior ao fim, duração até 168 h | `device_id`, período, duração, média, Wh, kWh estimado, contagem bruta e histórico `{time,power_w}` reduzido a até 240 pontos |
| `WS /ws` | Conexão sem autenticação; recebe texto para manter handler | Eventos `telemetry`, `state`, `config`, enviados a todos os clientes; filtragem por dispositivo ocorre no frontend |

Evidências: [rotas REST](../web-smart-fan-iot/backend/app/main.py:133), [metrics](../web-smart-fan-iot/backend/app/main.py:265), [schemas](../web-smart-fan-iot/backend/app/schemas.py:7), [WebSocket](../web-smart-fan-iot/backend/app/main.py:344). O FastAPI também fornece OpenAPI e Swagger. Não há filtro de agregação configurável, paginação/limite de leitura bruta, response models explícitos nem CRUD/listagem de dispositivos. Metrics não exige dispositivo cadastrado, ao contrário das rotas de comando/configuração.

## Fase 2 — Validação do fluxo

### Execuções e evidências

| Verificação | Resultado observado |
|---|---|
| `pio run` | SUCCESS, 67,95 s; RAM 45.404/327.680 bytes; flash 784.837/1.310.720 bytes |
| Coerência de build | Arquivos gerados nos caminhos referenciados pelo Wokwi; GPIO34 ligado ao potenciômetro e GPIO23 ao relé |
| `docker compose config --quiet` | Passou com o ambiente local saneado |
| `docker compose up -d --build` | Falhou ao obter token anônimo de `auth.docker.io`: conexão fechada pelo remoto; build limpo não comprovado |
| Serviços existentes | Após iniciar Docker Desktop, os cinco containers previamente existentes ficaram ativos; serviços de dados confirmados por `compose up -d mosquitto postgres influxdb` |
| Identidade do backend | SHA-256 de `main`, MQTT e configuração dentro do container igual ao código local; backend usa bind mount atual |
| Python local, isolado | `140 passed`, 1 warning de depreciação TestClient/httpx; Python 3.14 |
| Python do container | `140 passed`, mesmo warning; Python 3.11.16 |
| `npm run typecheck` | Passou; `tsc --showConfig` confirmou `strict: true` herdado |
| `npm test` | 6 arquivos, 102 testes passaram |
| `npm run build` | Passou; bundle JS ~318,95 kB, gzip ~115,16 kB |
| Browser do frontend atual | Servidor temporário na porta 5174; página Ventora abriu, consulta à API retornou 200, um canvas renderizado; estado vazio exibido |
| GitHub | `git ls-remote --heads origin feature/dashboard-energy-v2 main` encontrou ambas em `3786a80`; novos commits permanecem locais |

O container frontend existente não tem bind mount e contém imagem anterior. Sua simples execução em 5173 não comprova o dashboard atual. Por isso foi validado o código atual em 5174, com Node local 24.21.0. O Node do container é 20.20.2, compatível com o engine declarado pelo Vite instalado (`^20.19.0 || >=22.12.0`); não há evidência de incompatibilidade de engine.

Teste real de integração, sem comandos ao ventilador cadastrado:

```text
device_id exclusivo: review_probe_20261026
mosquitto_pub: 3 publicações QoS 1, exit 0
WebSocket: 3 eventos telemetry, power_w=29.72
InfluxDB: count(power_w)=3
API metrics: HTTP 200, history_count=3, avg_power_w=29.72
energy_wh=0.036, estimated_kwh=0.000036
tempos armazenados: 2026-10-26T13:06:43.554207Z até 13:06:47.940195Z
```

As três amostras permanecem no InfluxDB sob o ID de revisão, distinguíveis do dispositivo real. Nenhum registro de configuração foi criado para esse ID, nenhum comando foi enviado ao ventilador existente e nenhum volume foi apagado. As amostras confirmam integração de potência com tempo de recepção, não uma medição elétrica calibrada.

### Status por elo

1. **ESP32/Wokwi — PARCIAL.** Compilação e arquivos coerentes; Wi-Fi público do simulador e host do gateway privado configurados. Comandos de volta implementados. O sensor é um potenciômetro que representa corrente, não sensor elétrico calibrado. Não há tratamento de falha de ADC; abaixo de 0,05 A o firmware substitui a leitura por 0,28 A, mascarando zero/baixo consumo. Reconexão MQTT é bloqueante e pode impedir o desligamento local quando o broker cai; recuperação Wi-Fi não é gerenciada explicitamente no loop. Execução na IDE/gateway e comutação do relé: **não verificadas**. [Firmware](../esp32-simulador/src/main.cpp:258).
2. **MQTT/Mosquitto — PARCIAL.** Broker ativo e publicação real confirmada; tópicos hierárquicos coerentes. Sem autenticação/TLS/ACL e exposto em todas as interfaces do host. QoS da telemetria efetiva é 0; comandos não retained e configuração retained são escolhas adequadas, mas sem ACK de aplicação. Volumes existem, porém [configuração](../web-smart-fan-iot/mosquitto/config/mosquitto.conf:1) não ativa persistência explícita de mensagens retidas.
3. **Backend Python — PARCIAL.** Reconexão Paho com backoff 1–5 s, resubscribe e tratamento de exceções presentes; escrita real comprovada. Falta validação efetiva de telemetria e de estado/configuração. Erros de Influx não derrubam o callback, mas descartam o ponto e ainda enviam o evento WS, sem retry/fila. [Subscriber](../web-smart-fan-iot/backend/app/mqtt_service.py:57).
4. **InfluxDB — OK para o caminho básico.** Token, bucket e org configuráveis; três pontos consultados diretamente. Retenção atual sem expiração; falta política explícita, retry e indicação de perdas. [Cliente](../web-smart-fan-iot/backend/app/database.py:19).
5. **API de histórico — PARCIAL.** Consulta real 200, filtros de período e redução para 240 pontos. ID inválido, intervalo de 169 h e período com apenas início retornaram 422. CORS permite consumo pelo browser, mas é irrestrito. Faltam agregação/limite bruto configuráveis e resposta controlada para indisponibilidade do Influx. [Metrics](../web-smart-fan-iot/backend/app/main.py:265).
6. **Dashboard Vue — PARCIAL.** Vue 3, Composition API, script setup TS, Vite, Chart.js, strict, build e testes confirmados. Há indicador atual, histórico, mensagens de erro, salvamento e estado vazio. Falta loading específico para consultas e indicação de dados antigos; requisições concorrentes podem sobrescrever período mais recente com resposta antiga. Browser verificado no estado sem telemetria do ESP32. [App](../web-smart-fan-iot/frontend/src/App.vue:147).
7. **Energy v2 — PARCIAL.** Integração no backend é uma boa separação; fórmulas dimensionais corretas. Cobertura/gráfico e projeção precisam correção antes de serem apresentados como informação confiável sobre a janela inteira. Evidências abaixo.

### Energia, unidades e consistência

O [firmware](../esp32-simulador/src/main.cpp:323) estima `I = ADC/4095 × 0,8 A`, `P = I × 127 V × 0,90`. O fator de potência e a tensão são assumidos; os rótulos de corrente eficaz/potência ativa devem deixar claro que se trata de simulação. Potência real exigiria sensor/calibração apropriados.

O [domínio Python](../web-smart-fan-iot/backend/app/energy.py:29) integra `Wh = Σ((P₁+P₂)/2 × Δt_s/3600)` entre amostras separadas por até 80 s, e `kWh = Wh/1000`. Correto para essa aproximação. Não extrapola as bordas nem os intervalos maiores. A média retornada é aritmética por amostra, não média ponderada no tempo. Uptime/energia acumulada do ESP32 não são a fonte dessa conta.

O [frontend](../web-smart-fan-iot/frontend/src/App.vue:103) calcula custo `kWh × tarifa`; a [projeção mensal](../web-smart-fan-iot/frontend/src/lib/format.ts:51) multiplica pela razão `720 h / duração da janela`. As unidades estão corretas, mas ausência de cobertura é implicitamente tratada como ausência de consumo, podendo subestimar a projeção. A tarifa atual é aplicada retrospectivamente, sem vigência histórica. Para a primeira etapa, basta rotular a estimativa e mostrar cobertura real; para múltiplos clientes/relatórios, centralizar custo/projeção no backend com a política de tarifa definida.

**Reprodução de erro de cobertura:** 14.401 amostras de 30 W a cada 2 s por 8 h → integração Python de 240 Wh → 240 pontos no histórico → função TypeScript `computeCoverage` retorna **0** porque todos os intervalos reamostrados excedem 90 s. [Redução](../web-smart-fan-iot/backend/app/energy.py:182), [cálculo UI](../web-smart-fan-iot/frontend/src/lib/chartRules.ts:553), [uso no componente](../web-smart-fan-iot/frontend/src/components/dashboard/PowerChart.vue:209). Cobertura deve vir dos dados brutos no backend; os metadados de descarte já existem parcialmente em `EnergyResult`, mas não são expostos na API.

**Reprodução de inferência indevida:** `buildTimeline([t,t+1h],[0,0])` retorna `offMs=3600000`, `noDataMs=0`. Duas leituras zero não provam ausência de consumo entre elas: pode haver comandos, falha de publicação ou reconexão. A [regra](../web-smart-fan-iot/frontend/src/lib/chartRules.ts:334) prioriza zero nas pontas antes da lacuna, enquanto o domínio Python quebra regiões em lacunas. Além disso, a linha atravessa trechos sem dados; a explicação de interpolação fica sobretudo em tooltip. Preservar gaps identificados no backend evita reconstruir continuidade a partir da série reduzida.

Estatísticas média/máxima do gráfico também usam a série reduzida, que pode descartar picos e comprime regiões desligadas. Podem divergir das estatísticas dos dados brutos. Não integrar energia sobre essa série é uma decisão correta já existente.

### Query de verificação

Flux executado com o token obtido do ambiente local, sem imprimi-lo:

```flux
from(bucket: "telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "electrical_measurement")
  |> filter(fn: (r) => r.device_id == "review_probe_20261026")
  |> filter(fn: (r) => r._field == "power_w")
  |> count()
```

Retornou 3 no momento da revisão. Para repetir posteriormente, usar intervalo absoluto envolvendo os timestamps registrados; `-1h` deixará de incluir essas amostras. Não copiar tokens para comandos ou documentação. O editor Data Explorer do Influx pode executar essa query com a sessão autenticada.

### Validação manual ainda necessária no Wokwi

1. Subir os serviços e abrir o projeto do simulador na IDE; compilar antes de iniciar.
2. Executar `Wokwi: Start Simulator`, conferir conexão a `Wokwi-GUEST`, sincronização NTP e conexão MQTT no serial. Confirmar que o gateway privado está ativo e alcança `host.wokwi.internal:1883`.
3. Manter a simulação executando e acompanhar `devices/esp32_fan_01/telemetry` com `mosquitto_sub`. Verificar leituras de dois em dois segundos simulados e timestamps de recepção no Influx.
4. Abrir o dashboard atual, aguardar presença, acionar ON/OFF e observar relé/LED, mensagem state, telemetria, API e gráfico. Mover o potenciômetro com o relé ligado e observar potência/corrente.
5. Salvar um horário próximo e conferir o desligamento. Depois repetir com broker indisponível e restabelecido: o loop bloqueante identificado pode impedir a proteção local. Não usar esse comportamento como controle confiável de hardware real.
6. Testar pausa/reinício do simulador, reconexão e interrupção de Influx. Conferir distinção entre offline, desligado e ausência de histórico.

O [guia oficial Wokwi para VS Code](https://docs.wokwi.com/vscode/project-config) confirma caminhos de firmware e gateway privado incluído na extensão. O [guia de rede](https://docs.wokwi.com/guides/esp32-wifi) explica o hostname para acessar a máquina local. A existência desses arquivos não comprova a sessão do simulador.

### Checklist de aceite — 13 requisitos

| # | Requisito | Status | Evidência/limite |
|---|---|---|---|
| 1 | Problema real claramente definido | PARCIAL | Monitoramento, custo e desligamento presentes; falta explicitar público, desperdício a reduzir e critério de sucesso no [README](../web-smart-fan-iot/README.md:3) |
| 2 | Interface Vue 3 | OK | [App](../web-smart-fan-iot/frontend/src/App.vue:1), browser e build |
| 3 | TypeScript | OK | Typecheck passou e [tipos](../web-smart-fan-iot/frontend/src/types/index.ts:1) |
| 4 | Vite | OK | [Configuração](../web-smart-fan-iot/frontend/vite.config.ts), build passou |
| 5 | Pelo menos um sensor IoT | PARCIAL | Potenciômetro/ADC em [diagrama](../esp32-simulador/diagram.json:15); representa corrente. Não há sensor elétrico dedicado; confirmar se o critério acadêmico aceita entrada analógica simulada |
| 6 | Dispositivo simulado no Wokwi | PARCIAL | [Configuração](../esp32-simulador/wokwi.toml:1), diagrama e firmware compilado; execução da sessão não verificada |
| 7 | MQTT | OK | Subscriber real, publicações e eventos confirmados |
| 8 | Mosquitto | OK | Container ativo e `mosquitto_pub` executado dentro dele |
| 9 | Backend Python | OK | FastAPI, Python 3.11 do container, 140 testes |
| 10 | Leituras no InfluxDB | OK | Três leituras de teste gravadas e consultadas; origem Wokwi ainda pendente |
| 11 | Histórico consultável | OK | Endpoint retornou 3 registros e métricas |
| 12 | Gráfico/indicador | OK | Chart.js e indicadores renderizados; qualidade da cobertura tem falha identificada |
| 13 | GitHub | OK para baseline; PARCIAL para entrega atual | Remote [repositório](https://github.com/felipematsukuma/smart-fan-iot), branches remotas em `3786a80`; commits atuais não enviados conforme instrução |

Não há aceite integral ponta a ponta até concluir a sessão Wokwi e resolver/aceitar as limitações relevantes.

## Fase 3 — Arquitetura e estrutura

| Tema | Avaliação concreta | Recomendação mínima |
|---|---|---|
| Responsabilidades | Energia isolada em módulo puro; API orquestra consulta; MQTT mistura parsing, persistência, estado e broadcast | Manter monólito Python; extrair primeiro validação e regras de estado para funções pequenas, sem framework novo |
| Estado e comando | [Scheduler](../web-smart-fan-iot/backend/app/scheduler.py:45) grava OFF mesmo quando envio falha; broker ACK não é ACK do relé | Separar comando desejado de estado observado; atualizar estado somente por confirmação/telemetria; retry limitado para comando pendente |
| Persistência e UI | [Writer](../web-smart-fan-iot/backend/app/mqtt_service.py:100) transmite live mesmo quando write falha; comentário do [database](../web-smart-fan-iot/backend/app/database.py:25) sugere garantia maior | Documentar semântica e expor falha de persistência; retry limitado/pequena fila quando necessário, sem introduzir outro serviço |
| Configuração | Segredos saneados; hosts Python configuráveis; identidade/tópicos/tensão/fator de potência firmware fixos; ID único na UI | Expor configuração de compilação para firmware e seleção/configuração de dispositivo no frontend; manter defaults dev documentados |
| Contratos | Schema MQTT existe, mas não é aplicado; REST sem response models; tipos TS manuais | Validar entrada real, completar schemas, documentar unidades/tempo, adicionar um teste de contrato. Geração de cliente é opcional |
| Múltiplos dispositivos | Tag Influx, chave única e wildcard MQTT já ajudam; API/UI/default seed presos a um ID; telemetria de ID não cadastrado é aceita mas comandos exigem cadastro | Cadastro/listagem simples e autorização por ID quando necessário; não adicionar multitenancy completo agora |
| Novos sensores | Measurement/fields elétricos fixos e payload sem versão | Evoluir schema de forma explícita, com campos opcionais/versionamento quando surgir novo sensor; não criar barramento genérico antecipadamente |
| Alertas/autenticação | Não implementados; scheduler já oferece local simples para regra inicial | Adiar alertas complexos; preparar estado confiável e limites de acesso antes de expor externamente |
| Reprodutibilidade | Compose único e volumes; build limpo bloqueado por rede; sem healthchecks, dependências Python flutuantes, `create_all` no import | Healthchecks, startup tolerante a readiness, lock/constraints, `npm ci`, exclusões de contexto Docker |
| Estrutura | Dois diretórios funcionais, infra sob web; scaffolding residual e README frontend padrão | README raiz com links e roadmap; manter pastas atuais até haver benefício concreto em movê-las |
| PostgreSQL | Guarda configurações e estado, mas acrescenta operação além da stack mínima | Manter enquanto atende persistência atual; documentar a função. Reavaliar simplificação somente com requisito de persistência definido e migração aprovada |

Não proponho microserviços, CQRS, event bus adicional, repository genérico, outro banco ou substituição de tecnologias. O maior ganho está em corrigir contratos, estado e metadados da série existente.

### Resiliência

- O backend reconecta ao MQTT e refaz subscriptions; configuração é republicada a partir do PostgreSQL. O MQTT usa clean session: não fornece armazenamento durável de mensagens perdidas durante desconexão.
- Escrita Influx síncrona acontece no callback de rede MQTT. Lentidão do banco bloqueia processamento MQTT e pode afetar keepalive; não há retry de aplicação ou backpressure explícitos. A entrega WS continua mesmo após falha de escrita.
- [create_all](../web-smart-fan-iot/backend/app/main.py:71) roda no import. PostgreSQL indisponível impede até subir a API; `depends_on` não garante readiness. A política restart ajuda reinícios, mas não substitui readiness/healthcheck.
- O [reconnect do firmware](../esp32-simulador/src/main.cpp:258) entra em laço com `delay(3000)` até conectar. Nesse período não roda a verificação local de horário. Inicialização Wi-Fi e NTP também bloqueiam; o loop MQTT não tem recuperação Wi-Fi independente.
- O prazo de publicação Python é 2 s; o frontend espera confirmação por estado por 10 s. Não há correlação, logo uma mudança externa coincidente pode parecer confirmação do comando.
- O cliente Influx não tem timeout/retry definidos no projeto nem fechamento explícito no shutdown. Defaults da biblioteca não constituem política documentada de recuperação.
- Evitar múltiplos workers do backend neste desenho: cada processo teria subscriber e scheduler próprios, com risco de duplicar ingestão/agendamento. Um worker é suficiente para esta etapa.

## Fase 4 — Segurança

### Credenciais e histórico

Senhas de serviços e token Influx estavam em arquivos rastreados e no commit inicial `3786a80`, que também está no GitHub. Isso foi confirmado por busca em todas as refs e comparação mascarada com os valores ativos; a busca por padrões também contém falsos positivos e não é garantia de ausência de todo segredo possível. Não foram impressos novamente valores durante o saneamento.

Os arquivos atuais foram saneados com sua autorização, mas **a rotação não foi executada**. É necessário gerar novo token com permissões mínimas, atualizar backend, verificar ingestão, revogar o anterior, trocar senhas PostgreSQL/Influx e atualizar o ambiente local. Alterar variáveis de inicialização do Compose não troca credenciais em volumes já inicializados. Fazer isso pelos mecanismos dos serviços, preservando os dados; não usar remoção de volumes como procedimento de rotação.

A limpeza de histórico pode ser planejada depois da rotação, caso necessária, e exige coordenação específica. Não foi reescrito o histórico nem feito force push. A branch de backup também mantém os commits antigos, como esperado.

### Superfícies de acesso

- [Mosquitto](../web-smart-fan-iot/mosquitto/config/mosquitto.conf:1): `allow_anonymous true`, sem TLS/ACL. Qualquer cliente com acesso ao broker pode ler telemetria, falsificar estado e publicar comandos/configuração. É tolerável apenas em ambiente de desenvolvimento isolado; o Compose publica a porta em todas as interfaces, não só loopback. Evoluir para bind local no dev, credenciais e ACL por dispositivo; TLS antes de tráfego em rede não confiável.
- [API/CORS](../web-smart-fan-iot/backend/app/main.py:124): origens, métodos e headers `*`; não há autenticação REST nem WS. CORS não protege MQTT e não substitui autorização. Restringir origens do frontend e acesso à rede; autenticação antes de exposição externa.
- WS transmite todos os dispositivos para todos os clientes; filtro da UI não é controle de acesso. Para múltiplos usuários, filtrar/autorização no servidor.
- Firmware usa credenciais padrão públicas do Wokwi, sem segredo de rede real identificado. O MQTT usa cliente não TLS, sem usuário/senha. Provisionamento de hardware real precisará ser separado da simulação.

### Validação e query

O ID da API é restringido por regex; datas são parseadas e reserializadas, intervalo é limitado. As tentativas realizadas retornaram 422. Não foi demonstrada injeção Flux pelos parâmetros públicos atuais. O bucket vem de configuração administrativa e é interpolado; parametrização/escape evita erro com nomes especiais, mas não deve ser apresentado como exploração pública comprovada.

A falha mais direta é MQTT: [TelemetryPayload](../web-smart-fan-iot/backend/app/schemas.py:46) não é usado. Reprodução em memória passou `is_on: "false"`, `power_w: -12.5`, `current_a: -0.1`; o writer aceitou `is_on=1`, potência e corrente negativas. Validar tipos, booleanos, finitude, faixas, identidade, tamanho e campos antes da persistência/broadcast. Mensagens state/config também precisam validação de hora/boolean; hoje `bool("false")` é verdadeiro.

O parser [parseShutdownTime](../esp32-simulador/src/main.cpp:63) usa `toInt` sem garantir dígitos; entradas como `ab:cd` podem ser interpretadas como `00:00`. A API rejeita esse formato, mas publicação MQTT direta contorna a API. `speed` é aceito pela API e ignorado pelo atuador: remover ou implementar somente com aprovação de contrato.

### Dependências auditadas

- `npm audit`: **9 pacotes**, 3 moderate, 3 high, 3 critical. Os críticos envolvem Vitest, coverage e Tinypool; há Vite e dependências transitivas afetadas. Não significa nove explorações comprovadas no browser. O [advisory do mantenedor Vitest](https://github.com/vitest-dev/vitest/security/advisories/GHSA-5xrq-8626-4rwp) condiciona um dos problemas ao servidor UI escutando; os testes desta revisão usaram `vitest run`.
- `npm audit --omit=dev`: **2 high**, `follow-redirects@1.16.0` e `source-map-js` até 1.2.1. Avaliar caminho/condições de uso; não presumir exploração do adaptador browser do Axios. Atualização do lock e ferramentas requer teste de compatibilidade; não foi usado `audit fix --force`.
- `pip-audit` no ambiente novo: duas entradas duplicadas para a mesma vulnerabilidade de `pip@26.1.2` (`GHSA-qwm4-qh6w-59xr`), sem achados nas bibliotecas da aplicação recém-resolvidas. Isso não descreve a imagem antiga.
- Auditoria separada das 39 versões da aplicação instaladas no container: um achado em `certifi@2026.7.22`, `GHSA-6q48-6c7w-9gw2`. O [advisory](https://github.com/advisories/GHSA-6q48-6c7w-9gw2) indica correção em 2026.10.19 ou posterior. A auditoria por freeze não incluiu o pip do container; não é auditoria da imagem/OS inteira.
- Não foi executado scanner de CVEs de imagens Docker/OS. Tags explícitas existem, mas não são imutáveis. As bases rodam como root por default e os Dockerfiles são voltados a desenvolvimento (`--reload`/Vite dev).

## Fase 5 — Clean code e qualidade

### Python

Há logging, anotações parciais, módulo de energia puro e docstrings de regras. Não foi encontrado `except:` vazio nos módulos revisados; existem capturas amplas de `Exception` nas fronteiras MQTT/banco/WS. Algumas são apropriadas para manter o serviço, mas devem diferenciar validação, transporte e persistência e expor observabilidade.

`ruff check app tests` sem configuração retornou 5 problemas: três imports não usados e duas redefinições de testes em [test_scheduler.py](../web-smart-fan-iot/backend/tests/test_scheduler.py:166). `ruff format --check` indicou 13 arquivos fora do formato padrão. Nenhuma formatação foi aplicada.

`mypy app --ignore-missing-imports --python-executable .venv/Scripts/python.exe` retornou 16 erros, principalmente tipagem ORM `Column` e construção de Settings por ambiente. Os dois alertas de argumentos obrigatórios de Settings após o saneamento exigem configuração/plugin Pydantic; o runtime e os testes carregaram as variáveis corretamente. Não classificá-los como falha de inicialização comprovada. Há corpos sem anotação que o mypy padrão não verifica.

Recomendação mínima: configurar Ruff lint/format e mypy gradualmente, usar os tipos ORM adequados quando tocar nos modelos e remover criação de tabelas do import quando corrigir startup. Instâncias globais mutáveis de MQTT, scheduler e clientes de banco hoje exigem monkeypatch de módulos nos testes; injetar as fronteiras necessárias sem criar camadas genéricas.

### TypeScript/Vue

Strict e checagem de tipos passam; componentes visuais e funções puras já estão separados. A [camada REST](../web-smart-fan-iot/frontend/src/App.vue:147) ainda vive no componente raiz com axios sem genéricos de resposta. O [WS](../web-smart-fan-iot/frontend/src/composables/useWebSocket.ts:29) faz parse e merge de JSON sem validação runtime. Types TS não tornam um payload externo seguro.

Faltam ESLint/Prettier e scripts de lint. Extrair um cliente API/composable pequeno com resposta tipada, timeout, cancelamento/controle de ordem e loading/erro/dados antigos. O flag de comando pendente em [App](../web-smart-fan-iot/frontend/src/App.vue:72) é um `let` comum passado ao template; deve ser reativo para atualizar o botão de forma confiável. Proteger somente a função contra reentrada não garante feedback visual.

O componente de gráfico tem 722 linhas e [chartRules](../web-smart-fan-iot/frontend/src/lib/chartRules.ts) tem 590, com comentários contraditórios sobre gaps, zeros e linha contínua. Há complexidade de eixo comprimido, histerese e estatística superior ao mínimo de um gráfico histórico. Preservar a experiência necessária, mas corrigir primeiro a semântica de tempo/cobertura; não acrescentar outra biblioteca de gráficos.

### Firmware

Existem constantes de pinos/tópicos e funções separadas, mas tudo reside no mesmo arquivo. O loop de telemetria usa `millis`, o que é adequado. Reconexão MQTT, inicialização Wi-Fi e NTP bloqueiam. Substituir primeiro esses caminhos por tentativas temporizadas para manter a proteção local ativa.

Valores 127 V, fator 0,90, escala 0,8 A, limiar 0,05 A e fallback 0,28 A precisam nomes e explicação da simulação. Não há detecção/calibração de sensor. A energia local usa potência da última amostra vezes todo o intervalo; uma transição ON no meio do intervalo pode contabilizar tempo anterior ao acionamento, e OFF pode perder o final do trecho. Ela diverge por desenho da integração histórica do servidor. Não usá-las como duas fontes equivalentes de faturamento.

O buffer JSON de 512 bytes não aumenta o pacote MQTT. PubSubClient 2.8 instalado usa buffer default de 256 bytes; `publish` retorna false se tópico+payload+overhead excederem esse valor. O firmware ignora esse retorno. Um payload representativo mediu 197 bytes, exigindo 234 com tópico/overhead e cabendo; portanto não foi demonstrada falha atual por tamanho. Há pouca margem para contadores maiores ou novos campos. Ajustar buffer explicitamente e verificar retorno ao evoluir o payload. [API oficial](https://pubsubclient.knolleary.net/api) e código instalado foram consultados.

Contadores `unsigned long` de tempo ligado e uptime têm rollover e reinício; `timestamp` não é um relógio civil. Para o segundo bimestre, distinguir uptime/boot de timestamp UTC, mantendo o tempo de recepção no servidor.

### Testes e documentação

Há testes úteis de energia, validação REST, MQTT, estado e regras frontend. As fronteiras externas são substituídas em [conftest](../web-smart-fan-iot/backend/tests/conftest.py:1); a integração real de três pontos complementou essa suíte, mas não cobriu falha de serviços/reconexão do dispositivo.

Problemas concretos da suíte:

- [Teste do broker offline](../web-smart-fan-iot/backend/tests/test_scheduler.py:149) exige marcar OFF mesmo sem publicar. Deve passar a proteger estado observado, junto da mudança de comportamento aprovada.
- Dois nomes de testes são redefinidos e as versões anteriores deixam de ser coletadas.
- [Teste de tolerância firmware](../web-smart-fan-iot/backend/tests/test_scheduler.py:118) apenas verifica constante local positiva; não testa firmware.
- [dbg2.test.ts](../web-smart-fan-iot/frontend/src/lib/dbg2.test.ts:1) só imprime informações, sem assertion.
- Não há teste útil do firmware nem teste integrado que passe o histórico reduzido do backend para a cobertura frontend.

Mínimo útil proposto: regressões para publicação falha sem falsificar estado, payload MQTT inválido rejeitado, cobertura densa após downsample, lacuna entre zeros como desconhecida e reconexão sem bloquear proteção local. Aproveitar as suítes existentes; não criar uma matriz extensa de mocks que apenas espelhe a implementação.

Os READMEs explicam execução, portas, tópicos e fórmulas, mas o [README web](../web-smart-fan-iot/README.md:315) menciona 134/66 testes, enquanto a execução atual coletou 140/102; a afirmação de 100% de cobertura não foi revalidada. O problema real e o roadmap do segundo bimestre precisam seção explícita. A documentação ainda mistura afirmações de comportamento desejado com comportamento efetivo, por exemplo QoS e confirmação de estado.

Não há exclusão de contexto Docker. `COPY . .` pode enviar/copiar ambientes virtuais, dependências npm e outros artefatos locais para imagens, apesar do ignore Git. Criar arquivos de exclusão Docker por contexto é uma correção simples proposta para reduzir contexto e evitar carregar dependências Windows em imagens Linux. Não foi aplicada nesta revisão.

## Plano de ação — aguarda aprovação

| Prioridade | Mudança proposta, em commit próprio | Problema resolvido e aceite |
|---|---|---|
| P0 | Rotacionar credenciais dos serviços em procedimento separado | Invalidar valores publicados; provar ingestão com novas credenciais e revogação das antigas, preservando volumes |
| P1 | Corrigir estado observado e confirmação de comandos | Broker offline não pode transformar ON em OFF no banco; teste de falha, confirmação por telemetria/estado e retry limitado |
| P1 | Aplicar schemas MQTT na entrada real | Rejeitar booleano/string indevido, negativos/não finitos, hora inválida, identidade incoerente e payload excessivo antes de write/WS |
| P1 | Corrigir metadados da série e cobertura | Calcular cobertura/estatísticas nos dados brutos; enviar gaps/metadados na API e consumir na UI; 8 h contínuas devem indicar cobertura próxima de 100% após redução |
| P1 | Tornar reconexões do firmware não bloqueantes | Verificação local de desligamento continua mesmo sem MQTT/Wi-Fi; verificar manualmente no Wokwi |
| P1 | Reduzir exposição dev e atualizar dependências auditadas | Bind local, CORS configurável, lock revisado; planejar ACL/TLS/autenticação antes de rede externa; repetir auditorias e testes sem atualização forçada |
| P2 | Readiness, recuperação e contexto Docker | Healthchecks, startup sem efeito no import, política de falha Influx, exclusões Docker, `npm ci`; demonstrar build limpo quando Docker Hub estiver acessível |
| P2 | Cliente API/composable e feedback reativo | Tipos, timeout, loading, dados antigos, controle de ordem de requests e pending reativo; confirmar no browser |
| P2 | Higiene de testes/documentação | Remover duplicações/teste de debug sem assertion, configurar Ruff/ESLint/Prettier, README raiz, problema real, roadmap e exemplos consistentes |
| P3 | Cadastro/seleção de dispositivo e evolução de contrato | Preparar múltiplos dispositivos e novos sensores com mudanças pequenas, guiadas pelo requisito real do segundo bimestre |

Mudanças de comportamento, contrato e estrutura acima **não foram executadas**. A autorização recebida abrangeu o saneamento e a continuidade da revisão, não a implementação deste plano. Nenhuma tecnologia da stack foi substituída.
