import { describe, expect, it } from 'vitest';
import {
  COVERAGE_GAP_LIMIT_MS,
  DEFAULT_CEILING,
  HEADROOM_W,
  MIN_CEILING,
  ceilingFor,
  computeCoverage,
  computeStats,
  nextScaleState,
  type ScaleState,
} from './chartRules';

const H = 3600_000;
const T = Date.parse('2026-09-28T18:00:00Z');

const blank = (): ScaleState => ({ scale: { max: DEFAULT_CEILING }, anchor: null });

/** Série de N pontos com passo de 4 min, e um pico no meio. */
function series(count: number, peak: number | null, stepMs = 4 * 60_000, startMs = T) {
  const times: number[] = [];
  const values: number[] = [];
  for (let i = 0; i < count; i++) {
    times.push(startMs + i * stepMs);
    values.push(i === Math.floor(count / 2) && peak !== null ? peak : 20);
  }
  return { times, values };
}

describe('ceilingFor — teto do eixo Y', () => {
  it('é exatamente pico + folga', () => {
    expect(ceilingFor(32)).toBe(42);
    expect(ceilingFor(100)).toBe(110);
    expect(ceilingFor(91.4)).toBeCloseTo(101.4, 5);
  });

  it('não arredonda para múltiplo de degrau', () => {
    // Regressão: arredondar transformava pico 91,4 W em teto 125 W.
    expect(ceilingFor(91.4)).toBeLessThan(102);
  });

  it('nunca degenera com potência zero', () => {
    // teto = 0 + folga; MIN_CEILING é apenas uma rede de segurança
    expect(ceilingFor(0)).toBe(HEADROOM_W);
    expect(ceilingFor(0)).toBeGreaterThanOrEqual(MIN_CEILING);
  });

  it('a folga é sempre HEADROOM_W para valores úteis', () => {
    for (const pico of [0.4, 5, 29.77, 32, 60, 100, 250, 900, 1500]) {
      expect(ceilingFor(pico) - pico).toBeCloseTo(HEADROOM_W, 6);
    }
  });
});

describe('nextScaleState — histerese do teto', () => {
  it('série vazia volta ao teto padrão', () => {
    const s = nextScaleState(blank(), [], [], T);
    expect(s.scale.max).toBe(DEFAULT_CEILING);
    expect(s.anchor).toBeNull();
  });

  it('sobe imediatamente com um pico novo', () => {
    const { times, values } = series(21, 32);
    const s = nextScaleState(blank(), values, times, T - 8 * H);
    expect(s.scale.max).toBe(42);
    expect(s.anchor?.power).toBe(32);
  });

  it('mantém o teto quando o pico sai do subconjunto mas continua na janela', () => {
    const a = series(21, 32);
    let s = nextScaleState(blank(), a.values, a.times, T - 8 * H);
    expect(s.scale.max).toBe(42);
    // o pico some do slice exibido (reamostragem por índice)
    const semPico = series(30, null);
    for (let i = 0; i < 25; i++) {
      s = nextScaleState(s, semPico.values, semPico.times, T - 8 * H);
    }
    expect(s.scale.max).toBe(42);
  });

  it('pico maior substitui o vigente e expande', () => {
    const a = series(21, 32);
    let s = nextScaleState(blank(), a.values, a.times, T - 8 * H);
    const b = series(21, 60, 4 * 60_000, T - 1 * H);
    s = nextScaleState(s, b.values, b.times, T - 8 * H);
    expect(s.scale.max).toBe(70);
  });

  it('recalcula quando o pico sai de verdade da janela', () => {
    // pico 7 h atrás, dentro de uma janela que começava 8 h atrás
    const comPico = series(21, 60, 4 * 60_000, T - 7.5 * H);
    let s = nextScaleState(blank(), comPico.values, comPico.times, T - 8 * H);
    expect(s.scale.max).toBe(70);
    // o pico fica em T-6,8 h, ou seja, fora da janela que começará em T-1 h
    expect(s.anchor?.at).toBeLessThan(T - 1 * H);

    // a janela passa a começar em T-1h: o pico de 7 h atrás ficou de fora
    const semPico = series(30, null, 4 * 60_000, T - 1 * H);
    s = nextScaleState(s, semPico.values, semPico.times, T - 1 * H);
    expect(s.scale.max).toBe(30);
  });

  it('não oscila quando o pico é estável', () => {
    let s = blank();
    const vistos: number[] = [];
    const serie = series(21, 32);
    for (let i = 0; i < 40; i++) {
      s = nextScaleState(s, serie.values, serie.times, T - 8 * H);
      vistos.push(s.scale.max);
    }
    expect(new Set(vistos).size).toBe(1);
    expect(vistos[0]).toBe(42);
  });

  it('expande e encolhe conforme o pico entra e sai da janela', () => {
    const comPico = series(41, 120, 4 * 60_000, T - 7.5 * H);
    let s = nextScaleState(blank(), comPico.values, comPico.times, T - 8 * H);
    const alto = s.scale.max;
    const semPico = series(30, null, 4 * 60_000, T - 1 * H);
    s = nextScaleState(s, semPico.values, semPico.times, T - 1 * H);
    expect(alto).toBeGreaterThan(s.scale.max);
  });

  it('nunca corta o pico: o teto é sempre >= pico + folga', () => {
    let s = blank();
    for (const pico of [0, 5, 29.77, 32, 45, 60, 100, 250, 900, 1500]) {
      const { times, values } = series(21, pico === 0 ? 0 : pico, 4 * 60_000, T - 1 * H);
      s = nextScaleState(s, values, times, T - 8 * H);
      const max = Math.max(...values);
      expect(s.scale.max).toBeGreaterThanOrEqual(max);
    }
  });
});

describe('computeCoverage — cobertura da janela', () => {
  it('série sem lacuna cobre tudo', () => {
    const { times } = series(120, null, 4000);   // ~8 min
    const c = computeCoverage(times, T, T + 8 * H);
    expect(c).toBeLessThanOrEqual(1);
    expect(c).toBeGreaterThan(0);
  });

  it('2 h de dados numa janela de 8 h dá cerca de 25%', () => {
    // 300 pontos de 4 s = 20 min; janela de 8 h
    const { times } = series(300, null, 4000);
    const c = computeCoverage(times, T, T + 8 * H);
    expect(c).toBeGreaterThan(0);
    expect(c).toBeLessThan(0.05);
  });

  it('janela invertida ou degenerada devolve 0', () => {
    expect(computeCoverage([T, T + 1000], T + H, T)).toBe(0);
    expect(computeCoverage([T], T, T + H)).toBe(0);
    expect(computeCoverage([], T, T + H)).toBe(0);
  });

  it('nunca devolve valor fora de 0..1', () => {
    const { times } = series(500, null, 4000);
    for (const janela of [H, 8 * H, 24 * H, 7 * 24 * H]) {
      const c = computeCoverage(times, T, T + janela);
      expect(c).toBeGreaterThanOrEqual(0);
      expect(c).toBeLessThanOrEqual(1);
    }
  });

  it('uma lacuna maior que a tolerância não conta como cobertura', () => {
    const times = [T, T + COVERAGE_GAP_LIMIT_MS * 2];
    expect(computeCoverage(times, T, T + 2 * COVERAGE_GAP_LIMIT_MS)).toBe(0);
  });
});

describe('computeStats — estatísticas exibidas', () => {
  it('série vazia devolve zeros', () => {
    expect(computeStats([])).toEqual({ min: 0, max: 0, mean: 0, deviation: 0 });
  });

  it('média, mínimo e máximo corretos', () => {
    const s = computeStats([10, 20, 30]);
    expect(s.mean).toBe(20);
    expect(s.min).toBe(10);
    expect(s.max).toBe(30);
  });

  it('desvio padrão amostral correto', () => {
    // [2,4,4,4,5,5,7,9]: média 5, variância 4, desvio 2
    const s = computeStats([2, 4, 4, 4, 5, 5, 7, 9]);
    expect(s.mean).toBe(5);
    expect(s.deviation).toBeCloseTo(2, 6);
  });

  it('série constante tem desvio numericamente zero', () => {
    const s = computeStats(Array(50).fill(29.77));
    // o resíduo ~1e-14 vem do erro de ponto flutuante da média
    expect(s.deviation).toBeCloseTo(0, 10);
    expect(s.mean).toBeCloseTo(29.77, 6);
  });

  it('nunca devolve desvio negativo ou NaN', () => {
    for (const valores of [[0], [1, 1], [0, 0, 0], [29.77, 29.77, 0]]) {
      const s = computeStats(valores);
      expect(s.deviation).toBeGreaterThanOrEqual(0);
      expect(Number.isNaN(s.deviation)).toBe(false);
    }
  });
});
