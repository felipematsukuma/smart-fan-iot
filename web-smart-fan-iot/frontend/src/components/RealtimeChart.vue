<script setup lang="ts">
import { ref, watch } from 'vue';
import { Line } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import type { MetricPoint } from '../types';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

const props = defineProps<{
  currentPower: number;
  timestamp: number;
  history: MetricPoint[];
  appendLive?: boolean;
}>();

const MAX_POINTS = 120;

const chartData = ref({
  labels: [] as string[],
  datasets: [
    {
      label: 'Potência Instantânea (Watts)',
      backgroundColor: 'rgba(59, 130, 246, 0.2)',
      borderColor: '#3b82f6',
      data: [] as number[],
      pointRadius: 2,
      fill: true,
      tension: 0.3
    }
  ]
});

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    y: {
      beginAtZero: true,
      suggestedMax: 80,
      title: { display: true, text: 'Watts (W)' }
    }
  },
  animation: { duration: 0 }
};

const formatPointLabel = (value: string | Date) => new Date(value).toLocaleString([], {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit'
});

function replaceHistory(history: MetricPoint[]) {
  const points = history.slice(-MAX_POINTS);
  chartData.value = {
    labels: points.map((point) => formatPointLabel(point.time)),
    datasets: [{ ...chartData.value.datasets[0], data: points.map((point) => point.power_w) }]
  };
}

function appendPoint(power: number, time: Date) {
  const labels = [...chartData.value.labels, formatPointLabel(time)];
  const data = [...chartData.value.datasets[0].data, power];

  if (labels.length > MAX_POINTS) {
    labels.shift();
    data.shift();
  }

  chartData.value = {
    labels,
    datasets: [{ ...chartData.value.datasets[0], data }]
  };
}

watch(
  () => props.history,
  (history) => replaceHistory(history),
  { immediate: true }
);

let lastTimestamp = props.timestamp;
watch(
  () => props.timestamp,
  (timestamp) => {
    if (props.appendLive === false || !timestamp || timestamp === lastTimestamp) return;
    lastTimestamp = timestamp;
    appendPoint(props.currentPower, new Date());
  }
);
</script>

<template>
  <div style="height: 260px; width: 100%;">
    <Line :data="chartData" :options="chartOptions" />
    <p v-if="chartData.datasets[0].data.length === 0" class="empty-chart">
      Aguardando telemetria do ESP32...
    </p>
  </div>
</template>

<style scoped>
.empty-chart {
  margin: 0.5rem 0 0;
  color: #64748b;
  font-size: 0.85rem;
  text-align: center;
}
</style>
