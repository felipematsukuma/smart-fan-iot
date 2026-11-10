# M15 — Cena 3D do ar-condicionado

[V] Three.js 0.187.0 direto, sem framework adicional, conforme
[ADR 004](../../../../../docs/adr/004-threejs-direto.md). Remover a biblioteca
elimina a cena exigida; não há backend Node nem assets/modelos externos. Import
fica na rota lazy `/cena-3d`; Vue e Chart.js existentes atendem UI e minigráfico.

## Dados e interação

[V] [Model](./model.ts) mapeia o ID do equipamento, cinco sensores e dois atuadores
recebidos no escopo autorizado WS. Leituras e previsões vêm exclusivamente dos
frames; REST fornece só faixas cadastrais e o painel operacional separado.
Cadastro sem amostra é representado sem valor inventado. Seleção funciona por
raycast e por oito botões textuais navegáveis pelo teclado.

[V] [Renderer](./renderer.ts) cria geometria uma vez por dispositivo selecionado.
Frame troca apenas buffer; RAF limitado a 30 FPS aplica transforms, cores e uniforms.
Temperaturas interna/externa comandam dois mapas de cor do ambiente; falta de
sensor fica cinza. Marcadores usam faixas cadastradas; compressor usa saúde válida.
Vibração controla tremor e estado observado do ventilador habilita rotação
ilustrativa, explicitamente sem alegar RPM medido. Nenhum timer prevê sensores.

[V] Timestamp com idade >6 s, dispositivo desativado ou boot diferente impede
aplicação/movimento. Última pose e cores ficam congeladas e UI oculta números
atuais. Câmera continua controlável pelo usuário. `prefers-reduced-motion` desliga
movimento físico, preservando seleção e atualização dos dados. Sem WebGL/contexto
perdido há aviso e alternativa textual. ResizeObserver redimensiona canvas/câmera;
unmount remove RAF, controles, observer, listeners, geometrias e materiais.

## Orçamento e verificação

[V] Pixel ratio ≤1,5; sem sombras, texturas, pós-processamento ou alocação geométrica
por amostra. No navegador local automatizado: **30 FPS, 44 chamadas de desenho,
2.052 triângulos e 44 geometrias**, abaixo dos limites 100 chamadas/50 mil triângulos.
Métricas descrevem esse ensaio; não certificam todos os dispositivos ou latência
fim a fim. Contagem geométrica permaneceu estável durante a parada do simulador.

[V] 241 Vitest aprovados, incluindo identidade/ordem/frescor/cores e estados sem
previsão. Playwright usa comando Web real com ACK, verifica rotação, seleciona
sensor por teclado, exercita movimento reduzido, para o simulador e confere ângulo
congelado. Verifica largura de 390 px após o ResizeObserver estabilizar e navega
para fora da cena. Screenshots desktop/celular revisados localmente.

Comandos no frontend: `npm run typecheck`, `npm run lint`, `npm run test`,
`npm run format:check`, `npx playwright test e2e/scene.spec.ts`.
[Test runner](../../../../../tools/bootstrap/test-scene.ps1) prepara Compose.
[Documentação Three.js](https://threejs.org/docs/pages/WebGLRenderer) fundamenta
pixel ratio/descarte e [OrbitControls](https://threejs.org/docs/pages/OrbitControls)
os controles de câmera.

[N] Carga integrada prolongada, cenário guiado de falha e scan/CI remoto são
M17/M18. Não há modelo físico/CFD no navegador nem teste em equipamento real.
