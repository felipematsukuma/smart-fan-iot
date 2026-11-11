<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { Activity, Thermometer, Wind, Radio } from 'lucide-vue-next';
import { live, streamStatus, streamNotice } from '../realtime';
import LivePowerChart from '../components/LivePowerChart.vue';
import HistoryPanel from '../components/HistoryPanel.vue';

const selected = ref('');
const now = ref(Date.now());
let clock: ReturnType<typeof setInterval> | undefined;
const devices = computed(() => [...live.devices.values()]);
watch(
  devices,
  (value) => {
    if (!value.some((item) => item.id === selected.value))
      selected.value = value[0]?.id ?? '';
  },
  { immediate: true },
);
const frame = computed(() => live.frames.get(selected.value));
const fresh = computed(() => live.fresh(selected.value, now.value));
const readings = computed(() => frame.value?.conteudo.telemetry.readings);
const history = computed(() =>
  frame.value ? [...(live.history.get(selected.value) ?? [])] : [],
);
const insight = computed(() => frame.value?.conteudo.insight);
const presence = computed(() => live.availability.get(selected.value));
const format = (value: number | null | undefined, digits = 1) =>
  value == null
    ? '—'
    : value.toLocaleString('pt-BR', { maximumFractionDigits: digits });
const statusLabels = {
  offline: 'Desconectado',
  connecting: 'Conectando',
  authenticating: 'Autenticando',
  connected: 'Conectado',
  reconnecting: 'Reconectando',
};
onMounted(() => {
  clock = setInterval(() => {
    now.value = Date.now();
  }, 500);
});
onBeforeUnmount(() => clearInterval(clock));
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">SEU AMBIENTE, EM PERSPECTIVA</span>
      <h1>Visão geral</h1>
      <p class="muted">
        Condições do ambiente e acompanhamento do equipamento.
      </p>
    </div>
    <span
      class="status-pill"
      :class="fresh ? 'positive' : 'neutral'"
      role="status"
      >{{ statusLabels[streamStatus] }} ·
      {{ fresh ? 'Dados recentes' : 'Sem dados em tempo real' }}</span
    >
  </div>
  <label v-if="devices.length" for="selected-device">Equipamento</label
  ><select
    v-if="devices.length"
    id="selected-device"
    v-model="selected"
    class="device-selector"
  >
    <option v-for="device in devices" :key="device.id" :value="device.id">
      {{ device.name }} · {{ device.zone }}
    </option>
  </select>
  <p v-if="presence" class="muted reading-age">
    Último estado informado pelo dispositivo:
    {{ presence.status === 'online' ? 'online' : 'offline' }} ·
    {{ new Date(presence.timestamp).toLocaleTimeString('pt-BR') }}
  </p>
  <p v-if="streamNotice" class="notice" role="status">{{ streamNotice }}</p>
  <p v-if="frame" class="muted reading-age">
    Última amostra:
    {{ new Date(frame.timestamp).toLocaleTimeString('pt-BR') }} ·
    {{ Math.max(0, Math.floor((now - Date.parse(frame.timestamp)) / 1000)) }} s
    atrás{{ fresh ? '' : ' — sem dados recentes' }}
  </p>
  <div
    class="metric-grid"
    :class="{ 'stale-readings': !fresh }"
    data-testid="live-metrics"
    :data-source-id="frame?.conteudo.source_event_id"
    :data-sampled-at="frame?.timestamp"
    :data-observed-at="frame?.metadata.observed_at"
  >
    <article class="card metric">
      <Thermometer :size="20" /><span>Temperatura interna</span
      ><strong>{{ format(readings?.indoor_temp_c) }}<small> °C</small></strong>
      <p>Externa: {{ format(readings?.outdoor_temp_c) }} °C</p>
    </article>
    <article class="card metric">
      <Activity :size="20" /><span>Saúde do compressor</span
      ><strong
        >{{ insight?.status === 'valid' ? format(insight.health_score) : '—'
        }}<small v-if="insight?.status === 'valid'"> %</small></strong
      >
      <p>
        {{
          insight?.status === 'valid'
            ? `Vida útil estimada: ${format(insight.rul_calendar_hours)} h`
            : 'Sem previsão disponível'
        }}
      </p>
    </article>
    <article class="card metric">
      <Wind :size="20" /><span>Potência observada</span
      ><strong>{{ format(readings?.power_w, 0) }}<small> W</small></strong>
      <p>Corrente: {{ format(readings?.current_a, 2) }} A</p>
    </article>
  </div>
  <section v-if="frame" class="card" :data-frame-id="frame.id">
    <div class="section-heading">
      <h2>Potência em tempo real</h2>
      <span class="muted">Últimas {{ history.length }} amostras recebidas</span>
    </div>
    <LivePowerChart :frames="history" />
    <div class="sensor-summary">
      <span
        >Carcaça:
        <strong>{{ format(readings?.compressor_case_temp_c) }} °C</strong></span
      ><span
        >Vibração:
        <strong
          >{{ format(readings?.vibration_rms_mm_s, 2) }} mm/s</strong
        ></span
      ><span
        >Compressor:
        <strong>{{
          frame.conteudo.telemetry.actuators.compressor_on
            ? 'Ligado'
            : 'Desligado'
        }}</strong></span
      ><span
        >Ventilador:
        <strong>{{
          frame.conteudo.telemetry.actuators.condenser_fan_on
            ? 'Ligado'
            : 'Desligado'
        }}</strong></span
      >
    </div>
  </section>
  <section v-else class="card empty-state">
    <div class="empty-icon"><Radio :size="30" /></div>
    <h2>Aguardando leituras em tempo real</h2>
    <p>
      A conexão pode estar ativa mesmo quando o equipamento ainda não enviou um
      quadro recente.
    </p>
    <span class="muted">Nenhum valor estimado é exibido como leitura.</span>
  </section>
  <HistoryPanel v-if="selected" :device-id="selected" />
</template>
<style scoped>
.device-selector {
  max-width: 420px;
  margin-bottom: 1.2rem;
}
.reading-age {
  font-size: 0.8rem;
}
.stale-readings .metric > strong {
  color: #6e8189;
}
.sensor-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 1rem 1.4rem;
  border-top: 1px solid #e7edef;
  font-size: 0.8rem;
  color: #617782;
}
</style>
