<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { Line } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
  type TooltipModel,
} from 'chart.js';
import {
  readings,
  selectReading,
  chartSamples,
  type ReadingKey,
} from '../live-chart';
import type { FrameReadyV2 } from '../../lib/contracts-v2.generated';
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
);
const props = defineProps<{
  frames: FrameReadyV2[];
  pilot?: boolean;
  selected: ReadingKey[];
}>();
const emit = defineEmits<{ 'update:selected': [value: ReadingKey[]] }>();
const series = computed(() =>
  readings.filter((item) => props.selected.includes(item.key)),
);
const unit = computed(() => series.value[0]!.unit);
const mobile = ref(false);
const chartRef = ref<{ chart?: ChartJS<'line'> }>();
let pinned = false;
const chartArea = ref<HTMLElement>();
function dismissTooltip() {
  pinned = true;
  hover.value = null;
}
function outside(event: PointerEvent) {
  if (!chartArea.value?.contains(event.target as Node)) dismissTooltip();
}
function escape(event: KeyboardEvent) {
  if (event.key === 'Escape') dismissTooltip();
}
const tooltipNumber = (value: number) =>
  value.toLocaleString(
    'pt-BR',
    unit.value === '°C'
      ? { minimumFractionDigits: 1, maximumFractionDigits: 1 }
      : undefined,
  );
const hover = ref<{ title: string; lines: string[] } | null>(null);
let media: MediaQueryList;
const resize = () => {
  mobile.value = media.matches;
};
onMounted(() => {
  media = matchMedia('(max-width: 600px)');
  resize();
  media.addEventListener('change', resize);
  document.addEventListener('pointerdown', outside, true);
  document.addEventListener('keydown', escape);
});
onBeforeUnmount(() => {
  media?.removeEventListener('change', resize);
  document.removeEventListener('pointerdown', outside, true);
  document.removeEventListener('keydown', escape);
});
const visible = computed(() => {
  if (!props.pilot || !mobile.value) return props.frames;
  const end = Date.parse(props.frames.at(-1)?.timestamp ?? '');
  return props.frames.filter(
    (frame) => Date.parse(frame.timestamp) >= end - 60000,
  );
});
const range = computed(() =>
  visible.value.length
    ? `${new Date(visible.value[0]!.timestamp).toLocaleTimeString('pt-BR')} — ${new Date(visible.value.at(-1)!.timestamp).toLocaleTimeString('pt-BR')}`
    : 'Sem amostras',
);
const data = computed(() => chartSamples(visible.value, props.selected));
watch([() => props.selected, () => props.frames[0]?.dispositivo], () => {
  pinned = false;
  hover.value = null;
});
function inspectPoint(event: PointerEvent) {
  const chart = chartRef.value?.chart;
  if (!chart) return;
  const bounds = chart.canvas.getBoundingClientRect();
  const x = ((event.clientX - bounds.left) * chart.width) / bounds.width;
  const position = chart.scales.x?.getValueForPixel(x);
  if (position == null) return;
  const index = Math.round(position);
  const at = data.value.labels[index];
  if (!at) return;
  const lines = data.value.datasets
    .filter((item) => item.data[index] != null)
    .map((item) => `${item.label}: ${tooltipNumber(item.data[index]!)}`);
  pinned = true;
  hover.value = {
    title: at,
    lines: lines.length ? lines : ['Sem leituras neste instante'],
  };
}
const options = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: {
      mode: 'index' as const,
      intersect: false,
      enabled: false,
      external: ({ tooltip }: { tooltip: TooltipModel<'line'> }) => {
        if (pinned) return;
        hover.value = tooltip.opacity
          ? {
              title: tooltip.title.join(' '),
              lines: tooltip.dataPoints
                .filter((point) => point.parsed.y != null)
                .map(
                  (point) =>
                    `${point.dataset.label}: ${point.parsed.y == null ? 'Sem leitura' : tooltipNumber(point.parsed.y)}`,
                ),
            }
          : null;
      },
      callbacks: {
        label: (item: {
          dataset: { label?: string };
          parsed: { y: number | null };
        }) =>
          `${item.dataset.label}: ${item.parsed.y == null ? 'Sem leitura' : tooltipNumber(item.parsed.y)}`,
      },
      titleFont: { size: props.pilot ? 14 : 12 },
      bodyFont: { size: props.pilot ? 14 : 12 },
    },
  },
  scales: {
    x: {
      grid: { display: false },
      ticks: {
        maxTicksLimit: props.pilot && mobile.value ? 3 : 6,
        maxRotation: 0,
        color: props.pilot ? '#475569' : '#718892',
        font: { size: props.pilot ? 14 : 12 },
      },
    },
    y: {
      beginAtZero: unit.value !== '°C',
      title: {
        display: true,
        text: unit.value,
        color: '#475569',
        font: { size: 14 },
      },
      ticks: {
        maxTicksLimit: 5,
        color: props.pilot ? '#475569' : '#718892',
        font: { size: props.pilot ? 14 : 12 },
      },
      grid: { color: '#edf2f4' },
    },
  },
}));
</script>
<template>
  <div>
    <details class="pv-reading-picker">
      <summary>
        Leituras · {{ selected.length }}
        {{ selected.length === 1 ? 'selecionada' : 'selecionadas' }}
      </summary>
      <fieldset>
        <legend class="sr-only">Comparação de leituras</legend>

        <p>
          Até três temperaturas do mesmo equipamento. Outra grandeza substitui a
          seleção anterior; mantenha ao menos uma leitura.
        </p>
        <div class="pv-reading-options">
          <label v-for="item in readings" :key="item.key">
            <input
              type="checkbox"
              :checked="selected.includes(item.key)"
              :disabled="selected.length === 1 && selected.includes(item.key)"
              @change="
                emit('update:selected', selectReading(selected, item.key))
              "
            />
            {{ item.name }} ({{ item.unit }})
          </label>
        </div>
      </fieldset>
    </details>
    <ul class="pv-series-legend" aria-label="Legenda das leituras">
      <li v-for="item in series" :key="item.key" :data-series="item.key">
        <svg width="36" height="12" aria-hidden="true">
          <line
            x1="0"
            x2="36"
            y1="6"
            y2="6"
            :stroke="item.color"
            stroke-width="3"
            :stroke-dasharray="item.dash.join(' ')"
          />
        </svg>
        {{ item.name }} ({{ item.unit }})
      </li>
    </ul>
    <p v-if="pilot" class="pv-visible-range">
      Visível: {{ range }}<span v-if="mobile"> · até 1 min</span>
    </p>
    <div
      v-if="visible.length"
      ref="chartArea"
      class="power-chart"
      :data-series-count="series.length"
      :data-unit="unit"
      @pointerup="inspectPoint"
    >
      <Line
        ref="chartRef"
        :data="data"
        :options="options"
        role="img"
        :aria-label="`Leituras observadas: ${series.map((item) => item.name).join(', ')}, em ${unit}`"
      />
      <div v-if="hover" role="tooltip" class="pv-chart-tooltip">
        <strong>Consulta às {{ hover.title }}</strong>
        <div v-for="line in hover.lines" :key="line">{{ line }}</div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.pv-reading-picker fieldset {
  border: 0;
  padding: 0;
  margin: 0.5rem 0 0;
  min-width: 0;
}
.pv-reading-picker {
  margin: 0 1rem 1rem;
  border: 1px solid #64748b;
  border-radius: 0.5rem;
  padding: 0.75rem;
  min-width: 0;
}
.pv-reading-picker summary {
  user-select: none;
  cursor: pointer;
  min-height: 3.14286rem;
  display: list-item;
  align-content: center;
  font-size: 1.14286rem;
  font-weight: 650;
}
.pv-reading-picker p {
  font-size: 1rem;
  color: #475569;
}
.pv-reading-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.25rem 0.75rem;
}
.pv-reading-options label {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1rem;
  min-height: 3.14286rem;
  color: #334155;
}
.pv-reading-options input {
  padding: 0;
  width: 1.25rem;
  height: 1.25rem;
  margin: 0;
  flex-shrink: 0;
  accent-color: #0f766e;
}
.pv-series-legend {
  list-style: none;
  margin: 0;
  padding: 0 1rem 0.5rem;
  display: flex;
  gap: 0.5rem 1rem;
  flex-wrap: wrap;
}
.pv-series-legend li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #334155;
  font-size: 1rem;
}
.pv-series-legend svg {
  flex-shrink: 0;
}
.pv-selection-status {
  margin: 0;
  padding: 0 1rem 0.5rem;
}
@media (max-width: 600px) {
  .pv-reading-options {
    grid-template-columns: 1fr;
  }
}

.pv-visible-range {
  font-size: 1rem;
  color: #475569;
  margin: 0;
  padding: 0 1rem 0.75rem;
}
.pv-chart-tooltip {
  position: absolute;
  bottom: 3rem;
  left: 3rem;
  max-width: calc(100% - 4rem);
  padding: 0.75rem;
  background: #0f172a;
  color: white;
  border-radius: 0.5rem;
  font-size: 1rem;
  pointer-events: none;
}
.power-chart {
  position: relative;
  height: 260px;
  padding: 0 1rem 1rem;
}
</style>
