import { describe, expect, it } from 'vitest';
import {
  formatCoverage,
  formatCurrency,
  formatCurrent,
  formatKwh,
  formatPower,
  projectMonthlyCost,
  sampleIntervalMinutes,
} from './format';

describe('formatKwh — energia', () => {
  it('usa 3 casas acima de 0,001 kWh', () => {
    expect(formatKwh(0.002)).toBe('0.002');
    expect(formatKwh(0.1234)).toBe('0.123');
  });

  it('usa 6 casas abaixo de 0,001 kWh para não virar zero', () => {
    expect(formatKwh(0.0004)).toBe('0.000400');
    expect(formatKwh(0.000001)).toBe('0.000001');
  });

  it('zero aparece como zero, não como NaN', () => {
    expect(formatKwh(0)).toBe('0.000000');
  });
});

describe('formatCurrency — dinheiro', () => {
  it('formata valores relevantes com 2 casas', () => {
    const t = formatCurrency(12.5);
    expect(t).toContain('12,50');
    expect(t).toMatch(/R\$/);
  });

  it('formata valores pequenos com 5 casas para não sumirem', () => {
    // Regressão: consumo residual de minutos virava "R$ 0,00"
    expect(formatCurrency(0.00238)).toContain('0,00238');
  });

  it('zero não vira -0,00', () => {
    expect(formatCurrency(0)).toContain('0,00000');
  });

  it('formata valores grandes', () => {
    expect(formatCurrency(1234.56)).toContain('1.234,56');
  });
});

describe('formatPower / formatCurrent — grandezas', () => {
  it('potência com uma casa', () => {
    expect(formatPower(29.77)).toBe('29.8');
    expect(formatPower(0)).toBe('0.0');
  });

  it('corrente com três casas', () => {
    expect(formatCurrent(0.26)).toBe('0.260');
    expect(formatCurrent(0.25999999)).toBe('0.260');
  });
});

describe('projectMonthlyCost — projeção mensal', () => {
  it('projeta a partir do consumo e da duração do período', () => {
    // 0,042 kWh em 1 h a R$ 1,00/kWh => 0,042 * 30 / (1/24) = 30,24
    expect(projectMonthlyCost(0.042, 1.0, 1)).toBeCloseTo(30.24, 6);
  });

  it('proporcional à tarifa', () => {
    const a = projectMonthlyCost(0.1, 1.0, 1);
    const b = projectMonthlyCost(0.1, 2.0, 1);
    expect(b).toBeCloseTo(a * 2, 6);
  });

  it('mesma potência média dá a mesma projeção', () => {
    // A projeção extrapola a MÉDIA de potência, não a energia bruta. 0,042 kWh em
    // 1 h e 0,084 kWh em 2 h têm a mesma média, logo a mesma projeção.
    const h1 = projectMonthlyCost(0.042, 1.0, 1);
    const h2 = projectMonthlyCost(0.084, 1.0, 2);
    expect(h2).toBeCloseTo(h1, 6);
  });

  it('janelas maiores com o mesmo consumo horário dobram a projeção', () => {
    // Aqui a média cai pela metade, então a projeção também.
    const h1 = projectMonthlyCost(0.042, 1.0, 1);
    const h2 = projectMonthlyCost(0.042, 1.0, 2);
    expect(h2).toBeCloseTo(h1 / 2, 6);
  });

  it('devolve 0 para duração inválida em vez de dividir por zero', () => {
    expect(projectMonthlyCost(0.1, 1.0, 0)).toBe(0);
    expect(projectMonthlyCost(0.1, 1.0, -5)).toBe(0);
  });

  it('consumo zero projeta zero', () => {
    expect(projectMonthlyCost(0, 1.25, 8)).toBe(0);
  });
});

describe('sampleIntervalMinutes — intervalo entre amostras', () => {
  it('calcula a partir dos extremos e nunca fica abaixo de 1', () => {
    // 10 amostras em 45 s => 9 intervalos de 5 s; arredonda para 0, mas o piso
    // evita exibir "a cada 0 min" na tela.
    const t0 = Date.parse('2026-09-28T18:00:00Z');
    const iso = Array.from({ length: 10 }, (_, i) =>
      new Date(t0 + i * 5000).toISOString(),
    );
    expect(sampleIntervalMinutes(iso)).toBe(1);
  });

  it('calcula intervalos de minutos corretamente', () => {
    const t0 = Date.parse('2026-09-28T18:00:00Z');
    // 61 amostras em 60 passos de 1 min
    const iso = Array.from({ length: 61 }, (_, i) =>
      new Date(t0 + i * 60_000).toISOString(),
    );
    expect(sampleIntervalMinutes(iso)).toBe(1);
  });

  it('devolve null com dados insuficientes', () => {
    expect(sampleIntervalMinutes([])).toBeNull();
    expect(sampleIntervalMinutes(['2026-09-28T18:00:00Z'])).toBeNull();
  });

  it('devolve null quando o relógio retrocede', () => {
    expect(
      sampleIntervalMinutes(['2026-09-28T18:00:10Z', '2026-09-28T18:00:00Z']),
    ).toBeNull();
  });

  it('calcula intervalos de horas em janelas longas', () => {
    const t0 = Date.parse('2026-09-21T18:00:00Z');
    const iso = Array.from({ length: 8 }, (_, i) =>
      new Date(t0 + i * 24 * 3600_000).toISOString(),
    );
    // 7 intervalos de 24 h
    expect(sampleIntervalMinutes(iso)).toBe(1440);
  });
});

describe('formatCoverage', () => {
  it('formata em porcentagem inteira', () => {
    expect(formatCoverage(1)).toBe('100%');
    expect(formatCoverage(0.085)).toBe('9%');
    expect(formatCoverage(0)).toBe('0%');
  });
});
