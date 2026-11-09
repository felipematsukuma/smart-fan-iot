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
  Filler,
} from 'chart.js';
import type { FrameReadyV2 } from '../../lib/contracts-v2.generated';
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
);
const props = defineProps<{ frames: FrameReadyV2[] }>();
const data = computed(() => {
  const labels: string[] = [];
  const values: (number | null)[] = [];
  props.frames.forEach((frame, index) => {
    const previous = props.frames[index - 1];
    const label = new Date(frame.timestamp).toLocaleTimeString('pt-BR');
    if (
      previous &&
      (Date.parse(frame.timestamp) - Date.parse(previous.timestamp) > 6000 ||
        previous.metadata.boot_id !== frame.metadata.boot_id)
    ) {
      labels.push(label);
      values.push(null);
    }
    labels.push(label);
    values.push(frame.conteudo.telemetry.readings.power_w);
  });
  return {
    labels,
    datasets: [
      {
        label: 'Potência (W)',
        data: values,
        borderColor: '#238574',
        backgroundColor: '#23857415',
        fill: true,
        pointRadius: props.frames.length < 2 ? 3 : 0,
        borderWidth: 2,
        spanGaps: false,
        tension: 0.15,
      },
    ],
  };
});
const options = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  plugins: { legend: { display: false } },
  scales: {
    x: {
      grid: { display: false },
      ticks: { maxTicksLimit: 8, color: '#718892' },
    },
    y: {
      beginAtZero: true,
      suggestedMax: 100,
      ticks: { color: '#718892' },
      grid: { color: '#edf2f4' },
    },
  },
};
</script>
<template>
  <div class="power-chart">
    <Line
      :data="data"
      :options="options"
      role="img"
      aria-label="Potência observada no equipamento, em watts"
    />
  </div>
</template>
<style scoped>
.power-chart {
  height: 260px;
  padding: 0 1rem 1rem;
}
</style>
