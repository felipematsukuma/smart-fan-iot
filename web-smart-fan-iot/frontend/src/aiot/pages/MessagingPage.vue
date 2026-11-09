<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
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
    const [stats, journal] = await Promise.all([
      api<Snapshot>('/messaging', { signal: request.signal }),
      refreshJournal
        ? api<FailurePage>('/messaging/failures', { signal: request.signal })
        : Promise.resolve(null),
    ]);
    if (disposed) return;
    snapshot.value = stats;
    if (journal) {
      failures.value = journal.items;
      cursor.value = journal.next_cursor;
    }
    error.value = '';
    stale.value = false;
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
      failures.value = [...failures.value, ...result.items].slice(0, 200);
      cursor.value = result.next_cursor;
    }
  } catch (failure) {
    error.value =
      failure instanceof Error
        ? failure.message
        : 'Falha ao consultar journal.';
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function replay(failure: Failure) {
  replaying.value = failure.id;
  notice.value = '';
  const key = requests.get(failure.id) ?? crypto.randomUUID();
  requests.set(failure.id, key);
  try {
    await api(`/messaging/failures/${failure.id}/replay`, {
      method: 'POST',
      body: JSON.stringify({ request_id: key }),
    });
    if (!disposed) {
      notice.value =
        'Reprocessamento solicitado ao gravador. Bytes e horário originais preservados; a falha continua no journal.';
      await load();
    }
  } catch (problem) {
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
  clearTimeout(timer);
  controller?.abort();
});
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">TRANSPORTE E RECUPERAÇÃO</p>
      <h1>Mensageria</h1>
      <p>
        Filas RabbitMQ via API do backend. Atualização a cada cinco segundos.
      </p>
    </div>
    <button class="button secondary" :disabled="busy" @click="load()">
      Atualizar mensageria
    </button>
  </div>
  <p v-if="error" role="alert" class="error-box">{{ error }}</p>
  <p v-if="notice" role="status">{{ notice }}</p>
  <p v-if="busy && !snapshot" role="status">Consultando broker e journal…</p>
  <p v-if="stale && snapshot" role="status">
    Dados antigos: a última consulta falhou. Contadores abaixo não representam o
    estado atual.
  </p>
  <section class="card" :aria-busy="busy">
    <div class="section-heading">
      <h2>Filas e consumidores</h2>
      <small v-if="snapshot"
        >Observado em
        {{ new Date(snapshot.sampled_at).toLocaleString('pt-BR') }}</small
      >
    </div>
    <div v-if="snapshot" class="table-scroll">
      <table>
        <caption>
          Mensagens prontas aguardam consumidor; em processamento ainda não
          receberam ACK. Taxas por segundo informadas pelo broker.
        </caption>
        <thead>
          <tr>
            <th>Fila</th>
            <th>Prontas</th>
            <th>Em processamento</th>
            <th>Consumidores</th>
            <th>Entrada/s</th>
            <th>Entrega/s</th>
            <th>Durabilidade</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="queue in snapshot.queues"
            :key="queue.name"
            :data-queue="queue.name"
            :data-ready="queue.messages_ready"
            :data-consumers="queue.consumers"
          >
            <td>
              {{ queue.name }}<br /><small>{{ queue.consumer_service }}</small>
            </td>
            <td>{{ queue.messages_ready }}</td>
            <td>{{ queue.messages_unacknowledged }}</td>
            <td>{{ queue.consumers }}</td>
            <td>
              {{
                queue.publish_rate.toLocaleString('pt-BR', {
                  maximumFractionDigits: 1,
                })
              }}
            </td>
            <td>
              {{
                queue.delivery_rate.toLocaleString('pt-BR', {
                  maximumFractionDigits: 1,
                })
              }}
            </td>
            <td>
              {{ queue.durable ? 'Durável' : 'Não durável' }} ·
              {{ queue.type }} · {{ queue.state }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else-if="!busy" class="table-message">
      Sem snapshot disponível do broker.
    </p>
  </section>
  <section class="card journal" :aria-busy="busy">
    <div class="section-heading"><h2>Falhas e prévias da DLQ</h2></div>
    <p class="explanation">
      Prévia do journal durável, limitada às 200 falhas mais recentes por
      serviço. Consultar não retira mensagens da DLQ. O contador da DLQ pode
      diferir do journal. Nenhum payload bruto ou credencial é exibido.
    </p>
    <p class="explanation">
      Somente telemetria original com falha terminal no gravador pode voltar à
      sua inbox. Máximo três solicitações, intervalo de 30 segundos; comandos
      físicos não são reprocessados. Reprocessar mantém deduplicação, identidade
      e horário da fonte.
    </p>
    <p v-if="!failures.length" class="table-message">
      Nenhuma falha no journal consultado.
    </p>
    <div v-else class="table-scroll">
      <table>
        <caption>
          Tipo, produtor e dispositivo são apresentados somente após validação
          do contrato.
        </caption>
        <thead>
          <tr>
            <th>Falha e serviço</th>
            <th>Motivo</th>
            <th>Prévia validada</th>
            <th>Entrega</th>
            <th>Recuperação</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="failure in failures" :key="failure.id">
            <td>
              {{ failure.id }}<br /><small
                >{{ failure.owner }} ·
                {{
                  new Date(failure.created_at).toLocaleString('pt-BR')
                }}</small
              >
            </td>
            <td>
              {{ failure.reason_code }}<br />{{ failure.attempts }} tentativas
            </td>
            <td>
              <template v-if="failure.preview.type"
                >{{ failure.preview.type }}<br />{{
                  failure.preview.producer
                }}
                · {{ failure.preview.device_id ?? 'Sem dispositivo autorizado'
                }}<br /><small>{{ failure.preview.timestamp }}</small></template
              ><span v-else
                >Payload inválido ou não reconhecido; conteúdo omitido.</span
              >
            </td>
            <td>{{ failure.delivery_state ?? 'Quarentena sem inbox' }}</td>
            <td>
              <button
                v-if="failure.can_replay"
                class="button secondary"
                :disabled="!!replaying"
                @click="replay(failure)"
              >
                Reprocessar telemetria</button
              ><span v-else>Sem replay elegível</span><br /><small
                >{{ failure.replay_count }} solicitações</small
              >
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
  </section>
</template>
<style scoped>
.journal {
  margin-top: 1.5rem;
}
.explanation {
  padding: 0 1.4rem;
  font-size: 0.85rem;
  line-height: 1.6;
}
caption {
  padding: 1rem;
  text-align: left;
  font-size: 0.8rem;
}
td {
  overflow-wrap: anywhere;
}
td:first-child {
  max-width: 250px;
}
</style>
