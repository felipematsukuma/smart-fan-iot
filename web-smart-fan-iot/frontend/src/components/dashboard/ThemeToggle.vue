<script setup lang="ts">
import { Moon, Sun } from 'lucide-vue-next';
import { useTheme } from '../../composables/useTheme';

const { isDark, toggleTheme } = useTheme();
</script>

<template>
  <button
    class="icon-button"
    type="button"
    :aria-label="isDark ? 'Mudar para tema claro' : 'Mudar para tema escuro'"
    :title="isDark ? 'Mudar para tema claro' : 'Mudar para tema escuro'"
    @click="toggleTheme"
  >
    <Sun v-if="isDark" :size="16" />
    <Moon v-else :size="16" />
  </button>
</template>

<style scoped>
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  flex: 0 0 auto;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--muted-foreground);
  cursor: pointer;
  transition: background-color 160ms ease, color 160ms ease;
}
.icon-button:hover {
  background: var(--muted);
  color: var(--foreground);
}
</style>
