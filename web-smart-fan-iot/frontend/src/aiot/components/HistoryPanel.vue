<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue';
import { api } from '../auth';
interface Metrics {
  period_start: string;
  period_end: string;
  chart: {
    timestamp: string;
    power_w: number | null;
    indoor_temp_c: number | null;
  }[];
  energy: {
    energy_wh: number | null;
    coverage_fraction: number;
    total_samples: number;
    missing_samples: number;
  };
}
const props = defineProps<{ deviceId: string }>();
const hours = ref(24);
const result = ref<Metrics | null>(null);
const busy = ref(false);
const error = ref('');
let controller: AbortController | undefined;
async function load() {
  controller?.abort();
  if (!props.deviceId) return;
  const request = new AbortController();
  controller = request;
  busy.value = true;
  error.value = '';
  try {
    const data = await api<Metrics>(
      `/devices/${encodeURIComponent(props.deviceId)}/metrics?hours=${hours.value}`,
      { signal: request.signal },
    );
    if (!request.signal.aborted) result.value = data;
  } catch (failure) {
    if (!request.signal.aborted)
      error.value =
        failure instanceof Error
          ? failure.message
          : 'Não foi possível consultar o histórico.';
  } finally {
    if (!request.signal.aborted) busy.value = false;
  }
}
const number = (value: number | null, digits = 2) =>
  value === null
    ? '—'
    : value.toLocaleString('pt-BR', { maximumFractionDigits: digits });
watch(
  () => [props.deviceId, hours.value],
  () => {
    result.value = null;
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => controller?.abort());
</script>
<template>
  <section class="card historical-panel" :aria-busy="busy">
    <div class="section-heading">
      <h2>Histórico e consumo</h2>
      <div class="history-controls">
        <label for="history-period" class="sr-only">Período do histórico</label
        ><select id="history-period" v-model="hours">
          <option :value="1">Última hora</option>
          <option :value="24">Últimas 24 horas</option>
          <option :value="168">Últimos 7 dias</option></select
        ><button class="button secondary" :disabled="busy" @click="load">
          Atualizar
        </button>
      </div>
    </div>
    <p v-if="busy" class="table-message" role="status">
      Consultando histórico…
    </p>
    <p v-if="error" class="error-box" role="alert">{{ error }}</p>
    <template v-if="result && !busy"
      ><div class="energy-summary">
        <div>
          <small>Energia no período com cobertura</small
          ><strong
            >{{
              number(
                result.energy.energy_wh !== null &&
                  result.energy.energy_wh >= 1000
                  ? result.energy.energy_wh / 1000
                  : result.energy.energy_wh,
              )
            }}
            {{
              result.energy.energy_wh !== null &&
              result.energy.energy_wh >= 1000
                ? 'kWh'
                : 'Wh'
            }}</strong
          >
        </div>
        <p>
          Cobertura observada:
          <strong
            >{{ number(result.energy.coverage_fraction * 100, 1) }}%</strong
          ><br />{{
            result.energy.total_samples.toLocaleString('pt-BR')
          }}
          amostras brutas · {{ result.energy.missing_samples }} sem potência
        </p>
      </div>
      <p v-if="!result.chart.length" class="table-message">
        Nenhuma leitura no período selecionado.
      </p>
      <div v-else class="table-scroll">
        <table>
          <caption>
            Últimos 20 pontos agregados do período. Energia calculada sobre
            leituras brutas, sem preencher lacunas.
          </caption>
          <thead>
            <tr>
              <th>Horário</th>
              <th>Potência</th>
              <th>Temperatura interna</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="point in result.chart.slice(-20)" :key="point.timestamp">
              <td>{{ new Date(point.timestamp).toLocaleString('pt-BR') }}</td>
              <td>{{ number(point.power_w) }} W</td>
              <td>{{ number(point.indoor_temp_c) }} °C</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
<style scoped>
.historical-panel {
  margin-top: 1.5rem;
}
.history-controls {
  display: flex;
  gap: 0.6rem;
}
.history-controls select {
  width: auto;
  padding: 0.5rem;
  font-size: 0.8rem;
}
.energy-summary {
  padding: 1rem 1.4rem;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
.energy-summary small {
  color: #637c87;
}
.energy-summary strong {
  display: block;
  font-size: 1.8rem;
}
.energy-summary p {
  color: #637c87;
  font-size: 0.8rem;
}
.energy-summary p strong {
  display: inline;
  font-size: inherit;
}
caption {
  padding: 0.7rem 1.4rem;
  text-align: left;
  font-size: 0.75rem;
  color: #637c87;
}
@media (max-width: 700px) {
  .section-heading {
    flex-wrap: wrap;
  }
  .energy-summary {
    flex-direction: column;
  }
}
</style>
