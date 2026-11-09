# M09 — Termostato, agenda e comando manual

| Item | Comportamento |
|---|---|
| Serviço mínimo | [V] `control` consome `q.control`, avalia termostato e registra ACK. Sem ele, o automático e a reconciliação de confirmações param; por isso é um serviço próprio. Python, UID 10001, 192 MiB/0,5 CPU, credenciais PostgreSQL/RabbitMQ exclusivas |
| Fonte | [V] Apenas amostra original confirmada no journal do gateway, identidade/rota/boot válidos, sequência crescente e UTC com até seis segundos. Backlog é contabilizado e concluído sem atuar |
| Termostato | [V] Padrão didático: setpoint 24 °C, faixa ±1 °C, mínimo desligado 180 s e ligado 60 s. Sem dados suficientes não inventa temperatura. Agenda opcional no fuso America/Sao_Paulo; madrugada de janela noturna pertence ao dia de início |
| Segurança | [V] Parada lógica em carcaça ≥80 °C; nova partida somente ≤75 °C. Não reduz intertravamento local de 85/75 °C nem mínimo desligado do simulador. Compressor ligado exige ventilador ligado |
| Prioridade | [V] Comando manual mantém modo manual até `release_auto`; desligar ventilador solicita também compressor desligado. Último ACK manual confirmado impede o automático mesmo se o relatório de modo ainda estiver em trânsito |
| Serialização | [V] Um comando pendente por dispositivo; lock transacional comum ao API/control/desativação; revisão cresce acima da sequência persistida e do watermark observado. Boot/revisão desconhecidos ou leitura antiga recusam intenção |
| Entrega | [V] Intenção e outbox são atômicas. AMQP confirmado e MQTT PUBACK não confirmam atuador. Somente ACK físico com identidade/revisão/boot/observado coerentes atualiza confirmação |
| Prazo | [V] Comando expira em 15 s. Após mais 5 s sem ACK: `failed`, `ack_timeout`, `execution_unknown=true`. ACK físico tardio reconcilia o registro original. Não estender validade nem criar outro pedido automaticamente |
| Idempotência | [V] `Idempotency-Key` por usuário, até 128 caracteres alfanuméricos/`_`/`-`. Mesmo pedido devolve a intenção original; corpo/dispositivo diferente com a mesma chave gera 409. ID do comando é o ID do envelope |
| Regras | [V] Admin edita configuração versionada com `expected_revision`; append-only de versões. Operador/admin controlam atuador; visualizador somente consulta. Auditoria transacional de intenção, resultado, timeout e regra |

## API e interface

- `POST /api/v1/devices/{id}/commands`, corpo `{"action":"fan_on"}`,
  `fan_off` ou `release_auto`, cabeçalho `Idempotency-Key`; retorna 202 e Location.
- `GET /api/v1/commands/{uuid}` e `GET /devices/{id}/commands` paginado por cursor
  UUID da intenção anterior. Payload privado e identificador do autor não são expostos.
- `GET /devices/{id}/control`: observação operacional recente, modo/bloqueio e horário;
  **não** alimenta a store do dashboard ou cena 3D.
- `GET/PATCH /devices/{id}/rule`: setpoint/faixa, ciclos e agenda; revisão e fuso explícitos.
- Em Dispositivos → Detalhes, botões exibem intenção pendente/confirmada/falha e
  observação física separada. Formulário de regra somente para administrador.

## Verificação e limites

[V] Resultado local: 193 testes Python, 231 Vitest, 27 integrações PostgreSQL/API/
gateway/controle/WS e seis Playwright passaram. Lint, tipos, formatação e build
passaram; permanece o aviso conhecido do chunk de validação descrito no M07.

[test-control.ps1](../../tools/bootstrap/test-control.ps1) usa banco descartável para
testes de domínio, API e protocolo; os percursos Playwright usam o Compose real.
O teste Web desliga ambos, liga ventilador e libera automático ao final, sem reduzir
o intervalo de proteção nem avançar relógios live.

[V] Antes do aceite final do módulo, testes locais já observaram um comando automático
com ACK real do simulador e o percurso Web→API→AMQP→gateway→MQTT→atuador→telemetria.
Esse ensaio não calibra a física, estima vida útil nem prova recuperação de perda de disco.

[N] Histerese de alertas preditivos e inferência são M13; eventos de insight recebidos
não comandam diretamente compressor neste módulo. Configuração do cenário físico pela
UI exigirá contrato explícito, sem esconder parâmetros em reason_code. Retenção/backup
dos comandos e medidas de latência/carga integrada permanecem em M18.
