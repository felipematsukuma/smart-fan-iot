<script setup lang="ts">
import { computed } from 'vue';
import {
  Wind,
  LayoutDashboard,
  AirVent,
  Box,
  Activity,
  MessageSquare,
  FlaskConical,
  BrainCircuit,
  Network,
  ScrollText,
  Users,
  ExternalLink,
  LogOut,
} from 'lucide-vue-next';
import { currentUser } from '../auth';
defineProps<{ mobile?: boolean }>();
const emit = defineEmits<{ navigate: []; logout: [] }>();
const groups = computed(() => [
  {
    title: 'Operação',
    items: [
      { to: '/', text: 'Visão geral', icon: LayoutDashboard },
      { to: '/dispositivos', text: 'Dispositivos', icon: AirVent },
      { to: '/cena-3d', text: 'Cena 3D', icon: Box },
    ],
  },
  {
    title: 'Análise',
    items: [
      { to: '/insights', text: 'Insights', icon: Activity },
      { to: '/assistente', text: 'Assistente local', icon: MessageSquare },
    ],
  },
  ...(currentUser.value?.role === 'administrador'
    ? [
        {
          title: 'Laboratório',
          items: [
            {
              to: '/laboratorio',
              text: 'Dados sintéticos',
              icon: FlaskConical,
            },
            { to: '/treinamento', text: 'Treinamento', icon: BrainCircuit },
          ],
        },
        {
          title: 'Administração',
          items: [
            { to: '/mensageria', text: 'Mensageria', icon: Network },
            { to: '/auditoria', text: 'Auditoria', icon: ScrollText },
            { to: '/usuarios', text: 'Usuários', icon: Users },
            {
              to: '/interfaces',
              text: 'Interfaces locais',
              icon: ExternalLink,
            },
          ],
        },
      ]
    : []),
]);
</script>
<template>
  <div class="pv-navigation">
    <RouterLink
      to="/"
      class="pv-brand"
      aria-label="Ventora, visão geral"
      @click="emit('navigate')"
      ><span class="pv-brand-mark"><Wind :size="23" /></span
      ><span>ventora<small>CLIMA & EQUIPAMENTO</small></span></RouterLink
    >
    <nav :aria-label="mobile ? 'Navegação móvel' : 'Navegação principal'">
      <section v-for="group in groups" :key="group.title" class="pv-nav-group">
        <h2>{{ group.title }}</h2>
        <RouterLink
          v-for="item in group.items"
          :key="item.to"
          :to="item.to"
          @click="emit('navigate')"
          ><component :is="item.icon" :size="17" aria-hidden="true" /><span>{{
            item.text
          }}</span></RouterLink
        >
      </section>
    </nav>
    <footer v-if="currentUser">
      <span class="pv-user-avatar" aria-hidden="true">{{
        currentUser.username[0]?.toUpperCase()
      }}</span
      ><span class="pv-user-name"
        >{{ currentUser.username }}<small>{{ currentUser.role }}</small></span
      ><button
        type="button"
        aria-label="Sair"
        title="Sair"
        @click="emit('logout')"
      >
        <LogOut :size="18" />
      </button>
    </footer>
  </div>
</template>
<style scoped>
.pv-navigation {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 24px 16px 16px;
  color: #334155;
  background: #fff;
}
.pv-brand {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 0 8px 22px;
  color: #142c32;
  font-size: 1.71429rem;
  font-weight: 750;
  letter-spacing: -0.8px;
}
.pv-brand small {
  display: block;
  font-size: 1rem;
  letter-spacing: 1.2px;
  color: #475569;
  font-weight: 600;
}
.pv-brand-mark {
  background: #e3f3ee;
  color: #11695c;
  border-radius: 10px;
  padding: 9px;
  display: flex;
}
nav {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 0 2px;
}
.pv-nav-group {
  margin-bottom: 20px;
}
.pv-nav-group h2 {
  font-size: 1rem;
  text-transform: uppercase;
  letter-spacing: 1.1px;
  color: #475569;
  margin: 0 0 7px 10px;
  font-weight: 650;
}
nav a {
  display: flex;
  gap: 10px;
  align-items: center;
  min-height: 40px;
  padding: 9px 10px;
  border-radius: 7px;
  font-size: 1rem;
  font-weight: 550;
  margin-bottom: 2px;
  border: 1px solid transparent;
}
nav a:hover {
  background: #f1f5f9;
}
nav a.router-link-exact-active {
  color: #0f6659;
  background: #eaf5f1;
  border-color: #d2e9df;
  font-weight: 650;
}
footer {
  display: flex;
  gap: 9px;
  align-items: center;
  border-top: 1px solid #e2e8f0;
  padding-top: 15px;
  margin-top: 8px;
  font-size: 1rem;
}
.pv-user-name {
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 650;
}
footer small {
  display: block;
  color: #475569;
  font-size: 1rem;
  font-weight: 400;
}
.pv-user-avatar {
  background: #f1f5f9;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
footer button {
  margin-left: auto;
  background: transparent;
  border: 0;
  padding: 10px;
  color: #475569;
  border-radius: 6px;
  display: flex;
}
a:focus-visible,
button:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: 2px;
}
</style>
