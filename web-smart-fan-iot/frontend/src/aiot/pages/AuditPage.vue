<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { RefreshCw } from 'lucide-vue-next';
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
const actions: Record<string, string> = {
  'auth.login': 'Entrada na conta',
  'auth.login_failed': 'Tentativa de acesso',
  'auth.logout': 'Saída da conta',
  'auth.ws_ticket': 'Conexão em tempo real',
  'auth.rate_limited': 'Limite de tentativas',
  'user.created': 'Conta criada',
  'user.updated': 'Acesso atualizado',
  'user.bootstrap': 'Conta inicial criada',
  'user.hash_policy': 'Política de senha atualizada',
};
const busy = ref(false);
const error = ref('');
const cursor = ref<string | null>(null);
const nextCursor = ref<string | null>(null);
const previous = ref<(string | null)[]>([]);
async function load(next: string | null = cursor.value) {
  busy.value = true;
  error.value = '';
  try {
    const result = await api<{ items: Entry[]; next_cursor: string | null }>(
      `/audit?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ''}`,
    );
    entries.value = result.items;
    nextCursor.value = result.next_cursor;
    cursor.value = next;
  } catch (failure) {
    error.value =
      failure instanceof Error
        ? failure.message
        : 'Não foi possível carregar a auditoria.';
  } finally {
    busy.value = false;
  }
}
function forward() {
  previous.value.push(cursor.value);
  void load(nextCursor.value);
}
function back() {
  void load(previous.value.pop() ?? null);
}
onMounted(() => void load());
</script>

<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">RASTREABILIDADE</span>
      <h1>Auditoria</h1>
      <p class="muted">
        Histórico de acessos e alterações, com identificação de cada operação.
      </p>
    </div>
    <button class="button secondary" :disabled="busy" @click="load()">
      <RefreshCw :size="16" />Atualizar
    </button>
  </div>
  <p v-if="error" class="error-box" role="alert">{{ error }}</p>
  <section class="card table-card" :aria-busy="busy">
    <p v-if="busy" class="table-message" role="status">Carregando auditoria…</p>
    <p v-else-if="!entries.length" class="table-message">
      Nenhuma operação registrada.
    </p>
    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Quando</th>
            <th>Operação</th>
            <th>Quem</th>
            <th>Resultado</th>
            <th>Referência</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.id">
            <td class="nowrap">
              {{ new Date(entry.created_at).toLocaleString('pt-BR') }}
            </td>
            <td>
              <strong>{{ actions[entry.action] ?? entry.action }}</strong
              ><small class="table-detail">{{ entry.entity_type }}</small>
            </td>
            <td>
              {{
                entry.actor_username ??
                (entry.action.startsWith('user.')
                  ? 'Sistema'
                  : 'Não autenticado')
              }}
            </td>
            <td>
              <span
                class="status-pill"
                :class="entry.outcome === 'success' ? 'positive' : 'neutral'"
                >{{
                  entry.outcome === 'success' ? 'Concluída' : 'Negada'
                }}</span
              >
            </td>
            <td>
              <code class="correlation">{{ entry.correlation_id }}</code>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <button
        class="button secondary"
        :disabled="!previous.length || busy"
        @click="back"
      >
        Anterior</button
      ><button
        class="button secondary"
        :disabled="!nextCursor || busy"
        @click="forward"
      >
        Próxima
      </button>
    </div>
  </section>
</template>
