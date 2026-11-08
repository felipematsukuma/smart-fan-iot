<script setup lang="ts">
defineProps<{
  label: string;
  value: string;
  unit?: string;
  highlight?: boolean;
}>();
</script>

<template>
  <article class="metric-card" :class="{ highlight }">
    <header>
      <span>{{ label }}</span>
      <span class="metric-icon" aria-hidden="true"><slot name="icon" /></span>
    </header>
    <div class="metric-value">
      <strong>{{ value }}</strong>
      <small v-if="unit">{{ unit }}</small>
    </div>
    <footer v-if="$slots.footer"><slot name="footer" /></footer>
  </article>
</template>

<style scoped>
.metric-card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 0.75rem;
  padding: 1rem;
  background: var(--card);
  box-shadow: var(--shadow-card);
}
.metric-card.highlight {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  background: color-mix(in srgb, var(--primary) 6%, var(--card));
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  color: var(--muted-foreground);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}
.metric-icon {
  color: var(--muted-foreground);
  opacity: 0.75;
}
.metric-value {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  margin-top: 0.75rem;
}
.metric-value strong {
  color: var(--foreground);
  font-family: var(--font-display);
  font-size: clamp(1.35rem, 2.5vw, 1.85rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}
.metric-value small {
  color: var(--muted-foreground);
  font-size: 0.78rem;
  font-weight: 600;
}
footer {
  margin-top: 0.7rem;
  color: var(--muted-foreground);
  font-size: 0.72rem;
}
</style>
