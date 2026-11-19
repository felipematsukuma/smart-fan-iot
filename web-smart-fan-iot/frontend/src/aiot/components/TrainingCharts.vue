<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { featureLabel } from '../job-presentation';
import { Bar, Scatter } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js';
import type { TargetReport } from '../training-types';
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
);
const props = defineProps<{ entry: TargetReport; unit: string }>();
const scatter = computed(() => {
  const values = props.entry.scatter.flatMap((value) => [
    value.real,
    value.predicted,
  ]);
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(1, ...values);
  return {
    datasets: [
      {
        label: 'Teste reservado',
        data: props.entry.scatter.map((value) => ({
          x: value.real,
          y: value.predicted,
        })),
        backgroundColor: '#147d8d',
        pointRadius: 3,
        showLine: false,
      },
      {
        label: 'Previsto = real',
        data: [
          { x: minimum, y: minimum },
          { x: maximum, y: maximum },
        ],
        borderColor: '#64748b',
        pointRadius: 0,
        showLine: true,
      },
    ],
  };
});
const scatterOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  scales: {
    x: {
      type: 'linear' as const,
      ticks: { color: '#475569', font: { size: 14 } },
      title: {
        display: true,
        color: '#475569',
        font: { size: 14 },
        text: `Real (${props.unit})`,
      },
    },
    y: {
      type: 'linear' as const,
      ticks: { color: '#475569', font: { size: 14 } },
      title: {
        display: true,
        color: '#475569',
        font: { size: 14 },
        text: `Previsto (${props.unit})`,
      },
    },
  },
  plugins: {
    legend: { display: true, labels: { color: '#475569', font: { size: 14 } } },
  },
}));
const mobile = ref(false);
let query: MediaQueryList | undefined;
const updateSize = () => {
  mobile.value = query?.matches ?? false;
};
onMounted(() => {
  query = matchMedia('(max-width: 600px)');
  updateSize();
  query.addEventListener('change', updateSize);
});
onBeforeUnmount(() => query?.removeEventListener('change', updateSize));
const ranked = computed(() =>
  [...props.entry.feature_importance].sort(
    (a, b) => b.importance - a.importance,
  ),
);
const visibleImportance = computed(() =>
  mobile.value ? ranked.value.slice(0, 5) : ranked.value,
);
function chartLabel(feature: string) {
  const label = featureLabel(feature);
  if (label.includes(' · ')) return label.split(' · ');
  if (label === 'Diferença carcaça–exterior')
    return ['Diferença', 'carcaça–exterior'];
  return label;
}
const importance = computed(() => {
  const sorted = visibleImportance.value;
  return {
    labels: sorted.map((value) => chartLabel(value.feature)),
    datasets: [
      {
        label: 'Aumento do MAE ao permutar',
        data: sorted.map((value) => value.importance),
        backgroundColor: sorted.map((value) =>
          value.importance >= 0 ? '#147d8d' : '#a27758',
        ),
      },
    ],
  };
});
const importanceOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  indexAxis: 'y' as const,
  scales: {
    x: { ticks: { color: '#475569', font: { size: 14 } } },
    y: { ticks: { autoSkip: false, color: '#475569', font: { size: 14 } } },
  },
  plugins: { legend: { display: false } },
};
</script>
<template>
  <div class="training-plots">
    <section>
      <h3>Previsto × real</h3>
      <div class="plot">
        <Scatter
          :data="scatter"
          :options="scatterOptions"
          role="img"
          :aria-label="`Previsto versus real, ${unit}; até 200 pontos do teste reservado`"
        />
      </div>
      <details>
        <summary>Valores do gráfico</summary>
        <table>
          <caption>
            Primeiros 20 pontos do teste reservado.
          </caption>
          <thead>
            <tr>
              <th>Real</th>
              <th>Previsto</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(point, index) in entry.scatter.slice(0, 20)"
              :key="index"
            >
              <td>{{ point.real.toFixed(3) }}</td>
              <td>{{ point.predicted.toFixed(3) }}</td>
            </tr>
          </tbody>
        </table>
      </details>
    </section>
    <section>
      <h3>Importância dos atributos</h3>
      <p v-if="mobile" class="tp-muted">Cinco atributos de maior importância</p>
      <div
        class="plot importance"
        :style="{
          height: `${mobile ? 340 : Math.max(430, visibleImportance.length * 42)}px`,
        }"
      >
        <Bar
          :data="importance"
          :options="importanceOptions"
          role="img"
          :aria-label="`Importância por permutação: ${visibleImportance.length} de ${entry.feature_importance.length} atributos; lista completa em tabela`"
        />
      </div>
      <p>
        Calculada na validação, sem novo ajuste. Valores negativos podem indicar
        ruído.
      </p>
      <details>
        <summary>Importâncias em tabela</summary>
        <table>
          <caption>
            Variação de MAE e desvio das repetições.
          </caption>
          <thead>
            <tr>
              <th>Atributo</th>
              <th>Nome técnico</th>
              <th>Importância</th>
              <th>Desvio</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in entry.feature_importance" :key="item.feature">
              <td>{{ featureLabel(item.feature) }}</td>
              <td>
                <code>{{ item.feature }}</code>
              </td>
              <td>{{ item.importance.toFixed(4) }}</td>
              <td>{{ item.std.toFixed(4) }}</td>
            </tr>
          </tbody>
        </table>
      </details>
    </section>
  </div>
</template>
<style scoped>
.training-plots {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 350px), 1fr));
  gap: 1.5rem;
  margin-top: 1.5rem;
}
.plot {
  height: 320px;
}
.importance {
  height: 430px;
}
.training-plots p {
  font-size: 1rem;
  line-height: 1.5;
}
details {
  margin: 0.7rem 0;
  overflow: auto;
}
summary {
  cursor: pointer;
}
table {
  font-size: 1rem;
}
</style>
