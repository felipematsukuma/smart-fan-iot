<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from 'reka-ui';
import { Card, Badge } from '../ui/primitives';
import IdentifierDetails from '../components/IdentifierDetails.vue';
import { shortId, jobDate } from '../job-presentation';
import {
  queueLabels,
  eventLabels,
  reasonLabels,
  messagingStale,
} from '../operations-presentation';
import '../ui/task-page.css';
import '../ui/operations-pages.css';
import { api } from '../auth';
interface Queue {
  name: string;
  consumer_service: string;
  messages_ready: number;
  messages_unacknowledged: number;
  consumers: number;
  publish_rate: number;
  delivery_rate: number;
  durable: boolean;
  type: string;
  state: string;
}
interface Snapshot {
  sampled_at: string;
  source: string;
  cache_seconds: number;
  queues: Queue[];
  recent_messages?: {
    items: {
      id: string;
      type: string;
      producer: string;
      device_id: string | null;
      timestamp: string;
      received_at: string;
      queue: string;
    }[];
    note: string;
  };
}
interface Failure {
  id: string;
  source_event_id: string;
  owner: string;
  reason_code: string;
  attempts: number;
  created_at: string;
  delivery_state: string | null;
  preview: Record<string, string | null>;
  can_replay: boolean;
  replay_count: number;
}
interface FailurePage {
  items: Failure[];
  next_cursor: string | null;
  note: string;
}
const snapshot = ref<Snapshot | null>(null);
const failures = ref<Failure[]>([]);
const cursor = ref<string | null>(null);
const busy = ref(false);
const error = ref('');
const notice = ref('');
const replaying = ref('');
const stale = ref(false);
const journalError = ref('');
const journalLoaded = ref(false);
const journalAt = ref('');
const now = ref(Date.now());
const clock = setInterval(() => {
  now.value = Date.now();
}, 1000);
const outdated = computed(
  () =>
    stale.value ||
    (!!snapshot.value &&
      messagingStale(
        snapshot.value.sampled_at,
        snapshot.value.cache_seconds,
        now.value,
      )),
);
const workQueues = computed(
  () => snapshot.value?.queues.filter((q) => q.name !== 'q.dlq') ?? [],
);
const dlq = computed(() =>
  snapshot.value?.queues.find((q) => q.name === 'q.dlq'),
);
const confirmOpen = ref(false);
const pending = ref<Failure | null>(null);
const noticeError = ref(false);
let expandedJournal = false;
function askReplay(failure: Failure) {
  pending.value = failure;
  confirmOpen.value = true;
}
async function confirmReplay() {
  if (pending.value?.can_replay) await replay(pending.value);
  confirmOpen.value = false;
}
const rate = (value: number) =>
  value.toLocaleString('pt-BR', { maximumFractionDigits: 1 });
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let controller: AbortController | undefined;
const requests = new Map<string, string>();
async function load(refreshJournal = true) {
  clearTimeout(timer);
  if (busy.value) {
    timer = setTimeout(() => void load(refreshJournal), 500);
    return;
  }
  busy.value = true;
  const request = new AbortController();
  controller = request;
  try {
    const [stats, journal] = await Promise.allSettled([
      api<Snapshot>('/messaging', { signal: request.signal }),
      refreshJournal
        ? api<FailurePage>('/messaging/failures', { signal: request.signal })
        : Promise.resolve(null),
    ]);
    if (disposed) return;
    if (stats.status === 'fulfilled') {
      snapshot.value = stats.value;
      error.value = '';
      stale.value = false;
    } else {
      error.value =
        stats.reason instanceof Error
          ? stats.reason.message
          : 'Falha ao consultar filas.';
      stale.value = true;
    }
    if (journal.status === 'fulfilled' && journal.value) {
      const page = journal.value;
      const incoming = new Set(page.items.map((item) => item.id));
      failures.value = expandedJournal
        ? [
            ...page.items,
            ...failures.value.filter((item) => !incoming.has(item.id)),
          ].slice(0, 200)
        : page.items;
      if (!expandedJournal) cursor.value = page.next_cursor;
      journalLoaded.value = true;
      journalError.value = '';
      journalAt.value = new Date().toISOString();
    } else if (journal.status === 'rejected')
      journalError.value = 'Falha ao consultar o registro de falhas.';
  } catch (failure) {
    if (!disposed && !request.signal.aborted) {
      error.value =
        failure instanceof Error ? failure.message : 'Mensageria indisponível.';
      stale.value = true;
    }
  } finally {
    if (!disposed) {
      busy.value = false;
      timer = setTimeout(() => void load(false), 5000);
    }
  }
}
async function more() {
  if (!cursor.value) return;
  busy.value = true;
  try {
    const result = await api<FailurePage>(
      `/messaging/failures?before=${cursor.value}`,
    );
    if (!disposed) {
      const known = new Set(failures.value.map((item) => item.id));
      failures.value = [
        ...failures.value,
        ...result.items.filter((item) => !known.has(item.id)),
      ].slice(0, 200);
      expandedJournal = true;
      cursor.value = result.next_cursor;
    }
  } catch (failure) {
    journalError.value =
      failure instanceof Error
        ? failure.message
        : 'Falha ao consultar registro de falhas.';
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function replay(failure: Failure) {
  replaying.value = failure.id;
  notice.value = '';
  noticeError.value = false;
  const key = requests.get(failure.id) ?? crypto.randomUUID();
  requests.set(failure.id, key);
  try {
    const result = await api<{ status: string }>(
      `/messaging/failures/${failure.id}/replay`,
      {
        method: 'POST',
        body: JSON.stringify({ request_id: key }),
      },
    );
    if (!disposed) {
      notice.value =
        result.status === 'already_requested'
          ? 'Solicitação já registrada; execução ainda não confirmada.'
          : 'Reprocessamento solicitado ao gravador; execução ainda não confirmada.';
      await load();
    }
  } catch (problem) {
    noticeError.value = true;
    if (!disposed)
      notice.value =
        problem instanceof Error
          ? problem.message
          : 'Não foi possível solicitar reprocessamento.';
  } finally {
    if (!disposed) replaying.value = '';
  }
}
onMounted(() => void load());
onBeforeUnmount(() => {
  disposed = true;
  clearInterval(clock);
  clearTimeout(timer);
  controller?.abort();
});
</script>
<template>
  <div class="task-page operations-page messaging-page">
    <header class="tp-heading">
      <h1>Mensageria</h1>
      <button class="button secondary" :disabled="busy" @click="load()">
        Atualizar mensageria
      </button>
    </header>
    <p v-if="error" role="alert" class="tp-field-error">{{ error }}</p>
    <p
      v-if="notice"
      :role="noticeError ? 'alert' : 'status'"
      :class="{ 'tp-field-error': noticeError }"
    >
      {{ notice }}
    </p>
    <Card class="tp-card" :aria-busy="busy && !snapshot">
      <div class="tp-section-heading">
        <h2>Filas e consumidores</h2>
        <Badge v-if="snapshot" :tone="outdated ? 'warning' : 'good'">{{
          outdated ? 'Dados desatualizados' : 'Consulta atualizada'
        }}</Badge>
      </div>
      <p v-if="snapshot" class="tp-muted">
        Última atualização às
        {{ new Date(snapshot.sampled_at).toLocaleTimeString('pt-BR') }}
      </p>
      <p v-if="outdated && snapshot" role="status">
        Os contadores preservados não representam o estado atual.
      </p>
      <p v-if="!snapshot">
        {{ busy ? 'Consultando filas…' : 'Sem dados das filas disponíveis.' }}
      </p>
      <div v-if="snapshot" class="tp-table ops-table">
        <table>
          <thead>
            <tr>
              <th>Fila</th>
              <th>Pendentes (mensagens)</th>
              <th>Em processamento</th>
              <th>Consumidores</th>
              <th>Entrada (msg/s)</th>
              <th>Entrega (msg/s)</th>
              <th>Detalhes</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="queue in workQueues"
              :key="queue.name"
              :data-queue="queue.name"
              :data-ready="queue.messages_ready"
              :data-consumers="queue.consumers"
            >
              <td data-label="Fila">
                <strong>{{ queueLabels[queue.name] ?? queue.name }}</strong>
                <div class="queue-state">
                  <Badge v-if="queue.state !== 'running'" tone="danger"
                    >Fila indisponível</Badge
                  ><Badge v-else-if="!queue.consumers" tone="warning"
                    >Consumidor ausente</Badge
                  ><Badge
                    v-else-if="
                      !queue.messages_ready && !queue.messages_unacknowledged
                    "
                    >Fila vazia</Badge
                  ><Badge v-else>Mensagens em trânsito</Badge>
                </div>
              </td>
              <td data-label="Pendentes (mensagens)">
                {{ queue.messages_ready }}
              </td>
              <td data-label="Em processamento">
                {{ queue.messages_unacknowledged }}
              </td>
              <td data-label="Consumidores">{{ queue.consumers }}</td>
              <td data-label="Entrada (msg/s)">
                {{ rate(queue.publish_rate) }}
              </td>
              <td data-label="Entrega (msg/s)">
                {{ rate(queue.delivery_rate) }}
              </td>
              <td class="queue-details">
                <details>
                  <summary>Detalhes da fila</summary>
                  <dl class="tp-definition">
                    <dt>Nome</dt>
                    <dd>{{ queue.name }}</dd>
                    <dt>Serviço</dt>
                    <dd>{{ queue.consumer_service }}</dd>
                    <dt>Tipo / estado</dt>
                    <dd>{{ queue.type }} / {{ queue.state }}</dd>
                    <dt>Persistência</dt>
                    <dd>{{ queue.durable ? 'Durável' : 'Não durável' }}</dd>
                  </dl>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <details v-if="snapshot">
        <summary>Sobre os contadores</summary>
        <p>
          Pendentes aguardam entrega; em processamento aguardam confirmação do
          consumidor. Taxas em mensagens por segundo.
        </p>
        <p>
          Fonte: {{ snapshot.source }} · cache de
          {{ snapshot.cache_seconds }} s.
        </p>
      </details>
    </Card>
    <Card class="tp-card recent-messages"
      ><h2>Mensagens recentes</h2>
      <p v-if="!snapshot?.recent_messages">Prévia de mensagens indisponível.</p>
      <p v-else-if="!snapshot.recent_messages.items.length">
        Nenhuma mensagem observada nesta sessão da API.
      </p>
      <div
        v-else
        class="tp-table ops-table bounded-records"
        tabindex="0"
        role="region"
        aria-label="Mensagens recentes"
      >
        <table>
          <thead>
            <tr>
              <th>Recebida em</th>
              <th>Evento</th>
              <th>Dispositivo</th>
              <th>Detalhes</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in snapshot.recent_messages.items" :key="item.id">
              <td data-label="Recebida em">
                {{ new Date(item.received_at).toLocaleString('pt-BR') }}
              </td>
              <td data-label="Evento">
                {{ eventLabels[item.type] ?? 'Outro evento' }}
              </td>
              <td data-label="Dispositivo">{{ item.device_id ?? 'Global' }}</td>
              <td>
                <details>
                  <summary>Detalhes da mensagem</summary>
                  <IdentifierDetails :value="item.id" />
                  <p>
                    Tipo: {{ item.type }} · produtor: {{ item.producer }} ·
                    fila: {{ item.queue }}
                  </p>
                  <p>
                    Origem:
                    {{ new Date(item.timestamp).toLocaleString('pt-BR') }}
                  </p>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <details>
        <summary>Sobre as prévias</summary>
        <p>
          Até 100 metadados por cinco minutos, sem conteúdo bruto. Consultar
          esta página não consome mensagens das filas de trabalho.
        </p>
        <p v-if="snapshot?.recent_messages">
          {{ snapshot.recent_messages.note }}
        </p>
      </details>
    </Card>
    <Card class="tp-card journal"
      ><div class="tp-section-heading">
        <h2>Falhas e DLQ</h2>
        <Badge v-if="dlq" :tone="dlq.messages_ready ? 'warning' : 'neutral'"
          >{{ dlq.messages_ready }} mensagens pendentes na DLQ</Badge
        >
      </div>
      <details v-if="dlq">
        <summary>Estatísticas da DLQ</summary>
        <dl class="tp-definition">
          <dt>Nome</dt>
          <dd>{{ dlq.name }}</dd>
          <dt>Pendentes</dt>
          <dd>{{ dlq.messages_ready }} mensagens</dd>
          <dt>Em processamento</dt>
          <dd>{{ dlq.messages_unacknowledged }} mensagens</dd>
          <dt>Consumidores</dt>
          <dd>{{ dlq.consumers }}</dd>
          <dt>Entrada / entrega</dt>
          <dd>
            {{ rate(dlq.publish_rate) }} / {{ rate(dlq.delivery_rate) }} msg/s
          </dd>
          <dt>Serviço</dt>
          <dd>{{ dlq.consumer_service }}</dd>
          <dt>Tipo / estado</dt>
          <dd>{{ dlq.type }} / {{ dlq.state }}</dd>
          <dt>Persistência</dt>
          <dd>{{ dlq.durable ? 'Durável' : 'Não durável' }}</dd>
        </dl>
      </details>
      <p v-if="journalAt" class="tp-muted">
        Registro consultado em {{ new Date(journalAt).toLocaleString('pt-BR') }}
      </p>
      <p v-if="journalError" role="alert" class="tp-field-error">
        {{ journalError
        }}{{ journalLoaded ? ' Registros anteriores preservados.' : '' }}
      </p>
      <p v-if="!journalLoaded && !journalError">Consultando falhas…</p>
      <p v-else-if="journalLoaded && !failures.length && !journalError">
        Nenhuma falha no registro consultado.
      </p>
      <div
        v-if="failures.length"
        class="tp-table ops-table bounded-records"
        tabindex="0"
        role="region"
        aria-label="Falhas registradas"
      >
        <table>
          <thead>
            <tr>
              <th>Data / serviço</th>
              <th>Motivo</th>
              <th>Entrega</th>
              <th>Recuperação</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="failure in failures"
              :key="failure.id"
              :data-failure-id="failure.id"
            >
              <td data-label="Data / serviço">
                {{ jobDate(failure.created_at) }}
                <p>{{ failure.owner }}</p>
              </td>
              <td data-label="Motivo">
                {{
                  reasonLabels[failure.reason_code] ??
                  'Motivo não traduzido; consulte os detalhes'
                }}
              </td>
              <td data-label="Entrega">
                {{
                  failure.delivery_state === 'failed'
                    ? 'Falhou'
                    : failure.delivery_state === 'completed'
                      ? 'Concluída'
                      : failure.delivery_state === 'pending'
                        ? 'Pendente'
                        : (failure.delivery_state ?? 'Quarentena sem inbox')
                }}
              </td>
              <td>
                <button
                  v-if="failure.can_replay"
                  class="button secondary"
                  :disabled="!!replaying"
                  @click="askReplay(failure)"
                >
                  Reprocessar telemetria</button
                ><span v-else>Reprocessamento indisponível</span>
                <p class="tp-muted">{{ failure.replay_count }} solicitações</p>
                <details>
                  <summary>Detalhes da falha</summary>
                  <IdentifierDetails
                    :value="failure.id"
                    label="Identificação da falha"
                  /><IdentifierDetails
                    :value="failure.source_event_id"
                    label="Evento original"
                  />
                  <p>
                    Código: {{ failure.reason_code }} ·
                    {{ failure.attempts }} tentativas
                  </p>
                  <p v-if="failure.preview.type">
                    {{ failure.preview.type }} ·
                    {{ failure.preview.producer }} ·
                    {{
                      failure.preview.device_id ?? 'Dispositivo não disponível'
                    }}
                  </p>
                  <p v-if="failure.preview.timestamp">
                    Horário de origem: {{ failure.preview.timestamp }}
                  </p>
                  <p v-if="!failure.preview.type">
                    Prévia indisponível; conteúdo omitido.
                  </p>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <button
        v-if="cursor && failures.length < 200"
        class="button secondary"
        :disabled="busy"
        @click="more"
      >
        Mais falhas
      </button>
      <details>
        <summary>Restrições de recuperação</summary>
        <p>
          Registro durável limitado a 200 falhas. O total pode diferir da DLQ. A
          consulta não retira mensagens de nenhuma fila.
        </p>
        <p>
          Somente telemetria original com falha terminal no gravador é elegível.
          Até três solicitações, com intervalo de 30 segundos. Comandos físicos
          não são reprocessados. Identidade, horário e deduplicação são
          preservados.
        </p>
      </details>
    </Card>
  </div>
  <DialogRoot v-model:open="confirmOpen"
    ><DialogPortal
      ><DialogOverlay class="ops-confirm-overlay" /><DialogContent
        class="ops-confirm"
        ><DialogTitle>Confirmar reprocessamento</DialogTitle
        ><DialogDescription
          >Solicitar nova tentativa para a telemetria
          {{ pending ? shortId(pending.id) : '' }}? A solicitação não confirma a
          execução nem remove a falha do registro. O servidor mantém os limites
          de elegibilidade e intervalo.</DialogDescription
        >
        <div class="tp-actions">
          <DialogClose class="button secondary" :disabled="!!replaying"
            >Cancelar</DialogClose
          ><button
            class="button primary"
            :disabled="!!replaying"
            @click="confirmReplay"
          >
            {{ replaying ? 'Solicitando…' : 'Confirmar reprocessamento' }}
          </button>
        </div></DialogContent
      ></DialogPortal
    ></DialogRoot
  >
</template>
