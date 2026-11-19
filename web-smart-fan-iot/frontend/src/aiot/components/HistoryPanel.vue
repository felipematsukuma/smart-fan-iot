<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue';
import { api } from '../auth';
import HistoryPowerChart from './HistoryPowerChart.vue';
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
const props = defineProps<{ deviceId: string; pilot?: boolean }>();
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
  <section
    class="card historical-panel"
    :class="{ 'pv-history-panel': pilot }"
    :aria-busy="busy"
  >
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
    <div
      v-if="pilot"
      class="pv-history-shortcuts"
      aria-label="Consultas rápidas do histórico"
    >
      <button type="button" :aria-pressed="hours === 1" @click="hours = 1">
        Última hora
      </button>
      <button type="button" :aria-pressed="hours === 24" @click="hours = 24">
        24 horas
      </button>
    </div>
    <p v-if="busy" class="table-message" role="status">
      Consultando histórico…
    </p>
    <p v-if="error" class="error-box" role="alert">{{ error }}</p>
    <p v-if="pilot && error && result" class="pv-history-period">
      Histórico anterior preservado. A consulta atual falhou; os valores abaixo
      não foram atualizados.
    </p>
    <template v-if="result && !busy"
      ><p v-if="pilot" class="pv-history-period">
        Consulta: {{ new Date(result.period_start).toLocaleString('pt-BR') }} —
        {{ new Date(result.period_end).toLocaleString('pt-BR') }}
      </p>
      <div class="energy-summary">
        <div>
          <small>{{
            pilot ? 'Energia na consulta' : 'Energia no período com cobertura'
          }}</small
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
          ><br v-if="!pilot" /><span v-if="!pilot"
            >{{ result.energy.total_samples.toLocaleString('pt-BR') }} amostras
            brutas · {{ result.energy.missing_samples }} sem potência</span
          >
        </p>
      </div>
      <p
        v-if="pilot && result.energy.coverage_fraction < 1"
        class="pv-history-period"
      >
        Cobertura parcial: energia calculada apenas sobre as leituras
        disponíveis.
      </p>
      <details v-if="pilot" class="pv-history-details">
        <summary>Detalhes da consulta</summary>
        <p>
          {{ result.energy.total_samples.toLocaleString('pt-BR') }} amostras ·
          {{ result.energy.missing_samples }} sem potência. Energia e cobertura
          referem-se à consulta completa, independentemente do recorte do
          gráfico.
        </p>
      </details>
      <p v-if="!result.chart.length" class="table-message">
        Nenhuma leitura no período selecionado.
      </p>
      <HistoryPowerChart
        v-if="pilot && result.chart.length"
        :points="result.chart"
        :period-end="result.period_end"
      />
      <component
        :is="pilot ? 'details' : 'div'"
        v-if="result.chart.length"
        class="table-scroll"
      >
        <summary v-if="pilot">Ver últimos 20 pontos agregados</summary>
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
      </component>
    </template>
  </section>
</template>
<style scoped>
.pv-history-details {
  padding: 0.5rem 1.71429rem;
  font-size: 1rem;
  color: #475569;
}
.pv-history-details p {
  margin: 0.5rem 0;
}
.pv-history-panel {
  font-size: 1.14286rem;
}
.pv-history-panel :is(small, p, caption, th, td, select, button) {
  font-size: 1rem;
  color: #475569;
}
.pv-history-panel :is(select, button) {
  min-height: 3.14286rem;
}
.pv-history-shortcuts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.57143rem;
  padding: 0 1.71429rem 0.85714rem;
}
.pv-history-shortcuts button {
  border: 1px solid #64748b;
  border-radius: 0.57143rem;
  background: white;
  padding: 0.57143rem 0.85714rem;
}
.pv-history-shortcuts button[aria-pressed='true'] {
  color: #fff;
  background: #0f766e;
}
.pv-history-shortcuts span {
  font-size: 1rem;
  color: #475569;
}

.pv-history-panel {
  border-radius: 12px;
  border-color: #e2e8f0;
  box-shadow: 0 1px 2px #0f172a05;
  margin-top: 0;
}
.pv-history-panel .section-heading {
  padding: 20px 24px 14px;
}
.pv-history-panel h2 {
  margin: 0;
  font-size: 1.21429rem;
}
.pv-history-panel .energy-summary {
  padding: 16px 24px 20px;
}
.pv-history-panel .energy-summary strong {
  font-size: 1.85714rem;
  letter-spacing: -0.6px;
  color: #1e293b;
}
.pv-history-panel .energy-summary p strong {
  font-size: inherit;
}
.pv-history-panel .history-controls select {
  border-color: #64748b;
  border-radius: 7px;
}
.pv-history-panel .table-scroll {
  border-top: 1px solid #edf1f4;
  padding: 14px 24px;
  font-size: 1rem;
}
.pv-history-panel summary {
  cursor: pointer;
  color: #475569;
  font-weight: 600;
}
.pv-history-period {
  font-size: 1rem;
  color: #475569;
  padding: 0 24px;
  margin: 0;
}
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
/* Explicit descendants outrank the retained legacy component selectors. */
.pv-history-panel .energy-summary small,
.pv-history-panel .energy-summary p,
.pv-history-panel .history-controls select,
.pv-history-panel .history-controls button,
.pv-history-panel .table-scroll :is(caption, th, td) {
  font-size: 1rem;
  color: #475569;
}
</style>
