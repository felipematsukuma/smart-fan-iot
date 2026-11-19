# ADR 009 — Prévias limitadas e estado de alerta no transporte existente

Status: implementada no [fechamento funcional](../implementacao-2026-11-14.md), sem novo serviço, dependência, fila ou migration.

Contexto: a Mensageria precisa mostrar mensagens recentes sem consumir filas de trabalho; a cena precisa recuperar alertas existentes pelo WebSocket, inclusive após reconexão.

Decisão:

- Capturar somente metadados dos eventos validados e commitados pelo consumidor API existente. Buffer de 100 entradas em memória, janela consultável de cinco minutos, reiniciado com o processo. A API administrativa combina essas prévias com o monitoramento RabbitMQ já existente.
- Não persistir payloads extras nem abrir consumidor de diagnóstico. A lista representa `q.events.api`, não promete visibilidade de todas as filas. A DLQ continua no journal durável próprio.
- Guardar a última transição de alerta por equipamento na tabela de snapshots existente. Para dados anteriores à atualização, recuperar os bytes originais já aceitos na inbox da API, referenciados pelo alerta cadastrado; não fabricar uma nova transição a partir de SQL.
- Enviar o evento original no snapshot WS com instante preservado. A cena lê estado e alertas do store; dados antigos não movimentam a geometria. Ausência de leitura não encerra um alerta.

Consequências: prévias podem desaparecer no restart, sem afetar processamento ou auditoria. O histórico oficial continua nos bancos/journals existentes. Snapshot mantém teto de 300 eventos, priorizando frames, presença e alerta antes do estado auxiliar. Remoção futura de bytes antigos da inbox pode impedir recuperação de transição anterior à atualização; não se deve fabricar mensagem substituta.

Alternativas rejeitadas: `get`/ACK nas filas para inspecionar alteraria entrega; fila extra de captura e tabela de payloads ampliariam topologia, retenção e manutenção sem necessidade nesta entrega.
