<script setup lang="ts">
withDefaults(defineProps<{ compact?: boolean }>(), { compact: false });
</script>

<template>
  <div class="brand">
    <h1 :class="compact ? 'compact' : 'full'">Ventora</h1>
    <div class="brand-sub">
      <span class="brand-line" aria-hidden="true" />
      <span>Energia em movimento</span>
    </div>
  </div>
</template>

<style scoped>
.brand h1 {
  margin: 0;
  color: var(--foreground);
  font-family: var(--font-display);
  font-weight: 700;
  letter-spacing: -0.03em;
}
.brand h1.full {
  font-size: 1.8rem;
}
.brand h1.compact {
  font-size: 1.5rem;
}
.brand-sub {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.4rem;
  color: var(--muted-foreground);
  font-size: 0.56rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.brand-line {
  display: block;
  width: 1.5rem;
  height: 0.125rem;
  background: var(--primary);
}
</style>
