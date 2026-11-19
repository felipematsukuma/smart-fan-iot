<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { Card, Badge } from '../ui/primitives';
import '../ui/task-page.css';
import '../ui/job-pages.css';
import IdentifierDetails from '../components/IdentifierDetails.vue';
import { shortId, jobDate } from '../job-presentation';
import { api } from '../auth';
import { jobUpdates, streamStatus } from '../realtime';
interface Configuration {
  generator_version: 'hvac-lab-v1';
  days: number;
  equipment_count: number;
  sensor_counts: Record<string, number>;
  sample_interval_seconds: 1 | 2 | 5;
  seed: number;
  failure_fraction: number;
  failure_modes: ('mechanical_wear' | 'heat_transfer_loss')[];
  noise_std: number;
  missing_fraction: number;
  outlier_fraction: number;
  block_size: number;
  records_cap: number;
  start_utc: string;
}
interface Job {
  id: string;
  dataset_id: string;
  status: 'queued' | 'running' | 'completed' | 'cancelled' | 'failed';
  processed: number;
  total: number;
  cancel_requested: boolean;
  reason_code: string | null;
  attempts: number;
  updated_at: string;
  kind: string;
}
interface Dataset {
  id: string;
  rows: number;
  status: string;
  sha256: string | null;
  manifest: null | {
    content: {
      generator_version: string;
      rul_unit: string;
      channels: { field: string; primary: boolean; position: string }[];
      devices: { id: string; failure_observed: boolean }[];
    };
    execution: { seconds: number; peak_rss_mib: number | null };
  };
}
interface Preview {
  scope: string;
  rows: {
    equipment_index: number;
    timestamp_seconds: number;
    readings: (number | null)[];
    truth_health_score: number | null;
    truth_rul_calendar_hours: number | null;
  }[];
}
const config = ref<Configuration | null>(null);
const jobs = ref<Job[]>([]);
const selected = ref<Job | null>(null);
const dataset = ref<Dataset | null>(null);
const preview = ref<Preview | null>(null);
const busy = ref(false);
const error = ref('');
const loadingError = ref('');
const notice = ref('');
let key: string | undefined;
let requestConfig = '';
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
let selectedGeneration = 0;
const rows = computed(() =>
  config.value
    ? Math.floor(
        (config.value.days * 86400) / config.value.sample_interval_seconds,
      ) * config.value.equipment_count
    : 0,
);
const failurePercent = computed({
  get: () => (config.value?.failure_fraction ?? 0) * 100,
  set: (value: number) => {
    if (config.value) config.value.failure_fraction = value / 100;
  },
});
const channels = computed(() =>
  config.value
    ? Object.values(config.value.sensor_counts).reduce(
        (sum, value) => sum + value,
        0,
      )
    : 0,
);
const progress = computed(() => {
  const job = selected.value;
  if (!job) return null;
  const event = jobUpdates.get(job.id);
  return event && Date.parse(event.timestamp) >= Date.parse(job.updated_at)
    ? event.conteudo
    : job;
});
const labels: Record<string, string> = {
  current_a: 'Corrente (A)',
  compressor_case_temp_c: 'Carcaça (°C)',
  vibration_rms_mm_s: 'Vibração (mm/s)',
  indoor_temp_c: 'Temperatura interna (°C)',
  outdoor_temp_c: 'Temperatura externa (°C)',
};
const statusLabels = {
  queued: 'Na fila',
  running: 'Em execução',
  completed: 'Concluído',
  cancelled: 'Cancelado',
  failed: 'Falhou',
};
async function select(job: Job) {
  selectedGeneration++;
  selected.value = job;
  dataset.value = null;
  preview.value = null;
  await details(selectedGeneration);
}
async function details(generation: number) {
  const identity = selected.value?.dataset_id;
  if (
    !identity ||
    selected.value?.status !== 'completed' ||
    dataset.value?.id === identity
  )
    return;
  try {
    const [data, values] = await Promise.all([
      api<Dataset>(`/datasets/${identity}`),
      api<Preview>(`/datasets/${identity}/preview?limit=20`),
    ]);
    if (!disposed && generation === selectedGeneration) {
      dataset.value = data;
      preview.value = values;
    }
  } catch (failure) {
    if (!disposed && generation === selectedGeneration)
      loadingError.value =
        failure instanceof Error ? failure.message : 'Artefato indisponível.';
  }
}
async function refresh() {
  const request = new AbortController();
  controller = request;
  try {
    const response = await api<{ items: Job[] }>(
      '/jobs?limit=30&kind=generate',
      {
        signal: request.signal,
      },
    );
    if (disposed) return;
    jobs.value = response.items;
    loadingError.value = '';
    if (selected.value) {
      const updated = response.items.find(
        (job) => job.id === selected.value?.id,
      );
      if (updated) selected.value = updated;
      else
        selected.value = await api<Job>(`/jobs/${selected.value.id}`, {
          signal: request.signal,
        });
      await details(selectedGeneration);
    }
  } catch (failure) {
    if (!disposed && !request.signal.aborted)
      loadingError.value =
        failure instanceof Error ? failure.message : 'Jobs indisponíveis.';
  } finally {
    if (!disposed) timer = setTimeout(() => void refresh(), 2000);
  }
}
async function create() {
  if (!config.value) return;
  busy.value = true;
  error.value = '';
  notice.value = '';
  const body = JSON.stringify(config.value);
  if (!key || requestConfig !== body) {
    key = crypto.randomUUID();
    requestConfig = body;
  }
  try {
    const result = await api<Job>('/lab/jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body,
    });
    if (disposed) return;
    key = undefined;
    notice.value =
      'Job registrado de forma durável. O gerador executa em segundo plano.';
    await select(result);
    jobs.value = [result, ...jobs.value.filter((job) => job.id !== result.id)];
  } catch (failure) {
    if (!disposed)
      error.value =
        failure instanceof Error
          ? failure.message
          : 'Pedido sem confirmação. Repetir a mesma configuração reutiliza a chave.';
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function cancel() {
  if (!selected.value) return;
  busy.value = true;
  error.value = '';
  try {
    selected.value = await api<Job>(`/jobs/${selected.value.id}/cancel`, {
      method: 'POST',
    });
    notice.value =
      'Cancelamento solicitado. O estado só muda após confirmar a parada do trabalho.';
  } catch (failure) {
    error.value =
      failure instanceof Error
        ? failure.message
        : 'Falha ao solicitar cancelamento.';
  } finally {
    busy.value = false;
  }
}
onMounted(async () => {
  try {
    const defaults = await api<{ configuration: Configuration }>(
      '/lab/defaults',
    );
    if (!disposed) config.value = defaults.configuration;
  } catch (failure) {
    if (!disposed)
      error.value =
        failure instanceof Error
          ? failure.message
          : 'Configuração indisponível.';
  }
  if (!disposed) void refresh();
});
onBeforeUnmount(() => {
  disposed = true;
  selectedGeneration++;
  clearTimeout(timer);
  controller?.abort();
});
const number = (value: number | null) =>
  value === null
    ? '—'
    : value.toLocaleString('pt-BR', { maximumFractionDigits: 2 });
</script>
<template>
  <div class="task-page job-page">
    <header class="tp-heading"><h1>Dados sintéticos</h1></header>
    <p v-if="error" class="error-box" role="alert">{{ error }}</p>
    <p v-if="loadingError" class="error-box" role="alert">{{ loadingError }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="!config && !error" role="status">
      Carregando configuração do laboratório…
    </p>
    <form
      v-if="config"
      class="card tp-card lab-form"
      @submit.prevent="create"
      @invalid.capture="showInvalid"
      @input="clearInvalid"
    >
      <fieldset :disabled="busy">
        <legend>Nova geração</legend>
        <div class="tp-form-grid">
          <label
            >Período (dias)<input
              v-model.number="config.days"
              type="number"
              min="0.01"
              max="365"
              step="0.01"
              required /></label
          ><label
            >Equipamentos sintéticos<input
              v-model.number="config.equipment_count"
              type="number"
              min="3"
              max="1000"
              step="1"
              required /></label
          ><label
            >Intervalo entre vetores (s)<select
              v-model="config.sample_interval_seconds"
            >
              <option :value="1">1</option>
              <option :value="2">2</option>
              <option :value="5">5</option>
            </select></label
          ><label
            >Semente reproduzível<input
              v-model.number="config.seed"
              type="number"
              min="0"
              max="2147483647"
              step="1"
              required /></label
          ><label
            >Equipamentos com falha (%)<input
              v-model.number="failurePercent"
              type="number"
              min="0"
              max="100"
              step="1"
              required
          /></label>
        </div>
        <details class="tp-details">
          <summary>Opções avançadas</summary>
          <div class="tp-form-grid">
            <label
              >Ruído normalizado<input
                v-model.number="config.noise_std"
                type="number"
                min="0"
                max="0.2"
                step="0.005"
                required /></label
            ><label
              >Fração de leituras faltantes<input
                v-model.number="config.missing_fraction"
                type="number"
                min="0"
                max="0.2"
                step="0.005"
                required /></label
            ><label
              >Fração de outliers<input
                v-model.number="config.outlier_fraction"
                type="number"
                min="0"
                max="0.1"
                step="0.005"
                required /></label
            ><label
              >Vetores por bloco<input
                v-model.number="config.block_size"
                type="number"
                min="100"
                max="50000"
                step="100"
                required /></label
            ><label
              >Teto de vetores<input
                v-model.number="config.records_cap"
                type="number"
                min="1"
                max="5000000"
                step="1"
                required /></label
            ><label
              >Início sintético (UTC)<input
                v-model="config.start_utc"
                required
                placeholder="2026-01-01T00:00:00Z"
            /></label>
          </div>
          <h2>Sensores por equipamento</h2>
          <div class="tp-form-grid">
            <label v-for="(label, field) in labels" :key="field"
              >{{ label
              }}<input
                v-model.number="config.sensor_counts[field]"
                type="number"
                min="1"
                max="4"
                step="1"
                required
            /></label>
          </div>
          <p>
            Primeiro canal de cada tipo é primário; canais extras ficam no
            artefato auxiliar. Identidades sintéticas próprias; não cadastra nem
            comanda equipamentos reais.
          </p>
          <div class="actions">
            <label
              ><input
                v-model="config.failure_modes"
                type="checkbox"
                value="mechanical_wear"
              />Desgaste mecânico</label
            ><label
              ><input
                v-model="config.failure_modes"
                type="checkbox"
                value="heat_transfer_loss"
              />Perda de troca térmica</label
            >
          </div>
        </details>
        <p class="estimate" data-testid="dataset-estimate">
          Estimativa: {{ rows.toLocaleString('pt-BR') }} vetores ·
          {{ channels }} canais por vetor.
        </p>
        <p
          v-if="rows > config.records_cap || rows > 5000000"
          role="alert"
          class="error-box"
        >
          Volume acima do teto. Reduza dias/equipamentos ou aumente o intervalo.
        </p>
        <p v-if="config.equipment_count < 30">
          Menos de 30 equipamentos reduz diversidade e a avaliação por
          equipamento no treino.
        </p>
        <button
          class="button primary"
          type="submit"
          :disabled="
            rows < 1 ||
            rows > config.records_cap ||
            rows > 5000000 ||
            !config.failure_modes.length
          "
        >
          Gerar dataset
        </button>
      </fieldset>
    </form>
    <Card
      v-if="selected && progress"
      class="tp-card job-detail"
      :data-job-id="selected.id"
      :data-job-status="selected.status"
    >
      <div class="tp-section-heading">
        <h2>Geração selecionada</h2>
        <Badge>{{ statusLabels[selected.status] }}</Badge>
      </div>
      <IdentifierDetails :value="selected.id" label="Identificação do job"
        ><p>Tentativa {{ selected.attempts }}</p>
        <IdentifierDetails
          :value="selected.dataset_id"
          label="Identificação do dataset"
      /></IdentifierDetails>
      <progress
        v-if="progress.total > 0"
        :value="progress.processed"
        :max="progress.total"
        aria-label="Progresso da geração"
      ></progress>
      <p>
        {{ progress.processed.toLocaleString('pt-BR') }} de
        {{ progress.total.toLocaleString('pt-BR') }} vetores processados
      </p>
      <p v-if="streamStatus !== 'connected'" class="tp-muted">
        Atualização por consulta periódica; conexão de eventos indisponível.
      </p>
      <p v-if="selected.status === 'queued'">
        Aguardando fila e recurso exclusivo de CPU/memória.
      </p>
      <p v-if="selected.reason_code">Motivo: {{ selected.reason_code }}</p>
      <p
        v-if="
          selected.cancel_requested &&
          ['queued', 'running'].includes(selected.status)
        "
      >
        Cancelamento solicitado; aguardando parada confirmada.
      </p>
      <button
        v-if="['queued', 'running'].includes(selected.status)"
        class="button secondary"
        :disabled="busy || selected.cancel_requested"
        @click="cancel"
      >
        Cancelar geração
      </button>
      <p v-if="['failed', 'cancelled'].includes(selected.status)">
        Parcial não treinável; não há dataset completo publicado.
      </p>
      <template v-if="dataset?.manifest"
        ><h3>Resultado gerado</h3>
        <p>{{ dataset.rows.toLocaleString('pt-BR') }} vetores gerados</p>
        <details>
          <summary>Detalhes do artefato</summary>
          <p>
            SHA-256
            <code>{{ dataset.sha256 }}</code>
          </p>
          <p>
            Geração: {{ number(dataset.manifest.execution.seconds) }} s · pico
            do subprocesso:
            {{ number(dataset.manifest.execution.peak_rss_mib) }} MiB · RUL em
            horas de calendário.
          </p>
          <p>
            Rótulos sintéticos ficam somente neste laboratório e no artefato.
            RUL ausente indica falha não observada no período, nunca zero
            inventado. Hash desconsidera métricas de execução e tamanho do
            bloco.
          </p>
        </details></template
      >
    </Card>
    <Card v-if="preview" class="tp-card preview"
      ><details>
        <summary>Amostra com rótulos</summary>
        <div class="section-heading">
          <h2>Amostra do laboratório com rótulos</h2>
        </div>
        <div class="tp-table">
          <table>
            <caption>
              Até 20 posições do artefato; não é telemetria ao vivo. Rótulos
              nunca são publicados em MQTT ou WebSocket.
            </caption>
            <thead>
              <tr>
                <th>Equipamento</th>
                <th>Tempo sintético</th>
                <th>Cinco canais primários</th>
                <th>Saúde verdadeira</th>
                <th>RUL verdadeira (h)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in preview.rows" :key="index">
                <td>{{ row.equipment_index }}</td>
                <td>
                  {{
                    new Date(row.timestamp_seconds * 1000).toLocaleString(
                      'pt-BR',
                    )
                  }}
                </td>
                <td>
                  {{
                    row.readings
                      .filter(
                        (_, i) =>
                          dataset?.manifest?.content.channels[i]?.primary,
                      )
                      .map((value) => number(value))
                      .join(' · ')
                  }}
                </td>
                <td>{{ number(row.truth_health_score) }}</td>
                <td>{{ number(row.truth_rul_calendar_hours) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details></Card
    >
    <Card class="tp-card jobs">
      <div class="section-heading"><h2>Jobs recentes</h2></div>
      <p v-if="!jobs.length" class="table-message">Nenhum job registrado.</p>
      <div
        v-else
        class="tp-table"
        tabindex="0"
        role="region"
        aria-label="Jobs recentes"
      >
        <table>
          <caption>
            Gerações anteriores
          </caption>
          <thead>
            <tr>
              <th>Job</th>
              <th>Tipo</th>
              <th>Estado</th>
              <th>Vetores</th>
              <th>Ação</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in jobs" :key="job.id">
              <td data-label="Geração">
                {{ shortId(job.id)
                }}<small class="record-date">{{
                  jobDate(job.updated_at)
                }}</small>
              </td>
              <td data-label="Tipo">
                {{ job.kind === 'generate' ? 'Geração' : job.kind }}
              </td>
              <td data-label="Estado">{{ statusLabels[job.status] }}</td>
              <td data-label="Vetores">
                {{ job.processed.toLocaleString('pt-BR') }} /
                {{ job.total.toLocaleString('pt-BR') }}
              </td>
              <td>
                <button class="button secondary" @click="select(job)">
                  Ver geração
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
