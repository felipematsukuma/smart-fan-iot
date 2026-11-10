# Plano técnico do 2º bimestre — índice de consolidação

Este índice organiza a documentação de planejamento do smart-fan-iot. Toda a documentação deve ser consolidada e revisada antes de qualquer implementação. Não é cronograma nem autorização de desenvolvimento.

**Estado:** conteúdo das cinco etapas e oito ADRs consolidado documentalmente. Após a revisão final, o usuário autorizou execução contínua dos módulos conforme o plano, sem confirmação entre módulos. Branch por módulo, validação e merge local permanecem obrigatórios; push/PR continuam não autorizados. Só interromper por bloqueio que exija decisão do usuário. O aceite operacional depende dos testes reais, não da autorização de execução.

**Revisão técnica final:** os três refinamentos aprovados foram incorporados: ativação apenas de modelo aprovado e selecionado no registro; lease renovável com fencing e recuperação segura; UTC real no live, acelerando apenas a degradação do cenário. Especificações em [arquitetura](./plano/03-arquitetura.md), critérios em [módulos](./plano/04-modulos.md) e [aceite](./plano/05-riscos-aceite.md). Nenhum desses controles foi implementado por esta revisão documental.

## Registro de execução sob demanda

| Módulo | Evidência e limite |
|---|---|
| M00 — contratos v2 | Implementado e validado localmente em `feat/contratos-v2`, merge `83f89e4`; [README do pacote](../packages/smartfan_common/README.md). 134 testes Python do pacote, 216 frontend, 153 backend, lint/tipos/geração e build locais aprovados; CI remoto e fluxo AIoT integrado pendentes |
| M01 — infraestrutura | Fundação implementada em `feat/infra-aiot`; [execução e limites](../infra/README.md). Compose novo isolado, imagens pinadas, segredos locais, serviços sem root, brokers autenticados, oito filas quorum e modelo local preparado. Verificação real da infraestrutura e quatro testes de preparo; consumidores/frontend HVAC, scan de imagens e CI remoto ainda pendentes. O ciclo prossegue com M02; demais módulos pendentes |
| M02 — entrega durável | Implementado em `feat/entrega-duravel`: [garantias e operação](../packages/smartfan_common/src/smartfan_common/reliability/README.md). 138 testes do pacote e 11 integrações PostgreSQL/AMQP reais; transações, dedupe, quota, RLS, fencing, retry, DLQ e confirms verificados localmente. Consumidores de negócio, supervisão dos jobs, carga/chaos completo e CI remoto permanecem pendentes |
| M03 — simulador Python | Implementado em `feat/simulador-python`: [uso e limites](../services/simulator/README.md). Cinco sensores, dois atuadores, degradação, proteções e spool SQLite; estado versionado v2.1 com revisão observada. Oito testes do dispositivo, 141 do pacote e integração MQTT real com fixture de gateway persistente. Gateway M04 permanente, Web/controle/inferência e CI remoto ainda pendentes |

| M04 — gateway MQTT↔AMQP | Implementado em `feat/gateway-mqtt-amqp`: [garantias e operação](../services/gateway/README.md). Recebimento durável, origem autenticada, confirmação física, presença e expiração; 15 integrações isoladas e um percurso real pelo gateway. Interrupções reais: spool 0→4→0 e outbox 0→4→0 após retomada. Cadastro dinâmico, gravador, Web, carga integrada e CI remoto permanecem pendentes |

| M05 — writer e histórico HVAC | Implementado em `feat/gravador-influxdb`: [garantias, consultas e medições](../services/writer/README.md). Reserva de ponto antes do upsert, token de escrita restrito a live e persisted após InfluxDB; consultas limitadas e energia sem preencher lacunas. Ensaio isolado: 1 M vetores em 30,001 s; consulta agregada p95 0,123 s. Fluxo integrado de carga, API/UI, limpeza operacional, CI remoto e scan permanecem pendentes |

| M06 — API, auth e auditoria | [V] Implementado em `feat/api-auth-auditoria`: [operação e limites](../services/api/README.md). JWT/sessões, três papéis, bcrypt calibrado para a máquina, rate limit, auditoria append-only e shell/login Vue. Apenas frontend em loopback; telemetria/WS e negócio de outros módulos permanecem pendentes. CI remoto e scan ainda [N] |

| M07 — WebSocket e dashboard | [V] Implementado em `feat/websocket-dashboard`: [contratos, segurança e limites](../services/api/REALTIME.md). Ticket com escopo, consumidor API, snapshot durável, store e gráfico live; histórico/energia separados. 171 testes Python, 231 Vitest, 10 integrações e quatro Playwright passaram. Validação pré-compilada mantém CSP sem unsafe-eval; origem impede replays reenriquecidos. Inferência M13 contínua, carga, CI remoto e scan permanecem pendentes |
| M08 — Cadastro de dispositivos | [V] Implementado em `feat/cadastro-dispositivos`: [perfil, versões, permissões e limites](../services/api/DEVICES.md). Cinco sensores/dois atuadores com IDs estáveis, edição administrativa, concorrência 409, desativação lógica e histórico preservado. 184 testes Python, 231 Vitest, 22 integrações e cinco Playwright passaram. Provisionamento de outro cliente MQTT/instância não é automático; comandos HTTP completos ficam em M09 |
| M09 — Controle de atuadores | [V] Implementado em `feat/controle-atuadores`: [termostato, agenda, prioridade manual e ACK](../services/control/README.md). Outbox transacional, chave idempotente, revisão/boot, timeout com resultado desconhecido, comando Web e regra automática demonstrados no Compose real. 193 testes Python, 231 Vitest, 27 integrações e seis Playwright passaram. Histerese preditiva, cenário físico pela UI e carga integrada permanecem em módulos posteriores |
| M10 — Mensageria e DLQ | [V] Implementado em `feat/mensageria-dlq`: [monitoramento, prévias e replay restrito](../services/api/MESSAGING.md). Monitor somente leitura; prévias sem payload bruto; replay transacional exclusivo do writer, sem comandos físicos. Parada/retorno do writer demonstrados pela UI com fila crescendo/esvaziando. 193 testes Python, 231 Vitest, 31 integrações e sete Playwright passaram; recuperação de jobs/inferência e retenção operacional permanecem posteriores |
| M11 — Laboratório sintético | [V] Implementado em `feat/laboratorio-dados`: [artefatos, censura, supervisor e medições](../services/jobs/README.md). 1.036.800 vetores reais por job, seed reproduzível, blocos/memmap, rótulos fora do WS, cancelamento e lease com prova de parada. Três execuções: 2,14–2,24 s/96–97 MiB no filho, sem representar p95 integrado. 207 testes Python, 231 Vitest, 38 integrações e oito Playwright passaram. Treino/inferência, retenção e aceite integrado permanecem posteriores |
| M12 — Treino e registro | [V] Implementado em `feat/treino-registro-modelos`: [métricas, isolamento e promoção](../services/jobs/TRAINING.md). Ridge/HGB por alvo, baseline, janelas causais compartilhadas, grupos disjuntos e benchmark com outra seed. Ensaio de 1.036.800 vetores: 37,09 s/246,73 MiB no filho; MAE benchmark saúde 0,569 vs 23,006 e RUL 3,177 h vs 9,746 h. 214 testes Python +153 legados, 231 Vitest, 45 integrações e nove percursos Playwright validados. Aprovação/desired não ativam modelo; hot-reload e uso efetivo são M13 |

| M13 — Inferência e alertas | [V] Implementado em `feat/inferencia-alertas`: [origem, ativação e histerese](../services/inference/README.md). Janela causal compartilhada, recuperação passada, resultado idempotente por fonte e hot-reload cercado por aprovação/revisão/hash. Sete integrações focadas incluem revogação, commit incerto e histerese persistida; pipeline real alcança WS com regressores treinados. 221 testes Python, 153 legados e 231 Vitest passaram. UI Insights, retenção e aceite integrado permanecem posteriores |

| M14 — Página Insights | [V] Implementado em `feat/pagina-insights`: [estados, versões e histórico](../services/api/INSIGHTS.md). Saúde/RUL/tendência/comparação via WS; números ocultados quando stale; histórico REST e regras versionadas separados. 238 Vitest, 12 integrações e um percurso Playwright real com parada do simulador passaram. Injeção guiada de falha e carga integrada permanecem M18 |

| M15 — Cena 3D | [V] Implementado em `feat/cena-3d`: [fluxo WS, recursos e medição](../web-smart-fan-iot/frontend/src/aiot/scene/README.md). Oito IDs cadastrados, geometria procedural persistente, dois mapas térmicos, seleção por teclado, minigráfico e controle Web separado. Ensaio local: 30 FPS, 44 chamadas/2.052 triângulos; 241 Vitest. Movimento reduzido e parada real do simulador congelam animação. Carga prolongada/CI/scan permanecem M17/M18 |

## Decisões desta consolidação

- Domínio-alvo: ar-condicionado split residencial convencional liga/desliga, mantendo redução de desperdício e acompanhamento de consumo.
- Equipamento monitorado proposto: compressor; sensores iniciais de corrente, vibração e temperaturas da carcaça, interna e externa.
- Atuadores propostos: compressor automático e ventilador da condensadora controlável pela Web, com intertravamentos. Detalhamento nas etapas seguintes.
- Mesma máquina para execução e apresentação; orçamento de recursos ainda precisa de medição.
- Firmware, circuito e documentação do ventilador permanecem preservados como legado; esta etapa não os modifica.
- Os selos [V], [I] e [N] distinguem evidência, inferência e ausência de confirmação.

## Documentos e fluxo de aprovação

| Etapa | Documento | Branch | Estado |
|---|---|---|---|
| 1 — Inventário | [01-inventario.md](./plano/01-inventario.md) | `docs/plano-etapa-1-inventario` | Integrado à main local em `8b00596`; aceite operacional pendente |
| 2 — Lacunas | [02-lacunas.md](./plano/02-lacunas.md) | `docs/plano-etapa-2-lacunas` | Integrado à main local em `d3d9230`; aceite operacional pendente |
| 3 — Arquitetura e ADRs | [03-arquitetura.md](./plano/03-arquitetura.md) e [oito ADRs](./plano/03-arquitetura.md#14-adrs-pendências-e-limite-desta-entrega) | `docs/plano-etapa-3-arquitetura` | Integrado à main local em `b266854`; aceite operacional pendente |
| 4 — Catálogo de módulos | [04-modulos.md](./plano/04-modulos.md) | `docs/plano-etapa-4-modulos` | Integrado à main local em `b8c3c45`; aceite operacional pendente |
| 5 — Riscos e aceite | [05-riscos-aceite.md](./plano/05-riscos-aceite.md) | `docs/plano-etapa-5-riscos-aceite` | Conteúdo consolidado; revisão final do usuário pendente |

Conforme atualização do usuário nesta sessão, cada alteração relevante terá branch própria, commits separados e merge local na main ao concluir. Push e PR continuam sujeitos a autorização explícita. Cada etapa parte da main local com os merges anteriores; origin/main ainda não recebeu esses commits, pois não houve push autorizado. Se o remoto divergir, será necessário resolver a base sem reescrever histórico. Não haverá empilhamento silencioso. Os 19 módulos do catálogo identificam unidades sob demanda, sem calendário ou divisão por integrante.

## História preservada

[V] O código-base desta consolidação é `346f7de`, cuja descrição registra o merge da branch de energia. O plano anterior, inclusive seus ADRs incorporados e registro da entrega M00, permanece integralmente acessível em sua [versão histórica no commit 90e2053](https://github.com/felipematsukuma/smart-fan-iot/blob/90e2053/docs/PLANO-BIMESTRE-2.md). A referência foi verificada no histórico Git local; disponibilidade dessa página remota não foi testada nesta etapa.

[V] Permanecem no repositório os documentos originais do ventilador:

- [Visão geral do projeto](../README.md).
- [Firmware e Wokwi](../esp32-simulador/README.md).
- [Aplicação Web](../web-smart-fan-iot/README.md).
- [Revisão técnica de 26/10/2026](./revisao-tecnica-2026-10-26.md).
- [Registro de implementação e validação de 26/10/2026](./implementacao-2026-10-26.md).
- [Núcleo compartilhado M00](../packages/smartfan_common/README.md).

O plano histórico contém autorizações e decisões de uma execução anterior. Elas não substituem as regras desta consolidação: somente documentação por etapa aprovada, nenhuma implementação antes da consolidação completa e nenhuma publicação sem confirmação explícita.
