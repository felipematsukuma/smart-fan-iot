<script setup lang="ts">
import { computed } from 'vue';
import { Line } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
} from 'chart.js';
import { trend, type PredictionPoint } from '../insights';
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
);
const props = defineProps<{
  points: PredictionPoint[];
  target: 'health_score' | 'rul_calendar_hours';
}>();
const label = computed(() =>
  props.target === 'health_score' ? 'Saúde (%)' : 'RUL (h de calendário)',
);
const data = computed(() => {
  const series = trend(props.points, props.target);
  return {
    labels: series.labels,
    datasets: [
      {
        label: label.value,
        data: series.values,
        borderColor: '#238574',
        pointRadius: props.points.length === 1 ? 3 : 0,
        borderWidth: 2,
        spanGaps: false,
      },
    ],
  };
});
const options = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  plugins: { legend: { display: false } },
  scales: { x: { ticks: { maxTicksLimit: 6 } }, y: { beginAtZero: true } },
};
</script>
<template>
  <p
    v-if="
      !points.some((point) => point.status === 'valid' && point[target] != null)
    "
    class="muted"
  >
    Nenhuma previsão válida nesta janela; lacunas não recebem valores estimados.
  </p>
  <div v-else class="insight-chart">
    <Line
      :data="data"
      :options="options"
      role="img"
      :aria-label="`Tendência de ${label}, lacunas preservadas`"
    />
  </div>
</template>
<style scoped>
.insight-chart {
  height: 240px;
  padding: 1rem;
}
</style>
