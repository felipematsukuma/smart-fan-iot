# Fechamento funcional AIoT — 14/11/2026

Escopo aprovado: três blocos, um equipamento, sem commits/merge/push, sem redesign e sem carga ampliada. Estado de trabalho sobre `ed21817`; alterações ainda não commitadas.

## Bloco 1 — Assistente e Mensageria

- O resumo do assistente consulta MAE/RMSE/R² de teste sintético da versão da previsão, não do último candidato. Métricas não finitas, versão divergente ou registro ausente resultam em `unavailable`. Arquitetura é texto estático da aplicação; nenhum dado livre do dispositivo vira instrução ou ferramenta.
- A Mensageria mostra somente IDs, tipo, produtor, dispositivo, instante e fila dos eventos já validados e aceitos pelo consumidor API. Limite de 100 entradas em memória e cinco minutos, com expiração ao consultar e descarte no reinício. Nenhum payload, credencial, leitura extra das filas ou nova assinatura AMQP. É uma amostra de `q.events.api`, não captura de todas as filas.
- Observado nesta execução: cinco testes unitários focados passaram; 14 integrações PostgreSQL reais de assistente/Mensageria/WS passaram; tipos frontend, Ruff e mypy dos módulos alterados passaram. Consulta real ao registro encontrou métricas da versão `mdl_edcc5fb6df9e49879f028ab2e9c7f178`; prompt básico com 1.296 bytes, dentro do teto existente de 1.700.
- Limite: a resposta textual do modelo pequeno não constitui validação de diagnóstico. Ensaio real do chat com o contexto ampliado será registrado no bloco 3.

## Bloco 2 — Controles, interfaces locais e cena

Implementado: controle na Visão geral; página administrativa de links RabbitMQ/Influx em loopback; controle por atuador e minigráfico binário; saúde/RUL e tendência apenas no equipamento; instâncias nas aletas, portas/tubulações conectadas e materiais cinza sem dados. Reutiliza painel, autorização e contratos existentes. Alertas recebidos por AMQP são preservados no snapshot existente e enviados pelo WS com instante original. Nenhum novo serviço/dependência ou migration.

Observado: 15 testes Vitest focados passaram; tipos e ESLint das áreas alteradas passaram; 14 integrações reais passaram após a alteração do snapshot, incluindo reconexão com alerta e prévias. Um teste real de treino/ativação após aprovação passou em banco descartável. Dois testes de navegador passaram com Ollama real, comando/ACK, seleção por teclado, redução de movimento e parada/retorno do simulador. Cena: 30 FPS, 36 chamadas, 3.116 triângulos e 36 geometrias; screenshot inspecionado. Esses números são observações locais, não p95/carga.

As primeiras tentativas de navegador não passaram: contas operador/visualizador não aceitam mais as senhas iniciais; depois foi identificada seleção automática de outro cadastro (`09`) sem produtor live. Repetição explícita com conta administrativa válida e seleção `ac_01` passou. Não houve redefinição de senha, exclusão de cadastro ou ocultação de falha. Testes focados agora aceitam usuário/arquivo privado de senha e selecionam o equipamento explicitamente. O ensaio contínuo usa contas aleatórias de prova e as desativa ao terminar.

## Bloco 3 — Documentação e ensaio contínuo

README atualizado e cenário [documentado](cenario-demo.md). Duas execuções contínuas concluídas; revisão arquitetural **não encerrada**, por reprovação semântica do LLM detalhada abaixo. As evidências anteriores de M17/M18 permanecem históricas; não equivalem ao resultado desta execução.

### Primeira execução contínua e revisão textual

Execução `1794698776380`, 23:26:16–23:33:03 UTC: 12 passos funcionais passaram em 6,8 min; 191 frames. Dados sintéticos/treino disparados pela UI, pausa/drenagem do writer, três papéis com contas de prova, comandos físicos, consultas aos bancos, falha, nova transição e cor da cena observados. Saúde 100→87,95%, RUL 27,07→24,18 h; corrente 4,7352→5,3158 A, vibração 1,4145→3,3592 mm/s, carcaça 46,633→64,636 °C. Regra anterior restaurada e contas de prova desativadas; spool original preservado.

O teste inicialmente validava streaming e presença dos dados, mas a revisão do texto revelou confusão do LLM: RUL tratada como atualização de software e saúde atribuída ao modelo. Portanto, essa execução **não aprova a fidelidade da resposta do assistente**. Perguntas focadas posteriores também expuseram fórmulas incorretas e números sem previsão válida. Não foram ocultadas nem tratadas como diagnóstico real.

Correção limitada ao contexto/prompt: seleção fixa por assunto, definições explícitas, nomes de condição do compressor em português e exclusão de agregados de sensores em perguntas só sobre RUL/alertas. Seis unitários de contexto/prévias passaram, incluindo separação entre métricas e condição física. A execução final repetiu o fluxo e três perguntas distintas (alerta/RUL, métricas e arquitetura). Não houve troca de modelo, aumento de recursos/timeouts ou redução das proteções.

### Repetição final — funcionamento aprovado, texto reprovado

Execução `1794699656555`, 23:40:56–23:48:12 UTC, 7,3 min, 205 frames: os 12 passos funcionais passaram novamente. Três papéis com contas temporárias reais, fila acumulando/drenando, bancos consultados, comandos do dashboard com ACK, geração de 1.036.800 vetores e treino assíncrono concluídos. Novo candidato `mdl_2ae41b419fdf4fabb0be6f94547e8547` não foi promovido artificialmente; inferência permaneceu na versão aprovada anterior. O hot-reload de um bundle realmente treinado foi verificado separadamente em banco descartável, sem reiniciar a instância do componente.

Na falha: corrente 4,6894→5,2840 A; vibração 1,3904→3,3694 mm/s; carcaça 46,262→64,141 °C; saúde 100→87,84%. RUL nos dois marcos ~24,09 h, com oscilação nas previsões intermediárias; não se comprovou redução monotônica. Alerta anterior encerrou por dez previsões boas; novo alerta warning abriu às 23:47:32 UTC após três ruins, revisão 6, sem mudança de limiares durante o ensaio. A cena recebeu o estado por WS. Configuração original 40/45%, 24/30 h e 3/10 restaurada após a sequência; spool original recolocado, writer ativo, contas de prova desativadas. Volumes e auditoria de prova preservados.

O Ollama respondeu às três perguntas com HTTP/SSE corretos, mas a revisão humana do texto **reprovou o resultado**:

- Definiu RUL corretamente e depois inverteu sua interpretação, afirmando que RUL baixa dispensava atenção e RUL alta indicava declínio.
- Expandiu os nomes de MAE/RMSE corretamente, mas explicou cálculos incorretos e alegou RMSE menor que MAE como indicador de precisão.
- Descreveu InfluxDB como banco em nuvem, embora o resumo confiável e o Compose sejam locais; também confundiu direções de transporte.

Portanto, `passed: true` nos dois relatórios originais comprova **asserções funcionais**, não fidelidade de linguagem. O teste foi esclarecido para registrar `functional_passed` e `semantic_review: manual_required` nas próximas execuções. Relatórios originais não foram reescritos. As respostas vieram do modelo real; não foram substituídas por texto pronto, ocultadas ou promovidas a diagnóstico confiável.

### Estado de encerramento e pendência de decisão

Correções funcionais dos três blocos implementadas, sem commit/merge/push. Seis unitários de contexto/prévias, 15 Vitest focados, 14 integrações de assistente/Mensageria/WS, quatro integrações adicionais de recuperação de alerta e um teste real de treino/hot-reload passaram. Após a última alteração do contexto, seis integrações do assistente passaram novamente. Ruff/mypy, tipos frontend, build e ESLint das áreas alteradas passaram. Warning de depreciação Starlette/httpx permanece, sem falha funcional.

Checagem final da cena por item passou no navegador: compressor não oferece botão manual do ventilador; selecionar ventilador mostra minigráfico binário e comanda com ACK pelo painel do item. Parada/retorno do simulador e movimento reduzido continuam validados, com 30 FPS/36 chamadas/3.116 triângulos. Não houve redesenho visual.

**Bloqueio remanescente obrigatório:** fidelidade demonstrável do assistente. Ajustar o contexto não foi suficiente para o modelo 1B Q4. A execução foi interrompida antes de trocar modelo, elevar recursos/timeouts ou abrir nova campanha de avaliação: isso muda o risco de memória/latência e requer decisão do usuário conforme o limite aprovado. Nenhuma reorganização visual foi iniciada. Primeira etapa proposta de UI/UX, após a decisão: hierarquia da Visão geral, escolha explícita do equipamento e distinção clara de estado recente, intenção pendente e estado confirmado; preservar contratos e controles.

Limites opcionais continuam adiados: carga ampliada, p95 sustentado, falhas combinadas e automação de backups. Contas originais operador/visualizador exigem suas senhas atuais; as iniciais não autenticaram nesta máquina e não foram redefinidas.

## Continuação autorizada — avaliação delimitada e proposta de UI/UX

A [comparação 1B versus único candidato 3B](avaliacao-llm-2026-11-14.md) foi concluída: dez respostas, mesmos prompts por caso e limites preservados. Candidato reprovado por fidelidade, sem troca de configuração; não houve busca de outros modelos. A [proposta única de navegação e Visão geral](proposta-uiux-visao-geral.md) usa shadcn como referência, registra componentes/dependências/custo e aguarda revisão. Nenhuma mudança visual foi implementada. Os demais componentes permanecem concluídos no escopo validado.

Decisão final do usuário nesta etapa: avaliação encerrada, manter 1B provisoriamente e classificar o assistente como **atendimento parcial, com pendência de fidelidade semântica**. Isso delimita o estado atual e substitui a pendência de decisão anteriormente registrada; não reabre os demais componentes. Sem novas tentativas ou ajustes de prompt. A proposta visual deve usar somente dados estruturados para valores/alertas/métricas, com unidade, versão e horário pertinentes. Texto gerado não determina comandos nem encerramento de alertas.


## Continuação — piloto visual aprovado

Navegação e Visão geral implementadas no escopo aprovado; verificações e capturas em [UI piloto — 15/11/2026](ui-piloto-2026-11-15.md). Expansão visual aguarda avaliação do responsável. A pendência semântica do assistente permanece delimitada, sem novas tentativas.
