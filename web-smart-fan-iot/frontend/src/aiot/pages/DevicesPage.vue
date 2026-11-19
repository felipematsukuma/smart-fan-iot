<script setup lang="ts">
import {
  computed,
  onMounted,
  onBeforeUnmount,
  nextTick,
  ref,
  toRaw,
} from 'vue';
import { useRoute } from 'vue-router';
import { api, currentUser, ApiError } from '../auth';
import { startRealtime, live } from '../realtime';
import HistoryPanel from '../components/HistoryPanel.vue';
import ControlPanel from '../components/ControlPanel.vue';

import { Card, Badge, Alert } from '../ui/primitives';
import Button from '../ui/Button.vue';
import { overviewFreshness } from '../overview-freshness';
import '../ui/task-page.css';

type Field =
  | 'current_a'
  | 'compressor_case_temp_c'
  | 'vibration_rms_mm_s'
  | 'indoor_temp_c'
  | 'outdoor_temp_c';
interface Profile {
  nominal_voltage_v: number;
  rated_power_w: number;
  expected_life_hours: number;
  healthy_ranges: Record<Field, { minimum: number; maximum: number }>;
}
interface Device {
  id: string;
  name: string;
  zone: string;
  enabled: boolean;
  revision: number;
  sensor_ids: Record<Field, string>;
  actuator_ids: Record<string, string>;
  sensor_units: Record<Field, string>;
  boot_id: string | null;
  last_sample_at: string | null;
  profile: Profile;
}
const labels: Record<Field, string> = {
  current_a: 'Corrente (A)',
  compressor_case_temp_c: 'Temperatura da carcaça (°C)',
  vibration_rms_mm_s: 'Vibração (mm/s)',
  indoor_temp_c: 'Temperatura interna (°C)',
  outdoor_temp_c: 'Temperatura externa (°C)',
};
const defaults = (): Profile => ({
  nominal_voltage_v: 220,
  rated_power_w: 1000,
  expected_life_hours: 30000,
  healthy_ranges: {
    current_a: { minimum: 0, maximum: 12 },
    compressor_case_temp_c: { minimum: 15, maximum: 75 },
    vibration_rms_mm_s: { minimum: 0, maximum: 3 },
    indoor_temp_c: { minimum: 20, maximum: 28 },
    outdoor_temp_c: { minimum: 15, maximum: 40 },
  },
});
const devices = ref<Device[]>([]);
const selected = ref<Device | null>(null);
const route = useRoute();
const editing = ref<Device | null>(null);
const showForm = ref(false);
const id = ref('');
const name = ref('');
const zone = ref('');
const profile = ref(defaults());
const busy = ref(false);
const error = ref('');
const notice = ref('');
const cursor = ref<string | null>(null);
const saving = ref(false);
const now = ref(Date.now());
const formElement = ref<HTMLFormElement>();
const fieldErrors = ref<Record<string, string>>({});
const profileOpen = ref(false);
let returnFocus: HTMLElement | null = null;
const working = computed(() => busy.value || saving.value);
const numericFields = [
  {
    key: 'nominal_voltage_v',
    label: 'Tensão nominal (V)',
    min: 110,
    max: 240,
    step: '1',
  },
  {
    key: 'rated_power_w',
    label: 'Potência nominal (W)',
    min: 1,
    max: 10000,
    step: 'any',
  },
  {
    key: 'expected_life_hours',
    label: 'Vida útil de referência (horas)',
    min: 1000,
    max: 200000,
    step: '1',
  },
] as const;
const rows = computed(() =>
  devices.value.map((device) => {
    const frame = live.frames.get(device.id);
    const state = overviewFreshness(
      frame,
      live.devices.get(device.id)?.boot_id ?? device.boot_id,
      Math.max(now.value, Date.now()),
    );
    return {
      device,
      frame,
      state,
      lastAt: frame?.timestamp ?? device.last_sample_at,
    };
  }),
);
// Selection can survive pagination/refresh: its telemetry is not tied to the
// currently displayed registry page.
const selectedState = computed(() =>
  selected.value
    ? overviewFreshness(
        live.frames.get(selected.value.id),
        live.devices.get(selected.value.id)?.boot_id ?? selected.value.boot_id,
        Math.max(now.value, Date.now()),
      )
    : undefined,
);
const telemetryLabel = (kind: string) =>
  ({
    recent: 'Dados recentes',
    old: 'Dados desatualizados',
    missing: 'Sem telemetria recente',
    unavailable: 'Telemetria indisponível',
  })[kind] ?? 'Telemetria indisponível';
const clock = setInterval(() => {
  now.value = Date.now();
}, 500);
onBeforeUnmount(() => clearInterval(clock));
function validate() {
  const errors: Record<string, string> = {};
  for (const input of formElement.value?.querySelectorAll('input') ?? []) {
    if (input.disabled || input.validity.valid) continue;
    errors[input.name] = input.validity.valueMissing
      ? 'Preencha este campo.'
      : input.validity.patternMismatch
        ? 'Use letras, números, _ ou -.'
        : input.validity.rangeUnderflow || input.validity.rangeOverflow
          ? `Informe um valor entre ${input.min} e ${input.max}.`
          : 'Informe um valor válido para este campo.';
  }
  if (
    !name.value.trim() ||
    [...name.value].some(
      (character) =>
        character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127,
    )
  )
    errors.name = 'Informe um nome válido.';
  for (const field of Object.keys(labels) as Field[]) {
    const range = profile.value.healthy_ranges[field];
    if (range.minimum >= range.maximum)
      errors[`${field}.maximum`] = 'O máximo deve ser maior que o mínimo.';
  }
  fieldErrors.value = errors;
  if (Object.keys(errors).some((key) => !['id', 'name', 'zone'].includes(key)))
    profileOpen.value = true;
  if (Object.keys(errors).length) {
    void nextTick(() =>
      formElement.value
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus(),
    );
    return false;
  }
  return true;
}
async function closeForm() {
  showForm.value = false;
  await nextTick();
  returnFocus?.focus();
}
async function selectDevice(device: Device) {
  selected.value = device;
  await nextTick();
  document.getElementById('device-detail-heading')?.focus();
}
const administrator = computed(
  () => currentUser.value?.role === 'administrador',
);
async function load(append = false) {
  busy.value = true;
  error.value = '';
  try {
    const result = await api<{ items: Device[]; next_cursor: string | null }>(
      `/devices?limit=50${append && cursor.value ? `&after=${encodeURIComponent(cursor.value)}` : ''}`,
    );
    devices.value = append ? [...devices.value, ...result.items] : result.items;
    if (!selected.value && typeof route.query.device === 'string')
      selected.value =
        devices.value.find((item) => item.id === route.query.device) ?? null;
    if (selected.value)
      selected.value =
        devices.value.find((item) => item.id === selected.value?.id) ??
        selected.value;
    cursor.value = result.next_cursor;
  } catch (failure) {
    error.value =
      failure instanceof Error
        ? failure.message
        : 'Falha ao consultar dispositivos.';
  } finally {
    busy.value = false;
  }
}
function form(device: Device | null, event?: Event) {
  returnFocus = (event?.currentTarget as HTMLElement) ?? null;
  fieldErrors.value = {};
  profileOpen.value = false;
  editing.value = device;
  id.value = device?.id ?? '';
  name.value = device?.name ?? '';
  zone.value = device?.zone ?? '';
  profile.value = device ? structuredClone(toRaw(device.profile)) : defaults();
  showForm.value = true;
  error.value = '';
  notice.value = '';
  void nextTick(() => document.getElementById('device-name')?.focus());
}
async function save() {
  if (working.value || !validate()) return;
  saving.value = true;
  busy.value = true;
  error.value = '';
  notice.value = '';
  try {
    const path = editing.value
      ? `/devices/${encodeURIComponent(editing.value.id)}`
      : '/devices';
    const body = editing.value
      ? {
          expected_revision: editing.value.revision,
          name: name.value,
          profile: profile.value,
        }
      : {
          id: id.value,
          name: name.value,
          zone: zone.value,
          profile: profile.value,
        };
    const result = await api<Device>(path, {
      method: editing.value ? 'PATCH' : 'POST',
      body: JSON.stringify(body),
    });
    selected.value = result;
    showForm.value = false;
    notice.value =
      'Cadastro salvo. O estado físico do aparelho não foi alterado.';
    await load();
    startRealtime();
    await nextTick();
    document.getElementById('device-detail-heading')?.focus();
  } catch (failure) {
    if (
      failure instanceof ApiError &&
      failure.status === 409 &&
      !editing.value
    ) {
      fieldErrors.value.id = failure.message;
      void nextTick(() =>
        formElement.value?.querySelector<HTMLElement>('[name="id"]')?.focus(),
      );
    }
    error.value =
      failure instanceof Error ? failure.message : 'Falha ao salvar cadastro.';
  } finally {
    busy.value = false;
    saving.value = false;
  }
}
async function toggle(device: Device) {
  busy.value = true;
  error.value = '';
  try {
    const result = await api<Device>(
      `/devices/${encodeURIComponent(device.id)}`,
      {
        method: 'PATCH',
        body: JSON.stringify({
          expected_revision: device.revision,
          enabled: !device.enabled,
        }),
      },
    );
    if (selected.value?.id === device.id) selected.value = result;
    notice.value = result.enabled
      ? 'Cadastro habilitado. Aguardando telemetria para confirmar o estado físico.'
      : 'Cadastro desabilitado. Comandos bloqueados e histórico preservado; o aparelho não foi desligado por esta ação.';
    await load();
    startRealtime();
  } catch (failure) {
    error.value =
      failure instanceof Error ? failure.message : 'Falha ao alterar cadastro.';
  } finally {
    busy.value = false;
  }
}
onMounted(() => void load());
</script>
<template>
  <div class="task-page devices-page">
    <header class="tp-heading">
      <div>
        <p class="tp-overline">EQUIPAMENTOS</p>
        <h1>Dispositivos</h1>
      </div>
      <Button
        v-if="administrator"
        variant="primary"
        :disabled="working"
        @click="form(null, $event)"
        >Novo dispositivo</Button
      >
    </header>
    <Alert v-if="error" tone="danger" role="alert">{{ error }}</Alert>
    <Alert v-if="notice" tone="good" role="status">{{ notice }}</Alert>
    <Card v-if="showForm && administrator" class="tp-card">
      <form
        ref="formElement"
        novalidate
        :aria-busy="saving"
        @submit.prevent="save"
      >
        <h2>{{ editing ? 'Editar dispositivo' : 'Cadastrar dispositivo' }}</h2>
        <div class="tp-form-grid">
          <label
            >Nome<input
              id="device-name"
              aria-label="Nome"
              v-model="name"
              name="name"
              required
              maxlength="80"
              :aria-invalid="!!fieldErrors.name"
              :aria-describedby="
                fieldErrors.name ? 'device-name-error' : undefined
              "
              @input="fieldErrors.name = ''"
            /><span
              v-if="fieldErrors.name"
              id="device-name-error"
              class="tp-field-error"
              >{{ fieldErrors.name }}</span
            ></label
          >
          <label
            >Zona<input
              v-model="zone"
              aria-label="Zona"
              name="zone"
              required
              pattern="[A-Za-z0-9_\-]{1,64}"
              maxlength="64"
              :disabled="!!editing"
              :aria-invalid="!!fieldErrors.zone"
              :aria-describedby="
                fieldErrors.zone ? 'device-zone-error' : undefined
              "
              @input="fieldErrors.zone = ''"
            /><span
              v-if="fieldErrors.zone"
              id="device-zone-error"
              class="tp-field-error"
              >{{ fieldErrors.zone }}</span
            ></label
          >
          <label
            >ID do dispositivo<input
              v-model="id"
              aria-label="ID do dispositivo"
              name="id"
              required
              pattern="[A-Za-z0-9_\-]{1,32}"
              maxlength="32"
              :disabled="!!editing"
              :aria-invalid="!!fieldErrors.id"
              :aria-describedby="
                fieldErrors.id ? 'device-id-error' : 'device-id-help'
              "
              @input="fieldErrors.id = ''"
            /><span
              v-if="fieldErrors.id"
              id="device-id-error"
              class="tp-field-error"
              >{{ fieldErrors.id }}</span
            ><small v-else id="device-id-help"
              >ID e zona não podem ser alterados depois do cadastro.</small
            ></label
          >
        </div>
        <details
          :open="profileOpen"
          @toggle="profileOpen = ($event.target as HTMLDetailsElement).open"
        >
          <summary>Perfil e faixas de referência</summary>
          <div class="tp-form-grid">
            <label v-for="field in numericFields" :key="field.key"
              >{{ field.label
              }}<input
                v-model.number="profile[field.key]"
                :aria-label="field.label"
                :name="field.key"
                type="number"
                required
                :min="field.min"
                :max="field.max"
                :step="field.step"
                :aria-invalid="!!fieldErrors[field.key]"
                :aria-describedby="
                  fieldErrors[field.key]
                    ? `field-${field.key}-error`
                    : undefined
                "
              /><span
                v-if="fieldErrors[field.key]"
                :id="`field-${field.key}-error`"
                class="tp-field-error"
                >{{ fieldErrors[field.key] }}</span
              ></label
            >
          </div>
          <div class="tp-form-grid">
            <fieldset
              v-for="(label, field) in labels"
              :key="field"
              class="device-range"
            >
              <legend>{{ label }}</legend>
              <label
                v-for="bound in ['minimum', 'maximum'] as const"
                :key="bound"
                >{{ bound === 'minimum' ? 'Mínimo' : 'Máximo'
                }}<input
                  v-model.number="profile.healthy_ranges[field][bound]"
                  :name="`${field}.${bound}`"
                  :aria-label="`${label} — ${bound === 'minimum' ? 'Mínimo' : 'Máximo'}`"
                  type="number"
                  :min="
                    ['current_a', 'vibration_rms_mm_s'].includes(field)
                      ? 0
                      : -50
                  "
                  :max="
                    ['current_a', 'vibration_rms_mm_s'].includes(field)
                      ? 50
                      : 150
                  "
                  step="any"
                  required
                  :aria-invalid="!!fieldErrors[`${field}.${bound}`]"
                  :aria-describedby="
                    fieldErrors[`${field}.${bound}`]
                      ? `field-${field}-${bound}-error`
                      : undefined
                  "
                /><span
                  v-if="fieldErrors[`${field}.${bound}`]"
                  :id="`field-${field}-${bound}-error`"
                  class="tp-field-error"
                  >{{ fieldErrors[`${field}.${bound}`] }}</span
                ></label
              >
            </fieldset>
          </div>
          <p class="tp-muted">
            As faixas de referência não alteram as proteções físicas do
            equipamento.
          </p>
        </details>
        <p v-if="!editing" class="tp-muted">
          O cadastro não cria um simulador nem provisiona credenciais MQTT.
        </p>
        <div class="tp-actions device-form-actions">
          <Button type="submit" variant="primary" :disabled="working">{{
            saving ? 'Salvando…' : 'Salvar cadastro'
          }}</Button
          ><Button type="button" :disabled="working" @click="closeForm"
            >Cancelar</Button
          >
        </div>
      </form>
    </Card>
    <Card class="tp-card" :aria-busy="busy"
      ><div class="tp-section-heading">
        <h2>Equipamentos cadastrados</h2>
        <Button :disabled="working" @click="load()">Atualizar lista</Button>
      </div>
      <p v-if="busy && !saving" role="status" class="tp-muted">
        Consultando cadastro…
      </p>
      <p v-if="!busy && !devices.length && !error" class="tp-muted">
        Nenhum dispositivo cadastrado.
      </p>
      <ul class="device-list">
        <li
          v-for="row in rows"
          :key="row.device.id"
          class="device-row"
          :data-device-id="row.device.id"
          :class="{ 'device-selected': selected?.id === row.device.id }"
        >
          <div>
            <h3>{{ row.device.name }}</h3>
            <p class="tp-muted">{{ row.device.zone }}</p>
            <div class="tp-actions">
              <Badge :tone="row.device.enabled ? 'good' : 'neutral'">{{
                row.device.enabled ? 'Habilitado' : 'Desabilitado'
              }}</Badge>
            </div>
          </div>
          <div>
            <Badge :tone="row.state.fresh ? 'good' : 'neutral'">{{
              telemetryLabel(row.state.kind)
            }}</Badge>
            <p v-if="row.lastAt" class="tp-muted">
              {{ row.frame ? 'Última leitura' : 'Último registro' }} às
              {{ new Date(row.lastAt).toLocaleString('pt-BR') }}
            </p>
            <p v-else class="tp-muted">Sem leitura observada.</p>
            <p v-if="row.state.kind === 'unavailable'" class="tp-muted">
              {{ row.state.reason }}
            </p>
            <p v-if="row.state.fresh && row.frame" class="tp-muted">
              Compressor
              {{
                row.frame.conteudo.telemetry.actuators.compressor_on
                  ? 'ligado'
                  : 'desligado'
              }}
            </p>
          </div>
          <div class="tp-actions">
            <Button
              :aria-label="`Detalhes de ${row.device.name}`"
              :disabled="working"
              @click="selectDevice(row.device)"
              >Detalhes</Button
            ><template v-if="administrator"
              ><Button
                :aria-label="`Editar ${row.device.name}`"
                :disabled="working"
                @click="form(row.device, $event)"
                >Editar</Button
              ><Button
                :aria-label="`${row.device.enabled ? 'Desabilitar' : 'Habilitar'} ${row.device.name}`"
                :disabled="working"
                @click="toggle(row.device)"
                >{{ row.device.enabled ? 'Desabilitar' : 'Habilitar' }}</Button
              ></template
            >
          </div>
        </li>
      </ul>
      <Button v-if="cursor" :disabled="working" @click="load(true)"
        >Carregar mais</Button
      >
    </Card>
    <template v-if="selected"
      ><header class="tp-heading">
        <div>
          <h2 id="device-detail-heading" tabindex="-1">{{ selected.name }}</h2>
          <p class="tp-muted">{{ selected.zone }}</p>
        </div>
        <Badge :tone="selected.enabled ? 'good' : 'neutral'">{{
          selected.enabled ? 'Cadastro habilitado' : 'Cadastro desabilitado'
        }}</Badge>
      </header>
      <div class="device-detail-grid">
        <ControlPanel
          :key="selected.id"
          :device-id="selected.id"
          :enabled="selected.enabled"
          pilot
          management
          :pilot-fresh="selectedState?.fresh ?? false"
        />
        <div class="tp-stack">
          <Card class="tp-card"
            ><details>
              <summary>Detalhes do cadastro</summary>
              <dl class="tp-definition">
                <dt>ID</dt>
                <dd>{{ selected.id }}</dd>
                <dt>Revisão</dt>
                <dd>{{ selected.revision }}</dd>
                <dt>Inicialização observada</dt>
                <dd>
                  {{
                    live.devices.get(selected.id)?.boot_id ??
                    selected.boot_id ??
                    'Não observada'
                  }}
                </dd>
                <dt>Tensão nominal</dt>
                <dd>{{ selected.profile.nominal_voltage_v }} V</dd>
                <dt>Potência nominal</dt>
                <dd>{{ selected.profile.rated_power_w }} W</dd>
                <dt>Vida útil de referência</dt>
                <dd>{{ selected.profile.expected_life_hours }} h</dd>
              </dl>
              <h3>Sensores e faixas</h3>
              <ul class="device-technical-list">
                <li
                  v-for="(sensor, field) in selected.sensor_ids"
                  :key="sensor"
                >
                  <strong>{{ labels[field] }}</strong
                  ><br />{{ sensor }}<br />{{
                    selected.profile.healthy_ranges[field].minimum
                  }}–{{ selected.profile.healthy_ranges[field].maximum }}
                  {{ selected.sensor_units[field] }}
                </li>
              </ul>
              <h3>Atuadores</h3>
              <ul class="device-technical-list">
                <li v-for="actuator in selected.actuator_ids" :key="actuator">
                  {{ actuator }} · liga/desliga
                </li>
              </ul>
            </details></Card
          >
          <HistoryPanel :key="selected.id" :device-id="selected.id" pilot />
        </div>
      </div>
    </template>
  </div>
</template>
<style scoped>
.device-list {
  list-style: none;
  padding: 0;
  margin: 1rem 0 0;
}
.device-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(10rem, 0.7fr);
  gap: 1.25rem;
  align-items: center;
  border-top: 1px solid #e2e8f0;
  padding: 1.25rem 0;
}
.device-row h3 {
  margin: 0;
}
.device-row > :first-child .tp-actions {
  margin-top: 0.75rem;
}
.device-selected {
  border-left: 3px solid #0f766e;
  padding-left: 1rem;
}
.device-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  align-items: start;
  gap: 1.28571rem;
}
.device-range {
  margin: 0;
  padding: 0.75rem;
  border: 1px solid #64748b;
  border-radius: 0.5rem;
}
.device-range label + label {
  margin-top: 0.75rem;
}
.device-form-actions {
  margin-top: 1.25rem;
}
.device-technical-list {
  padding-left: 1.25rem;
  font-size: 1rem;
  overflow-wrap: anywhere;
}
.device-technical-list li {
  margin: 0.75rem 0;
}
@media (max-width: 850px) {
  .device-row,
  .device-detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
