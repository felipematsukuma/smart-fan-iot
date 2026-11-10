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
import type { FrameReadyV2 } from '../../lib/contracts-v2.generated';
import { sensorLabels, units, type SensorField } from '../scene/model';
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
);
const props = defineProps<{ frames: FrameReadyV2[]; field: SensorField }>();
const label = computed(
  () => `${sensorLabels[props.field]} (${units[props.field]})`,
);
const data = computed(() => {
  const labels: string[] = [],
    values: (number | null)[] = [];
  props.frames.forEach((frame, index) => {
    const previous = props.frames[index - 1];
    const at = new Date(frame.timestamp).toLocaleTimeString('pt-BR');
    if (
      previous &&
      (frame.metadata.boot_id !== previous.metadata.boot_id ||
        Date.parse(frame.timestamp) - Date.parse(previous.timestamp) > 6000)
    ) {
      labels.push(at);
      values.push(null);
    }
    labels.push(at);
    values.push(frame.conteudo.telemetry.readings[props.field]);
  });
  return {
    labels,
    datasets: [
      {
        label: label.value,
        data: values,
        borderColor: '#238574',
        pointRadius: 0,
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
  scales: { x: { ticks: { maxTicksLimit: 4 } } },
};
</script>
<template>
  <div class="mini-chart">
    <Line
      :data="data"
      :options="options"
      role="img"
      :aria-label="`Histórico WS de ${label}`"
    />
  </div>
</template>
<style scoped>
.mini-chart {
  height: 180px;
}
</style>
