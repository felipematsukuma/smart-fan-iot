# UI/UX — Dispositivos e Insights

Estado: direção visual aprovada, ajustes finais verificados e **etapa encerrada**. Dados sintéticos/Treinamento dependem da revisão da próxima proposta. Referência: [piloto encerrado](ui-piloto-2026-11-15.md). Sem commit ou publicação.

## Dispositivos

- Lista por nome/zona, com estados independentes de **Habilitado/Desabilitado** e telemetria. O cadastro é implícito na lista; o badge redundante Registrado foi removido no encerramento. Cadastro habilitado não implica telemetria recente nem aparelho ligado. O estado do compressor só aparece na lista com frame recente; registro histórico sem frame atual não é promovido a leitura ao vivo.
- Ações visíveis por papel: todos consultam; administrador cadastra, edita e habilita/desabilita; operador/administrador comandam pelo painel existente. Habilitação continua usando o mesmo PATCH com revisão esperada, sem prometer acionamento físico.
- Formulário prioriza nome/zona e o ID necessário à criação; perfil e faixas ficam em seção expansível. ID/zona permanecem imutáveis na edição. Validação próxima ao campo reutiliza restrições existentes, inclusive ordenação das faixas e limites de corrente/vibração. Nomes acessíveis dos campos permanecem estáveis quando há erro; descrições de erro são associadas por `aria-describedby`. Salvamento tem estado próprio e feedback, sem alterar o corpo dos contratos.
- IDs, revisão, inicialização, perfil, sensores, faixas e atuadores continuam disponíveis em detalhes. No desktop, histórico/detalhes ocupam a coluna ao lado dos comandos; no celular, ficam abaixo.
- Painel operacional reutiliza a apresentação aprovada de intenção aceita, execução validada e observação física. Termostato, agenda e histórico completo de comandos foram preservados em seções expansíveis.

## Insights

- Equipamento, saúde do compressor, RUL em horas, tendência e alertas têm prioridade. Versão da amostra, versões ativa/desejada, identificadores, comparação e regra preditiva permanecem em detalhes expansíveis.
- O filtro inicial de alertas é **Ativos**; filtros Todas/Encerrados e paginação continuam disponíveis. Falha de consulta não é apresentada como ausência de alertas e não encerra os registros conhecidos.
- Reutiliza `overviewFreshness`, com a mesma amostra/referência temporal e os seis segundos existentes, tanto no equipamento selecionado quanto na comparação. Usa `presentation` para as previsões, distinguindo aquecimento, inatividade, modelo indisponível, dados antigos e valores válidos iguais a zero. Falhas HTTP são exibidas separadamente dos estados estruturados da previsão.
- Histórico consultado explicitamente continua separado dos indicadores correntes, sem recalcular versões antigas nem sobrescrever saúde/RUL atuais.
- O gráfico de tendência mantém as lacunas e adiciona a apresentação aprovada somente pela opção `pilot`: fontes de 14 px, cores de contraste elevado, unidade no eixo e menos rótulos horizontais. O consumidor da cena 3D continua com a apresentação anterior.

## Reutilização e limites de escopo

Componentes locais Card, Badge, Alert e Button e painéis de controle/histórico existentes foram reutilizados. `task-page.css` é restrito às duas páginas, com texto base de 16 px e apoio de 14 px em rem, foco visível e alvos de toque. A raiz tipográfica e os estilos das demais páginas não foram redefinidos.

O conteúdo existente de termostato/agenda e histórico de comandos foi extraído para `ControlSettings.vue`, com tipos compartilhados em `control-types.ts`. Ações e requisições continuam no mesmo `ControlPanel.vue`; o consumidor legado mantém o mesmo conteúdo. A opção de gerenciamento só é habilitada nesta página. Não houve mudança de regra, permissão, endpoint ou mecanismo de segurança.

Nenhuma dependência, serviço, migração, alteração de backend, arquitetura ou LLM. O frontend foi reconstruído e atualizado isoladamente. Nenhum ajuste automático de outras páginas foi iniciado.

## Verificações

- Build de produção AIoT no Docker, verificação de tipos e ESLint passaram.
- Onze testes unitários focados de frescor, apresentação de comandos e previsões passaram.
- Cinco cenários Playwright passaram em 32,2 s: leitura real nas duas páginas/duas larguras; cadastro com validação/salvamento/revisão; estados e erros de Insights; papéis reais; progressão de comandos em fixture.
- Verificação final focal: leitura/capturas/contrastes e comandos passaram novamente em 19,4 s após o ajuste que mantém o frescor do equipamento selecionado independente da página visível da lista. O teste de comandos também emula a troca de página do cadastro, verificando que a observação e os controles permitidos continuam disponíveis para a seleção existente. Validação de cadastro e capturas já haviam sido repetidas após estabilizar os nomes acessíveis e os alvos de toque.
- Teclado: entrada por nome no formulário, validação/foco de erro, detalhes expansíveis por Enter, seleção nativa e regiões de tabela focáveis. Navegação móvel e interação por toque foram usadas no cenário real. Sem transbordamento horizontal global em 1440 e 390 px.
- Contas temporárias de visualizador/operador foram criadas e desativadas no encerramento dos testes. Não houve redefinição de senhas de contas originais. Requisições reais proibidas de cadastro e regra retornaram 403 para ambos; comando de visualizador retornou 403. A interface oculta ações administrativas e mantém campos de regras somente para leitura nesses papéis.
- Seletores dos testes anteriores afetados foram adaptados aos novos rótulos/áreas expansíveis; esses ensaios legados não foram executados integralmente nesta etapa. Não houve repetição do ensaio completo ou campanha de carga.

### Contraste medido nas capturas

Cálculo de luminância relativa sRGB sobre cores/fundos efetivamente computados no Chromium, convertendo OKLCH pelo canvas e compondo transparências dos ancestrais. Mesma metodologia do piloto; dados locais em `evidence/ui-devices-insights/*-contrast.json`. Textos desabilitados e visualmente ocultos são excluídos. O teste exige 4,5:1 para texto comum, 3:1 para grande e tamanho mínimo de 14 px.

| Página / largura | Textos avaliados | Menor tamanho | Menor contraste |
|---|---|---|---|
| Dispositivos desktop | 208 | 14 px | 5,36:1 |
| Dispositivos celular | 208 | 14 px | 5,36:1 |
| Insights desktop | 71 | 14 px | 7,04:1 |
| Insights celular | 71 | 14 px | 7,04:1 |

Eixos e legendas dos gráficos usam #475569 sobre branco (7,58:1); o traçado piloto usa #0f766e sobre branco (5,47:1). Estados têm rótulos textuais, além de cor. As medições cobrem os textos renderizados nas capturas; não constituem certificação completa da aplicação.

## Evidência real versus fixtures

**Observado com serviços reais:** as capturas usam cadastro/telemetria/previsões/alertas reais locais, com consulta do histórico e conteúdo carregado. Não houve comandos físicos nem alteração de regra/cadastro de equipamentos nesses cenários de captura.

**Fixtures explícitas:** gravações de cadastro e de termostato são interceptadas no navegador, validando corpo, revisão esperada, IDs/zona imutáveis, campos inválidos, conflito, salvamento pendente, habilitação e erros de consulta. Esses equipamentos não foram persistidos no PostgreSQL. Estados de previsão cobrem ausência, zero válido, aquecimento, inatividade, modelo indisponível, dados antigos, falha e recuperação; histórico com saúde 88 não substitui a saúde corrente igual a zero. Configuração mantém os mínimos de três previsões ruins e dez boas.

**Comandos em fixture:** intenção aceita não altera observação; estado `confirmed` sem referência validada não é mostrado como execução física; com a referência, a UI mostra execução, e só altera o estado observado quando a observação recebida muda. Não se afirma novo ensaio físico completo: o fluxo real anterior está documentado no piloto e os contratos/backend não mudaram.

**Limitações:** Chromium automatizado com eventos de toque, sem ensaio em telefone físico ou leitor de tela. Não houve nova validação integral do sistema, avaliação de LLM, treino, carga ou publicação. A direção visual foi aprovada; a próxima expansão aguarda revisão do responsável.

## Capturas

- [Dispositivos — desktop](../evidence/ui-devices-insights/devices-desktop.png)
- [Dispositivos — celular](../evidence/ui-devices-insights/devices-mobile.png)
- [Insights — desktop](../evidence/ui-devices-insights/insights-desktop.png)
- [Insights — celular](../evidence/ui-devices-insights/insights-mobile.png)

## Ajustes finais e encerramento

A API existente já retorna `reason_code` na consulta de alertas, embora o tipo/visualização frontend não o utilizasse. Agora o motivo aparece em uma descrição curta, com severidade e início preservados. IDs, versão, revisão e código bruto continuam em **Origem do alerta**.

O emissor atual grava `predictive_health_or_rul`: a interface traduz como **Saúde ou vida útil estimada abaixo do limite; condição específica não registrada.** Esse código não identifica qual condição individual disparou. A apresentação não reconstrói o motivo a partir da previsão ou regra atual. `health_low`, existente no contrato de exemplo, identifica saúde baixa; o código legado genérico `predictive_threshold` mantém a ausência de motivo específico explícita. Código ausente ou desconhecido mostra **Motivo não disponível no registro do alerta.** Nenhum LLM é usado, e o backend não foi alterado.

Os três blocos expansíveis principais de Insights têm menos preenchimento vertical quando fechados, mantendo seus conteúdos e o preenchimento de leitura ao abrir. O teste confirma altura fechada de até 60 px e área do summary de pelo menos 44 px, com abertura/fechamento por Enter e toque. Habilitação e telemetria de Dispositivos continuam distintas, sem o badge Registrado.

Validação somente dos comportamentos afetados: nove testes unitários do módulo de Insights passaram, incluindo motivos conhecidos, combinação ambígua, ausência e código não suportado. Dois testes de navegador passaram em 14,7 s: leitura/capturas reais e caso controlado de motivos/compactação/interação. Build de produção AIoT, tipos e ESLint passaram. Capturas principais acima atualizadas; a captura de motivos ausentes/desconhecidos em `evidence/ui-devices-insights/insights-reasons-fixture-mobile.png` é explicitamente uma fixture. O piloto não foi reaberto, não houve treino/geração de dados ou alterações no LLM, commit ou publicação. **Dispositivos e Insights encerrados; próxima etapa somente após revisão da proposta.**
