# M12 — Treino, avaliação e registro

| Aspecto | Implementação |
|---|---|
| Alvos/modelos | [V] Dois regressores independentes: saúde e RUL em horas de calendário. Ridge e HistGradientBoosting são ajustados por alvo; validação escolhe o algoritmo, teste fica reservado. DummyRegressor(mean) é ajustado somente no treino |
| Fonte | [V] Somente dataset completed com configuração/contagem/hashes verificados. Seleção limitada de janelas evita materializar milhão de dicts; massa original permanece memmap. Cinco canais primários observados; auxiliares/rótulos/IDs/seed/modo de falha não entram no vetor |
| Features compartilhadas | [V] [summarize_window](../../packages/smartfan_common/src/smartfan_common/features.py) é o mesmo núcleo instalado usado pelo FeatureWindow incremental. Corte causal explícito recusa futuro; split de equipamento/boot/estado precede cálculo. Versão hvac-window-v1, ordem de 18 atributos e configuração de janela são registradas |
| Split | [V] Grupos de equipamento 60/20/20 no padrão de 30 máquinas, com arredondamento explícito em outros tamanhos. Estratifica disponibilidade de RUL observada para reservar exemplos desse alvo; pelo menos dez grupos e cinco com falha observada. Identidade é dataset-hash + ID sintético; grupos não se misturam |
| Censura/qualidade | [V] RUL desconhecida excluída, nunca imputada como zero. Janelas sem cobertura suficiente são rejeitadas. Quantis 1/99%, mediana e scaler são ajustados somente no treino e persistidos no pipeline; não usam estatísticas da validação/teste |
| Benchmark | [V] Outra seed gera frota independente com o mesmo cenário/config, preservada no artefato do modelo. Candidato, baseline e ativo de referência são avaliados nas mesmas janelas. Mudança do ativo antes de promover exige nova comparação |
| Relatório | [V] MAE/RMSE/R² por alvo, candidatos/baseline na validação, teste e benchmark; scatter ≤200 pontos, importância por permutação (duas repetições, amostra limitada), contagens/censura/modos, split/hash, versões e hiperparâmetros. Métrica indefinida mantém null e motivo |
| Falta de dados | [V] Sem grupos/falhas/variação suficientes, job falha com motivo estável; UI informa métricas indisponíveis. Não registra R² fictício. Benchmark sem RUL observada fica indisponível e bloqueia promoção |
| Artefato | [V] Bundle confiável, relatório, model card e benchmark com hashes. Sem upload/caminho de usuário; loader compara hash antes de desserializar versão ativa de referência. Políticas e predição limitada (saúde 0–100/RUL ≥0) também são compartilhadas |
| Execução | [V] q.jobs.train, usuário jobs-worker, prefetch 1, mesmo supervisor/lease/cancelamento M11; subprocesso com threads numéricas limitados a um. Treino/cancelamento não alteram dataset de origem |

## Aprovação e ativação

1. Worker conclui avaliação e grava métricas/artefato; não tem permissão para aprovar.
2. Admin pede promoção com UUID idempotente e expected_revision da seleção.
3. API recalcula política a partir de métricas do worker, bloqueia seleção em transação,
   confere ativo de referência e grava approved + desired_version + revisão monotônica
   + notificação pendente + auditoria atomicamente. API não pode editar métricas.
4. O mesmo worker transforma notificação em outbox autenticada model.available e marca
   enqueued na mesma transação. Notificação superada é marcada superseded. A API não
   publica fingindo ser jobs-worker nem ganha acesso à outbox de outro proprietário.
5. [N] M13 implementará carga/verificação e troca atômica, revalidando aprovação,
   desired_version e activation_revision antes da troca. model.available sozinho
   não ativa. A UI apresenta desired e active separadamente; active só muda pela inferência.

Política: ambos alvos reduzem MAE ≥5% contra baseline sem piorar RMSE. Contra ativo
comparável, nenhum MAE piora e pelo menos um melhora ≥2%; regressão >10% em modo com
≥100 exemplos bloqueia. Métricas indefinidas ou referência ativa diferente bloqueiam.
Candidato rejeitado permanece auditável; não há retreino/promoção automática.

## API administrativa e UI

| Rota | Uso |
|---|---|
| `POST /api/v1/training/jobs` + Idempotency-Key | Dataset UUID, seeds, teto de janelas e amostras de benchmark/importância; 202 + Location |
| `GET /api/v1/jobs?kind=train` | Progresso percentual durável; WS publica somente status/contadores, sem rótulos |
| `POST /api/v1/jobs/{uuid}/cancel` | Mesmo supervisor, parada confirmada; origem continua completed |
| `GET /api/v1/models?before={version}` | Registro paginado, seleção desired/active e revisões |
| `GET /api/v1/models/{version}`, `/card` | Métricas, manifesto, aprovação e model card como texto seguro |
| `POST /api/v1/models/{version}/promote` | request_id + expected_revision; 202 ou 409 com bloqueios |

Treinamento oferece configuração mínima, estados de fila/erro/cancelamento, duas
tabelas de comparação, scatter e importância com alternativa tabular, IDs do split,
limitações/model card e promoção. Somente administrador acessa registro e ações.
O seletor dos gráficos tem associação explícita label/for/id verificada no navegador.

Dependências pinadas: scikit-learn 1.9.1 e transitivas compatíveis com Python 3.11,
sem pandas ou framework extra de jobs. SciPy/joblib/threadpoolctl/narwhals/cloudpickle
atendem ao runtime do estimador/serialização; removê-las quebra importação ou execução.
Referências primárias: [scikit-learn](https://pypi.org/project/scikit-learn/1.9.1/),
[SciPy](https://pypi.org/project/scipy/1.17.1/), [joblib](https://pypi.org/project/joblib/1.6.0/).

## Medição executada na mesma máquina

[V] Ensaio real por API→fila→subprocesso sobre **1.036.800 vetores**: 37,09 s no filho,
pico 246,73 MiB, 100 mil janelas candidatas antes dos filtros. Não é p95 integrado.

| Alvo | Escolhido | MAE benchmark | MAE baseline | R² benchmark |
|---|---|---:|---:|---:|
| Saúde (pontos) | Ridge | 0,569 | 23,006 | 0,998 |
| RUL (h de calendário) | HistGradientBoosting | 3,177 | 9,746 | 0,840 |

[I] R² elevado da saúde é coerente com a construção analítica do gerador: seus
sensores carregam assinaturas diretas da degradação. Isso exige validação externa,
não comprova acurácia em equipamento real. [V] Testes alteram os rótulos e obtêm os
mesmos vetores, comparam lote/incremental e recusam futuro. Benchmark usa outra seed,
mas continua sendo o mesmo gerador; o model card explicita essa limitação.

## Verificação e pendências

[V] 214 testes Python da evolução, 153 testes do backend legado e 231 Vitest passaram.
Lint, tipos, formatação e build passaram. Nove percursos Playwright foram validados:
oito no ensaio completo e o treino novamente após corrigir a associação do rótulo do
seletor. Repetição do treino compara métricas com tolerância 1e-8. O runner com overlay
também executou as sete integrações do registro/treino. Aviso de chunk do validador
continua documentado no M07; CI remoto e scans não são certificados por estes checks.

[V] 45 integrações passaram, incluindo treino em subprocesso, privilégios por coluna,
candidato inferior rejeitado, referência ativa alterada, notificação atrasada superada,
idempotência e origem preservada no cancelamento. Fixtures de métricas exercitam a
política/autorizações, não certificam qualidade; a medição acima usa modelo real.

[test-training.ps1](../../tools/bootstrap/test-training.ps1) usa bancos descartáveis
e navegador real. O runner descartável usa [overlay de testes](../../infra/compose.test.yaml)
de 768 MiB para acomodar pytest mais subprocesso; sem isso, o limite de 192 MiB do
bootstrap one-shot pode limitar o teste a frio. Aplicação usa seu orçamento próprio.

[N] Hot-reload, reconstrução de janelas live, alertas/drift e versão efetivamente em
uso são M13. CI remoto, scan e aceite de carga/backup são M17/M18. A operação em
equipamento real permanece fora desta validação sintética.
