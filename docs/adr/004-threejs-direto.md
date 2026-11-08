# ADR 004 — Three.js direto

Status: decisão proposta; cena ainda não existe.

Contexto: gêmeo digital procedural simples com poucos objetos e estado recebido por WebSocket.

Decisão: Three.js direto integrado ao ciclo de vida Vue; store/buffer, objetos persistentes e requestAnimationFrame para animação condicionada a dados frescos.

Alternativas: TresJS adiciona abstração dispensável no mínimo; Babylon.js é permitido, mas não traz vantagem necessária para a cena definida.

Consequências: controlar explicitamente recursos, resize, acessibilidade e descarte; congelar animação em ausência de dados, sem simulação autônoma no browser.

Se remover a biblioteca 3D sem equivalente, perde-se requisito obrigatório; não adicionar framework 3D redundante.

Ver [arquitetura, seção 9](../plano/03-arquitetura.md#9-frontend-tempo-real-e-cena-3d).
