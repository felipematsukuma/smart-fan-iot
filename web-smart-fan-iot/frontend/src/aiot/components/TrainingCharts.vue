<script setup lang="ts">
import { computed } from 'vue';
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
        borderColor: '#81959e',
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
      title: { display: true, text: `Real (${props.unit})` },
    },
    y: {
      type: 'linear' as const,
      title: { display: true, text: `Previsto (${props.unit})` },
    },
  },
  plugins: { legend: { display: true } },
}));
const importance = computed(() => {
  const sorted = [...props.entry.feature_importance].sort(
    (a, b) => b.importance - a.importance,
  );
  return {
    labels: sorted.map((value) => value.feature),
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
      <div class="plot importance">
        <Bar
          :data="importance"
          :options="importanceOptions"
          role="img"
          aria-label="Importância por permutação dos 18 atributos observados"
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
              <th>Importância</th>
              <th>Desvio</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in entry.feature_importance" :key="item.feature">
              <td>{{ item.feature }}</td>
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
  font-size: 0.8rem;
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
  font-size: 0.75rem;
}
</style>
