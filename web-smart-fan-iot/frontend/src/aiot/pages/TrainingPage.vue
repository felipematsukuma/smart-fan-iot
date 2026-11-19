<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import { Card } from '../ui/primitives';
import '../ui/task-page.css';
import '../ui/job-pages.css';
import IdentifierDetails from '../components/IdentifierDetails.vue';
import { shortId, jobDate } from '../job-presentation';
import { api, ApiError } from '../auth';
import { jobUpdates } from '../realtime';
import TrainingCharts from '../components/TrainingCharts.vue';
import type { ModelRecord, Selection, TargetName } from '../training-types';
interface Job {
  id: string;
  dataset_id: string;
  status: string;
  processed: number;
  total: number;
  updated_at: string;
  cancel_requested: boolean;
  reason_code: string | null;
}
const statusLabels = {
  queued: 'Na fila',
  running: 'Em execução',
  completed: 'Concluído',
  failed: 'Falhou',
  cancelled: 'Cancelado',
};
const datasets = ref<Job[]>([]);
const datasetId = ref('');
const seed = ref(42);
const benchmarkSeed = ref(31415);
const maximum = ref(100000);
const importanceRows = ref(1000);
const benchmarkRows = ref(30000);
const models = ref<ModelRecord[]>([]);
const selected = ref<ModelRecord | null>(null);
const selection = ref<Selection>({
  desired_version: null,
  active_version: null,
  activation_revision: 0,
  active_revision: 0,
});
const jobs = ref<Job[]>([]);
const cursor = ref<string | null>(null);
const target = ref<TargetName>('health_score');
const error = ref('');
const notice = ref('');
const busy = ref(false);
const loading = ref(false);
const card = ref('');
function showInvalid(event: Event) {
  const input = event.target as HTMLInputElement;
  input.setAttribute('aria-invalid', 'true');
  const details = input.closest('details');
  if (details) details.open = true;
  const label = input.closest('label');
  if (label && !label.querySelector('.tp-field-error')) {
    const message = document.createElement('span');
    message.className = 'tp-field-error';
    message.id = `field-error-${crypto.randomUUID()}`;
    message.textContent = input.validationMessage;
    input.setAttribute('aria-describedby', message.id);
    label.append(message);
  }
}
function clearInvalid(event: Event) {
  const input = event.target as HTMLInputElement;
  input.removeAttribute('aria-invalid');
  input.removeAttribute('aria-describedby');
  input.closest('label')?.querySelector('.tp-field-error')?.remove();
}
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let controller: AbortController | undefined;
let generation = 0;
let key: string | undefined;
let previousRequest = '';
const promotionRequests = new Map<
  string,
  { request_id: string; expected_revision: number }
>();
const report = computed(() => selected.value?.report);
const entry = computed(() => report.value?.targets[target.value]);
const labels: Record<TargetName, string> = {
  health_score: 'Saúde (0–100)',
  rul_calendar_hours: 'RUL (horas de calendário)',
};
const selectedJob = computed(() =>
  jobs.value.find((job) => job.id === selected.value?.job_id),
);
const progress = computed(() => {
  const job = selectedJob.value;
  if (!job) return null;
  const event = jobUpdates.get(job.id);
  return event && Date.parse(event.timestamp) >= Date.parse(job.updated_at)
    ? event.conteudo
    : job;
});
const reasons = computed(
  () =>
    selected.value?.promotion_reasons ?? report.value?.promotion_reasons ?? [],
);
function reasonLabel(reason: string) {
  if (reason === 'insufficient_active_improvement')
    return 'Melhoria insuficiente em relação ao modelo ativo';
  if (reason === 'active_reference_changed')
    return 'O modelo ativo mudou desde a avaliação';
  for (const target of ['health_score', 'rul_calendar_hours'] as const) {
    if (!reason.startsWith(target + '_')) continue;
    const descriptions: Record<string, string> = {
      undefined_metrics: 'métricas indisponíveis',
      below_baseline_gate: 'resultado abaixo do critério contra o baseline',
      active_not_comparable: 'comparação com o ativo indisponível',
      regresses_active: 'MAE pior que o modelo ativo',
      mechanical_wear_regression:
        'regressão acima do limite em desgaste mecânico',
      heat_transfer_loss_regression:
        'regressão acima do limite em perda de troca térmica',
    };
    const description = descriptions[reason.slice(target.length + 1)];
    if (description) return `${labels[target]}: ${description}`;
  }
  return `Motivo registrado: ${reason}`;
}
const selectionStale = ref(false);
const failureLabels: Record<string, string> = {
  insufficient_equipment_groups: 'equipamentos observados insuficientes',
  insufficient_observed_failures:
    'menos de cinco equipamentos com falha observada',
  health_score_insufficient_variation:
    'saúde sem variação ou amostra suficiente',
  rul_calendar_hours_insufficient_variation:
    'RUL sem falhas observadas ou amostra suficiente',
  training_data_or_artifact_invalid:
    'dados ou artefato não puderam ser validados',
};
async function choose(version: string) {
  const epoch = ++generation;
  card.value = '';
  try {
    const data = await api<ModelRecord>(`/models/${version}`);
    if (!disposed && epoch === generation) {
      selected.value = data;
      if (data.status === 'completed') {
        const modelCard = await api<{ markdown: string }>(
          `/models/${version}/card`,
        );
        if (!disposed && epoch === generation) card.value = modelCard.markdown;
      }
    }
  } catch (failure) {
    if (!disposed && epoch === generation)
      error.value =
        failure instanceof Error ? failure.message : 'Modelo indisponível.';
  }
}
async function refresh() {
  const request = new AbortController();
  controller = request;
  loading.value = true;
  try {
    const [registry, training, generated] = await Promise.all([
      api<{
        items: ModelRecord[];
        selection: Selection;
        next_cursor: string | null;
      }>('/models?limit=50', { signal: request.signal }),
      api<{ items: Job[] }>('/jobs?kind=train&limit=30', {
        signal: request.signal,
      }),
      api<{ items: Job[] }>('/jobs?kind=generate&limit=100', {
        signal: request.signal,
      }),
    ]);
    if (disposed) return;
    const incoming = new Set(registry.items.map((model) => model.version));
    models.value = [
      ...registry.items,
      ...models.value.filter((model) => !incoming.has(model.version)),
    ].slice(0, 200);
    selection.value = registry.selection;
    selectionStale.value = false;
    if (models.value.length <= 50) cursor.value = registry.next_cursor;
    jobs.value = training.items;
    datasets.value = generated.items.filter(
      (job) => job.status === 'completed',
    );
    if (!datasetId.value) datasetId.value = datasets.value[0]?.dataset_id ?? '';
    if (selected.value) {
      const current = models.value.find(
        (model) => model.version === selected.value?.version,
      );
      if (
        current &&
        (current.status !== selected.value.status ||
          current.approved !== selected.value.approved)
      )
        await choose(current.version);
    }
  } catch (failure) {
    if (!disposed && !request.signal.aborted) {
      selectionStale.value = true;
      error.value =
        failure instanceof Error ? failure.message : 'Registro indisponível.';
    }
  } finally {
    if (!disposed) {
      loading.value = false;
      timer = setTimeout(() => void refresh(), 3000);
    }
  }
}
async function create() {
  busy.value = true;
  error.value = '';
  notice.value = '';
  const body = JSON.stringify({
    dataset_id: datasetId.value,
    seed: seed.value,
    benchmark_seed: benchmarkSeed.value,
    max_feature_rows: maximum.value,
    benchmark_feature_rows: benchmarkRows.value,
    importance_rows: importanceRows.value,
  });
  if (!key || body !== previousRequest) {
    key = crypto.randomUUID();
    previousRequest = body;
  }
  try {
    const job = await api<Job>('/training/jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body,
    });
    if (disposed) return;
    key = undefined;
    notice.value =
      'Treino registrado. Escolha usa somente a validação; o teste permanece separado.';
    const registry = await api<{ items: ModelRecord[] }>('/models?limit=50');
    if (disposed) return;
    models.value = registry.items;
    const model = registry.items.find((item) => item.job_id === job.id);
    if (model) await choose(model.version);
    jobs.value = [job, ...jobs.value.filter((item) => item.id !== job.id)];
  } catch (failure) {
    if (!disposed)
      error.value =
        failure instanceof Error
          ? failure.message
          : 'Pedido de treino sem confirmação.';
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function promote() {
  if (!selected.value) return;
  busy.value = true;
  error.value = '';
  notice.value = '';
  const version = selected.value.version;
  let body = promotionRequests.get(version);
  if (!body) {
    body = {
      request_id: crypto.randomUUID(),
      expected_revision: selection.value.activation_revision,
    };
    promotionRequests.set(version, body);
  }
  try {
    await api(`/models/${version}/promote`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    promotionRequests.delete(version);
    notice.value =
      'Aprovação registrada. Versão em uso só muda após confirmação da inferência.';
    await choose(version);
    const state = await api<{ selection: Selection }>('/models?limit=1');
    if (!disposed) selection.value = state.selection;
  } catch (failure) {
    if (failure instanceof ApiError && failure.status === 409)
      promotionRequests.delete(version);
    if (!disposed)
      error.value =
        failure instanceof Error
          ? failure.message
          : 'Sem confirmação da promoção.';
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function cancel() {
  if (!selected.value) return;
  busy.value = true;
  try {
    const updated = await api<Job>(`/jobs/${selected.value.job_id}/cancel`, {
      method: 'POST',
    });
    jobs.value = jobs.value.map((job) =>
      job.id === updated.id ? updated : job,
    );
    notice.value = 'Cancelamento solicitado; aguarde parada confirmada.';
  } catch (failure) {
    error.value =
      failure instanceof Error ? failure.message : 'Cancelamento indisponível.';
  } finally {
    busy.value = false;
  }
}
async function more() {
  if (!cursor.value) return;
  busy.value = true;
  try {
    const result = await api<{
      items: ModelRecord[];
      next_cursor: string | null;
    }>(`/models?limit=50&before=${cursor.value}`);
    models.value = [...models.value, ...result.items].slice(0, 200);
    cursor.value = result.next_cursor;
  } catch (failure) {
    error.value =
      failure instanceof Error ? failure.message : 'Consulta indisponível.';
  } finally {
    busy.value = false;
  }
}
onMounted(() => void refresh());
onBeforeUnmount(() => {
  disposed = true;
  generation++;
  clearTimeout(timer);
  controller?.abort();
});
const number = (value: number | null | undefined) =>
  value == null
    ? 'Indisponível'
    : value.toLocaleString('pt-BR', { maximumFractionDigits: 3 });
</script>
<template>
  <div class="task-page job-page">
    <header class="tp-heading"><h1>Treinamento</h1></header>
    <p v-if="error" role="alert" class="error-box">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <Card class="tp-card selection">
      <h2>Versão em uso e seleção desejada</h2>
      <p v-if="selectionStale" role="status">
        Seleção antiga: a última consulta falhou.
      </p>
      <p>
        Em uso:
        <strong data-testid="active-model">{{
          selection.active_version
            ? shortId(selection.active_version)
            : 'Nenhum modelo ativado'
        }}</strong>
      </p>
      <p
        v-if="
          selection.active_version &&
          selection.active_version === selection.desired_version &&
          selection.active_revision === selection.activation_revision
        "
      >
        Seleção aplicada.
      </p>
      <p v-else>
        Selecionado para ativação:
        {{
          selection.desired_version
            ? shortId(selection.desired_version)
            : 'Nenhum'
        }}<span v-if="selection.desired_version">
          · aguardando confirmação</span
        >
      </p>
      <details>
        <summary>Detalhes da ativação</summary>
        <p>
          Em uso: {{ selection.active_version ?? 'Nenhum' }} · revisão
          {{ selection.active_revision }}
        </p>
        <IdentifierDetails
          v-if="selection.active_version"
          :value="selection.active_version"
          label="Identificador ativo"
        />
        <p>
          Seleção desejada: {{ selection.desired_version ?? 'Nenhuma' }} ·
          revisão {{ selection.activation_revision }}
        </p>
        <IdentifierDetails
          v-if="selection.desired_version"
          :value="selection.desired_version"
          label="Identificador selecionado"
        />
      </details>
    </Card>
    <form
      class="card tp-card train-form"
      @submit.prevent="create"
      @invalid.capture="showInvalid"
      @input="clearInvalid"
    >
      <fieldset :disabled="busy">
        <legend>Novo treino em fila</legend>
        <p v-if="loading && !datasets.length" role="status">
          Consultando datasets completos…
        </p>
        <p v-if="!loading && !datasets.length">
          Gere um dataset no Laboratório antes de treinar.
        </p>
        <div class="tp-form-grid">
          <label
            >Dataset completo<select v-model="datasetId" required>
              <option disabled value="">Selecione</option>
              <option
                v-for="dataset in datasets"
                :key="dataset.id"
                :value="dataset.dataset_id"
              >
                {{ jobDate(dataset.updated_at) }} ·
                {{ dataset.total.toLocaleString('pt-BR') }} vetores ·
                {{ shortId(dataset.dataset_id) }}
              </option>
            </select></label
          ><label
            >Semente da divisão<input
              v-model.number="seed"
              type="number"
              min="0"
              max="2147483646"
              required
          /></label>
        </div>
        <IdentifierDetails
          v-if="datasetId"
          :value="datasetId"
          label="Identificação do dataset selecionado"
        />
        <details class="tp-details">
          <summary>Opções avançadas do treino</summary>
          <div class="tp-form-grid">
            <label
              >Seed independente do benchmark<input
                v-model.number="benchmarkSeed"
                type="number"
                min="0"
                max="2147483647"
                required /></label
            ><label
              >Máximo de janelas candidatas<input
                v-model.number="maximum"
                type="number"
                min="1000"
                max="200000"
                step="1000"
                required /></label
            ><label
              >Janelas do benchmark<input
                v-model.number="benchmarkRows"
                type="number"
                min="1000"
                max="50000"
                step="1000"
                required /></label
            ><label
              >Amostra para importância<input
                v-model.number="importanceRows"
                type="number"
                min="100"
                max="2000"
                step="100"
                required
            /></label>
          </div>
          <p>
            Ridge e HistGradientBoosting são avaliados na validação.
            Preprocessamento é ajustado só no treino; RUL censurada é excluída.
            Pelo menos dez equipamentos e cinco com falha observada são
            necessários; recomenda-se 30 ou mais.
          </p>
        </details>
        <button class="button primary" type="submit" :disabled="!datasetId">
          Treinar modelos
        </button>
      </fieldset>
    </form>
    <Card
      v-if="selected"
      class="tp-card model-detail"
      :data-model-version="selected.version"
      :data-model-status="selected.status"
    >
      <h2>Treino selecionado</h2>
      <p class="tp-muted">{{ shortId(selected.version) }}</p>
      <IdentifierDetails
        :value="selected.version"
        label="Identificação do modelo"
      />
      <p>
        Estado: {{ statusLabels[selected.status] }} ·
        {{ selected.approved ? 'Modelo aprovado' : 'Modelo não aprovado' }}
        <span v-if="selected.version === selection.desired_version">
          · Selecionado para ativação</span
        >
        <span v-if="selected.version === selection.active_version">
          · Efetivamente ativo</span
        >
        <span v-else-if="selected.status === 'completed'"> · Não ativo</span>
      </p>
      <p v-if="selected.status === 'failed'">
        Métricas indisponíveis:
        {{
          failureLabels[selectedJob?.reason_code ?? ''] ??
          'o treino não concluiu; nenhuma métrica foi publicada'
        }}.
      </p>
      <template
        v-if="progress && ['queued', 'running'].includes(selected.status)"
        ><progress
          v-if="progress.total > 0"
          :value="progress.processed"
          :max="progress.total"
          aria-label="Progresso do treinamento"
        ></progress>
        <p>
          {{
            progress.total === 100
              ? `${progress.processed}% informado pelo treino`
              : 'Progresso detalhado indisponível'
          }}
          · {{ statusLabels[selected.status] }}
        </p></template
      >
      <p
        v-if="
          selectedJob?.cancel_requested &&
          ['queued', 'running'].includes(selected.status)
        "
        role="status"
      >
        Cancelamento solicitado; aguardando parada confirmada.
      </p>
      <button
        v-if="['queued', 'running'].includes(selected.status)"
        class="button secondary"
        :disabled="busy || selectedJob?.cancel_requested"
        @click="cancel"
      >
        Cancelar treino
      </button>
      <template v-if="report"
        ><details>
          <summary>Dataset e artefato</summary>
          <IdentifierDetails
            :value="selected.dataset_id"
            label="Identificação do dataset"
          />
          <p>
            {{ report.source_rows.toLocaleString('pt-BR') }} vetores de origem ·
            {{ report.feature_rows.toLocaleString('pt-BR') }} janelas válidas ·
            {{ report.feature_version }} · RUL em horas de calendário.
          </p>
          <p>
            Dataset SHA-256: {{ report.dataset_sha256 }}<br />Artefato SHA-256:
            {{ selected.artifact_sha256 }}
          </p>
        </details>
        <h3>Métricas por alvo</h3>
        <section
          v-for="(label, name) in labels"
          :key="name"
          class="metric-target"
        >
          <h3>{{ label }}</h3>
          <div class="tp-table responsive-metrics">
            <table>
              <caption>
                Teste reservado por equipamento ·
                {{
                  report.targets[name].test.count
                }}
                amostras ·
                {{
                  report.targets[name].selected_algorithm
                }}
              </caption>
              <thead>
                <tr>
                  <th>Avaliação</th>
                  <th>MAE ({{ name === 'health_score' ? 'pontos' : 'h' }})</th>
                  <th>RMSE ({{ name === 'health_score' ? 'pontos' : 'h' }})</th>
                  <th>R²</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>Modelo</th>
                  <td
                    :data-label="
                      'MAE' + (name === 'health_score' ? ' (pontos)' : ' (h)')
                    "
                  >
                    {{ number(report.targets[name].test.mae) }}
                  </td>
                  <td
                    :data-label="
                      'RMSE' + (name === 'health_score' ? ' (pontos)' : ' (h)')
                    "
                  >
                    {{ number(report.targets[name].test.rmse) }}
                  </td>
                  <td data-label="R²">
                    {{ number(report.targets[name].test.r2) }}
                  </td>
                </tr>
                <tr>
                  <th>Baseline (média)</th>
                  <td
                    :data-label="
                      'MAE' + (name === 'health_score' ? ' (pontos)' : ' (h)')
                    "
                  >
                    {{ number(report.targets[name].test_baseline.mae) }}
                  </td>
                  <td
                    :data-label="
                      'RMSE' + (name === 'health_score' ? ' (pontos)' : ' (h)')
                    "
                  >
                    {{ number(report.targets[name].test_baseline.rmse) }}
                  </td>
                  <td data-label="R²">
                    {{ number(report.targets[name].test_baseline.r2) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <details>
            <summary>Benchmark independente</summary>
            <div class="tp-table">
              <table>
                <caption>
                  {{
                    report.targets[name].benchmark.count
                  }}
                  amostras · semente
                  {{
                    report.benchmark_seed
                  }}
                  · MAE/RMSE em
                  {{
                    name === 'health_score' ? 'pontos' : 'horas de calendário'
                  }}
                </caption>
                <thead>
                  <tr>
                    <th>Avaliação</th>
                    <th>MAE</th>
                    <th>RMSE</th>
                    <th>R²</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(metric, key) in {
                      Modelo: report.targets[name].benchmark,
                      Baseline: report.targets[name].benchmark_baseline,
                    }"
                    :key="key"
                  >
                    <th>{{ key }}</th>
                    <td>{{ number(metric.mae) }}</td>
                    <td>{{ number(metric.rmse) }}</td>
                    <td>{{ number(metric.r2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        </section>
        <div class="target-selector">
          <label for="training-target">Alvo dos gráficos</label
          ><select id="training-target" v-model="target">
            <option value="health_score">Saúde</option>
            <option value="rul_calendar_hours">RUL (h de calendário)</option>
          </select>
        </div>
        <TrainingCharts
          v-if="entry"
          :entry="entry"
          :unit="target === 'health_score' ? 'pontos' : 'h de calendário'"
        />
        <details>
          <summary>Comparação na validação</summary>
          <div v-if="entry" class="tp-table">
            <table>
              <caption>
                Escolha do candidato não usa o teste reservado.
              </caption>
              <thead>
                <tr>
                  <th>Algoritmo</th>
                  <th>MAE</th>
                  <th>RMSE</th>
                  <th>R²</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(value, name) in entry.validation_candidates"
                  :key="name"
                >
                  <td>{{ name }}</td>
                  <td>{{ number(value.mae) }}</td>
                  <td>{{ number(value.rmse) }}</td>
                  <td>{{ number(value.r2) }}</td>
                </tr>
                <tr>
                  <td>Baseline (média)</td>
                  <td>{{ number(entry.validation_baseline.mae) }}</td>
                  <td>{{ number(entry.validation_baseline.rmse) }}</td>
                  <td>{{ number(entry.validation_baseline.r2) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
        <details>
          <summary>Equipamentos disjuntos e configuração</summary>
          <p v-for="(ids, name) in report.split" :key="name">
            {{ name }}: {{ ids.join(', ') }}
          </p>
          <p>
            Benchmark independente: seed {{ report.benchmark_seed }} ·
            {{ report.benchmark_sha256 }}
          </p>
          <pre>{{ JSON.stringify(report.hyperparameters, null, 2) }}</pre>
        </details>
        <h3>Aprovação e ativação</h3>
        <details>
          <summary>Regras de promoção</summary>
          <p>
            Ambos alvos: reduzir MAE ≥5% contra baseline e não piorar RMSE.
            Havendo ativo, nenhum MAE piora e um melhora ≥2%; sem regressão >10%
            por modo com amostra suficiente.
          </p>
        </details>
        <p v-if="reasons.length">
          Bloqueios: {{ reasons.map(reasonLabel).join('; ') }}
        </p>
        <p v-else>
          Critérios atendidos na avaliação registrada. Aprovação continua
          explícita.
        </p>
        <button
          class="button primary"
          :disabled="
            busy ||
            !!reasons.length ||
            selected.version === selection.desired_version
          "
          @click="promote"
        >
          Promover candidato
        </button>
        <details>
          <summary>Limitações registradas</summary>
          <ul>
            <li v-for="limitation in report.limitations" :key="limitation">
              {{ limitation }}
            </li>
          </ul>
        </details>
        <details v-if="card">
          <summary>Model card</summary>
          <pre>{{ card }}</pre>
        </details></template
      >
    </Card>
    <Card class="tp-card registry">
      <div class="section-heading"><h2>Registro de modelos</h2></div>
      <p v-if="!models.length" class="table-message">
        Nenhum modelo registrado.
      </p>
      <div
        v-else
        class="tp-table"
        tabindex="0"
        role="region"
        aria-label="Registro de modelos"
      >
        <table>
          <caption>
            Candidatos permanecem auditáveis, inclusive quando rejeitados.
          </caption>
          <thead>
            <tr>
              <th>Versão</th>
              <th>Estado</th>
              <th>Aprovação</th>
              <th>Ação</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="model in models" :key="model.version">
              <td data-label="Modelo">{{ shortId(model.version) }}</td>
              <td data-label="Estado">{{ statusLabels[model.status] }}</td>
              <td data-label="Aprovação">
                {{ model.approved ? 'Aprovado' : 'Não aprovado' }}
              </td>
              <td>
                <button class="button secondary" @click="choose(model.version)">
                  Ver modelo
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <button
        v-if="cursor && models.length < 200"
        class="button secondary"
        :disabled="busy"
        @click="more"
      >
        Mais modelos
      </button>
    </Card>
  </div>
</template>
