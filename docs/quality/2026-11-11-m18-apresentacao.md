# M18 — Aceite focado na apresentação

## Escopo aprovado

O usuário informou aprovação acadêmica para substituir o ventilador pelo ar-condicionado e priorizou estabilização, ensaio funcional e depois interface. Antes de novas alterações da interface, haverá planejamento conjunto e execução por etapas aprovadas. O legado permanece preservado. Push/PR não foram autorizados.

O aceite abaixo não substitui as metas ampliadas de NF01–NF15. A [carga anterior](2026-11-11-m18-load-failed.md) continua reprovada; o ensaio com dez dispositivos não foi repetido. Não se presume que as correções resolvam a capacidade ampliada.

## Publicação e execução nominal

| Verificação | Evidência e limite |
|---|---|
| Correção | [V] `4e64d93`, integrado à main local por `b3d6809`: reserva/conclusão de lotes limitados no PostgreSQL, confirmação AMQP individual e espera apenas em ciclos ociosos. Nenhuma garantia foi removida |
| Entrega durável | [V] 16 integrações PostgreSQL/RabbitMQ passaram: posse concorrente, prazo/geração, rollback de lote e corte após confirmação parcial, além das garantias anteriores |
| Regressão Python | [V] 220 testes do pacote, simulador e inferência passaram |
| Integração de negócio | [V] 25 testes de gateway, writer, controle, inferência e WebSocket real passaram em containers; testes de domínio usam banco descartável |
| Qualidade | [V] Lint, tipos, formatação e contratos gerados passaram; scanner staged sem achados; hooks executados no commit |
| Compose | [V] Os 13 serviços permanentes ficaram saudáveis; bootstrap e inicialização do modelo concluíram |
| Fluxo contínuo | [V] Em 65 s, 34 frames reais do simulador chegaram pelo pipeline ao coletor WebSocket autenticado; p95 amostra→coletor 362,141 ms, máximo 380,048 ms. Não inclui renderização do navegador nem comprova carga ampliada |
| Pendências de publicação | [V] Consulta ao journal após a coleta não encontrou outbox pending/working. É uma observação nominal, não prova de ausência de perda em todas as falhas |
| Estado das previsões | [V] Os 34 frames indicaram inactive, corretamente sem saúde/RUL numéricas enquanto compressor parado. A versão registrada foi preservada; esse ensaio não comprova degradação/alerta |

## Ensaio no navegador

[V] `npm run test:e2e`: 15 testes passaram em 2,9 minutos com a pilha real. Cobrem assistente Ollama, papéis/login, comando físico manual e liberação do automático, cadastro, Insights com parada do simulador, geração massiva, Mensageria com parada/retorno do writer, WebSocket/reconexão, cena 3D e treino com métricas.

Os casos de contas, Markdown/limites e indisponibilidade HTTP incluem fixtures explícitas; o caso AMQP de reconexão publica frames de prova. Não equivalem à demonstração inteira com falha física e predições reais. Na cena com telemetria real foram observados 30 FPS, 44 chamadas e 2.052 triângulos.

## Modelo treinado e ativação

[V] Os sete testes de registro/promoção passaram com PostgreSQL real. O teste `test_real_training_bundle_hot_loads_only_after_api_approval` mantém a mesma instância de `ModelRuntime` viva durante o treino real em subprocesso: antes da aprovação ela permanece sem modelo; após promoção pela API, sem métricas fabricadas nem aprovação por SQL, carrega o bundle treinado e confirma a versão ativa. Este teste valida a troca do componente em execução em banco descartável; não representa uma promoção de candidato na pilha de demonstração.

[V] Um treino adicional na pilha, usando até 200 mil linhas de features, concluiu, mas a promoção foi recusada por `rul_calendar_hours_regresses_active`. A versão saudável anterior foi mantida. Não se contornou a política para produzir uma troca artificial na apresentação.

## Degradação e alerta reais

[V] O [resultado estruturado](2026-11-11-m18-apresentacao.json) resume um ensaio de 420 s no pipeline real. Foram recebidos 208 frames, dos quais 62 com previsão válida. Um volume temporário isolou o estado físico do simulador; o volume original foi preservado e recolocado ao final. Somente o desgaste foi acelerado; UTC, warm-up e intertravamentos permaneceram reais.

| Variável | Primeira previsão válida | Última previsão válida |
|---|---|---|
| Corrente | 4,954 A | 6,332 A |
| Vibração RMS | 1,866 mm/s | 6,046 mm/s |
| Temperatura da carcaça | 49,939 °C | 80,250 °C |
| Saúde estimada | 100% | 56,14% |
| RUL estimada | 26,34 h | 19,06 h |

[V] O compressor partiu automaticamente após o intervalo de proteção e foi desligado pela proteção térmica; frames posteriores ficaram inactive, sem inventar saúde/RUL atuais. A versão treinada em uso permaneceu a mesma. São hipóteses didáticas e predições sintéticas, sem calibração para aparelho físico.

[V] Para demonstrar uma transição nova, a API administrativa configurou sensibilidade explícita de demonstração: saúde ativa abaixo de 90%/encerra acima de 95%; RUL ativa abaixo de 1 h/encerra acima de 2 h, mantendo 3 amostras ruins/10 boas. O alerta antigo encerrou às 14:45:56 UTC pela histerese; um novo abriu às 14:46:59 UTC na revisão 2. Nenhuma linha de alerta foi apagada ou encerrada manualmente. Ao final, a configuração original 40/45%, 24/30 h e 3/10 foi restaurada pela API versionada. O ensaio não demonstra uma nova transição com os limiares originais.

[V] No navegador, a página Insights exibiu saúde 85,5%, RUL 19,6 h e o novo alerta ativo. A Cena 3D indicou dados recentes; o Ollama local respondeu à pergunta sobre o alerta e a vida útil, em streaming, com 897 caracteres no texto renderizado. A verificação foi feita em Chromium sem alterar componentes, estilos ou navegação.

## Limites do ensaio de apresentação

[V] Os percursos obrigatórios foram exercitados por testes seriados e pelo cenário físico acima. Isso não é um ensaio humano contínuo, cronometrado, de toda a apresentação em dez minutos. O roteiro final deve ser repetido após as mudanças aprovadas da interface. A proteção de partida pode ser coberta pela apresentação de login/API/Mensageria, sem encurtar os 180 s.

[V] Quinze testes dos operadores de backup/restore e escopo de carga passaram, com lint/formatação limpos. Não houve repetição do ensaio ampliado de carga. A evidência de restauração anterior permanece separada.

## Pendências adiadas

| Pendência | Tratamento |
|---|---|
| Dez simuladores/20 vetores por segundo, p95 completos e memória agregada | Adiados; não atendidos por presunção |
| Campanha de falhas combinadas, repetição de todos os benchmarks, auditoria exaustiva de acessibilidade | Adiadas; preservar testes funcionais e proteções existentes |
| Agendamento de backup e perda integral da máquina | Adiados; [restauração local verificada](2026-11-11-m18-backup.md) permanece válida no escopo registrado |
| README principal, publicação e CI remoto/equipe | Pendentes para entrega; sem push automático |
| Interface | Sem novas alterações visuais; aguardar planejamento conjunto antes de executar |
