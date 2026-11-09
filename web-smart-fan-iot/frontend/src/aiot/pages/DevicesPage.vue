<script setup lang="ts">
import { computed, onMounted, ref, toRaw } from 'vue';
import { api, currentUser } from '../auth';
import { startRealtime } from '../realtime';
import HistoryPanel from '../components/HistoryPanel.vue';
import ControlPanel from '../components/ControlPanel.vue';

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
function form(device: Device | null) {
  editing.value = device;
  id.value = device?.id ?? '';
  name.value = device?.name ?? '';
  zone.value = device?.zone ?? '';
  profile.value = device ? structuredClone(toRaw(device.profile)) : defaults();
  showForm.value = true;
  error.value = '';
  notice.value = '';
}
async function save() {
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
  } catch (failure) {
    error.value =
      failure instanceof Error ? failure.message : 'Falha ao salvar cadastro.';
  } finally {
    busy.value = false;
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
      ? 'Dispositivo ativado.'
      : 'Dispositivo desativado. Histórico preservado; comandos bloqueados. A desativação não desliga fisicamente o aparelho.';
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
  <div class="page-heading">
    <div>
      <p class="eyebrow">EQUIPAMENTOS E CAPACIDADES</p>
      <h1>Dispositivos</h1>
      <p>Cadastro separado das leituras e do estado físico observado.</p>
    </div>
    <button
      v-if="administrator"
      class="button primary"
      :disabled="busy"
      @click="form(null)"
    >
      Novo dispositivo
    </button>
  </div>
  <p v-if="error" role="alert" class="error-box">{{ error }}</p>
  <p v-if="notice" role="status">{{ notice }}</p>
  <form
    v-if="showForm && administrator"
    class="card device-form"
    @submit.prevent="save"
  >
    <h2>{{ editing ? 'Editar dispositivo' : 'Cadastrar ar-condicionado' }}</h2>
    <p>
      Perfil split on/off: cinco sensores e dois atuadores liga/desliga. IDs e
      zona são imutáveis. O cadastro não provisiona uma nova credencial MQTT nem
      cria um simulador.
    </p>
    <div class="fields">
      <label
        >ID do dispositivo<input
          v-model="id"
          required
          pattern="[A-Za-z0-9_-]{1,32}"
          maxlength="32"
          :disabled="!!editing" /></label
      ><label>Nome<input v-model="name" required maxlength="80" /></label
      ><label
        >Zona<input
          v-model="zone"
          required
          pattern="[A-Za-z0-9_-]{1,64}"
          maxlength="64"
          :disabled="!!editing"
      /></label>
      <label
        >Tensão nominal (V)<input
          v-model.number="profile.nominal_voltage_v"
          type="number"
          required
          min="110"
          max="240"
          step="1" /></label
      ><label
        >Potência nominal (W)<input
          v-model.number="profile.rated_power_w"
          type="number"
          required
          min="1"
          max="10000"
          step="any" /></label
      ><label
        >Vida útil de referência (horas)<input
          v-model.number="profile.expected_life_hours"
          type="number"
          required
          min="1000"
          max="200000"
          step="1"
      /></label>
    </div>
    <h3>Faixas de referência configuráveis</h3>
    <p>
      Valores didáticos; não substituem especificações do fabricante e não
      alteram os intertravamentos de segurança.
    </p>
    <div class="fields">
      <fieldset v-for="(label, field) in labels" :key="field">
        <legend>{{ label }}</legend>
        <label
          >Mínimo<input
            v-model.number="profile.healthy_ranges[field].minimum"
            type="number"
            min="-50"
            max="150"
            step="any"
            required /></label
        ><label
          >Máximo<input
            v-model.number="profile.healthy_ranges[field].maximum"
            type="number"
            min="-50"
            max="150"
            step="any"
            required
        /></label>
      </fieldset>
    </div>
    <div class="actions">
      <button type="submit" class="button primary" :disabled="busy">
        Salvar cadastro</button
      ><button
        type="button"
        class="button secondary"
        :disabled="busy"
        @click="showForm = false"
      >
        Cancelar
      </button>
    </div>
  </form>
  <section class="card" :aria-busy="busy">
    <div class="section-heading">
      <h2>Equipamentos cadastrados</h2>
      <button class="button secondary" :disabled="busy" @click="load()">
        Atualizar lista
      </button>
    </div>
    <p v-if="busy" role="status" class="table-message">Consultando cadastro…</p>
    <p v-else-if="!devices.length" class="table-message">
      Nenhum dispositivo cadastrado.
    </p>
    <div v-if="devices.length" class="table-scroll">
      <table>
        <caption>
          Metadados administrativos. Ativo não significa conectado ou ligado.
        </caption>
        <thead>
          <tr>
            <th>Equipamento</th>
            <th>Zona</th>
            <th>Cadastro</th>
            <th>Revisão</th>
            <th>Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="device in devices" :key="device.id">
            <td>
              {{ device.name }}<br /><small>{{ device.id }}</small>
            </td>
            <td>{{ device.zone }}</td>
            <td>{{ device.enabled ? 'Ativo' : 'Desativado' }}</td>
            <td>{{ device.revision }}</td>
            <td>
              <div class="actions">
                <button class="button secondary" @click="selected = device">
                  Detalhes de {{ device.id }}</button
                ><template v-if="administrator"
                  ><button
                    class="button secondary"
                    :disabled="busy"
                    @click="form(device)"
                  >
                    Editar {{ device.id }}</button
                  ><button
                    class="button secondary"
                    :disabled="busy"
                    @click="toggle(device)"
                  >
                    {{ device.enabled ? 'Desativar' : 'Ativar' }}
                    {{ device.id }}
                  </button></template
                >
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <button
      v-if="cursor"
      class="button secondary"
      :disabled="busy"
      @click="load(true)"
    >
      Carregar mais
    </button>
  </section>
  <section v-if="selected" class="card device-detail">
    <h2>Componentes de {{ selected.id }}</h2>
    <p>
      Split on/off ·
      {{
        selected.last_sample_at
          ? `Última amostra: ${new Date(selected.last_sample_at).toLocaleString('pt-BR')}`
          : 'Sem amostra observada'
      }}
    </p>
    <ul>
      <li v-for="(sensor, field) in selected.sensor_ids" :key="sensor">
        {{ sensor }} · {{ labels[field] }} ·
        {{ selected.profile.healthy_ranges[field].minimum }}–{{
          selected.profile.healthy_ranges[field].maximum
        }}
        {{ selected.sensor_units[field] }}
      </li>
      <li v-for="actuator in selected.actuator_ids" :key="actuator">
        {{ actuator }} · liga/desliga
      </li>
    </ul>
    <p>
      Boot observado: {{ selected.boot_id ?? 'Ainda não observado' }}. Não há
      previsão de saúde ou vida restante no cadastro.
    </p>
  </section>
  <ControlPanel
    v-if="selected"
    :key="selected.id"
    :device-id="selected.id"
    :enabled="selected.enabled"
  />
  <HistoryPanel v-if="selected" :device-id="selected.id" />
</template>
<style scoped>
.device-form,
.device-detail {
  padding: 1.4rem;
  margin-bottom: 1.5rem;
}
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
}
.fields label {
  display: grid;
  gap: 0.35rem;
}
.fields fieldset {
  border: 1px solid #ccd8de;
  border-radius: 0.5rem;
  padding: 0.8rem;
  min-width: 0;
}
.fields legend {
  font-size: 0.85rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.device-detail {
  margin-top: 1.5rem;
  overflow-wrap: anywhere;
}
.device-detail li {
  margin: 0.5rem 0;
}
caption {
  padding: 1rem;
  text-align: left;
  font-size: 0.8rem;
}
</style>
