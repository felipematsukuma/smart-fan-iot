import { describe, expect, it } from 'vitest';
import {
  COMPRESSED_SPAN_MS,
  OFF_POWER_W,
  axisTickCandidates,
  buildTimeline,
  formatDuration,
} from './chartRules';

const MIN = 60_000;
const H = 60 * MIN;
const T0 = Date.parse('2026-09-28T18:00:00Z');

/** [minutos desde T0, potencia] */
function build(pairs: Array<[number, number]>) {
  const times = pairs.map(([m]) => T0 + m * MIN);
  const values = pairs.map(([, w]) => w);
  return { times, values };
}

const ON = 29.77;

describe('buildTimeline — série sem interrupção', () => {
  it('mapeia tempo real 1:1 quando não há nada a comprimir', () => {
    const { times, values } = build([[0, ON], [1, ON], [2, ON]]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 2 * MIN,
    });
    expect(t.gaps).toHaveLength(0);
    expect(t.axisMs).toBe(2 * MIN);
    expect(t.xOf(times[1])).toBe(MIN);
  });

  it('preserva a ordem e os valores', () => {
    const { times, values } = build([[0, ON], [1, 20], [2, 40]]);
    const t = buildTimeline(times, values);
    const real = t.points.filter((p) => p.y !== null);
    expect(real.map((p) => p.y)).toEqual([ON, 20, 40]);
    for (let i = 1; i < t.points.length; i++) {
      expect(t.points[i].x).toBeGreaterThanOrEqual(t.points[i - 1].x);
    }
  });

  it('série vazia não quebra', () => {
    const t = buildTimeline([], []);
    expect(t.points).toEqual([]);
    expect(t.axisMs).toBe(0);
  });
});

describe('buildTimeline — desligamento', () => {
  it('comprime um trecho desligado longo', () => {
    const { times, values } = build([
      [0, ON], [1, ON],          // ligado
      [2, 0], [90, 0], [91, 0],  // 89 min desligado
      [92, ON], [93, ON],        // religado
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 93 * MIN,
    });

    const off = t.gaps.find((g) => g.reason === 'off');
    expect(off).toBeDefined();
    // A duração REAL é preservada no rótulo…
    expect(off!.to - off!.from).toBe(89 * MIN);
    // …mas a largura no eixo é comprimida.
    expect(off!.xTo - off!.xFrom).toBe(COMPRESSED_SPAN_MS);
  });

  it('a desativação é muito menor que o tempo real', () => {
    const { times, values } = build([
      [0, ON], [2, 0], [180, 0], [182, ON],
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 182 * MIN,
    });
    const off = t.gaps.find((g) => g.reason === 'off')!;
    // 178 min reais viram 45 s de eixo
    expect(off.xTo - off.xFrom).toBe(COMPRESSED_SPAN_MS);
    expect(off.to - off.from).toBe(178 * MIN);
  });

  it('a linha é contínua, sem quebras (leitura do InfluxDB)', () => {
    // Pedido explícito: linha conectando os pontos, como no InfluxDB, e sem
    // marcadores. O vale a 0 W vem das próprias amostras de 0 W.
    const { times, values } = build([
      [0, ON], [1, ON], [2, 0], [60, 0], [61, ON], [62, ON],
    ]);
    const t = buildTimeline(times, values);
    expect(t.points.every((p) => p.y !== null)).toBe(true);
    expect(t.points.length).toBe(6);
    // e o trecho desligado continua registrado, para o resumo de tempo
    expect(t.gaps.length).toBe(1);
  });

  it('o desligamento aparece como vale a 0 W, como no InfluxDB', () => {
    const { times, values } = build([[0, ON], [2, 0], [60, 0], [61, ON]]);
    const t = buildTimeline(times, values);
    // As amostras a 0 W entram na linha: a queda a zero é a leitura.
    expect(t.points.some((p) => p.y === 0)).toBe(true);
    expect(t.points[0].y).toBe(ON);
    expect(t.points[t.points.length - 1].y).toBe(ON);
  });

  it('conectado, o espaço do trecho comprimido fica vazio de pontos', () => {
    const { times, values } = build([[0, ON], [1, ON], [200, ON], [201, ON]]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0, windowEndMs: T0 + 201 * MIN,
    });
    const vazio = t.gaps.find((g) => g.reason === 'no-data')!;
    const dentro = t.points.filter((p) => p.x > vazio.xFrom && p.x < vazio.xTo);
    // A reta liga os dois extremos atravessando a faixa, mas não há ponto
    // samples lá dentro: a compressão é visível pela distância entre os pontos.
    expect(dentro).toHaveLength(0);
  });

  it('série vazia devolve uma linha do tempo utilizável', () => {
    const t = buildTimeline([], [], { windowStartMs: T0, windowEndMs: T0 + H });
    expect(t.points).toEqual([]);
    expect(t.gaps).toEqual([]);
    expect(t.axisMs).toBe(0);
    expect(t.xOf(T0)).toBe(0);
    expect(t.realAt(0)).toBe(0);
  });

  it('realAt fora do eixo devolve um instante plausível, não NaN', () => {
    // Guarda de segurança: se algo pedir uma posição além do fim, o rótulo
    // não pode virar "Invalid Date" na tela.
    const { times, values } = build([[0, ON], [1, ON]]);
    const t = buildTimeline(times, values, { windowStartMs: T0, windowEndMs: T0 + MIN });
    const fora = t.realAt(t.axisMs * 3);
    expect(Number.isFinite(fora)).toBe(true);
    expect(fora).toBeGreaterThanOrEqual(T0);
  });

  it('não comprime 0 W isolado, para não apagar um pico real', () => {
    // Uma única leitura a 0 W entre dois trechos ligados é ruído, não desligamento.
    const { times, values } = build([[0, ON], [1, 0], [2, ON]]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 2 * MIN,
    });
    expect(t.gaps.filter((g) => g.reason === 'off')).toHaveLength(0);
    expect(t.axisMs).toBe(2 * MIN);
    // A amostra a 0 W continua na linha (é leitura), mas sem comprimir o eixo.
    expect(t.points).toHaveLength(3);
  });

  it('as amostras das bordas de um vão continuam sendo desenhadas', () => {
    // A amostra que fecha um vão é uma medição real e precisa aparecer, senão
    // o gráfico perderia a transição.
    const { times, values } = build([[0, ON], [1, ON], [200, ON], [201, ON]]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0, windowEndMs: T0 + 201 * MIN,
    });
    expect(t.points).toHaveLength(4);
  });

  it('cadência fraca não vira um bloco só', () => {
    // Uma amostra a cada 4 min é baixa resolução, NÃO ausência. Se os vãos
    // curtos se fundissem, o gráfico apagaria dezenas de leituras que existem.
    const pares: Array<[number, number]> = [];
    for (let m = 0; m < 60; m += 4) pares.push([m, ON]);
    const { times, values } = build(pares);
    const t = buildTimeline(times, values, {
      windowStartMs: T0, windowEndMs: T0 + 60 * MIN,
    });
    // Todas as amostras são desenhadas e ligadas, em tempo real.
    expect(t.points).toHaveLength(15);
    expect(t.gaps).toHaveLength(0);
    expect(t.axisMs).toBe(60 * MIN);
  });

  it('respeita o limite de duração mínima', () => {
    // 20 s desligado fica ABAIXO de MIN_OFF_DURATION_MS
    const { times, values } = build([
      [0, ON], [0.2, 0], [0.5, 0], [1, ON],
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + MIN,
    });
    expect(t.gaps.filter((g) => g.reason === 'off')).toHaveLength(0);
  });

  it('acima do limite, comprime', () => {
    const { times, values } = build([
      [0, ON], [0.2, 0], [1, 0], [1.2, ON],
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 1.2 * MIN,
    });
    expect(t.gaps.filter((g) => g.reason === 'off').length).toBe(1);
  });

  it('tolera ruído de ponto flutuante em torno de 0', () => {
    const { times, values } = build([
      [0, ON], [2, 0.0000001], [40, 0.4], [41, ON],
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 41 * MIN,
    });
    // 0,4 W está dentro da folga de OFF_POWER_W
    expect(OFF_POWER_W).toBeGreaterThan(0.4);
    expect(t.gaps.filter((g) => g.reason === 'off').length).toBe(1);
  });

  it('acumula o tempo total desligado', () => {
    const { times, values } = build([
      [0, ON], [2, 0], [32, 0], [33, ON],   // 30 min
      [34, ON], [35, 0], [45, 0], [46, ON], // 10 min
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 46 * MIN,
    });
    expect(t.offMs).toBe(30 * MIN + 10 * MIN);
  });
});

describe('buildTimeline — falta de telemetria', () => {
  it('comprime e classifica como no-data, nunca como 0 W', () => {
    const { times, values } = build([[0, ON], [1, ON], [10, ON], [11, ON]]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 11 * MIN,
    });
    const gap = t.gaps.find((g) => g.reason === 'no-data')!;
    expect(gap).toBeDefined();
    // Nenhum ponto desenhado dentro do trecho: sem dado, não se inventa 0 W.
    const dentro = t.points.filter((p) => p.x > gap.xFrom && p.x < gap.xTo);
    expect(dentro.every((p) => p.y === null)).toBe(true);
  });

  it('separa desligado de sem telemetria', () => {
    const { times, values } = build([
      [0, ON], [2, 0], [40, 0],       // desligado
      [300, ON], [301, ON],            // 260 min sem telemetria
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 301 * MIN,
    });
    const reasons = t.gaps.map((g) => g.reason);
    expect(reasons).toContain('off');
    expect(reasons).toContain('no-data');
    expect(t.offMs).toBe(38 * MIN);
    // Só o vão de 260 min conta. O de 2 min no início não conta: nesta série a
    // cadência mediana é de 38 min, então 2 min é ruído, não interrupção.
    expect(t.noDataMs).toBe(260 * MIN);
  });

  it('comprime o espaço antes da primeira e depois da última amostra', () => {
    const { times, values } = build([[100, ON], [101, ON]]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 200 * MIN,
    });
    // 100 min de antes e 99 min de depois: dois trechos comprimidos
    const compressidos = t.segments.filter((s) => s.kind === 'no-data');
    expect(compressidos.length).toBe(2);
    // O eixo inteiro cabe em ~2 min de largura, não 200.
    expect(t.axisMs).toBeLessThan(200 * MIN);
  });
});

describe('buildTimeline — o eixo fica utilizável', () => {
  it('a atividade real ganha a largura que o tempo morto perde', () => {
    // Caso real do projeto: 1 h de telemetria densa dentro de uma janela de 10 h.
    const pares: Array<[number, number]> = [];
    for (let s = 0; s < 3600; s += 4) pares.push([s / 60, ON]);        // 0 -> 60 min
    for (let s = 24000; s < 24600; s += 4) pares.push([s / 60, ON]);   // 400 -> 410 min
    const { times, values } = build(pares);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 600 * MIN,
    });
    const ativo = t.segments.filter((s) => s.kind === 'active');
    const larguraAtiva = ativo.reduce((a, s) => a + (s.xTo - s.xFrom), 0);
    const razao = larguraAtiva / t.axisMs;
    // Sem compressão, 70 min de atividade em 600 min ocupariam 11,7% da largura.
    expect(razao).toBeGreaterThan(0.8);
  });

  it('com muitas interrupções, elas não viram o gráfico inteiro', () => {
    // Caso real: 40 rajadas curtas separadas por 10 h. Sem compressão, a
    // série ocuparia 0,5% da largura. As interrupções ficam estreitas, e a
    // leitura continua dominando.
    const pares: Array<[number, number]> = [];
    for (let rajada = 0; rajada < 40; rajada++) {
      const base = rajada * 600;
      for (let s = 0; s < 120; s += 4) pares.push([base + s / 60, ON]); // 2 min
    }
    const { times, values } = build(pares);
    const t = buildTimeline(times, values, {
      windowStartMs: T0,
      windowEndMs: T0 + 24000 * MIN,
    });
    expect(t.gaps.length).toBeGreaterThan(20);
    const ativo = t.segments.filter((s) => s.kind === 'active');
    const larguraAtiva = ativo.reduce((a, s) => a + (s.xTo - s.xFrom), 0);
    // Com 41 interrupções, o piso de 45 s por trecho passa a mandar sobre a
    // fração-alvo: 41 x 45 s = 31 min contra 80 min de atividade. A série
    // ainda domina, e cada interrupção fica larga o bastante para ser vista
    // como uma descida, e não como um borrão.
    expect(larguraAtiva / t.axisMs).toBeGreaterThan(0.7);
  });

  it('nunca deixa o eixo vazio nem com largura zero', () => {
    const { times, values } = build([[0, ON], [1, ON]]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0, windowEndMs: T0 + MIN,
    });
    expect(t.axisMs).toBeGreaterThan(0);
  });

  it('xOf e realAt são inversos um do outro', () => {
    const { times, values } = build([
      [0, ON], [2, 0], [100, 0], [101, ON], [102, ON],
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0, windowEndMs: T0 + 102 * MIN,
    });
    for (const tempo of [0, 1, 2, 50, 100, 101, 102]) {
      const real = T0 + tempo * MIN;
      expect(t.realAt(t.xOf(real))).toBeCloseTo(real, -2);
    }
  });

  it('os trechos são contíguos e não se sobrepõem', () => {
    const { times, values } = build([
      [0, ON], [2, 0], [100, 0], [101, ON], [500, ON], [501, ON],
    ]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0, windowEndMs: T0 + 501 * MIN,
    });
    for (let i = 1; i < t.segments.length; i++) {
      expect(t.segments[i].from).toBe(t.segments[i - 1].to);
      expect(t.segments[i].xFrom).toBe(t.segments[i - 1].xTo);
    }
  });

  it('o eixo termina exatamente no fim da janela', () => {
    const fim = T0 + 500 * MIN;
    const { times, values } = build([[0, ON], [1, ON], [2, ON]]);
    const t = buildTimeline(times, values, {
      windowStartMs: T0, windowEndMs: fim,
    });
    expect(t.realAt(t.axisMs)).toBeCloseTo(fim, -2);
  });
});

describe('casos limite — 0 e 1 ponto', () => {
  it('zero amostras não quebra o eixo', () => {
    const t = buildTimeline([], [], { windowStartMs: T0, windowEndMs: T0 + H });
    expect(t.points).toEqual([]);
    expect(t.axisMs).toBe(0);
    expect(t.gaps).toEqual([]);
    expect(t.offMs).toBe(0);
    expect(t.noDataMs).toBe(0);
  });

  it('uma única amostra produz eixo e rótulos válidos', () => {
    // Acontece de verdade: consultar uma janela de 1 minuto costuma devolver
    // um único ponto. O gráfico precisa desenhar sem virar "Invalid Date".
    const t = buildTimeline([T0 + 30_000], [ON], {
      windowStartMs: T0,
      windowEndMs: T0 + MIN,
    });
    expect(t.points).toHaveLength(1);
    expect(t.points[0].y).toBe(ON);
    expect(t.axisMs).toBeGreaterThan(0);
    for (const x of axisTickCandidates(t, 4)) {
      const instante = t.realAt(x);
      expect(Number.isFinite(instante)).toBe(true);
      expect(instante).toBeGreaterThanOrEqual(T0);
      expect(instante).toBeLessThanOrEqual(T0 + MIN);
    }
  });

  it('uma única amostra a 0 W não vira desligamento', () => {
    // Não há como saber por quanto tempo o ventilador ficou desligado: uma
    // leitura isolada não é um desligamento.
    const t = buildTimeline([T0 + 30_000], [0], {
      windowStartMs: T0,
      windowEndMs: T0 + MIN,
    });
    expect(t.gaps).toEqual([]);
    expect(t.offMs).toBe(0);
  });

  it('janela muito curta, sem amostra nenhuma', () => {
    const t = buildTimeline([], [], { windowStartMs: T0, windowEndMs: T0 });
    expect(t.axisMs).toBe(0);
  });
});

describe('axisTickCandidates', () => {
  it('sempre inclui os extremos', () => {
    const { times, values } = build([[0, ON], [1, ON], [2, ON]]);
    const t = buildTimeline(times, values, { windowStartMs: T0, windowEndMs: T0 + 2 * MIN });
    const ticks = axisTickCandidates(t, 6);
    expect(ticks[0]).toBe(0);
    expect(ticks[ticks.length - 1]).toBe(t.axisMs);
  });

  it('limita a quantidade de rótulos', () => {
    const pares: Array<[number, number]> = [];
    for (let i = 0; i < 60; i++) pares.push([i * 2, ON], [i * 2 + 40, 0]);
    const { times, values } = build(pares);
    const t = buildTimeline(times, values, { windowStartMs: T0, windowEndMs: T0 + 130 * MIN });
    expect(axisTickCandidates(t, 8).length).toBeLessThanOrEqual(8);
  });

  it('não repete posições', () => {
    const { times, values } = build([[0, ON], [1, ON]]);
    const t = buildTimeline(times, values);
    const ticks = axisTickCandidates(t, 10);
    expect(new Set(ticks).size).toBe(ticks.length);
  });
});

describe('formatDuration', () => {
  it('formata minutos, horas e dias', () => {
    expect(formatDuration(0)).toBe('0 min');
    expect(formatDuration(20_000)).toBe('instantes');
    expect(formatDuration(30 * MIN)).toBe('30 min');
    expect(formatDuration(90 * MIN)).toBe('1 h 30 min');
    expect(formatDuration(2 * H)).toBe('2 h');
    expect(formatDuration(26 * H)).toBe('1 d 2 h');
    expect(formatDuration(48 * H)).toBe('2 d');
  });

  it('nunca devolve texto negativo', () => {
    expect(formatDuration(-5)).toBe('0 min');
  });
});
