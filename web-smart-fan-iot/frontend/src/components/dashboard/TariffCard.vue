<script setup lang="ts">
import { Check, ReceiptText } from 'lucide-vue-next';

defineProps<{
  tariff: number;
  saving: boolean;
  saved: boolean;
}>();

const emit = defineEmits<{
  'update:tariff': [value: string];
  save: [];
}>();
</script>

<template>
  <article class="dashboard-card tariff-card">
    <h2 class="card-title"><ReceiptText :size="16" /> Tarifa de energia</h2>
    <p class="card-description">
      Atualize o valor usado nas estimativas de custo do painel.
    </p>

    <label class="card-field">
      <span>Tarifa (R$/kWh)</span>
      <input
        :value="tariff"
        type="number"
        min="0"
        step="0.01"
        inputmode="decimal"
        @input="emit('update:tariff', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <button class="primary-button" type="button" :disabled="saving" @click="emit('save')">
      <Check v-if="saved" :size="16" />
      {{ saved ? 'Tarifa salva' : 'Salvar tarifa' }}
    </button>

    <p class="save-hint" aria-live="polite">
      {{ saved ? 'Estimativas de custo atualizadas.' : '' }}
    </p>
  </article>
</template>

<style scoped>
.tariff-card { padding: 1.25rem; }
.card-title {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  color: var(--foreground);
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.card-title svg { color: var(--primary); flex: 0 0 auto; }
.card-description {
  margin: 0.5rem 0 0;
  color: var(--muted-foreground);
  font-size: 0.75rem;
  line-height: 1.5;
}
.card-field { display: block; margin-top: 1rem; }
.card-field > span {
  display: block;
  margin-bottom: 0.375rem;
  color: var(--muted-foreground);
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--input);
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  background: var(--background);
  color: var(--foreground);
  font-family: var(--font-display);
  font-size: 0.875rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  outline: none;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}
input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 30%, transparent);
}
.primary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  margin-top: 1rem;
  border: 0;
  border-radius: 0.375rem;
  padding: 0.6rem 0.9rem;
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: filter 160ms ease;
}
.primary-button:not(:disabled):hover { filter: brightness(1.07); }
.primary-button:disabled { cursor: not-allowed; opacity: 0.5; }
.save-hint {
  min-height: 1rem;
  margin: 0.5rem 0 0;
  color: var(--muted-foreground);
  font-size: 0.6875rem;
  text-align: center;
}
</style>
