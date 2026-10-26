/**
 * Regras puras do gráfico de potência.
 *
 * Ficam fora do componente de propósito: assim são testáveis sem DOM, sem
 * Chart.js e sem Vue. O `PowerChart.vue` só compõe estado reativo em cima
 * destas funções.
 */

/** Folga em W acima do pico para o topo do eixo Y. */
export const HEADROOM_W = 10;

/** Teto usado antes de haver qualquer amostra. */
export const DEFAULT_CEILING = 40;

/** Teto mínimo, para o eixo não degenerar quando a potência é ~0. */
export const MIN_CEILING = 5;

/**
 * Lacuna a partir da qual consideramos não haver cobertura do dispositivo.
 * Mesma ordem de grandeza da tolerância de integração de energia do backend
 * (80 s): acima disso não sabemos o que o ventilador estava fazendo.
 */
export const COVERAGE_GAP_LIMIT_MS = 90_000;

/**
 * Potência abaixo da qual o relé está aberto.
 *
 * O firmware só zera a potência quando o ventilador está realmente desligado
 * (`power_w = is_on ? I * V * FP : 0`), então 0 W é sinal de desligamento, e
 * não de ruido. A folga de 0,5 W absorve arredondamento de ponto flutuante.
 */
export const OFF_POWER_W = 0.5;

/**
 * Duração mínima a 0 W para classificar o trecho como "desligado".
 *
 * Abaixo disso pode ser uma leitura isolada, e interromper o gráfico por causa
 * de uma amostra só apagaria um pico real.
 */
export const MIN_OFF_DURATION_MS = 30_000;

/**
 * Largura MÍNIMA de um trecho interrompido, em unidades de eixo.
 *
 * O gráfico NÃO usa mais tempo real no eixo X. Trechos em que nada foi medido
 * — ventilador desligado ou sem telemetria — são comprimidos, e a largura que
 * sobra vai para o que realmente aconteceu. É o que torna a janela de 7 dias
 * legível: sem isso, 2,4 h de atividade ocupavam 1,4% da largura.
 *
 * O valor está em "ms de eixo", não em pixels, para não depender da resolução.
 * Serve de PISO, para que um vão de poucos segundos não desapareça.
 * Ver `chooseCompressedSpan`.
 */
export const COMPRESSED_SPAN_MS = 45_000;

/**
 * Fração do eixo que idealmente os trechos interrompidos ocupariam, se
 * houvesse espaço para todos sem atrapalhar. É uma preferência, não um limite.
 */
export const TARGET_GAP_AXIS_FRACTION = 0.15;

/**
 * Escolhe a largura de cada trecho interrompido.
 *
 * A única exigência é que a série real domine a largura. Como o gráfico não
 * usa marcadores, não existe a restrição de separar visualmente uma
 * interrupção da outra: um trecho muito estreito vira uma descida quase
 * vertical, que é exatamente como o InfluxDB desenha.
 */
export function chooseCompressedSpan(activeTotalMs: number, gapCount: number): number {
  if (gapCount <= 0 || !(activeTotalMs > 0)) return COMPRESSED_SPAN_MS;
  const target = (activeTotalMs * TARGET_GAP_AXIS_FRACTION) / gapCount;
  return Math.max(COMPRESSED_SPAN_MS, target);
}

/** Motivo de um trecho interrompido. */
export type GapReason = 'off' | 'no-data';

export interface Gap {
  reason: GapReason;
  /** Instante real do início do trecho. */
  from: number;
  /** Instante real do fim do trecho. */
  to: number;
  /** Posição no eixo comprimido onde o trecho começa. */
  xFrom: number;
  /** Posição no eixo comprimido onde o trecho termina. */
  xTo: number;
}

export interface YScale {
  max: number;
}

export interface PeakAnchor {
  /** Instante (epoch ms) em que o pico ocorreu. */
  at: number;
  /** Valor do pico em W. */
  power: number;
}

export interface Point {
  x: number;
  y: number | null;
}

/**
 * Teto do eixo Y: `pico + HEADROOM_W`, sem arredondar.
 *
 * Arredondar para múltiplo do degrau inflava o topo (pico 91,4 W virava teto
 * 125 W) e achatava visualmente séries de baixa potência. Os ticks continuam
 * redondos porque o Chart.js escolhe os próprios degraus dentro do intervalo.
 */
export function ceilingFor(max: number): number {
  return Math.max(max + HEADROOM_W, MIN_CEILING);
}

export interface ScaleState {
  scale: YScale;
  anchor: PeakAnchor | null;
}

/**
 * Decide o teto do eixo Y com histerese.
 *
 * Regra: o teto é `pico + folga` e só muda quando o ponto de pico sai da janela
 * analisada — podendo subir ou descer.
 *
 * Ancoramos no pico COM o seu instante porque o backend reamostra o histórico
 * por índice: um pico real pode sair do subconjunto exibido sem ter saído da
 * janela. Guardando o instante, a queda do teto acontece exatamente quando
 * `windowStartMs` ultrapassa o pico.
 */
export function nextScaleState(
  state: ScaleState,
  values: number[],
  times: number[],
  windowStartMs: number
): ScaleState {
  // 1. O pico que sustentava o teto saiu da janela?
  if (state.anchor && state.anchor.at < windowStartMs) {
    state = { scale: { max: DEFAULT_CEILING }, anchor: null };
  }

  if (!values.length) {
    return { scale: { max: DEFAULT_CEILING }, anchor: null };
  }

  const currentMax = Math.max(...values);

  // 2. Pico novo (maior que o vigente)? Ancora e sobe imediatamente.
  if (!state.anchor || currentMax > state.anchor.power) {
    const index = values.indexOf(currentMax);
    const at = index >= 0 ? (times[index] ?? windowStartMs) : windowStartMs;
    return { scale: { max: ceilingFor(currentMax) }, anchor: { at, power: currentMax } };
  }

  // 3. O pico vigente continua na janela: mantém o teto, mesmo que ele não
  //    apareça no subconjunto atual (reamostragem por índice).
  return { scale: { max: ceilingFor(state.anchor.power) }, anchor: state.anchor };
}

export interface TimelineOptions {
  gapLimitMs?: number;
  offPowerW?: number;
  minOffDurationMs?: number;
  windowStartMs?: number;
  windowEndMs?: number;
}

/** Trecho contíguo da janela, com posição real e posição no eixo comprimido. */
export interface Segment {
  kind: 'active' | GapReason;
  /** Instante real do início. */
  from: number;
  /** Instante real do fim. */
  to: number;
  /** Posição no eixo comprimido onde o trecho começa. */
  xFrom: number;
  /** Posição no eixo comprimido onde o trecho termina. */
  xTo: number;
}

export interface Timeline {
  /** Pontos da série de potência, em coordenadas do eixo COMPRIMIDO. */
  points: Point[];
  /** Trechos comprimidos, com instantes reais e posição no eixo. */
  gaps: Gap[];
  /** Todos os trechos, inclusive os ativos (o eixo é feito deles). */
  segments: Segment[];
  /** Largura total do eixo comprimido. */
  axisMs: number;
  /** Tempo acumulado em que o ventilador estava desligado (ms reais). */
  offMs: number;
  /** Tempo acumulado sem telemetria (ms reais). */
  noDataMs: number;
  /** Instante real -> posição no eixo. */
  xOf(time: number): number;
  /** Posição no eixo -> instante real. É o que reconverte os rótulos.
   *
   *  `xOf` e `realAt` são inversos um do outro; a propriedade de ida-e-volta
   *  é travada por teste, porque é ela que garante que o rótulo do eixo
   *  mostra a hora verdadeira e não um horário deslocado.
   */
  realAt(x: number): number;
}

/** Remove rótulos de eixo visualmente repetidos, preservando os extremos. */
export function dedupeLabels(labels: string[]): string[] {
  const out: string[] = [];
  for (const label of labels) {
    if (out.length && out[out.length - 1] === label) continue;
    out.push(label);
  }
  return out;
}

/**
 * Monta a linha do tempo comprimida.
 *
 * O eixo X deixa de ser tempo real. Trechos em que nada foi medido são
 * comprimidos para `compressedSpanMs`, e a largura que sobra vai para os
 * trechos com medição. É o que torna a janela de 7 dias legível: sem isso,
 * 2,4 h de atividade ocupavam 1,4% da largura e o resto era vazio.
 *
 * Três invariantes sustentam a honestidade do gráfico:
 *
 *   1. Nada é desenhado onde não houve medição. Um trecho sem telemetria vira
 *      `null` (com `spanGaps: false`), isto é, espaço vazio — nunca 0 W.
 *      A única exceção é o trecho realmente desligado, em que 0 W É a leitura.
 *   2. A compressão é visível, não silenciosa. Todo trecho interrompido ganha
 *      marcador e responde ao tooltip com o motivo e a duração REAL.
 *   3. A duração real nunca se perde. `gaps` guarda início e fim reais, e é
 *      o que alimenta o rótulo do eixo e o resumo "X fora do ar".
 */
export function buildTimeline(
  times: number[],
  values: number[],
  options: TimelineOptions = {}
): Timeline {
  const {
    gapLimitMs = COVERAGE_GAP_LIMIT_MS,
    offPowerW = OFF_POWER_W,
    minOffDurationMs = MIN_OFF_DURATION_MS,
  } = options;

  if (times.length === 0) {
    return {
      points: [], gaps: [], segments: [], axisMs: 0,
      offMs: 0, noDataMs: 0, xOf: () => 0, realAt: () => 0,
    };
  }

  const first = times[0];
  const last = times[times.length - 1];
  // Sem janela explícita, o eixo cobre exatamente o que foi medido.
  const windowStart = Math.min(options.windowStartMs ?? first, first);
  const windowEnd = Math.max(options.windowEndMs ?? last, last);

  /**
   * Limiar para chamar um vão de "sem sinal".
   *
   * Não basta o piso fixo de 90 s. Numa série em que o ESP32 reporta a cada
   * 4 s, um vão de 4 min é uma interrupção evidente. Numa série de baixa
   * resolução, com uma amostra a cada 4 min, um vão de 4 min é a cadência
   * normal — tratá-lo como interrupção encheria o gráfico de losangos sem
   * informar nada.
   *
   * Por isso o limiar é o maior entre o piso e três vezes a cadência mediana
   * da própria série: cada gráfico se calibre no próprio ritmo.
   */
  const medianIntervalMs = (() => {
    if (times.length < 3) return gapLimitMs;
    const deltas: number[] = [];
    for (let i = 1; i < times.length; i++) {
      const delta = times[i] - times[i - 1];
      if (delta > 0) deltas.push(delta);
    }
    if (!deltas.length) return gapLimitMs;
    deltas.sort((a, b) => a - b);
    return deltas[Math.floor(deltas.length / 2)];
  })();
  const noDataThresholdMs = Math.max(gapLimitMs, medianIntervalMs * 3);

  // --- 1. Trechos contíguos cobrindo a janela inteira ---------------------
  //
  // A ORDEM DAS REGRAS IMPORTA. O teste de "0 W nas duas pontas" vem ANTES do
  // teste de lacuna, e não por acaso:
  //
  //   * medimos 0 W antes e depois da lacuna. O ventilador estava desligado
  //     nos dois extremos, e nada no sistema consegue ligá-lo sozinho — ele só
  //     reage a comando MQTT, e um comando durante a pausa nem chega a ser
  //     processado. Logo o trecho é desligamento;
  //   * invertendo a ordem, o trecho viraria "sem sinal" e a fusão de trechos
  //     vizinhos já teria comido o desligamento. Nos dados reais deste projeto
  //     isso importava: cada desligamento tem só 2 amostras, separadas por
  //     minutos, então o gráfico nunca diria "desligado" — que é justamente o
  //     que se quer enxergar;
  //   * sem 0 W nas pontas, aí sim é lacuna: o estado no meio é desconhecido e
  //     não pode ser preenchido.
  // Cada intervalo entre amostras consecutivas, com os índices das amostras
  // que ele liga.
  type Raw = { kind: 'active' | GapReason; from: number; to: number };
  const raw: Raw[] = [];
  // O que existe antes da primeira e depois da última amostra também é ausência
  // de medição. Passa pelo mesmo limiar das demais: numa série de cadência
  // fraca, 4 min de borda é a cadência normal, não uma interrupção.
  // O que existe antes da primeira e depois da última amostra também precisa
  // entrar no eixo, senão a janela desenhada não bate com a janela pedida.
  // Passa pelo mesmo limiar das demais: numa série de cadência fraca, 4 min de
  // borda é a cadência normal, não uma interrupção — nesse caso o trecho é
  // ativo, e a linha simplesmente se estende até a borda.
  if (windowStart < first) {
    raw.push({
      kind: first - windowStart > noDataThresholdMs ? 'no-data' : 'active',
      from: windowStart,
      to: first,
    });
  }
  for (let i = 1; i < times.length; i++) {
    const from = times[i - 1];
    const to = times[i];
    if (to - from <= 0) continue;
    // A ORDEM DAS REGRAS IMPORTA. O teste de "0 W nas duas pontas" vem
    // ANTES do teste de lacuna, e não por acaso:
    //
    //   * medimos 0 W antes e depois da lacuna. O ventilador estava desligado
    //     nos dois extremos, e nada no sistema consegue ligá-lo sozinho — ele
    //     só reage a comando MQTT, e um comando durante a pausa nem chega a
    //     ser processado. Logo o trecho é desligamento;
    //   * invertendo a ordem, o trecho viraria "sem sinal" e a fusão de
    //     trechos vizinhos já teria comido o desligamento;
    //   * sem 0 W nas pontas, aí sim é lacuna: o estado no meio é desconhecido.
    if (values[i - 1] <= offPowerW && values[i] <= offPowerW) {
      raw.push({ kind: 'off', from, to });
    } else if (to - from > noDataThresholdMs) {
      raw.push({ kind: 'no-data', from, to });
    } else {
      raw.push({ kind: 'active', from, to });
    }
  }
  if (windowEnd > last) {
    raw.push({
      kind: windowEnd - last > noDataThresholdMs ? 'no-data' : 'active',
      from: last,
      to: windowEnd,
    });
  }

  // --- 2. Agrupa trechos interrompidos ------------------------------------
  //
  // "off" funde sempre: 0 W é uma medição real, então uma hora de ventilador
  // desligado com amostras a cada 4 s é UM desligamento, não 900 trechos. Sem
  // a fusão, a hora voltaria ao tempo real no eixo e a compressão sumiria.
  //
  // "no-data" NUNCA funde: um vão liga duas amostras e não tem nada entre
  // elas — é uma lacuna de verdade. Juntar dois vãos significaria apagar a
  // amostra do meio, que existe. A calibre do limiar (`noDataThresholdMs`,
  // acima) é que evita chamar de interrupção a simples cadência fraca.
  const runs: Raw[] = [];
  for (const piece of raw) {
    const previous = runs[runs.length - 1];
    if (previous && previous.kind === 'off' && piece.kind === 'off') {
      previous.to = piece.to;
    } else {
      runs.push({ ...piece });
    }
  }

  // Um trecho a 0 W muito curto não chega a ser interrupção: volta a ser dado,
  // senão um pico real de uma amostra sumiria do gráfico.
  for (const run of runs) {
    if (run.kind === 'off' && run.to - run.from < minOffDurationMs) {
      run.kind = 'active';
    }
  }

  // Reagrupa os ativos contíguos, agora que alguns 'off' curtos voltaram a ser
  // dado. Sem isso a janela ficaria com buracos: dois trechos ativos seguidos
  // e nenhum segmento cobrindo o meio.
  const merged: Raw[] = [];
  for (const run of runs) {
    const previous = merged[merged.length - 1];
    if (previous && previous.kind === 'active' && run.kind === 'active') {
      previous.to = run.to;
    } else {
      merged.push({ ...run });
    }
  }

  const segments: Segment[] = merged.map((run) => ({
    kind: run.kind, from: run.from, to: run.to, xFrom: 0, xTo: 0,
  }));

  // --- 3. Largura dos trechos interrompidos -------------------------------
  // Depende de quantos são: a largura mínima fixa só funciona quando são
  // poucos. Com muitos, precisa crescer para os marcadores não se fundirem.
  const activeTotalMs = segments
    .filter((segment) => segment.kind === 'active')
    .reduce((total, segment) => total + (segment.to - segment.from), 0);
  // Só as interrupções contam: passar o total de segmentos (ativos inclusive)
  // faria cada uma receber largura demais estreita e os marcadores se
  // fundiriam.
  const gapCount = segments.filter((segment) => segment.kind !== 'active').length;
  const compressedSpanMs = chooseCompressedSpan(activeTotalMs, gapCount);

  // --- 4. Posições no eixo ------------------------------------------------
  let cursor = 0;
  for (const segment of segments) {
    const real = segment.to - segment.from;
    const width = segment.kind === 'active' ? real : compressedSpanMs;
    segment.xFrom = cursor;
    segment.xTo = cursor + width;
    cursor = segment.xTo;
  }
  const axisMs = Math.max(cursor, 1);

  const segmentAt = (time: number): Segment | null => {
    for (const segment of segments) {
      if (time >= segment.from && time < segment.to) return segment;
    }
    return segments.length && time >= segments[segments.length - 1].to
      ? segments[segments.length - 1]
      : null;
  };

  const xOf = (time: number): number => {
    const segment = segmentAt(time);
    if (!segment) return time - windowStart;
    const real = segment.to - segment.from;
    if (real <= 0) return segment.xFrom;
    const ratio = Math.min(1, Math.max(0, (time - segment.from) / real));
    return segment.xFrom + ratio * (segment.xTo - segment.xFrom);
  };

  const realAt = (x: number): number => {
    for (const segment of segments) {
      if (x < segment.xFrom) break;
      if (x <= segment.xTo) {
        const width = segment.xTo - segment.xFrom;
        if (width <= 0) return segment.from;
        const ratio = Math.min(1, Math.max(0, (x - segment.xFrom) / width));
        return segment.from + ratio * (segment.to - segment.from);
      }
    }
    return windowStart + Math.max(0, x);
  };

  // --- 5. Série ----------------------------------------------------------
  //
  // NENHUMA amostra a 0 W entra no gráfico. O pedido é linha contínua ligando
  // os pontos, sem vales em zero: um desligamento de 3 h viraria um vale
  // Deep que não existe, porque a largura de 8 px na tela representa 3 h.
  //
  // O desligamento não desaparece: vira um marcador âmbar, e o tooltip diz
  // "Desligado por 3 h 12 min" com os dois instantes reais. A informação
  // continua lá — só não vira um traço falso.
  //
  // Descartar por VALOR (e não por trecho) importa: a amostra a 0 W que marca
  // o instante do desligamento é a primeira do trecho ativo seguinte, e
  // entraria como um ponto isolado em zero.
  const emitted: Array<{ x: number; y: number | null }> = [];
  for (let i = 0; i < times.length; i++) {
    // Todas as amostras entram, inclusive as de 0 W: é delas que vem o vale
    // que o gráfico faz ao desligar, exatamente como no InfluxDB. O que NÃO
    // entra é nada — a linha é contínua e sem marcadores.
    emitted.push({ x: xOf(times[i]), y: values[i] });
  }

  const gaps: Gap[] = segments
    .filter((segment) => segment.kind !== 'active')
    .map((segment) => ({
      reason: segment.kind as GapReason,
      from: segment.from,
      to: segment.to,
      xFrom: segment.xFrom,
      xTo: segment.xTo,
    }));

  // A série é sempre CONTÍNUA: os pontos se ligam atravessando o trecho
  // comprimido, como no InfluxDB. Não há `null` na série, e portanto nada
  // interrompe o traço.
  const points: Point[] = [...emitted];

  const offMs = gaps
    .filter((gap) => gap.reason === 'off')
    .reduce((total, gap) => total + (gap.to - gap.from), 0);
  const noDataMs = gaps
    .filter((gap) => gap.reason === 'no-data')
    .reduce((total, gap) => total + (gap.to - gap.from), 0);

  return {
    points,
    gaps,
    segments,
    axisMs,
    offMs,
    noDataMs,
    xOf,
    realAt,
  };
}

/**
 * Rótulos do eixo X.
 *
 * Num eixo comprimido, os ticks automáticos do Chart.js ficariam errados:
 * ele escolhe valores uniformes no eixo, e como o tempo real não é uniforme,
 * quatro rótulos saíam colados no fim ("28/09 14:42", "14:59", "15:42", "17:10")
 * enquanto o resto da largura ficava sem rótulo.
 *
 * Amostramos posições uniformes do EIXO e reconvertemos para o instante real,
 * o que garante boa distribuição do texto na tela. Rótulos visualmente
 * idênticos são removidos pelo chamador (`dedupeLabels`), porque dois
 * "28/09 15:42" lado a lado só gastam espaço.
 */
export function axisTickCandidates(timeline: Timeline, maxTicks = 10): number[] {
  const { axisMs } = timeline;
  if (!(axisMs > 0) || maxTicks < 2) return [0, axisMs].filter((x) => x <= axisMs);

  if (maxTicks === 2) return [0, axisMs];
  const step = axisMs / (maxTicks - 1);
  const out: number[] = [];
  for (let i = 0; i < maxTicks; i++) out.push(i === maxTicks - 1 ? axisMs : i * step);
  return out;
}

/** Duração real de um trecho, em texto curto para o tooltip. */
export function formatDuration(ms: number): string {
  if (!(ms > 0)) return '0 min';
  const totalMinutes = Math.round(ms / 60_000);
  if (totalMinutes < 1) return 'instantes';
  if (totalMinutes < 60) return `${totalMinutes} min`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours < 24) return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days} d ${restHours} h` : `${days} d`;
}

/**
 * Fração da janela coberta por telemetria, entre 0 e 1.
 *
 * Dois pontos distantes entre si não "cobrem" o intervalo todo, então só
 * contamos os trechos dentro da tolerância de lacuna.
 *
 * Isto é medido em TEMPO REAL, e não sobre o eixo comprimido. A compressão
 * existe para o gráfico ficar legível; a cobertura precisa continuar dizendo
 * a verdade sobre o período, senão o usuário deixa de saber que está olhando
 * 1,4% de uma janela de 7 dias.
 */
export function computeCoverage(
  times: number[],
  windowStartMs: number,
  windowEndMs: number,
  gapLimitMs = COVERAGE_GAP_LIMIT_MS
): number {
  const span = windowEndMs - windowStartMs;
  if (span <= 0 || times.length < 2) return 0;

  let covered = 0;
  for (let i = 1; i < times.length; i++) {
    const dt = times[i] - times[i - 1];
    if (dt <= gapLimitMs) covered += dt;
  }
  return Math.max(0, Math.min(1, covered / span));
}

/** Estatísticas da série, como exibidas nos cartões acima do gráfico. */
export interface SeriesStats {
  min: number;
  max: number;
  mean: number;
  deviation: number;
}

export function computeStats(values: number[]): SeriesStats {
  if (!values.length) {
    return { min: 0, max: 0, mean: 0, deviation: 0 };
  }
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((total, value) => total + (value - mean) ** 2, 0) / values.length;
  return {
    min: Math.min(...values),
    max: Math.max(...values),
    mean,
    deviation: Math.sqrt(variance),
  };
}
