# Aceite integrado — 19/11/2026

## Escopo e integridade

Ensaio real com `ac_01`, na interface final, sem fixtures de domínio. Uma geração massiva e um treino novos; contas existentes, dados, volumes, modelos e histórico preservados. Sem mudanças de backend, UI, dependências ou LLM; sem commit/publicação.

Antes do ensaio, o administrador atualizou explicitamente as senhas das contas existentes `operador` e `visualizador`, conforme autorização do responsável, usando seus arquivos privados. Os dois logins e papéis foram confirmados, com HTTP 403 no recurso administrativo de usuários. Nenhum segredo é reproduzido neste registro.

O Compose foi validado e os 13 serviços estavam saudáveis na preparação. O diff acumulado de trabalho foi inventariado; não foi revertido, limpo nem publicado. As verificações estáticas desta execução ficam limitadas ao roteiro de aceite alterado: ESLint, formatação, TypeScript e `git diff --check`. Não se repetiu a campanha geral de qualidade já registrada na [consolidação](consolidacao-final-2026-11-15.md).

## Continuidade e rastreabilidade

- Preparação `1795089055773`: interrompida antes do passo 1 por uma pré-condição indevida do teste, que exigia modo automático. O equipamento estava legitimamente em manual, com ambos os atuadores desligados. Nenhuma geração ou treino. A pré-condição foi substituída pela exigência de observação recente.
- Execução `1795089099614`: passos 1–9 realizados; interrompida no seletor de dataset do teste, antes de acionar o treino. A página mostrava o dataset corretamente. O seletor foi corrigido para usar papel/nome acessível do combobox.
- Continuação: retoma o dataset da execução anterior, sem repetir os passos 1–9, sem nova geração e sem esconder a interrupção. O cleanup intermediário restaurou a regra, o simulador original e a saúde dos serviços.

Portanto, este registro distingue aceite por passo de execução única sem interrupção. A última não pode ser declarada aprovada por esta evidência.

## Configuração declarada

Conforme o [roteiro](cenario-demo.md): seed 42, dano inicial zero, desgaste `mechanical_wear` de 12 por hora de operação, saúde ativa abaixo de 90 e limpa acima de 95, RUL ativa abaixo de 1 h e limpa acima de 2 h, três previsões ruins para abrir e dez boas para limpar. Os parâmetros não são ajustados durante a degradação. Anticiclo de 180 s e proteção térmica permanecem. O cenário didático não certifica transição com os limiares padrão de produção.

O simulador de demonstração usa volume separado. O volume original e a seleção do modelo ativo são preservados; a conclusão do treino não implica promoção. Reinicialização do simulador segue seu startup seguro existente, e não restauração de uma fotografia física arbitrária.

## Resultado por passo

As evidências novas estão no [resultado 1–9](../evidence/acceptance/1795089099614/result.json), no [resultado da continuação](../evidence/acceptance/1795089099614/continuation/result.json), nos frames correspondentes e na [conferência somente leitura](../evidence/acceptance/1795089099614/continuation/post-observation.json). São locais e ignoradas pelo Git, sem credenciais. Os resultados automatizados reprovados foram preservados, sem alteração para parecerem aprovados.

| Passo | Aceite funcional por observação | Evidência nova | Evidência anterior, separada |
|---|---|---|---|
| 1. Compose após parada normal | APROVADO | `stop` seguido de `up -d --wait --wait-timeout 180`; 13 serviços saudáveis | Consolidação verificava saúde, sem nova partida completa |
| 2. Login e papéis | APROVADO | Três contas existentes no navegador; controles ausentes para visualizador e presentes para operador/admin; autenticação prévia e papéis conferidos | Ensaios anteriores com contas de prova; novo acesso elimina esse bloqueio |
| 3. Simulador via MQTT | APROVADO | Frames novos de `ac_01`; identidade original encontrada na inbox concluída do writer | Fluxo verificado em 14/11 e 15/11 |
| 4. Documentação FastAPI | APROVADO | HTTP 200 em `/api/v1/docs` | Roteiro existente |
| 5. Mensageria e consumidor parado | APROVADO | Writer parado: zero consumidor e mensagens pendentes; retomado: um consumidor e fila drenada; prévias visíveis | Acúmulo/drenagem também verificados em 15/11 |
| 6. PostgreSQL, InfluxDB e histórico | APROVADO | Cadastro PostgreSQL e histórico com potência não nula; evento novo persistido pelo writer | Persistência e cobertura registradas na consolidação |
| 7. Dashboard em tempo real | APROVADO | Identificador de amostra mudou pelo WS | Consolidação e validações da UI |
| 8. Atuador manual e automático | APROVADO | Três comandos da UI com IDs próprios, execução confirmada e leitura posterior coerente; `thermostat_hot` confirmado às 08:58:29 locais, com compressor ligado observado na continuação | Comandos e estado físico verificados em 15/11 |
| 9. Laboratório massivo | APROVADO | Uma geração pela UI, concluída com 1.036.800 vetores; sem repetir após interrupção | Artefatos anteriores reutilizados somente na consolidação |
| 10. Treinamento e métricas | APROVADO | Um treino pela UI do dataset recém-gerado; dois alvos com MAE/RMSE/R² e baseline finitos; promoção desabilitada por melhora insuficiente frente ao ativo | Modelo aprovado/ativo anterior preservado |
| 11. Falha, histerese, Insights e 3D | APROVADO para abertura do alerta | Três previsões consecutivas ruins na fonte da abertura; degradação de três variáveis, saúde/RUL válidas, novo alerta e mudança de cor 3D via WS | Abertura/recuperação documentadas anteriormente; nova limpeza por dez previsões boas não foi exercitada agora |
| 12. Assistente sobre a falha | APROVADO para integração; fidelidade parcial | Turno concluído na UI, texto real e resumo separados, requisição persistida e auditoria de sucesso; sem segunda pergunta | Avaliação semântica anterior permanece parcial, sem requalificação |

### Artefatos e números observados

- Geração: job `945a2bc9-8574-44a4-9c7d-6f484e577c01`, dataset `3c410a45-8b77-4f4b-9d43-59f3ee464248`, **1.036.800 vetores**. Não equivale a dizer 1.036.800 valores escalares de sensores.
- Candidato concluído: `mdl_48aba5d222504cdaa2363514c35ce4e6`. Não aprovado para promoção: `insufficient_active_improvement`. Modelo ativo/desejado preservado: `mdl_edcc5fb6df9e49879f028ab2e9c7f178`, revisão 1.
- Teste por equipamento, alvo saúde: MAE **0,5322 pontos percentuais**, RMSE **1,1597 pontos percentuais**, R² **0,9979**; baseline MAE **21,5410**, RMSE **26,1214**, R² **−0,0706**. Alvo RUL: MAE **2,7149 h**, RMSE **3,3880 h**, R² **0,8794**; baseline MAE **8,5806 h**, RMSE **9,9669 h**, R² **−0,0436**. Vencer baseline não basta para substituir o ativo: política preservada.
- No trecho válido da degradação, vibração **1,4706 → 3,3626 mm/s**, corrente **4,6827 → 5,2973 A**, carcaça **46,2 → 63,914 °C**, saúde **100 → 87,6779%** e RUL **25,1900 → 25,0609 h de calendário**. Não houve previsão de falha imediata; o alerta foi compatível com o limite didático de saúde.
- Novo alerta `4a0b05b7-9e0c-4fff-afe2-87f2c689e3f1`, regra revisão 10, abertura às **09:03:42 locais**, motivo estruturado `predictive_health_or_rul`. Na fonte da abertura havia exatamente **3 previsões ruins consecutivas**; o estado persistido confirmou `bad_count=3` e `good_count=0`. [Captura da cena](../evidence/acceptance/1795089099614/continuation/scene.png).
- Chat `a58a7068-7bec-4e0e-a05a-ecd5962c7159`: `completed`, **5.098 ms até o primeiro fragmento**, **8.410 ms de duração total no backend**, 109 tokens e uma auditoria `assistant.completed` com sucesso. São tempos diferentes, não duas medidas de duração total. Resumo da tela: saúde **85,8%**, RUL **25,9 h**, um alerta. Métricas do modelo estavam explicitamente indisponíveis nesse resumo, sem inventar valores. Texto gerado não determina comandos ou encerramento de alertas. Uma resposta concluída não elimina a pendência semântica.

### Falhas do ensaio e correções delimitadas

Além da pré-condição e do seletor mencionados acima, a continuação terminou com falha de instrumentação **depois** de concluir o chat: Chromium não disponibilizou `response.text()` do fetch SSE já consumido. A UI já mostrava `completed`, conteúdo gerado e resumo estruturado. A requisição e sua auditoria foram conferidas somente por leitura no PostgreSQL, sem outra chamada ao LLM. A correção do teste usa esses registros e o turno concluído, sem exigir retenção do corpo SSE pelo navegador.

Também houve rejeição `boot_mismatch` de um comando de preparação da continuação enviado durante a troca de boot; a proteção rejeitou corretamente o destino antigo. A espera do teste passou a exigir telemetria nova após a recriação antes de enviar comandos. O acionamento automático posterior foi real e confirmado. Nenhuma proteção de produção foi alterada.

O teste corrigido foi formatado e conferido por ESLint, TypeScript e descoberta do Playwright, mas **não foi reexecutado integralmente**. Não se declara suíte end-to-end verde nem ensaio ininterrupto aprovado. Nenhuma regressão comprovada de aplicação exigiu alteração de produção.

## Restauração

Conferência independente após o cleanup: **13 serviços saudáveis**, writer com **um consumidor, zero mensagens prontas e zero não confirmadas**, modelo ativo/desejado e revisões preservados, configuração preditiva original restaurada: saúde **40/45**, RUL **24/30 h**, histerese **3/10**. Regra de termostato preservada, incluindo anticiclo de 180 s.

O volume original do simulador foi retomado; o equipamento voltou a manual com atuadores desligados, coerente com o modo inicial e startup seguro. Volume de demonstração, novo dataset, candidato, alerta e auditoria foram preservados. O alerta de demonstração não foi apagado nem encerrado artificialmente: sua abertura deve ser interpretada com a revisão didática registrada, não deduzida da configuração atual restaurada.

## Gates e pendências

| Gate/pendência | Classificação | Situação e limite |
|---|---|---|
| Doze passos numa execução sem interrupção | Exigência deste aceite | NÃO APROVADO: interrupções da automação registradas; os passos foram observados entre execução e continuação; não repetir massa/treino nesta rodada |
| Fidelidade semântica do assistente | Problema concreto frente ao requisito funcional | PARCIAL; integração aprovada não certifica correção conceitual geral; sem busca de modelos ou ajustes de prompt |
| Nova limpeza por dez previsões boas | Verificação do requisito de histerese | Não exercitada nesta execução; não afirmar cobertura nova da transição de limpeza; abertura com três ruins comprovada |
| Troca efetiva/hot-reload para candidato novo | Verificação condicional do requisito de IA | Não exercitada: candidato sem melhora suficiente foi corretamente bloqueado; não burlar política nem chamar conclusão de ativação |
| Gate histórico de segredos e cobertura combinada | Exigências internas de qualidade do projeto | Mantêm o último resultado documentado na consolidação; não reexecutados nem dispensados aqui; não declarar CI integralmente verde |
| Carga ampliada, p95, falhas combinadas, backups adicionais | Melhorias opcionais desta entrega acadêmica | Fora do ensaio de um equipamento; sem nova campanha |

## Executar a aplicação

Na raiz, com Docker Desktop Linux/WSL2 ativo e ambiente privado já preparado:

```powershell
docker compose up -d --build
docker compose ps -a
```

Abra `http://127.0.0.1:8080`, use as contas existentes com suas credenciais privadas e siga os 12 passos do [README](../README.md). Para conferir uma nova partida normal, `docker compose stop` seguido de `docker compose up -d --wait --wait-timeout 180`; não usar remoção de volumes.

O comando completo opt-in está no [cenário](cenario-demo.md). Não é necessário executá-lo para apenas iniciar a aplicação; cria nova geração/treino e não deve ser disparado novamente por padrão. A continuação desta rodada teve `AIOT_ACCEPTANCE_RESUME=1795089099614`; isso documenta a retomada, não uma instrução para reexecutar jobs concluídos.
