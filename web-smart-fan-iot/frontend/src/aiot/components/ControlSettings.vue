<script setup lang="ts">
import type { Command, Rule } from '../control-types';
const rule = defineModel<Rule | null>('rule', { required: true });
defineProps<{
  commands: Command[];
  administrator: boolean;
  busy: boolean;
  pilot?: boolean;
}>();
const emit = defineEmits<{ save: [] }>();
</script>
<template>
  <div :class="{ 'pv-settings': pilot }">
    <details v-if="rule">
      <summary>Termostato e agenda · revisão {{ rule.revision }}</summary>
      <p>
        Fuso America/Sao_Paulo. Liga acima do setpoint + faixa; desliga abaixo
        do setpoint − faixa, respeitando ciclos mínimos. Manual tem prioridade.
        Faixas térmicas de proteção: parar a 80 °C na carcaça, permitir nova
        partida até 75 °C.
      </p>
      <form class="rule-form" @submit.prevent="emit('save')">
        <fieldset :disabled="!administrator || busy">
          <legend>Regra automática</legend>
          <label
            ><input v-model="rule.configuration.enabled" type="checkbox" />Regra
            habilitada</label
          >
          <div class="fields">
            <label
              >Setpoint (°C)<input
                v-model.number="rule.configuration.setpoint_c"
                type="number"
                min="18"
                max="30"
                step="0.5"
                required /></label
            ><label
              >Faixa de histerese (°C)<input
                v-model.number="rule.configuration.hysteresis_c"
                type="number"
                min="0.5"
                max="3"
                step="0.5"
                required /></label
            ><label
              >Mínimo desligado (s)<input
                v-model.number="rule.configuration.minimum_off_seconds"
                type="number"
                min="180"
                max="1800"
                step="1"
                required /></label
            ><label
              >Mínimo ligado (s)<input
                v-model.number="rule.configuration.minimum_on_seconds"
                type="number"
                min="60"
                max="600"
                step="1"
                required
            /></label>
          </div>
          <label
            ><input
              v-model="rule.configuration.schedule_enabled"
              type="checkbox"
            />Usar agenda</label
          >
          <div class="fields">
            <label
              >Hora inicial<input
                v-model.number="rule.configuration.start_hour"
                type="number"
                min="0"
                max="23"
                required /></label
            ><label
              >Hora final<input
                v-model.number="rule.configuration.end_hour"
                type="number"
                min="0"
                max="23"
                required
            /></label>
          </div>
          <p>
            Dias: 1 segunda-feira a 7 domingo; no período que cruza meia-noite,
            a madrugada pertence ao dia inicial.
          </p>
          <div class="actions">
            <label v-for="day in [1, 2, 3, 4, 5, 6, 7]" :key="day"
              ><input
                v-model="rule.configuration.weekdays"
                type="checkbox"
                :value="day"
              />{{ day }}</label
            >
          </div>
          <button v-if="administrator" class="button primary" type="submit">
            Salvar regra
          </button>
        </fieldset>
      </form>
    </details>
    <details>
      <summary>Últimas intenções e confirmações</summary>
      <p v-if="!commands.length">Nenhum comando registrado.</p>
      <ul>
        <li v-for="command in commands" :key="command.id">
          {{ command.id }} · {{ command.producer }} · revisão
          {{ command.revision }} · {{ command.status }} ·
          {{ command.result ?? command.reason_code
          }}<span v-if="command.execution_unknown">
            · resultado físico desconhecido</span
          >
        </li>
      </ul>
    </details>
  </div>
</template>
<style scoped>
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
}
.fields label {
  display: grid;
  gap: 0.4rem;
}
.rule-form fieldset {
  border: 1px solid #ccd8de;
  border-radius: 0.6rem;
  padding: 1rem;
  margin-top: 1rem;
}
input[type='checkbox'] {
  width: auto;
}
details {
  margin: 1rem 0;
}
summary {
  cursor: pointer;
}
p {
  font-size: 0.85rem;
  line-height: 1.6;
}
li {
  font-size: 0.8rem;
  margin: 0.5rem 0;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin: 1rem 0;
}
.pv-settings {
  color: #475569;
  font-size: 1rem;
  border-top: 1px solid #e2e8f0;
  margin-top: 1rem;
}
.pv-settings :is(label, p, li, legend) {
  font-size: 1rem;
}
.pv-settings :is(summary, input, button) {
  min-height: 3.14286rem;
}
.pv-settings input[type='checkbox'] {
  min-height: 1.25rem;
}
.pv-settings input {
  border-color: #64748b;
}
.pv-settings summary {
  align-content: center;
  font-weight: 600;
}
.pv-settings li {
  overflow-wrap: anywhere;
}
</style>
