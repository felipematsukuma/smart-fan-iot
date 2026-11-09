# WebSocket, snapshot e dashboard — M07

[V] A API mantém um consumidor `q.events.api`, snapshot PostgreSQL e hub WebSocket no
mesmo processo. Executar **um worker Uvicorn**: o hub é local, sem serviço adicional.
Remover o consumidor interrompe atualizações; remover o snapshot impede recuperação
do estado após desconexão. WS não promete entregar todo frame ao navegador.

## Fronteiras verificadas

| Entrada | Controle |
|---|---|
| `/api/v1/auth/ws-ticket` | JWT/sessão, Origin e dispositivos autorizados; somente hash do ticket, escopo capturado, TTL máximo 30 s |
| `/ws` | Origin permitido, nenhuma query string; primeira mensagem authenticate em até cinco segundos; ticket consumido atomicamente |
| Subscribe | Subconjunto do escopo emitido, revalidado no servidor; outro dispositivo fecha a conexão |
| Sessão | Consulta de revogação/versão a cada segundo, com timeout; logout/expiração encerram o stream |
| Recursos | Até quatro sockets pendentes/IP, 16 globais, 32 autenticados e três por usuário; fila individual 32, envio com deadline |
| Heartbeat | Ping de aplicação a cada 15 s, pong correspondente; silêncio de 45 s encerra a conexão |
| AMQP | Conta autenticada, rota, message ID e schema; commit antes do ACK; inválidos em quarentena durável |
| Frame | Hora, equipamento, boot, sequência, zona e digest de leituras devem corresponder à origem registrada pelo gateway |
| Frescor | Timestamp original e primeira observação com até seis segundos; nenhum replay ganha horário novo |

[V] A identidade de origem é registrada atomicamente com a inbox/outbox do gateway.
A migration preserva metadados de eventos existentes ainda disponíveis. O digest de
conteúdo é independente do enriquecimento do envelope; dados fonte não são reescritos.
As migrations novas não alteram revisões já aplicadas.

## Protocolo e navegador

[V] Eventos de domínio usam o envelope v2 existente, diretamente no WebSocket.
Controles são Pydantic em [ws_protocol.py](../../packages/smartfan_common/src/smartfan_common/ws_protocol.py),
exportados por [export_ws_contracts.py](../../tools/export_ws_contracts.py). Authenticate,
subscribe, snapshot, ping/pong e notice são fechados; fixtures Python/TypeScript comuns.

[V] O navegador obtém a identidade dos dispositivos por REST e os valores live somente
pelo WebSocket. Reconexão usa novo ticket, backoff 1–30 s com jitter e snapshot autorizado.
Tokens/tickets não aparecem na URL. Logout elimina maps, buffers e timers. Boot, ordem,
sequência, futuro e duplicatas são verificados novamente no store. A presença MQTT,
conexão e frescor são estados separados; sem frame fresco há “sem dados”, sem extrapolação.
O gráfico conserva até 120 amostras e quebra linhas em lacunas/mudanças de boot.

[V] A CSP permanece sem unsafe-eval. Validadores AJV são compilados antes da execução
e versionados; [script de geração](../../web-smart-fan-iot/frontend/scripts/contracts-validators.mjs).
As regras de negócio entre campos continuam no validador compartilhado. Schemas/fixtures
Python são excluídos somente do formatador; geração e consistência têm checks próprios.
Referência: [AJV standalone](https://ajv.js.org/standalone).

## Histórico e energia

[V] `/api/v1/devices/{id}/metrics?hours=24` exige sessão e dispositivo autorizado;
intervalo 1–168 h. Token exclusivo da API lê live/lab e não escreve. Gráfico tem no
máximo 1000 pontos. Energia usa potência bruta, gaps de até seis segundos, identidade
de boot e omissões; não usa pontos agregados nem preenche ausência com zero. Sem
cobertura, energia é null. Erros/dependências geram problem+json, sem total parcial falso.
Histórico tem estado de carregamento/vazio/erro e é independente da reconexão live.
Consultas históricas têm timeout de 10 s por consulta, sem aumentar a tolerância
de frescor de seis segundos do stream. Falhas continuam visíveis e permitem repetir.

## Como verificar e limites

[V] [test-realtime.ps1](../../tools/bootstrap/test-realtime.ps1) executa PostgreSQL/InfluxDB
descartáveis, conexão AMQP→API→WS real e Playwright. O fixture de inferência usa uma
amostra **real** do simulador e insight model_unavailable/null; não é o serviço ML M13.
Ensaios que publicam frames ou reiniciam a API são sequenciais, para não disputar o
mesmo simulador. O E2E verifica ID correlacionado no painel, expiração, reinício da API,
novo frame e histórico preservado. Não executar junto a uma apresentação ativa.

[V] Validação local: 171 testes Python, 231 testes Vitest, 10 testes de integração
com PostgreSQL/InfluxDB/AMQP e quatro testes Playwright passaram. Lint, tipos e
checks dos contratos gerados passaram; build mantém aviso de chunk acima de 500 kB
(validador de contratos pré-compilado, cerca de 57 kB gzip), sem liberar unsafe-eval.

[N] M13 ainda deve produzir os frames continuamente; treino/inferência, cena 3D,
carga integrada, CI remoto e scans não são certificados por este módulo. Fonte sem
frame recente permanece sem dados, mesmo com socket conectado. Retenção operacional
das identidades/snapshots será consolidada com os backups e a limpeza em M18.
