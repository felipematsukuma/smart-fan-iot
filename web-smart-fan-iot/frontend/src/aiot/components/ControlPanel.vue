<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { api, currentUser } from '../auth';
import Button from '../ui/Button.vue';
import { Card, Badge, Alert } from '../ui/primitives';
import { commandPresentation } from '../command-presentation';
import type { Command, Observation, Rule } from '../control-types';
import ControlSettings from './ControlSettings.vue';
const props = defineProps<{
  deviceId: string;
  enabled?: boolean;
  target?: 'compressor' | 'fan';
  pilot?: boolean;
  pilotFresh?: boolean;
  management?: boolean;
}>();
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
const shownCommand = computed(() =>
  busy.value
    ? undefined
    : (latest.value ??
      commands.value.find((item) => item.status === 'pending') ??
      commands.value[0]),
);
const progress = computed(() =>
  commandPresentation(shownCommand.value, busy.value),
);
const controlsUnavailable = computed(
  () =>
    busy.value ||
    pending.value ||
    !!loadingError.value ||
    !state.value?.fresh ||
    props.enabled === false ||
    (props.pilot && !props.pilotFresh),
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
  <Card v-if="pilot" class="pv-control" aria-labelledby="pilot-control-heading">
    <div class="pv-control-title">
      <div>
        <span class="pv-overline">OPERAÇÃO</span>
        <h2 id="pilot-control-heading">Estado e comandos</h2>
      </div>
      <Badge>{{
        state?.fresh && state.observation
          ? state.observation.mode === 'manual'
            ? 'Manual'
            : 'Automático'
          : 'Sem observação atual'
      }}</Badge>
    </div>
    <Alert v-if="loadingError || error" tone="danger" role="alert">{{
      loadingError || error
    }}</Alert>
    <p v-if="!state && !loadingError" role="status">
      Consultando estado observado…
    </p>
    <div
      v-if="state?.fresh && state.observation && pilotFresh"
      data-testid="physical-state"
      class="pv-physical"
    >
      <div>
        <span>Compressor</span
        ><strong>{{
          state.observation.telemetry.actuators.compressor_on
            ? 'Ligado'
            : 'Desligado'
        }}</strong>
      </div>
      <div>
        <span>Ventilador</span
        ><strong>{{
          state.observation.telemetry.actuators.condenser_fan_on
            ? 'Ligado'
            : 'Desligado'
        }}</strong>
      </div>
      <small
        >Estado observado às
        {{
          new Date(state.observation.sampled_at).toLocaleTimeString('pt-BR')
        }}</small
      >
    </div>
    <p v-else-if="state" class="pv-control-help">
      Sem observação recente. Comandos indisponíveis.
    </p>
    <p v-if="state?.observation?.manual_cooling_block" class="pv-control-help">
      Bloqueio manual ativo. Libere o automático para permitir a avaliação do
      termostato.
    </p>
    <div v-if="operator" class="pv-command-actions">
      <Button :disabled="controlsUnavailable" @click="send('fan_on')"
        >Ligar ventilador</Button
      ><Button :disabled="controlsUnavailable" @click="send('fan_off')"
        >Desligar ventilador</Button
      ><Button
        variant="primary"
        :disabled="controlsUnavailable"
        @click="send('release_auto')"
        >Liberar automático</Button
      >
    </div>
    <p v-else class="pv-control-help">
      Seu acesso é de visualização. Operador e administrador podem enviar
      comandos.
    </p>
    <p class="pv-control-help">
      Desligar o ventilador também para o compressor. Proteções e espera mínima
      permanecem ativas.
    </p>
    <div
      v-if="shownCommand || busy"
      class="pv-command-progress"
      role="status"
      :data-command-id="shownCommand?.id"
      :data-command-status="busy ? 'sending' : shownCommand?.status"
    >
      <span class="pv-overline">ÚLTIMA INTENÇÃO</span
      ><Badge :tone="progress.tone">{{ progress.label }}</Badge>
      <p>{{ progress.detail }}</p>
      <small v-if="shownCommand"
        >Solicitação de
        {{ new Date(shownCommand.created_at).toLocaleString('pt-BR') }}</small
      >
    </div>
    <details class="pv-control-details">
      <summary>Detalhes do comando e da regra</summary>
      <dl v-if="shownCommand">
        <dt>Comando</dt>
        <dd>{{ shownCommand.id }}</dd>
        <dt>Revisão</dt>
        <dd>{{ shownCommand.revision }}</dd>
        <dt>Retorno</dt>
        <dd>
          {{ shownCommand.result ?? 'Aguardando confirmação do dispositivo' }}
        </dd>
        <dt>Referência de confirmação</dt>
        <dd>{{ shownCommand.ack_event_id ?? 'Nenhuma' }}</dd>
      </dl>
      <p v-if="rule">
        Regra {{ rule.revision }} · setpoint
        {{ rule.configuration.setpoint_c }} °C · faixa ±{{
          rule.configuration.hysteresis_c
        }}
        °C · mínimo desligado {{ rule.configuration.minimum_off_seconds }} s.
      </p>
      <p>
        Recebimento intermediário não é confirmação física. A execução é
        confirmada somente por retorno validado do dispositivo.
      </p>
      <RouterLink :to="{ path: '/dispositivos', query: { device: deviceId } }"
        >Abrir detalhes do equipamento →</RouterLink
      >
    </details>
    <ControlSettings
      v-if="management"
      v-model:rule="rule"
      :commands="commands"
      :administrator="administrator"
      :busy="busy"
      pilot
      @save="saveRule"
    />
    <p
      v-if="management && notice.startsWith('Regra')"
      role="status"
      class="pv-control-help"
    >
      {{ notice }}
    </p>
  </Card>
  <section v-else class="card control-panel">
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
        v-if="target !== 'compressor'"
        class="button secondary"
        :disabled="busy || pending || !state?.fresh || enabled === false"
        @click="send('fan_on')"
      >
        Ligar ventilador do condensador</button
      ><button
        v-if="target !== 'compressor'"
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
    <ControlSettings
      v-model:rule="rule"
      :commands="commands"
      :administrator="administrator"
      :busy="busy"
      @save="saveRule"
    />
  </section>
</template>
<style scoped>
.pv-control {
  padding: 22px;
  min-width: 0;
}
.pv-control-title {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.pv-control-title h2 {
  margin: 4px 0 0;
  font-size: 1.21429rem;
  letter-spacing: -0.3px;
}
.pv-overline {
  display: block;
  font-size: 1rem;
  font-weight: 650;
  letter-spacing: 1px;
  color: #475569;
  margin-bottom: 6px;
}
.pv-physical {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  padding: 0 0 18px;
  border-bottom: 1px solid #edf1f4;
}
.pv-physical span {
  display: block;
  color: #475569;
  font-size: 1rem;
}
.pv-physical strong {
  font-size: 1.14286rem;
  font-weight: 650;
  color: #1e293b;
}
.pv-physical small {
  grid-column: 1/-1;
  color: #475569;
  font-size: 1rem;
}
.pv-command-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 18px;
}
.pv-command-actions > :last-child {
  grid-column: 1/-1;
}
.pv-control-help {
  color: #475569;
  font-size: 1rem;
  line-height: 1.6;
  margin: 14px 0;
}
.pv-command-progress {
  border-top: 1px solid #e2e8f0;
  padding-top: 16px;
  margin-top: 16px;
}
.pv-command-progress p {
  font-size: 1rem;
  color: #475569;
  margin: 9px 0;
}
.pv-command-progress small {
  font-size: 1rem;
  color: #475569;
}
.pv-control-details {
  font-size: 1rem;
  color: #475569;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}
.pv-control-details summary {
  cursor: pointer;
  font-weight: 600;
}
.pv-control-details dl {
  display: grid;
  gap: 5px;
}
.pv-control-details dd {
  margin: 0 0 8px;
  overflow-wrap: anywhere;
}
.pv-control-details a {
  color: #0f766e;
  text-decoration: underline;
}
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
