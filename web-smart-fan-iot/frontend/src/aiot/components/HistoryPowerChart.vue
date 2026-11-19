<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { Line } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
} from 'chart.js';
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
);
const props = defineProps<{
  periodEnd: string;
  points: { timestamp: string; power_w: number | null }[];
}>();
const minutes = ref(0);
let media: MediaQueryList;
const chosen = ref(false);
const defaultWindow = () => {
  if (!chosen.value) minutes.value = media.matches ? 15 : 0;
};
onMounted(() => {
  media = matchMedia('(max-width: 600px)');
  defaultWindow();
  media.addEventListener('change', defaultWindow);
});
onBeforeUnmount(() => media?.removeEventListener('change', defaultWindow));
const points = computed(() =>
  minutes.value
    ? props.points.filter(
        (point) =>
          Date.parse(point.timestamp) >=
          Date.parse(props.periodEnd) - minutes.value * 60000,
      )
    : props.points,
);
const range = computed(() =>
  points.value.length
    ? `${new Date(points.value[0]!.timestamp).toLocaleString('pt-BR')} — ${new Date(points.value.at(-1)!.timestamp).toLocaleString('pt-BR')}`
    : 'Sem pontos neste recorte',
);
const data = computed(() => ({
  labels: points.value.map((point) =>
    new Date(point.timestamp).toLocaleString('pt-BR'),
  ),
  datasets: [
    {
      label: 'Potência média (W)',
      data: points.value.map((point) => point.power_w),
      borderColor: '#0f766e',
      borderWidth: 2,
      pointRadius: 0,
      spanGaps: false,
    },
  ],
}));
const options = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  interaction: { mode: 'nearest' as const, intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: {
      titleFont: { size: 14 },
      bodyFont: { size: 14 },
      callbacks: {
        label: (item: { parsed: { y: number | null } }) =>
          `${item.parsed.y?.toLocaleString('pt-BR') ?? 'Sem leitura'} W`,
      },
    },
  },
  scales: {
    x: {
      grid: { display: false },
      ticks: {
        maxTicksLimit: 3,
        maxRotation: 0,
        color: '#475569',
        font: { size: 14 },
        callback: (_value: unknown, index: number) => {
          const point = points.value[index];
          return point
            ? new Date(point.timestamp).toLocaleTimeString('pt-BR', {
                hour: '2-digit',
                minute: '2-digit',
              })
            : '';
        },
      },
    },
    y: {
      beginAtZero: true,
      ticks: { maxTicksLimit: 5, color: '#475569', font: { size: 14 } },
      grid: { color: '#f1f5f9' },
    },
  },
};
</script>
<template>
  <div>
    <div class="pv-zoom">
      <label
        >Janela do gráfico
        <select
          v-model="minutes"
          aria-label="Janela do gráfico"
          @change="chosen = true"
        >
          <option :value="15">Últimos 15 min</option>
          <option :value="60">Última hora</option>
          <option :value="0">Período completo</option>
        </select></label
      >
      <p>Visível: {{ range }}</p>
    </div>
    <div class="pv-history-chart">
      <Line
        :data="data"
        :options="options"
        role="img"
        aria-label="Histórico de potência média em watts; lacunas não preenchidas"
      />
    </div>
  </div>
</template>
<style scoped>
.pv-zoom {
  padding: 0 1.71429rem;
  font-size: 1rem;
  color: #475569;
}
.pv-zoom select {
  min-height: 3.14286rem;
  font-size: 1.14286rem;
  width: auto;
  max-width: 100%;
}
.pv-zoom label {
  margin: 0;
  font-size: 1rem;
}
.pv-history-chart {
  height: 245px;
  padding: 8px 20px 18px;
}
</style>
