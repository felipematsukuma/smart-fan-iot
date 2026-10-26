# Implementação e validação — 26/10/2026

Branch `feature/dashboard-energy-v2`. Implementação autorizada após a [revisão técnica](./revisao-tecnica-2026-10-26.md). A revisão original é um registro anterior às correções; este documento descreve o estado posterior.

## Resultado

O fluxo **ESP32/Wokwi → Mosquitto → backend Python → InfluxDB → API → Vue** foi executado. O Wokwi permaneceu ativo e em primeiro plano durante a validação, conforme orientação do usuário. Houve comando ON/OFF pelo dashboard, confirmação pelo dispositivo, mudança no relé/LED, leitura analógica, escrita histórica e atualização do gráfico/indicadores.

O potenciômetro no máximo produziu aproximadamente **0,800 A e 91,44 W**. OFF voltou a **0 W**. São valores do modelo de simulação, não calibração elétrica.

## Mudanças implementadas

| Área | Alteração | Evidência no código |
|---|---|---|
| Estado observado | Scheduler não grava OFF após publicar ou falhar; repete solicitação no minuto devido enquanto observa ON | [scheduler](../web-smart-fan-iot/backend/app/scheduler.py) e [testes](../web-smart-fan-iot/backend/tests/test_scheduler.py) |
| Entrada MQTT | Schema aplicado ao payload real; booleanos estritos, finitude/faixas, tamanho, identidade e horário | [schemas](../web-smart-fan-iot/backend/app/schemas.py), [subscriber](../web-smart-fan-iot/backend/app/mqtt_service.py) |
| Energia | Integração e metadados calculados antes de reduzir a série | [energy](../web-smart-fan-iot/backend/app/energy.py) |
| Gráfico | Cobertura/segmentos/máximo vêm dos dados brutos; lacunas interrompem o traço; eixo contempla máximo bruto | [PowerChart](../web-smart-fan-iot/frontend/src/components/dashboard/PowerChart.vue) e [timeline tests](../web-smart-fan-iot/frontend/src/lib/timeline.test.ts) |
| API | Registro/listagem de dispositivos, response models, limites de período/pontos/leitura bruta e 503 explícito para storage | [main](../web-smart-fan-iot/backend/app/main.py) |
| Frontend | Cliente REST tipado, timeout, ordem de respostas, loading/erro/vazio/dados antigos, pending reativo e seletor de dispositivo | [api](../web-smart-fan-iot/frontend/src/lib/api.ts), [App](../web-smart-fan-iot/frontend/src/App.vue) |
| WS | Validação runtime; retained state/config não conta como presença; falha de persistência é sinalizada | [realtime](../web-smart-fan-iot/frontend/src/lib/realtime.ts), [useWebSocket](../web-smart-fan-iot/frontend/src/composables/useWebSocket.ts) |
| Firmware | Reconexão temporizada, NTP assíncrono, proteção local antes da rede, leitura zero sem fallback fictício, buffer MQTT explícito e validação de configuração | [main.cpp](../esp32-simulador/src/main.cpp) |
| Tempo | Uptime separado do epoch opcional do dispositivo; timestamp UTC de recepção capturado antes do write/retry | [firmware](../esp32-simulador/src/main.cpp), [writer](../web-smart-fan-iot/backend/app/mqtt_service.py) |
| Operação | Healthchecks/readiness, portas em loopback, CORS configurável e origem WS verificada, Mosquitto persistente | [Compose](../web-smart-fan-iot/docker-compose.yml), [mosquitto.conf](../web-smart-fan-iot/mosquitto/config/mosquitto.conf) |
| Resiliência | Timeout de transporte e limite de espera do chamador mesmo quando DNS demora; concorrência limitada sem fila crescente | [BoundedIO](../web-smart-fan-iot/backend/app/io_boundary.py) e [testes](../web-smart-fan-iot/backend/tests/test_io_boundary.py) |
| Reprodutibilidade | Constraints Python, lock npm, `npm ci`, contextos Docker sem dependências/ambiente local | [requirements.lock](../web-smart-fan-iot/backend/requirements.lock), [package-lock](../web-smart-fan-iot/frontend/package-lock.json) |
| Qualidade | Ruff, mypy/Pydantic e ORM tipado; ESLint/Prettier; remoção de testes duplicados/debug sem assertion | [pyproject](../web-smart-fan-iot/backend/pyproject.toml), [eslint](../web-smart-fan-iot/frontend/eslint.config.js) |

O campo `speed` foi removido do comando REST porque o atuador é um relé ON/OFF. Clientes que enviavam esse campo agora recebem 422. Os tópicos existentes foram preservados. Novos metadados no histórico são aditivos; o frontend atual os utiliza para não inferir cobertura da série reamostrada.

## Verificações executadas

- Firmware: `pio run` passou. Último build registrado: RAM 45.412 bytes e flash 785.605 bytes.
- Python local: **153 testes passaram**; Ruff lint/format e mypy passaram. Há um warning de depreciação da combinação FastAPI/Starlette TestClient com httpx; os testes continuam passando.
- Python 3.11 no container: **153 testes passaram** também na imagem reconstruída.
- Frontend: **104 testes passaram**, ESLint, Prettier, `vue-tsc` e build Vite passaram.
- `npm audit`: **zero vulnerabilidades** após atualizar Vite/Vitest, dependências transitivas e o lock. Node de desenvolvimento/Docker foi alinhado à versão 24, compatível com as versões verificadas no registry.
- `pip-audit` no ambiente de desenvolvimento: **nenhuma vulnerabilidade conhecida**. Uma auditoria separada das versões congeladas do container também não encontrou vulnerabilidades conhecidas. A imagem foi reconstruída com certifi atualizado e pip 26.2.2.
- `docker compose up -d --build` passou, com volumes preservados e serviços de dados saudáveis. As portas publicadas são locais.
- Verificação final: backend saudável/MQTT conectado, dispositivo OFF com agendamento original, histórico HTTP 200 com 433 amostras na janela consultada, energia 1,559 Wh e máximo 91,44 W. Origem local 5174 recebeu CORS; uma origem externa de teste não recebeu permissão. Node do container frontend: 24.22.1.
- Validação browser: comando ON confirmado pelo ESP32, indicadores de 0,800 A/91,4 W, comando OFF confirmado, histórico com consumo não zero e gráfico renderizado. Contagem de amostras agora se refere à coleta bruta, sem inventar cadência a partir da redução visual.
- Regressão de oito horas: 14.401 pontos a cada 2 s, 30 W constantes, reduzidos a 240 pontos, mantêm **100% de cobertura e 240 Wh**. Duas leituras zero separadas por uma hora são ausência de cobertura nos metadados brutos.

### Desligamento local com broker parado

Foi observado o relógio sincronizado do próprio ESP32 por RFC2217, programado o minuto seguinte e solicitado ON. Após confirmação de configuração/estado, o Mosquitto foi parado. O serial confirmou OFF local no epoch `1793025900` (11:45 no relógio do dispositivo), com o broker ainda parado. Isso demonstra que o loop de reconexão não bloqueou o desligamento.

O broker foi reiniciado; agendamento original **07:54, habilitado**, foi restaurado; o estado final solicitado/confirmado foi OFF. Os volumes permaneceram intactos. O teste levou em conta que a velocidade da simulação pode ser menor que o tempo de parede.

### Queda do Influx e recuperação

O primeiro teste real revelou que o timeout do cliente não limitava adequadamente DNS do sistema operacional. A resposta ultrapassava a espera desejada; por isso foi acrescentada a fronteira de I/O limitada.

No reteste com endereço IPv4 explícito, a API retornou **503 em 3,04 s**. Telemetria continuou chegando por WS com `persisted=false`. O browser exibiu aviso de histórico desatualizado e de persistência não confirmada, preservando os dados anteriores. Após reiniciar o Influx, a API recuperou **HTTP 200**.

O limite não cancela uma chamada DNS em andamento: mantém o worker ocupado e rejeita novas operações quando a capacidade esgota. Não há crescimento ilimitado de fila. Uma escrita que excedeu o prazo pode completar depois; portanto `persisted=false` significa **gravação não confirmada dentro do prazo**, não prova de que jamais será gravada. Não há replay durável de amostras descartadas.

## Credenciais

Rotação efetuada no ambiente local, sem imprimir novos valores:

- Senha PostgreSQL nova verificada; senha antiga rejeitada.
- Senha Influx nova aceita em signin (204); antiga rejeitada (401).
- Token de aplicação novo com read/write apenas no bucket de telemetria; token administrativo novo separado e fora do ambiente do backend.
- Autorização antiga do Influx marcada `inactive`. A consulta com token antigo foi negada (404 por ocultação do recurso); a mesma consulta com token novo retornou 200.
- Backend reconstruído/recriado e ingestão verificada com as credenciais novas.

Os valores ficam apenas no ambiente local ignorado. O histórico Git não foi reescrito: os valores antigos permanecem nos commits anteriores, mas foram invalidados no ambiente testado. Outros ambientes que tenham reutilizado esses valores precisam de rotação própria.

## Teste reutilizável

Com as dependências de desenvolvimento instaladas, execute da raiz:

```powershell
python tools/verify_wokwi.py
python tools/verify_wokwi.py --control
```

O [smoke test](../tools/verify_wokwi.py) padrão apenas lê telemetria/histórico. `--control` solicita ON/OFF e restaura o estado inicial; use somente no simulador. A execução com controle passou com ON 91,44 W, OFF 0 W e 309 amostras na janela de uma hora naquele momento. Requer Wokwi ativo/em primeiro plano e pyserial, declarado nas [dependências dev](../web-smart-fan-iot/backend/requirements-dev.txt).

## Limites e decisões mantidas

### Checklist atualizado

| # | Requisito | Situação após implementação |
|---|---|---|
| 1 | Problema real | OK: público, desperdício e critério de sucesso no README raiz |
| 2 | Interface Vue 3 | OK: interface executada com ESP32 ativo |
| 3 | TypeScript | OK: strict e typecheck |
| 4 | Vite | OK: build e execução |
| 5 | Sensor IoT | PARCIAL: entrada analógica simulada por potenciômetro; aceitação acadêmica a confirmar |
| 6 | Wokwi | OK: sessão executada em primeiro plano com firmware atual |
| 7 | MQTT | OK: telemetria e comandos reais na simulação |
| 8 | Mosquitto | OK: execução, interrupção e reconexão verificadas |
| 9 | Backend Python | OK: Python 3.11 no Docker e suíte passando |
| 10 | Leituras InfluxDB | OK: leituras do Wokwi persistidas; recuperação testada |
| 11 | Histórico | OK: API consultada e usada pelo painel |
| 12 | Gráfico/indicador | OK: potência, energia, cobertura e estado observados |
| 13 | GitHub | Baseline publicado; implementação em commits locais, sem push conforme instrução |

### Escopo futuro explícito

- Segurança de produção permanece no roadmap: o broker dev ainda é anônimo, sem TLS/ACL; API/WS não têm autenticação por usuário. Loopback e CORS reduzem exposição local, mas não substituem esses controles. Não expor externamente essa configuração.
- Potenciômetro é um substituto analógico do sensor. A aceitação desse requisito acadêmico depende do avaliador; hardware real/calibração não foram implementados.
- Projeção de custo continua simples e explicitamente estimada na UI, com alerta de cobertura parcial; não houve implantação de tarifa histórica/faturamento.
- Retenção do bucket existente continua sem expiração. Nenhuma política destrutiva de retenção foi aplicada aos dados existentes.
- Sem migração geral de pastas ou novos serviços/frameworks. O monorepo atual ganhou documentação raiz e contratos; PostgreSQL foi mantido para configuração.
- Sem ACK correlacionado por comando, fila durável ou deduplicação entre boots. O tempo de recepção torna retries do mesmo ponto idempotentes, mas não resolve duplicação de mensagens de origem com novos tempos de recepção.
- Imagens têm tags explícitas, mas não digests imutáveis no Compose/Dockerfiles. As auditorias de pacotes não substituem scanner de CVEs de imagens/OS.
- Somente um worker do backend no desenho atual. Mais de um duplicaria subscriber/scheduler.

Foram criados commits próprios após a preservação, sem push, rebase ou alteração de histórico. A branch `backup/pre-review-20261026` continua apontando para o estado preservado antes da implementação. O [README](../README.md) e os guias dos componentes refletem os contratos atuais.
