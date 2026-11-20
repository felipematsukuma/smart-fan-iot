# Verificação delimitada do CI — 20/11/2026

O CI do commit `77a581a` ([execução](https://github.com/felipematsukuma/smart-fan-iot/actions/runs/44582471194)) aprovou os testes, a cobertura e o scan das imagens, mas reprovou a auditoria de dependências. Não representa aprovação integral do pipeline.

## Correção e evidência nova

- Auditoria Python local reproduziu `CVE-2026-126360` em `opentelemetry-api==1.45.1`, indicando correção em `1.45.2`.
- Atualizado somente esse pin no [lockfile](../web-smart-fan-iot/backend/requirements.lock), sem mudar gates, recursos ou timeouts.
- `python -m pip_audit -r web-smart-fan-iot/backend/requirements.lock --disable-pip --no-deps`: nenhuma vulnerabilidade conhecida encontrada após o patch.
- Patch instalado no ambiente virtual local; `python -m pytest services/api/tests -q -p no:cacheprovider`: 9 testes aprovados em 3,18 s.
- `git diff --check`: aprovado.

## Limites

Os testes locais são dirigidos; a validação Linux/Python 3.11 e a integração completa pertencem à nova execução remota. Não foi repetido o ensaio operacional nem alterados dados, contas, volumes ou modelos. A fidelidade semântica do assistente continua com atendimento parcial, fora deste reparo.
