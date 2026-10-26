<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import axios from 'axios';
import { api, DEVICE_ID, getDevice, getMetrics, listDevices } from './lib/api';
import {
  Activity,
  Gauge,
  Menu,
  MoonStar,
  PanelLeftClose,
  PanelLeftOpen,
  ReceiptText,
  X,
  Zap,
  Clock3,
  Wallet,
} from 'lucide-vue-next';
import { useWebSocket } from './composables/useWebSocket';
import Brand from './components/dashboard/Brand.vue';
import StatusCard from './components/dashboard/StatusCard.vue';
import ScheduleCard from './components/dashboard/ScheduleCard.vue';
import TariffCard from './components/dashboard/TariffCard.vue';
import MetricCard from './components/dashboard/MetricCard.vue';
import PeriodSelector from './components/dashboard/PeriodSelector.vue';
import PowerChart from './components/dashboard/PowerChart.vue';
import ThemeToggle from './components/dashboard/ThemeToggle.vue';
import type { Device, MetricsSummary } from './types';
import {
  COMMAND_TIMEOUT_MS,
  METRICS_REFRESH_MS,
  PERIODS,
  STATUS_TICK_MS,
  formatLastSeen,
  isDeviceOnline,
  isMultiDay,
  periodLabel as periodLabelOf,
  type PeriodKey,
} from './lib/freshness';
import {
  formatCurrency as formatCurrencyValue,
  formatKwh as formatKwhValue,
  projectMonthlyCost,
} from './lib/format';

const WS_URL =
  (import.meta.env.VITE_WS_URL as string) || 'ws://localhost:8000/ws';

/**
 * Tempos de frescor, período e formatação vivem em `lib/`, onde são cobertos
 * por testes unitários. Aqui só os consumimos.
 */

const { telemetry, isConnected, lastMessageAt } = useWebSocket(
  WS_URL,
  DEVICE_ID,
);
const now = ref(Date.now());
const periodKey = ref<PeriodKey>('8h');
const showCustom = ref(false);
const customStart = ref('');
const customEnd = ref('');
const railOpen = ref(true);
const mobileOpen = ref(false);
const isScheduleSaving = ref(false);
const isTariffSaving = ref(false);
const isScheduleSaved = ref(false);
const isTariffSaved = ref(false);

let statusTimer: ReturnType<typeof setInterval> | null = null;
let metricsTimer: ReturnType<typeof setInterval> | null = null;
let commandTimeout: ReturnType<typeof setTimeout> | null = null;
let scheduleSavedTimer: ReturnType<typeof setTimeout> | null = null;
let tariffSavedTimer: ReturnType<typeof setTimeout> | null = null;
const isCommandPending = ref(false);
const metricsLoading = ref(false);
const metricsStale = ref(false);
let metricsRequest = 0;
let pendingCommand: { action: 'ON' | 'OFF'; expectedState: boolean } | null =
  null;
const feedback = ref<{
  type: 'success' | 'error' | 'info';
  text: string;
} | null>(null);

const devices = ref<Device[]>([]);
const selectDevice = (event: Event) => {
  const value = (event.target as HTMLSelectElement).value;
  if (value !== DEVICE_ID)
    window.location.search = new URLSearchParams({ device: value }).toString();
};

const device = ref<Device>({
  id: 1,
  device_id: DEVICE_ID,
  name: 'Ventilador Quarto',
  is_on: false,
  kwh_rate: 0.85,
  auto_off_time: '03:00',
  auto_off_enabled: true,
});

const metrics = ref<MetricsSummary>({
  device_id: DEVICE_ID,
  duration_hours: 8,
  avg_power_w: 0,
  energy_wh: 0,
  estimated_kwh: 0,
  history_count: 0,
  history: [],
});

/** Fonte única de verdade sobre o estado de conexão, com regra testada. */
const deviceOnline = computed(() =>
  isDeviceOnline(isConnected.value, lastMessageAt.value, now.value),
);
const selectedHours = computed(() =>
  periodKey.value === 'custom' ? undefined : PERIODS[periodKey.value],
);
const multiDay = computed(() => isMultiDay(periodKey.value));
const lastSeen = computed(() => formatLastSeen(lastMessageAt.value, now.value));
const estimatedCost = computed(
  () => metrics.value.estimated_kwh * Number(device.value.kwh_rate || 0),
);
const periodLabel = computed(() => periodLabelOf(periodKey.value));
const monthlyForecast = computed(() =>
  projectMonthlyCost(
    metrics.value.estimated_kwh,
    Number(device.value.kwh_rate || 0),
    metrics.value.duration_hours ?? selectedHours.value ?? 8,
  ),
);
const formatKwh = (value: number) => formatKwhValue(value);
const formatCurrency = (value: number) => formatCurrencyValue(value);

const clearCommandConfirmation = () => {
  pendingCommand = null;
  if (commandTimeout) {
    clearTimeout(commandTimeout);
    commandTimeout = null;
  }
  isCommandPending.value = false;
};

const setSavedFlag = (type: 'schedule' | 'tariff') => {
  if (type === 'schedule') {
    isScheduleSaved.value = true;
    if (scheduleSavedTimer) clearTimeout(scheduleSavedTimer);
    scheduleSavedTimer = setTimeout(() => {
      isScheduleSaved.value = false;
    }, 2600);
  } else {
    isTariffSaved.value = true;
    if (tariffSavedTimer) clearTimeout(tariffSavedTimer);
    tariffSavedTimer = setTimeout(() => {
      isTariffSaved.value = false;
    }, 2600);
  }
};

const getErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === 'string' ? detail : error.message;
  }
  return fallback;
};

const loadDeviceData = async () => {
  try {
    const data = await getDevice();
    if (data.device_id === DEVICE_ID) device.value = data;
  } catch (error) {
    feedback.value = {
      type: 'error',
      text: getErrorMessage(error, 'Não foi possível carregar o dispositivo.'),
    };
  }
};

const getCustomPeriod = () => {
  const start = new Date(customStart.value);
  const end = new Date(customEnd.value);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    feedback.value = {
      type: 'error',
      text: 'Informe um início e um fim válidos.',
    };
    return null;
  }
  if (start >= end) {
    feedback.value = {
      type: 'error',
      text: 'O início deve ser anterior ao fim.',
    };
    return null;
  }
  return { start, end };
};

const loadMetrics = async () => {
  const custom = periodKey.value === 'custom' ? getCustomPeriod() : null;
  if (periodKey.value === 'custom' && !custom) return false;

  // No período personalizado, o fim é o que o usuário escolheu — usar "agora"
  // descartaria o campo de data final e mostraria uma janela que ninguém
  // pediu. Nos atalhos, o fim é sempre agora.
  const end = custom ? custom.end : new Date();
  const start = custom
    ? custom.start
    : new Date(end.getTime() - (selectedHours.value ?? 8) * 60 * 60 * 1000);

  const request = ++metricsRequest;
  metricsLoading.value = true;
  try {
    const data = await getMetrics(start, end);
    if (request !== metricsRequest) return false;
    metrics.value = data;
    metricsStale.value = false;
    return true;
  } catch (error) {
    if (request !== metricsRequest) return false;
    metricsStale.value = true;
    feedback.value = {
      type: 'error',
      text: getErrorMessage(
        error,
        'Não foi possível carregar o consumo do InfluxDB.',
      ),
    };
    return false;
  } finally {
    if (request === metricsRequest) metricsLoading.value = false;
  }
};

const selectPeriod = async (next: PeriodKey) => {
  periodKey.value = next;
  if (next === 'custom') {
    const end = new Date();
    const start = new Date(end.getTime() - 8 * 60 * 60 * 1000);
    const toInput = (date: Date) => {
      const pad = (n: number) => String(n).padStart(2, '0');
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    };
    customStart.value = toInput(start);
    customEnd.value = toInput(end);
    showCustom.value = true;
  } else {
    showCustom.value = false;
    await loadMetrics();
  }
};

const applyCustomPeriod = async () => {
  if (await loadMetrics()) {
    showCustom.value = false;
    feedback.value = {
      type: 'success',
      text: 'Período aplicado. Consumo e custo recalculados.',
    };
  }
};

const togglePower = async () => {
  if (isCommandPending.value) return;
  if (!deviceOnline.value) {
    feedback.value = {
      type: 'error',
      text: 'ESP32 sem telemetria recente. Abra a aba Wokwi e deixe-a visível.',
    };
    return;
  }

  const action = telemetry.value.is_on ? 'OFF' : 'ON';
  isCommandPending.value = true;
  pendingCommand = { action, expectedState: action === 'ON' };
  feedback.value = {
    type: 'info',
    text: `Comando ${action} enviado. Aguardando confirmação do ESP32...`,
  };
  commandTimeout = setTimeout(() => {
    if (!pendingCommand || pendingCommand.action !== action) return;
    clearCommandConfirmation();
    feedback.value = {
      type: 'error',
      text: `O ESP32 não confirmou ${action}. A simulação Wokwi pode estar pausada.`,
    };
  }, COMMAND_TIMEOUT_MS);

  try {
    await api.post(`/device/${DEVICE_ID}/command`, { action });
  } catch (error) {
    clearCommandConfirmation();
    feedback.value = {
      type: 'error',
      text: getErrorMessage(error, 'Falha ao enviar o comando.'),
    };
  }
};

const saveAutoShutdown = async () => {
  isScheduleSaving.value = true;
  try {
    await api.put(`/device/${DEVICE_ID}/auto-shutdown`, {
      auto_off_time: device.value.auto_off_time,
      auto_off_enabled: device.value.auto_off_enabled,
    });
    setSavedFlag('schedule');
    feedback.value = {
      type: 'success',
      text: 'Desligamento automático salvo e publicado no ESP32.',
    };
  } catch (error) {
    feedback.value = {
      type: 'error',
      text: getErrorMessage(
        error,
        'Falha ao salvar o desligamento automático.',
      ),
    };
  } finally {
    isScheduleSaving.value = false;
  }
};

const saveTariff = async () => {
  isTariffSaving.value = true;
  try {
    await api.put(`/device/${DEVICE_ID}/tariff`, {
      kwh_rate: Number(device.value.kwh_rate),
    });
    setSavedFlag('tariff');
    feedback.value = {
      type: 'success',
      text: 'Tarifa atualizada. O custo estimado foi recalculado.',
    };
  } catch (error) {
    feedback.value = {
      type: 'error',
      text: getErrorMessage(error, 'Falha ao salvar a tarifa.'),
    };
  } finally {
    isTariffSaving.value = false;
  }
};

watch(
  () => telemetry.value.is_on,
  (isOn) => {
    if (!pendingCommand || isOn !== pendingCommand.expectedState) return;
    const action = pendingCommand.action;
    clearCommandConfirmation();
    feedback.value = {
      type: 'success',
      text: `Comando ${action} confirmado pelo ESP32.`,
    };
  },
);

onMounted(() => {
  listDevices()
    .then((data) => {
      devices.value = data;
    })
    .catch(() => {
      feedback.value = {
        type: 'error',
        text: 'Não foi possível listar os dispositivos.',
      };
    });
  loadDeviceData();
  loadMetrics();
  statusTimer = setInterval(() => {
    now.value = Date.now();
  }, STATUS_TICK_MS);
  metricsTimer = setInterval(loadMetrics, METRICS_REFRESH_MS);
});

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer);
  if (metricsTimer) clearInterval(metricsTimer);
  if (scheduleSavedTimer) clearTimeout(scheduleSavedTimer);
  if (tariffSavedTimer) clearTimeout(tariffSavedTimer);
  metricsRequest++;
  clearCommandConfirmation();
});
</script>

<template>
  <div class="ventora-app">
    <div class="app-shell">
      <aside class="control-rail" :class="{ collapsed: !railOpen }">
        <template v-if="railOpen">
          <div class="rail-content">
            <Brand />
            <div class="rail-toolbar">
              <span>Central de controle</span>
              <div class="toolbar-actions">
                <ThemeToggle />
                <button
                  class="rail-icon"
                  type="button"
                  aria-label="Recolher menu"
                  @click="railOpen = false"
                >
                  <PanelLeftClose :size="16" />
                </button>
              </div>
            </div>
            <StatusCard
              :device="device.name"
              :online="deviceOnline"
              :last-seen="lastSeen"
              :is-on="telemetry.is_on"
              :pending="isCommandPending"
              @toggle="togglePower"
            />
            <ScheduleCard
              :enabled="device.auto_off_enabled"
              :time="device.auto_off_time"
              :saving="isScheduleSaving"
              :saved="isScheduleSaved"
              @update:enabled="device.auto_off_enabled = $event"
              @update:time="device.auto_off_time = $event"
              @save="saveAutoShutdown"
            />
            <TariffCard
              :tariff="Number(device.kwh_rate)"
              :saving="isTariffSaving"
              :saved="isTariffSaved"
              @update:tariff="device.kwh_rate = Number($event)"
              @save="saveTariff"
            />
            <p
              v-if="feedback"
              class="feedback"
              :class="`feedback-${feedback.type}`"
              role="status"
            >
              {{ feedback.text }}
            </p>
          </div>
        </template>
        <template v-else>
          <div class="collapsed-rail">
            <div class="brand-mark" aria-hidden="true">V</div>
            <button
              class="rail-icon"
              type="button"
              aria-label="Expandir menu"
              title="Expandir menu"
              @click="railOpen = true"
            >
              <PanelLeftOpen :size="17" />
            </button>
            <div class="rail-separator" />
            <button
              class="rail-icon"
              type="button"
              title="Status do dispositivo"
              @click="railOpen = true"
            >
              <Gauge :size="17" />
            </button>
            <button
              class="rail-icon"
              type="button"
              title="Desligamento automático"
              @click="railOpen = true"
            >
              <MoonStar :size="17" />
            </button>
            <button
              class="rail-icon"
              type="button"
              title="Tarifa de energia"
              @click="railOpen = true"
            >
              <ReceiptText :size="17" />
            </button>
            <div class="collapsed-theme"><ThemeToggle /></div>
          </div>
        </template>
      </aside>

      <main class="main-content">
        <header class="mobile-header">
          <Brand compact />
          <div class="header-actions">
            <ThemeToggle />
            <button
              class="rail-icon"
              type="button"
              aria-label="Abrir controles"
              @click="mobileOpen = true"
            >
              <Menu :size="18" />
            </button>
          </div>
        </header>

        <div
          v-if="mobileOpen"
          class="mobile-backdrop"
          @click.self="mobileOpen = false"
        >
          <aside class="mobile-drawer" @click.stop>
            <div class="drawer-header">
              <Brand />
              <div class="drawer-actions">
                <ThemeToggle />
                <button
                  class="rail-icon"
                  type="button"
                  aria-label="Fechar controles"
                  @click="mobileOpen = false"
                >
                  <X :size="18" />
                </button>
              </div>
            </div>
            <StatusCard
              :device="device.name"
              :online="deviceOnline"
              :last-seen="lastSeen"
              :is-on="telemetry.is_on"
              :pending="isCommandPending"
              @toggle="togglePower"
            />
            <ScheduleCard
              :enabled="device.auto_off_enabled"
              :time="device.auto_off_time"
              :saving="isScheduleSaving"
              :saved="isScheduleSaved"
              @update:enabled="device.auto_off_enabled = $event"
              @update:time="device.auto_off_time = $event"
              @save="saveAutoShutdown"
            />
            <TariffCard
              :tariff="Number(device.kwh_rate)"
              :saving="isTariffSaving"
              :saved="isTariffSaved"
              @update:tariff="device.kwh_rate = Number($event)"
              @save="saveTariff"
            />
            <p
              v-if="feedback"
              class="feedback"
              :class="`feedback-${feedback.type}`"
              role="status"
            >
              {{ feedback.text }}
            </p>
          </aside>
        </div>

        <header class="page-header">
          <div>
            <h2>Telemetria em tempo real</h2>
            <p>Consumo e eficiência do ventilador · {{ periodLabel }}</p>
          </div>
          <div class="period-area">
            <PeriodSelector
              :model-value="periodKey"
              :start="customStart"
              :end="customEnd"
              :show-custom="showCustom"
              @update:model-value="selectPeriod($event as PeriodKey)"
              @update:start="customStart = $event"
              @update:end="customEnd = $event"
              @update:show-custom="showCustom = $event"
              @apply="applyCustomPeriod"
            />
          </div>
        </header>

        <label
          >Dispositivo
          <select
            :value="DEVICE_ID"
            aria-label="Dispositivo"
            @change="selectDevice"
          >
            <option
              v-for="item in devices"
              :key="item.device_id"
              :value="item.device_id"
            >
              {{ item.name }} ({{ item.device_id }})
            </option>
          </select>
        </label>
        <section class="metrics-grid">
          <MetricCard
            label="Corrente eficaz"
            :value="telemetry.current_a.toFixed(3)"
            unit="A"
          >
            <template #icon><Activity :size="15" /></template>
            <template #footer>Última leitura via WebSocket</template>
          </MetricCard>
          <MetricCard
            label="Potência ativa"
            :value="telemetry.power_w.toFixed(1)"
            unit="W"
            highlight
          >
            <template #icon><Zap :size="15" /></template>
            <template #footer
              ><div class="power-bar">
                <span
                  :style="{
                    width: `${Math.min(100, Math.max(4, (telemetry.power_w / 40) * 100))}%`,
                  }"
                /></div
            ></template>
          </MetricCard>
          <MetricCard
            label="Consumo no período"
            :value="formatKwh(metrics.estimated_kwh)"
            unit="kWh"
          >
            <template #icon><Clock3 :size="15" /></template>
            <template #footer
              >{{ metrics.history_count }} amostras coletadas</template
            >
          </MetricCard>
          <MetricCard
            label="Custo estimado"
            :value="formatCurrency(estimatedCost)"
          >
            <template #icon><Wallet :size="15" /></template>
            <template #footer
              ><span class="forecast"
                >Previsão: {{ formatCurrency(monthlyForecast) }} / mês</span
              ></template
            >
          </MetricCard>
        </section>

        <p v-if="telemetry.persisted === false" role="alert">
          A última leitura chegou, mas a gravação no histórico não foi
          confirmada.
        </p>
        <p v-if="metricsLoading" role="status">Atualizando histórico…</p>
        <p v-if="metricsStale" role="alert">
          Histórico desatualizado: falha na última consulta.
        </p>
        <p v-if="(metrics.coverage ?? 0) < 0.98" role="status">
          Consumo parcial: há períodos sem coleta. A previsão mensal pode
          subestimar o consumo.
        </p>
        <PowerChart
          :coverage="metrics.coverage"
          :source-segments="metrics.segments"
          :raw-mean="metrics.avg_power_w"
          :raw-maximum="metrics.max_power_w"
          :raw-count="metrics.history_count"
          :current-power="telemetry.power_w"
          :timestamp="telemetry.timestamp"
          :history="metrics.history"
          :append-live="false"
          :multi-day="multiDay"
          :period-label="periodLabel"
          :period-start="metrics.period_start"
          :period-end="metrics.period_end"
        />
      </main>
    </div>
  </div>
</template>

<style scoped>
.ventora-app {
  min-height: 100vh;
  background: var(--background);
  color: var(--foreground);
}
/* O shell ocupa 100% da largura para o rail encostar na borda esquerda.
 * A largura máxima fica no conteúdo principal, não no shell. */
.app-shell {
  display: flex;
  min-height: 100vh;
}
.control-rail {
  position: sticky;
  top: 0;
  z-index: 20;
  width: 21rem;
  height: 100vh;
  flex: 0 0 auto;
  border-right: 1px solid var(--border);
  background: var(--sidebar);
  transition: width 300ms ease;
}
.control-rail.collapsed {
  width: 5rem;
}
.rail-content {
  display: grid;
  gap: 1rem;
  align-content: start;
  height: 100%;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 1.5rem 1.25rem;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.rail-content::-webkit-scrollbar {
  width: 6px;
}
.rail-content::-webkit-scrollbar-track {
  background: transparent;
}
.rail-content::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--border);
}
.rail-content::-webkit-scrollbar-thumb:hover {
  background: var(--muted-foreground);
}
.brand-mark {
  display: grid;
  width: 2.75rem;
  height: 2.75rem;
  place-items: center;
  border-radius: 0.6rem;
  background: var(--primary);
  color: var(--primary-foreground);
  font-family: var(--font-display);
  font-size: 1.25rem;
  font-weight: 700;
}
.rail-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.85rem 0;
  border-block: 1px solid var(--border);
  color: var(--muted-foreground);
  font-size: 0.6rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.rail-icon {
  display: inline-grid;
  width: 2.25rem;
  height: 2.25rem;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--muted-foreground);
  cursor: pointer;
  transition:
    color 160ms ease,
    background-color 160ms ease;
}
.rail-icon:hover {
  color: var(--foreground);
  background: var(--muted);
}
.collapsed-rail {
  display: flex;
  height: 100%;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem 0.5rem;
}
.rail-separator {
  width: 2rem;
  height: 1px;
  margin: 0.5rem 0;
  background: var(--border);
}
.collapsed-theme {
  margin-top: auto;
}
.main-content {
  display: grid;
  gap: 1.5rem;
  min-width: 0;
  flex: 1;
  align-content: start;
  padding: 1rem;
}
@media (min-width: 640px) {
  .main-content {
    padding: 1.5rem;
  }
}
@media (min-width: 1024px) {
  .main-content {
    padding: 2.5rem;
  }
}
.mobile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.page-header {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
}
.page-header > div {
  min-width: 0;
}
.page-header h2 {
  margin: 0;
  color: var(--foreground);
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.03em;
}
@media (min-width: 1024px) {
  .page-header h2 {
    font-size: 1.875rem;
  }
}
.page-header p {
  margin: 0.25rem 0 0;
  color: var(--muted-foreground);
  font-size: 0.85rem;
}
.period-area {
  flex: 0 0 auto;
}
.feedback {
  margin: 0;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: var(--card);
  box-shadow: var(--shadow-card);
  color: var(--muted-foreground);
  font-size: 0.75rem;
  line-height: 1.45;
}
.feedback-info {
  color: var(--primary);
}
.feedback-success {
  color: var(--online);
}
.feedback-error {
  color: #d45c5c;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}
@media (min-width: 640px) {
  .metrics-grid {
    gap: 1rem;
  }
}
@media (min-width: 1280px) {
  .metrics-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
.power-bar {
  height: 0.3rem;
  overflow: hidden;
  border-radius: 999px;
  background: var(--muted);
}
.power-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--primary);
  transition: width 200ms ease;
}
.forecast {
  color: var(--primary);
  font-weight: 700;
}
.mobile-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: color-mix(in srgb, var(--foreground) 30%, transparent);
  backdrop-filter: blur(4px);
}
.mobile-drawer {
  display: grid;
  gap: 1rem;
  align-content: start;
  width: min(88vw, 340px);
  height: 100%;
  overflow-y: auto;
  overscroll-behavior: contain;
  border-right: 1px solid var(--border);
  padding: 1.25rem;
  background: var(--sidebar);
  box-shadow: 1.25rem 0 3rem rgb(0 0 0 / 22%);
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.mobile-drawer::-webkit-scrollbar {
  width: 6px;
}
.mobile-drawer::-webkit-scrollbar-track {
  background: transparent;
}
.mobile-drawer::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--border);
}
.drawer-header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 0.75rem;
}
.drawer-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
@media (min-width: 1024px) {
  .control-rail {
    display: flex;
  }
  .mobile-header {
    display: none;
  }
}
@media (max-width: 1023px) {
  .control-rail {
    display: none;
  }
}
@media (max-width: 600px) {
  .main-content {
    padding: 0.9rem;
  }
  .metrics-grid {
    gap: 0.6rem;
  }
}
</style>
