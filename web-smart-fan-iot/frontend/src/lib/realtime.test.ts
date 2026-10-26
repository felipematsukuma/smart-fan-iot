import { expect, it } from 'vitest';
import { isRealtimeMessage } from './realtime';

it('rejects malformed external telemetry rather than trusting TS types', () => {
  const valid = {
    device_id: 'fan',
    event: 'telemetry',
    is_on: false,
    voltage_rms: 127,
    current_a: 0,
    power_w: 0,
    timestamp: 10,
  };
  expect(isRealtimeMessage(valid)).toBe(true);
  expect(isRealtimeMessage({ ...valid, is_on: 'false' })).toBe(false);
  expect(isRealtimeMessage({ ...valid, power_w: -1 })).toBe(false);
  expect(isRealtimeMessage({ ...valid, power_w: Infinity })).toBe(false);
  expect(isRealtimeMessage(null)).toBe(false);
});
