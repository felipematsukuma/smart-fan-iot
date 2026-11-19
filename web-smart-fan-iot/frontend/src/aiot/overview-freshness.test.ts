import { expect, it } from 'vitest';
import controls from '../lib/ws.fixtures.json';
import { isServerControl } from '../lib/ws-control';
import { frameFresh } from './live-store';
import { overviewFreshness } from './overview-freshness';

function sample() {
  const snapshot: unknown = structuredClone(
    controls.find((item) => item.name === 'snapshot')!.value,
  );
  if (!isServerControl(snapshot) || snapshot.type !== 'snapshot')
    throw new Error('Invalid fixture');
  const frame = snapshot.events.find((item) => item.tipo === 'frame.ready');
  if (!frame || frame.tipo !== 'frame.ready') throw new Error('Missing frame');
  frame.timestamp = '2026-11-15T12:00:00.100Z';
  frame.metadata.observed_at = frame.timestamp;
  return {
    frame,
    at: Date.parse(frame.timestamp),
    boot: frame.metadata.boot_id,
  };
}
it('reproduces the cached clock race and classifies age/freshness at the actual reference', () => {
  const { frame, at, boot } = sample();
  expect(frameFresh(frame, at - 100)).toBe(false); // previous 500ms UI tick
  expect(overviewFreshness(frame, boot, at + 1)).toMatchObject({
    fresh: true,
    age: 0,
    kind: 'recent',
  });
  expect(overviewFreshness(frame, boot, at + 6000)).toMatchObject({
    fresh: true,
    age: 6,
  });
  expect(overviewFreshness(frame, boot, at + 6001)).toMatchObject({
    fresh: false,
    age: 6,
    kind: 'old',
  });
  for (let elapsed = 0; elapsed < 10000; elapsed += 25) {
    const state = overviewFreshness(frame, boot, at + elapsed);
    if (state.kind === 'old') expect(state.age).toBeGreaterThanOrEqual(6);
  }
});
it('distinguishes missing telemetry and boot/clock unavailability from old data', () => {
  const { frame, at, boot } = sample();
  expect(overviewFreshness(undefined, boot, at)).toMatchObject({
    kind: 'missing',
    age: null,
  });
  expect(overviewFreshness(frame, 'new-boot', at)).toMatchObject({
    kind: 'unavailable',
    age: 0,
  });
  expect(overviewFreshness(frame, boot, at - 1)).toMatchObject({
    kind: 'unavailable',
    age: null,
  });
});
