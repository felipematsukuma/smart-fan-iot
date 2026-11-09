# M10 — Mensageria, prévias e reprocessamento restrito

| Aspecto | Evidência e limite |
|---|---|
| Contadores | [V] Backend chama somente `GET /api/queues/%2Fsmartfan`; usuário `api-monitor`, tag monitoring e configure/write/read vazios. Nenhuma credencial sai na resposta ou URL do navegador |
| Snapshot | [V] Oito filas conhecidas: prontas, sem ACK, consumidores, taxas, tipo e durabilidade. Timeout 3 s, corpo máximo 2 MiB, cache 2 s; UI consulta a cada 5 s e identifica contadores antigos quando falha |
| DLQ | [V] Abrir a tela não executa get/ack/purge. Prévia vem do journal PostgreSQL, máximo 200 falhas por serviço na view, paginação de 50/máximo 100; UI limita 200 linhas por consulta expandida. Journal e contador da DLQ podem divergir |
| Redação | [V] Payload só é interpretado internamente. Resposta permite tipo/produtor/UTC validados e dispositivo cadastrado. Payload inválido é omitido; não retorna bytes, base64, rota arbitrária, credenciais, hash original ou corpo livre |
| Acesso | [V] Tela e três rotas exigem administrador. Visualizador/operador recebem 403 também no servidor. API não recebe senha do usuário bootstrap nem Docker socket |
| Replay | [V] Função SQL SECURITY DEFINER com search_path fixo e EXECUTE exclusivo da API reseta somente inbox terminal **writer**, validando fonte original, hash, rota, dispositivo/zona e tipo telemetry.sampled. Não muda bytes/ID/horário e não publica em nome de outro serviço |
| Cercas | [V] Incrementa geração, invalida lease anterior, zera tentativas e mantém falha original. `request_id` UUID torna a solicitação idempotente; máximo três por falha, intervalo mínimo 30 s. Auditoria atômica com reset |
| Comandos | [V] Não são elegíveis, inclusive vencidos. Retentar operação física exige nova intenção explícita pelo fluxo M09; nunca estender validade de comando antigo |

## Rotas

- `GET /api/v1/messaging`: snapshot da API de gerenciamento.
- `GET /api/v1/messaging/failures?before={uuid}&limit=50`: prévias do journal.
- `POST /api/v1/messaging/failures/{uuid}/replay`, corpo `{"request_id":"UUID"}`:
  202 requested/already_requested ou 409 não elegível/conflito/limite.

Falhas sem inbox correspondente, de origem inválida ou de outros consumidores são
somente consultáveis neste módulo. A função com privilégio não concede à API update
direto em linhas de outro proprietário; a RLS continua filtrando essas linhas.

## Evidências executadas

[V] 193 testes Python, 231 Vitest, 31 integrações e sete Playwright passaram; lint,
tipos, formatação e build passaram. Aviso de chunk do validador permanece no M07.

[V] Teste de replay escreve no Influx real e interrompe antes de concluir no PG;
reprocessar mantém um ponto, rejeita conclusão com lease antigo, confirma o worker
e preserva falha/auditoria. Testes verificam prévia com corpo/rota contendo segredo
sintético, autorização por papel, comando não elegível e monitor sem acesso ao get
da DLQ. O teste de permissão usa conta sem read e confirma recusa 401/403.

[V] No navegador com Compose real: parar writer mostra consumidor 1→0 e fila pronta
crescer; reiniciar mostra consumidor 1 e fila esvaziar. Abrir/atualizar a tela não
reduz a DLQ. O teste restaura o serviço em finally; não executar durante demonstração.

[test-messaging.ps1](../../tools/bootstrap/test-messaging.ps1) reproduz os ensaios.
Testes PG/Influx usam banco/bucket descartáveis, sem truncar dados do projeto.

[N] Recuperação de falhas de treino/geração/inferência depende de seus próprios
estados e supervisores (M11–M13); não ampliar replay genérico. Retenção operacional,
backups, carga integrada, scan e execução remota do CI permanecem em M17/M18.
