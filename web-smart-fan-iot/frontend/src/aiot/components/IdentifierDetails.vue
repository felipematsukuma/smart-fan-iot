<script setup lang="ts">
import { ref } from 'vue';
defineProps<{ value: string; label?: string }>();
const feedback = ref('');
async function copy(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    feedback.value = 'Identificador copiado.';
  } catch {
    feedback.value =
      'Não foi possível copiar. Selecione o identificador abaixo.';
  }
}
</script>
<template>
  <details class="identifier-details">
    <summary>{{ label ?? 'Identificação' }}</summary>
    <p>
      <code>{{ value }}</code>
    </p>
    <button type="button" class="button secondary" @click="copy(value)">
      Copiar identificador
    </button>
    <p v-if="feedback" role="status">{{ feedback }}</p>
    <slot />
  </details>
</template>
