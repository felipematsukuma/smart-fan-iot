# Segundo diagnóstico: redimensionamento do assistente

## Falha observada

A [tentativa 2 do CI](https://github.com/felipematsukuma/smart-fan-iot/actions/runs/44805523148/attempts/2), no commit `29da2bc`, aprovou 85 integrações e 44 testes de navegador, mas reprovou o teste móvel do assistente: a conversa foi medida em 834,296875 px e o formulário em 566,9375 px. Três ensaios opt-in não foram executados. A tentativa anterior havia passado.

## Causa reproduzida

O teste lia os retângulos em duas chamadas ao navegador imediatamente após `setViewportSize`. O evento `visualViewport.resize` atualiza assincronamente a altura do workbench. As leituras podiam pertencer a layouts diferentes.

Em cinco execuções diagnósticas locais, com a conversa simulada identificada, a medição atômica imediatamente após o resize encontrou conversa/formulário em 790,828125/801,328125 px; após o ajuste, 556,4375/566,9375 px. A separação permaneceu 10,5 px nos dois momentos. A altura do workbench mudou de 736,062 para 501,672 px. Isso reproduz a mistura temporal responsável pela falsa sobreposição; não foi observada sobreposição persistente neste cenário.

## Correção delimitada

No [teste existente](../web-smart-fan-iot/frontend/e2e/final-ui.spec.ts), ambos os retângulos são lidos na mesma avaliação síncrona. A asserção aguarda, dentro do prazo padrão existente, ausência de sobreposição e formulário inteiramente dentro do viewport. Não usa pausa fixa, retry do teste, tolerância geométrica ou mudança de timeout. Uma sobreposição persistente continua reprovando.

Nenhuma alteração na aplicação, CSS, backend, modelo ou contexto do assistente. O arquivo diagnóstico temporário foi removido.

## Validação

- Teste corrigido: cinco execuções consecutivas aprovadas em 13,3 s, com fixture de resposta e autenticação real.
- `npx playwright test final-ui.spec.ts assistant.spec.ts`: cinco casos aprovados em 35,0 s, incluindo chat real via Ollama e cena com telemetria real; os casos simulados permanecem identificados como fixtures. O resultado remoto deve ser consultado na execução do commit correspondente.
- A aprovação funcional do chat não comprova fidelidade semântica: o assistente permanece com atendimento parcial.
