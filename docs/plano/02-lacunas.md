# Etapa 2 — Análise de lacunas

Referência: 08/11/2026; base documental `8b00596`; implementação inventariada em `346f7de`, sem mudanças de código desde então. Branch: `docs/plano-etapa-2-lacunas`. Complementa o [inventário](./01-inventario.md).

## 1. Critério de leitura

Todo estado descreve a implementação atual: **Atende** significa que há implementação e evidência no nível indicado, não aceite integrado; **Parcial** significa cobertura incompleta; **Não existe** significa ausência da funcionalidade operacional no conjunto rastreado consultado. Contratos, fixtures e planos não contam como serviço em execução.

Selos: [V] leitura/comando; [I] inferência com base declarada; [N] não confirmado. Recomendações estão identificadas como propostas e não como fatos sobre hardware real. A matriz deve ser revalidada na apresentação; os testes da sessão anterior não substituem os fluxos completos.

## 2. Matriz dos 20 requisitos

| # | Requisito | Estado | Evidência | O que falta |
|---|---|---|---|---|
| 1 | Vue/React, TS e Vite | Atende | [V] [package.json:20](../../web-smart-fan-iot/frontend/package.json#L20); build executado nesta sessão, registrado no inventário | Ampliar navegação para as páginas exigidas; integração final pendente |
| 2 | Python/FastAPI e REST | Atende | [V] [main.py:108](../../web-smart-fan-iot/backend/app/main.py#L108); testes REST executados na sessão | Versionar API, adicionar auth, jobs e rotas AIoT |
| 3 | WebSocket | Parcial | [V] [main.py:362](../../web-smart-fan-iot/backend/app/main.py#L362), [useWebSocket.ts:21](../../web-smart-fan-iot/frontend/src/composables/useWebSocket.ts#L21) | Ticket, autorização, eventos AIoT e reconexão com backoff; fluxo integrado não reexecutado |
| 4 | MQTT/Mosquitto bidirecional | Parcial | [V] [mqtt_service.py:51](../../web-smart-fan-iot/backend/app/mqtt_service.py#L51), [main.cpp:274](../../esp32-simulador/src/main.cpp#L274) | Simulador Python, gateway, ACL, autenticação, novo envelope e confirmação correlacionada |
| 5 | Pelo menos 3 sensores | Parcial | [V] [main.cpp:322](../../esp32-simulador/src/main.cpp#L322): corrente analógica, tensão constante, potência derivada | Simular cinco canais HVAC independentes/coerentes; campos derivados não multiplicam sensores |
| 6 | Pelo menos 2 atuadores | Parcial | [V] [main.cpp:30](../../esp32-simulador/src/main.cpp#L30): um relé; [contracts.py:104](../../packages/smartfan_common/src/smartfan_common/contracts.py#L104): dois estados apenas declarados | Compressor e ventilador da condensadora operacionais, com efeitos observáveis |
| 7 | Equipamento com degradação em 3 variáveis | Não existe | [V] Firmware de [main.cpp:322](../../esp32-simulador/src/main.cpp#L322) não modela desgaste; M00 declara medições | Modelo de degradação progressiva do compressor e cenário de falha |
| 8 | Atuador automático por regra | Parcial | [V] [scheduler.py:17](../../web-smart-fan-iot/backend/app/scheduler.py#L17): desligamento por horário | Termostato, proteção térmica, histerese e intertravamentos no domínio HVAC |
| 9 | Atuador controlado pela Web | Parcial | [V] [main.py:151](../../web-smart-fan-iot/backend/app/main.py#L151), [App.vue:264](../../web-smart-fan-iot/frontend/src/App.vue#L264) | Controle HVAC com ID, prazo, ACK e retorno nos sensores; o fluxo atual controla apenas relé legado |
| 10 | RabbitMQ e Mensageria | Não existe | [V] [docker-compose.yml:1](../../web-smart-fan-iot/docker-compose.yml#L1) sem broker AMQP; [topology.py:19](../../packages/smartfan_common/src/smartfan_common/topology.py#L19) é declarativo | Topic exchange, consumidores, quatro filas operacionais, jobs, retries, DLQ, permissões por serviço e tela via backend |
| 11 | PostgreSQL e InfluxDB | Parcial | [V] [models.py:9](../../web-smart-fan-iot/backend/app/models.py#L9), [mqtt_service.py:101](../../web-smart-fan-iot/backend/app/mqtt_service.py#L101) | Usuários, regras, alertas e auditoria; migrações, novo schema de telemetria e isolamento lab |
| 12 | Dashboard, gráficos e histórico | Atende | [V] [App.vue:593](../../web-smart-fan-iot/frontend/src/App.vue#L593), [main.py:268](../../web-smart-fan-iot/backend/app/main.py#L268); testes/build registrados | Ampliar indicadores para HVAC/IA e demonstrar histórico real integrado |
| 13 | Cadastro e gestão IoT | Parcial | [V] [main.py:127](../../web-smart-fan-iot/backend/app/main.py#L127): criar/listar/consultar | UI de gestão, edição/desativação, capacidades, validação, papéis e auditoria |
| 14 | Cena 3D só por WS | Não existe | [V] `git ls-files`, dashboard e [package.json:20](../../web-smart-fan-iot/frontend/package.json#L20) sem biblioteca/cena 3D | Cena, painel de item, cores/alertas, dois efeitos ambientais e congelamento por falta de dados |
| 15 | Gerador massivo configurável | Não existe | [V] Manifestos e lista rastreada sem gerador; [contracts.py:300](../../packages/smartfan_common/src/smartfan_common/contracts.py#L300) apenas descreve job | NumPy em blocos, >=1 milhão de leituras, seed, falhas, ruído, UI, progresso, limite e job AMQP |
| 16 | Dois regressores e avaliação | Não existe | [V] [requirements.txt:1](../../web-smart-fan-iot/backend/requirements.txt#L1) sem ML; [features.py:90](../../packages/smartfan_common/src/smartfan_common/features.py#L90) calcula features, não modelos | Treino, split por equipamento, baseline, métricas/gráficos/importância, versão e hot-reload |
| 17 | Saúde, RUL e alertas ao vivo | Não existe | [V] [contracts.py:258](../../packages/smartfan_common/src/smartfan_common/contracts.py#L258) define tipos, sem consumidor de inferência rastreado | Inferência via RabbitMQ, histerese, validade, abstenção e página Insights |
| 18 | Assistente LLM local | Não existe | [V] Compose e conjunto rastreado sem Ollama/assistente | Modelo CPU, resumo backend, streaming, Markdown sem HTML, limites, timeout e auditoria |
| 19 | Compose sobe tudo | Parcial | [V] [docker-compose.yml:1](../../web-smart-fan-iot/docker-compose.yml#L1): cinco serviços do legado | Todos os novos serviços, bootstrap, readiness, volumes, usuários sem root e exposição mínima |
| 20 | GitHub, equipe e README | Parcial | [V] `git remote -v`, `git log`, `git shortlog`; [README.md:1](../../README.md#L1) | README da solução consolidada e demonstração; [N] identidade/contribuição de todos os integrantes e proteção remota |

### Segurança transversal e simulador

[V] O backend não exige JWT nas rotas lidas e WS usa somente verificação de Origin ([main.py:119](../../web-smart-fan-iot/backend/app/main.py#L119), [main.py:362](../../web-smart-fan-iot/backend/app/main.py#L362)). [V] Mosquitto aceita anônimo ([mosquitto.conf:3](../../web-smart-fan-iot/mosquitto/config/mosquitto.conf#L3)). Faltam três papéis, bcrypt, limite de tentativas, auditoria e ticket WS de uso único; essa lacuna afeta os requisitos 2, 3, 4, 9, 10, 11, 13, 15, 16, 18 e 19.

[V] Os Dockerfiles da [API:1](../../web-smart-fan-iot/backend/Dockerfile#L1) e do [frontend:1](../../web-smart-fan-iot/frontend/Dockerfile#L1) não declaram usuário sem root; [Compose:1](../../web-smart-fan-iot/docker-compose.yml#L1) publica também portas da API, MQTT e bancos em loopback. A configuração-alvo deve distinguir frontend público, portas internas e interfaces administrativas locais.

[V] Há literais de credenciais em configuração histórica, conforme [inventário, seção 7.3](./01-inventario.md#73-verificação-de-segredos-sem-exposição-de-valores). [N] Revogação efetiva não confirmada. Nenhum valor será copiado para documentação ou exemplos.

[V] O dispositivo atual é Arduino/ESP32 ([platformio.ini:1](../../esp32-simulador/platformio.ini#L1)). Proposta: simulador Python passa a ser o único dispositivo da execução final; firmware e circuito Wokwi permanecem como legado documentado, sem fazer parte do Compose AIoT. Destino físico definitivo dos arquivos será registrado em ADR, sem movê-los nesta etapa.

## 3. Continuidade: ventilador para ar-condicionado

| Aspecto | Continuidade proposta |
|---|---|
| Problema original | Reduzir desperdício residencial por funcionamento prolongado e entender energia/custo |
| Evolução | Acrescentar conforto térmico, carga de trabalho e manutenção preditiva do compressor |
| Por que ar-condicionado | Mais relações úteis entre ambiente, esforço, degradação e eficiência; não desqualifica o monitoramento de ventiladores |
| Modelo mínimo | Split convencional liga/desliga; sem inversor, aquecimento, circuito refrigerante detalhado ou controle de pressão |
| Clima | Temperatura externa variável e ciclos diários; calor aumenta carga sem significar falha |
| Vida do aparelho | Horas ligadas, partidas e esforço térmico acumulados; idade cronológica é contexto, não diagnóstico |
| Limite das previsões | Saúde/RUL estimadas para o cenário sintético; não equivalem à vida útil certificada de um produto real |

[V] A continuidade se apoia no problema declarado no [README.md:3](../../README.md#L3) e nos contratos HVAC já existentes ([contracts.py:91](../../packages/smartfan_common/src/smartfan_common/contracts.py#L91)). A escolha de domínio foi confirmada pelo usuário. [N] Aceitação da mudança pelo professor ainda não confirmada.

## 4. Sensores e atuadores mínimos

### 4.1 Sensores

Todos os canais abaixo são propostos como simulados em Python; [V] seus nomes já existem em [contracts.py:91](../../packages/smartfan_common/src/smartfan_common/contracts.py#L91). Limites daquele schema são estruturais amplos, não faixas saudáveis de fabricante.

| Canal | Unidade | Papel e resposta esperada no simulador |
|---|---|---|
| `current_a` | A | Esforço elétrico do compressor; desligado reduz componente de corrente do compressor, sem apagar consumo do ventilador |
| `vibration_rms_mm_s` | mm/s RMS | Vibração escalar do compressor; desgaste altera média/variabilidade; não simula espectro de alta frequência |
| `compressor_case_temp_c` | °C | Temperatura da carcaça; sobe com carga/desgaste e esfria progressivamente após desligamento |
| `indoor_temp_c` | °C | Ambiente interno; responde à refrigeração, carga térmica e troca com exterior |
| `outdoor_temp_c` | °C | Ambiente externo; ciclo diário, sazonalidade simples e variabilidade entre cenários |

Proposta inicial: uma leitura por equipamento a cada 2 s no modo live; dados sintéticos usam a mesma semântica de janela, com passo configurável e compatibilidade validada. Potência é derivada do modelo elétrico do aparelho e dos dois atuadores; não conta como sexto sensor independente. Não reutilizar automaticamente a tensão e o fator de potência do ventilador.

Umidade, fluxo de ar, rotação e vazão de condensado são evoluções possíveis. Para um split com drenagem por gravidade, água é condensado, não circuito de refrigeração a água. Ausência de vazão não comprova entupimento sem contexto de umidade e operação. Filtros, fluxo de ar e dreno são aspectos de manutenção reconhecidos pelo [Natural Resources Canada](https://natural-resources.canada.ca/energy-efficiency/energy-star/air-conditioning-your-home); os cinco canais iniciais não permitem diagnóstico conclusivo desses defeitos.

### 4.2 Atuadores, autoridade e intertravamentos

| Atuador | Controle mínimo proposto | Efeito observável |
|---|---|---|
| Compressor | Automático por temperatura interna e setpoint, com histerese; comando de parada e proteção têm prioridade | Aumenta corrente/potência e vibração; reduz temperatura interna com atraso; carcaça tem inércia térmica |
| Ventilador da condensadora | Comando direto ON/OFF na Web, sujeito a intertravamento; automático pode ligá-lo antes de liberar compressor | Muda estado e consumo; altera dissipação térmica quando há refrigeração |

Regras propostas para detalhar na arquitetura:

1. Compressor nunca permanece ligado com ventilador externo desligado. Pedido manual de desligar o ventilador interrompe o compressor e estabelece bloqueio manual de refrigeração, visível na UI, até liberação explícita; o automático não desfaz a intenção silenciosamente.
2. Comando ON do ventilador não liga obrigatoriamente o compressor; permite demonstrar controle manual com efeito próprio no consumo.
3. Prioridade: proteção/intertravamento > parada manual > agenda > termostato. Mostrar motivo, estado desejado, pendente e observado separadamente.
4. Ponto inicial de simulação: setpoint 24 °C, liga acima de 25 °C, desliga abaixo de 23 °C, espera mínima de 180 s após parada. São parâmetros didáticos ajustáveis, não especificações universais; versão e valores ficam na configuração auditada.
5. Proteção térmica usa limite configurado para o aparelho simulado; limite de saúde não deve ser copiado do máximo estrutural do schema. Reinício exige condição segura e intervalo mínimo.
6. Partida de uma demonstração não exige espera artificial se o aparelho estiver elegível; tentativas durante bloqueio devem mostrar contagem restante, sem burlar proteção.
7. ACK só confirma aplicação pelo simulador; mudança do estado deve reaparecer nas leituras seguintes. OFF pode ser idempotente e aplicado mesmo se já estiver desligado.

O estado mínimo do ventilador interno será abstraído pelo modo do aparelho, com consumo e efeito térmico documentados; não contará como terceiro atuador nem terceiro sensor. Se essa abstração impedir coerência física suficiente, adicionar ventilador interno será uma evolução explícita, não serviço novo.

## 5. Degradação e assinaturas de falha

As relações abaixo são **hipóteses do gerador**, com ruído, atraso, heterogeneidade por equipamento e sobreposição de estados. Não são regras diagnósticas validadas em aparelhos reais. A falha operacional será definida por um limiar latente de degradação ou perda sustentada de capacidade, com parâmetros versionados no manifesto, nunca enviados no live.

| Cenário | Variáveis afetadas | Assinatura esperada no modelo sintético | Tratamento |
|---|---|---|---|
| Desgaste mecânico progressivo do compressor | Vibração, corrente e temperatura da carcaça | Tendência de aumento gradual das três durante operação, com sensibilidade variável e ruído | Modo principal para saúde e RUL; atende a três variáveis de degradação |
| Redução progressiva de dissipação da condensadora | Carcaça, corrente e taxa de resfriamento interno | Carcaça mais quente para exterior semelhante; esforço maior e refrigeração mais lenta | Segundo modo simples, calibrado no simulador; sem atribuir toda anomalia a desgaste mecânico |
| Desequilíbrio mecânico | Vibração dominante; corrente e carcaça secundárias | Vibração cresce antes de alterações térmicas/elétricas relevantes | Evolução; não exigir que todos os sensores subam simultaneamente |
| Sensor com deriva ou travado | Um canal; coerência com demais | Desvio gradual ou leitura constante incompatível com mudanças de carga | Defeito de qualidade; não rotular automaticamente equipamento como condenado |
| Dia mais quente ou carga térmica maior | Exterior, interior, corrente e tempo ligado | Maior esforço em máquina saudável, sem aumento mecânico obrigatório | Controle negativo essencial para reduzir falso positivo |
| Uso prolongado saudável | Horas acumuladas e ciclos | Temperatura estabiliza sob carga; consumo coerente, sem falha inevitável no horizonte | Deve aparecer no dataset, evitando aprender que tempo ligado sempre é defeito |

Desgaste acumula com horas de operação, ciclos e esforço térmico; taxas latentes variam por máquina e não são features. Falha mecânica e defeito de sensor usam rótulos distintos. A UI informa anomalia/limitação, sem prometer identificar a causa exata com esses cinco canais.

## 6. Dados exigidos para a IA

### 6.1 Contagem, geração e rótulos

Proposta: contar **uma leitura como um vetor de um equipamento em um instante**, com os cinco canais e estados. O mínimo será >=1.000.000 desses registros; não multiplicar a contagem por fields ou por pontos resultantes do pivot do InfluxDB. Gerar em blocos NumPy, com teto inicial configurável de 5 milhões de registros, manifesto e progresso pelo RabbitMQ. Limites de memória e tempo serão medidos nas etapas posteriores, não garantidos aqui.

| Dado | Definição proposta | Onde pode existir |
|---|---|---|
| `health_true` | Índice sintético 0..100 derivado da degradação latente versionada; não de uma regra idêntica aplicada às leituras visíveis | Artefato de treino, separado do vetor de features |
| `rul_true_hours` | Horas simuladas de calendário até primeira falha do equipamento sob o perfil operacional gerado: `(failure_at - sample_at)/3600` | Somente treino para trajetórias com falha observada |
| `is_degrading`, `failure_mode`, `failure_at` | Verdade sintética e diagnóstico do cenário | Artefato/manifesto do laboratório; nunca telemetria live |
| `censored` | Equipamento ainda não falhou quando o horizonte termina | Rótulo de laboratório, nunca entrada da regressão |
| `health_predicted`, `rul_predicted_hours` | Saídas dos modelos, com versão e qualidade | Eventos de inferência e UI, claramente distintos de verdade |

Equipamentos censurados não recebem RUL zero nem tempo até o fim do dataset como falha fictícia. Para manter regressão simples, ficam fora da perda supervisionada de RUL e permanecem no treino de saúde e na avaliação de falsos alarmes. Relatar a proporção excluída e o viés para máquinas que falharam; modelos de sobrevivência ficam fora do mínimo.

A RUL depende do perfil de uso futuro que o gerador impõe. A inferência informa estimativa condicional ao cenário, sem acesso a esse futuro. O laboratório percorre horas simuladas em artefatos; no live, timestamp e cadência usam tempo real, com clock_scale=1. A demonstração pode acelerar apenas a progressão da degradação, com cenário identificado e seu efeito no modelo medido; não acelerar timestamps, prazos de comandos ou janelas. RUL continua expressa em horas de calendário do cenário de treino, sem converter automaticamente para uma contagem regressiva da demonstração.

Parâmetros da UI: número de equipamentos e sensores por tipo, dias simulados, proporção de falhas, modos ativos, ruído, faltantes, outliers, seed, passo temporal e teto de registros. Proposta mínima: um sensor de cada tipo por equipamento para o perfil HVAC inicial; quantidades adicionais devem usar perfis/identidades suportados, sem introduzir arrays incompatíveis com M00 silenciosamente. Contrato dessa parametrização será fechado na etapa 3.

### 6.2 Features, causalidade e qualidade

[V] A implementação atual compartilhada tem 18 features: média, desvio e inclinação de cada um dos cinco canais; diferença média carcaça/exterior; taxa de resfriamento interno; cobertura mínima dos canais ([features.py:16](../../packages/smartfan_common/src/smartfan_common/features.py#L16)). Não inclui máximos; acrescentá-los exige nova versão, ordem explícita e novo treino.

| Tema | Estado atual e proposta |
|---|---|
| Janela | [V] M00 usa 60 s, span mínimo 30 s, >=3 amostras, cobertura >=80%, lacuna máxima 5 s, <=300 amostras e <=1000 equipamentos ([features.py:30](../../packages/smartfan_common/src/smartfan_common/features.py#L30)); validar essas escolhas com cadência proposta de 2 s |
| Reinício | [V] M00 limpa a janela por boot, lacuna ou transição do compressor; compressor desligado gera `inactive` ([features.py:90](../../packages/smartfan_common/src/smartfan_common/features.py#L90)) |
| Causalidade | [V] M00 recebe eventos ordenados e recusa tempos/seq antigos; [I] treino deve reproduzir exatamente o mesmo caminho, inclusive aquecimento e reinícios |
| Faltantes | [V] Contrato representa nulos e lista consistente de canais ausentes ([contracts.py:109](../../packages/smartfan_common/src/smartfan_common/contracts.py#L109)); [V] features não convertem nulo em zero e abstêm-se sem cobertura suficiente |
| Outliers | Proposta: não apagar a evidência bruta; valores impossíveis rejeitados/quarentenados pelo contrato, extremos plausíveis preservados; política robusta adicional só entra com versão comum a treino e live |
| Pré-processamento aprendido | Proposta: Pipeline ajustada só no treino; sem interpolação futura, média de todo o dataset ou normalização usando teste |
| Predição ausente | Proposta: `warming_up`, `insufficient_data`, `inactive`, `stale` ou modelo indisponível; nunca fabricar saúde 100 ou RUL numérica |

`coverage` de features é fração de campos presentes nas observações retidas, não cobertura temporal do gráfico. Temperatura externa elevada e horários de uso entram como contexto observado, jamais como rótulo direto de falha.

### 6.3 Divisão, modelos e avaliação

Proposta mínima: dois regressores independentes, um para saúde e outro para RUL, com baseline de média para cada alvo. Iniciar com família de árvores de complexidade limitada; algoritmo e hiperparâmetros serão definidos na arquitetura, após avaliar custo e dados. Não é necessário criar um serviço por modelo.

- Divisão inicial por equipamento: 60% treino, 20% validação, 20% teste; IDs sem interseção e seed registrada. Quantidade de máquinas deve viabilizar falhas nos grupos e diversidade de cenários; a UI recusa configuração incapaz de avaliar os alvos.
- Particionar por ID antes de qualquer ajuste estatístico. Janelas nunca cruzam equipamento, boot ou fronteira de partição. Seed e parâmetros latentes não entram nas features.
- Reservar teste para avaliação final de candidatos previamente selecionados na validação; não repetir promoção por consultas sucessivas ao mesmo teste.
- Exibir MAE, RMSE, R², previsto versus real, importância dos atributos e métricas do baseline, por alvo. Reportar também avaliação por equipamento e por modo de falha, evitando ocultar máquinas ruins sob média global.
- Candidato deve vencer baseline e política de comparação com versão atual em conjunto comparável; se não vencer, registrar rejeição. Não promover candidato só porque o treino terminou.
- Investigar R² praticamente perfeito, erros quase nulos, dependência exagerada de uma feature e desempenho muito diferente entre seeds; isso é sinal de auditoria, não prova automática de leakage.
- Avaliar alerta por sequência de previsões, não apenas erro pontual: histerese proposta de 3 previsões válidas para ativar e 10 para limpar; tempos sem dados não contam como melhora.

O split por grupo e o pré-processamento aprendido somente no treino seguem a prevenção de vazamento descrita na [documentação scikit-learn](https://scikit-learn.org/stable/common_pitfalls.html). As proporções e regras de promoção são propostas do projeto, não prescrições dessa fonte.

## 7. Impacto no InfluxDB e separação de dados

[V] O legado grava `electrical_measurement`, tag `device_id` e fields elétricos; a consulta de métricas filtra esse measurement ([mqtt_service.py:101](../../web-smart-fan-iot/backend/app/mqtt_service.py#L101), [main.py:309](../../web-smart-fan-iot/backend/app/main.py#L309)). A evolução não deve reinterpretar registros antigos como medições HVAC nem apagar o histórico para viabilizar o novo schema.

### 7.1 Modelo inicial proposto — a fechar em ADR

| Área | Measurement/armazenamento | Tags e fields | Política inicial |
|---|---|---|---|
| Legado | `electrical_measurement` no bucket atual | Manter nomes e tipos existentes | Não alterar retenção sem inspeção e autorização de migração |
| Live HVAC | Bucket `live`, measurement `hvac_telemetry` | Tags: `device_id`, `zone`, `equipment_type`; fields: cinco canais, `power_w`, dois estados booleanos, `event_id`, `boot_id`, `sequence`, `received_at` e indicadores de qualidade | Retenção proposta de 30 dias; timestamp do evento preservado |
| Insights | Bucket `live`, measurement `hvac_insight` | Mesmas tags; saúde, RUL, versão do modelo, versão de features, evento-fonte, status e timestamp da amostra como fields | 30 dias; UI distingue idade da previsão e da telemetria |
| Laboratório visual | Bucket `lab`, measurement `hvac_lab_sample` | Tags de equipamento e cenário com conjunto limitado; `dataset_id` como field; leituras sem verdade latente | Retenção proposta de 7 dias e amostra <=100 mil registros por dataset; teto global de amostras definido na arquitetura |
| Dataset completo | Arquivos NumPy em blocos/artefatos e manifesto; metadados no PostgreSQL | Features/leituras e rótulos separados logicamente; hash, seed, versão e identidade de equipamento | >=1 milhão de registros; retenção por política de artefatos, sem limpeza automática de modelos em uso |
| Alertas/auditoria | PostgreSQL | Estado, motivos, transições, autoria, correlação | Não tratar InfluxDB como registro transacional principal |

O milhão de leituras do laboratório é comprovado no artefato, não na amostra visual. O ensaio de capacidade de ingestão/consulta de 1 milhão no InfluxDB será separado e controlado, sem misturar massa de teste com live. O prazo de retenção não dispensa backup.

As recomendações de tags para filtros e controle de cardinalidade seguem o [schema design do InfluxDB OSS v2](https://docs.influxdata.com/influxdb/v2/write-data/best-practices/schema-design/). Esta análise não propõe migrar para InfluxDB 3.

### 7.2 Tipos, cardinalidade, identidade e lacunas

- Identificadores de evento, boot, dataset, correlação e versão de modelo não serão tags de cardinalidade crescente. IDs de equipamento são tags com cadastro limitado; `zone` e `equipment_type` precisam de vocabulário controlado.
- Estimativa conservadora de combinações: equipamentos x zonas x tipos, observando que um equipamento normalmente pertence a apenas uma zona/tipo por período; registrar mudanças de localização. Quantidade de registros e fields também impacta disco, mesmo sem novas combinações de tags.
- Nulos não são escritos como zero. O writer omite o field ausente e registra qualidade; consultas fazem pivot/alinhamento para reconstruir a leitura sem exigir que todos os fields estejam presentes.
- Tipos por field são fixos: estados booleanos, sensores floats, sequência inteira e identidades strings. Evitar conflito entre inteiro e float; usar outro measurement se houver mudança incompatível.
- Identidade de ponto Influx é measurement + tags + timestamp, não `event_id` guardado em field. Writer deve preservar a chave determinística no retry; timestamps não podem ser recriados na reentrega. Colisão de duas amostras distintas do mesmo equipamento no mesmo instante será rejeitada/quarentenada ou resolvida por política explícita na etapa 3.
- `event_id` em field auxilia rastreabilidade, mas não cria sozinho idempotência. Publicar confirmação de persistência exige política de ACK e deduplicação que cubra falha entre gravação e publicação; será detalhada na arquitetura.
- Não iniciar consulta de milhão de leituras retornando todos os pontos à UI. Amostragem/agrupamento para gráfico é separado da integração de energia, contagens e métricas sobre dados brutos.
- Restrições atuais de consulta (168 h e 400 mil amostras) precisam de revisão para capacidade, sem simplesmente remover os limites ([main.py:268](../../web-smart-fan-iot/backend/app/main.py#L268)).

## 8. Premissas, lacunas e próximos contratos

| Tipo | Registro |
|---|---|
| Decisão confirmada | Ar-condicionado, mesma máquina, complexidade mínima e documentação completa antes de implementação |
| Proposta a consolidar na etapa 3 | Dois atuadores com intertravamento, cinco sensores, RUL em horas simuladas de calendário, schemas e retenções acima |
| [V] Compatibilidade existente | M00 já usa os nomes HVAC; contratos operacionais ainda são legados; não alterar nenhum deles nesta etapa |
| [N] Calibração | Relações físicas, limites saudáveis e definição de falha não validados em hardware/fabricante |
| [N] Recursos | Tempo para gerar milhão, memória do dataset/treino, cardinalidade real, capacidade Influx e concorrência com Ollama não medidos |
| [N] Operação | Fluxos integrados, perdas, backup/restore e revogação de credenciais históricas não ensaiados |
| [N] Organização | Contribuições de todos os integrantes, proteção de branch e aceite acadêmico da evolução não confirmados |
| Próximos contratos | Envelope em português versus nomes existentes em inglês; identidade de sensor adicional; tempo simulado versus frescor real; identidade de ponto; ACK/idempotência; erros API e eventos WS |

Nenhum requisito ausente será marcado como concluído apenas por adicionar sua dependência ou seu contrato. A etapa seguinte é a arquitetura-alvo e seus ADRs; esta entrega não autoriza iniciar módulos de implementação.
