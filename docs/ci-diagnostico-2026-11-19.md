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
