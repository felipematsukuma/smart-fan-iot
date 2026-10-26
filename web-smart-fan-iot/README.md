# Aplicação web — Smart Fan IoT

Veja a [visão geral e o roadmap](../README.md). A stack é Vue 3 + TS + Vite + Chart.js, FastAPI/Python, Mosquitto e InfluxDB. PostgreSQL armazena configuração e o último estado observado do relé.

## Inicialização

Com Docker Desktop ativo, neste diretório:

```powershell
# Somente na primeira configuração; não sobrescreva um ambiente existente.
Copy-Item .env.example .env
# Edite o arquivo local e substitua os placeholders antes de subir.
docker compose up -d --build
docker compose ps
```

O [.env.example](./.env.example) lista as variáveis principais. Senhas/token não têm defaults utilizáveis no código. Na primeira inicialização Influx, `INFLUXDB_TOKEN` também inicializa o administrador se `INFLUXDB_ADMIN_TOKEN` estiver ausente. Depois, separe um token administrativo de um token de aplicação com apenas read/write no bucket. Um volume já inicializado não muda de senha/token quando você edita variáveis de setup: use a API/CLI do serviço para rotacionar.

| Serviço | Endereço local |
|---|---|
| Dashboard | http://localhost:5173 |
| API / OpenAPI | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| InfluxDB | http://localhost:8086 |
| MQTT | localhost:1883 |
| PostgreSQL | localhost:5432 |

As portas do Compose são publicadas em `127.0.0.1`. Influx/PostgreSQL têm healthchecks e o backend espera readiness, com tentativas limitadas de inicialização. O broker persiste mensagens retidas no volume. Reiniciar não exige apagar volumes: use `docker compose stop` e `docker compose up -d`.

Compile e inicie o [Wokwi](../esp32-simulador/README.md), mantendo a aba ativa e em primeiro plano durante testes. `host.wokwi.internal` é o host usado pelo firmware; `localhost` dentro do ESP32 não é o broker do computador.

## Configuração

[Settings](./backend/app/config.py) lê variáveis de processo e o ambiente local ancorado neste diretório. Fora do Docker, sobrescreva `POSTGRES_HOST=127.0.0.1`, `INFLUXDB_URL=http://127.0.0.1:8086` e `MQTT_BROKER=127.0.0.1`. Defaults de host são nomes dos serviços Docker.

`CORS_ORIGINS` é uma lista JSON de origens permitidas; a origem WS também é verificada. `INFLUXDB_TIMEOUT_MS` limita transporte, com retry limitado. Uma fronteira de I/O também limita a espera por consultas a 3 s e escritas a 2 s, inclusive quando DNS não respeita o timeout do socket; workers ocupados não geram uma fila crescente. Não é fila durável. O evento live indica `persisted: false` quando a escrita não é confirmada dentro do prazo; ela ainda pode terminar depois. A UI distingue essa incerteza de uma gravação confirmada.

`VITE_API_URL`, `VITE_WS_URL` e `VITE_DEVICE_ID` configuram o frontend. O seletor usa `?device=ID`, recriando a sessão para o dispositivo escolhido. REST tem timeout; respostas antigas não sobrescrevem a seleção mais recente de período. Loading, vazio, erro e dados antigos são estados distintos.

## Contrato MQTT

Prefixo: `devices/{device_id}`. Payload JSON de até 2048 bytes no backend; identidade deve corresponder ao tópico. Tipos, números finitos/não negativos e horários são validados antes de persistir/transmitir. A UI também valida WS em runtime.

| Sufixo | Origem | Dados | Entrega |
|---|---|---|---|
| `/telemetry` | ESP32 | Identidade, booleanos, V, A, W, uptime em ms; configuração/contadores opcionais | QoS 0, sem retain |
| `/state` | ESP32 | Identidade, `is_on`, configuração/contadores | QoS 0, retained |
| `/config` | ESP32 | Identidade, `auto_mode`, `shutdown_time` | QoS 0, retained |
| `/command` | Backend | `action: ON` ou `action: OFF` | QoS 1, sem retain; ESP32 assina QoS 1 |
| `/config/set` | Backend | `auto_mode` boolean, `shutdown_time` HH:MM | QoS 1, retained; ESP32 assina QoS 1 |

Exemplo ilustrativo:

```json
{"device_id":"esp32_fan_01","is_on":true,"voltage_rms":127,"current_a":0.4,"power_w":45.72,"timestamp":20000,"device_epoch_s":1793025900,"auto_mode":true,"shutdown_time":"03:00","total_energy_wh":0.1,"fan_on_time_ms":10000}
```

`timestamp` é uptime, não epoch. `device_epoch_s` é opcional, somente com NTP sincronizado. O ponto Influx usa tempo UTC de recepção capturado antes de escrever, preservado nos retries. Measurement `electrical_measurement`, tag `device_id`, fields `is_on` inteiro, `voltage_rms`, `current_a`, `power_w` e, quando disponível, `device_epoch_s`. Energia acumulada do firmware não é a fonte do total histórico.

O subscriber aceita novos IDs para telemetria; comandos/configuração exigem cadastro. Não há ACK de aplicação correlacionado por ID de comando. ACK MQTT indica publicação; estado observado muda só por mensagens do dispositivo. O scheduler repete OFF a cada 30 s no minuto devido enquanto observa ON, sem marcar OFF quando o broker falha.

## API REST e WebSocket

Contratos em http://localhost:8000/docs e nos [schemas](./backend/app/schemas.py).

| Método | Rota | Entrada/resultado |
|---|---|---|
| GET | `/health` | Processo e conexão MQTT; não é auditoria completa dos bancos |
| GET | `/api/devices` | Lista de dispositivos |
| POST | `/api/devices` | `device_id`, `name`; 201, 409 para duplicado |
| GET | `/api/device/{id}` | Configuração e estado observado; 404 se ausente |
| POST | `/api/device/{id}/command` | Apenas `action: ON/OFF`; `speed` removido porque o relé não controla velocidade |
| PUT | `/api/device/{id}/schedule` | Hora, habilitação e tarifa, para compatibilidade |
| PUT | `/api/device/{id}/auto-shutdown` | Hora HH:MM e `auto_off_enabled` boolean |
| PUT | `/api/device/{id}/tariff` | `kwh_rate` finito e não negativo |
| GET | `/api/device/{id}/metrics` | `range_hours` 1..168 ou `start`/`end` juntos; `max_points` 2..1000, default 240 |
| WS | `/ws` | Eventos telemetry/state/config; presença exige telemetria recente, não apenas estado retido |

Metrics retorna período, duração, `history_count` bruto, histórico reduzido, `avg_power_w`, `max_power_w`, `energy_wh`, `estimated_kwh`, `coverage`, `covered_seconds` e `segments` active/off/no-data com limites reais. Pydantic valida a resposta. Janela inválida: 422; leitura acima de 400 mil amostras: 413; falha de consulta: 503. Não há agregação arbitrária: a redução serve à exibição, não à contabilidade.

## Energia e gráfico

Simulação: `P[W] = V[V] × I[A] × FP`. O backend integra trapézios: `Wh = Σ((P1+P2)/2 × Δt_s/3600)`, só para intervalos de até 80 s. `kWh = Wh/1000`. Bordas sem amostras não são extrapoladas. A média é aritmética das leituras, não ponderada no tempo.

Cobertura, continuidade e máximo são calculados sobre dados brutos antes do downsample. O gráfico usa esses metadados e interrompe a linha nas lacunas reais. O eixo comprime intervalos desligados e sem dados; rótulos/tooltips mantêm tempos reais. O gráfico consulta a API a cada 5 s; indicadores instantâneos usam WS. Contagem bruta não é quantidade de pontos desenhados.

Custo na UI: `kWh × tarifa atual`. Projeção mensal: `custo × 720h / duração da janela`. Com cobertura incompleta, a UI avisa que podem estar subestimados. Não é faturamento: falta tarifa histórica, sensor calibrado e política de cobertura mínima.

## Desenvolvimento e qualidade

No [backend/](./backend/):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check app tests
.venv/Scripts/python.exe -m ruff format --check app tests
.venv/Scripts/python.exe -m mypy app
.venv/Scripts/python.exe -m pip_audit
```

O [lock Python](./backend/requirements.lock) fixa o grafo testado em Linux/Python 3.11; uvloop é excluído no Windows por marcador. As dependências diretas usam essas constraints. Atualizações exigem regenerar constraints e repetir os testes. [pyproject.toml](./backend/pyproject.toml) configura pytest, Ruff e mypy com plugin Pydantic.

No [frontend/](./frontend/), com Node 24:

```powershell
npm ci
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npm audit
```

Docker usa `npm ci`. Os contextos excluem dependências locais, ambientes virtuais e arquivos de ambiente. Os testes cobrem domínio, validação e fronteiras com fakes; não substituem Wokwi. Não há promessa de 100% de cobertura.

## Segurança e operação

As credenciais anteriormente versionadas foram rotacionadas no ambiente local da revisão. O token antigo está inativo. O histórico Git foi preservado; não reutilize valores encontrados nele. O administrador novo fica apenas no ambiente local e não é passado ao backend.

Mosquitto é anônimo no dev isolado. Antes de exposição remota: autenticação REST/WS, autorização por dispositivo, usuário/senha MQTT, ACL, TLS, gestão de segredos e configuração de produção. CORS não substitui autenticação. Execute apenas um worker enquanto MQTT/scheduler estiverem integrados ao processo.

A retenção do bucket existente é sem expiração; o Compose não a altera automaticamente. Defina retenção antes de ampliar volume e faça backup. Inicialização de tabelas não substitui migrações de schema futuras.
