<script setup lang="ts">
import { onMounted, onBeforeUnmount, nextTick, ref } from 'vue';
import { Plus, Pencil, RefreshCw } from 'lucide-vue-next';
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
import '../ui/task-page.css';
import '../ui/account-pages.css';
import { api, ApiError, currentUser, clearSession, type Role } from '../auth';

interface Account {
  id: string;
  username: string;
  role: Role;
  enabled: boolean;
}
const accounts = ref<Account[]>([]);
const fields = ref<Record<string, string>>({});
const formError = ref('');
const confirmOpen = ref(false);
const originalEnabled = ref(true);
const loaded = ref(false);
let disposed = false;
let controller: AbortController | undefined;
const roles: Record<Role, string> = {
  visualizador: 'Visualizador',
  operador: 'Operador',
  administrador: 'Administrador',
};
function invalid(event: Event) {
  const input = event.target as HTMLInputElement;
  fields.value[input.id] = input.validationMessage;
}
function clearField(event: Event) {
  delete fields.value[(event.target as HTMLInputElement).id];
  formError.value = '';
}
async function submit() {
  fields.value = {};
  formError.value = '';
  if (new TextEncoder().encode(password.value).length > 72) {
    fields.value['account-password'] = 'Use no máximo 72 bytes em UTF-8.';
    password.value = '';
    await nextTick();
    document.getElementById('account-password')?.focus();
    return;
  }
  if (editing.value && originalEnabled.value && !enabled.value) {
    confirmOpen.value = true;
    return;
  }
  await save();
}
async function confirmDisable() {
  await save();
  confirmOpen.value = false;
}
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
  if (busy.value) return false;
  busy.value = true;
  const request = new AbortController();
  controller = request;
  error.value = '';
  try {
    const page = await api<{ items: Account[]; next_cursor: string | null }>(
      `/users?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ''}`,
      { signal: request.signal },
    );
    if (disposed) return false;
    loaded.value = true;
    accounts.value = page.items;
    nextCursor.value = page.next_cursor;
    cursor.value = next;
    return true;
  } catch (failure) {
    if (disposed || request.signal.aborted) return false;
    error.value =
      failure instanceof Error
        ? failure.message
        : 'Falha ao carregar usuários.';
    return false;
  } finally {
    if (!disposed) busy.value = false;
  }
}
function reset() {
  fields.value = {};
  formError.value = '';
  editing.value = null;
  username.value = '';
  password.value = '';
  role.value = 'visualizador';
  enabled.value = true;
}
async function edit(account: Account) {
  fields.value = {};
  formError.value = '';
  notice.value = '';
  originalEnabled.value = account.enabled;
  editing.value = account.id;
  username.value = account.username;
  role.value = account.role;
  enabled.value = account.enabled;
  password.value = '';
  await nextTick();
  document.getElementById('account-role')?.focus();
}
async function save() {
  if (new TextEncoder().encode(password.value).length > 72) {
    fields.value['account-password'] =
      'Esta senha é muito longa. Use menos caracteres.';
    password.value = '';
    return;
  }
  saving.value = true;
  formError.value = '';
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
    const wasEditing = !!editing.value;
    reset();
    if (wasEditing) await load();
    else {
      previous.value = [];
      await load(null);
    }
  } catch (failure) {
    const message =
      failure instanceof Error ? failure.message : 'Não foi possível salvar.';
    if (
      failure instanceof ApiError &&
      failure.status === 409 &&
      !editing.value
    ) {
      fields.value['account-username'] = message;
      await nextTick();
      document.getElementById('account-username')?.focus();
    } else formError.value = message;
  } finally {
    password.value = '';
    saving.value = false;
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
  password.value = '';
});
onMounted(() => void load());
</script>

<template>
  <div class="task-page account-page users-page">
    <header class="tp-heading">
      <h1>Usuários</h1>
      <button
        class="button secondary"
        :disabled="busy || saving"
        @click="load()"
      >
        <RefreshCw :size="16" />Atualizar
      </button>
    </header>
    <p v-if="error" class="tp-field-error" role="alert">
      {{ error }}<span v-if="accounts.length"> Lista anterior preservada.</span>
    </p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <div class="accounts-layout">
      <Card class="tp-card accounts-list" :aria-busy="busy"
        ><div class="tp-section-heading">
          <h2>Contas de acesso</h2>
          <span v-if="loaded" class="tp-muted"
            >{{ accounts.length }} nesta página</span
          >
        </div>
        <p v-if="busy && !loaded" role="status">Carregando usuários…</p>
        <p v-if="loaded && !accounts.length && !error">
          Nenhum usuário encontrado.
        </p>
        <p v-if="!loaded && error">Lista indisponível.</p>
        <div v-if="accounts.length" class="tp-table accounts-table">
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>Papel</th>
                <th>Habilitação</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="account in accounts"
                :key="account.id"
                :data-account-id="account.id"
              >
                <td data-label="Nome">
                  <strong>{{ account.username }}</strong
                  ><small
                    v-if="account.id === currentUser?.id"
                    class="own-account"
                    >Sua conta</small
                  >
                </td>
                <td data-label="Papel">{{ roles[account.role] }}</td>
                <td data-label="Habilitação">
                  <Badge :tone="account.enabled ? 'good' : 'neutral'">{{
                    account.enabled ? 'Habilitada' : 'Desabilitada'
                  }}</Badge>
                </td>
                <td>
                  <button
                    class="button secondary"
                    :aria-label="`Editar ${account.username}`"
                    :disabled="saving"
                    @click="edit(account)"
                  >
                    <Pencil :size="16" />Editar
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <nav
          class="tp-actions account-pagination"
          aria-label="Paginação de usuários"
        >
          <button
            class="button secondary"
            :disabled="!previous.length || busy || saving"
            @click="back"
          >
            Anterior</button
          ><span>Página {{ previous.length + 1 }}</span
          ><button
            class="button secondary"
            :disabled="!nextCursor || busy || saving"
            @click="forward"
          >
            Próxima
          </button>
        </nav>
      </Card>
      <form
        class="card tp-card account-form"
        :aria-busy="saving"
        @submit.prevent="submit"
        @invalid.capture="invalid"
        @input="clearField"
        @change="clearField"
      >
        <div class="tp-section-heading">
          <h2>{{ editing ? 'Editar acesso' : 'Nova conta' }}</h2>
          <Plus v-if="!editing" :size="18" />
        </div>
        <p v-if="formError" class="tp-field-error" role="alert">
          {{ formError }}
        </p>
        <div class="account-field">
          <label for="account-username">Nome de usuário</label
          ><input
            id="account-username"
            v-model.trim="username"
            autocomplete="off"
            required
            pattern="[A-Za-z0-9_\-]+"
            maxlength="64"
            :readonly="!!editing"
            :disabled="saving"
            :aria-invalid="!!fields['account-username']"
            :aria-describedby="
              fields['account-username'] ? 'username-error' : undefined
            "
          />
          <p
            v-if="fields['account-username']"
            id="username-error"
            class="tp-field-error"
          >
            {{ fields['account-username'] }}
          </p>
        </div>
        <div class="account-field">
          <label for="account-role">Papel</label
          ><select id="account-role" v-model="role" :disabled="saving">
            <option value="visualizador">Visualizador</option>
            <option value="operador">Operador</option>
            <option value="administrador">Administrador</option>
          </select>
        </div>
        <div class="account-field">
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
            :aria-invalid="!!fields['account-password']"
            :aria-describedby="
              fields['account-password']
                ? 'password-help password-error'
                : 'password-help'
            "
          />
          <p id="password-help" class="tp-muted">
            Mínimo de 12 caracteres; máximo de 72 bytes em UTF-8.
          </p>
          <p
            v-if="fields['account-password']"
            id="password-error"
            class="tp-field-error"
          >
            {{ fields['account-password'] }}
          </p>
        </div>
        <label v-if="editing" class="account-enabled"
          ><input v-model="enabled" type="checkbox" :disabled="saving" />Conta
          habilitada</label
        >
        <p v-if="editing === currentUser?.id" class="tp-muted">
          Você está editando sua conta. Ao salvar, será necessário entrar
          novamente.
        </p>
        <div class="tp-actions">
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
        </div>
        <details>
          <summary>Permissões dos papéis</summary>
          <p>
            Visualizador acompanha os dados. Operador também envia comandos.
            Administrador também gerencia contas e configurações, gera dados e
            treina modelos.
          </p>
          <p>
            Alterações de acesso encerram as sessões anteriores. O sistema exige
            ao menos um administrador habilitado.
          </p>
        </details>
      </form>
    </div>
  </div>
  <DialogRoot v-model:open="confirmOpen"
    ><DialogPortal
      ><DialogOverlay class="account-confirm-overlay" /><DialogContent
        class="account-confirm"
        ><DialogTitle>Desativar {{ username }}?</DialogTitle
        ><DialogDescription
          >A conta {{ username }} perderá o acesso e suas sessões serão
          encerradas. As demais alterações do formulário também serão salvas.{{
            editing === currentUser?.id ? ' Esta é a sua conta.' : ''
          }}</DialogDescription
        >
        <div class="tp-actions">
          <DialogClose class="button secondary" :disabled="saving"
            >Cancelar</DialogClose
          ><button
            class="button primary"
            :disabled="saving"
            @click="confirmDisable"
          >
            {{ saving ? 'Salvando…' : 'Confirmar desativação' }}
          </button>
        </div></DialogContent
      ></DialogPortal
    ></DialogRoot
  >
</template>
