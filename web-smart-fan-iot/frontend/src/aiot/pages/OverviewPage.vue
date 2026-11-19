<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import {
  Activity,
  Thermometer,
  Wind,
  Clock3,
  ArrowUpRight,
  Radio,
  AlertTriangle,
} from 'lucide-vue-next';
import { api } from '../auth';
import { live, streamStatus, streamNotice, alertRevision } from '../realtime';
import { presentation, type AlertRecord } from '../insights';
import { Card, Badge, Alert, Skeleton } from '../ui/primitives';
import Button from '../ui/Button.vue';
import { chartTitle, type ReadingKey } from '../live-chart';
import { overviewFreshness } from '../overview-freshness';
import LivePowerChart from '../components/LivePowerChart.vue';
import HistoryPanel from '../components/HistoryPanel.vue';
import ControlPanel from '../components/ControlPanel.vue';
const route = useRoute();
const chartReadings = ref<ReadingKey[]>(['power_w']);
const liveTitle = computed(() =>
  fresh.value ? chartTitle(chartReadings.value) : 'Últimas leituras',
);
const selected = ref('');
const now = ref(Date.now());
const chosen = ref(false);
const devices = computed(() => [...live.devices.values()]);
watch(
  [devices, () => [...live.frames.values()]],
  ([items]) => {
    const requested =
      typeof route.query.device === 'string' ? route.query.device : '';
    if (!chosen.value && items.some((item) => item.id === requested)) {
      selected.value = requested;
      chosen.value = true;
    }
    if (!items.some((item) => item.id === selected.value))
      selected.value = items[0]?.id ?? '';
    if (!chosen.value && !live.fresh(selected.value, Date.now()))
      selected.value =
        items.find((item) => live.fresh(item.id, Date.now()))?.id ??
        selected.value;
  },
  { immediate: true },
);
const device = computed(() => live.devices.get(selected.value));
const frame = computed(() => live.frames.get(selected.value));
// Incoming frames also invalidate this computed. A new sample must never be
// compared to the previous timer tick, which may predate its observation.
const freshness = computed(() =>
  overviewFreshness(
    frame.value,
    device.value?.boot_id,
    Math.max(now.value, Date.now()),
  ),
);
const fresh = computed(() => freshness.value.fresh);
const history = computed(() =>
  frame.value ? [...(live.history.get(selected.value) ?? [])] : [],
);
const forecast = computed(() =>
  presentation(frame.value, freshness.value.reference, fresh.value),
);
const reading = (
  field:
    | 'power_w'
    | 'indoor_temp_c'
    | 'outdoor_temp_c'
    | 'current_a'
    | 'compressor_case_temp_c'
    | 'vibration_rms_mm_s',
) => (fresh.value ? frame.value?.conteudo.telemetry.readings[field] : null);
const format = (value: number | null | undefined, digits = 1) =>
  value == null
    ? '—'
    : value.toLocaleString('pt-BR', { maximumFractionDigits: digits });
const time = (value: string) => new Date(value).toLocaleTimeString('pt-BR');
const age = computed(() => freshness.value.age);
const statusLabels = {
  offline: 'Desconectada',
  connecting: 'Conectando',
  authenticating: 'Autenticando',
  connected: 'Conectada',
  reconnecting: 'Reconectando',
};
const indicators = computed(() => [
  {
    label: 'Potência atual',
    value: reading('power_w'),
    unit: 'W',
    icon: Wind,
    help: 'Leitura indisponível',
    id: 'pilot-power',
  },
  {
    label: 'Temperatura interna',
    value: reading('indoor_temp_c'),
    unit: '°C',
    icon: Thermometer,
    help: 'Leitura indisponível',
    id: 'pilot-temperature',
  },
  {
    label: 'Saúde do compressor',
    value: forecast.value.health,
    unit: '%',
    icon: Activity,
    help:
      forecast.value.status === 'valid'
        ? 'Condição estimada do equipamento'
        : forecast.value.label,
    id: 'pilot-health',
  },
  {
    label: 'Vida útil restante',
    value: forecast.value.rul,
    unit: 'h',
    icon: Clock3,
    help:
      forecast.value.status === 'valid'
        ? 'Estimativa em horas de calendário'
        : forecast.value.label,
    id: 'pilot-rul',
  },
]);
const sensors = computed(() => [
  { label: 'Corrente', value: reading('current_a'), unit: 'A' },
  { label: 'Vibração', value: reading('vibration_rms_mm_s'), unit: 'mm/s' },
  {
    label: 'Temperatura da carcaça',
    value: reading('compressor_case_temp_c'),
    unit: '°C',
  },
  {
    label: 'Temperatura externa',
    value: reading('outdoor_temp_c'),
    unit: '°C',
  },
]);
const alerts = ref<AlertRecord[] | null>(null);
const alertsError = ref('');
const alertsBusy = ref(false);
let alertRequest: AbortController | undefined;
let alertTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
async function loadAlerts() {
  clearTimeout(alertTimer);
  alertRequest?.abort();
  if (!selected.value) return;
  const identity = selected.value;
  const request = new AbortController();
  alertRequest = request;
  alertsBusy.value = true;
  try {
    const result = await api<{ items: AlertRecord[] }>(
      `/alerts?device=${encodeURIComponent(identity)}&status=active&limit=30`,
      { signal: request.signal },
    );
    if (disposed || request.signal.aborted || selected.value !== identity)
      return;
    alerts.value = result.items;
    alertsError.value = '';
  } catch (error) {
    if (!request.signal.aborted && !disposed)
      alertsError.value =
        error instanceof Error
          ? error.message
          : 'Não foi possível confirmar os alertas.';
  } finally {
    if (!disposed && !request.signal.aborted) {
      alertsBusy.value = false;
      alertTimer = setTimeout(() => void loadAlerts(), 10000);
    }
  }
}
watch(selected, () => {
  alerts.value = null;
  alertsError.value = '';
  void loadAlerts();
});
watch(alertRevision, () => void loadAlerts());
const critical = computed(() =>
  alerts.value?.some((item) => item.severity === 'critical'),
);
let clock: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  clock = setInterval(() => {
    now.value = Date.now();
  }, 500);
  if (selected.value) void loadAlerts();
});
onBeforeUnmount(() => {
  disposed = true;
  clearInterval(clock);
  clearTimeout(alertTimer);
  alertRequest?.abort();
});
</script>
<template>
  <div class="pilot-view">
    <header class="pv-page-heading">
      <div>
        <p class="pv-eyebrow">MONITORAMENTO</p>
        <h1>Visão geral</h1>
      </div>
      <span class="pv-live-connection"
        ><Radio :size="14" aria-hidden="true" /> Conexão ao vivo:
        {{ statusLabels[streamStatus] }}</span
      >
    </header>
    <Card class="pv-equipment">
      <div class="pv-equipment-select">
        <label for="selected-device">Equipamento</label
        ><select
          v-if="devices.length"
          id="selected-device"
          v-model="selected"
          @change="chosen = true"
        >
          <option v-for="item in devices" :key="item.id" :value="item.id">
            {{ item.name }} · {{ item.zone }}
          </option></select
        ><Skeleton v-else-if="streamStatus !== 'connected'" />
        <p v-else>
          Nenhum equipamento disponível.
          <RouterLink to="/dispositivos">Consultar dispositivos</RouterLink>
        </p>
      </div>
      <div class="pv-freshness">
        <Badge :tone="fresh ? 'good' : 'neutral'" role="status">{{
          fresh
            ? 'Dados recentes'
            : freshness.kind === 'old'
              ? 'Dados desatualizados'
              : freshness.kind === 'missing'
                ? 'Sem telemetria'
                : 'Telemetria indisponível'
        }}</Badge>
        <p v-if="frame">
          Última leitura às {{ time(frame.timestamp)
          }}<span v-if="!fresh && age !== null"> · há {{ age }} s</span>
        </p>
        <p v-if="freshness.reason">{{ freshness.reason }}</p>
        <small v-if="device">{{ device.zone }}</small>
      </div>
    </Card>
    <Alert v-if="streamNotice" class="pv-notice">{{ streamNotice }}</Alert>
    <Alert v-if="!fresh && selected" tone="warning" class="pv-notice"
      ><strong>Sem telemetria recente</strong>
      <p>
        A conexão pode estar ativa sem novas leituras do equipamento. Valores
        atuais e comandos ficam indisponíveis; o histórico permanece acessível.
      </p></Alert
    >
    <Alert v-if="alertsError" tone="warning" class="pv-notice" role="alert"
      ><strong>Situação dos alertas não confirmada</strong>
      <p>
        {{ alertsError }} Os alertas já conhecidos não são encerrados por esta
        falha.
      </p>
      <Button @click="loadAlerts">Tentar novamente</Button></Alert
    >
    <Alert
      v-if="alerts?.length"
      :tone="critical ? 'danger' : 'warning'"
      class="pv-priority"
      ><div class="pv-alert-heading">
        <AlertTriangle :size="19" aria-hidden="true" /><strong>{{
          critical
            ? 'Alerta crítico no equipamento'
            : 'O equipamento precisa de atenção'
        }}</strong
        ><Button as-child variant="ghost"
          ><RouterLink :to="{ path: '/insights', query: { device: selected } }"
            >Ver Insights <ArrowUpRight :size="14" /></RouterLink
        ></Button>
      </div>
      <p>
        {{ alerts.length }}
        {{ alerts.length === 1 ? 'alerta ativo' : 'alertas ativos' }}. Ausência
        de novas previsões não significa recuperação.
      </p>
      <details>
        <summary>Origem e horários dos alertas</summary>
        <dl v-for="item in alerts" :key="item.id">
          <dt>
            {{ item.severity === 'critical' ? 'Crítico' : 'Atenção' }} · aberto
            em {{ new Date(item.raised_at).toLocaleString('pt-BR') }}
          </dt>
          <dd>
            Regra {{ item.rule_revision }} · modelo
            {{ item.model_version ?? 'Não informado' }} · alerta {{ item.id }}
          </dd>
        </dl>
      </details></Alert
    >
    <p v-else-if="alerts !== null && !alertsError" class="pv-alert-status">
      Nenhum alerta ativo confirmado na última consulta.
    </p>
    <p v-else-if="alertsBusy" class="pv-alert-status" role="status">
      Consultando alertas…
    </p>
    <div
      class="pv-kpis"
      data-testid="live-metrics"
      :data-source-id="frame?.conteudo.source_event_id"
      :data-sampled-at="frame?.timestamp"
      :data-observed-at="frame?.metadata.observed_at"
    >
      <Card v-for="item in indicators" :key="item.id" class="pv-kpi"
        ><div>
          <span>{{ item.label }}</span
          ><component :is="item.icon" :size="17" aria-hidden="true" />
        </div>
        <strong :data-testid="item.id"
          >{{ format(item.value)
          }}<small v-if="item.value != null">{{ item.unit }}</small></strong
        >
        <p v-if="item.value == null && fresh">{{ item.help }}</p></Card
      >
    </div>
    <details v-if="device" class="pv-source">
      <summary>Fonte e detalhes técnicos</summary>
      <dl>
        <dt>Equipamento</dt>
        <dd>{{ device.id }}</dd>
        <dt>Versão da previsão nesta amostra</dt>
        <dd>{{ forecast.version ?? 'Modelo indisponível' }}</dd>
        <dt>Horário da fonte</dt>
        <dd>
          {{
            frame
              ? new Date(frame.timestamp).toLocaleString('pt-BR')
              : 'Sem leitura'
          }}
        </dd>
        <dt>Evento de origem</dt>
        <dd>{{ frame?.conteudo.source_event_id ?? 'Sem evento' }}</dd>
      </dl>
      <p>
        Saúde e RUL vêm dos regressores e dos dados estruturados; não são
        respostas do assistente.
      </p>
    </details>
    <div v-if="selected" class="pv-live-layout">
      <ControlPanel
        :key="selected"
        :device-id="selected"
        :enabled="device?.enabled"
        pilot
        :pilot-fresh="fresh"
      />
      <Card class="pv-live-chart" :data-frame-id="frame?.id"
        ><div class="pv-section-heading">
          <div>
            <span v-if="fresh" class="pv-eyebrow">AO VIVO</span>
            <span v-else-if="frame" class="pv-eyebrow" role="status"
              >Atualização interrompida</span
            >
            <h2>{{ liveTitle }}</h2>
          </div>
          <span class="pv-muted">{{ history.length }} amostras</span>
        </div>
        <LivePowerChart
          :frames="history"
          v-model:selected="chartReadings"
          pilot
        />
        <div v-if="!history.length" class="pv-chart-empty">
          <Radio :size="28" />
          <h3>Aguardando telemetria</h3>
          <p>Aguardando dados do equipamento.</p>
        </div>
      </Card>
      <Card class="pv-readings"
        ><div class="pv-section-heading">
          <h2>Leituras do equipamento</h2>
          <Badge>{{ fresh ? 'Observadas' : 'Sem dados atuais' }}</Badge>
        </div>
        <dl class="pv-sensor-grid">
          <div v-for="item in sensors" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd>
              {{ format(item.value, 2)
              }}<small v-if="item.value != null"> {{ item.unit }}</small>
            </dd>
          </div>
        </dl></Card
      >
    </div>
    <div v-if="selected" class="pv-page-links">
      <Button as-child
        ><RouterLink
          :to="{ path: '/dispositivos', query: { device: selected } }"
          >Detalhes do equipamento
          <ArrowUpRight :size="14" /></RouterLink></Button
      ><Button as-child
        ><RouterLink :to="{ path: '/insights', query: { device: selected } }"
          >Analisar saúde e alertas
          <ArrowUpRight :size="14" /></RouterLink></Button
      ><a href="#pilot-history">Ir para histórico ↓</a>
    </div>
    <div v-if="selected" id="pilot-history" class="pv-history">
      <HistoryPanel :device-id="selected" pilot />
    </div>
  </div>
</template>
<style scoped>
.pilot-view {
  font-size: 1.14286rem;
  line-height: 1.5;
  color: #1e293b;
}
.pv-muted {
  color: #475569;
}
.pv-page-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}
.pv-eyebrow {
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 1.3px;
  color: #475569;
  margin: 0 0 6px;
}
.pv-page-heading h1 {
  font-size: 1.92857rem;
  letter-spacing: -0.8px;
  margin: 0 0 7px;
}
.pv-page-heading p:last-child {
  margin: 0;
  font-size: 1rem;
}
.pv-live-connection {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #475569;
  font-size: 1rem;
  flex-wrap: wrap;
}
.pv-equipment {
  padding: 20px 24px;
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: center;
  margin-bottom: 18px;
}
.pv-equipment-select {
  flex: 1;
  max-width: 510px;
}
.pv-equipment label {
  font-size: 1rem;
  color: #475569;
  font-weight: 600;
  margin: 0 0 6px;
}
.pv-equipment select {
  font-size: 1.14286rem;
  color: #1e293b;
  font-weight: 600;
  border-color: #64748b;
  padding: 10px 12px;
  border-radius: 7px;
}
.pv-freshness {
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.pv-freshness p {
  margin: 7px 0 0;
  color: #475569;
  font-size: 1rem;
}
.pv-freshness small {
  color: #475569;
  font-size: 1rem;
}
.pv-notice {
  margin: 12px 0;
}
.pv-notice p,
.pv-priority p {
  margin: 6px 0 0;
  font-size: 1rem;
  line-height: 1.6;
}
.pv-priority {
  margin: 16px 0;
}
.pv-alert-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pv-alert-heading > :last-child {
  margin-left: auto;
}
.pv-priority details {
  font-size: 1rem;
  margin-top: 10px;
}
.pv-priority dd {
  margin: 5px 0 10px;
  overflow-wrap: anywhere;
}
.pv-alert-status {
  font-size: 1rem;
  color: #475569;
  margin: 10px 0 18px;
}
.pv-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.pv-kpi {
  padding: 16px;
  min-width: 0;
}
.pv-kpi > div {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  color: #475569;
  font-size: 1rem;
}
.pv-kpi > strong {
  display: block;
  font-size: 2.21429rem;
  letter-spacing: -1px;
  font-weight: 650;
  color: #142c32;
  line-height: 1.4;
  margin: 6px 0 4px;
}
.pv-kpi small {
  font-size: 1.07143rem;
  margin-left: 6px;
  color: #475569;
  letter-spacing: 0;
  font-weight: 400;
}
.pv-kpi p {
  font-size: 1rem;
  color: #475569;
  margin: 0;

  line-height: 1.5;
}
.pv-source {
  margin: 12px 0 22px;
  font-size: 1rem;
  color: #475569;
}
.pv-source summary {
  cursor: pointer;
  width: fit-content;
}
.pv-source dl {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 6px;
  padding: 12px 0;
}
.pv-source dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.pv-live-layout {
  display: grid;
  grid-template-columns: minmax(285px, 1fr) minmax(0, 1.65fr);
  gap: 18px;
  align-items: start;
  grid-template-rows: min-content min-content;
  margin-bottom: 20px;
}
.pv-live-layout > :first-child {
  grid-row: 1;
}
.pv-readings {
  grid-column: 1;
  grid-row: 2;
}
.pv-live-layout .pv-sensor-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.pv-live-chart {
  grid-column: 2;
  grid-row: 1 / 3;
  min-width: 0;
  align-self: start;
}
.pv-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 16px;
}
.pv-section-heading h2 {
  font-size: 1.14286rem;
  letter-spacing: -0.3px;
  margin: 0;
}
.pv-section-heading > span {
  font-size: 1rem;
}
.pv-chart-caption {
  border-top: 1px solid #edf1f4;
  padding: 12px 24px;
  font-size: 1rem;
  color: #475569;
  margin: 0;
}
.pv-chart-empty {
  padding: 40px 24px;
  text-align: center;
  color: #475569;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.pv-chart-empty h3 {
  color: #334155;
  font-size: 1rem;
  margin-bottom: 6px;
}
.pv-chart-empty p {
  font-size: 1rem;
  max-width: 340px;
  margin: 0;
}
.pv-sensor-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
  padding: 0 24px 22px;
  gap: 16px;
}
.pv-sensor-grid dt {
  color: #475569;
  font-size: 1rem;
  margin-bottom: 3px;
}
.pv-sensor-grid dd {
  margin: 0;
  font-size: 1.42857rem;
  font-weight: 600;
  letter-spacing: -0.4px;
}
.pv-sensor-grid small {
  margin-left: 4px;
  font-size: 1rem;
  font-weight: 400;
  color: #475569;
}
.pv-page-links {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin: 18px 0 26px;
}
.pv-page-links > a {
  font-size: 1rem;
  color: #0f766e;
  margin-left: auto;
  text-decoration: underline;
}
.pv-history {
  scroll-margin-top: 20px;
}
.pilot-view :deep(:focus-visible) {
  outline: 2px solid #0f766e;
  outline-offset: 3px;
}
.pilot-view :deep(button),
.pilot-view :deep(select),
.pilot-view :deep(summary) {
  min-height: 3.14286rem;
}
.pilot-view :deep(summary) {
  cursor: pointer;
}
@media (max-width: 1250px) {
  .pv-live-layout {
    grid-template-columns: minmax(270px, 1fr) minmax(0, 1.3fr);
  }
  .pv-kpi {
    padding: 17px;
  }
  .pv-kpi > strong {
    font-size: 2rem;
  }
}
@media (max-width: 1100px) {
  .pv-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .pv-live-layout {
    grid-template-columns: 1fr;
  }
  .pv-live-layout > :first-child {
    grid-row: auto;
  }
  .pv-live-chart {
    grid-column: 1;
    grid-row: 2;
  }
  .pv-readings {
    grid-column: 1;
    grid-row: 3;
  }
}
@media (max-width: 600px) {
  .pv-page-heading {
    align-items: start;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 18px;
  }
  .pv-page-heading h1 {
    font-size: 1.78571rem;
  }
  .pv-equipment {
    padding: 18px;
    align-items: start;
    flex-direction: column;
    gap: 14px;
  }
  .pv-equipment-select {
    max-width: none;
    width: 100%;
  }
  .pv-freshness {
    font-variant-numeric: tabular-nums;
    text-align: left;
  }
  .pv-kpis {
    gap: 10px;
    grid-template-columns: 1fr;
  }
  .pv-kpi {
    padding: 16px 18px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    column-gap: 10px;
  }
  .pv-kpi > div {
    font-size: 1rem;
    grid-column: 1;
  }
  .pv-kpi > strong {
    font-size: 1.92857rem;
    grid-column: 2;
    grid-row: 1;
    margin: 0;
  }
  .pv-kpi p {
    font-size: 1rem;
    grid-column: 1;
    margin-top: 5px;
  }
  .pv-kpi > div > svg {
    display: none;
  }
  .pv-sensor-grid {
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    padding: 0 20px 20px;
  }
  .pv-section-heading {
    padding: 18px 20px;
  }
  .pv-source dl {
    grid-template-columns: 1fr;
  }
  .pv-source dd {
    margin-bottom: 7px;
  }
  .pv-page-links {
    align-items: stretch;
    flex-direction: column;
  }
  .pv-page-links > a {
    margin-left: 0;
  }
  .pv-alert-heading > :last-child {
    margin-left: 0;
  }
}
@media (max-width: 380px) {
  .pv-kpis {
    grid-template-columns: 1fr;
  }
}
</style>
