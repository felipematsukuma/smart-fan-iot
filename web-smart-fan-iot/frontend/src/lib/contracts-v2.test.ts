import { describe, expect, it } from 'vitest';
import cases from './contracts-v2.fixtures.json';
import { isEventV2, parseEventV2 } from './contracts-v2';

describe('v2 Python/TypeScript contract and semantic invariants', () => {
  for (const sample of cases) {
    it(sample.name, () => expect(isEventV2(sample.value)).toBe(sample.valid));
  }
  it('enforces wire bytes and rejects non-finite values', () => {
    const sample: unknown = structuredClone(cases[0].value);
    if (!isEventV2(sample) || sample.tipo !== 'telemetry.sampled')
      throw new Error('Expected sample');
    expect(parseEventV2(JSON.stringify(sample))).toEqual(sample);
    expect(() =>
      parseEventV2(JSON.stringify(sample) + ' '.repeat(16384)),
    ).toThrow();
    sample.conteudo.readings.current_a = Number.NaN;
    expect(isEventV2(sample)).toBe(false);
  });
});
