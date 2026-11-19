# Diagnóstico do CI — 19/11/2026

## Causas confirmadas

1. Primeira execução: instalação das dependências de sistema do Chromium falhou com HTTP 503 dos repositórios Ubuntu e saída apt 100. Na única repetição autorizada, a instalação passou sem modificar versões.
2. Segunda tentativa: 278 testes Python AIoT passaram, mas a coleta dos testes legados falhou por ausência de `POSTGRES_PASSWORD` e `INFLUXDB_TOKEN`. `Settings()` é instanciado na importação, antes de fixtures convencionais. [Log remoto](https://github.com/felipematsukuma/smart-fan-iot/actions/runs/44522552681/job/135695113741#step:8:50).

## Escolha da correção

| Opção | Avaliação |
|---|---|
| Injetar segredos reais no CI unitário | Desnecessário: as fronteiras de I/O já são substituídas; aumenta exposição e dependência do ambiente |
| Adicionar defaults na configuração de produção | Rejeitado: esconderia configuração ausente em execução real |
| Remover os testes legados do gate | Rejeitado: deixaria de verificar regressões |
| Preparar credenciais efêmeras no conftest antes das importações | Adotado: funciona localmente e no CI, sem credenciais reais ou mudança de produção |

O [conftest](../web-smart-fan-iot/backend/tests/conftest.py) sobrescreve as duas variáveis apenas no processo pytest com valores aleatórios e restaura o ambiente ao encerrar. Os dublês de PostgreSQL, InfluxDB e transporte permanecem existentes; nenhum segredo é escrito em arquivo.

O [workflow](../.github/workflows/quality.yml) separa instalação Python, npm e Chromium em etapas distintas, preservando comandos e versões. Isso melhora o diagnóstico de uma próxima falha; não impede indisponibilidade externa nem ignora erros.

## Validação local

- 153 testes legados aprovados em 3,18 s, em cópia temporária no container Python 3.11, sem rede e sem `.env`; nenhum volume da aplicação alterado.
- Ruff, formatação do arquivo e `git diff --check` aprovados.
- Aviso de depreciação do TestClient preservado; sem atualizar dependências nesta correção.

## Próximos gates e limites

Cobertura combinada (70% global e 80% nos escopos específicos), integrações reais, build, navegador, scan de imagens e auditoria de dependências ainda dependem da nova execução. Não se reduzem limiares, removem testes ou alteram políticas para obter aprovação. HTTP 503 pode voltar; mudanças de retry/mirror só devem ser consideradas mediante recorrência confirmada. O aviso de depreciação do Lucide não impediu a instalação e não é tratado como causa da falha.

Não executar o runtime completo localmente sobre os serviços/volumes de demonstração: sua validação deve ocorrer no runner isolado. O assistente continua parcial por fidelidade semântica, fora deste reparo de CI.

## Reanálise após a primeira correção

O commit `c30af9a` passou em instalações, lint/contratos e testes unitários/legados no remoto. A [execução seguinte](https://github.com/felipematsukuma/smart-fan-iot/actions/runs/44564744598/job/135703406901) encontrou saída 1 do bootstrap no ambiente de cobertura, antes de executar integrações. O log original não incluía o traceback interno desse container.

Foi comprovada uma incompatibilidade de permissões no arranjo de QA: a pasta de cobertura criada pelo runner Linux não permite escrita ao UID 10001 dos containers. Reprodução isolada, sem volumes do projeto: diretório UID 1001/modo 0755 produziu `SQLITE_CANTOPEN` e saída 1 no coverage; diretório com dono 10001 produziu saída 0. Isso demonstra o defeito de permissões; o novo CI ainda deve confirmar que não há outra causa no bootstrap.

Correção restrita ao QA: helper descartável sem rede ajusta somente o bind de cobertura para dono 10001 e grupo do runner, modo 2770. Serviços permanecem sem root; nenhum volume ou segredo da aplicação é montado no helper. O grupo permite ao runner ler e remover artefatos antigos sem escrita global.

A subida entrou no bloco de cleanup: erro de inicialização agora captura log limitado do bootstrap, remove valores dos arquivos de segredos da saída e mantém a falha original. O workflow preserva também a cobertura unitária quando a integração falha. Um teste verificou a redação e a parada mesmo diante de falha de subida (aprovado); Ruff/formatação passaram. Limiares, testes e políticas continuam preservados.

## Integração e navegador

O commit `d16d5be` superou o bootstrap; 85 integrações reais passaram. No navegador, 35 testes passaram, dez falharam e três ensaios opt-in permaneceram desabilitados como antes. As falhas revelaram seletores anteriores à UI aprovada, pressuposição de `admin` na primeira página, logout móvel sem abrir o menu e leitura visual de artefatos antes de sua geração. A cena também confundia congelamento por movimento reduzido com congelamento por ausência de telemetria; o teste agora aguarda sair do primeiro estado antes de verificar o segundo.

Correções somente de automação: rótulos/expansíveis/confirmadores atuais, paginação real, DLQ na seção separada, conexão WS distinta de frescor. Em `AIOT_COVERAGE=1`, os testes existentes de laboratório e treinamento são dependências explícitas das consultas, executados uma vez cada. Fora desse modo, não se introduz geração/treino implícito nas verificações visuais dirigidas. A descoberta continua incluindo os 48 casos, sem excluir falhas.

O treino instrumentado permaneceu `running` ao atingir a espera de 120 s. Para validar o fluxo no runner compartilhado, o modo cobertura usa os campos já suportados na UI: 12.000 janelas candidatas, 4.000 de benchmark e 200 para importância, mantendo o dataset de 1.036.800 vetores e os critérios de aprovação. Não se aumenta timeout, recurso ou limite de aprovação; esse ensaio não certifica o tempo do treino com a configuração padrão. O treino padrão real permanece documentado no aceite integrado.

Verificações locais dirigidas: três casos de autenticação/paginação/mobile, dois de recuperação HTTP/gestão com fixtures, consulta real de dados/treinamento e cena real passaram. Nenhuma conta, dispositivo ou configuração foi alterada; nenhum dataset ou modelo foi criado. Logins mantêm a auditoria normal. Os testes que interrompem serviços e os jobs novos ficam para o runner isolado.
