# Gateway MQTT ↔ RabbitMQ — M04

O serviço liga o simulador do ar-condicionado ao barramento interno, usando exclusivamente
as credenciais `mqtt_gateway`, `rabbit_gateway` e `postgres_gateway`. Executa como UID
10001, sem portas publicadas, com 192 MiB e 0,5 CPU no Compose raiz.

## Garantias implementadas

| Fronteira | Comportamento |
|---|---|
| MQTT → PostgreSQL | Valida contrato, tópico, dispositivo e zona; grava bytes originais, presença e outbox na mesma transação |
| PostgreSQL → simulador | Envia `transport.received` somente depois do commit; repetição conserva ID e primeiro horário de observação |
| Outbox → RabbitMQ | Publicação persistente e mandatory, publisher confirms e `user_id=gateway`; repete os mesmos bytes após falha |
| RabbitMQ → comando | Consumidor registrado em `q.commands.gateway`, prefetch 1; ACK do broker somente após inbox durável |
| Origem do comando | `user_id` autenticado pelo RabbitMQ deve corresponder a `api` ou `control`; controle automático não pode solicitar modo manual |
| Encaminhamento MQTT | QoS 1, sem retain; exige boot observado, revisão conhecida e amostra com até seis segundos; revalida expiração imediatamente antes do publish |
| Confirmação física | PUBACK não conclui comando. Apenas ACK do simulador, vinculado ao comando e gravado com sua outbox, permite concluir a inbox |
| Falhas | Payload inválido/conflitante em quarentena durável; falha de dependência mantém pendências e retira readiness |

O LWT contém o horário de configuração da conexão, não o instante da queda. O gateway
gera um evento de disponibilidade com ID derivado e horário da primeira observação,
preservando o original na inbox. O simulador prepara outro ID de LWT para cada reconexão.
Amostras antigas continuam encaminhadas para histórico, mas não renovam a presença.

Comandos aguardando ACK usam o retry do pacote comum; a retomada consulta primeiro o
resultado já persistido. Um comando vencido sem ACK não é reenviado nem recebe confirmação
física inventada. A aplicação deverá distinguir expiração de confirmação em M09.

## Verificação

Execute `powershell -ExecutionPolicy Bypass -File tools/bootstrap/test-gateway.ps1` na raiz.
O script usa imagem instalada, PostgreSQL de teste descartável e vhost RabbitMQ isolado
para durabilidade/ACL. O teste final usa o simulador real: liga o ventilador da condensadora
com o compressor desligado, confirma telemetria e restaura ambos desligados em modo auto.
Não execute simultaneamente com outro operador comandando o mesmo aparelho simulado.

Os testes também cobrem payload original, duplicatas, horário de observação, amostra antiga,
expiração, impersonação, origem e ACK. Interrupções reais do gateway e RabbitMQ foram
exercitadas localmente: spool e outbox cresceram e esvaziaram após a retomada.

## Limites explícitos

- Registro consultado no PostgreSQL por M08; identidade inicial `ac_01`/`quarto`.
  Telemetria de cadastro desativado é preservada; comandos são recusados também no
  despacho. Cadastro não provisiona automaticamente novos clientes/ACL MQTT.
- Não implementa termostato, API Web, gravador InfluxDB nem inferência.
- A visão SQL `transport.device_status` expõe somente metadados; usuários consumidores
  não recebem acesso de escrita às tabelas do gateway.
- Recebimentos anteriores a M04 podem não trazer `user_id` AMQP. M05 deverá comprovar
  correspondência de hash com a inbox do gateway antes de aceitar esses eventos legados.
- Retenção das tabelas específicas e ensaio de carga sustentada serão consolidados no
  aceite integrado; CI remoto e scan de imagens ainda não foram verificados.

Remover este serviço interrompe os dois sentidos do transporte e a confirmação durável
que permite liberar o spool do simulador.
