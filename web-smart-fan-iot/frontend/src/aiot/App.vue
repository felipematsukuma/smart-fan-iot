<script setup lang="ts">
import { watch, onBeforeUnmount, onMounted, ref, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import { Menu, X } from 'lucide-vue-next';
import {
  DialogRoot,
  DialogTrigger,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from 'reka-ui';
import { currentUser, signOut, sessionNotice } from './auth';
import { router } from './router';
import { startRealtime, stopRealtime } from './realtime';
import NavigationContent from './components/NavigationContent.vue';
import Button from './ui/Button.vue';
import './ui/pilot.css';
const route = useRoute();
const menuOpen = ref(false);
let focusContent = false;
let desktopMedia: MediaQueryList | undefined;
function resized() {
  if (desktopMedia?.matches && menuOpen.value) {
    focusContent = true;
    menuOpen.value = false;
  }
}
onMounted(() => {
  desktopMedia = matchMedia('(min-width: 1024px)');
  desktopMedia.addEventListener('change', resized);
});
onBeforeUnmount(() => desktopMedia?.removeEventListener('change', resized));
watch(currentUser, (value) => {
  if (value) startRealtime();
  else stopRealtime();
  if (!value && !route.meta.public) void router.replace('/entrar');
});
watch(
  () => route.fullPath,
  () => {
    if (menuOpen.value) {
      focusContent = true;
      menuOpen.value = false;
    }
  },
);
onBeforeUnmount(stopRealtime);
async function closeNavigation() {
  focusContent = true;
  menuOpen.value = false;
}
async function afterClose(event: Event) {
  if (focusContent) {
    event.preventDefault();
    focusContent = false;
    await nextTick();
    document.getElementById('main-content')?.focus();
  }
}
async function logout() {
  menuOpen.value = false;
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
  <div v-else-if="currentUser" class="app-frame pv-shell">
    <a href="#main-content" class="skip-link">Ir para conteúdo</a>
    <aside class="pv-desktop-nav"><NavigationContent @logout="logout" /></aside>
    <div
      class="workspace"
      :class="{
        'pv-pilot-workspace': [
          '/',
          '/dispositivos',
          '/insights',
          '/laboratorio',
          '/treinamento',
          '/mensageria',
          '/auditoria',
          '/usuarios',
          '/interfaces',
          '/assistente',
          '/cena-3d',
        ].includes(route.path),
      }"
    >
      <header class="topbar pv-topbar">
        <div class="pv-breadcrumb">
          <DialogRoot v-model:open="menuOpen">
            <DialogTrigger as-child
              ><Button
                class="pv-mobile-trigger"
                variant="ghost"
                aria-label="Abrir navegação"
                ><Menu :size="20" /></Button
            ></DialogTrigger>
            <DialogPortal
              ><DialogOverlay class="pv-sheet-overlay" /><DialogContent
                class="pv-sheet"
                @close-auto-focus="afterClose"
              >
                <DialogTitle class="sr-only">Navegação do Ventora</DialogTitle
                ><DialogDescription class="sr-only"
                  >Escolha uma página. Escape fecha o menu.</DialogDescription
                >
                <DialogClose
                  class="pv-sheet-close"
                  aria-label="Fechar navegação"
                  ><X :size="20"
                /></DialogClose>
                <NavigationContent
                  mobile
                  @navigate="closeNavigation"
                  @logout="logout"
                /> </DialogContent
            ></DialogPortal>
          </DialogRoot>
          <span
            ><span class="pv-breadcrumb-root"
              >Residencial <span class="divider">/</span></span
            >{{ route.meta.title }}</span
          >
        </div>
        <span class="environment-badge">AMBIENTE SIMULADO</span>
      </header>
      <main id="main-content" tabindex="-1"><RouterView /></main>
    </div>
  </div>
</template>
<style scoped>
.pv-shell > .skip-link {
  top: 0.5rem;
  left: 1rem;
  transform: translateY(calc(-100% - 1rem));
  max-width: calc(100% - 2rem);
  font-size: 1rem;
  z-index: 80;
}
.pv-shell > .skip-link:focus {
  transform: none;
}
.pv-shell > .skip-link:not(:focus) {
  clip-path: inset(50%);
}
.pv-desktop-nav {
  position: fixed;
  inset: 0 auto 0 0;
  width: 236px;
  border-right: 1px solid #e2e8f0;
  z-index: 20;
}
.pv-shell .pv-topbar {
  min-height: 4.57143rem;
  height: auto;
  flex-wrap: wrap;
  gap: 0.57143rem;
  padding-block: 0.57143rem;
}
.pv-topbar :is(.environment-badge, .pv-breadcrumb) {
  font-size: 1rem;
  color: #475569;
}
.pv-topbar .divider {
  color: #475569;
  font-size: 1rem;
}
.pv-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.pv-mobile-trigger {
  display: none;
}
.pv-pilot-workspace main#main-content {
  max-width: 1460px;
  padding: 30px 32px 44px;
}
@media (max-width: 1023px) {
  .pv-desktop-nav {
    display: none;
  }
  .pv-shell .workspace {
    margin-left: 0;
    width: 100%;
  }
  .pv-mobile-trigger {
    display: inline-flex;
  }
  .pv-shell .pv-topbar {
    padding: 0 16px;
  }
  .pv-breadcrumb-root {
    display: none;
  }
  .pv-pilot-workspace main#main-content {
    padding: 24px 20px;
  }
}
@media (max-width: 600px) {
  .pv-pilot-workspace main#main-content {
    padding: 20px 16px 32px;
  }
  .pv-shell .environment-badge {
    font-size: 1rem;
    letter-spacing: 0.5px;
  }
}
</style>
<style>
/* Teleported Sheet styles are limited to these dedicated class names. */
.pv-sheet-overlay {
  position: fixed;
  inset: 0;
  background: #0f172a66;
  z-index: 90;
}
.pv-sheet {
  position: fixed;
  inset: 0 auto 0 0;
  width: min(22.85714rem, 92vw);
  height: 100dvh;
  z-index: 100;
  background: white;
  outline: none;
  box-shadow: 12px 0 40px #0f172a22;
}
.pv-sheet-close {
  position: absolute;
  right: 8px;
  top: 12px;
  z-index: 1;
  border: 0;
  background: white;
  color: #475569;
  padding: 10px;
  display: flex;
  border-radius: 6px;
}
.pv-sheet-close:focus-visible {
  outline: 2px solid #0f766e;
}
</style>
