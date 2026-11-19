<script setup lang="ts">
import {
  computed,
  onMounted,
  onBeforeUnmount,
  nextTick,
  ref,
  watch,
} from 'vue';
import { Card, Badge } from '../ui/primitives';
import AssistantData from '../components/AssistantData.vue';
import '../ui/task-page.css';
import '../ui/final-pages.css';
import { apiResponse, onSessionEnded } from '../auth';
import { live } from '../realtime';
import { safeMarkdown } from '../assistant-markdown';
import { consumeSse } from '../assistant-stream';
interface Turn {
  id: string;
  question: string;
  answer: string;
  summary: Record<string, unknown> | null;
  outcome: string;
  firstToken: number | null;
  model: string;
}
const devices = computed(() => [...live.devices.values()]);
const selected = ref('');
const question = ref('');
const turns = ref<Turn[]>([]);
const busy = ref(false);
const error = ref('');
const state = ref('');
const phase = ref('idle');
const phaseLabels: Record<string, string> = {
  waiting: 'Aguardando',
  loading: 'Carregando modelo',
  streaming: 'Recebendo resposta',
  completed: 'Concluída',
  cancelled: 'Cancelamento solicitado',
  failed: 'Erro',
};
const conversation = ref<HTMLElement>();
const composer = ref<HTMLElement>();
const workbench = ref<HTMLElement>();
const following = ref(true);
function trackScroll() {
  const el = conversation.value;
  if (el)
    following.value = el.scrollHeight - el.scrollTop - el.clientHeight <= 32;
}
async function follow() {
  await nextTick();
  if (following.value && conversation.value)
    conversation.value.scrollTop = conversation.value.scrollHeight;
}
function goToEnd() {
  following.value = true;
  void follow();
}
watch(
  () => turns.value.map((turn) => [turn.answer, turn.outcome, turn.summary]),
  () => void follow(),
  { deep: true, flush: 'post' },
);
function sizeWorkbench() {
  const el = workbench.value;
  if (!el) return;
  const top = el.getBoundingClientRect().top + scrollY;
  el.style.height = `${Math.max(340, (visualViewport?.height ?? innerHeight) - top - 16)}px`;
}
function viewportChanged() {
  sizeWorkbench();
  if (document.activeElement?.id === 'assistant-question')
    requestAnimationFrame(() =>
      composer.value?.scrollIntoView({ block: 'end', behavior: 'instant' }),
    );
}
onMounted(async () => {
  await nextTick();
  sizeWorkbench();
  visualViewport?.addEventListener('resize', viewportChanged);
});
let controller: AbortController | undefined;
let epoch = 0;
function cancel() {
  epoch++;
  controller?.abort();
  busy.value = false;
  phase.value = 'cancelled';
  state.value =
    'Cancelamento solicitado. A geração local é interrompida antes de liberar os recursos.';
  const last = turns.value.at(-1);
  if (last?.outcome === 'streaming') last.outcome = 'cancelled';
}
watch(
  devices,
  (items) => {
    if (!items.some((item) => item.id === selected.value))
      selected.value = items[0]?.id ?? '';
  },
  { immediate: true },
);
watch(selected, () => {
  cancel();
  turns.value = [];
  state.value = error.value = '';
  phase.value = 'idle';
  following.value = true;
});
const remove = onSessionEnded(cancel);
onBeforeUnmount(() => {
  cancel();
  remove();
  visualViewport?.removeEventListener('resize', viewportChanged);
});
async function send() {
  if (busy.value || !question.value.trim() || !selected.value) return;
  const generation = ++epoch;
  const text = question.value.trim();
  const history = turns.value
    .filter((turn) => turn.outcome === 'completed')
    .slice(-2)
    .map((turn) => ({
      question: turn.question.slice(0, 256),
      answer: turn.answer.slice(0, 512),
    }));
  const turn: Turn = {
    id: crypto.randomUUID(),
    question: text,
    answer: '',
    summary: null,
    outcome: 'streaming',
    firstToken: null,
    model: 'modelo local',
  };
  turns.value = [...turns.value.slice(-19), turn];
  const current = turns.value.at(-1)!;
  busy.value = true;
  error.value = '';
  state.value = 'Solicitando conversa local…';
  phase.value = 'waiting';
  void follow();
  const request = new AbortController();
  controller = request;
  try {
    const response = await apiResponse('/assistant/chat', {
      method: 'POST',
      signal: request.signal,
      body: JSON.stringify({
        device_id: selected.value,
        question: text,
        history,
      }),
    });
    await consumeSse(response, request.signal, ({ event, data }) => {
      if (generation !== epoch) return;
      if (event === 'meta') {
        phase.value = data.state === 'queued' ? 'waiting' : 'loading';
        state.value =
          data.state === 'queued'
            ? 'Aguardando o recurso local…'
            : 'Preparando o modelo local; a primeira resposta pode levar até 30 segundos.';
        if (data.summary && typeof data.summary === 'object')
          current.summary = data.summary as Record<string, unknown>;
        if (typeof data.model === 'string') current.model = data.model;
      } else if (event === 'delta') {
        state.value = 'Recebendo resposta…';
        phase.value = 'streaming';
        current.answer += data.text as string;
        if (current.answer.length > 32768) {
          request.abort();
          throw new Error('Resposta excedeu o limite local.');
        }
      } else if (event === 'done') {
        current.outcome = 'completed';
        phase.value = 'completed';
        current.firstToken =
          typeof data.first_token_ms === 'number' ? data.first_token_ms : null;
        state.value = 'Resposta concluída e auditada.';
        question.value = '';
      } else {
        current.outcome = 'failed';
        phase.value = 'failed';
        error.value = `${typeof data.message === 'string' ? data.message : 'Resposta interrompida.'} (${String(data.code ?? 'local_model_error')})`;
        state.value = '';
      }
    });
  } catch (failure) {
    if (generation === epoch && !request.signal.aborted) {
      current.outcome = 'failed';
      phase.value = 'failed';
      error.value =
        failure instanceof Error
          ? failure.message
          : 'Falha ao acessar assistente local.';
      state.value = '';
    }
  } finally {
    if (generation === epoch) busy.value = false;
  }
}
</script>
<template>
  <div class="task-page assistant-page">
    <header class="tp-heading">
      <h1>Assistente local</h1>
      <div class="assistant-device">
        <label for="assistant-device">Equipamento da conversa</label
        ><select id="assistant-device" v-model="selected" :disabled="busy">
          <option v-for="device in devices" :key="device.id" :value="device.id">
            {{ device.name }} · {{ device.zone }}
          </option>
        </select>
      </div>
    </header>
    <p class="assistant-warning">
      Atendimento parcial: o assistente pode cometer erros de significado.
      Confira os dados estruturados; o texto não executa comandos nem encerra
      alertas.
    </p>
    <p v-if="!devices.length" role="status">
      Aguardando dispositivos autorizados.
    </p>
    <div ref="workbench" class="assistant-workbench">
      <section
        ref="conversation"
        class="conversation"
        tabindex="0"
        aria-label="Conversa com assistente local"
        @scroll.passive="trackScroll"
      >
        <Card v-if="!turns.length" class="tp-card assistant-empty"
          ><p>O que você quer saber sobre o equipamento?</p></Card
        >
        <Card
          v-for="turn in turns"
          :key="turn.id"
          class="tp-card turn"
          :data-turn-outcome="turn.outcome"
          ><h2>Sua pergunta</h2>
          <p class="question">{{ turn.question }}</p>
          <div class="tp-section-heading">
            <h3>Resposta gerada</h3>
            <Badge :tone="turn.outcome === 'failed' ? 'danger' : 'neutral'">{{
              turn.outcome === 'streaming'
                ? 'Em andamento'
                : turn.outcome === 'completed'
                  ? 'Concluída'
                  : turn.outcome === 'cancelled'
                    ? 'Interrompida nesta interface'
                    : 'Não concluída'
            }}</Badge>
          </div>
          <!-- safeMarkdown alone emits HTML; raw HTML and remote images remain disabled. -->
          <div
            class="markdown"
            data-testid="assistant-answer"
            v-html="safeMarkdown(turn.answer)"
          />
          <p v-if="!turn.answer" class="tp-muted">
            {{
              turn.outcome === 'streaming'
                ? 'Aguardando o primeiro fragmento…'
                : 'Nenhuma resposta disponível.'
            }}
          </p>
          <AssistantData v-if="turn.summary" :summary="turn.summary" />
          <details>
            <summary>Detalhes da geração</summary>
            <p>Modelo: {{ turn.model }}</p>
            <p v-if="turn.firstToken != null">
              Primeiro fragmento: {{ (turn.firstToken / 1000).toFixed(2) }} s.
            </p>
            <p v-if="turn.outcome === 'cancelled'">
              Cancelamento solicitado; esta interface não confirma a liberação
              dos recursos no servidor.
            </p>
          </details>
        </Card>
      </section>
      <button
        v-if="!following && turns.length"
        class="button secondary chat-end"
        type="button"
        @click="goToEnd"
      >
        Ir para o fim da conversa
      </button>
      <form
        ref="composer"
        class="card tp-card question-form"
        @submit.prevent="send"
      >
        <label for="assistant-question">Pergunta sobre o equipamento</label
        ><textarea
          id="assistant-question"
          v-model="question"
          rows="2"
          maxlength="2000"
          :disabled="busy"
          required
          aria-describedby="assistant-limits"
        />
        <div class="tp-actions">
          <button
            class="button primary"
            :disabled="busy || !selected || !question.trim()"
          >
            Perguntar ao assistente</button
          ><button
            v-if="busy"
            type="button"
            class="button secondary"
            @click="cancel"
          >
            Cancelar resposta</button
          ><Badge
            v-if="phase !== 'idle'"
            :tone="phase === 'failed' ? 'danger' : 'neutral'"
            >{{ phaseLabels[phase] }}</Badge
          >
        </div>
        <p v-if="state" role="status" class="chat-status">{{ state }}</p>
        <p v-if="error" role="alert" class="tp-field-error">{{ error }}</p>
        <details>
          <summary>Limites e funcionamento</summary>
          <p id="assistant-limits">
            Até 2.000 caracteres e cinco perguntas por minuto. Até dois turnos
            recentes podem integrar o contexto, dentro do orçamento existente. O
            modelo local recebe um resumo agregado; não acessa os bancos nem
            executa comandos. Durante geração de dados ou treinamento o recurso
            pode estar indisponível.
          </p>
        </details>
      </form>
    </div>
  </div>
</template>
