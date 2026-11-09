<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { api, currentUser } from '../auth';
interface Command {
  id: string;
  revision: number;
  producer: string;
  status: 'pending' | 'confirmed' | 'failed';
  result: string | null;
  reason_code: string;
  execution_unknown: boolean;
  created_at: string;
}
interface Observation {
  fresh: boolean;
  observation: null | {
    sampled_at: string;
    mode: string;
    manual_cooling_block: boolean;
    telemetry: {
      actuators: { compressor_on: boolean; condenser_fan_on: boolean };
    };
  };
}
interface Rule {
  revision: number;
  timezone: string;
  configuration: {
    enabled: boolean;
    setpoint_c: number;
    hysteresis_c: number;
    minimum_off_seconds: number;
    minimum_on_seconds: number;
    schedule_enabled: boolean;
    start_hour: number;
    end_hour: number;
    weekdays: number[];
  };
}
const props = defineProps<{ deviceId: string; enabled?: boolean }>();
const state = ref<Observation | null>(null);
const commands = ref<Command[]>([]);
const rule = ref<Rule | null>(null);
const error = ref('');
const loadingError = ref('');
const busy = ref(false);
const notice = ref('');
const submitted = ref('');
const operator = computed(() =>
  ['operador', 'administrador'].includes(currentUser.value?.role ?? ''),
);
const administrator = computed(
  () => currentUser.value?.role === 'administrador',
);
const pending = computed(() =>
  commands.value.some((item) => item.status === 'pending'),
);
const latest = computed(() =>
  commands.value.find((item) => item.id === submitted.value),
);
let timer: ReturnType<typeof setTimeout> | undefined;
let generation = 0;
let controller: AbortController | undefined;
let intent: { action: string; key: string } | undefined;
async function refresh(epoch: number) {
  const request = new AbortController();
  controller = request;
  try {
    const [observation, history] = await Promise.all([
      api<Observation>(
        `/devices/${encodeURIComponent(props.deviceId)}/control`,
        { signal: request.signal },
      ),
      api<{ items: Command[] }>(
        `/devices/${encodeURIComponent(props.deviceId)}/commands`,
        { signal: request.signal },
      ),
    ]);
    if (epoch !== generation) return;
    state.value = observation;
    commands.value = history.items;
    loadingError.value = '';
  } catch (failure) {
    if (epoch === generation && !request.signal.aborted)
      loadingError.value =
        failure instanceof Error ? failure.message : 'Controle indisponível.';
  } finally {
    if (epoch === generation)
      timer = setTimeout(() => void refresh(epoch), 2000);
  }
}
async function loadRule(epoch: number) {
  try {
    const result = await api<Rule>(
      `/devices/${encodeURIComponent(props.deviceId)}/rule`,
    );
    if (epoch === generation) rule.value = result;
  } catch (failure) {
    if (epoch === generation)
      error.value =
        failure instanceof Error ? failure.message : 'Regra indisponível.';
  }
}
async function send(action: 'fan_on' | 'fan_off' | 'release_auto') {
  busy.value = true;
  error.value = '';
  notice.value = '';
  if (intent?.action !== action) intent = { action, key: crypto.randomUUID() };
  const epoch = generation;
  try {
    const result = await api<Command>(
      `/devices/${encodeURIComponent(props.deviceId)}/commands`,
      {
        method: 'POST',
        headers: { 'Idempotency-Key': intent.key },
        body: JSON.stringify({ action }),
      },
    );
    if (epoch !== generation) return;
    submitted.value = result.id;
    commands.value = [
      result,
      ...commands.value.filter((item) => item.id !== result.id),
    ];
    intent = undefined;
    notice.value =
      'Intenção registrada. Aguardando confirmação física do aparelho.';
  } catch (failure) {
    if (epoch === generation)
      error.value =
        failure instanceof Error
          ? failure.message
          : 'Sem confirmação do pedido. Repetir a mesma ação reutiliza sua chave.';
  } finally {
    if (epoch === generation) busy.value = false;
  }
}
async function saveRule() {
  if (!rule.value) return;
  busy.value = true;
  error.value = '';
  try {
    rule.value = await api<Rule>(
      `/devices/${encodeURIComponent(props.deviceId)}/rule`,
      {
        method: 'PATCH',
        body: JSON.stringify({
          expected_revision: rule.value.revision,
          configuration: rule.value.configuration,
        }),
      },
    );
    notice.value =
      'Regra salva; será avaliada sobre a próxima leitura recente.';
  } catch (failure) {
    error.value =
      failure instanceof Error ? failure.message : 'Falha ao salvar regra.';
  } finally {
    busy.value = false;
  }
}
watch(
  () => props.deviceId,
  () => {
    generation++;
    clearTimeout(timer);
    controller?.abort();
    state.value = null;
    commands.value = [];
    rule.value = null;
    submitted.value = '';
    intent = undefined;
    error.value = '';
    notice.value = '';
    busy.value = false;
    void refresh(generation);
    void loadRule(generation);
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  generation++;
  clearTimeout(timer);
  controller?.abort();
});
</script>
<template>
  <section class="card control-panel">
    <h2>Controle do ar-condicionado</h2>
    <p>
      Consulta operacional por API. Os valores deste painel não alimentam
      gráficos ou cena em tempo real.
    </p>
    <p v-if="loadingError" role="alert" class="error-box">{{ loadingError }}</p>
    <p v-if="error" role="alert" class="error-box">{{ error }}</p>
    <p v-if="!state && !loadingError" role="status">
      Consultando estado observado…
    </p>
    <p v-if="state?.fresh && state.observation" data-testid="physical-state">
      Última leitura: compressor
      {{
        state.observation.telemetry.actuators.compressor_on
          ? 'ligado'
          : 'desligado'
      }}
      · ventilador do condensador
      {{
        state.observation.telemetry.actuators.condenser_fan_on
          ? 'ligado'
          : 'desligado'
      }}
      · modo
      {{ state.observation.mode === 'manual' ? 'manual' : 'automático' }}.
    </p>
    <p v-else-if="state">Sem observação recente; comandos indisponíveis.</p>
    <p v-if="state?.observation?.manual_cooling_block">
      Bloqueio manual de refrigeração ativo. Liberar automático permite
      novamente avaliar o termostato.
    </p>
    <div v-if="operator" class="actions">
      <button
        class="button secondary"
        :disabled="busy || pending || !state?.fresh || enabled === false"
        @click="send('fan_on')"
      >
        Ligar ventilador do condensador</button
      ><button
        class="button secondary"
        :disabled="busy || pending || !state?.fresh || enabled === false"
        @click="send('fan_off')"
      >
        Desligar ventilador do condensador</button
      ><button
        class="button primary"
        :disabled="busy || pending || !state?.fresh || enabled === false"
        @click="send('release_auto')"
      >
        Liberar controle automático
      </button>
    </div>
    <p v-else>
      Seu papel permite consultar; comandos exigem operador ou administrador.
    </p>
    <p>
      Desligar o ventilador também solicita desligar o compressor. O manual
      permanece até a liberação do automático. Proteção térmica e intervalo
      mínimo desligado são verificados no simulador.
    </p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p
      v-if="latest"
      role="status"
      :data-command-id="latest.id"
      :data-command-status="latest.status"
    >
      Comando {{ latest.id }} · revisão {{ latest.revision }} ·
      {{
        latest.status === 'pending'
          ? 'pendente'
          : latest.status === 'confirmed'
            ? 'confirmado'
            : 'falhou'
      }}
      · {{ latest.result ?? 'aguardando ACK'
      }}<span v-if="latest.execution_unknown"
        >. Sem ACK: resultado físico desconhecido; consultar novas leituras. Não
        repetir como nova intenção.</span
      >
    </p>
    <details v-if="rule">
      <summary>Termostato e agenda · revisão {{ rule.revision }}</summary>
      <p>
        Fuso America/Sao_Paulo. Liga acima do setpoint + faixa; desliga abaixo
        do setpoint − faixa, respeitando ciclos mínimos. Manual tem prioridade.
        Faixas térmicas de proteção: parar a 80 °C na carcaça, permitir nova
        partida até 75 °C.
      </p>
      <form class="rule-form" @submit.prevent="saveRule">
        <fieldset :disabled="!administrator || busy">
          <legend>Regra automática</legend>
          <label
            ><input v-model="rule.configuration.enabled" type="checkbox" />Regra
            habilitada</label
          >
          <div class="fields">
            <label
              >Setpoint (°C)<input
                v-model.number="rule.configuration.setpoint_c"
                type="number"
                min="18"
                max="30"
                step="0.5"
                required /></label
            ><label
              >Faixa de histerese (°C)<input
                v-model.number="rule.configuration.hysteresis_c"
                type="number"
                min="0.5"
                max="3"
                step="0.5"
                required /></label
            ><label
              >Mínimo desligado (s)<input
                v-model.number="rule.configuration.minimum_off_seconds"
                type="number"
                min="180"
                max="1800"
                step="1"
                required /></label
            ><label
              >Mínimo ligado (s)<input
                v-model.number="rule.configuration.minimum_on_seconds"
                type="number"
                min="60"
                max="600"
                step="1"
                required
            /></label>
          </div>
          <label
            ><input
              v-model="rule.configuration.schedule_enabled"
              type="checkbox"
            />Usar agenda</label
          >
          <div class="fields">
            <label
              >Hora inicial<input
                v-model.number="rule.configuration.start_hour"
                type="number"
                min="0"
                max="23"
                required /></label
            ><label
              >Hora final<input
                v-model.number="rule.configuration.end_hour"
                type="number"
                min="0"
                max="23"
                required
            /></label>
          </div>
          <p>
            Dias: 1 segunda-feira a 7 domingo; no período que cruza meia-noite,
            a madrugada pertence ao dia inicial.
          </p>
          <div class="actions">
            <label v-for="day in [1, 2, 3, 4, 5, 6, 7]" :key="day"
              ><input
                v-model="rule.configuration.weekdays"
                type="checkbox"
                :value="day"
              />{{ day }}</label
            >
          </div>
          <button v-if="administrator" class="button primary" type="submit">
            Salvar regra
          </button>
        </fieldset>
      </form>
    </details>
    <details>
      <summary>Últimas intenções e confirmações</summary>
      <p v-if="!commands.length">Nenhum comando registrado.</p>
      <ul>
        <li v-for="command in commands" :key="command.id">
          {{ command.id }} · {{ command.producer }} · revisão
          {{ command.revision }} · {{ command.status }} ·
          {{ command.result ?? command.reason_code
          }}<span v-if="command.execution_unknown">
            · resultado físico desconhecido</span
          >
        </li>
      </ul>
    </details>
  </section>
</template>
<style scoped>
.control-panel {
  padding: 1.4rem;
  margin-top: 1.5rem;
  overflow-wrap: anywhere;
}
.control-panel p {
  font-size: 0.85rem;
  line-height: 1.6;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin: 1rem 0;
}
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
}
.fields label {
  display: grid;
  gap: 0.4rem;
}
.rule-form fieldset {
  border: 1px solid #ccd8de;
  border-radius: 0.6rem;
  padding: 1rem;
  margin-top: 1rem;
}
.control-panel input[type='checkbox'] {
  width: auto;
}
.control-panel details {
  margin: 1rem 0;
}
.control-panel summary {
  cursor: pointer;
}
.control-panel li {
  font-size: 0.8rem;
  margin: 0.5rem 0;
}
</style>
