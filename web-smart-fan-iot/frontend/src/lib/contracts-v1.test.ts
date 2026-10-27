import { describe, expect, it } from 'vitest';
import cases from './contracts-v1.fixtures.json';
import { isEventV1 } from './contracts-v1';

describe('canonical Python/TypeScript wire contract', () => {
  for (const sample of cases) {
    it(sample.name, () => {
      expect(isEventV1(sample.value)).toBe(sample.valid);
    });
  }
  it('rejects native non-finite values', () => {
    const value = structuredClone(cases[0].value);
    if (!('readings' in value.data) || !value.data.readings)
      throw new Error('Expected telemetry fixture');
    value.data.readings.current_a = Number.NaN;
    expect(isEventV1(value)).toBe(false);
  });
});
