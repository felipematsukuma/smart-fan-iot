import { expect, it } from 'vitest';
import controls from '../lib/ws.fixtures.json';
import { isServerControl } from '../lib/ws-control';
import { LiveStore, frameFresh } from './live-store';
import type { FrameReadyV2 } from '../lib/contracts-v2.generated';

function fixture() {
  const raw = structuredClone(
    controls.find((item) => item.name === 'snapshot')!.value,
  );
  if (!isServerControl(raw) || raw.type !== 'snapshot')
    throw new Error('Invalid canonical fixture');
  const frame = raw.events.find(
    (event) => event.tipo === 'frame.ready',
  ) as FrameReadyV2;
  const store = new LiveStore();
  store.replaceDevices(raw.devices);
  return { store, frame, now: Date.parse(frame.metadata.observed_at) };
}
it('requires fresh source and observation, not a connected socket', () => {
  const { store, frame, now } = fixture();
  expect(store.apply(frame, now)).toBe(true);
  expect(frameFresh(frame, now + 6001)).toBe(false);
  expect(store.apply(frame, now + 6001)).toBe(false);
  expect(store.frames.get('ac_01')?.id).toBe(frame.id);
  expect(store.history.get('ac_01')).toHaveLength(1);
});
it('duplicates, reversed sequence and future messages never refresh live values', () => {
  const { store, frame, now } = fixture();
  expect(store.apply(frame, now)).toBe(true);
  expect(store.apply(frame, now)).toBe(false);
  const next = structuredClone(frame);
  next.id = '22222222-2222-4222-8222-222222222222';
  next.timestamp = new Date(now + 1000).toISOString();
  next.metadata.observed_at = next.timestamp;
  expect(store.apply(next, now)).toBe(false);
  expect(store.apply(next, now + 1000)).toBe(false);
  next.metadata.sequence++;
  expect(store.apply(next, now + 1000)).toBe(true);
  expect(store.history.get('ac_01')).toHaveLength(2);
});
it('maps readings to registered identities and clears them when scope is removed', () => {
  const { store, frame, now } = fixture();
  store.apply(frame, now);
  expect(store.sensors.get('ac_01_current')).toBe(
    frame.conteudo.telemetry.readings.current_a,
  );
  expect(store.actuators.get('ac_01_compressor')).toBe(
    frame.conteudo.telemetry.actuators.compressor_on,
  );
  store.replaceDevices([]);
  expect(store.frames.size).toBe(0);
  expect(store.sensors.size).toBe(0);
  expect(store.actuators.size).toBe(0);
});
