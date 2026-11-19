<script setup lang="ts">
import { computed } from 'vue';
const props = defineProps<{ summary: Record<string, unknown> }>();
const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const prediction = computed(() => record(props.summary.prediction));
const metrics = computed(() => record(props.summary.model_metrics));
const targets = computed(() => record(metrics.value.targets));
const number = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('pt-BR', { maximumFractionDigits: 3 })
    : 'Indisponível';
const stamp = (value: unknown) =>
  typeof value === 'string' && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleString('pt-BR')
    : 'Indisponível';
const available = computed(() => prediction.value.status === 'valid');
const names: Record<string, string> = {
  health_score: 'Saúde',
  rul_calendar_hours: 'RUL',
};
</script>
<template>
  <details class="assistant-data">
    <summary>Dados estruturados desta resposta</summary>
    <p class="tp-muted">
      Resumo do backend em {{ stamp(summary.utc) }} · leitura em
      {{ stamp(summary.sample_utc) }}
    </p>
    <dl class="tp-definition">
      <dt>Saúde</dt>
      <dd>
        {{
          available
            ? number(prediction.saude_compressor_percentual)
            : 'Indisponível'
        }}<span
          v-if="
            available &&
            typeof prediction.saude_compressor_percentual === 'number'
          "
        >
          %</span
        >
      </dd>
      <dt>RUL</dt>
      <dd>
        {{
          available
            ? number(prediction.vida_util_restante_estimada_horas)
            : 'Indisponível'
        }}<span
          v-if="
            available &&
            typeof prediction.vida_util_restante_estimada_horas === 'number'
          "
        >
          h de calendário</span
        >
      </dd>
      <dt>Alertas no resumo</dt>
      <dd>
        {{
          Array.isArray(summary.alerts) ? summary.alerts.length : 'Indisponível'
        }}
      </dd>
    </dl>
    <p v-if="!available">
      Previsão indisponível neste resumo. Estado registrado:
      {{ prediction.status ?? 'não informado' }}.
    </p>
    <template v-if="metrics.status === 'test_synthetic'"
      ><h3>Métricas do teste sintético</h3>
      <p class="tp-muted">Versão: {{ metrics.version ?? 'não informada' }}</p>
      <dl v-for="(entry, name) in targets" :key="name" class="tp-definition">
        <dt>{{ names[String(name)] ?? name }}</dt>
        <dd>
          MAE {{ number(record(entry).mae) }} {{ record(entry).unit }} · RMSE
          {{ number(record(entry).rmse) }} {{ record(entry).unit }} · R²
          {{ number(record(entry).r2) }}
        </dd>
      </dl></template
    >
    <p v-else class="tp-muted">
      Métricas do modelo indisponíveis neste resumo.
    </p>
    <details>
      <summary>Referências técnicas do resumo</summary>
      <pre>{{ JSON.stringify(summary, null, 2) }}</pre>
    </details>
  </details>
</template>
