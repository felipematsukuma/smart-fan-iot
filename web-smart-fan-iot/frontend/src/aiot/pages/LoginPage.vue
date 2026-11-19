<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Wind, LockKeyhole, ArrowRight } from 'lucide-vue-next';
import { Card } from '../ui/primitives';
import '../ui/task-page.css';
import '../ui/final-pages.css';
import { signIn, sessionNotice } from '../auth';
import { safeDestination } from '../access';

const username = ref('');
const password = ref('');
const busy = ref(false);
const error = ref('');
const route = useRoute();
const router = useRouter();
async function submit() {
  busy.value = true;
  error.value = '';
  try {
    await signIn(username.value, password.value);
    await router.replace(safeDestination(route.query.next));
  } catch (failure) {
    error.value =
      failure instanceof Error ? failure.message : 'Não foi possível entrar.';
  } finally {
    password.value = '';
    busy.value = false;
  }
}
</script>

<template>
  <main class="task-page entry-page">
    <div class="entry-wrap">
      <div class="entry-brand">
        <Wind :size="27" aria-hidden="true" /><strong>ventora</strong>
      </div>
      <Card class="tp-card entry-card"
        ><form class="entry-form" :aria-busy="busy" @submit.prevent="submit">
          <header class="tp-heading">
            <h1>Entrar</h1>
            <LockKeyhole :size="22" aria-hidden="true" />
          </header>
          <p v-if="sessionNotice" class="entry-notice" role="status">
            {{ sessionNotice }}
          </p>
          <p v-if="error" class="tp-field-error" role="alert">{{ error }}</p>
          <div class="entry-field">
            <label for="username">Usuário</label
            ><input
              id="username"
              v-model="username"
              name="username"
              autocomplete="username"
              autocapitalize="none"
              :spellcheck="false"
              required
              maxlength="64"
              :disabled="busy"
              autofocus
            />
          </div>
          <div class="entry-field">
            <label for="password">Senha</label
            ><input
              id="password"
              v-model="password"
              name="password"
              type="password"
              autocomplete="current-password"
              required
              maxlength="72"
              :disabled="busy"
            />
          </div>
          <button
            class="button primary entry-submit"
            type="submit"
            :disabled="busy"
          >
            {{ busy ? 'Entrando…' : 'Entrar'
            }}<ArrowRight :size="18" aria-hidden="true" />
          </button></form
      ></Card>
    </div>
  </main>
</template>
