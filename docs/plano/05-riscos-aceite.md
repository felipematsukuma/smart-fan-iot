# Etapa 5 — Riscos, rastreabilidade e aceite

Base documental: `b8c3c45`; branch `docs/plano-etapa-5-riscos-aceite`. Código avaliado no inventário: `346f7de`. Esta entrega consolida o planejamento; não implementa nem aprova operacionalmente a stack AIoT.

Referências normativas do plano: [inventário](./01-inventario.md), [lacunas](./02-lacunas.md), [arquitetura](./03-arquitetura.md), [módulos e D0](./04-modulos.md) e [ADRs](./03-arquitetura.md#14-adrs-pendências-e-limite-desta-entrega). Selos [V]/[I]/[N] mantêm os significados definidos no inventário.

## 1. Critérios e estado do aceite

Todos os testes T, NF, F e S abaixo são **planejados/não executados** para a solução-alvo. [V] Testes do legado e M00 v1 executados anteriormente nesta sessão estão identificados no [inventário, seção 8](./01-inventario.md#8-qualidade-e-evidências-de-execução). Não foram reexecutados nem convertidos em evidência AIoT por esta etapa.

| Estado de um critério | Significado |
|---|---|
| Planejado | Procedimento definido; sem resultado de execução |
| Bloqueado | Dependência/ambiente/decisão impede executar; motivo explícito |
| Falhou | Executado, resultado diverge do esperado ou excede meta |
| Aprovado | Execução real no commit identificado, evidência íntegra e sem pendência relevante daquele critério |
| Não aplicável | Somente com justificativa de escopo; não pode eliminar requisito obrigatório |

Aceite de módulo exige D0 e critérios da ficha; aceite final exige T01–T20, comportamentos B01/B02, ensaios relevantes de falha/segurança e metas NF com resultados. Stub pode aprovar unidade/layout, não fluxo integrado. Uma meta não atingida continua falha mesmo que haja justificativa; ajuste da meta requer decisão explícita e atualização documental, nunca mudar o relatório para esconder o resultado.

## 2. Matriz de riscos

P e I são probabilidade/impacto estimados: 1 baixo, 2 médio, 3 alto. Prioridade=P×I. São avaliações de planejamento [I], baseadas nas dependências/recursos da arquitetura; não estatísticas medidas. Responsabilidade é indicada por módulo, sem divisão por integrante ou calendário.

| ID | Risco | P | I | PxI | Mitigação / módulo | Sinal de alerta |
|---|---|---|---|---|---|---|
| R01 | LLM lento em CPU | 3 | 3 | 9 | Contexto/saída limitados, warmup, uma requisição; benchmark 3b e alternativa 1b documentada; M16 | TTFT quente >10 s ou total >90 s |
| R02 | RAM Docker/WSL insuficiente | 3 | 3 | 9 | Limites, medir RSS, serializar job pesado/chat e descarregar modelo; M01/M11/M12/M16 | Swap sustentado, OOM ou >10 GiB agregado |
| R03 | Milhão de leituras causa OOM/disco cheio | 2 | 3 | 6 | NumPy em blocos/memmap, teto, quota e progresso; M11/M18 | Crescimento de RSS proporcional à massa inteira; disco >90% |
| R04 | Modelo acerta demais por leakage | 3 | 3 | 9 | Split por equipamento, causalidade, labels isolados, teste reservado; M00/M12 | R² quase perfeito, ID/futuro/seed no vetor ou queda forte em seed nova |
| R05 | Regressor não vence baseline | 2 | 3 | 6 | Dados variados, avaliação por alvo/máquina, rejeitar promoção ruim; M11/M12 | MAE/RMSE não melhores ou métricas indefinidas |
| R06 | Cena 3D pesada | 2 | 2 | 4 | Geometria simples, buffers/instâncias, budget e lazy import; M15 | <30 FPS, >100 draw calls ou crescimento de objetos por evento |
| R07 | Segredo novo ou histórico reutilizado | 2 | 3 | 6 | Scan integral/redigido, confirmar revogação e rotação; M01/M17/M18 | Valor ativo em arquivo rastreado/log/imagem ou baseline genérica |
| R08 | Perda entre MQTT, AMQP e bancos | 2 | 3 | 6 | Spool, inbox/outbox, confirmação por fronteira e reconciliação; M02–M05 | Recebido/ACKado sem cópia durável; IDs aceitos não reconciliam |
| R09 | Contrato diverge entre módulos | 3 | 3 | 9 | Pacote único, schema/TS gerados, fixtures compartilhadas e upgrade coordenado; M00/M17 | Exportação com diff, campos extras aceitos ou consumidores em versões distintas |
| R10 | Comando duplicado ou fora de ordem | 2 | 3 | 6 | ID/hash, revisão/boot/expiry e estado persistente; M03/M04/M09 | Dois efeitos para uma intenção, estado antigo sobrescreve novo |
| R11 | Controle automático desfaz comando manual | 2 | 3 | 6 | Prioridade/proteção e bloqueio manual explícito; M09 | Ventilador religado automaticamente sem liberação do usuário |
| R12 | Backlog/replay parece dado atual | 2 | 3 | 6 | Origem temporal/observed_at/seq, filtros de frescor e freeze; M04/M07/M13/M15 | Cena continua animada com simulador parado |
| R13 | RUL muda de unidade sem aviso | 2 | 3 | 6 | Schema2.0, unidade de calendário simulada e rejeição do campo antigo; M00/M12/M14 | Horas de operação tratadas como calendário por alias |
| R14 | Equipamentos censurados ganham falha fictícia | 2 | 3 | 6 | RUL desconhecida não vira zero/fim do dataset; reportar exclusão/viés; M11/M12 | Todas as trajetórias têm RUL exata apesar de não falharem |
| R15 | Calor tropical confundido com defeito | 3 | 2 | 6 | Controle saudável sob carga alta, diversidade por máquina e causa não conclusiva; M03/M11/M12 | Saúde cai só porque temperatura externa subiu |
| R16 | Mudança de aparelho perde continuidade | 2 | 3 | 6 | Justificar energia/desperdício e preservar legado; M18 | Apresentação parece projeto sem relação com primeiro bimestre; aceite acadêmico [N] |
| R17 | UID/versão/permissão de broker incompatível | 2 | 3 | 6 | Pin por patch/digest, smoke não-root, ACL/DLX negativos; M01/M17 | Root runtime, guest ativo, publish fora de rota ou bootstrap em loop |
| R18 | Treino bloqueia API/controle | 2 | 3 | 6 | Worker/limites separados, lease de recursos; M11/M12/M16 | p95 API sobe muito ou janela de controle perde cadência durante job |
| R19 | Prompt injection/Markdown vira ação | 2 | 3 | 6 | Sem tools, resumo allowlist, Markdown sem HTML e comando apenas API autorizada; M16 | Texto executa script/comando ou revela dado não autorizado |
| R20 | Restore inconsistente entre bancos/artefatos | 2 | 3 | 6 | Fronteira quiescente, manifestos, volumes isolados e reconciliação; M18 | Modelo ativo sem arquivo/hash ou outbox perdida após restore |
| R21 | Merge local conflita com proteção remota | 2 | 2 | 4 | Não publicar main como contorno; branch/PR autorizado e reconciliação explícita; M17 | Push rejeitado ou PR inclui base inesperada |
| R22 | Roteiro excede 10 minutos | 3 | 2 | 6 | Ensaio completo com cache preparado, budgets e duração real; M18 | Job não conclui no trecho previsto ou LLM recarrega durante pergunta |
| R23 | Cardinalidade/retencão cresce sem limite | 2 | 3 | 6 | IDs de evento em fields, tags limitadas, limpeza de terminais/quota; M02/M05 | Séries crescem por evento ou limpeza remove única cópia pendente |
| R24 | CI verde sem evidência de integração | 2 | 3 | 6 | Gate agregador, jobs obrigatórios e distinção real/stub; M17/M18 | Job obrigatório skipped tratado como sucesso; cobertura só por mocks |

## 3. Matriz de rastreabilidade

IDs T identificam casos de aceite a implementar, não nomes de testes já existentes. D01–D13 são passos da demonstração na seção 7. Segurança transversal tem sua própria matriz S; metas e falhas têm NF/F. M00/M01/M02/M17 podem habilitar vários itens sem satisfazê-los isoladamente.

| Requisito | Módulos principais | Teste de aceite | Passo da demonstração |
|---|---|---|---|
| 1 — Vue/TS/Vite | M06/M07/M17 | T01 build, tipos e navegação da UI | D02/D07 |
| 2 — FastAPI/REST | M06/M17 | T02 OpenAPI e chamadas positivas/negativas | D04 |
| 3 — WebSocket | M00/M06/M07 | T03 ticket, stream/reconnect e autorização | D07 |
| 4 — MQTT bidirecional | M01/M03/M04/M09 | T04 leitura e comando/ACK por MQTT real | D03/D08 |
| 5 — >=3 sensores | M00/M03/M08 | T05 cinco canais, unidades e histórico | D03/D06 |
| 6 — >=2 atuadores | M03/M08/M09 | T06 dois estados/efeitos independentes | D08 |
| 7 — equipamento com >=3 variáveis de degradação | M03/M11/M12 | T07 cenário progressivo e controle saudável | D03/D11 |
| 8 — regra automática | M03/M09 | T08 termostato, histerese e proteção | D08 |
| 9 — comando Web | M04/M06/M07/M09 | T09 intenção→AMQP→MQTT→ACK→leituras | D08 |
| 10 — RabbitMQ e Mensageria | M00–M02/M04/M05/M10–M13 | T10 topologia, consumidores, DLQ e filas de jobs | D05/D09/D10 |
| 11 — PostgreSQL e InfluxDB | M02/M05/M06/M08/M09/M18 | T11 papéis, schema, histórico e auditoria | D06 |
| 12 — dashboard/gráficos/histórico | M05/M07/M14 | T12 leitura live e histórico persistido | D07 |
| 13 — gestão IoT | M06/M08 | T13 criar/editar/desativar com auditoria | D06 |
| 14 — 3D por dados WS | M07/M08/M13/M15 | T14 objetos/estados/ambiente/painel e freeze | D11 |
| 15 — laboratório massivo | M00/M02/M06/M07/M11 | T15 job >=1 M configurável e reproduzível | D09 |
| 16 — dois regressores e métricas | M00/M11/M12/M13 | T16 split/baseline/métricas/promoção/reload | D10/D11 |
| 17 — saúde/RUL/alertas | M09/M13/M14/M15 | T17 inferência real e histerese observável | D11 |
| 18 — assistente local | M01/M02/M06/M16 | T18 resposta local baseada em resumo, stream e limites | D12 |
| 19 — Compose completo | M01/M17/M18 | T19 subida, readiness e scripts de instalação | D01 |
| 20 — GitHub/equipe/README | M17/M18 | T20 histórico real, documentação reproduzível e checks | D13 |

## 4. Checklist funcional dos 20 requisitos

Todos os itens estão desmarcados por se referirem ao aceite integrado futuro. Para preencher, associar evidência real ao ID T, e não apenas screenshot ou dependência instalada.

| Aceite | Como verificar | Evidência esperada |
|---|---|---|
| [ ] T01 | Compilar frontend e abrir páginas da solução final | Build Vite/vue-tsc sem erros; páginas Vue reais e versões/commit |
| [ ] T02 | Abrir OpenAPI versionada e executar REST válido, inválido e sem permissão | Respostas/status/schema esperados; backend Python/FastAPI, sem Node backend |
| [ ] T03 | Obter ticket, conectar WS, reutilizar ticket e reconectar após queda | Primeiro consumo único, segundo recusado, frames reais, autorização server-side e expiração |
| [ ] T04 | Rastrear um ID de amostra e um comando por MQTT/gateway/AMQP | Logs/IDs nos dois sentidos; simulator Python publica e recebe; ACK de transporte separado de aplicação |
| [ ] T05 | Exibir os cinco sensores no simulador, cadastro, leitura e histórico | Corrente/vibração/carcaça/interna/externa com unidades; tensão/potência derivadas não contam como sensores adicionais |
| [ ] T06 | Alterar os dois atuadores e observar sua influência nas leituras | Compressor e ventilador externo com estados próprios, consumo e dinâmica coerentes; intertravamento demonstrado |
| [ ] T07 | Comparar cenário saudável e desgaste progressivo sob carga comparável | Tendências de >=3 variáveis do compressor com ruído/heterogeneidade; exterior quente isolado não é falha automática |
| [ ] T08 | Cruzar limites de temperatura e tentar partida bloqueada | Regra com histerese, tempo mínimo, razão registrada e estado observado; não só horário fixo legado |
| [ ] T09 | Enviar comando no dashboard, repetir chave e esperar retorno | 202/pendente, uma intenção, comando na fila, ACK correlacionado e leituras seguintes; timeout não inventa estado |
| [ ] T10 | Inspecionar exchange topic, >=4 filas com consumidores distintos, jobs e falha | Topologia real, usuários por serviço sem guest, ACL negativa, DLQ com original preservado e Mensageria via backend |
| [ ] T11 | Consultar cadastro/regras/auditoria PG e leituras no Influx | Migration version, entidades/FKs, histórico real e separação live/lab/legado; sem duplicação de ponto em replay |
| [ ] T12 | Alternar período/dispositivo e interromper coleta | Indicadores WS, gráfico/histórico REST, lacunas e cobertura corretas, loading/vazio/erro/sem dados |
| [ ] T13 | Admin criar/editar/desativar; operador tentar alterar cadastro | Restrições de papel, IDs únicos, auditoria e histórico preservado; comando para desativado recusado |
| [ ] T14 | Inspecionar objetos, clique/teclado e dois efeitos ambientais; parar simulador | Sensores/atuadores/equipamento por ID, painel/minigráfico/saúde/comando, temperaturas mudam ambiente, conexões sem pontas soltas; freeze <=6 s |
| [ ] T15 | Configurar e executar job >=1 M, repetir seed e cancelar outro job | Vetores equipamento/instante contados, manifesto/hash, parâmetros completos, progresso/limite, blocos e rótulos só em artefato |
| [ ] T16 | Treinar os dois alvos e testar candidato bom/ruim/artefato incompatível | IDs de split disjuntos; MAE/RMSE/R², previsto×real, importância e baseline; modelo válido vence base; promoção versionada e troca sem restart |
| [ ] T17 | Injetar falha progressiva e recuperação; deixar leitura stale | Saúde e RUL de modelos reais com unidade/versão/fonte; alerta ativa/limpa com histerese, dado ausente não vira melhora |
| [ ] T18 | Perguntar sobre falha com modelo em CPU e rede externa indisponível após cache | Ollama real, resumo backend, stream incremental, fontes/idade, Markdown seguro, rate limit e auditoria; sem cloud/tools |
| [ ] T19 | Após bootstrap inicial, executar Compose sem profiles | Todos os serviços obrigatórios e modelo disponíveis, readiness sem ciclo, não-root e portas corretas; sem serviço fake |
| [ ] T20 | Reproduzir instruções e revisar GitHub/commits da equipe | README com problema/diagrama/bootstrap/demonstração/usuários sem senhas, contribuições reais de todos e checks no commit publicado |

### 4.1 Comportamentos demonstráveis obrigatórios

| Aceite | Ação | Resultado/evidência |
|---|---|---|
| [ ] B01 | Pausar writer pelo terminal autorizado do Compose, mantendo sensores/gateway ativos; observar Mensageria; retomar | Ready cresce, consumidor ausente e taxas mudam; ao voltar a fila escoa; comparar IDs/pontos prova ausência de efeito duplicado. UI não usa Docker socket |
| [ ] B02 | Desligar o processo simulador mantendo navegador/WS abertos | Em <=6 s após última leitura fresca, animações congelam e há aviso sem dados; WS conectado não mantém máquina ficticiamente online; histórico não desaparece |

Os dois ensaios são distintos: parar writer testa backlog, parar simulador testa frescor. LWT pode chegar antes/depois do limite visual; não substitui idade da amostra.

## 5. Metas não funcionais e como medir

Metas propostas na [arquitetura, seção 13](./03-arquitetura.md#13-metas-não-funcionais-mensuráveis). Não são resultados observados. Perfil nominal: 10 equipamentos, uma leitura/2 s, um browser, 30 min; pico 20 amostras/s por 10 min. Relatório identifica modelo/seed/versão/carga, relógios sincronizados e medição fria/quente. Registrar p50/p95/máximo e taxa de erros, não apenas média.

| Aceite | Meta | Procedimento e evidência |
|---|---|---|
| [ ] NF01 | Simulador→tela p95 <=1,5 s; gateway observed_at→tela <=1 s | Correlacionar amostra com render real via Playwright; medir ambas as fronteiras, sem omitir fila antes do gateway |
| [ ] NF02 | 20 amostras/s por 10 min, sem perdas de eventos aceitos e backlog final zero | Reconciliar IDs únicos e contar separadamente eventos AMQP derivados; registrar CPU/RAM/disco |
| [ ] NF03 | API cadastro/status p95 <=300 ms; histórico agregado <=1 s | 10 clientes concorrentes; latência por rota e erros separados; chat/job não entram como resposta síncrona rápida |
| [ ] NF04 | Influx ingere 1 M vetores em <=15 min; consulta 24 h/1 máquina agregada <=1000 pontos p95 <=2 s | Bucket de benchmark isolado, batches e contagem por equipamento/instante; cold/warm cache e relatório de consultas |
| [ ] NF05 | Gerar 1 M vetores <=120 s; incremento RSS worker <=1,5 GiB | Config/seed fixos, contagem/hash do artefato, amostragem de RSS e duração monotônica; amostra Influx não conta como massa |
| [ ] NF06 | RSS agregado <=8 GiB nominal, <=10 GiB pico controlado; sem OOM/swap sustentado | docker stats por segundo e métricas WSL/host; demonstrar que lease impede treino pesado junto ao chat |
| [ ] NF07 | LLM TTFT p95 <=10 s quente, <=30 s frio; resposta <=90 s e <=256 tokens | 10 perguntas fixas em português, contexto limitado, digest do modelo, tempos de load/prompt/geração; sem treino simultâneo |
| [ ] NF08 | Subida até readiness/warmup <=180 s com cache | Reiniciar serviços mantendo volumes/cache; medir primeiro serviço até todos obrigatórios prontos. Download inicial separado |
| [ ] NF09 | Reconexão <=30 s após dependência voltar; backlog de pausa 60 s drena <=120 s | Derrubar consumidor, broker e banco separadamente; registrar horários, ready/unacked, IDs e tempo de retomada |
| [ ] NF10 | Zero perda de aceitos nos crashes ensaiados, volumes íntegros | Reconciliar spool/inbox/outbox/Influx; verificar um efeito por intenção. Não estender garantia a disco perdido/down -v |
| [ ] NF11 | RPO provisório <=24 h e restore <=30 min para massa de demo | Restaurar backup em volumes novos/isolados; contagens/hashes, modelo ativo e retomada conferidos; último backup conhecido |
| [ ] NF12 | >=80% branches em domínio/contratos/controle/ML; >=70% global, lint/tipos sem erros | Relatórios pytest-cov/Vitest e gates Ruff/mypy/ESLint/vue-tsc no mesmo commit; não excluir módulo difícil só para elevar percentual |
| [ ] NF13 | Zero vulnerabilidades críticas abertas nas imagens selecionadas | Scan com data, digest e banco de vulnerabilidades; exceção documentada não transforma meta falha em aprovada |
| [ ] NF14 | Todas páginas têm loading/vazio/erro/offline; teclado e contraste AA | Playwright/axe e inspeção manual; cena e gráfico com alternativa textual e reduced-motion |
| [ ] NF15 | 3D >=30 FPS, <=100 draw calls, <=50 mil triângulos e freeze <=6 s | renderer.info/perfil de frame na máquina; número de objetos estável por mensagem; teste com simulador desligado |

Estimativas de p95 com apenas 10 perguntas são descritivas e instáveis; repetir o conjunto se houver variação importante e relatar tamanho de amostra. Não omitir timeouts do cálculo/taxa de falhas. Percentuais de cobertura são metas, não cobertura já medida no repositório.

## 6. Ensaios de falha, recuperação e segurança

Comandos dependentes da stack futura são ações planejadas. Executar em projeto Compose de teste com volumes próprios e caminhos resolvidos/conferidos. Jamais usar exclusão de volumes reais como parte do ensaio. Cada queda tem baseline, ação, confirmação do estado, retomada e reconciliação.

### 6.1 Falhas e durabilidade

| Teste | Injeção | Resultado obrigatório |
|---|---|---|
| F01 | Pausar/retomar writer enquanto chegam sensores | Cumprir B01; sem evento persisted antes da gravação confirmada |
| F02 | Parar Mosquitto durante geração live | Simulador guarda amostras aceitas no spool; volta com mesmos bytes/IDs; ausência visual sinalizada; sem coleta imaginária enquanto processo parado |
| F03 | Parar RabbitMQ após receipt MQTT e antes de confirm AMQP | Gateway mantém outbox; retorno entrega sem perder aceitos ou criar nova identidade |
| F04 | Parar PostgreSQL antes do commit do gateway/consumidor | Não enviar receipt/ACK indevido; backpressure; processo permanece vivo e readiness indica dependência indisponível |
| F05 | Parar Influx entre reserva do ponto e escrita | Sem frame fresco fingindo persistência; retomar regrava chave determinística; colisão de outra amostra vai à falha preservada |
| F06 | Encerrar writer após write Influx e antes de commit/outbox | Retry do mesmo ponto; um resultado lógico e evento-fonte rastreável, sem recriar timestamp |
| F07 | Perder ACK de comando/repetir intenção/reiniciar simulador | Uma aplicação; ACK idempotente; boot/revisão/expiry impedem replay antigo; estado real retorna nas leituras |
| F08 | Publicar inválido dentro do tamanho permitido e falha permanente | Original preservado com hash/motivo e DLQ; inspeção não drena fila; replay é auditado e valida de novo |
| F09 | Esgotar quota de spool/fila/outbox em teste controlado | Alerta em 70/90%, pausa/rejeição de novos aceitos, sem drop-head nem apagar única cópia pendente |
| F10 | Reiniciar inferência; enviar modelo com hash/schema errado, sem aprovação ou com revisão de ativação antiga | Versão não aprovada/obsoleta nunca ativa; carregar só a seleção desired aprovada e revalidada sob bloqueio; warmup/abstenção explícitos; active reflete o processo real e é reconciliado após crash |
| F11 | Desligar simulador, manter WS e injetar backlog antigo | Cumprir B02; replay não anima nem limpa alerta; retained state não renova presença |
| F12 | Encerrar job entre blocos, repetir mensagem e tentar concluir/liberar com fencing token antigo | Parcial não vira dataset/modelo válido; geração antiga não conclui/promove/libera recurso novo; completed só após manifesto/hash e lease vigente; sem promoção duplicada |
| F13 | Pedir chat durante job; interromper renovação PG e congelar supervisor antigo | Sem sobreposição pesada; TTL 30 s/renovação 5 s e parada após 20 s sem renovar são ensaiados; recurso recovering não ganha novo dono sem prova de parada/liberação de memória; incerteza exige recuperação explícita |
| F14 | Restaurar conjunto PG/Influx/artefatos em volumes isolados | Cumprir NF11; schema compatível, hashes e contagens reconciliados; pendências retomadas sem replay inseguro de comandos |

Cada registro de teste deve explicitar o ponto de corte. Restart aleatório sem prova de atingir a janela crítica não comprova recuperação daquela janela. Convergência de contagens sozinha não prova identidade: comparar IDs/hashes e efeitos por comando.

### 6.2 Segurança negativa

| Teste | Tentativa | Resultado obrigatório |
|---|---|---|
| S01 | Token ausente/expirado/algoritmo ou audience errados; usuário desativado | 401; sessão/stream encerrados conforme prazo; nenhum segredo nos logs |
| S02 | Visualizador comanda; operador gera/treina; ID de dispositivo não autorizado | 403 no backend, não apenas botão escondido; evento de auditoria pertinente |
| S03 | Reusar ticket WS, ticket vencido ou socket sem autenticar | Recusa/fechamento no prazo; nenhum evento antes de autorização; JWT/ticket ausentes da URL |
| S04 | Login repetido e excesso de sockets/requests/chat | 429/limite documentado; estado de usuário não revelado; sem bloqueio permanente causado por terceiro |
| S05 | MQTT anônimo, dispositivo ac_01 publica em ac_02, usuário AMQP publica comando sem permissão | Falha de autenticação/ACL/topic permissions; guest ausente; nenhuma mensagem indevida chega à aplicação |
| S06 | Navegador tenta alcançar broker/LLM/banco; inspecionar bundle/requests | Só frontend publicado no padrão; links de UIs locais condicionais; nenhuma credencial de serviço no bundle/browser; JWT da sessão só em memória e Authorization, nunca URL/log |
| S07 | Prompt pede segredos/SQL/ação e texto contém HTML/URL insegura | Nenhuma tool/execução/alteração; Markdown escapado sem HTML ativo; resumo limita dados autorizados |
| S08 | Scan staged/arquivos/histórico e imagens | Sem segredo novo ou crítica aberta; achados históricos tratados por localização/revogação, sem allowlist genérica |
| S09 | Inspecionar UID, capabilities, mounts e permissões de serviços | Aplicação sem root, sem Docker socket, secrets RO e sem acesso ao segredo de outro papel |
| S10 | Alterar mesmo Idempotency-Key com corpo diferente, revision velha ou ponto Influx conflitante | 409/rejeição/quarentena apropriada; não sobrescrever estado/ponto nem criar intenção nova silenciosa |
| S11 | Consultar auditoria/falhas e tentar alterar/apagar por conta runtime inadequada | Leitura restrita, dados sensíveis redigidos, delete/update indevido negado; integridade e autoria verificáveis |

### 6.3 Registro mínimo de evidência

Modelo de registro futuro, sem resultado preenchido:

```json
{
  "criterion_id": "F06",
  "status": "planejado",
  "commit": null,
  "environment": null,
  "dependency_mode": "real",
  "versions_and_digests": {},
  "procedure": "Interromper writer entre escrita Influx e commit da outbox e retomar",
  "expected": "Um ponto logico e entrega retomada pelo mesmo evento-fonte",
  "observed": null,
  "duration_ms": null,
  "event_ids": [],
  "evidence_refs": [],
  "limitations": []
}
```

Arquivos de evidência futuros ficam no relatório do módulo ou artefato de CI identificado, com logs redigidos e timestamps. Credenciais, Authorization, tickets e dumps sensíveis não viram anexos públicos. Screenshot complementa, mas não substitui IDs/contagens/métricas. Distinguir evidência do teste automatizado de demonstração presencial e registrar falhas encontradas sem editá-las para sucesso.

## 7. Roteiro de demonstração de 10 minutos

É sequência de apresentação, não cronograma de desenvolvimento. Data de referência do usuário: 16/11/2026. A soma dos budgets abaixo é 600 s; são **alocações de ensaio**, não duração medida nem promessa de desempenho. Boot pode atender NF08 e ainda exceder o budget de D01; geração pode atender NF05 e ainda exceder D09. R22 só é resolvido após ensaio completo caber.

Preparação permitida antes da apresentação: imagens/modelo em cache, segredos locais válidos, usuários de demonstração, cadastro e cenários conhecidos, cópia de segurança e massa/modelos anteriores claramente versionados. Não preparar segredo no README, slides obrigatórios, replay fictício ou fixtures como produção. Informar se volumes/modelos já existiam. Usar nova identificação para jobs demonstrados; métricas anteriores não provam conclusão do job novo.

| Passo | Janela/budget | Ação e resultado a mostrar |
|---|---|---|
| D01 | 00:00–01:15 / 75 s | Executar `docker compose up` com cache, mostrar todos serviços reais e readiness. Abrir frontend; sem esconder componente não saudável |
| D02 | 01:15–01:40 / 25 s | Mostrar login e três papéis, uma operação proibida e sessão administrativa para lab; sem expor senhas |
| D03 | 01:40–02:05 / 25 s | Simulador Python, cinco sensores, equipamento e MQTT; apontar identidade/seq e dois atuadores |
| D04 | 02:05–02:25 / 20 s | Abrir OpenAPI FastAPI e resposta REST, com contrato/erro versionado |
| D05 | 02:25–03:10 / 45 s | Página Mensageria; pausar writer por terminal, ver fila crescer, retomar e ver escoar; DLQ e consumidores reais |
| D06 | 03:10–03:35 / 25 s | Mostrar dispositivo/configuração/auditoria no PG e leituras/histórico no Influx; gestão IoT e separação de dados |
| D07 | 03:35–03:55 / 20 s | Dashboard WS, indicadores e gráfico histórico; distinguir idade, cobertura e presença |
| D08 | 03:55–04:30 / 35 s | Demonstrar termostato automático e botão do ventilador; observar ACK/leituras e intertravamento; cenário começa em condição de partida elegível, sem burlar intervalo mínimo |
| D09 | 04:30–05:50 / 80 s | Configurar e iniciar geração >=1 M, acompanhar job e confirmar contagem/hash quando concluir. Se exceder budget, registrar; não trocar por amostra como prova do milhão |
| D10 | 05:50–07:30 / 100 s | Disparar treino dos dois alvos, acompanhar status, mostrar baseline/métricas e versão ativada quando concluir; candidato ruim rejeitado pode ser evidência de teste identificada |
| D11 | 07:30–08:45 / 75 s | Injetar degradação progressiva calibrada, ver saúde/RUL/alerta e cena 3D reagirem; parar simulador e confirmar freeze/sem dados; retomar para pergunta |
| D12 | 08:45–09:45 / 60 s | Assistente local responde sobre a falha, com streaming e dados-fonte; modelo aquecido após término do job; resposta curta compatível com o budget |
| D13 | 09:45–10:00 / 15 s | Mostrar README/GitHub/commits reais da equipe e onde estão evidências de testes; encerrar sem alegar requisito não demonstrado |

Condição de ensaio: D09/D10 devem concluir de fato se a demonstração anunciar geração e treino novos completos. Se o treino real não couber em 100 s ou a sequência ultrapassar 600 s, o roteiro está **não validado**: otimizar dentro do escopo, reduzir busca de hiperparâmetros sem eliminar dois alvos/avaliação, ou negociar formato com o avaliador. Não reduzir o dataset abaixo do mínimo, não renomear artefato antigo como novo e não usar stub para caber. O tempo de treino não tinha meta global definida na arquitetura; 100 s é budget de apresentação a validar, não benchmark já atendido.

Na pausa curta D05, a contagem deve crescer de forma visível e drenar; o ensaio NF09 de pausa 60 s é executado separadamente e tem evidência identificada. Restore, teste de milhão no Influx, scans e adversariais podem ter relatórios prévios verificáveis; isso não substitui os três fluxos ao vivo exigidos.

## 8. Fora do escopo — não fazer no mínimo

| Item considerado | Motivo da exclusão |
|---|---|
| Node.js como backend / LLM cloud | Proibidos; Node apenas compila frontend, Ollama roda localmente |
| Kubernetes, service mesh e cluster multihost | Não necessários à execução em uma máquina nem à apresentação |
| Redis/Celery/novo scheduler externo | RabbitMQ + worker e PG inbox/outbox/lease já cobrem jobs/recuperação |
| Um serviço por modelo ou por página | Não acrescenta requisito, aumenta operação; papéis compartilham imagem/pacote |
| Prometheus/Grafana permanentes | Management, logs e métricas backend bastam ao mínimo; reavaliar só se evidência exigir histórico maior |
| Framework 3D adicional/segunda biblioteca de gráficos | Three.js direto e Chart.js atendem; evitar duplicação |
| ESP32 e Python ativos simultaneamente no fluxo final | Manter ESP32 como legado; um contrato operacional HVAC evita duplicar compatibilidade |
| Física completa, CFD, circuito refrigerante ou controle inverter | Complexidade não exigida; simulação coerente e limites declarados bastam |
| Diagnóstico certificado de aparelho real ou promessa de vida útil real | Sem calibração/dados reais, saúde/RUL são do cenário sintético |
| Instrumentação adicional obrigatória de água/umidade/rpm/pressão | Cinco sensores iniciais atendem; ampliar só com caso de uso e nova versão/aceite |
| Comando por texto do assistente, tools/SQL arbitrário | Assistente explica dados; controle segue API/papéis/intertravamentos |
| RAG framework, vector database e Open WebUI | Resumo backend limitado atende consulta aos dados sem stack redundante |
| Exactly-once ponta a ponta/alta disponibilidade física | Um nó e múltiplos sistemas não dão essa garantia; at-least-once + efeitos idempotentes e backup |
| Retreino/promoção automática por drift | Drift sinaliza mudança; promoção exige comparação e política registrada |
| Modelos de sobrevivência no mínimo | Censura é tratada explicitamente na regressão e no relatório de viés; sobrevivência é evolução possível |
| Publicação, alteração de proteção remota ou reescrita do histórico sem autorização | Fora da autorização documental; não contornar branch protection ou mudar autoria |
| Cronograma, responsáveis por integrante e backlog de issues | Trabalho sob demanda, conforme instrução do usuário |

## 9. Revisão de consistência da consolidação

Esta seção fixa a leitura conjunta sem reescrever documentos históricos. Refinamento posterior explícito prevalece sobre descrição genérica anterior; não altera os arquivos de implementação nem torna contrato proposto uma API existente.

| Tema | Leitura consolidada / evidência |
|---|---|
| Domínio | Ar-condicionado evolui energia/desperdício residencial; ventilador e firmware preservados como legado. Escolha do usuário, aceitação acadêmica [N] |
| Baseline | [V] Inventário parte de `346f7de`; etapas posteriores só acrescentaram documentos/índice/ADRs, verificável por diff Git |
| Schema e nomes | V1 existente não é v2 proposto. Envelope v2 e tabela de conteúdos na arquitetura; schema união executável completo é entrega M00, não arquivo criado pelo plano |
| RUL | V2 usa `rul_calendar_hours`, horas simuladas de calendário; não alias de `rul_operating_hours` da v1. Artefato/model card e UI indicam unidade/escala |
| IDs e observed_at | Refinamento da etapa 4: gateway encaminha bytes da amostra imutáveis e registra observed_at confiável no journal PG; writer o inclui no derivado com ID novo; frame herda. Mesma identidade nunca muda hash por enriquecimento |
| Permissão do journal | M02/M04/M05 devem prover view/grant mínimo de leitura do carimbo por event_id ao writer, sem abrir acesso geral a payloads/segredos de outro serviço |
| AMQP | Bindings-alvo da etapa 3 prevalecem sobre topologia declarativa M00 v1. M00/M01 precisam testar que cada evento tem consumidor/rota prevista antes de ativar produtor |
| Fluxo de IA | Persisted alimenta inferência; frame com telemetria e previsão/status alimenta UI. Sem modelo, não inventar RUL; não contornar inferência com ligação direta ao 3D |
| Tempo/frescor | Relógio sintético fica só nos artefatos lab. Live exige UTC real e clock_scale=1; acelerar apenas progressão de degradação, nunca timestamps/janelas/expiry. Replay/seq antiga não vira dado atual por novo horário de recebimento |
| Ativação de modelo | Evento model.available só provoca consulta; versão precisa estar aprovada e corresponder a desired_version/activation_revision vigentes. Revalidar sob bloqueio antes da troca; active reflete processo real |
| Lease de recurso | TTL/renovação e fencing impedem efeitos de dono antigo; expiração entra em recovering. Não iniciar novo trabalho até comprovar parada anterior; token sozinho não libera CPU/RAM |
| Limites de jobs | Configuração-alvo permite até 5 M vetores inicialmente; M00 v1 tem limite diferente, portanto UI/backend v2 precisam concordar. Milhão é vetor equipamento/instante, não field |
| Sensores adicionais | Perfil mínimo seleciona cinco canais primários; sensores extras do lab não mudam dimensão do vetor live/modelo por acidente |
| Censura e targets | Health de verdade no lab não é previsão; RUL desconhecida não recebe falha fictícia. Modelos atuais apenas de classificação não satisfariam dois regressores |
| Retenção | Live/lab e journal têm limites propostos; não alterar retenção legada nem apagar pendência automaticamente para cumprir quota |
| Hardware | [V] Inventário consultou aproximadamente 15,7 GiB RAM e i5-12450H; [N] limites reais Docker/WSL, disco e desempenho ainda não medidos |
| CI e merge | Merge local autorizado por atualização do usuário; push/PR continuam pendentes. Se remoto exigir PR, não publicar main como contorno; reconciliação futura explícita |
| Status dos documentos | Consolidado significa planejamento redigido/coerente; não significa D0/CI/segurança/metas executados ou aprovados |

### 9.1 Decisões a validar na implementação, sem inventar resultado

| Item [N] | Módulo/ação que deve fechar a pendência |
|---|---|
| Patch/digest de imagens e modelo; suporte quorum/DLX/UID | M01 pin e smoke/scan; falhar instalação se garantia necessária não suportada |
| Schema união v2 gerado e fixtures completas | M00 validar Python/JSON Schema/TS e compatibilidade negativa |
| Grants management/PG/Influx e ACL efetivos | M01/M02/M04/M05/M06 com testes negativos reais |
| Revogação de credenciais históricas | M01/M17/M18 com confirmação no serviço; não copiar os valores para relatório |
| Memória Docker, disco e tempo LLM/geração/treino | M01/M11/M12/M16/M18 com NF e ensaio de 600 s |
| Dinâmica e limites de falha/saúde | M03/M11/M12 com configuração versionada, controles saudáveis e limites de validade |
| Perda/duplicação/recovery/restore | M02–M05/M09/M13/M18 com testes F e reconciliação |
| Acessibilidade/3D na máquina | M07/M14/M15/M18 com NF14/NF15 e inspeção manual |
| GitHub, checks/proteção e equipe | M17/M18, somente após autorização remota e confirmação dos integrantes |
| Aprovação acadêmica do novo equipamento/roteiro | Usuário confirma com avaliador; não presumir aceitação por código ou plano |

### 9.2 Verificações documentais desta etapa

[V] Foram conferidos os cinco capítulos, índice e oito ADRs: destinos e âncoras dos links locais, referências de linha dentro dos arquivos, fences Markdown balanceados e leitura dos blocos JSON. [V] Os oito ADRs têm até 20 linhas; o catálogo contém M00–M18, com grafo de dependências sem ciclo na verificação da etapa 4. [V] Este documento contém T01–T20, NF01–NF15, F01–F14, S01–S11 e 13 passos de demonstração cuja soma de budgets é 600 s. [V] O diff da consolidação contra o código-base foi limitado à documentação; a implementação não foi alterada. [N] Mermaid não foi renderizado graficamente nesta revisão e os testes operacionais planejados não foram executados. Verificação de padrões de segredos nos novos documentos não equivale a auditoria dedicada completa.

Revisão final autorizada nesta sessão: aprovação/seleção vigente antes de ativar modelo; renovação/perda de lease com fencing e recuperação sem sobreposição; relógio live em tempo real com aceleração apenas da degradação. Os três refinamentos foram incorporados às especificações e aos testes planejados; sua implementação e validação operacional permanecem [N].

## 10. Fechamento documental e próximos pedidos

O conjunto contém inventário, lacunas, arquitetura, oito ADRs, catálogo e aceite com rastreabilidade. Premissas adotadas: mesma máquina, split residencial convencional, cinco sensores, dois atuadores, stack obrigatória local, complexidade mínima, branch por mudança e merge local; nenhuma autorização de push/PR nem de implementação foi inferida.

Antes de declarar a solução pronta: preencher as evidências dos 20 requisitos e metas, tratar riscos e confirmar pendências da seção 9.1. Antes de iniciar implementação: revisão final deste conjunto pelo usuário e pedido explícito de módulo. Não confundir a conclusão desta etapa com ordem para executar M00 ou qualquer outro módulo.
