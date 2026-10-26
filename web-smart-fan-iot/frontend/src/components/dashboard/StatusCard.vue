<script setup lang="ts">
import { Wifi, WifiOff } from 'lucide-vue-next';

defineProps<{
  device: string;
  online: boolean;
  lastSeen: string;
  isOn: boolean;
  pending?: boolean;
}>();

const emit = defineEmits<{ toggle: [] }>();
</script>

<template>
  <article class="dashboard-card status-card">
    <header class="card-header">
      <span class="eyebrow">Dispositivo</span>
      <span class="status-pill" :class="online ? 'is-online' : 'is-offline'">
        <span v-if="online" class="status-dot" aria-hidden="true">
          <span class="status-ping" />
        </span>
        <WifiOff v-else :size="12" />
        {{ online ? 'Online' : 'Offline' }}
      </span>
    </header>

    <p class="device-name">{{ device }}</p>

    <dl class="status-details">
      <div>
        <dt>Último sinal</dt>
        <dd>{{ lastSeen }}</dd>
      </div>
      <div>
        <dt><Wifi :size="14" /> Estado</dt>
        <dd>{{ isOn ? 'Ligado' : 'Desligado' }}</dd>
      </div>
    </dl>

    <button
      class="power-button"
      :class="{ on: isOn, offline: !online }"
      type="button"
      :disabled="pending || !online"
      @click="emit('toggle')"
    >
      <span class="power-indicator" aria-hidden="true" />
      {{
        !online
          ? 'ESP32 offline'
          : pending
            ? 'Aguardando…'
            : isOn
              ? 'Desligar ventilador'
              : 'Ligar ventilador'
      }}
    </button>
  </article>
</template>

<style scoped>
.status-card {
  display: grid;
  gap: 0.75rem;
  padding: 1.25rem;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.eyebrow {
  color: var(--muted-foreground);
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border-radius: 999px;
  padding: 0.3rem 0.6rem;
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.status-pill.is-online {
  color: var(--online);
  background: color-mix(in srgb, var(--online) 12%, transparent);
}
.status-pill.is-offline {
  color: var(--offline);
  background: color-mix(in srgb, var(--offline) 12%, transparent);
}
.status-dot {
  position: relative;
  display: inline-flex;
  width: 0.5rem;
  height: 0.5rem;
}
.status-dot::after {
  content: '';
  position: relative;
  display: block;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  background: currentColor;
}
.status-ping {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.6;
  animation: status-ping 1.6s cubic-bezier(0, 0, 0.2, 1) infinite;
}
@keyframes status-ping {
  75%,
  100% {
    transform: scale(2.4);
    opacity: 0;
  }
}
.device-name {
  margin: 0;
  color: var(--foreground);
  font-family: var(--font-display);
  font-size: 1.125rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.status-details {
  display: grid;
  gap: 0.375rem;
  margin: 0;
  color: var(--muted-foreground);
  font-size: 0.75rem;
}
.status-details div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.status-details dt {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.status-details dd {
  margin: 0;
  color: var(--foreground);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.power-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  border: 1px solid color-mix(in srgb, #dc5b5b 40%, var(--border));
  border-radius: 0.5rem;
  padding: 0.6rem 0.8rem;
  background: color-mix(in srgb, #dc5b5b 12%, var(--card));
  color: #dc5b5b;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition:
    background-color 160ms ease,
    color 160ms ease,
    border-color 160ms ease;
}
.power-button.on {
  border-color: color-mix(in srgb, #22a06b 40%, var(--border));
  background: color-mix(in srgb, #22a06b 12%, var(--card));
  color: #22a06b;
}
.power-button.offline {
  border-color: color-mix(in srgb, var(--offline) 40%, var(--border));
  background: color-mix(in srgb, var(--offline) 12%, var(--card));
  color: var(--offline);
}
.power-button:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
.power-button:not(:disabled):hover {
  color: var(--primary-foreground);
  background: var(--primary);
  border-color: var(--primary);
}
.power-indicator {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 999px;
  background: currentColor;
}
</style>
