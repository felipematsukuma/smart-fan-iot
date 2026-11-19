# Cenário reproduzível — um equipamento

Este ensaio é opt-in: usa serviços e dados reais, gera um dataset/treino, pausa o writer e muda o cenário do simulador; usa as três contas existentes, sem criar ou desativar contas. Execute fora de uma apresentação em curso. Não executa carga ampliada nem apaga dados.

## Preparação fixa

- Acesso às contas `admin`, `operador` e `visualizador` conferido antes da parada. As senhas atuais devem corresponder aos arquivos privados `secrets/initial_admin_password`, `secrets/initial_operator_password` e `secrets/initial_viewer_password` (administrador também aceita o caminho definido em `AIOT_TEST_PASSWORD_FILE`). Não imprime credenciais nem redefine senhas durante o ensaio.
- Código alterado construído: `docker compose up -d --build` na raiz; ambiente já preparado e senha administrativa atual disponível em arquivo privado.
- Apenas o dispositivo live `ac_01`. O laboratório mantém 30 equipamentos **sintéticos de treino**, não 30 produtores MQTT.
- A aplicação preserva o modelo aprovado ativo; um treino novo pode ser recusado pela política e não é promovido artificialmente.
- Antes de iniciar os passos, a API administrativa registra configuração didática: saúde ativa abaixo de 90 e limpa acima de 95; RUL ativa abaixo de 1 h e limpa acima de 2 h; **3 previsões ruins / 10 boas**. Esses limites são explícitos e não mudam durante o ensaio. Não são limites de fabricante nem os defaults 40/45%, 24/30 h.
- O simulador usa novo volume nomeado `smartfan_demo_<execução>`, seed 42, dano inicial zero, inicialmente saudável. O volume original permanece intacto. Somente o helper de ownership existente prepara o volume novo.

## Execução contínua

Na pasta do frontend, com dependências e Chromium Playwright instalados:

```powershell
$env:AIOT_ACCEPTANCE='1'
# Opcional se a senha administrativa atual difere da senha inicial:
# $env:AIOT_TEST_PASSWORD_FILE='C:/caminho/privado/senha-atual'
npx playwright test e2e/acceptance.spec.ts
```

O teste verifica os acessos, registra o estado original, executa `docker compose stop` e `docker compose up -d --wait --wait-timeout 180`, e segue os 12 passos do README em uma sequência. Modo manual inicial é válido; o roteiro libera o automático depois dos comandos manuais. Após laboratório/treino, injeta `mechanical_wear`, `SIM_INITIAL_DAMAGE=0`, `SIM_DAMAGE_RATE=12` por hora de operação, no mesmo volume de demonstração. Reinicia somente o simulador: UTC e cadência continuam reais; startup seguro, espera anticiclo de 180 s e proteção térmica permanecem. Somente a progressão de desgaste é acelerada.

O teste aguarda uma **nova** abertura de alerta depois da injeção, sem apagar/encerrar alertas existentes. Uma máquina saudável pode limpar o alerta anterior apenas por dez previsões acima da faixa configurada. Ausência de previsão não conta como melhora. Depois, vibração/corrente/carcaça devem evoluir e saúde/RUL refletir o modelo; a cena recebe o alerta via WS e o assistente usa o resumo real. O teste não altera os limiares para obter aprovação durante a sequência.

O `finally` retoma writer, recria simulador com o Compose original, restaura a configuração anterior pela API versionada e verifica a saúde dos serviços. Não altera contas. O estado físico após recriar o simulador segue o startup seguro existente; o estado observado antes e depois fica registrado. O volume de demonstração e os registros de auditoria são preservados; nenhuma exclusão automática. Não executar duas instâncias ao mesmo tempo. Interrupção externa/queda do host pode impedir `finally`: retome com `docker compose up -d --no-deps --force-recreate simulator writer` e confira/restaure a regra pela aplicação.

## Evidência e limites

Resultados locais em `evidence/acceptance/<execução>/result.json` e imagem da cena, ignorados pelo Git. Não contêm senha/JWT; relatório inclui configuração, etapas concluídas, frames, modelo, previsões e alertas. O estado de aprovação será consolidado no [registro de implementação](implementacao-2026-11-14.md).

É ensaio de funcionamento com um equipamento, não benchmark de capacidade/p95 nem validação clínica/física de diagnóstico. A resposta do LLM deve ser comparada com os números estruturados; streaming correto não garante toda interpretação. Não certifica uma transição nova com os limiares default: certifica a configuração didática fixada acima.

**Resultado de 14/11:** sequência funcional concluída duas vezes; revisão textual do LLM reprovada, mesmo após ajuste do contexto. O assistente continua pendente de decisão sobre modelo/qualidade. O relatório funcional não é selo de aprovação semântica. Veja o [registro completo](implementacao-2026-11-14.md).


**Consolidação após UI/UX:** o ensaio delimitado atual é [consolidation.spec.ts](../web-smart-fan-iot/frontend/e2e/consolidation.spec.ts), descrito no [README](../README.md). Ele reutiliza artefatos e não repete este cenário completo. O 1B foi mantido provisoriamente, com assistente parcial por fidelidade semântica; a avaliação de modelos está encerrada nesta rodada. Não tratar este arquivo como instrução para corrigir a fidelidade por novas tentativas.


**Aceite final de 19/11:** o ensaio usa as contas existentes, identifica cada comando e exige leitura física posterior; gera e treina uma única vez, mantém a seleção original e verifica os bloqueios de promoção. O chat real é consultado uma vez, com streaming e contexto estruturado registrados; a fidelidade semântica continua parcial, sem nova avaliação de modelos. Resultados desta execução serão registrados em [aceite integrado](aceite-integrado-2026-11-19.md).
