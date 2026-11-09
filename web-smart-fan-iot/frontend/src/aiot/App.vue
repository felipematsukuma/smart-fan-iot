<script setup lang="ts">
import { watch, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import {
  Wind,
  LayoutDashboard,
  Users,
  ScrollText,
  LogOut,
  AirVent,
  Network,
  FlaskConical,
} from 'lucide-vue-next';
import { currentUser, signOut, sessionNotice } from './auth';
import { router } from './router';
import { startRealtime, stopRealtime } from './realtime';

const route = useRoute();
watch(currentUser, (value) => {
  if (value) startRealtime();
  else stopRealtime();
  if (!value && !route.meta.public) void router.replace('/entrar');
});
onBeforeUnmount(stopRealtime);
async function logout() {
  try {
    await signOut();
  } catch {
    sessionNotice.value =
      'Saída local concluída. A conexão não permitiu confirmar a revogação.';
  }
  await router.replace('/entrar');
}
</script>

<template>
  <RouterView v-if="route.meta.public" />
  <div v-else-if="currentUser" class="app-frame">
    <a href="#main-content" class="skip-link">Ir para conteúdo</a>
    <aside class="sidebar">
      <RouterLink to="/" class="brand" aria-label="Ventora, visão geral">
        <span class="brand-icon"><Wind :size="25" /></span>
        <span
          >ventora<span class="brand-caption">CLIMA & EQUIPAMENTO</span></span
        >
      </RouterLink>
      <p class="nav-label">MONITORAMENTO</p>
      <nav aria-label="Navegação principal">
        <RouterLink to="/"
          ><LayoutDashboard :size="18" />Visão geral</RouterLink
        >
        <RouterLink to="/dispositivos"
          ><AirVent :size="18" />Dispositivos</RouterLink
        >
        <template v-if="currentUser.role === 'administrador'">
          <p class="nav-label">ADMINISTRAÇÃO</p>
          <RouterLink to="/usuarios"><Users :size="18" />Usuários</RouterLink>
          <RouterLink to="/mensageria"
            ><Network :size="18" />Mensageria</RouterLink
          >
          <RouterLink to="/laboratorio"
            ><FlaskConical :size="18" />Laboratório</RouterLink
          >
          <RouterLink to="/auditoria"
            ><ScrollText :size="18" />Auditoria</RouterLink
          >
        </template>
      </nav>
      <div class="sidebar-bottom">
        <span class="avatar" aria-hidden="true">{{
          currentUser.username[0]?.toUpperCase()
        }}</span>
        <div>
          <strong>{{ currentUser.username }}</strong
          ><small>{{ currentUser.role }}</small>
        </div>
        <button
          class="icon-button"
          title="Sair"
          aria-label="Sair"
          @click="logout"
        >
          <LogOut :size="19" />
        </button>
      </div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <span
          >Residencial <span class="divider">/</span>
          {{ route.meta.title }}</span
        ><span class="environment-badge">AMBIENTE SIMULADO</span>
      </header>
      <main id="main-content" tabindex="-1"><RouterView /></main>
    </div>
  </div>
</template>
