<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import axios from 'axios';
import { useWebSocket } from './composables/useWebSocket';
import RealtimeChart from './components/RealtimeChart.vue';
import type { Device, MetricsSummary } from './types';

const DEVICE_ID = 'esp32_fan_01';
const API_BASE = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000/api';
const WS_URL = (import.meta.env.VITE_WS_URL as string) || 'ws://localhost:8000/ws';
const DEFAULT_PERIOD_HOURS = 8;
const METRICS_REFRESH_MS = 5000;

const toDateTimeInput = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const { telemetry, isConnected, lastMessageAt } = useWebSocket(WS_URL, DEVICE_ID);
const now = ref(Date.now());
const periodStart = ref(toDateTimeInput(new Date(Date.now() - DEFAULT_PERIOD_HOURS * 60 * 60 * 1000)));
const periodEnd = ref(toDateTimeInput(new Date()));
const isLivePeriod = ref(true);
let statusTimer: ReturnType<typeof setInterval> | null = null;
let metricsTimer: ReturnType<typeof setInterval> | null = null;
let isCommandPending = ref(false);
let feedback = ref<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
type PowerAction = 'ON' | 'OFF';
let pendingCommand: { action: PowerAction; expectedState: boolean } | null = null;
let commandTimeout: ReturnType<typeof setTimeout> | null = null;

const clearCommandConfirmation = () => {
  pendingCommand = null;
  if (commandTimeout) {
    clearTimeout(commandTimeout);
    commandTimeout = null;
  }
};

const device = ref<Device>({
  id: 1,
  device_id: DEVICE_ID,
  name: 'Ventilador Quarto',
  is_on: false,
  kwh_rate: 0.85,
  auto_off_time: '03:00',
  auto_off_enabled: true
});

const metrics = ref<MetricsSummary>({
  device_id: DEVICE_ID,
  duration_hours: DEFAULT_PERIOD_HOURS,
  avg_power_w: 0,
  energy_wh: 0,
  estimated_kwh: 0,
  history_count: 0,
  history: []
});

const hasTelemetry = computed(() => (
  lastMessageAt.value !== null && now.value - lastMessageAt.value <= 10_000
));

watch(
  () => telemetry.value.is_on,
  (isOn) => {
    if (!pendingCommand || isOn !== pendingCommand.expectedState) return;

    const action = pendingCommand.action;
    clearCommandConfirmation();
    isCommandPending.value = false;
    feedback.value = {
      type: 'success',
      text: `Comando ${action} confirmado pelo ESP32.`,
    };
  },
);

const getErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === 'string' ? detail : error.message;
  }
  return fallback;
};

const loadDeviceData = async () => {
  try {
    const devRes = await axios.get(`${API_BASE}/device/${DEVICE_ID}`);
    if (devRes.data?.device_id === DEVICE_ID) device.value = devRes.data;
  } catch (error) {
    feedback.value = {
      type: 'error',
      text: getErrorMessage(error, 'Não foi possível carregar o dispositivo.')
    };
  }
};

const updateLivePeriod = () => {
  const current = new Date();
  periodEnd.value = toDateTimeInput(current);
  periodStart.value = toDateTimeInput(
    new Date(current.getTime() - DEFAULT_PERIOD_HOURS * 60 * 60 * 1000)
  );
};

const getSelectedPeriod = () => {
  const start = new Date(periodStart.value);
  const end = new Date(periodEnd.value);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    feedback.value = {
      type: 'error',
      text: 'Informe um início e um fim válidos para o período.'
    };
    return null;
  }
  if (start >= end) {
    feedback.value = {
      type: 'error',
      text: 'O início do período deve ser anterior ao fim.'
    };
    return null;
  }
  return { start, end };
};

const loadMetrics = async () => {
  let period: { start: Date; end: Date } | null;
  if (isLivePeriod.value) {
    const end = new Date();
    const start = new Date(end.getTime() - DEFAULT_PERIOD_HOURS * 60 * 60 * 1000);
    periodStart.value = toDateTimeInput(start);
    periodEnd.value = toDateTimeInput(end);
    period = { start, end };
  } else {
    period = getSelectedPeriod();
  }
  if (!period) return false;

  try {
    const metricsRes = await axios.get(
      `${API_BASE}/device/${DEVICE_ID}/metrics`,
      {
        params: {
          start: period.start.toISOString(),
          end: period.end.toISOString()
        }
      }
    );
    metrics.value = {
      ...metrics.value,
      ...metricsRes.data,
      history: metricsRes.data.history ?? []
    };
    return true;
  } catch (error) {
    feedback.value = {
      type: 'error',
      text: getErrorMessage(error, 'Não foi possível carregar o consumo do InfluxDB.')
    };
    return false;
  }
};

const applyPeriod = async () => {
  const period = getSelectedPeriod();
  if (!period) return;
  isLivePeriod.value = false;
  if (await loadMetrics()) {
    feedback.value = {
      type: 'success',
      text: 'Período aplicado. O consumo e o custo foram recalculados.'
    };
  }
};

const selectLast8Hours = async () => {
  isLivePeriod.value = true;
  updateLivePeriod();
  await loadMetrics();
};

const togglePower = async () => {
  if (isCommandPending.value) return;

  if (!isConnected.value || !hasTelemetry.value) {
    feedback.value = {
      type: 'error',
      text: 'ESP32 sem telemetria recente. Abra a aba Wokwi e deixe-a visível antes de enviar comandos.'
    };
    return;
  }

  const newAction: PowerAction = telemetry.value.is_on ? 'OFF' : 'ON';
  const expectedState = newAction === 'ON';
  isCommandPending.value = true;
  pendingCommand = { action: newAction, expectedState };
  feedback.value = {
    type: 'info',
    text: `Comando ${newAction} enviado. Aguardando confirmação do ESP32...`
  };

  commandTimeout = setTimeout(() => {
    if (!pendingCommand || pendingCommand.action !== newAction) return;
    clearCommandConfirmation();
    isCommandPending.value = false;
    feedback.value = {
      type: 'error',
      text: `O ESP32 não confirmou ${newAction}. A simulação Wokwi pode estar pausada; abra a aba Wokwi e tente novamente.`
    };
  }, 10_000);

  try {
    await axios.post(`${API_BASE}/device/${DEVICE_ID}/command`, { action: newAction });
  } catch (error) {
    clearCommandConfirmation();
    isCommandPending.value = false;
    feedback.value = {
      type: 'error',
      text: getErrorMessage(error, 'Falha ao enviar o comando.')
    };
  }
};

const saveSchedule = async () => {
  try {
    await axios.put(`${API_BASE}/device/${DEVICE_ID}/schedule`, {
      auto_off_time: device.value.auto_off_time,
      auto_off_enabled: device.value.auto_off_enabled,
      kwh_rate: Number(device.value.kwh_rate)
    });
    feedback.value = {
      type: 'success',
      text: 'Agendamento salvo e publicado no ESP32.'
    };
  } catch (error) {
    feedback.value = {
      type: 'error',
      text: getErrorMessage(error, 'Falha ao salvar o agendamento.')
    };
  }
};

const formatKwh = (value: number) => (
  value >= 0.001 ? value.toFixed(3) : value.toFixed(6)
);

const formatCurrency = (value: number) => (
  value >= 0.1 ? value.toFixed(2) : value.toFixed(5)
);

const estimatedCost = computed(() => formatCurrency(
  metrics.value.estimated_kwh * Number(device.value.kwh_rate || 0)
));

onMounted(() => {
  loadDeviceData();
  loadMetrics();
  statusTimer = setInterval(() => {
    now.value = Date.now();
  }, 1000);
  metricsTimer = setInterval(() => {
    loadMetrics();
  }, METRICS_REFRESH_MS);
});

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer);
  if (metricsTimer) clearInterval(metricsTimer);
  clearCommandConfirmation();
});
</script>

<template>
  <div class="dashboard-container">
    <header class="header">
      <div>
        <h1>Smart Fan IoT Dashboard</h1>
        <p class="subtitle">Controle Térmico Noturno & Eficiência Energética</p>
      </div>
      <div class="status-badge" :class="{ online: isConnected && hasTelemetry }">
        <template v-if="!isConnected">○ WebSocket reconectando...</template>
        <template v-else-if="hasTelemetry">● ESP32/Wokwi online</template>
        <template v-else>○ ESP32 aguardando Wokwi visível</template>
      </div>
    </header>

    <div class="grid-layout">
      <div class="card control-card">
        <h2>Controle do Aparelho</h2>
        <div class="switch-section">
          <button
            class="power-btn"
            :class="{ active: telemetry.is_on }"
            :disabled="isCommandPending || !isConnected || !hasTelemetry"
            :title="!isConnected
              ? 'Aguarde a conexão WebSocket'
              : (!hasTelemetry ? 'Abra a aba Wokwi e deixe-a visível' : '')"
            @click="togglePower"
          >
            {{ isCommandPending
              ? 'AGUARDANDO ESP32...'
              : (!hasTelemetry ? 'ESP32 OFFLINE' : (telemetry.is_on ? 'LIGADO' : 'DESLIGADO')) }}
          </button>
          <span class="device-status">
            <template v-if="hasTelemetry">
              Estado atual: <strong>{{ telemetry.is_on ? 'Em funcionamento' : 'Em repouso' }}</strong>
            </template>
            <template v-else>Estado atual: <strong>sem telemetria recente</strong></template>
          </span>
          <small v-if="isConnected && !hasTelemetry" class="device-hint">
            Mantenha a aba Wokwi visível no VS Code; a extensão pausa a simulação quando ela fica oculta.
          </small>
        </div>

        <hr class="divider" />

        <h3>Desligamento Automático (Madrugada)</h3>
        <div class="form-group">
          <label>
            <input type="checkbox" v-model="device.auto_off_enabled" />
            Ativar Timer Noturno
          </label>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Horário de Desligar:</label>
            <input type="time" v-model="device.auto_off_time" :disabled="!device.auto_off_enabled" />
          </div>
          <div class="form-group">
            <label>Tarifa (R$/kWh):</label>
            <input type="number" step="0.01" v-model="device.kwh_rate" />
          </div>
        </div>
        <button class="save-btn" @click="saveSchedule">Salvar Agendamento</button>
        <p
          v-if="feedback"
          class="feedback"
          :class="`feedback-${feedback.type}`"
          role="status"
        >
          {{ feedback.text }}
        </p>
      </div>

      <div class="card metrics-card">
        <h2>Telemetria em Tempo Real</h2>
        <div class="period-panel">
          <div class="period-heading">
            <h3>Período de análise</h3>
            <span v-if="isLivePeriod" class="period-live">Últimas 8h</span>
          </div>
          <div class="period-fields">
            <label>
              Início
              <input v-model="periodStart" type="datetime-local" @input="isLivePeriod = false" />
            </label>
            <label>
              Fim
              <input v-model="periodEnd" type="datetime-local" @input="isLivePeriod = false" />
            </label>
          </div>
          <div class="period-actions">
            <button class="period-btn primary" @click="applyPeriod">Aplicar período</button>
            <button class="period-btn" @click="selectLast8Hours">Últimas 8h</button>
          </div>
          <p class="period-note">
            Intervalo analisado: {{ metrics.duration_hours?.toFixed(1) || '0' }} h ·
            {{ metrics.history_count }} amostras
          </p>
        </div>
        <div class="metrics-grid">
          <div class="metric-item">
            <span class="metric-label">Corrente Eficaz</span>
            <span class="metric-value">{{ telemetry.current_a.toFixed(3) }} <small>A</small></span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Potência Ativa</span>
            <span class="metric-value">{{ telemetry.power_w.toFixed(1) }} <small>W</small></span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Consumo no Período</span>
            <span class="metric-value">{{ formatKwh(metrics.estimated_kwh) }} <small>kWh</small></span>
          </div>
          <div class="metric-item highlight">
            <span class="metric-label">Custo Estimado do Período</span>
            <span class="metric-value">R$ {{ estimatedCost }}</span>
          </div>
        </div>

        <div class="chart-wrapper">
          <RealtimeChart
            :currentPower="telemetry.power_w"
            :timestamp="telemetry.timestamp"
            :history="metrics.history"
            :append-live="isLivePeriod"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  color: #1e293b;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}
.subtitle { color: #64748b; margin-top: 0.25rem; }
.status-badge {
  padding: 0.5rem 1rem;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 600;
  background: #fee2e2;
  color: #dc2626;
}
.status-badge.online {
  background: #dcfce7;
  color: #16a34a;
}
.grid-layout {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 1.5rem;
}
.card {
  background: #ffffff;
  padding: 1.5rem;
  border-radius: 12px;
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
  border: 1px solid #e2e8f0;
}
.power-btn {
  width: 100%;
  padding: 1.2rem;
  font-size: 1.25rem;
  font-weight: bold;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  background-color: #ef4444;
  color: white;
  transition: 0.2s ease;
}
.power-btn.active {
  background-color: #22c55e;
}
.power-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
.device-hint {
  max-width: 34rem;
  color: #b45309;
  text-align: center;
  line-height: 1.35;
}
.feedback {
  margin: 0.75rem 0 0;
  font-size: 0.85rem;
}
.feedback-info {
  color: #1d4ed8;
}
.feedback-success {
  color: #15803d;
}
.feedback-error {
  color: #b91c1c;
}
.switch-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  margin-top: 1rem;
}
.divider { margin: 1.5rem 0; border: 0; border-top: 1px solid #e2e8f0; }
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-weight: 600; font-size: 0.9rem; margin-bottom: 0.25rem; }
.form-group input[type="time"], .form-group input[type="number"] {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.save-btn {
  width: 100%;
  padding: 0.75rem;
  background-color: #2563eb;
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}
.period-panel {
  margin-bottom: 1.25rem;
  padding: 1rem;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}
.period-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.period-heading h3 {
  margin: 0;
  color: #1e3a8a;
  font-size: 1rem;
}
.period-live {
  color: #1d4ed8;
  font-size: 0.8rem;
  font-weight: 700;
}
.period-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
.period-fields label {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  color: #475569;
  font-size: 0.8rem;
  font-weight: 600;
}
.period-fields input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.5rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
}
.period-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.period-btn {
  padding: 0.55rem 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  cursor: pointer;
  font-weight: 600;
}
.period-btn.primary {
  border-color: #2563eb;
  background: #2563eb;
  color: #fff;
}
.period-note {
  margin-top: 0.65rem;
  color: #64748b;
  font-size: 0.78rem;
}
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.metric-item {
  background: #f8fafc;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
  display: flex;
  flex-direction: column;
}
.metric-item.highlight {
  background: #eff6ff;
  border-color: #bfdbfe;
}
.metric-label { font-size: 0.8rem; color: #64748b; font-weight: 600; }
.metric-value { font-size: 1.4rem; font-weight: bold; color: #0f172a; }
.chart-wrapper { margin-top: 1rem; }
@media (max-width: 900px) {
  .grid-layout { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  .header { align-items: flex-start; flex-direction: column; gap: 1rem; }
  .period-fields { grid-template-columns: 1fr; }
  .period-actions { flex-wrap: wrap; }
}
</style>
