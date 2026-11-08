# ADR 001 — Manter Vue 3

Status: decisão proposta na arquitetura documental; não implementa mudanças.

Contexto: [V] Vue, TypeScript e Vite estão declarados em [package.json:20](../../web-smart-fan-iot/frontend/package.json#L20); há componentes e testes do dashboard.

Decisão: manter Vue 3, acrescentar Vue Router e store reativo nativo; lazy loading para páginas pesadas.

Alternativas: React exigiria reescrever UI sem resolver requisito adicional; Pinia só será considerada se o store nativo ficar difícil de manter.

Consequências: reaproveitar componentes/testes; separar App.vue em páginas; autorização permanece na API, independentemente dos guards.

Se remover Vue sem substituto, a interface deixa de existir; trocar framework agora aumenta trabalho sem benefício exigido.

Ver [arquitetura, seção 9](../plano/03-arquitetura.md#9-frontend-tempo-real-e-cena-3d).
