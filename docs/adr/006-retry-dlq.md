# ADR 006 — Retry durável, idempotência e DLQ

Status: decisão proposta; sem garantia operacional medida.

Contexto: MQTT, AMQP, Influx e PostgreSQL não compartilham transação distribuída; confirmações podem se perder.

Decisão: at-least-once, inbox/outbox PG por consumidor, efeitos idempotentes, retry agendado no próprio processo e falha permanente preservada em PG + DLQ.

Backoff: 1/5/30 s com jitter; cinco tentativas, circuito para indisponibilidade persistente; sem requeue infinito nem replay automático de comando expirado.

Quorum durável em um nó; publisher confirms e mandatory; dead-letter at-least-once como proteção adicional, validado na versão pinada.

Alternativas: nack/requeue imediato cria loop; plugin delayed-message adiciona dependência; Celery/Redis redundam serviços; exactly-once ponta a ponta seria promessa indevida.

Consequências: mais tabelas/estado de recuperação, mas menos ferramentas; ensaiar queda entre cada gravação e publicação; disco íntegro continua premissa.

Se remover inbox/outbox, uma falha entre confirmar e publicar pode perder evento ou repetir efeito sem controle.

Ver [arquitetura, seção 5](../plano/03-arquitetura.md#5-mensageria-e-semântica-de-entrega).
