# Entrega durável — M02

Dependências opcionais: instalar `smartfan-common[reliability]`. Importar contratos/features não abre banco, broker nem servidor. A imagem Python compartilhada instala versões fixadas desse extra e as constraints do backend.

## Banco e migrações

O bootstrap privilegiado cria contas PostgreSQL por serviço sem alterar senhas existentes, remove CREATE público e aplica Alembic no schema transport. As revisões são incrementais: 0001_transport cria o journal e 0002_retention acrescenta limpeza restrita. Não usar create_all para migrar nem downgrade destrutivo. Os bancos/volumes legados permanecem separados.

`engine_for(owner, password_file)` usa credencial de arquivo, URL estruturada, connect/lock/statement timeouts, pool limitado e parâmetros ocultos em erros. Workers não recebem segredo administrativo. RLS de inbox/outbox/failures usa a identidade PostgreSQL, não um service_id enviado pelo cliente. A view receipts permite a writer/control ler somente event_id/observed_at do gateway, sem seu payload.

## Inbox/outbox

- `receive`: persistir bytes e hash, com saídas opcionais na mesma transação; repetir ID/bytes/rota retorna duplicate. ID com bytes ou rota diferentes preserva falha e prepara DLQ.
- `transaction` permite agrupar decisão de domínio e enqueue. Se houver transação externa, **ACK somente após o commit externo**, nunca apenas porque receive retornou.
- `claim`: obtém trabalho com geração e prazo; apenas uma posse vigente. `renew` mantém tarefas longas; dono expirado não pode concluir nem renovar.
- `finish`: efeito SQL de domínio, saídas e conclusão são atômicos. Revalida a posse depois do callback, antes da conclusão. I/O externo não fica dentro da transação SQL.
- `retry`: backoff 1/5/30 s, jitter limitado; quinta tentativa de inbox ou falha permanente produz registro de falha/DLQ. Falha de publicação mantém outbox, sem descartar evento aceito.
- `ConfirmedPublisher` habilita confirms uma vez por canal e publica persistent/mandatory; só conclui outbox após confirmação. Queda nessa fronteira pode repetir publicação: destinatário precisa dedupe.
- `quarantine` preserva também payload vazio. Corpo maior que 16 KiB usa referência à falha, mantendo wrapper DLQ no limite. A biblioteca não valida origem/ACL do evento de domínio: o adapter deve validar M00 antes de aceitar trabalho.

Quota por proprietário considera payload pendente e uma margem fixa de 256 bytes por registro, incluindo falhas. Não é limite exato de disco/índices; monitorar volume continua necessário. Ao exceder, a transação falha sem confirmação falsa. Pequena exclusão por advisory lock por proprietário serializa as mutações/quotas e evita deadlocks entre receber e concluir; medir throughput no aceite de carga.

`prune_terminal_payloads` libera corpos terminais após 24 h e remove identidades concluídas após 31 dias. A função SQL restrita usa session_user: um serviço não escolhe outro proprietário nem ganha DELETE arbitrário. Falhas originais e pendências não são eliminadas. Os loops dos serviços devem chamá-la periodicamente; ela não cria daemon adicional.

## Leases de recursos e operação

ResourceLeases aceita API/chat ou jobs-worker/generate/train e confere a conta PostgreSQL autenticada. TTL até 30 s, renovação a cada 5 s pelo supervisor de execução. Geração antiga não renova/libera dono novo. Expiração entra em recovering e não transfere posse até `release_after_confirmed_stop` ser chamado por supervisor que comprovou a parada; um timestamp expirado não prova que memória/CPU foi liberada. Supervisão/cancelamento do processo pesado serão integrados nos jobs/assistente, não simulados como existentes aqui.

HealthState/health_server distinguem liveness de dependências prontas. O loop chama tick mesmo durante backoff; readiness só passa após inicialização e dependências válidas. JsonFormatter/configure_logging usam campos permitidos e não serializam mensagem livre, request, senha ou traceback; códigos de motivo identificam o erro sem copiar exceção com credenciais.

## Testes

No host, na raiz:

```powershell
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m pytest -c packages/smartfan_common/pyproject.toml packages/smartfan_common/tests -q
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m mypy --config-file packages/smartfan_common/pyproject.toml packages/smartfan_common/src
tools/bootstrap/test-reliability.ps1
```

O último comando constrói a imagem, usa PostgreSQL/RabbitMQ reais e cria banco descartável com nome gerado. Só esse banco é removido ao final. A fila de prova AMQP é exclusiva e desaparece ao fechar conexão; nenhuma fila de negócio é drenada. Segredo Rabbit writer é montado somente no container de teste.

Evidência local: 138 testes do pacote e 11 integrações reais cobrem rollback, duplicata/conflito, quota, RLS, concorrência, receipt restrito, posse/renovação, retenção, banco inacessível, confirm→reentrega→dedupe, unroutable e publish de comando negado a writer. CI remoto, carga/chaos completo, supervisão dos jobs e aceite AIoT final continuam pendentes.
