<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { Card, Badge } from '../ui/primitives';
import '../ui/task-page.css';
import '../ui/final-pages.css';
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
import { numberText, presentation, pointsFromFrames } from '../insights';
import InsightTrend from '../components/InsightTrend.vue';
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
  <div class="task-page scene-page">
    <header class="tp-heading">
      <h1>Cena 3D</h1>
      <Badge
        :tone="fresh ? 'good' : 'warning'"
        role="status"
        data-testid="scene-status"
        >{{ fresh ? 'Dados recentes' : 'Sem dados — cena congelada' }}</Badge
      >
    </header>
    <div class="scene-device">
      <label for="scene-device">Equipamento na cena</label
      ><select id="scene-device" v-model="identity">
        <option v-for="item in devices" :key="item.id" :value="item.id">
          {{ item.name }} · {{ item.zone }}
        </option>
      </select>
    </div>
    <p v-if="!device" role="status">
      {{
        streamStatus === 'connected'
          ? 'Nenhum dispositivo autorizado.'
          : 'Conectando aos dispositivos…'
      }}
    </p>
    <p v-if="streamNotice" role="status">{{ streamNotice }}</p>
    <p v-if="metadataError" role="alert" class="tp-field-error">
      {{ metadataError
      }}<button class="button secondary" @click="profile">
        Tentar consultar faixas novamente
      </button>
    </p>
    <p v-if="loading" role="status">Consultando faixas cadastradas…</p>
    <template v-if="device">
      <Card
        class="scene-card"
        :data-fan-angle="stats?.fanAngle.toFixed(6)"
        :data-scene-frozen="!fresh"
        :data-equipment-color="stats?.equipmentColor"
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
          :alert="live.alerts.get(device.id)"
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
          ><span v-if="frame"
            >Última leitura às
            {{ new Date(frame.timestamp).toLocaleTimeString('pt-BR') }}</span
          >
        </div>
      </Card>
      <div class="scene-legend" aria-label="Legenda da cena">
        <span>Verde · normal</span><span>Âmbar · atenção</span
        ><span>Vermelho · crítico</span><span>Cinza · indisponível</span
        ><span>Azul · atuador ligado</span>
      </div>
      <details class="scene-help">
        <summary>Navegação e cores da cena</summary>
        <p>
          Arraste para girar e use a roda para aproximar. A lista abaixo permite
          selecionar pelo teclado ou toque. Cores dos sensores seguem a faixa
          cadastrada; alertas da IA se aplicam ao equipamento. Ambiente interno
          e externo: azul a laranja entre 18 e 42 °C. A preferência de movimento
          reduzido do sistema é respeitada.
        </p>
        <p>
          Movimento ilustrativo condicionado à telemetria; não representa RPM
          medido. Sem amostra recente, geometria e movimento ficam congelados.
        </p>
      </details>
      <div class="scene-detail-grid">
        <Card class="tp-card component-list"
          ><h2>Componentes cadastrados</h2>
          <ul>
            <li v-for="item in items" :key="item.id">
              <button
                class="component-button"
                :aria-pressed="selected === item.id"
                :aria-label="`Selecionar ${item.label}`"
                @click="selected = item.id"
              >
                <span>{{ item.label }}</span
                ><strong>{{ value(item.id) }}</strong>
              </button>
            </li>
          </ul></Card
        >
        <Card class="tp-card component-detail"
          ><h2>{{ entity?.label ?? 'Selecione um componente' }}</h2>
          <strong v-if="entity?.kind !== 'equipment'" class="detail-value">{{
            value(selected)
          }}</strong>
          <template v-if="entity?.kind === 'sensor'"
            ><SensorTrend
              :frames="history"
              :field="entity.field as SensorField"
          /></template>
          <template v-if="entity?.kind === 'equipment'"
            ><p>{{ forecast.label }}</p>
            <dl class="scene-prediction">
              <div>
                <dt>Saúde</dt>
                <dd>
                  {{
                    forecast.health == null
                      ? 'Indisponível'
                      : `${numberText(forecast.health)} %`
                  }}
                </dd>
              </div>
              <div>
                <dt>RUL</dt>
                <dd>
                  {{
                    forecast.rul == null
                      ? 'Indisponível'
                      : `${numberText(forecast.rul)} h de calendário`
                  }}
                </dd>
              </div>
            </dl>
            <InsightTrend
              :points="pointsFromFrames(history)"
              target="health_score"
              pilot
          /></template>
          <template v-if="entity?.kind === 'actuator'"
            ><SensorTrend
              :frames="history"
              :field="
                entity.field === 'compressor_on'
                  ? 'compressor_on'
                  : 'condenser_fan_on'
              " />
            <p>
              {{
                entity.field === 'compressor_on'
                  ? 'Compressor sob termostato e proteções.'
                  : 'Ventilador com controle manual disponível conforme seu papel.'
              }}
            </p>
            <ControlPanel
              :key="entity.id"
              :device-id="device.id"
              :enabled="device.enabled"
              :target="entity.field === 'compressor_on' ? 'compressor' : 'fan'"
          /></template>
          <details v-if="entity">
            <summary>Detalhes do item</summary>
            <dl class="tp-definition">
              <dt>Identificador</dt>
              <dd>{{ entity.id }}</dd>
              <dt>Equipamento</dt>
              <dd>{{ device.id }}</dd>
            </dl>
            <p v-if="entity.kind === 'sensor' && ranges">
              {{ sensorLabels[entity.field as SensorField] }} · faixa
              {{ ranges[entity.field as SensorField].minimum }}–{{
                ranges[entity.field as SensorField].maximum
              }}
              {{ units[entity.field as SensorField] }}
            </p>
            <p v-if="entity.kind === 'equipment'">
              Versão na amostra: {{ forecast.version ?? 'Sem modelo' }}. Saúde e
              RUL pertencem a este equipamento, não aos sensores individuais.
            </p>
            <p v-if="frame">
              Amostra: {{ new Date(frame.timestamp).toLocaleString('pt-BR') }}
            </p>
          </details>
        </Card>
      </div>
      <Card class="tp-card"
        ><details class="scene-controls">
          <summary>Controles do equipamento</summary>
          <ControlPanel
            :device-id="device.id"
            :enabled="device.enabled"
          /></details
      ></Card>
      <details v-if="stats" class="scene-performance">
        <summary>Renderização e desempenho</summary>
        <p>
          {{ stats.fps.toFixed(1) }} FPS · {{ stats.calls }} chamadas ·
          {{ stats.triangles }} triângulos · {{ stats.geometries }} geometrias.
          Limites existentes: 30 FPS, 100 chamadas e 50 mil triângulos. Não mede
          latência da telemetria.
        </p>
      </details>
    </template>
  </div>
</template>
