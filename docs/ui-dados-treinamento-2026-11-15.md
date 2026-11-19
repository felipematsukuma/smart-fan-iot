# Dados sintéticos e Treinamento — UI/UX — 15/11/2026

## Escopo
Implementação visual das duas páginas, nesta ordem, com o padrão aprovado do piloto, Dispositivos e Insights. Sem mudanças no backend, dependências, regras de geração/treino, LLM, commits ou publicação. Aguardando avaliação visual antes de outra expansão.

## Mudanças
- Dados sintéticos: equipamentos, dias, intervalo de amostragem, semente e percentual de falhas em destaque. Conversão de percentual para a fração existente no contrato; limites preservados. Estimativa em vetores e canais por vetor, separada dos vetores efetivamente gerados. Um vetor é uma linha por equipamento/instante, podendo conter canais ausentes; não corresponde a uma leitura escalar nem garante completude de todos os canais.
- Outros parâmetros, sensores e modos de falha em opções avançadas. Validação nativa próxima aos campos, abertura do expansível quando houver campo inválido e preservação de valores após erro.
- Jobs com estado, contadores reais e cancelamento solicitado separado do estado cancelado. Sem ETA inventado. O backend fornece estados gerais, não uma descrição detalhada da etapa interna. No treino, progresso percentual é apresentado somente a partir dos contadores fornecidos.
- Treinamento: datasets completos oferecidos pelo contrato existente; essa condição não garante os requisitos estatísticos que só são conferidos pelo treino. Configuração técnica recolhida. Métricas do modelo e baseline por alvo, teste reservado, quantidade de amostras, unidades e benchmark independente. R² sem unidade. Valores ausentes continuam indisponíveis, nunca zero substituto.
- Modelo concluído, aprovado, selecionado para ativação e ativo continuam distintos. Critérios e bloqueios vêm dos registros estruturados existentes; tradução dos códigos conhecidos somente na apresentação. Promoção explícita preservada, sem ativação automática pela conclusão do treino.
- Gráficos Chart.js mantidos, fontes de eixos/legenda de 14 px e tabelas alternativas acessíveis. Detalhes técnicos, limitações e model card em expansíveis. Listas com rolagem própria e região focável; tabelas podem exigir rolagem horizontal no celular.

## Verificações reais
- Build de produção e typecheck concluídos; lint sem erros.
- Vitest: quatro testes de autenticação aprovados.
- Playwright: consultas reais com login administrador, defaults, jobs, datasets, amostra e relatórios de modelos já existentes; sem POST de geração, treino, promoção ou cancelamento real.
- Capturas em 1440 × 1000 e 390 × 844; ausência de transbordamento horizontal da página, gráficos preenchidos e alternância de alvo. Expansíveis operados por Enter e toque emulado. Sem erros JavaScript observados nesse cenário.
- Contrastes dos textos visíveis: mínimo 6,10:1 em ambas as páginas e resoluções; tamanho mínimo 14 px. Registros JSON junto às capturas. Verificador corrigido para excluir conteúdo realmente invisível de details fechados usando checkVisibility; a primeira medição contava esses elementos. Textos em canvas recebem cores/fontes explícitas, mas não são medidos pelo verificador DOM.

## Fixtures, não ensaio de processamento
- Erro de validação local impede envio; erro HTTP preserva campos preenchidos.
- Percentual de falhas de 25% enviado como failure_fraction 0.25.
- Geração em execução, cancelamento solicitado com botão desabilitado e cancelamento confirmado por consulta posterior.
- Treino em 35%, erro de envio, retenção de semente e cancelamento; versão ativa anterior mantida.
- Papéis visualizador e operador simulados na resposta de identidade: links administrativos ocultos. Não equivale a novo teste de autorização do backend; contratos e guards existentes foram preservados.
- Cinco cenários Playwright aprovados. Não foram executados os testes antigos de geração/treino que criam massa e modelos reais.

## Limitações
Sem geração, treino ou promoção reais nesta etapa visual. Sem novo ensaio integrado, carga ou avaliação do LLM. Celular validado em Chromium com viewport e toque emulados, sem aparelho físico ou ensaio com leitor de tela. Detalhamento de etapas e estimativa de término não estão disponíveis no contrato. Capturas e relatórios em [evidências](../evidence/ui-data-training/).


## Refinamento final aprovado em escopo — 15/11/2026
- Ações curtas “Ver geração” e “Ver modelo”; IDs abreviados na lista, completos em detalhes com cópia por Clipboard API e feedback de sucesso/erro. Valores completos preservados nos contratos. Dataset apresentado por última atualização do job, volume e ID abreviado; data exibida não é data sintética nem tempo de criação inventado.
- Listas em cartões compactos no celular e tabelas no desktop. Tipo conhecido generate apresentado como Geração. Estado, volume/aprovação e ação permanecem visíveis sem quebra artificial de palavras.
- Métricas principais do teste reservado em blocos móveis para modelo e baseline, com MAE/RMSE e unidades, R² sem unidade e contexto do teste. Sem rolagem horizontal para esses valores; expansíveis técnicos e outras tabelas detalhadas continuam acessíveis.
- Nomes de atributos traduzidos apenas para apresentação. Nomes técnicos e todos os resultados mantidos na tabela. Cinco maiores importâncias no gráfico móvel, todas no desktop, sem recalcular valores. Rótulos multilinha, fontes de 14 px e altura por conteúdo.
- Estado concluído sem repetir “treino concluído”. Aprovação, seleção e ativação preservadas. Resumo “Seleção aplicada” somente quando versão e revisão desejadas coincidem com as confirmadas; valores completos de ambos continuam nos detalhes.
- Verificação final: build de produção com vue-tsc e Vite aprovado; lint aprovado; três testes unitários de apresentação aprovados; um cenário Playwright de consultas reais aprovado em 4,6 s, com desktop/celular, Enter, toque emulado, cópia real e leitura da área de transferência, ausência de transbordamento das listas/métricas, gráficos preenchidos e capturas revisadas visualmente. Contraste mínimo DOM 6,10:1 e fonte mínima 14 px nas quatro capturas.
- Na inspeção visual foram corrigidas a precedência de largura das tabelas móveis e a largura das legendas/captions após mudança para blocos. Não basta ausência de overflow: o teste também limita altura da caption para impedir texto disposto verticalmente.
- Não houve geração, treino, promoção ou cancelamento real. Os cinco cenários/ quatro testes de autenticação da implementação anterior permanecem evidência anterior; nesta rodada executaram-se somente as verificações afetadas indicadas acima. Sem novo ensaio de permissões, aparelho físico ou leitor de tela.
- Etapa encerrada. Proposta seguinte, ainda não implementada: Mensageria e Auditoria, com prioridade a estados, ocorrências recentes, filtros, detalhes acessíveis e permissões existentes. Aguardar revisão antes de executar.
