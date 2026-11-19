import { expect, it } from 'vitest';
import controls from '../lib/ws.fixtures.json';
import { isServerControl } from '../lib/ws-control';
import {
  allowedCombinations,
  chartSamples,
  readings,
  selectReading,
  type ReadingKey,
} from './live-chart';

it('keeps at least one series and only permits explicitly reviewed combinations', () => {
  for (const combo of allowedCombinations) {
    for (const reading of readings) {
      const next = selectReading([...combo], reading.key);
      expect(
        allowedCombinations.some(
          (allowed) =>
            allowed.length === next.length &&
            allowed.every((key) => next.includes(key)),
        ),
      ).toBe(true);
      expect(next.length).toBeGreaterThanOrEqual(1);
      expect(next.length).toBeLessThanOrEqual(3);
    }
  }
  expect(selectReading(['power_w'], 'power_w')).toEqual(['power_w']);
  expect(
    selectReading(['indoor_temp_c', 'outdoor_temp_c'], 'current_a'),
  ).toEqual(['current_a']);
});

it('preserves zero, nulls, timestamps, restart gaps and fixed style identity', () => {
  const raw: unknown = structuredClone(
    controls.find((item) => item.name === 'snapshot')!.value,
  );
  if (!isServerControl(raw) || raw.type !== 'snapshot')
    throw new Error('Invalid fixture');
  const first = raw.events.find((event) => event.tipo === 'frame.ready');
  if (!first || first.tipo !== 'frame.ready') throw new Error('Missing frame');
  first.conteudo.telemetry.readings.indoor_temp_c = 0;
  first.conteudo.telemetry.readings.outdoor_temp_c = null;
  first.conteudo.telemetry.quality.missing_fields = ['outdoor_temp_c'];
  const second = structuredClone(first);
  second.timestamp = new Date(Date.parse(first.timestamp) + 8000).toISOString();
  const selected: ReadingKey[] = [
    'indoor_temp_c',
    'outdoor_temp_c',
    'compressor_case_temp_c',
  ];
  const all = chartSamples([first, second], selected);
  expect(all.datasets[0]!.data).toEqual([0, null, 0]);
  expect(all.datasets[1]!.data).toEqual([null, null, null]);
  expect(all.labels[0]).toBe(
    new Date(first.timestamp).toLocaleTimeString('pt-BR'),
  );
  const single = chartSamples([first, second], ['outdoor_temp_c']);
  expect(single.datasets[0]).toEqual(all.datasets[1]);
  second.timestamp = new Date(Date.parse(first.timestamp) + 2000).toISOString();
  second.metadata.boot_id = 'other-boot';
  expect(chartSamples([first, second], selected).datasets[0]!.data).toEqual([
    0,
    null,
    0,
  ]);
});
