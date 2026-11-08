<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Line } from 'vue-chartjs';
import { AlertTriangle } from 'lucide-vue-next';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';
import type { MetricPoint, SeriesSegment } from '../../types';
import {
  buildTimeline,
  computeCoverage,
  computeStats,
  axisTickCandidates,
  DEFAULT_CEILING,
  dedupeLabels,
  formatDuration,
  nextScaleState,
  type PeakAnchor,
  type YScale,
} from '../../lib/chartRules';
import { formatCoverage } from '../../lib/format';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

const props = defineProps<{
  coverage?: number;
  sourceSegments?: SeriesSegment[];
  rawMean?: number;
  rawMaximum?: number;
  rawCount?: number;
  currentPower: number;
  timestamp: number;
  history: MetricPoint[];
  appendLive?: boolean;
  multiDay?: boolean;
  periodLabel?: string;
  /** Início da janela analisada (ISO 8601). Define quando um pico sai do período. */
  periodStart?: string;
  /** Fim da janela analisada (ISO 8601). Fecha o eixo temporal. */
  periodEnd?: string;
}>();

/**
 * Pontos mantidos em memória pelo gráfico.
 *
 * TEM de acompanhar `MAX_HISTORY_POINTS` do backend (`backend/app/main.py`).
 * Não é um limite de renderização: o backend já reamostra a série, e cortar de
 * novo aqui jogaria fora justamente a resolução das rajadas — foi o que
 * produzia os espinhos de 1 px na janela de 7 dias.
 *
 * O Canvas desenha 240 pontos sem esforço; a compressão do eixo é que faz o
 * trabalho de legibilidade.
 */
const MAX_POINTS = 240;

/** Item do tooltip já normalizado, para não repetir o tipo em cada callback. */
interface TooltipLineItem {
  datasetIndex: number;
  parsed: { x: number | null; y: number | null };
}
const FALLBACK: Record<
  'light' | 'dark',
  Record<string, [number, number, number]>
> = {
  light: {
    '--chart-1': [46, 156, 138],
    '--chart-2': [31, 168, 119],
    '--muted-foreground': [93, 120, 121],
    '--border': [198, 220, 216],
    '--popover': [255, 255, 255],
    '--foreground': [25, 48, 57],
  },
  dark: {
    '--chart-1': [120, 214, 194],
    '--chart-2': [124, 224, 172],
    '--muted-foreground': [165, 193, 192],
    '--border': [58, 84, 90],
    '--popover': [32, 52, 58],
    '--foreground': [230, 244, 240],
  },
};

/** O canvas não resolve `var(--x)` nem `color-mix()`, então as cores do tema
 * precisam ser materializadas em RGB reais.
 *
 * Os tokens são declarados em hex (`#20343a`), portanto não basta concatenar
 * em `rgb(...)`: é preciso deixar o próprio parser do browser aceitar o valor
 * e ler de volta a cor computada. Aceitamos hex, `rgb()`, `hsl()` e a forma
 * `r, g, b` usada nos fallbacks. */
const SENTINEL = 'rgb(1, 2, 3)';

const resolveToken = (name: string): [number, number, number] => {
  const dark = document.documentElement.classList.contains('dark');
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  const fallback = (dark ? FALLBACK.dark : FALLBACK.light)[name] ?? [0, 0, 0];
  if (!raw) return fallback;

  const probe = document.createElement('span');
  probe.style.display = 'none';
  document.body.appendChild(probe);

  probe.style.color = SENTINEL;
  probe.style.color = raw;
  let resolved = getComputedStyle(probe).color;
  if (resolved === SENTINEL) {
    // Não parseou (ex.: "120, 214, 194") — tenta a forma explícita rgb().
    probe.style.color = `rgb(${raw})`;
    resolved = getComputedStyle(probe).color;
  }
  probe.remove();

  const parts = resolved.match(/[\d.]+/g);
  if (!parts || parts.length < 3 || resolved === SENTINEL) return fallback;
  return [Number(parts[0]), Number(parts[1]), Number(parts[2])];
};

const readTheme = () => ({
  power: resolveToken('--chart-1'),
  average: resolveToken('--chart-2'),
  tick: resolveToken('--muted-foreground'),
  grid: resolveToken('--border'),
  popover: resolveToken('--popover'),
  foreground: resolveToken('--foreground'),
});

const theme = ref(readTheme());

const rgba = ([r, g, b]: [number, number, number], alpha: number) =>
  `rgba(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}, ${alpha})`;

const refreshTheme = () => {
  theme.value = readTheme();
};

let themeObserver: MutationObserver | null = null;
onMounted(() => {
  refreshTheme();
  themeObserver = new MutationObserver(refreshTheme);
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  });
});
onBeforeUnmount(() => themeObserver?.disconnect());

/** Rótulo de um instante. Em janelas longas mostra o dia, para não repetir a
 *  mesma hora em dias diferentes. */
const formatInstant = (ms: number) =>
  new Date(ms).toLocaleString('pt-BR', {
    day: props.multiDay ? '2-digit' : undefined,
    month: props.multiDay ? '2-digit' : undefined,
    hour: '2-digit',
    minute: '2-digit',
  });

const powerGradient = (context: { chart: ChartJS }) => {
  const { ctx, chartArea } = context.chart;
  const color = theme.value.power;
  if (!chartArea) return rgba(color, 0.24);
  const gradient = ctx.createLinearGradient(
    0,
    chartArea.top,
    0,
    chartArea.bottom,
  );
  gradient.addColorStop(0, rgba(color, 0.32));
  gradient.addColorStop(0.95, rgba(color, 0.02));
  return gradient;
};

const bandGradient = (context: { chart: ChartJS }) => {
  const { ctx, chartArea } = context.chart;
  const color = theme.value.average;
  if (!chartArea) return 'rgba(0, 0, 0, 0)';
  const gradient = ctx.createLinearGradient(
    0,
    chartArea.top,
    0,
    chartArea.bottom,
  );
  gradient.addColorStop(0, rgba(color, 0.16));
  gradient.addColorStop(1, rgba(color, 0.04));
  return gradient;
};

/** Potência de cada amostra e o instante correspondente (epoch ms). */
const values = ref<number[]>([]);
const times = ref<number[]>([]);

/** Limites reais da janela analisada. O eixo temporal usa ESTES limites, e não
 * o intervalo das amostras: é isso que faz 6 h sem telemetria aparecerem como
 * espaço vazio em vez de serem comprimidas fora da vista. */
const windowStartMs = computed(() => {
  const parsed = props.periodStart
    ? new Date(props.periodStart).getTime()
    : NaN;
  if (Number.isFinite(parsed)) return parsed;
  return times.value.length ? times.value[0] : Date.now();
});
const windowEndMs = computed(() => {
  const parsed = props.periodEnd ? new Date(props.periodEnd).getTime() : NaN;
  if (Number.isFinite(parsed)) return parsed;
  const last = times.value.length
    ? times.value[times.value.length - 1]
    : Date.now();
  return Math.max(last, windowStartMs.value + 1);
});

/**
 * Linha do tempo COMPRIMIDA.
 *
 * O eixo X não é mais tempo real: trechos em que o ventilador estava
 * desligado, ou em que o ESP32 simplesmente não reportou, são espremidos para
 * uma largura fixa. O que sobra de largura vai para os trechos em que houve
 * medição, que é o que interessa.
 *
 * Sem isso, a janela de 7 dias era 1,4% de atividade espalhada no meio de um
 * gráfico quase vazio — ilegível, e era o defeito relatado.
 */
const timeline = computed(() =>
  buildTimeline(times.value, values.value, {
    windowStartMs: windowStartMs.value,
    windowEndMs: windowEndMs.value,
    sourceSegments: props.sourceSegments,
  }),
);

/** Cobertura medida em TEMPO REAL — a compressão é visual, não contábil. */
const coverage = computed(
  () =>
    props.coverage ??
    computeCoverage(times.value, windowStartMs.value, windowEndMs.value),
);
const hasCoverageGap = computed(() => coverage.value < 0.98);

/** Duração da janela em horas, arredondada. Só para o rótulo curto. */
const windowHours = computed(() =>
  Math.max(
    1,
    Math.round((windowEndMs.value - windowStartMs.value) / 3_600_000),
  ),
);

/** "de 8h", "de 24h", "de 168h". Sem ruído decimal, como os atalhos da API. */
const windowLength = computed(() => `${windowHours.value}h`);

/**
 * Detalhe da cobertura, no `title` da linha curta.
 *
 * Fica fora da tela porque ocupa espaço e polui o cabeçalho, mas continua
 * acessível: é onde se explica que o eixo é comprimido e que uma linha
 * contínua atravessando um trecho comprimido é interpolação.
 */
const coverageDetail = computed(() => {
  const linhas = [
    `Cobertura de ${formatCoverage(coverage.value)} da janela de ${windowLength.value}.`,
    `Sem telemetria: ${formatDuration(timeline.value.noDataMs)}.`,
  ];
  if (timeline.value.offMs > 0) {
    linhas.push(
      `Ventilador desligado: ${formatDuration(timeline.value.offMs)}.`,
    );
  }
  linhas.push(
    'O eixo comprime intervalos desligados e sem dados. Lacunas reais interrompem a linha; a cobertura é calculada antes da redução visual.',
  );
  return linhas.join(' ');
});

const stats = computed(() => computeStats(values.value));
const mean = computed(() => props.rawMean ?? stats.value.mean);
const deviation = computed(() => stats.value.deviation);
const maximum = computed(() => props.rawMaximum ?? stats.value.max);

/** No período personalizado o rótulo fixo não serve, então o intervalo real
 *  é exibido no rodapé. */
const isCustomPeriod = computed(
  () => props.periodLabel === 'Período personalizado',
);
const samplesCount = computed(() => props.rawCount ?? props.history.length);

const range = computed(() => {
  const s = new Date(windowStartMs.value).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
  const e = new Date(windowEndMs.value).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
  return `${s} — ${e}`;
});

const buildDatasets = () => {
  const { power, average } = theme.value;
  const low = Math.max(0, mean.value - deviation.value);
  const high = Math.min(axisMaximum.value, mean.value + deviation.value);
  // Mesmo esqueleto com quebras, mas com o nível constante: a faixa de desvio
  // e a média também não podem atravessar um trecho interrompido.
  const flatAt = (level: number) =>
    timeline.value.points.map((p) => ({
      x: p.x,
      y: p.y === null ? null : level,
    }));

  return [
    {
      label: 'Potência',
      data: timeline.value.points,
      borderColor: rgba(power, 1),
      backgroundColor: powerGradient as never,
      fill: true,
      // `connectGaps` liga a linha através dos trechos comprimidos (leitura do
      // InfluxDB, e o que foi pedido). Não há `null` na série, então a opção é
      // irrelevante aqui — mas fica explícita caso a série volte a ter quebras.
      spanGaps: false,
      tension: 0.35,
      // Sem marcadores de amostra: os trechos desligados não entram como 0 W,
      // e as rajadas viram linha, não pontos soltos.
      pointRadius: 0,
      pointHitRadius: 6,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: rgba(power, 1),
      pointHoverBorderColor: rgba(power, 1),
      borderWidth: 2,
    },
    {
      label: 'Média',
      data: flatAt(mean.value),
      borderColor: rgba(average, 1),
      backgroundColor: 'transparent',
      borderDash: [6, 6],
      fill: false,
      spanGaps: false,
      tension: 0.35,
      pointRadius: 0,
      pointHoverRadius: 0,
      borderWidth: 1.5,
    },
    {
      label: 'Desvio superior',
      data: flatAt(high),
      borderColor: 'rgba(0, 0, 0, 0)',
      backgroundColor: bandGradient as never,
      fill: '+1',
      spanGaps: false,
      tension: 0.35,
      pointRadius: 0,
      pointHoverRadius: 0,
      borderWidth: 0,
    },
    {
      label: 'Desvio inferior',
      data: flatAt(low),
      borderColor: 'rgba(0, 0, 0, 0)',
      backgroundColor: 'rgba(0, 0, 0, 0)',
      fill: false,
      spanGaps: false,
      tension: 0.35,
      pointRadius: 0,
      pointHoverRadius: 0,
      borderWidth: 0,
    },
  ];
};

const chartData = computed(() => ({ datasets: buildDatasets() }));

/**
 * Rótulos do eixo X, já filtrados contra repetição.
 *
 * Rótulos repetidos ("28/09 15:42" duas vezes) não informam nada e ainda
 * empurram os vizinhos para fora da tela.
 */
const axisLabels = computed(() => {
  const timelineNow = timeline.value;
  const raw = axisTickCandidates(timelineNow, props.multiDay ? 7 : 8);
  return dedupeLabels(raw.map((x) => formatInstant(timelineNow.realAt(x))));
});

/* ------------------------------------------------------------------ *
 * Escala dinâmica do eixo Y com histerese.
 *
 * A regra mora em `lib/chartRules.ts` (puro e testado). Aqui só guardamos o
 * estado e reagimos às mudanças de dados. Ver o módulo para a justificativa de
 * por que ancoramos o pico pelo instante em vez de usar `Math.max` a cada
 * leitura.
 * ------------------------------------------------------------------ */
const yScale = ref<YScale>({ max: DEFAULT_CEILING });
const axisMaximum = computed(() =>
  props.rawMaximum === undefined ? yScale.value.max : props.rawMaximum + 10,
);
/** Pico que sustenta o teto atual, com o instante em que ocorreu. */
const peakAnchor = ref<PeakAnchor | null>(null);

const updateYScale = () => {
  const next = nextScaleState(
    { scale: yScale.value, anchor: peakAnchor.value },
    values.value,
    times.value,
    windowStartMs.value,
  );
  yScale.value = next.scale;
  peakAnchor.value = next.anchor;
};

const replaceHistory = (history: MetricPoint[]) => {
  const points = history.slice(-MAX_POINTS);
  times.value = points.map((point) => new Date(point.time).getTime());
  values.value = points.map((point) => point.power_w);
  updateYScale();
};

const appendPoint = (power: number, time: Date) => {
  times.value = [...times.value, time.getTime()];
  values.value = [...values.value, power];
  if (times.value.length > MAX_POINTS) {
    times.value.shift();
    values.value.shift();
  }
  updateYScale();
};

watch(() => props.history, replaceHistory, { immediate: true });
watch(
  () => props.multiDay,
  () => replaceHistory(props.history),
);
// Trocar de período move o início da janela: o pico pode ter saído dele.
watch(
  () => props.periodStart,
  () => updateYScale(),
);

let lastTimestamp = props.timestamp;
watch(
  () => props.timestamp,
  (timestamp) => {
    if (props.appendLive === false || !timestamp || timestamp === lastTimestamp)
      return;
    lastTimestamp = timestamp;
    appendPoint(props.currentPower, new Date());
  },
);

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  interaction: { mode: 'index' as const, intersect: false },
  layout: { padding: { top: 8, right: 8, left: 0, bottom: 0 } },
  plugins: {
    legend: { display: false },
    tooltip: {
      enabled: true,
      displayColors: false,
      // Só a série de potência entra no tooltip. A média e a diferença são
      // compostas no rodapé, para o corpo ficar com UMA linha — a que o
      // usuário lê primeiro e em destaque.
      filter: (item: { datasetIndex: number }) => item.datasetIndex === 0,
      backgroundColor: rgba(theme.value.popover, 1),
      // Hierarquia: horário discreto no topo, valor em destaque no corpo,
      // comparação discreta no rodapé.
      titleColor: rgba(theme.value.tick, 1),
      titleFont: { size: 11, weight: 500 },
      bodyColor: rgba(theme.value.foreground, 1),
      bodyFont: {
        size: 17,
        weight: 700,
        family: getComputedStyle(document.body).fontFamily,
      },
      footerColor: rgba(theme.value.average, 1),
      footerFont: { size: 11, weight: 400 },
      borderColor: rgba(theme.value.grid, 1),
      borderWidth: 1,
      padding: 12,
      cornerRadius: 12,
      caretSize: 6,
      caretPadding: 8,
      titleMarginBottom: 2,
      footerMarginTop: 4,
      display: 'auto' as const,
      callbacks: {
        title: (items: unknown[]) => {
          const first = items[0] as { parsed?: { x?: number } } | undefined;
          const x = first?.parsed?.x;
          if (typeof x !== 'number') return '';
          return formatInstant(timeline.value.realAt(x));
        },
        label: (context: { parsed: { y: number | null } }) =>
          `${(context.parsed.y ?? 0).toFixed(1)} W`,
        footer: (items: TooltipLineItem[]) => {
          const power = items[0]?.parsed.y;
          if (power === null || power === undefined) return '';
          const average = mean.value;
          const diff = power - average;
          const sinal = diff >= 0 ? '+' : '−';
          return `Média ${average.toFixed(1)} W • ${sinal}${Math.abs(diff).toFixed(1)} W`;
        },
      },
    },
  },
  scales: {
    x: {
      // Eixo do TEMPO COMPRIMIDO: a posição já não é epoch-ms, é a coordenada
      // do eixo. Os rótulos são reconvertidos para o instante real, senão o
      // usuário leria horas erradas.
      //
      // Um eixo por categorias compactaria o período sem telemetria e faria
      // 2 h de dados parecerem 8 h. E um eixo em tempo real puro desperdiçaria
      // a largura: em 7 dias, 98,6% da janela não teve medição.
      type: 'linear' as const,
      min: 0,
      max: timeline.value.axisMs,
      grid: { display: false },
      border: { display: false },
      // Num eixo comprimido os ticks automáticos do Chart.js ficariam errados:
      // ele escolhe valores uniformes no eixo, e como o tempo real não é
      // uniforme, os rótulos saíam todos colados no fim. Substituímos a lista
      // inteira por posições que sabemos bem distribuídas no eixo.
      afterBuildTicks: (axis: { ticks: Array<{ value: number }> }) => {
        axis.ticks = axisTickCandidates(
          timeline.value,
          props.multiDay ? 7 : 8,
        ).map((value) => ({ value }));
      },
      ticks: {
        color: rgba(theme.value.tick, 1),
        font: { size: 11 },
        maxRotation: 0,
        autoSkip: false,
        padding: 6,
        // O rótulo já vem pronto de `axisLabels`, deduplicado: dois "28/09
        // 15:42" lado a lado só gastam espaço e não informam nada.
        callback: (value: number | string) => {
          const position = axisTickCandidates(
            timeline.value,
            props.multiDay ? 7 : 8,
          ).indexOf(Number(value));
          return position >= 0 ? axisLabels.value[position] : '';
        },
      },
    },
    y: {
      beginAtZero: true,
      max: axisMaximum.value,
      border: { display: false },
      grid: { color: rgba(theme.value.grid, 0.6), drawTicks: false },
      // Sem stepSize fixo: o Chart.js escolhe degraus "bonitos" (2/5/10/20/25…)
      // dentro de [0, teto], preservando a folga exata de HEADROOM_W.
      ticks: {
        color: rgba(theme.value.tick, 1),
        font: { size: 11 },
        padding: 10,
        maxRotation: 0,
        // O topo do eixo é `pico + folga` e por isso quase nunca cai num
        // múltiplo do degrau (ex.: 101,44 W). O rótulo da própria fronteira
        // ficaria arbitrário no lugar do próximo degrau redondo, então ele é
        // omitido. O "0 W" e os degraus intermediários seguem normais.
        callback: (value: number | string) => {
          const numeric = Number(value);
          if (Math.abs(numeric - axisMaximum.value) < 1e-6 && numeric !== 0)
            return '';
          return `${value} W`;
        },
      },
    },
  },
}));
</script>

<template>
  <section class="power-chart-card">
    <header class="chart-header">
      <div>
        <h2>Potência instantânea (W)</h2>
        <p>Janela analisada: {{ range }}</p>
        <!-- Linha curta de propósito. O detalhe fica no title, que não ocupa
             espaço na tela mas preserva a explicação do que a cobertura e a
             compressão do eixo significam. -->
        <p
          v-if="hasCoverageGap"
          class="coverage-note"
          role="status"
          :title="coverageDetail"
        >
          <AlertTriangle :size="12" />
          Cobertura de {{ formatCoverage(coverage) }} de {{ windowLength }}
        </p>
      </div>
      <div class="chart-legend">
        <span><i class="dot-power" /> Potência</span>
        <span><i class="dot-average" /> Média</span>
        <span class="legend-badge">Linha + média</span>
        <span
          class="legend-badge is-scale"
          title="Teto do eixo Y: pico + 10 W, mantido até o pico sair da janela"
        >
          Escala 0–{{ axisMaximum.toFixed(0) }} W
        </span>
      </div>
    </header>

    <div class="chart-stats">
      <div>
        <span>Média</span><strong>{{ mean.toFixed(1) }} W</strong>
      </div>
      <div>
        <span>Máxima</span><strong>{{ maximum.toFixed(1) }} W</strong>
      </div>
    </div>

    <div class="chart-canvas">
      <Line :data="chartData" :options="chartOptions" />
      <p v-if="values.length === 0" class="empty-chart">
        Aguardando telemetria do ESP32…
      </p>
    </div>

    <footer class="chart-footer">
      <span>
        {{ periodLabel }}
        <!-- Período personalizado: o rótulo sozinho não diz nada, então o
             intervalo real vem logo abaixo. -->
        <small v-if="isCustomPeriod" class="period-range">{{ range }}</small>
      </span>
      <span class="tabular">
        {{ samplesCount }} amostras · cobertura {{ formatCoverage(coverage) }}
      </span>
    </footer>
  </section>
</template>

<style scoped>
.power-chart-card {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  box-shadow: var(--shadow-card);
}
.chart-header {
  display: flex;
  /* `baseline` alinha a legenda com o título pela linha de base do texto.
     Com `center`, a legenda ficava centrada no bloco inteiro (título +
     subtítulo + nota) e descia ~1 linha abaixo do "Potência instantânea". */
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  padding: 1.1rem 1.25rem;
  border-bottom: 1px solid var(--border);
}
.chart-header h2 {
  margin: 0;
  color: var(--foreground);
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.chart-header p {
  margin: 0.25rem 0 0;
  color: var(--muted-foreground);
  font-size: 0.75rem;
}
.coverage-note {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  /* Linha curta: o detalhe fica no title. */
  max-width: 100%;
  color: var(--offline) !important;
  line-height: 1.4;
  /* Deixa claro que há mais informação escondida. */
  cursor: help;
  border-bottom: 1px dotted color-mix(in srgb, var(--offline) 55%, transparent);
}
.coverage-note svg {
  flex: 0 0 auto;
}
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.35rem 1rem;
  color: var(--muted-foreground);
  font-size: 0.68rem;
  /* O badge tem borda e padding, então a caixa fica mais alta que a linha do
     texto. Sem esta margem, ele empurra a linha de base da legenda para baixo
     e desalinha do título. */
  margin-bottom: -0.2rem;
}
.chart-legend > span {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.chart-legend i {
  display: block;
}
.dot-power {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  background: var(--chart-1);
}
.dot-average {
  width: 1rem;
  height: 1px;
  border-top: 1px dashed var(--online);
}
.legend-badge {
  border: 1px solid var(--border);
  border-radius: 0.35rem;
  padding: 0.2rem 0.55rem;
  background: var(--surface-raised);
  color: var(--foreground);
  font-size: 0.6rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.legend-badge.is-scale {
  border-color: color-mix(in srgb, var(--primary) 40%, var(--border));
  background: color-mix(in srgb, var(--primary) 12%, var(--surface-raised));
  color: var(--primary);
  font-variant-numeric: tabular-nums;
}
.chart-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  border-top: 1px solid var(--border);
  padding: 0.7rem 1.25rem;
  color: var(--muted-foreground);
  font-size: 0.68rem;
}
/* No período personalizado o intervalo real vem abaixo do rótulo. */
.period-range {
  display: block;
  margin-top: 0.15rem;
  color: var(--foreground);
  font-size: 0.66rem;
  font-variant-numeric: tabular-nums;
}
.chart-footer > span:first-child {
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.chart-footer .tabular {
  font-variant-numeric: tabular-nums;
}
.chart-stats {
  display: grid;
  /* Dois campos apenas (média e máxima). A grade acompanha a quantidade real
     de itens para que não sobrasse coluna vazia. */
  grid-template-columns: repeat(2, 1fr);
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--background) 40%, transparent);
}
.chart-stats div {
  padding: 0.7rem 1rem;
  border-right: 1px solid var(--border);
}
.chart-stats div:last-child {
  border-right: 0;
}
.chart-stats span {
  display: block;
  color: var(--muted-foreground);
  font-size: 0.56rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.chart-stats strong {
  display: block;
  margin-top: 0.25rem;
  color: var(--foreground);
  font-family: var(--font-display);
  font-size: 0.875rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.chart-canvas {
  position: relative;
  height: 288px;
  padding: 1.5rem 1rem 1.5rem;
  cursor: crosshair;
}
.chart-canvas canvas {
  display: block;
}
@media (min-width: 1024px) {
  .chart-canvas {
    height: 384px;
    padding: 1.5rem 1.5rem 1.75rem;
  }
}
.empty-chart {
  position: absolute;
  inset: 45% 0 auto;
  color: var(--muted-foreground);
  font-size: 0.8rem;
  text-align: center;
  pointer-events: none;
}
@media (max-width: 700px) {
  .chart-stats div {
    padding: 0.6rem 0.75rem;
  }
  .chart-header {
    padding: 0.9rem 1rem;
  }
  .chart-footer {
    padding: 0.65rem 1rem;
  }
}
</style>
