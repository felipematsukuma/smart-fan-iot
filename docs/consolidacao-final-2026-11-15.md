# Consolidação final delimitada — 15/11/2026

## Resultado

UI/UX encerrada no escopo aprovado. Nenhuma regressão operacional nova impeditiva observada nos fluxos ensaiados. O assistente continua parcial por fidelidade semântica. O gate histórico de segredos permanece reprovado por três fingerprints não cadastrados de um exemplo já revisado por conteúdo; não se declara o CI integralmente verde.

## Diff acumulado

- Revisados arquivos alterados e novos arquivos versionáveis: UI, testes, documentação, ADR 009 e as correções funcionais anteriores de prévias, alertas e contexto do assistente. As mudanças anteriores no backend/renderizador pertencem aos blocos autorizados antes da UI; não foram revertidas como se fossem acidentes.
- Nenhum temporário versionável, dump ou segredo acidental encontrado. Evidências, builds e caches continuam ignorados. A ferramenta de avaliação do LLM é registro reprodutível da avaliação encerrada, não foi executada nem automatizada.
- As quatro dependências acumuladas da composição visual já haviam sido aprovadas. Nenhuma nova nesta consolidação.
- Contas, dados, volumes, modelos, alertas e histórico preservados. Resultados de ensaios falhos e bem-sucedidos mantidos separadamente.

Correções desta consolidação: anotações de tipos em um teste Python; seletores de testes desatualizados pelos novos rótulos/expansíveis; instruções e roteiro. Nenhuma melhoria visual, mudança do LLM ou alteração de lógica de produção.

## Checks locais

| Verificação | Resultado |
|---|---|
| Ruff e formatação Python | Aprovados; 183 arquivos conferidos inicialmente |
| mypy compartilhado | Aprovado em 45 arquivos |
| mypy serviços/infra | Três erros de anotação no teste do contexto corrigidos; retomado e aprovado em 79 arquivos |
| Ruff/mypy legado | Aprovados, 10 arquivos de tipos |
| ESLint, vue-tsc e Prettier | Aprovados; testes corrigidos conferidos pontualmente |
| Contratos V1/V2/WS, validadores e exports | Sem divergências |
| Unidade Python AIoT | 278 aprovados, 74,50 s |
| Regressão Python legado | 153 aprovados, 6,68 s; aviso de depreciação sem atualizar dependências |
| Vitest com cobertura | 260 aprovados em 19 arquivos, 7,86 s |
| Teste Python corrigido | Cinco testes reconferidos e aprovados |
| Build legado e AIoT | Aprovados; AIoT com `VITE_APP_MODE=aiot`, como no Docker |
| Compose base e override administrativo | `config --quiet` aprovado |
| `git diff --check` | Sem erros |
| Scan da árvore | Zero novos segredos; três placeholders exatos revisados |
| `strict-history` | REPROVADO: 17 achados, três fingerprints não cadastrados, zero `legacy_pending` |

O gate lint foi iniciado uma vez e interrompeu nos três erros mypy. Após a correção, suas etapas restantes foram retomadas; não se repetiu a suíte unitária pesada. O teste corrigido foi reconferido isoladamente.

Não foram repetidos runtime amplo de cobertura, integrações descartáveis completas, scans de imagens/dependências, carga, backups ou testes negativos deliberados dos gates. A cobertura unitária isolada do frontend foi 17,55% de linhas; o limiar de cobertura combinada de 70% não foi recertificado. Testes aprovados não equivalem à aprovação desse gate ou do CI completo.

Os três fingerprints históricos são do exemplo no commit `2f66c71055a7ffe4e15c65389dfd90c00640125f`, linhas 2/6/9, com hash normalizado idêntico ao placeholder exato já revisado. Não se alterou ledger, política ou histórico para fazê-los passar. A pendência impede aprovação integral do gate/CI, mas não impediu o funcionamento local. Veja [segurança](security/README.md).

## Ensaio integrado real

[consolidation.spec.ts](../web-smart-fan-iot/frontend/e2e/consolidation.spec.ts), opt-in com `AIOT_CONSOLIDATION=1`: aprovado em **44,5 s**, sem erro JavaScript observado, 13 serviços permanentes saudáveis no final.

- Novo frame de `ac_01` recebido pelo WS; original confirmado como `completed` na inbox do writer. Histórico Influx consultado: 901 pontos e aproximadamente 99,92% de cobertura.
- Writer interrompido brevemente: consumidor zerou, uma mensagem pendente observada, retomada e drenagem para zero. Nenhuma limpeza de fila ou consumo diagnóstico.
- Visão geral enviou `fan_off`, `fan_on` e `release_auto`. Cada comando teve ID próprio, confirmação de execução/`ack_event_id` e observação física posterior. ACK intermediário sozinho não foi aceito como prova. Automático restaurado.
- Dataset existente `a2ece2c6-323a-4141-b0ea-1a15bebc0773`, com **1.036.800 vetores**, e modelo aprovado/ativo `mdl_edcc5fb6df9e49879f028ab2e9c7f178` reutilizados. Geração e modelo consultados pela UI, dois alvos e métricas/baselines reais finitos. Nenhum job novo ou promoção.
- Insights, Cena 3D e Auditoria consultados após os comandos. Cena com dados recentes; comandos encontrados na auditoria. Nenhuma falha progressiva injetada ou alerta apagado/encerrado manualmente.

### Temporalidade da IA

A [tentativa inicial](../evidence/consolidation/result.json) exigia nova previsão válida em 120 s. Recebeu 59 frames, mas o compressor estava legitimamente desligado pelo automático. Falhou antes de atuar no equipamento ou pausar writer. Não era regressão comprovada nem motivo para alterar proteções.

O ensaio passou a reconhecer explicitamente `inactive` com compressor desligado e saúde/RUL nulas, consultando separadamente previsão histórica válida da mesma versão. Na execução aprovada, a amostra ao vivo das **21:52:57 locais** era `inactive`; o registro histórico de **21:48:05** tinha saúde 100 e RUL 35,195 h. Não foi anunciado como previsão numérica nova ao vivo.

Após restauração, sem novo comando ou mudança de limiares, houve nova previsão `valid` às **21:56:20 locais**: saúde 100 e RUL 28,088 h, mesma versão ativa. A observação somente leitura foi conferida no histórico persistido, sem repetir o ensaio completo. JSON usa UTC de 16/11, equivalente a 15/11 no fuso local.

Evidências: [resultado aprovado](../evidence/consolidation/1794790374658/result.json) e [observação posterior](../evidence/consolidation/1794790374658/post-restoration-observation.json). Não comprovam novo treino, nova falha progressiva ou fidelidade do LLM. Esses blocos mantêm as evidências anteriores separadas.

## Iniciar e demonstrar

Com ambiente já preparado e Docker Desktop Linux/WSL2 ativo, na raiz:

```powershell
docker compose up -d --build
docker compose ps -a
```

Abrir **http://127.0.0.1:8080**, entrar com `admin` e a senha administrativa atual e selecionar `ac_01`. A preparação de máquina nova está no [README](../README.md). Senhas iniciais só valem se não tiverem sido alteradas; não redefinir contas nem apagar volumes para preparar a apresentação.

Roteiro curto com artefatos existentes:

1. Mostrar serviços saudáveis, login e papéis. Nesta consolidação somente admin foi autenticado de novo; usar as senhas atuais dos demais papéis.
2. `docker compose logs --tail 10 simulator gateway`; abrir `/api/v1/docs` por Interfaces locais.
3. Mensageria: filas, taxas e consumidores. Para demonstrar interrupção: `docker compose stop writer`, observar acúmulo, `docker compose start writer`, aguardar drenagem.
4. Histórico, consultas PostgreSQL do README e Visão geral com atualização por WS.
5. Desligar ventilador, conferir confirmação de execução e novas leituras; ligar ventilador; Liberar automático. A espera anticiclo pode levar 180 s; não alterar regras para apressar.
6. Dados sintéticos: **Ver geração** em job concluído. Treinamento: **Ver modelo**, métricas por alvo, baseline, gráficos e versão ativa.
7. Insights e Cena 3D: equipamento, leituras e previsões quando disponíveis; estado de aquecimento/inativo quando pertinente. Uma nova falha exige a preparação separada do [cenário completo](cenario-demo.md), com seus limiares didáticos explicitados.
8. Assistente: aviso de atendimento parcial e dados estruturados separados. Não usar texto gerado para comandos ou encerramento de alertas.

O roteiro oficial de 12 passos, incluindo nova geração/treino e falha, está no README com os limites. Não afirmar que esses jobs/falha foram repetidos nesta consolidação. Para mostrar saúde/RUL, aguardar compressor ativo e janela aquecida; usar Mensageria, histórico e métricas durante a espera.

Repetir apenas o ensaio delimitado, com ferramentas Node/Playwright já instaladas:

```powershell
Set-Location web-smart-fan-iot/frontend
$env:AIOT_CONSOLIDATION='1'
npx playwright test e2e/consolidation.spec.ts
Remove-Item Env:AIOT_CONSOLIDATION
Set-Location ../..
```

Tem efeitos reais no ventilador e writer; não rodar durante a apresentação. Pré-condição: `ac_01` em automático. Não cria contas, não gera massa, não treina, não promove modelos, não chama LLM e não apaga dados.

## Pendências finais

- Nenhum bloqueio operacional novo observado no escopo ensaiado.
- Assistente 1B segue parcial por fidelidade semântica: não permite afirmar cumprimento integral desse item acadêmico.
- Gate histórico reprovado por metadados de três fingerprints; CI completo/cobertura combinada não recertificados.
- Logins reais de operador/visualizador, novos jobs, nova falha e LLM real não foram reensaiados; evidências anteriores e fixtures continuam identificadas.
- Celular/teclado físico, leitor de tela, carga ampliada e calibração física das estimativas permanecem fora desta consolidação.

Consolidação encerrada, sem nova melhoria visual, arquitetura, remoção de dados, commit, merge, push ou publicação.
