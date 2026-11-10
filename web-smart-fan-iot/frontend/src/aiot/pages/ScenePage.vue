<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { api } from '../auth';
import { live, streamNotice, streamStatus } from '../realtime';
import {
  entities,
  sensorLabels,
  units,
  type Ranges,
  type SensorField,
} from '../scene/model';
import type { SceneStats } from '../scene/renderer';
import { numberText, presentation } from '../insights';
import HvacCanvas from '../components/HvacCanvas.vue';
import SensorTrend from '../components/SensorTrend.vue';
import ControlPanel from '../components/ControlPanel.vue';
const identity = ref('');
const selected = ref('');
const now = ref(Date.now());
const ranges = ref<Ranges>();
const metadataError = ref('');
const loading = ref(false);
const stats = ref<SceneStats>();
const devices = computed(() => [...live.devices.values()]);
watch(
  devices,
  (value) => {
    if (!value.some((device) => device.id === identity.value))
      identity.value = value[0]?.id ?? '';
  },
  { immediate: true },
);
const device = computed(() => live.devices.get(identity.value));
const frame = computed(() => live.frames.get(identity.value));
const fresh = computed(() => live.fresh(identity.value, now.value));
const items = computed(() => (device.value ? entities(device.value) : []));
const entity = computed(() =>
  items.value.find((item) => item.id === selected.value),
);
const readings = computed(() => frame.value?.conteudo.telemetry.readings);
const forecast = computed(() =>
  presentation(frame.value, now.value, fresh.value),
);
const history = computed(() =>
  frame.value ? [...(live.history.get(identity.value) ?? [])] : [],
);
let request: AbortController | undefined;
let epoch = 0;
async function profile() {
  const generation = ++epoch;
  request?.abort();
  request = new AbortController();
  ranges.value = undefined;
  metadataError.value = '';
  loading.value = true;
  if (!identity.value) {
    loading.value = false;
    return;
  }
  try {
    const data = await api<{ profile: { healthy_ranges: Ranges } }>(
      `/devices/${encodeURIComponent(identity.value)}`,
      { signal: request.signal },
    );
    if (generation === epoch) ranges.value = data.profile.healthy_ranges;
  } catch (failure) {
    if (generation === epoch && !request.signal.aborted)
      metadataError.value =
        failure instanceof Error
          ? failure.message
          : 'Falha ao consultar faixas cadastradas.';
  } finally {
    if (generation === epoch) loading.value = false;
  }
}
watch(
  identity,
  () => {
    selected.value = identity.value;
    stats.value = undefined;
    void profile();
  },
  { immediate: true },
);
function value(id: string) {
  const item = items.value.find((entry) => entry.id === id);
  if (!fresh.value || !frame.value || !item) return 'Sem dados recentes';
  if (item.kind === 'sensor') {
    const field = item.field as SensorField;
    return `${numberText(readings.value?.[field])} ${units[field]}`;
  }
  if (item.kind === 'actuator')
    return frame.value.conteudo.telemetry.actuators[
      item.field as keyof typeof frame.value.conteudo.telemetry.actuators
    ]
      ? 'Ligado'
      : 'Desligado';
  return forecast.value.health == null
    ? forecast.value.label
    : `Saúde ${numberText(forecast.value.health)}%`;
}
const clock = setInterval(() => {
  now.value = Date.now();
}, 500);
onBeforeUnmount(() => {
  epoch++;
  clearInterval(clock);
  request?.abort();
});
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">EQUIPAMENTO EM PERSPECTIVA</span>
      <h1>Cena 3D</h1>
      <p class="muted">
        Ambiente interno, condensadora e compressor monitorado.
      </p>
    </div>
    <span
      class="status-pill"
      :class="fresh ? 'positive' : 'neutral'"
      role="status"
      data-testid="scene-status"
      >{{ fresh ? 'Dados recentes' : 'Sem dados — cena congelada' }}</span
    >
  </div>
  <label for="scene-device">Equipamento na cena</label
  ><select id="scene-device" v-model="identity">
    <option v-for="item in devices" :key="item.id" :value="item.id">
      {{ item.name }} · {{ item.zone }}
    </option>
  </select>
  <p v-if="!device" class="notice" role="status">
    {{
      streamStatus === 'connected'
        ? 'Nenhum dispositivo autorizado.'
        : 'Conectando aos dispositivos…'
    }}
  </p>
  <p v-if="streamNotice" role="status">{{ streamNotice }}</p>
  <p v-if="metadataError" role="alert">
    {{ metadataError }}
    <button class="button secondary" @click="profile">
      Tentar consultar faixas novamente
    </button>
  </p>
  <p v-if="loading" role="status">Consultando faixas cadastradas…</p>
  <template v-if="device">
    <section
      class="card scene-card"
      :data-fan-angle="stats?.fanAngle.toFixed(6)"
      :data-scene-frozen="!fresh"
      :data-draw-calls="stats?.calls"
      :data-triangles="stats?.triangles"
      :data-geometries="stats?.geometries"
    >
      <HvacCanvas
        :key="device.id"
        :device="device"
        :frame="frame"
        :ranges="ranges"
        :selected="selected"
        @select="selected = $event"
        @stats="stats = $event"
      />
      <div class="scene-caption">
        <span
          >Interior ·
          {{ fresh ? numberText(readings?.indoor_temp_c) : '—' }} °C</span
        ><span
          >Exterior ·
          {{ fresh ? numberText(readings?.outdoor_temp_c) : '—' }} °C</span
        ><span>Azul → laranja: 18–42 °C; cinza: indisponível</span>
      </div>
    </section>
    <p class="muted scene-help">
      Arraste para girar; use a roda para aproximar. Selecione um marcador ou
      use os botões abaixo pelo teclado. Cores: verde na faixa cadastrada, âmbar
      fora da faixa, cinza indisponível; atuadores azuis quando ligados.
      Movimento reduzido respeita a preferência do sistema.
    </p>
    <p v-if="frame" class="muted">
      Fonte {{ new Date(frame.timestamp).toLocaleString('pt-BR') }} ·
      {{ Math.max(0, Math.floor((now - Date.parse(frame.timestamp)) / 1000)) }}
      s atrás · escala 1×. Movimento é ilustrativo, condicionado à telemetria;
      não representa RPM medido.
    </p>
    <div class="scene-detail-grid">
      <section class="card component-list">
        <h2>Componentes cadastrados</h2>
        <ul>
          <li v-for="item in items" :key="item.id">
            <button
              class="component-button"
              :aria-pressed="selected === item.id"
              :aria-label="`Selecionar ${item.label}`"
              @click="selected = item.id"
            >
              <span
                >{{ item.label }}<small>{{ item.id }}</small></span
              ><strong>{{ value(item.id) }}</strong>
            </button>
          </li>
        </ul>
      </section>
      <section class="card component-detail" aria-live="polite">
        <h2>{{ entity?.label ?? 'Selecione um componente' }}</h2>
        <p v-if="entity" class="muted">
          {{ entity.id }} ·
          {{
            entity.kind === 'sensor'
              ? 'Sensor simulado'
              : entity.kind === 'actuator'
                ? 'Atuador observado'
                : 'Equipamento monitorado'
          }}
        </p>
        <strong class="detail-value">{{ value(selected) }}</strong
        ><template v-if="entity?.kind === 'sensor'"
          ><p>
            {{ sensorLabels[entity.field as SensorField] }} · unidade
            {{ units[entity.field as SensorField] }}
          </p>
          <p v-if="ranges">
            Faixa cadastrada:
            {{ ranges[entity.field as SensorField].minimum }}–{{
              ranges[entity.field as SensorField].maximum
            }}
            {{ units[entity.field as SensorField] }}
          </p>
          <SensorTrend :frames="history" :field="entity.field as SensorField"
        /></template>
        <p v-else>
          Saúde: {{ numberText(forecast.health) }}% · RUL:
          {{ numberText(forecast.rul) }} h de calendário.<br />Versão nesta
          amostra: {{ forecast.version ?? 'Sem modelo' }}.
        </p>
        <p class="muted">
          Sem amostra recente, geometria e movimento físico ficam congelados;
          valores atuais são ocultados.
        </p>
      </section>
    </div>
    <details class="card scene-controls">
      <summary>Controles do equipamento</summary>
      <ControlPanel :device-id="device.id" :enabled="device.enabled" />
    </details>
    <p v-if="stats" class="muted scene-performance">
      Renderização local: {{ stats.fps.toFixed(1) }} FPS ·
      {{ stats.calls }} chamadas · {{ stats.triangles }} triângulos ·
      {{ stats.geometries }} geometrias. Limite: 30 FPS / 100 chamadas / 50 mil
      triângulos. Não é uma medição de latência da telemetria.
    </p>
  </template>
</template>
<style scoped>
select {
  max-width: 420px;
  margin-bottom: 1rem;
}
.scene-card {
  overflow: hidden;
}
.scene-caption {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 1rem 1.3rem;
  font-size: 0.8rem;
}
.scene-help,
.scene-performance {
  font-size: 0.8rem;
  line-height: 1.6;
  margin-top: 1rem;
}
.scene-detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin: 1.4rem 0;
}
.component-list,
.component-detail,
.scene-controls {
  padding: 1.3rem;
  min-width: 0;
}
.component-list ul {
  padding: 0;
  list-style: none;
  margin: 0;
}
.component-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  text-align: left;
  gap: 1rem;
  width: 100%;
  border: 1px solid #e0e8e9;
  border-radius: 8px;
  padding: 0.7rem;
  margin: 0.4rem 0;
  background: white;
  color: #173640;
}
.component-button[aria-pressed='true'] {
  background: #e6f2ef;
  border-color: #238574;
}
.component-button small {
  display: block;
  font-size: 0.7rem;
  color: #5e727c;
  overflow-wrap: anywhere;
}
.component-button strong {
  font-size: 0.8rem;
}
.detail-value {
  display: block;
  font-size: 1.8rem;
  margin: 1.2rem 0;
}
.component-detail p {
  overflow-wrap: anywhere;
  font-size: 0.85rem;
  line-height: 1.6;
}
summary {
  cursor: pointer;
  font-weight: 600;
}
@media (max-width: 850px) {
  .scene-detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
