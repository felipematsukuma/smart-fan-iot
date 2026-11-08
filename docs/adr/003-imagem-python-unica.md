# ADR 003 — Uma imagem Python, processos separados

Status: decisão proposta; builds e limites ainda [N].

Contexto: API, simulador e consumidores usarão Python e o mesmo pacote de contratos/features.

Decisão: uma imagem multi-stage com dependências pinadas e wheel comum; entrypoint por papel, UID não-root e importação de ML somente nos papéis necessários.

Alternativas: imagem por serviço multiplica manutenção; monoprocesso com treino/LLM bloqueia atendimento e dificulta pausar consumidor.

Consequências: cache e compatibilidade compartilhados; imagem maior, mas processos leves não importam todo o ML; permissões/segredos/volumes continuam distintos.

Não é microserviço HTTP por função: workers consomem AMQP e expõem apenas health interno.

Se remover processos writer/inference/jobs separados, perde-se isolamento necessário para recuperação e demonstração de fila parada.

Ver [serviços](../plano/03-arquitetura.md#21-inventário-alvo-de-serviços) e [DevOps](../plano/03-arquitetura.md#12-devops-subida-e-recuperação).
