<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { RefreshCw } from 'lucide-vue-next';
import { Card, Badge } from '../ui/primitives';
import IdentifierDetails from '../components/IdentifierDetails.vue';
import { shortId } from '../job-presentation';
import {
  actionLabels,
  outcomeLabels,
  entityLabels,
} from '../operations-presentation';
import '../ui/task-page.css';
import '../ui/operations-pages.css';
import { api } from '../auth';

interface Entry {
  id: string;
  created_at: string;
  action: string;
  actor_username: string | null;
  entity_type: string;
  entity_id: string | null;
  outcome: string;
  correlation_id: string;
}
const entries = ref<Entry[]>([]);
const busy = ref(false);
const error = ref('');
const cursor = ref<string | null>(null);
const nextCursor = ref<string | null>(null);
const previous = ref<(string | null)[]>([]);
let disposed = false;
let controller: AbortController | undefined;
const loaded = ref(false);
async function load(next: string | null = cursor.value) {
  if (busy.value) return false;
  busy.value = true;
  const request = new AbortController();
  controller = request;
  error.value = '';
  try {
    const result = await api<{ items: Entry[]; next_cursor: string | null }>(
      `/audit?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ''}`,
      { signal: request.signal },
    );
    if (disposed) return false;
    loaded.value = true;
    entries.value = result.items;
    nextCursor.value = result.next_cursor;
    cursor.value = next;
    return true;
  } catch (failure) {
    if (disposed || request.signal.aborted) return false;
    error.value =
      failure instanceof Error
        ? failure.message
        : 'Não foi possível carregar a auditoria.';
    return false;
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function forward() {
  if (!nextCursor.value || busy.value) return;
  const current = cursor.value;
  if (await load(nextCursor.value)) previous.value.push(current);
}
async function back() {
  if (!previous.value.length || busy.value) return;
  if (await load(previous.value[previous.value.length - 1] ?? null))
    previous.value.pop();
}
onBeforeUnmount(() => {
  disposed = true;
  controller?.abort();
});
onMounted(() => void load());
</script>

<template>
  <div class="task-page operations-page audit-page">
    <header class="tp-heading">
      <h1>Auditoria</h1>
      <button class="button secondary" :disabled="busy" @click="load()">
        <RefreshCw :size="16" />Atualizar
      </button>
    </header>
    <p v-if="error" class="tp-field-error" role="alert">
      {{ error
      }}<span v-if="entries.length"> Registros anteriores preservados.</span>
    </p>
    <Card class="tp-card" :aria-busy="busy">
      <p v-if="busy && !loaded" role="status">Carregando auditoria…</p>
      <p v-if="loaded && !entries.length && !error">
        {{
          cursor
            ? 'Nenhum registro nesta página.'
            : 'Nenhuma operação registrada.'
        }}
      </p>
      <p v-if="!loaded && error">Registros indisponíveis.</p>
      <div v-if="entries.length" class="tp-table ops-table">
        <table>
          <thead>
            <tr>
              <th>Data / hora</th>
              <th>Usuário</th>
              <th>Ação</th>
              <th>Recurso</th>
              <th>Resultado</th>
              <th>Detalhes</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="entry in entries"
              :key="entry.id"
              :data-audit-id="entry.id"
            >
              <td data-label="Data / hora">
                {{ new Date(entry.created_at).toLocaleString('pt-BR') }}
              </td>
              <td data-label="Usuário">
                {{
                  entry.actor_username ??
                  (entry.action.startsWith('user.')
                    ? 'Sistema'
                    : 'Não identificado')
                }}
              </td>
              <td data-label="Ação">
                <strong>{{
                  actionLabels[entry.action] ?? 'Ação não traduzida'
                }}</strong>
              </td>
              <td data-label="Recurso">
                {{ entityLabels[entry.entity_type] ?? 'Outro recurso'
                }}<small v-if="entry.entity_id" class="ops-resource">{{
                  shortId(entry.entity_id)
                }}</small>
              </td>
              <td data-label="Resultado">
                <Badge
                  :tone="
                    entry.outcome === 'success'
                      ? 'good'
                      : ['failure', 'failed', 'denied'].includes(entry.outcome)
                        ? 'danger'
                        : 'neutral'
                  "
                  >{{
                    outcomeLabels[entry.outcome] ?? 'Resultado não traduzido'
                  }}</Badge
                >
              </td>
              <td>
                <details>
                  <summary>Detalhes do registro</summary>
                  <dl class="tp-definition">
                    <dt>Ação original</dt>
                    <dd>{{ entry.action }}</dd>
                    <dt>Resultado original</dt>
                    <dd>{{ entry.outcome }}</dd>
                    <dt>Tipo de recurso</dt>
                    <dd>{{ entry.entity_type }}</dd>
                  </dl>
                  <IdentifierDetails
                    :value="entry.id"
                    label="Identificação do registro"
                  /><IdentifierDetails
                    v-if="entry.entity_id"
                    :value="entry.entity_id"
                    label="Identificação do recurso"
                  /><IdentifierDetails
                    :value="entry.correlation_id"
                    label="Correlação"
                  />
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav
        class="tp-actions ops-pagination"
        aria-label="Paginação da auditoria"
      >
        <button
          class="button secondary"
          :disabled="!previous.length || busy"
          @click="back"
        >
          Anterior</button
        ><span>Página {{ previous.length + 1 }}</span
        ><button
          class="button secondary"
          :disabled="!nextCursor || busy"
          @click="forward"
        >
          Próxima
        </button>
      </nav>
    </Card>
  </div>
</template>
