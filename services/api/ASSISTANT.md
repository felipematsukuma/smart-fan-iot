# M16 — Assistente local com streaming

[V] Modelo efetivo: **llama3.2:1b-instruct-q4_K_M**, digest fixado em
[local_llm.py](../../packages/smartfan_common/src/smartfan_common/local_llm.py).
O candidato 3B excedeu 30 s em duas tentativas; o 1B padrão Q8 também excedeu
em repetição a frio. O 1B Q4 previsto na alternativa da arquitetura foi selecionado
após ensaio real. Modelos anteriores permanecem no cache, sem uso pelo chat.
Imagem Ollama CPU continua fixada no Compose; nunca há fallback em nuvem.

## Contexto e fronteira HTTP

[V] `POST /api/v1/assistant/chat` exige JWT e dispositivo autorizado. Aceita pergunta
até 2.000 caracteres e até dois turnos limitados; o orçamento de contexto pode
recusar pergunta menor que esse teto. Resposta SSE `meta/delta/done/error` via fetch
com Authorization, sem token na URL. Heartbeat 5 s, primeiro token até 30 s e total
90 s incluindo espera; erro no meio do stream termina com evento `error`.

[V] [Contexto](./assistant_context.py) contém identidade/UTC, fonte/idade/boot,
saúde percentual/RUL em horas de calendário quando válidas, IDs de até três alertas
e médias/máximos/cobertura dos últimos cinco minutos do bucket live. Não transmite
séries, nomes livres, rótulos do laboratório, credenciais ou SQL. Ausência e fonte
antiga ficam explícitas; não há atualização artificial de timestamp. Resumo até
1.200 bytes UTF-8 e mensagens até 1.700 bytes: teto conservador de tokens de entrada,
reservando template e 256 tokens de saída no contexto de 2.048. Turnos são omitidos
quando não cabem; nomes/unidades são explícitos para reduzir confusão semântica.

[V] O navegador apresenta os dados usados. Markdown-it 15.0.3 renderiza Markdown
com HTML/imagens desabilitados, sem plugins; links somente http/https e
noopener/noreferrer. Parser SSE trata UTF-8/eventos divididos e limites de tamanho.
Nenhuma saída vira comando. Pergunta/resposta não ficam transcritas na auditoria:
ator, fontes, modelo, hashes, duração, tokens e resultado são persistidos.

## Concorrência e recuperação

[V] [Supervisor do chat](./assistant.py): uma geração e duas esperas, com limites
persistidos 5/usuário/minuto e 20 globais/10 minutos sob lock PostgreSQL. Reinício
não apaga cotas. Jobs pesados recusam chat com 503; lease heavy compartilhado impede
geração e treino simultâneos. A espera local só libera o próximo após cleanup.

[V] API mantém flock em inode persistente de volume exclusivo; novo processo não
recupera um anterior ainda vivo. Lease TTL 30 s/renovação 5 s; falha de renovação
ou sessão cancela upstream. Cancelamento fecha stream e solicita unload; somente
`/api/ps` vazio prova parada na interrupção. Sem prova, mantém bloqueio/recovery.
Finalização normal exige `done` do Ollama e fence SQL antes de sucesso auditado;
mantém modelo quente por 10 minutos. Jobs descarregam a mesma constante de modelo
e confirmam memória liberada antes de iniciar seu filho.

[V] `ollama-init` agora só baixa/verifica digest. Carregamento ocorre na primeira
conversa, sob lease, evitando warmup paralelo a job. Timeout/cancelamento nunca
entrega texto de template como se fosse resposta do LLM.

## Evidência e limites

[V] 224 testes Python e 244 Vitest passaram; lint/tipos/formatação/build aprovados.
24 integrações reais de API/laboratório/assistente incluem seis casos do chat:
permissões, rate limit persistido/global, fila limitada, cancelamento, headers
abandonados e prova de parada recusada. Fixtures isolam protocolo, não qualidade.
Playwright também chamou o Ollama real, leu fragmentos, mostrou fontes e cancelou
uma segunda resposta: lease liberado e modelo ausente de `/api/ps`.

[V] Q4 no navegador: primeiro fragmento **12,369 s**, conclusão **15,807 s**.
Outra execução com modelo descarregado: primeiro fragmento **5,192 s** na API;
execução quente subsequente **2,318 s**. São amostras, não p95.
Revisão visual detectou confusão de RUL com precisão na versão inicial do prompt;
nomes/unidades e instruções foram corrigidos, com repetição real. Isso não garante
fidelidade de toda resposta: modelo pequeno ainda pode interpretar dados de forma
inadequada; métricas/alertas oficiais continuam sendo os estruturados do sistema.

[N] Partição PG/processo congelado, carga prolongada, memória total/p95 e concorrência
com filho pesado em execução são aceite integrado M18. CI remoto/scan são M17.
Ver [test-assistant.ps1](../../tools/bootstrap/test-assistant.ps1),
[API Ollama](https://docs.ollama.com/api/chat),
[modelo Q4](https://ollama.com/library/llama3.2:1b-instruct-q4_K_M) e
[segurança Markdown-it](https://github.com/markdown-it/markdown-it/blob/master/docs/safety.md).
