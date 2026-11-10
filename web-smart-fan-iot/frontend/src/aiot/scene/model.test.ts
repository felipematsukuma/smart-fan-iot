import { expect, it } from 'vitest';
import controls from '../../lib/ws.fixtures.json';
import type { FrameReadyV2 } from '../../lib/contracts-v2.generated';
import { isServerControl } from '../../lib/ws-control';
import { entities, sensorColor, state } from './model';
function fixture() {
  const value = structuredClone(
    controls.find((item) => item.name === 'snapshot')!.value,
  );
  if (!isServerControl(value) || value.type !== 'snapshot')
    throw new Error('Invalid fixture');
  const frame = value.events.find(
    (item) => item.tipo === 'frame.ready',
  ) as FrameReadyV2;
  const device = value.devices[0]!;
  device.boot_id = frame.metadata.boot_id;
  return { frame, device, now: Date.parse(frame.metadata.observed_at) };
}
it('uses the registered equipment, five sensor and two actuator identities', () => {
  const { device } = fixture();
  const items = entities(device);
  expect(items).toHaveLength(8);
  expect(new Set(items.map((item) => item.id)).size).toBe(8);
  expect(items.filter((item) => item.kind === 'sensor')).toHaveLength(5);
  expect(items.filter((item) => item.kind === 'actuator')).toHaveLength(2);
});
it('freezes on stale, future, disabled or different boot without extrapolation', () => {
  const { frame, device, now } = fixture();
  expect(state(frame, device, now)?.fan).toBe(
    frame.conteudo.telemetry.actuators.condenser_fan_on,
  );
  expect(state(frame, device, now + 6001)).toBeNull();
  expect(state(frame, device, Date.parse(frame.timestamp) - 1)).toBeNull();
  expect(state(frame, { ...device, enabled: false }, now)).toBeNull();
  expect(state(frame, { ...device, boot_id: 'another-boot' }, now)).toBeNull();
});
it('never colors missing sensors or missing configured ranges as healthy', () => {
  expect(sensorColor(null, { minimum: 0, maximum: 3 })).toBe('#8b9aab');
  expect(sensorColor(1)).toBe('#8b9aab');
  expect(sensorColor(1, { minimum: 0, maximum: 3 })).toBe('#238574');
  expect(sensorColor(4, { minimum: 0, maximum: 3 })).toBe('#d38a29');
});
