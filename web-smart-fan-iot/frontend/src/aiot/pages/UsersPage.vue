<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { Plus, Pencil, RefreshCw } from 'lucide-vue-next';
import { api, currentUser, clearSession, type Role } from '../auth';

interface Account {
  id: string;
  username: string;
  role: Role;
  enabled: boolean;
}
const accounts = ref<Account[]>([]);
const busy = ref(false);
const saving = ref(false);
const error = ref('');
const notice = ref('');
const username = ref('');
const password = ref('');
const role = ref<Role>('visualizador');
const enabled = ref(true);
const editing = ref<string | null>(null);
const cursor = ref<string | null>(null);
const nextCursor = ref<string | null>(null);
const previous = ref<(string | null)[]>([]);

async function load(next: string | null = cursor.value) {
  busy.value = true;
  error.value = '';
  try {
    const page = await api<{ items: Account[]; next_cursor: string | null }>(
      `/users?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ''}`,
    );
    accounts.value = page.items;
    nextCursor.value = page.next_cursor;
    cursor.value = next;
  } catch (failure) {
    error.value =
      failure instanceof Error
        ? failure.message
        : 'Falha ao carregar usuários.';
  } finally {
    busy.value = false;
  }
}
function reset() {
  editing.value = null;
  username.value = '';
  password.value = '';
  role.value = 'visualizador';
  enabled.value = true;
}
function edit(account: Account) {
  editing.value = account.id;
  username.value = account.username;
  role.value = account.role;
  enabled.value = account.enabled;
  password.value = '';
  document.getElementById('account-username')?.focus();
}
async function save() {
  if (new TextEncoder().encode(password.value).length > 72) {
    error.value = 'Esta senha é muito longa. Use menos caracteres.';
    password.value = '';
    return;
  }
  saving.value = true;
  error.value = '';
  notice.value = '';
  try {
    if (editing.value) {
      await api<void>(`/users/${editing.value}`, {
        method: 'PATCH',
        body: JSON.stringify({
          role: role.value,
          enabled: enabled.value,
          ...(password.value ? { password: password.value } : {}),
        }),
      });
      if (editing.value === currentUser.value?.id) {
        clearSession('Conta atualizada. Entre novamente.');
        return;
      }
    } else {
      await api<Account>('/users', {
        method: 'POST',
        body: JSON.stringify({
          username: username.value,
          password: password.value,
          role: role.value,
        }),
      });
    }
    notice.value =
      'Conta salva. Alterações de acesso encerram as sessões anteriores.';
    reset();
    previous.value = [];
    await load(null);
  } catch (failure) {
    error.value =
      failure instanceof Error ? failure.message : 'Não foi possível salvar.';
  } finally {
    password.value = '';
    saving.value = false;
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
      <span class="eyebrow">ADMINISTRAÇÃO</span>
      <h1>Usuários</h1>
      <p class="muted">Controle quem pode visualizar, operar e administrar.</p>
    </div>
    <button class="button secondary" :disabled="busy" @click="load()">
      <RefreshCw :size="16" />Atualizar
    </button>
  </div>
  <p v-if="error" class="error-box" role="alert">{{ error }}</p>
  <p v-if="notice" class="notice" role="status">{{ notice }}</p>
  <div class="admin-grid">
    <section class="card table-card" :aria-busy="busy">
      <div class="section-heading">
        <h2>Contas de acesso</h2>
        <span class="muted">{{
          busy ? 'Carregando…' : `${accounts.length} nesta página`
        }}</span>
      </div>
      <p v-if="busy" class="table-message" role="status">
        Carregando usuários…
      </p>
      <p v-else-if="!accounts.length" class="table-message">
        Nenhum usuário encontrado.
      </p>
      <div v-else class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Usuário</th>
              <th>Papel</th>
              <th>Estado</th>
              <th><span class="sr-only">Ações</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="account in accounts" :key="account.id">
              <td>
                <strong>{{ account.username }}</strong>
              </td>
              <td>{{ account.role }}</td>
              <td>
                <span
                  class="status-pill"
                  :class="account.enabled ? 'positive' : 'neutral'"
                  >{{ account.enabled ? 'Ativo' : 'Inativo' }}</span
                >
              </td>
              <td>
                <button
                  class="icon-button"
                  :aria-label="`Editar ${account.username}`"
                  @click="edit(account)"
                >
                  <Pencil :size="16" />
                </button>
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
    <form class="card account-form" :aria-busy="saving" @submit.prevent="save">
      <div class="section-heading">
        <h2>{{ editing ? 'Editar acesso' : 'Nova conta' }}</h2>
        <Plus v-if="!editing" :size="18" />
      </div>
      <label for="account-username">Usuário</label
      ><input
        id="account-username"
        v-model.trim="username"
        autocomplete="off"
        required
        pattern="[A-Za-z0-9_-]+"
        maxlength="64"
        :readonly="!!editing"
        :disabled="saving"
      />
      <label for="account-role">Papel</label
      ><select id="account-role" v-model="role" :disabled="saving">
        <option value="visualizador">Visualizador</option>
        <option value="operador">Operador</option>
        <option value="administrador">Administrador</option>
      </select>
      <p class="field-help">
        Visualizador acompanha. Operador comanda. Administrador configura e
        gerencia.
      </p>
      <label for="account-password">{{
        editing ? 'Nova senha (opcional)' : 'Senha inicial'
      }}</label
      ><input
        id="account-password"
        v-model="password"
        type="password"
        autocomplete="new-password"
        :required="!editing"
        minlength="12"
        maxlength="72"
        :disabled="saving"
      />
      <p class="field-help">
        Use ao menos 12 caracteres. A senha não pode ser consultada depois.
      </p>
      <label v-if="editing" class="checkbox-label"
        ><input v-model="enabled" type="checkbox" :disabled="saving" />Conta
        ativa</label
      >
      <button class="button primary" type="submit" :disabled="saving">
        {{ saving ? 'Salvando…' : 'Salvar conta' }}</button
      ><button
        v-if="editing"
        class="button secondary"
        type="button"
        :disabled="saving"
        @click="reset"
      >
        Cancelar edição
      </button>
    </form>
  </div>
</template>
