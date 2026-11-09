# M11 — Laboratório sintético e supervisor de jobs

| Item | Implementação e limite |
|---|---|
| Volume | [V] Padrão: 30 equipamentos × 2 dias × um vetor/5 s = **1.036.800 vetores**, não contagem de fields. Teto 5 M, blocos até 50 mil, até 1000 equipamentos e quatro sensores por tipo |
| Configuração UI | [V] Dias, equipamentos, canais, intervalo, seed, modos/proporção de falhas, ruído/faltantes/outliers, bloco, teto e início UTC sintético; estimativa antes de enviar. Config e hash são imutáveis no PostgreSQL |
| Física | [V] Aproximação didática quase estacionária de split on/off, coerente com assinaturas de corrente/carcaça/vibração e temperaturas interna/externa; ciclo/utilização e ambiente variam por equipamento. Não é reprodução passo a passo da dinâmica M03 nem calibração de fabricante |
| Verdade | [V] Saúde 0–100 e RUL em horas de **calendário** somente em arrays/manifesto e preview administrativo do Lab. Falha não observada no período: RUL NaN/JSON null, nunca zero. Equipamentos saudáveis permitem avaliar falsos positivos; não fornecem RUL exata |
| Sensores | [V] IDs sintéticos e posição por canal; primeiro de cada tipo é primário. Extras são auxiliares e não mudam o formato live. Campos de verdade não entram no contrato de telemetria ou progresso |
| Repetição | [V] Seed com substreams por equipamento/canal/tipo de perturbação. `.npy`/memmap, contagem e SHA-256 por arquivo; hash do conteúdo inclui configuração/versão NumPy/manifesto e exclui bloco, tempo e RSS da execução |
| Transporte | [V] API grava config/job/outbox atomicamente; `job.generate` usa q.jobs.generate, ACK após inbox durável. Mesmo pedido/chave retorna job original. Máximo dez jobs pendentes; eventos contêm somente IDs/referência de config |
| Runtime | [V] Serviço jobs-worker necessário para isolar cálculo da API. UID 10001, 1536 MiB/2 CPU, credenciais próprias, prefetch 1; subprocesso NumPy com bibliotecas numéricas limitadas a um thread. Não adiciona pandas/framework de jobs |
| Recursos | [V] Lease exclusivo heavy de 30 s, renovado a cada 5 s, junto à lease da inbox. Antes de gerar, descarrega Ollama e confirma ausência de modelos. Perda de renovação: watchdogs do pai e filho iniciam parada aos 18 s, antes do orçamento de 20 s |
| Prova de parada | [V] flock em inode persistente, herdado explicitamente pelo filho. Outro supervisor não adquire enquanto pai **ou filho** anterior estiver vivo. Recuperação libera lease somente após adquirir a mesma trava/provar parada. Expiração sozinha deixa recovering e não entrega recurso |
| Publicação | [V] Filho escreve em work; supervisor verifica contagem/config/hash com cercas SQL, move diretório atomicamente no mesmo volume e só então conclui no PG. Cancelamento concorrente tem prioridade sobre publicação lógica do dataset |
| Cancelamento | [V] Cooperativo entre blocos e durante hash, com terminate/kill+wait no supervisor. Estado só vira cancelled após parada. Partial permanece não treinável; nunca apaga nem promove silenciosamente o parcial |
| Disco | [V] Artefatos limitados a 4 GiB e reserva de 512 MiB livres, incluindo parciais. Falta de quota é falha explícita; sem remoção automática neste módulo. Até três execuções por job, preservando evidência de tentativas |

## Artefatos e recuperação

Volume nomeado artifacts, RW apenas para jobs-worker e RO para API. Diretório final
`datasets/{UUID}` contém arrays, configuração, progresso e manifesto; a disponibilidade
é determinada pelo estado completed no PostgreSQL, não pela mera presença do diretório.
Se o processo cair entre rename e commit, a recuperação pode validar o diretório final
e reconciliar a mesma configuração. Nenhum upload/caminho arbitrário é aceito pela API.

Não remover/substituir `.supervisor.lock`: o inode e seu FD herdado são a prova de
exclusão mesmo entre namespaces de PID. Se o processo filho sobreviver ao pai,
o watchdog independente encerra CPU pela ausência de renovação; o novo supervisor
espera a trava. Falha ao alcançar o PG mantém recuperação cercada até reconexão.

No live, UTC e clock_scale permanecem reais. O relógio sintético só existe no dataset;
o `job.progress` usa UTC atual e somente status/processed/total/reason_code. A UI usa
WebSocket para progresso e REST para recuperar o estado durável após reconexão.

## API

| Rota administrativa | Resultado |
|---|---|
| `GET /api/v1/lab/defaults`, `POST /lab/estimate` | Configuração/contagem e estimativa de bytes; excesso 422 |
| `POST /lab/jobs` + Idempotency-Key | 202 + Location para job; corpo LabConfig; duplicado não gera outro job |
| `GET /jobs`, `GET /jobs/{uuid}` | Paginação/estado durável, tentativa, processed/total e cancelamento solicitado |
| `POST /jobs/{uuid}/cancel` | 202 solicita parada, sem fingir conclusão antes do supervisor |
| `GET /datasets/{uuid}` | Config, estado, manifesto/hash somente após verificação |
| `GET /datasets/{uuid}/preview?limit=20` | Até 200 vetores via memmap, com rótulos lab-only; parcial retorna 409 |

NumPy 2.4.6 foi fixado para manter Python 3.11 da imagem e Python 3.14 local;
essa linha suporta ambos. [Release oficial](https://github.com/numpy/numpy/releases/tag/v2.4.6).
A linha 2.5 exige Python ≥3.12; não foi necessário trocar a base Python.
[Metadados oficiais](https://pypi.org/project/numpy/2.5.4/).

## Evidências locais

[V] 207 testes Python, 231 Vitest, 38 integrações e oito Playwright passaram; lint,
tipos, formatação e build passaram. Validações adicionais de tipos passaram após
explicitar os tipos do default de modos e da contagem de canais, sem mudar o vetor.

[V] Três gerações reais de 1.036.800 vetores em fila registraram 2,14/2,20/2,24 s
no subprocesso e picos de 96,9/97,0/96,3 MiB. Tempos incluem geração/escrita/hash
do filho; **não** são p95 do job completo, do Compose ou de consulta Influx.
O Lab não depende de escrever um milhão de pontos no Influx: seu artefato é completo;
a amostra lab em Influx é opcional na arquitetura aprovada e não foi adicionada.

[V] Playwright gera dois milhões em dois jobs e compara os hashes, consulta preview
e cancela outro pedido sem dataset completo. Captura WS verifica ausência de verdade
latente. Integração cobre cancelamento já em execução, filho efetivamente parado,
expiração sem transferência, geração cercada, trava herdada e heartbeat antigo.
Testes estatísticos verificam três assinaturas de falha, proporções de perturbações,
censura e hash idêntico com blocos de tamanhos diferentes.

[test-lab.ps1](../../tools/bootstrap/test-lab.ps1) reproduz banco/bucket descartáveis
e navegador no Compose real. Gera datasets de teste no volume; não executar durante
demonstração. O script não imprime credenciais e não limpa dados reais.

[N] Treino/promoção/inferência pertencem a M12/M13; dataset completo não significa
modelo aprovado. Retenção dos parciais, backup/restore, p95 integrado, CI remoto e
scans finais permanecem em M17/M18. Segurança da troca de recurso com streaming
Ollama será verificada junto ao assistente M16; aqui foi executado unload real.
