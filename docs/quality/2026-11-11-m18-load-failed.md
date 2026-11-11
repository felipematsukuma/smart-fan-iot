# M18 — Carga que identificou atraso de publicação

[V] O ensaio `e69651c0bc9e440e8fe9cb15cda3c50b`, instrumentado no commit `3d94758`, usou dez simuladores autenticados, intervalo solicitado de 0,4 s e duração configurada de 600 s. Não foi aprovado. O [diagnóstico estruturado](2026-11-11-m18-load-failed.json) não contém credenciais nem payloads.

| Evidência executada | Resultado |
|---|---|
| Gateway PostgreSQL | 14.782 eventos de telemetria únicos aceitos no conjunto do ensaio, incluindo partida; não equivale à taxa sustentada aprovada |
| Journal após recuperação | 2.876 publicações gateway ainda pending depois do limite de drenagem de 120 s |
| RabbitMQ | Filas de trabalho vazias durante observações; isso não prova que o journal anterior ao broker escoou |
| Tempo real e navegador | Zero frames atuais no coletor; o teste do DOM falhou por ausência de amostra atual |
| Proteção de frescor | Mensagens antigas não foram transformadas em previsões atuais para satisfazer o teste |
| Quota atual | Consulta de soma de pendentes medida em 2,828 ms, com o papel gateway |
| Publicação real isolada | 40 mensagens já aceitas publicadas com confirmação; média claim 5,506 ms, confirmação AMQP 9,690 ms e conclusão PostgreSQL 5,297 ms |

[I] As operações sequenciais de claim/conclusão e a espera fixa entre ciclos contribuem para o atraso. A próxima alteração será verificada com fencing, confirmação e recuperação preservados; não há justificativa para remover garantias de entrega ou aumentar os limites de latência.

[N] NF01–NF03 continuam sem aprovação nessa carga. A capacidade só será declarada após nova execução sustentada com reconciliação dos journals, InfluxDB, eventos derivados e entrega real ao navegador. Os serviços da cópia foram encerrados e os dados originais preservados.
