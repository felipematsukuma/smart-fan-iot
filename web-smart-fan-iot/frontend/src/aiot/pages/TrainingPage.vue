<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
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
    await api(`/jobs/${selected.value.job_id}/cancel`, { method: 'POST' });
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
  <div class="page-heading">
    <div>
      <p class="eyebrow">AVALIAÇÃO E REGISTRO REPRODUZÍVEIS</p>
      <h1>Treinamento</h1>
      <p>
        Regressores independentes para saúde e RUL; baseline de média e
        avaliação por equipamento.
      </p>
    </div>
  </div>
  <p v-if="error" role="alert" class="error-box">{{ error }}</p>
  <p v-if="notice" role="status">{{ notice }}</p>
  <section class="card selection">
    <h2>Versão em uso e seleção desejada</h2>
    <p v-if="selectionStale" role="status">
      Seleção antiga: a última consulta falhou.
    </p>
    <p>
      Em uso:
      <strong data-testid="active-model">{{
        selection.active_version ?? 'Nenhum modelo ativado'
      }}</strong>
      · revisão {{ selection.active_revision }}
    </p>
    <p>
      Desejada:
      <strong>{{
        selection.desired_version ?? 'Nenhuma promoção solicitada'
      }}</strong>
      · revisão {{ selection.activation_revision }}
    </p>
    <p>
      Aprovado, desejado e efetivamente ativado são estados diferentes. Uma
      notificação de modelo disponível não autoriza sozinha a troca.
    </p>
  </section>
  <form class="card train-form" @submit.prevent="create">
    <fieldset :disabled="busy">
      <legend>Novo treino em fila</legend>
      <p v-if="loading && !datasets.length" role="status">
        Consultando datasets completos…
      </p>
      <p v-if="!loading && !datasets.length">
        Gere um dataset no Laboratório antes de treinar.
      </p>
      <div class="fields">
        <label
          >Dataset completo<select v-model="datasetId" required>
            <option disabled value="">Selecione</option>
            <option
              v-for="dataset in datasets"
              :key="dataset.id"
              :value="dataset.dataset_id"
            >
              {{ dataset.dataset_id }} ·
              {{ dataset.total.toLocaleString('pt-BR') }} vetores
            </option>
          </select></label
        ><label
          >Seed do split<input
            v-model.number="seed"
            type="number"
            min="0"
            max="2147483646"
            required /></label
        ><label
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
        Preprocessamento é ajustado só no treino; RUL censurada é excluída. Pelo
        menos dez equipamentos e cinco com falha observada são necessários;
        recomenda-se 30 ou mais.
      </p>
      <button class="button primary" type="submit" :disabled="!datasetId">
        Treinar modelos
      </button>
    </fieldset>
  </form>
  <section
    v-if="selected"
    class="card model-detail"
    :data-model-version="selected.version"
    :data-model-status="selected.status"
  >
    <h2>{{ selected.version }}</h2>
    <p>
      Estado: {{ selected.status }} ·
      {{ selected.approved ? 'Aprovado' : 'Não aprovado' }} · dataset
      {{ selected.dataset_id }}
    </p>
    <p v-if="selected.status === 'failed'">
      Métricas indisponíveis:
      {{
        failureLabels[selectedJob?.reason_code ?? ''] ??
        'o treino não concluiu; nenhuma métrica foi publicada'
      }}.
    </p>
    <template v-if="progress"
      ><progress
        :value="progress.processed"
        :max="progress.total"
        aria-label="Progresso do treinamento"
      ></progress>
      <p>
        {{ progress.processed }} / {{ progress.total }} etapas percentuais;
        {{ selectedJob?.reason_code ?? 'processamento em fila' }}
      </p></template
    ><button
      v-if="['queued', 'running'].includes(selected.status)"
      class="button secondary"
      :disabled="busy || selectedJob?.cancel_requested"
      @click="cancel"
    >
      Cancelar treino
    </button>
    <template v-if="report"
      ><p>
        {{ report.source_rows.toLocaleString('pt-BR') }} vetores de origem ·
        {{ report.feature_rows.toLocaleString('pt-BR') }} janelas válidas ·
        {{ report.feature_version }} · RUL em horas de calendário.
      </p>
      <p>
        Dataset SHA-256: {{ report.dataset_sha256 }}<br />Artefato SHA-256:
        {{ selected.artifact_sha256 }}
      </p>
      <div class="table-scroll">
        <table>
          <caption>
            Teste reservado por equipamento; indisponível não é substituído por
            zero.
          </caption>
          <thead>
            <tr>
              <th>Alvo</th>
              <th>Algoritmo escolhido</th>
              <th>MAE teste</th>
              <th>RMSE teste</th>
              <th>R² teste</th>
              <th>MAE baseline</th>
              <th>MAE benchmark</th>
              <th>Baseline benchmark</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(label, name) in labels" :key="name">
              <td>{{ label }}</td>
              <td>{{ report.targets[name].selected_algorithm }}</td>
              <td>{{ number(report.targets[name].test.mae) }}</td>
              <td>{{ number(report.targets[name].test.rmse) }}</td>
              <td>{{ number(report.targets[name].test.r2) }}</td>
              <td>{{ number(report.targets[name].test_baseline.mae) }}</td>
              <td>{{ number(report.targets[name].benchmark.mae) }}</td>
              <td>{{ number(report.targets[name].benchmark_baseline.mae) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
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
      <h3>Comparação na validação</h3>
      <div v-if="entry" class="table-scroll">
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
      <h3>Política de promoção</h3>
      <p>
        Ambos alvos: reduzir MAE ≥5% contra baseline e não piorar RMSE. Havendo
        ativo, nenhum MAE piora e um melhora ≥2%; sem regressão >10% por modo
        com amostra suficiente.
      </p>
      <p v-if="reasons.length">Bloqueios: {{ reasons.join(', ') }}</p>
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
      <h3>Limitações</h3>
      <ul>
        <li v-for="limitation in report.limitations" :key="limitation">
          {{ limitation }}
        </li>
      </ul>
      <details v-if="card">
        <summary>Model card</summary>
        <pre>{{ card }}</pre>
      </details></template
    >
  </section>
  <section class="card registry">
    <div class="section-heading"><h2>Registro de modelos</h2></div>
    <p v-if="!models.length" class="table-message">Nenhum modelo registrado.</p>
    <div v-else class="table-scroll">
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
            <td>{{ model.version }}</td>
            <td>{{ model.status }}</td>
            <td>{{ model.approved ? 'Aprovado' : 'Não aprovado' }}</td>
            <td>
              <button class="button secondary" @click="choose(model.version)">
                Ver {{ model.version }}
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
  </section>
</template>
<style scoped>
.selection,
.train-form,
.model-detail {
  padding: 1.4rem;
  margin-bottom: 1.5rem;
  overflow-wrap: anywhere;
}
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
}
.fields label,
.target-selector {
  display: grid;
  gap: 0.4rem;
}
.train-form fieldset {
  border: 0;
  padding: 0;
  min-width: 0;
}
.model-detail progress {
  width: 100%;
}
.target-selector {
  max-width: 300px;
  margin: 1rem 0;
}
.registry {
  margin-top: 1.5rem;
}
caption {
  padding: 1rem;
  text-align: left;
  font-size: 0.8rem;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 0.8rem;
}
details {
  margin: 1rem 0;
}
.model-detail p {
  line-height: 1.6;
  font-size: 0.85rem;
}
</style>
