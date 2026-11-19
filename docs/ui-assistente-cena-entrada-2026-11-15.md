# Encerramento da rodada de UI/UX — Assistente, Cena 3D e entrada — 15/11/2026

## Escopo
Assistente, Cena 3D e entrada, nessa ordem. Padrão visual já aprovado reutilizado por componentes Card/Badge, tipografia, cores, foco e controles existentes. Sem novas dependências, backend, contratos, permissões, serviços ou alterações em modelo, prompt, contexto enviado, recursos ou timeouts do LLM. Sem commit ou publicação remota.

## Assistente
- Seleção do equipamento, conversa com rolagem própria e formulário de envio. A área da conversa e a do formulário são reservadas pelo grid, sem sobreposição. VisualViewport é usado somente para acomodar o layout e trazer o formulário ao alcance quando o campo está focado e a área visível muda.
- Acompanhamento dos fragmentos somente enquanto a conversa estiver a até 32 px do fim. Ao consultar conteúdo anterior, não altera a posição; botão explícito permite retornar ao fim. Sem rolagem suave obrigatória.
- Estados de espera, carregamento do modelo, streaming, conclusão, cancelamento solicitado e erro vêm dos eventos existentes. Cancelamento é interrupção nesta interface; não se inventa confirmação de liberação do recurso no servidor.
- Aviso curto, uma vez na página: atendimento parcial por limitação de fidelidade semântica. O texto não executa comandos nem encerra alertas. A limitação anterior do 1B permanece aberta, sem nova avaliação de modelos.
- Dados estruturados em expansível separado da resposta gerada: saúde, RUL em horas de calendário, quantidade de alertas incluídos no resumo e métricas por alvo quando presentes. Números, unidades, versão e horários vêm exclusivamente do resumo recebido. Zero continua zero; valor ausente/status inválido não vira zero. Quantidade de alertas é identificada como pertencente ao resumo, que pode ser limitado.
- O resumo é uma fotografia do momento da resposta, com horário de geração e da leitura; não é reclassificado como telemetria atual nem completado com números do texto gerado. Referências técnicas originais disponíveis em detalhes. Métricas mantêm identificação de teste sintético e versão exata informada.
- safeMarkdown e parser SSE preservados. Histórico enviado, limites de tamanho, orçamento de contexto e requisição de chat mantidos. Nenhuma resposta fixa substitui a saída do modelo em produção.

## Cena 3D
- Seleção de equipamento, área da cena, legenda fora da visualização, lista por teclado/toque e painel do item. No celular, detalhes ficam abaixo da cena/lista. Botão Recentrar câmera foi movido para fora do canvas, sem mudar sua ação.
- IDs em detalhes. Valores, unidades, última leitura e previsão indisponível apresentados diretamente; saúde/RUL aplicadas somente ao equipamento. Gráficos e comandos existentes preservados, inclusive diferenciação entre compressor e ventilador.
- Fontes e cores dos rótulos do mini gráfico ajustadas para o padrão; nenhuma alteração no cálculo de séries, lacunas ou valores zero. Preferência de movimento reduzido, foco e mensagens sem dados preservados.
- Nenhuma alteração no renderizador, geometria, materiais, animações, cap de FPS ou ligação dos dados nesta etapa. A cena continua usando o store/WebSocket existente. REST permanece apenas no cadastro/faixas e nos controles operacionais existentes, sem alimentar geometria ou gráficos ao vivo.
- Horário da última leitura sem contador de idade mudando a cada meio segundo. Dados sem frescor mantêm a indicação de cena congelada. Ajuda, referências e estatísticas de renderização em expansíveis.

## Entrada
- Formulário direto, sem conteúdo promocional. Tipografia, cores, campos, botões e foco do padrão aprovado.
- Rótulos Usuário/Senha, autocomplete username/current-password, envio por Enter e limpeza da senha preservados. Usuário não sofre autocapitalização. Mensagens de sessão e de segurança continuam presentes.
- Mesmo signIn, destino seguro, contratos e limites de autenticação. Nenhuma tentativa real com senha inválida para validar a apresentação.

## Verificações realizadas
- Build Docker de produção com vue-tsc/Vite e lint aprovados. Oito testes unitários existentes de Markdown/SSE e estados da cena aprovados.
- Quatro cenários Playwright aprovados por execução dirigida: três de fixtures em 4,7 s após o ajuste do layout e cenário real de cena/navegação em execução posterior. Não executados os testes antigos que enviam perguntas ao Ollama, comandos reais ou pausam o simulador.
- Fixtures do Assistente: eventos meta queued/warming, delta, done, erro e cancelamento; zeros estruturados; métricas com versão; imagem remota impedida; nenhuma chamada ao backend de chat. Conteúdo identifica-se como simulado. A fidelidade semântica do LLM não foi avaliada.
- Rolagem: novos fragmentos acompanham o fim, preservam scrollTop ao consultar o início e voltam a acompanhar após ação explícita. Captura e verificação geométrica garantem que o formulário não cobre a conversa. Campo focado e viewport 390 × 390 simulam espaço reduzido por teclado; botão de envio permanece alcançável. Isso não equivale a teste com teclado físico/IME de um celular real.
- Cena real: equipamento ac_01 explicitamente selecionado, dados WebSocket recentes, oito componentes, seleção de Vibração por Enter, gráfico preenchido e camera-reset fora do canvas. Preferência de movimento reduzido exercitada com telemetria ainda recente; ângulo do ventilador permanece estável. Botões do ventilador não aparecem no painel do compressor e permanecem acessíveis no painel pertinente. Nenhum comando enviado.
- Falta de dados simulada apenas no navegador: proxy Playwright deixa de encaminhar frame.ready, mantendo o servidor/simulador ativos. Após o limite existente, aviso sem dados e cor de indisponibilidade; ângulo estável após confirmação nas estatísticas do renderizador. Encaminhamento retomado e estado recente recuperado. Não é uma falha real do simulador.
- A verificação de congelamento aguarda a estatística do renderizador porque sua publicação ocorre em cadência diferente do relógio de frescor da página. Não se alterou o limite de seis segundos. A primeira seleção do ensaio também foi explicitada para o equipamento monitorado, sem mudar a seleção padrão do produto.
- Entrada real: capturas vazias de formulário e login administrador por Enter. Fixture 429: mensagem de limite preservada, usuário mantido e senha limpa, sem tentativa malsucedida no servidor.
- Capturas em 1440 × 1000 e 390 × 844. Contraste DOM mínimo: Assistente 7,04:1, Cena recente 7,04:1 e entrada 6,10:1; fonte mínima 14 px. Cena sem dados simulada: 6,10:1. Rótulos de gráficos em canvas recebem fonte explícita de 14 px, não são cobertos pela medição DOM. A captura aguarda o título renderizado para impedir medição vazia antes da montagem da aplicação.
- Passagem breve pelas rotas: Visão geral, Dispositivos, Insights, Dados sintéticos, Treinamento, Mensageria, Auditoria, Usuários, Interfaces locais e Assistente, além da Cena 3D e entrada. Cabeçalhos, navegação e largura da página conferidos sem polimento das páginas anteriores; menu móvel exercitado no retorno da cena. Sem erros JavaScript observados no cenário real/navegação.

## Pendências e limites preservados
1. Assistente continua atendimento parcial por fidelidade semântica do modelo 1B. Modelo, prompt, contexto e recursos permanecem como antes; não se fez inferência real nesta rodada visual.
2. Aguardar avaliação visual das capturas. Nenhuma nova expansão ou rodada de polimento automática.
3. Celular/teclado e movimento reduzido exercitados por emulação Chromium, sem aparelho físico ou leitor de tela. Cancelamento no backend, restrições de autenticação e comandos reais não foram reensaiados; evidências anteriores continuam separadas.
4. Passagem de rotas não substitui ensaio funcional completo. Sem novo treinamento, geração massiva, carga, replay ou ensaio integrado prolongado. Extras existentes preservados; pendências opcionais anteriores não reabertas.

Rodada de UI/UX encerrada no escopo aprovado. Capturas do Assistente são fixtures; Cena 3D usa telemetria real, exceto [interrupção simulada](../evidence/ui-final/fixture-scene-stale.png). [Assistente desktop](../evidence/ui-final/fixture-assistant-desktop.png), [Assistente celular](../evidence/ui-final/fixture-assistant-mobile.png), [Cena desktop](../evidence/ui-final/scene-desktop.png), [Cena celular](../evidence/ui-final/scene-mobile.png), [Entrada desktop](../evidence/ui-final/entry-desktop.png), [Entrada celular](../evidence/ui-final/entry-mobile.png).
