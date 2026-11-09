<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Wind, LockKeyhole, ArrowRight, ShieldCheck } from 'lucide-vue-next';
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
  <div class="login-layout">
    <section class="login-story" aria-label="Sobre o monitoramento">
      <div class="brand">
        <span class="brand-icon"><Wind :size="27" /></span
        ><span
          >ventora<span class="brand-caption">CLIMA & EQUIPAMENTO</span></span
        >
      </div>
      <div class="login-story-content">
        <span class="eyebrow">MONITORAMENTO RESIDENCIAL · AIoT</span>
        <h1>
          Um clima melhor.<br /><span>Uma operação mais inteligente.</span>
        </h1>
        <p>
          Acompanhe consumo, condições de operação e saúde do seu
          ar-condicionado em um só lugar.
        </p>
        <div class="ac-illustration" aria-hidden="true">
          <div class="ac-light"></div>
          <div class="ac-slats"></div>
          <Wind :size="64" :stroke-width="1" />
        </div>
        <div class="sensor-tags">
          <span>Corrente</span><span>Vibração</span><span>Temperaturas</span>
        </div>
      </div>
      <p class="login-footnote">
        Continuidade do projeto smart-fan-iot · Equipamento simulado
      </p>
    </section>
    <main class="login-form-area">
      <form class="login-form" :aria-busy="busy" @submit.prevent="submit">
        <div class="form-symbol"><LockKeyhole :size="25" /></div>
        <h2>Bem-vindo de volta</h2>
        <p class="muted">
          Entre para acompanhar o ambiente e seus equipamentos.
        </p>
        <p v-if="sessionNotice" class="notice" role="status">
          {{ sessionNotice }}
        </p>
        <p v-if="error" class="error-box" role="alert">{{ error }}</p>
        <label for="username">Usuário</label
        ><input
          id="username"
          v-model="username"
          name="username"
          autocomplete="username"
          required
          maxlength="64"
          :disabled="busy"
          autofocus
        />
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
        <button
          class="button primary login-submit"
          type="submit"
          :disabled="busy"
        >
          {{ busy ? 'Entrando…' : 'Entrar' }}<ArrowRight :size="18" />
        </button>
        <p class="login-security">
          <ShieldCheck :size="16" />Acesso conforme as permissões da sua conta.
        </p>
      </form>
    </main>
  </div>
</template>
