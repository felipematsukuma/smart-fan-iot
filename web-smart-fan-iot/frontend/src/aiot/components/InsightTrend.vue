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
  pilot?: boolean;
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
        borderColor: props.pilot ? '#0f766e' : '#238574',
        pointRadius: props.points.length === 1 ? 3 : 0,
        borderWidth: 2,
        spanGaps: false,
      },
    ],
  };
});
const options = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  plugins: {
    legend: { display: false },
    tooltip: {
      intersect: props.pilot ? false : true,
      titleFont: { size: props.pilot ? 14 : 12 },
      bodyFont: { size: props.pilot ? 14 : 12 },
    },
  },
  scales: {
    x: {
      ticks: {
        maxTicksLimit: props.pilot ? 3 : 6,
        maxRotation: props.pilot ? 0 : 50,
        color: props.pilot ? '#475569' : '#666',
        font: { size: props.pilot ? 14 : 12 },
      },
    },
    y: {
      beginAtZero: true,
      title: {
        display: !!props.pilot,
        text: label.value,
        color: '#475569',
        font: { size: 14 },
      },
      ticks: {
        color: props.pilot ? '#475569' : '#666',
        font: { size: props.pilot ? 14 : 12 },
      },
    },
  },
}));
</script>
<template>
  <p
    v-if="
      !points.some((point) => point.status === 'valid' && point[target] != null)
    "
    class="muted"
  >
    {{
      pilot
        ? 'Nenhuma previsão válida nesta janela.'
        : 'Nenhuma previsão válida nesta janela; lacunas não recebem valores estimados.'
    }}
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
