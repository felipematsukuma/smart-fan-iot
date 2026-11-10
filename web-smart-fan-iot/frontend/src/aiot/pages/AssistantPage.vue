<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
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
let controller: AbortController | undefined;
let epoch = 0;
function cancel() {
  epoch++;
  controller?.abort();
  busy.value = false;
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
});
const remove = onSessionEnded(cancel);
onBeforeUnmount(() => {
  cancel();
  remove();
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
        state.value =
          data.state === 'queued'
            ? 'Aguardando o recurso local…'
            : 'Preparando o modelo local; a primeira resposta pode levar até 30 segundos.';
        if (data.summary && typeof data.summary === 'object')
          current.summary = data.summary as Record<string, unknown>;
        if (typeof data.model === 'string') current.model = data.model;
      } else if (event === 'delta') {
        state.value = 'Recebendo resposta…';
        current.answer += data.text as string;
        if (current.answer.length > 32768) {
          request.abort();
          throw new Error('Resposta excedeu o limite local.');
        }
      } else if (event === 'done') {
        current.outcome = 'completed';
        current.firstToken =
          typeof data.first_token_ms === 'number' ? data.first_token_ms : null;
        state.value = 'Resposta concluída e auditada.';
        question.value = '';
      } else {
        current.outcome = 'failed';
        error.value = `${typeof data.message === 'string' ? data.message : 'Resposta interrompida.'} (${String(data.code ?? 'local_model_error')})`;
        state.value = '';
      }
    });
  } catch (failure) {
    if (generation === epoch && !request.signal.aborted) {
      current.outcome = 'failed';
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
  <div class="page-heading">
    <div>
      <span class="eyebrow">CONTEXTO DO SEU EQUIPAMENTO</span>
      <h1>Assistente local</h1>
      <p class="muted">
        Converse sobre as observações e estimativas do ar-condicionado.
      </p>
    </div>
    <span class="environment-badge">OLLAMA · CPU · SEM NUVEM</span>
  </div>
  <p class="notice">
    O assistente recebe um resumo agregado, não séries brutas. As respostas
    podem conter erros. Nenhuma resposta executa comandos no equipamento.
    Durante treino ou geração de dados, o recurso fica temporariamente
    indisponível.
  </p>
  <label for="assistant-device">Equipamento da conversa</label
  ><select id="assistant-device" v-model="selected" :disabled="busy">
    <option v-for="device in devices" :key="device.id" :value="device.id">
      {{ device.name }} · {{ device.zone }}
    </option>
  </select>
  <p v-if="!devices.length" role="status">
    Aguardando dispositivos autorizados.
  </p>
  <section class="conversation" aria-label="Conversa com assistente local">
    <p v-if="!turns.length" class="card assistant-empty">
      Pergunte, por exemplo: “O que os dados atuais dizem sobre o compressor?”
    </p>
    <article
      v-for="turn in turns"
      :key="turn.id"
      class="card turn"
      :data-turn-outcome="turn.outcome"
    >
      <h2>Sua pergunta</h2>
      <p class="question">{{ turn.question }}</p>
      <h3>Assistente · {{ turn.model }}</h3>
      <!-- Only safeMarkdown generates markup: HTML and images are disabled, links restricted. -->
      <div
        class="markdown"
        data-testid="assistant-answer"
        v-html="safeMarkdown(turn.answer)"
      />
      <p v-if="!turn.answer" class="muted">
        {{
          turn.outcome === 'streaming'
            ? 'Aguardando o primeiro fragmento…'
            : 'Nenhuma resposta foi concluída.'
        }}
      </p>
      <p
        v-if="turn.outcome === 'cancelled' || turn.outcome === 'failed'"
        class="notice"
      >
        Resposta parcial ou indisponível; não foi concluída.
      </p>
      <p v-if="turn.firstToken != null" class="muted">
        Primeiro fragmento: {{ (turn.firstToken / 1000).toFixed(2) }} s.
      </p>
      <details v-if="turn.summary">
        <summary>Dados usados nesta resposta</summary>
        <p>
          Resumo montado pelo backend no momento da geração. A idade permanece
          referenciada ao horário UTC registrado.
        </p>
        <pre>{{ JSON.stringify(turn.summary, null, 2) }}</pre>
      </details>
    </article>
  </section>
  <form class="card question-form" @submit.prevent="send">
    <label for="assistant-question">Pergunta sobre o equipamento</label
    ><textarea
      id="assistant-question"
      v-model="question"
      rows="3"
      maxlength="2000"
      :disabled="busy"
      required
      aria-describedby="assistant-limits"
    />
    <p id="assistant-limits" class="muted">
      Até 2.000 caracteres, sujeito ao orçamento do contexto local. Até dois
      turnos recentes, limitados, podem ser usados. Limite de cinco perguntas
      por minuto por usuário.
    </p>
    <div class="chat-actions">
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
        Cancelar resposta
      </button>
    </div>
    <p v-if="state" role="status">{{ state }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
  </form>
</template>
<style scoped>
select {
  max-width: 420px;
  margin-bottom: 1rem;
}
.conversation {
  display: grid;
  gap: 1rem;
  margin: 1rem 0;
}
.turn,
.assistant-empty,
.question-form {
  padding: 1.4rem;
}
.turn h2 {
  font-size: 0.85rem;
  color: #5e727c;
}
.turn h3 {
  font-size: 0.9rem;
  margin: 1.4rem 0 0.8rem;
}
.question {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.markdown {
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.markdown :deep(pre),
details pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f0f5f5;
  padding: 0.8rem;
  border-radius: 8px;
}
details {
  margin-top: 1rem;
  font-size: 0.85rem;
}
summary {
  cursor: pointer;
}
textarea {
  width: 100%;
  resize: vertical;
  min-height: 100px;
  border: 1px solid #cad7dc;
  border-radius: 9px;
  padding: 0.9rem;
  font: inherit;
}
textarea:focus-visible {
  outline: 3px solid #1e8e80;
  outline-offset: 3px;
}
.question-form .muted {
  font-size: 0.8rem;
  line-height: 1.6;
}
.chat-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem;
  margin: 1rem 0;
}
</style>
