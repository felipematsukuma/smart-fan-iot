<script setup lang="ts">
import { CalendarRange } from 'lucide-vue-next';

defineProps<{
  modelValue: string;
  start: string;
  end: string;
  showCustom: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string];
  'update:start': [value: string];
  'update:end': [value: string];
  'update:showCustom': [value: boolean];
  apply: [];
}>();

const periods = [
  { key: '8h', label: '8h' },
  { key: '24h', label: '24h' },
  { key: '7d', label: '7d' },
  { key: 'custom', label: 'Personalizar' },
];
</script>

<template>
  <div class="period-selector">
    <div class="period-tabs" role="tablist" aria-label="Período de análise">
      <button
        v-for="period in periods"
        :key="period.key"
        class="period-tab"
        :class="{ active: modelValue === period.key }"
        type="button"
        role="tab"
        :aria-selected="modelValue === period.key"
        @click="emit('update:modelValue', period.key)"
      >
        {{ period.label }}
      </button>
    </div>

    <div v-if="showCustom || modelValue === 'custom'" class="custom-period">
      <label>
        <span>De</span>
        <input
          :value="start"
          type="datetime-local"
          @input="
            emit('update:start', ($event.target as HTMLInputElement).value)
          "
        />
      </label>
      <label>
        <span>Até</span>
        <input
          :value="end"
          type="datetime-local"
          @input="emit('update:end', ($event.target as HTMLInputElement).value)"
        />
      </label>
      <button class="apply-period" type="button" @click="emit('apply')">
        <CalendarRange :size="15" />
        Aplicar período
      </button>
    </div>
  </div>
</template>

<style scoped>
.period-selector {
  display: grid;
  gap: 0.8rem;
  justify-items: end;
}
.period-tabs {
  display: inline-flex;
  max-width: 100%;
  overflow-x: auto;
  padding: 0.25rem;
  border: 1px solid var(--border);
  border-radius: 0.65rem;
  background: var(--card);
  box-shadow: var(--shadow-card);
}
.period-tab {
  border: 0;
  border-radius: 0.45rem;
  padding: 0.45rem 0.7rem;
  background: transparent;
  color: var(--muted-foreground);
  font-size: 0.78rem;
  font-weight: 700;
  white-space: nowrap;
  cursor: pointer;
}
.period-tab.active {
  background: var(--primary);
  color: var(--primary-foreground);
}
.custom-period {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.65rem;
  width: 100%;
  padding: 0.8rem;
  border: 1px solid var(--border);
  border-radius: 0.65rem;
  background: var(--card);
  box-shadow: var(--shadow-card);
}
.custom-period label {
  display: grid;
  gap: 0.3rem;
  color: var(--muted-foreground);
  font-size: 0.65rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.custom-period input {
  min-width: 12rem;
  border: 1px solid var(--input);
  border-radius: 0.45rem;
  padding: 0.5rem 0.6rem;
  background: var(--background);
  color: var(--foreground);
  font-size: 0.78rem;
}
.apply-period {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: 0;
  border-radius: 0.45rem;
  padding: 0.55rem 0.7rem;
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 0.78rem;
  font-weight: 700;
  cursor: pointer;
}
@media (max-width: 640px) {
  .period-selector {
    justify-items: stretch;
  }
  .period-tabs {
    justify-content: space-between;
  }
  .custom-period {
    align-items: stretch;
    flex-direction: column;
  }
  .custom-period input {
    min-width: 0;
    width: 100%;
  }
}
</style>
