# UI/UX — Mensageria e Auditoria — 15/11/2026

## Escopo entregue
Mensageria e depois Auditoria, reutilizando Card, Badge, tipografia, foco, cores e detalhes de identificação do padrão aprovado. Sem dependências novas, alterações no backend/LLM, mudanças de permissões, commit ou publicação remota. Aguardar avaliação visual antes de expandir.

## Mensageria
- Filas de trabalho primeiro: nome de apresentação, mensagens pendentes, em processamento, consumidores e taxas em msg/s. Nomes técnicos, serviço, tipo, estado e durabilidade em detalhes.
- Fila vazia exige estado running, consumidor presente e zero pendentes/em processamento. Consumidor ausente e fila indisponível têm estados próprios. DLQ administrativa fica separada, sem interpretar ausência de consumidor como incidente de uma fila de trabalho.
- DLQ mantém todas as estatísticas disponíveis em detalhes; registro de falhas e mensagens recentes são seções distintas. Códigos conhecidos traduzidos por lista explícita, originais mantidos em detalhes. IDs completos disponíveis com cópia.
- Horário de atualização vem de sampled_at; badge estável entre consultas. Falha de consulta preserva contadores e indica dados antigos. Resposta bem-sucedida com amostragem antiga também é identificada. Janela de atualidade exclusivamente visual: duas consultas de cinco segundos mais cache_seconds anunciado (12 s com cache de 2 s); não altera contrato, frescor de telemetria ou regra operacional do backend. Sem contador de idade mudando a cada segundo nem anúncios repetidos.
- Estatísticas e registro de falhas têm erros separados: consulta parcial bem-sucedida continua utilizável. Data do registro indica quando foi consultado e não é apresentada como chegada de uma nova falha. A consulta automática das estatísticas continua a cada cinco segundos; registro de falhas conserva atualização manual e após replay.
- Mais falhas e atualização preservam páginas carregadas até o teto de 200, com deduplicação por ID e cursor de continuação. Expansíveis keyed por ID permanecem abertos quando o registro continua válido.
- Replay exige diálogo explícito e mantém request_id e regras do servidor: somente telemetria elegível do writer, três solicitações e intervalo de 30 s. Solicitação aceita/already_requested não é execução concluída. Recusa aparece como erro. Nenhuma flexibilização de elegibilidade, deduplicação ou limites.
- A página consulta somente GET /messaging e /messaging/failures (e continuação). Estatísticas usam a API de gerenciamento, falhas usam o registro durável e mensagens recentes usam metadados previamente registrados pelo consumidor existente. Nenhuma chamada para consumir filas ou retirar mensagens da DLQ foi adicionada.

## Auditoria
- Prioridade: data/hora, usuário, ação, recurso e resultado. Códigos conhecidos traduzidos por listas explícitas; códigos desconhecidos indicados como não traduzidos, com valor original nos detalhes. Falha, negação e cancelamento não são confundidos.
- Detalhes exibem somente ação, resultado, tipo de recurso e identificadores originais. O objeto details retornado pelo backend NÃO é renderizado; sem serialização indiscriminada de payloads, senhas ou tokens.
- Não existiam filtros na página nem parâmetros de filtro no endpoint; nenhum filtro foi inventado. Paginação de 20 registros preservada. Atualizar mantém cursor; navegação só muda o histórico de páginas quando a consulta tem sucesso. Erros mantêm registros, página e detalhes abertos. Ausência de registros, página vazia e indisponibilidade têm textos distintos.
- Desktop com tabelas e celular com cartões compactos. Rotas continuam restritas a administrador pelos guards existentes.

## Verificações desta etapa
- Build Docker de produção (vue-tsc e Vite) e lint aprovados. Três testes unitários de apresentação aprovados: limite de frescor, resultados e semântica das traduções.
- Quatro cenários Playwright aprovados (8,5 s). Após a tradução final dos tipos de evento, cenário de consultas reais/capturas repetido e aprovado (4,2 s).
- Real: login administrador, estatísticas reais, mensagens recentes, falhas existentes e auditoria existente; desktop 1440 × 1000 e celular 390 × 844; teclado Enter, toque emulado, ausência de transbordamento da página e das filas móveis, sem erros JavaScript observados. Chamadas de Mensageria verificadas como GET e limitadas às rotas de consulta.
- Fixture: fila vazia, consumidor ausente com pendências, resposta antiga bem-sucedida, falha de consulta preservando dados, continuação de falhas preservada após atualização, expansíveis mantidos, diálogo de replay com Escape e retorno de foco, envio somente após confirmação explícita e recusa 409. POST de replay interceptado no navegador, sem atingir o backend.
- Fixture: paginação da Auditoria mantida em erro de atualização e de retorno; códigos originais acessíveis, erro separado de lista vazia, objeto details contendo marcadores de senha/token/payload não renderizado mesmo com detalhes abertos.
- Contrastes DOM nas capturas reais: mínimo 7,23:1, fonte mínima de 14 px. Fixture de erro/desatualização: mínimo 7,58:1. Registros JSON junto às imagens. Os dados simulados não comprovam execução do replay nem estabilidade dos consumidores.

## Limitações e encerramento
Não se pausaram consumidores, não se executou replay real, não se gerou massa nem se treinou ou promoveu modelo. Não houve novo ensaio de autorização do backend; guards e contratos existentes foram preservados. Celular validado por Chromium com viewport e toque emulados, sem aparelho físico ou leitor de tela. Mensagens recentes seguem a retenção e o teto existentes; desaparecimento por retenção é esperado. Sem novos filtros de auditoria.

Implementação concluída neste escopo; aguardar avaliação antes da próxima expansão. Capturas reais: [Mensageria desktop](../evidence/ui-messaging-audit/messaging-desktop.png), [Mensageria celular](../evidence/ui-messaging-audit/messaging-mobile.png), [Auditoria desktop](../evidence/ui-messaging-audit/audit-desktop.png), [Auditoria celular](../evidence/ui-messaging-audit/audit-mobile.png). Captura simulada identificada: [fixture de dados antigos e erro](../evidence/ui-messaging-audit/fixture-messaging-stale.png).


## Encerramento — ajuste de densidade — 15/11/2026
- Linhas desktop com padding vertical reduzido, sem diminuir fonte. Cartões móveis com menos padding e espaçamento entre campos. Mantidos resumo/controles com área mínima de 44 px.
- Mensageria móvel: nome e estado no topo, cinco contadores em grid de duas colunas e detalhes ao final. Detalhes das falhas também movidos ao final do item. Desktop mantém tabelas com detalhes na última coluna; cabeçalhos não quebram palavras artificialmente.
- Auditoria móvel: ação e resultado no topo; usuário, horário e recurso abaixo; detalhes ao final. Desktop mantém a ordem tabular anterior. Sem ocultar registros: 20 itens por página, mesmo limit=20 e paginação existente.
- Verificações afetadas: build de produção com tipagem e lint aprovados. Cenário Playwright de consultas reais aprovado na última execução em 4,8 s; confirma grid de duas colunas, posição final dos detalhes, ordem visual de ação/resultado, resumo de pelo menos 44 px, 20 registros presentes, teclado Enter, toque emulado, ausência de transbordamento horizontal da página e nenhum erro JavaScript observado. Capturas reais atualizadas em desktop/celular e inspecionadas. Contraste mínimo DOM 7,23:1; fonte mínima 14 px.
- Nesta rodada não se repetiram fixtures de replay/erros, ensaios de consumidores, autorização ou integração: os registros anteriores continuam sendo evidência anterior, não nova verificação. Nenhum replay real ou pausa de consumidor. Sem backend, LLM, dependências, commit ou publicação remota.
- Etapa encerrada. Próximo bloco proposto, sem implementação: Usuários (nome, papel, habilitação, ações e formulários existentes) e Interfaces locais (links por serviço, endereço local e informações essenciais para acesso). Reutilizar padrão e permissões existentes; aguardar aprovação.
