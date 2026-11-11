# M17 — Qualidade e evidências

Os comandos partem da raiz do repositório, com Python do ambiente de desenvolvimento e Node apenas para o frontend. Instale `web-smart-fan-iot/backend/requirements-dev.txt`, o pacote compartilhado editável e execute `npm ci` no frontend. Nenhuma ferramenta abaixo é um serviço de produção.

| Comando | Verificação |
|---|---|
| `python tools/quality/check.py lint` | Ruff, mypy, ESLint, vue-tsc, formatação e contratos gerados |
| `python tools/quality/check.py unit` | Python, regressão do backend legado e Vitest, com cobertura |
| `python tools/quality/negative.py` | Gates realmente rejeitam segredo temporário, erro de tipo, contrato inválido e título inválido |
| `python tools/quality/runtime.py` | Build, 79 integrações reais, navegador, cobertura combinada e scan das imagens |
| `python tools/quality/secret_scan.py tree` | Todos os arquivos versionáveis atuais; saída redigida |
| `python tools/quality/secret_scan.py strict-history` | Todas as referências Git; falha enquanto revogação histórica estiver pendente |
| `python tools/quality/legacy_issuers.py --stack legacy` ou `--stack aiot` | Credenciais históricas contra cópias isoladas dos emissores locais, com controles efetivos |
| `python tools/quality/images.py` | Todas as imagens selecionadas pelo Compose, zero vulnerabilidades críticas |
| `python tools/quality/install_hooks.py` | Hooks locais de lint, tipos, segredo staged e Conventional Commits |

O ensaio de runtime usa o overlay [compose.coverage.yaml](../../infra/compose.coverage.yaml), preserva os volumes e para os serviços ao terminar. Ele exige Docker disponível e porta 8080 livre. Geração, treino, Ollama e scans não são executados simultaneamente pelo orquestrador. Não execute contra um ambiente que outra pessoa esteja usando. O frontend instrumentado fornece source maps somente nesse build de teste.

O instalador usa `pre_commit run --all-files` nos hooks para não ocultar alterações não staged durante commits parciais. A configuração padrão do pre-commit guarda essas alterações temporariamente; esse comportamento é incompatível com a regra do projeto de não usar stash. O scanner ainda verifica o índice exato, e o título continua obrigatório. Hooks personalizados existentes são preservados: o instalador só substitui hooks gerados pelo próprio pre-commit ou por este instalador.

## Medição de cobertura

Python combina testes locais, integrações, processos dos serviços e subprocessos de treino. Unidade e runtime gravam em diretórios separados: repetir a suíte unitária não pode apagar a evidência dos containers. O código de testes é omitido; serviços não exercitados continuam no denominador. Os grupos de contratos, domínio/controle e ML estão explicitamente definidos em [coverage_gate.py](coverage_gate.py), com mínimo de 80% dos ramos e 70% global.

Frontend usa a mesma conversão AST de cobertura do Vitest para os traces V8 do Chromium. Bibliotecas e núcleo de negócio mantêm a instrumentação unitária; componentes e orquestração usam a instrumentação real do bundle de produção. Cada arquivo possui um único mapa de instrumentação: somar mapas SSR e browser incompatíveis produziria contagens falsas. Arquivos não visitados permanecem com zero. Os mínimos são 70% das linhas globais e 80% dos ramos do núcleo de negócio; tipos e validadores gerados não substituem testes de contrato.

Fixtures de falha HTTP, formulário e SSE verificam estados da interface e são identificadas como fixtures nos nomes dos testes. Elas não comprovam execução do backend ou do LLM. Há um teste separado que exige fragmentos do Ollama real, cancelamento e liberação do recurso. Timeout real do modelo falha esse teste; não há retry automático para transformar instabilidade em sucesso.

## Ferramentas e custo

| Ferramenta | O que deixa de ser verificado se removida |
|---|---|
| Ruff / mypy | Estilo e erros estáticos Python |
| ESLint / vue-tsc / Prettier | Erros estáticos e consistência Vue/TypeScript |
| pytest / Vitest / Playwright | Domínio, contratos, integração e fluxos reais no navegador |
| coverage / conversor AST | Denominador e limiares mensuráveis de cobertura |
| Gitleaks | Segredos na árvore, staging e histórico |
| Trivy / pip-audit / npm audit | Vulnerabilidades conhecidas nas imagens e dependências |
| pre-commit | Verificação antecipada local; CI continua obrigatório |

Gitleaks e Trivy são baixados por versão e checksum fixos; o cache é ignorado pelo Git. Os relatórios ficam em `evidence/`, também ignorado. Não publique backups nem arquivos de credenciais como artefatos de CI.

## Imagens e dados preservados

O runtime Python usa Debian Trixie. O PostgreSQL mantém a versão 15.19, retirando o helper `gosu` não utilizado porque o usuário do container já é fixo e não-root. O frontend atualiza a biblioteca Brotli da imagem fixada. InfluxDB passa de 2.7.12 para 2.9.1 após backup offline privado, restauração em volumes novos e validação de contagem e dos três tokens de escopo. A opção `INFLUXD_USE_HASHED_TOKENS=false` preserva a autenticação dos volumes existentes; não equivale a criptografia dos tokens em repouso. Acesso ao volume e backup continua restrito ao operador local.

O script [influx_upgrade.py](influx_upgrade.py) recusa arquivar o banco em execução e verifica a identidade do projeto/volume. O ensaio usa volumes novos, rede interna e nenhuma porta publicada. Não faz downgrade destrutivo nem remove os volumes originais.

## CI e política de contribuição

O workflow fixa ações por SHA, usa permissões de leitura e não persiste credenciais de checkout. Mudanças apenas em Markdown mantêm lint e scan de segredos; código exige testes, build, cobertura e scans. O gate agregador recusa jobs obrigatórios falhos, cancelados ou inesperadamente omitidos. Indisponibilidade de registry ou download não conta como aprovação.

Antes de publicar, configurar proteção de `main`: sem force-push/deleção, check `required-gate` obrigatório, conversas resolvidas e revisão de outro integrante quando houver equipe. Preservar commits e autoria reais; não fabricar participação. Execução remota e proteção não foram verificadas, pois push/PR não foram autorizados. O fluxo atual permite branches e merges locais.

Consulte [achados históricos](../../docs/security/README.md) antes de interpretar o resultado do scan. Baseline precisa não comprova revogação.

A auditoria cria cópias somente quando os originais estão parados. Usa PostgreSQL/InfluxDB com imagem compatível, sem portas publicadas, e cliente não-root; apenas a cópia/inicialização de permissões usa root. Sua remoção elimina a reprodução da evidência factual de autenticação, que uma comparação de arquivos de ambiente não fornece. Nenhum valor de credencial entra no relatório versionado.
