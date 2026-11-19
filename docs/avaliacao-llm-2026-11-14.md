# Avaliação delimitada do assistente local — 14/11/2026

**Decisão: candidato reprovado; nenhuma troca realizada. Avaliação encerrada.** Os demais componentes mantêm o aceite funcional anterior, com seus limites. Este registro não reabre a arquitetura geral.

**Decisão posterior do usuário:** manter o 1B provisoriamente e registrar o assistente como **atendimento parcial, com pendência de fidelidade semântica**. Esta etapa de avaliação está encerrada; não fazer novas tentativas de modelo ou ajustes sucessivos de prompt sem novo pedido.

Execução local de 14/11, 21:09–21:11 (UTC: 15/11/2026, 00:09–00:11). Evidência original em `evidence/llm/20261115T000912Z/{results,memory,limits}.json`, ignorada pelo Git. Operador reproduzível em [evaluate_llm.py](../tools/operations/evaluate_llm.py). Sem commit, publicação, download de outro modelo ou ensaio integrado de sete minutos.

## Candidato e método

- Atual: `llama3.2:1b-instruct-q4_K_M`, digest `22bc6b92eb0160c4629782fca05a9032c59d306ab2058b7dacc8a4644fbafa02`.
- Único candidato: `llama3.2:3b`, 3.2B/Q4_K_M, digest `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`, já presente no cache, ~2,02 GB em disco.
- Escolha: maior capacidade que o 1B, sem novo download/dependência; reavalia a alternativa anterior após a correção existente de `use_mmap`. Os timeouts históricos do 3B foram considerados, não apagados.
- Cinco perguntas fixas, uma resposta por pergunta/modelo, sem retry ou ajuste de prompt entre os modelos. Comparação serial: cinco chamadas 1B, depois cinco 3B. Uma partida fria por modelo, quatro chamadas quentes; sem histórico de conversa. Frio significa modelo descarregado, com `/api/ps` vazio; não houve limpeza do cache do sistema operacional nem reinício da máquina.
- Mesmo resumo congelado, capturado pelo backend: previsão válida, saúde **99,9%**, RUL **30,8 h**, nenhum alerta ativo, versão `mdl_edcc5fb6df9e49879f028ab2e9c7f178`. MAE de teste de saúde **0,532 pontos**, RUL **2,715 h**; RMSE **1,160 pontos / 3,388 h**; R² **0,998 / 0,879**. Não são medidas de acurácia em hardware real.
- O quinto caso é uma fixture declarada: previsão `insufficient_data`, dados antigos/ausentes e nenhum número atual. Não foi apresentado como estado real do dispositivo.
- A seleção de contexto por assunto do backend foi mantida. Os hashes dos cinco prompts coincidiram entre atual e candidato. O snapshot registra o estado na captura; não se alega que permaneceu atual durante toda a comparação.
- Usado o supervisor real do assistente, com sessão, auditoria, lease renovável, fencing e prova de parada. Somente no processo descartável do avaliador foram alterados o identificador/digest do LLM e a fonte de contexto congelada. Nenhuma resposta foi substituída por template.
- API pausada durante a comparação para usar sua trava exclusiva. Duas contas temporárias de visualização foram desativadas ao terminar. Ambos os modelos foram descarregados, a API foi retomada com a configuração 1B anterior e observada saudável ao fim da operação.

## Critério de decisão

Atender aos cinco temas, sem inversão conceitual, número/unidade incompatível com o contexto ou normalidade inventada; cumprir os limites existentes. Resposta incompleta não vale como atendimento integral. Concluir o stream não aprova conteúdo. O resultado operacional observado não comprova estabilidade ou p95.

## Revisão das dez respostas

| Caso / pergunta fixa | Atual 1B | Candidato 3B | Referência usada |
|---|---|---|---|
| RUL: significado, urgência de 10 h versus 100 h e valor atual | **Reprovado:** afirma que 100 h é mais urgente; inventa exemplos adicionais e omite 30,8 h | **Reprovado:** evita reconhecer a maior urgência relativa de 10 h e declara RUL indisponível apesar de 30,8 h no contexto | Vida útil restante estimada, horas de calendário; menor tempo restante exige maior atenção em condições comparáveis; previsão válida disponível |
| Saúde física versus qualidade da regressão, com saúde atual | **Parcial:** distingue os conceitos de forma genérica, mas não informa 99,9% solicitado | **Reprovado:** cita 99,9 corretamente e depois apresenta RUL de 30,8 h como qualidade/confiabilidade da regressão | Saúde pertence ao compressor; qualidade é avaliada por erros e ajuste no teste |
| MAE/RMSE/R² e MAEs da versão com unidades | **Reprovado:** confunde raiz/média, associa métrica a um timestamp e inventa interpretação de horas; termina incompleto | **Parcial:** melhora as definições, mas termina sem citar MAEs e unidades solicitados | Saúde 0,532 pontos; RUL 2,715 h; RMSE é raiz da média de erros quadráticos; R² não é saúde |
| Arquitetura local e funções de bancos/brokers | **Reprovado:** atribui histórico e exibição de dados aos brokers; fluxo incompleto | **Parcial:** descreve melhor bancos e caminho de dados; omite Ollama e termina o caminho inverso incompleto; trata processamento dos consumidores de modo impreciso | Brokers transportam; writer grava Influx; PostgreSQL relacional; inferência publica resultado; API/WS entrega; Ollama local recebe resumo |
| Previsão indisponível, leituras ausentes, normalidade e limpeza de alerta | **Atendeu neste caso:** não fabrica números, não conclui normalidade nem autoriza limpeza | **Atendeu neste caso:** reconhece insuficiência e não fabrica números/normalidade/limpeza | Ausência não equivale a saúde 100, RUL zero ou recuperação |

Os dois modelos atingiram 256 tokens nos casos métricas e arquitetura, com respostas incompletas. O teto de saída não foi aumentado. Não foi executada uma rodada adicional com perguntas ajustadas para selecionar uma resposta favorável.

### Erro conceitual versus resposta incompleta

| Categoria | Evidência observada | Interpretação |
|---|---|---|
| Erro conceitual em resposta sem corte pelo teto | 1B inverte urgência de RUL (147 tokens); 3B usa RUL como qualidade da regressão (159 tokens) | Conteúdo incorreto, independente do limite de 256 tokens |
| Erro de fidelidade em resposta sem corte pelo teto | 3B declara RUL indisponível apesar de 30,8 h na entrada (78 tokens) | Contradição com dados estruturados, não falta de espaço |
| Omissão sem atingir teto | 1B não cita a saúde atual solicitada (82 tokens) | Resposta incompleta, mas não atribuível ao limite de saída |
| Respostas incompletas ao atingir teto | Métricas e arquitetura chegam a 256 tokens nos dois modelos e terminam sem partes solicitadas | Corte compatível com o limite; não se sabe o que seria produzido com mais tokens e não se presume correção |
| Erro já presente antes do corte | 1B associa MAE a timestamp/unidade indevida e atribui histórico/interface aos brokers | O corte não justifica nem elimina essas afirmações erradas |

No 3B, as definições de métricas melhoraram, mas os MAEs/unidades pedidos não chegaram à resposta; essa falta de cobertura não é classificada, por si só, como erro conceitual. A rejeição não depende apenas dessas omissões: os casos RUL/saúde já apresentam falhas independentes do teto.

## Latência observada

Tempos em segundos. Primeiro fragmento é medido a partir do início da geração pelo supervisor; total inclui contexto/auditoria/finalização. A primeira pergunta é a única partida fria de cada modelo.

| Caso | 1B: primeiro fragmento | 1B: total | 3B: primeiro fragmento | 3B: total |
|---|---:|---:|---:|---:|
| RUL — frio | 6,930 | 11,283 | 24,297 | 30,138 |
| Saúde — quente | 0,291 | 2,572 | 0,725 | 12,409 |
| Métricas — quente | 1,541 | 9,136 | 4,254 | 23,836 |
| Arquitetura — quente | 0,670 | 8,276 | 2,216 | 21,775 |
| Ausência — quente | 1,321 | 4,912 | 4,018 | 11,284 |

Todas as dez chamadas cumpriram os limites existentes de **30 s até o primeiro fragmento** e **90 s totais**. Os **24,3 s a frio do 3B estão dentro do limite**, com margem observada de ~5,7 s. Uma partida fria por modelo e quatro chamadas quentes **não comprovam estabilidade, p95 ou ausência de futuros timeouts**. Os timeouts anteriores continuam relevantes.

## Memória observada e parâmetros preservados

Container Ollama mantido em **4 GiB / 4 CPUs**. Docker disponibilizava 8.183.754.752 bytes (~7,62 GiB); demais serviços continuaram ativos, exceto a API temporariamente pausada. Contexto 2.048, saída 256 tokens, quatro threads, `use_mmap=true`, temperatura 0,2, seed 42; nenhuma alteração de recurso ou timeout.

| Medida máxima amostrada no container Ollama | Atual 1B | Candidato 3B |
|---|---:|---:|
| Working set: `memory.current - inactive_file` | 1.789,9 MiB (~1,75 GiB) | 4.038,5 MiB (~3,94 GiB) |
| `memory.current`, inclui cache/kernel | 2.319,6 MiB | 4.094,9 MiB |
| Memória anônima do cgroup | 786,5 MiB | 1.882,9 MiB |
| Amostras | 28 | 76 |

Amostragem solicitada a cada segundo, com overhead de Docker/IO: são máximos **observados**, não pico contínuo garantido nem RAM exclusiva dos pesos do modelo. Working set inclui páginas ativas mapeadas; memória anônima sozinha subestima o uso com mmap. Não houve OOM observado na execução (`OOMKilled=false`). O 3B ocupou ~98,6% do limite pelo working set e quase todo o limite em `memory.current`; a margem observada é pequena. Não se afirma que um OOM futuro é inevitável.

## Decisão e reversão

O 3B concluiu as cinco chamadas e melhorou partes do texto, mas **não atende ao critério de fidelidade** e tem pouca margem de RAM. Não foi promovido. O 1B também não é aprovado semanticamente; preservá-lo é reversão da configuração, não declaração de atendimento.

Nenhuma modificação em `local_llm.py`, `ollama.py`, `model_init.py` ou Compose foi necessária. Cache/digests anteriores preservados. A retomada usou o mesmo container/configuração da API; não houve novo ensaio integrado ou alteração dos outros componentes. Ruff/format do operador passaram. Uma verificação posterior encontrou o Docker indisponível; causa não investigada neste escopo e não atribuída ao candidato. A saúde da API citada acima é a observação ao término do avaliador, não garantia do estado posterior.

Avaliação encerrada, sem terceiro candidato. Conforme decisão do usuário, assistente registrado como parcial e 1B mantido provisoriamente. Valores/definições determinísticos podem ser exibidos separadamente, mas não serão apresentados como resposta gerada nem usados para converter esta reprovação em aprovação. A proposta de UI/UX está separada e não altera esse resultado.
