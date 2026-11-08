# ADR 008 — SSE para o assistente, WebSocket para live

Status: decisão proposta; streaming ainda não implementado.

Contexto: assistente é requisição autenticada com resposta incremental; telemetria exige canal contínuo independente.

Decisão: POST via fetch com Authorization e stream SSE meta/delta/done/error; WS permanece para dados operacionais.

Alternativas: compartilhar WS mistura cancelamento/chat com eventos de máquina; EventSource nativo não oferece o mesmo POST/header; polling perde streaming útil.

Consequências: configurar proxy sem buffering, timeout e cancelamento upstream; parser SSE trata chunks partidos e desconexão; sem token na URL.

LLM é local, resumo montado na API, Markdown sem HTML e sem ferramentas de comando; chat indisponível durante job pesado conforme lease de recursos.

Se remover SSE, é necessário outro transporte incremental; não adicionar novo broker ou servidor só para chat.

Ver [arquitetura, seção 11](../plano/03-arquitetura.md#11-assistente-local-e-orçamento-compartilhado).
