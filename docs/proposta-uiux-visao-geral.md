# Proposta única de UI/UX — navegação e Visão geral

**Estado: piloto visualmente aprovado e encerrado; expansão depende de nova revisão da proposta.** Registro e evidências em [UI piloto — 15/11/2026](ui-piloto-2026-11-15.md). O texto abaixo preserva a proposta de referência. Escopo do piloto: shell de navegação e Visão geral. Vue 3, Chart.js, componentes de controle, autorização e Three.js permanecem. O resultado da [avaliação do assistente](avaliacao-llm-2026-11-14.md) é independente desta proposta; não reabre os demais componentes.

## Fonte dos valores e autoridade operacional

Saúde, RUL, alertas e métricas são apresentados diretamente dos dados estruturados. A resposta do LLM fica identificada como texto gerado, com atendimento parcial e pendência de fidelidade semântica; nunca substitui números oficiais, decide comando ou determina encerramento de alerta.

| Informação | Fonte existente | Contexto que deve acompanhar |
|---|---|---|
| Saúde e RUL atuais | Insight no frame WS validado | % / horas de calendário, status da previsão, versão efetiva do regressor e horário da amostra |
| Alertas | Registros estruturados da API e transições WS | Severidade textual, equipamento, revisão da regra, versão/fonte da previsão e horários de abertura/encerramento |
| Métricas de avaliação | Relatório estruturado do registro de modelos | Modelo/versão e conjunto avaliado; MAE/RMSE em pontos ou horas conforme alvo; R² sem unidade; identificação de teste sintético e baseline |
| Estado físico e comandos | Telemetria observada e registros de intenção/ACK existentes | Equipamento/atuador, horário da observação, ação solicitada e situação da confirmação |

Na Visão geral, a versão/horário ficam em texto auxiliar ou detalhes acessíveis, sem ocultar a indisponibilidade. Métricas completas continuam em Treinamento; caso resumidas em outra tela, usam o mesmo registro estruturado e a versão correspondente. Encerramento de alertas continua exclusivamente nas regras/histerese existentes; comandos permanecem ações explícitas autorizadas do usuário.

## Linguagem visual e integração recomendada

Usar [shadcn/ui](https://github.com/shadcn-ui/ui) como referência de composição e [shadcn-vue](https://www.shadcn-vue.com/) para adoção incremental de componentes Vue. Não importar blocos completos de dashboard nem trocar gráficos. Os componentes selecionados ficam no repositório e passam a ser mantidos pelo projeto.

Recomendação: começar com Card, Button, Badge, Alert, Skeleton, Separator e Sheet somente para navegação móvel. O seletor de equipamento continua nativo, seguindo o padrão [Native Select](https://www.shadcn-vue.com/docs/components/native-select); não exige pesquisa, combobox ou popup customizado para um equipamento. A estrutura da [Sidebar](https://www.shadcn-vue.com/docs/components/sidebar) orienta grupos, conteúdo rolável e rodapé de sessão, sem importar todas as suas variantes/menus nesta etapa.

| Componente/padrão | Uso no piloto | Decisão de integração |
|---|---|---|
| Card | Indicadores, controle e gráficos | Componente visual pequeno; recebe os dados existentes |
| Button e Badge | Ações e rótulos de estado | Variantes consistentes; badge nunca substitui texto do estado |
| Alert | Dados antigos, erro e alerta preditivo | Mensagem persistente, com ícone/título/ação quando cabível |
| Skeleton | Primeira carga | Reservar espaço; não mostrar número fictício nem piscar a cada mensagem |
| Separator | Grupos do menu e seções | Separação discreta, sem excesso de caixas |
| Sheet | Menu lateral em telas estreitas | Reutilizar a primitiva acessível de diálogo, com Escape, foco contido e retorno ao botão de abertura |
| Select nativo | Equipamento e período já existente | Preservar comportamento do navegador/teclado |
| Gráficos existentes | Potência live e histórico | Preservar Chart.js, agregação, lacunas e metadados |
| Painel operacional existente | Intenções/ACK/estado observado | Reorganizar apresentação; não refazer comandos ou regras |

### Dependências propostas antes de implementar

O projeto atual não usa Tailwind/Reka. A [instalação Vite oficial](https://www.shadcn-vue.com/docs/installation/vite) requer Tailwind; a [instalação manual](https://www.shadcn-vue.com/docs/installation/manual) descreve os utilitários de composição. Planejar somente:

- `tailwindcss` e `@tailwindcss/vite` na ferramenta de build para os componentes adotados.
- `class-variance-authority` e `cn`, conforme os arquivos selecionados, para variantes e combinação de classes.
- `reka-ui` para o [Sheet/Dialog](https://www.shadcn-vue.com/docs/components/sheet), sem bibliotecas de formulários/tabelas no piloto.
- Reutilizar `lucide-vue-next` já instalado; adaptar imports dos componentes em vez de acrescentar uma segunda biblioteca de ícones.
- `tw-animate-css` somente se o Sheet selecionado realmente utilizar essas classes; não é motivo para adicionar animações ao restante da interface.
- CLI shadcn-vue apenas como ferramenta de seleção/cópia, não como serviço ou dependência do backend. Versões e transitivas devem ser conferidas e fixadas no lock na implementação autorizada.

**Custo relativo M; risco M concentrado em CSS/build.** Principal proteção: não substituir a folha atual nem aplicar reset global. Tailwind permite [omitir Preflight](https://tailwindcss.com/docs/preflight#disabling-preflight); importar apenas o necessário, limitar tokens visuais ao shell/piloto e conferir conflitos de classes. Não adicionar dark mode, fontes remotas, TanStack Table, novo sistema de formulários ou pacote de gráficos. Após o piloto aprovado, estender os mesmos tokens/componentes por página.

## Navegação geral

Mesmas rotas e permissões, agrupadas por tarefa:

| Grupo | Entradas | Acesso |
|---|---|---|
| Operação | Visão geral; Dispositivos; Cena 3D | Papéis existentes; ações continuam autorizadas na API |
| Análise | Insights; Assistente local | Papéis existentes; assistente mantém limitação de qualidade explícita |
| Laboratório | Dados sintéticos; Treinamento | Administrador |
| Administração | Mensageria; Auditoria; Usuários; Interfaces locais | Administrador |

Desktop: lateral de aproximadamente 240 px, rótulos completos, item atual com `aria-current`, conteúdo rolável e usuário/papel/Sair no rodapé. Sem submenu de ícones ou grupos recolhidos no piloto. Em telas estreitas, botão “Abrir navegação” na barra superior abre Sheet à esquerda; selecionar destino fecha o menu e leva foco ao conteúdo. A sidebar desktop não deve reduzir a largura útil em celular.

## Visão geral — ordem de leitura e operação

```text
Navegação lateral   Visão geral
                    [Equipamento: nome · ID · zona             v]
                    Estado do equipamento | última leitura e idade
                    Conexão ao vivo: conectada/reconectando/etc.

                    [Alerta prioritário / dados antigos / erro]

                    [Potência] [Temperatura interna] [Saúde] [RUL]

                    [Operação e comandos]  [Gráfico live de potência]
                    Estado observado      Fonte e horário
                    Intenção pendente     Lacunas preservadas
                    Confirmação física

                    Demais leituras: corrente, vibração, carcaça, exterior
                    [Ver Insights] [Detalhes do equipamento]

                    Histórico — período, energia e cobertura
                    [Gráfico histórico existente]
```

### Equipamento e estado atual

- Nome, ID e zona sempre visíveis; não depender do nome comercial para distinguir equipamentos.
- Se só houver um produtor recente, ele pode ser a seleção inicial. Depois de escolha explícita, não trocar silenciosamente para outro equipamento quando ele ficar offline.
- Distinguir conexão WS, presença do dispositivo e idade da última leitura. “Conectado” sozinho não significa “dados recentes”. Usar o limite de frescor existente, sem alterar regra de negócio.
- Mostrar modo automático/manual e intertravamento ao lado do estado dos atuadores, com texto claro.

### Indicadores e alertas prioritários

- Quatro indicadores primários: potência atual (W), temperatura interna (°C), saúde estimada (%) e RUL estimada (h de calendário).
- Corrente, vibração, carcaça e temperatura externa ficam numa faixa/tabela compacta com unidades, última amostra e estados; nenhum sensor é removido.
- Alerta crítico acima de atenção. Alertas persistem sem dados: exibir “alerta ativo; previsão atual indisponível”, não sugerir recuperação.
- Usar os dados/endpoints de alertas já existentes. Falha ao consultar alertas significa “situação não confirmada”, não “sem alertas”.
- Saúde/RUL indisponíveis mostram traço e motivo (aquecimento, inativo, dados insuficientes, modelo ausente), nunca zero. A versão pode ficar em detalhe contextual.

### Comando pendente versus estado confirmado

- Manter duas linhas distintas: **estado observado**, com fonte/horário, e **última intenção**, com pendente/confirmada/resultado desconhecido.
- O clique não muda o estado físico exibido. Confirmação vem do ACK existente e a mudança deve reaparecer nas leituras.
- Botões explícitos de ligar/desligar ventilador e liberar automático; evitar switch que aparente resposta instantânea.
- Durante comando pendente, mostrar ação solicitada e impedir duplicação conforme lógica existente. Timeout sem ACK informa resultado físico desconhecido; não anunciar estado OFF nem repetir automaticamente.
- Consequência de desligar ventilador (também interrompe compressor) fica próxima à ação. Proteção térmica e anticiclo continuam informados, sem atalhos que os burlem.
- Visualizador vê estado e explicação do papel; operador/admin usam os controles existentes. Termostato/agenda permanecem em detalhes, sem expandir escopo.

### Frescor, histórico e detalhes

| Situação | Apresentação |
|---|---|
| Primeira carga | Skeleton e rótulo de carregamento; controles aguardam observação válida |
| WS reconectando | Aviso de conexão separado da idade dos dados; histórico já obtido preservado |
| Amostra antiga | Rótulo “sem dados recentes”, instante da última fonte e comandos indisponíveis conforme regra existente |
| Erro REST | Mensagem específica e ação de repetir; preservar valores anteriores somente como históricos/desatualizados |
| Sem dispositivos | Estado vazio com acesso a Dispositivos conforme papel |
| Histórico vazio | “Nenhuma leitura neste período”; manter seletor de período |
| Cobertura parcial | Cobertura e limitação da energia visíveis; não preencher lacunas com zero |
| Previsão ausente | Motivo de indisponibilidade ao lado de saúde/RUL, separado de sensor offline |

Histórico segue seção própria, com período/cobertura/energia e gráfico existentes. Um atalho no topo leva à seção, sem misturar dados REST históricos com animação/live. “Detalhes” e “Ver Insights” preservam o equipamento escolhido; se a rota destino ainda não lê a seleção, adaptar somente esse vínculo de navegação, sem novo store genérico ou API.

## Estilo e acessibilidade

- Neutros no fundo/superfícies, borda discreta, sombras leves; acento atual da marca reservado a ações e foco. Âmbar/vermelho apenas para atenção/crítico; cinza para indisponível. Texto/ícone acompanham toda cor.
- Fonte de sistema, corpo 14–16 px, título 24 px e números principais 28–32 px; espaçamentos em escala 4/8/12/16/24, cartões com 16–24 px. Sem fontes remotas ou troca de identidade visual.
- Grid de quatro indicadores em desktop, dois em tablet e um em celular. Controles antes do gráfico na ordem do documento; empilhamento móvel mantém essa ordem e evita reordenação visual que confunda teclado.
- Foco visível, labels ligados aos inputs, alvos de toque confortáveis, navegação Tab/Shift+Tab e Escape; anúncios moderados para conclusão/falha de comando, sem ler cada amostra.
- Conferir contraste AA na implementação. Respeitar movimento reduzido e evitar animação decorativa.

## Execução após aprovação e aceite do piloto

1. Introduzir componentes/tokens mínimos e navegação responsiva; conferir que CSS não altera as páginas ainda não migradas.
2. Organizar a Visão geral com componentes existentes e vínculo da seleção; manter protocolos e permissões.
3. Validar teclado/menu móvel, loading/erro/vazio/stale, intenção versus ACK, histórico e ausência de overflow em 390/768/1440 px. Reutilizar testes focados; não repetir o ensaio completo para cada ajuste visual.
4. Apresentar o piloto para revisão antes de usá-lo como padrão nas demais páginas. Um smoke da cena verifica apenas que a largura/navegação novas não quebram o canvas; Three.js não é refeito.

Critério: operador identifica equipamento, atualidade da amostra, alerta e estado físico antes de comandar; compreende o que está pendente; chega ao histórico/detalhes sem perder o contexto. Sem regressão nas permissões, gráficos ou confirmação física. **Aguardar aprovação antes de qualquer mudança visual.**
