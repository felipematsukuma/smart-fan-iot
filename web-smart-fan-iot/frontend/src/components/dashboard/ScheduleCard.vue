<script setup lang="ts">
import { Check, MoonStar } from 'lucide-vue-next';

defineProps<{
  enabled: boolean;
  time: string;
  saving: boolean;
  saved: boolean;
}>();

const emit = defineEmits<{
  'update:enabled': [value: boolean];
  'update:time': [value: string];
  save: [];
}>();
</script>

<template>
  <article class="dashboard-card schedule-card">
    <header class="card-header">
      <h2 class="card-title"><MoonStar :size="16" /> Desligamento automático</h2>
      <button
        class="toggle"
        type="button"
        role="switch"
        :aria-checked="enabled"
        aria-label="Ativar timer noturno"
        @click="emit('update:enabled', !enabled)"
      >
        <span class="toggle-knob" :class="{ on: enabled }" />
      </button>
    </header>

    <p class="card-description">
      {{ enabled
        ? `O ventilador desliga todos os dias às ${time}, mesmo que você esteja fora.`
        : 'Ative para escolher uma hora fixa de desligamento.' }}
    </p>

    <div class="card-fields" :class="{ disabled: !enabled }">
      <label>
        <span>Hora de desligar</span>
        <input
          :value="time"
          type="time"
          :disabled="!enabled"
          @input="emit('update:time', ($event.target as HTMLInputElement).value)"
        />
      </label>
    </div>

    <button class="primary-button" type="button" :disabled="!enabled || saving" @click="emit('save')">
      <Check v-if="saved" :size="16" />
      {{ saved ? 'Agendamento salvo' : 'Salvar agendamento' }}
    </button>

    <p class="save-hint" aria-live="polite">
      {{ saved ? 'Enviado ao dispositivo com sucesso.' : '' }}
    </p>
  </article>
</template>

<style scoped>
.schedule-card { padding: 1.25rem; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.card-title {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
  margin: 0;
  color: var(--foreground);
  font-family: var(--font-display);
  font-size: 0.875rem;
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
.toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: 2.5rem;
  height: 1.375rem;
  flex: 0 0 auto;
  border: 0;
  border-radius: 999px;
  background: var(--muted);
  cursor: pointer;
  transition: background-color 160ms ease;
}
.toggle[aria-checked='true'] { background: var(--primary); }
.toggle-knob {
  position: absolute;
  left: 0.1875rem;
  width: 1rem;
  height: 1rem;
  border-radius: 999px;
  background: #fff;
  box-shadow: 0 1px 2px rgb(0 0 0 / 25%);
  transition: transform 160ms ease;
}
.toggle-knob.on { transform: translateX(1.125rem); }
.card-fields {
  display: grid;
  gap: 0.75rem;
  margin-top: 1rem;
  transition: opacity 160ms ease;
}
.card-fields.disabled { pointer-events: none; opacity: 0.4; }
.card-fields label { display: block; }
.card-fields label > span {
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
