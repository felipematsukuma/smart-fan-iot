import { describe, expect, it } from 'vitest';
import {
  COMMAND_TIMEOUT_MS,
  OFFLINE_FRESHNESS_MS,
  PERIODS,
  formatLastSeen,
  isDeviceOnline,
  isMultiDay,
  periodLabel,
} from './freshness';

// Intervalos medidos em produção, dentro de sessões ativas.
const GAPS = [
  2.41, 2.9, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.83, 3.85, 3.9, 3.9, 3.95,
  4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.78, 4.9, 5.0, 5.1, 5.2, 5.3, 5.32,
  5.4, 6.0, 7.0, 10.19, 11.4, 13.2, 14.43, 18.7, 28.08, 31.15, 32.01, 35.59,
  41.02, 43.36, 45.02, 51.59, 68.4,
];

describe('isDeviceOnline — regra de frescor', () => {
  it('exige socket conectado', () => {
    const agora = 1_000_000;
    expect(isDeviceOnline(false, agora, agora)).toBe(false);
  });

  it('exige ao menos uma mensagem recebida', () => {
    expect(isDeviceOnline(true, null, 1_000_000)).toBe(false);
  });

  it('aceita mensagem recém-chegada', () => {
    const agora = 1_000_000;
    expect(isDeviceOnline(true, agora, agora)).toBe(true);
    expect(isDeviceOnline(true, agora - 5_000, agora)).toBe(true);
  });

  it('nunca marca offline durante a cadência real medida', () => {
    // Reproduz a cadência inteira: nenhuma lacuna pode virar OFFLINE.
    const agora = 10_000_000;
    let ultima = agora;
    for (const gap of GAPS) {
      const t = ultima + gap * 1000;
      expect(
        isDeviceOnline(true, ultima, t),
        `lacuna de ${gap}s não deveria marcar offline`
      ).toBe(true);
      ultima = t;
    }
  });

  it('com a folga antiga de 10 s a cadência real causaria falsos offline', () => {
    // Regressão documentada: era esse o defeito.
    const agora = 10_000_000;
    let ultima = agora;
    let falsos = 0;
    for (const gap of GAPS) {
      const t = ultima + gap * 1000;
      if (ultima !== null && t - ultima > 10_000) falsos += 1;
      ultima = t;
    }
    expect(falsos).toBeGreaterThan(0);
  });

  it('marca offline quando a ausência é real', () => {
    const agora = 1_000_000;
    const velha = agora - OFFLINE_FRESHNESS_MS - 1;
    expect(isDeviceOnline(true, velha, agora)).toBe(false);
  });

  it('aceita exatamente na borda da tolerância', () => {
    const agora = 1_000_000;
    const naBorda = agora - OFFLINE_FRESHNESS_MS;
    expect(isDeviceOnline(true, naBorda, agora)).toBe(true);
  });

  it('cobre toda a cauda observada com margem', () => {
    const maiorLacuna = Math.max(...GAPS) * 1000;
    expect(maiorLacuna).toBeLessThan(OFFLINE_FRESHNESS_MS);
  });
});

describe('formatLastSeen', () => {
  const agora = 1_000_000;

  it('sem mensagem mostra "sem sinal"', () => {
    expect(formatLastSeen(null, agora)).toBe('sem sinal');
  });

  it('até 3 s mostra "agora mesmo"', () => {
    expect(formatLastSeen(agora, agora)).toBe('agora mesmo');
    expect(formatLastSeen(agora - 2500, agora)).toBe('agora mesmo');   // 2,5 s
    expect(formatLastSeen(agora - 2999, agora)).toBe('agora mesmo');
  });

  it('a partir de 3 s passa a mostrar segundos', () => {
    expect(formatLastSeen(agora - 3000, agora)).toBe('há 3 s');
  });

  it('entre 3 s e 1 min mostra segundos', () => {
    expect(formatLastSeen(agora - 8000, agora)).toBe('há 8 s');
    expect(formatLastSeen(agora - 59_000, agora)).toBe('há 59 s');
  });

  it('acima de 1 min mostra minutos', () => {
    expect(formatLastSeen(agora - 60_000, agora)).toBe('há 1 min');
    expect(formatLastSeen(agora - 600_000, agora)).toBe('há 10 min');
  });

  it('nunca mostra segundo negativo', () => {
    // relógio do navegador andando para trás
    expect(formatLastSeen(agora + 5000, agora)).toBe('agora mesmo');
  });
});

describe('períodos de análise', () => {
  it('os atalhos cobrem 8h, 24h e 7d', () => {
    expect(PERIODS['8h']).toBe(8);
    expect(PERIODS['24h']).toBe(24);
    expect(PERIODS['7d']).toBe(168);
  });

  it('7d bate com o limite do backend (168 h)', () => {
    expect(PERIODS['7d']).toBe(168);
  });

  it('só o 7d precisa mostrar o dia nos rótulos', () => {
    expect(isMultiDay('8h')).toBe(false);
    expect(isMultiDay('24h')).toBe(false);
    expect(isMultiDay('7d')).toBe(true);
  });

  it('rótulo legível para cada período', () => {
    expect(periodLabel('8h')).toBe('Últimas 8h');
    expect(periodLabel('24h')).toBe('Últimas 24h');
    expect(periodLabel('7d')).toBe('Últimas 168h');
    expect(periodLabel('custom')).toBe('Período personalizado');
  });
});

describe('tempos de espera', () => {
  it('a confirmação de comando é independente da folga de offline', () => {
    // O ESP32 publica `state` assim que recebe o comando, então a confirmação
    // não depende da cadência da telemetria: 10 s continua correto mesmo com a
    // folga de offline em 90 s.
    expect(COMMAND_TIMEOUT_MS).toBeLessThan(OFFLINE_FRESHNESS_MS);
  });
});
