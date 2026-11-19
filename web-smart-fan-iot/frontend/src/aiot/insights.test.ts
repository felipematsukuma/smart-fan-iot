import { expect, it } from 'vitest';
import controls from '../lib/ws.fixtures.json';
import type { FrameReadyV2 } from '../lib/contracts-v2.generated';
import { isServerControl } from '../lib/ws-control';
import { alertReason, pointsFromFrames, presentation, trend } from './insights';

it('describes only recorded reasons and preserves combined-rule ambiguity', () => {
  expect(alertReason('health_low')).toBe('Saúde estimada abaixo do limite.');
  expect(alertReason('predictive_health_or_rul')).toContain(
    'condição específica não registrada',
  );
  expect(alertReason('predictive_threshold')).toContain(
    'motivo específico não disponível',
  );
});
it('does not invent a reason for missing or unsupported codes', () => {
  for (const reason of [null, undefined, '', 'unknown', 'rul_low'])
    expect(alertReason(reason)).toBe(
      'Motivo não disponível no registro do alerta.',
    );
});

function fixture() {
  const value = structuredClone(
    controls.find((item) => item.name === 'snapshot')!.value,
  );
  if (!isServerControl(value) || value.type !== 'snapshot')
    throw new Error('Invalid fixture');
  const frame = value.events.find(
    (item) => item.tipo === 'frame.ready',
  ) as FrameReadyV2;
  frame.conteudo.insight = {
    ...frame.conteudo.insight,
    status: 'valid',
    model_version: 'test-model',
    health_score: 72,
    rul_calendar_hours: 38,
  };
  return frame;
}
it('hides stale numbers without relabelling the last model as desired', () => {
  const frame = fixture();
  const now = Date.parse(frame.metadata.observed_at);
  expect(presentation(frame, now).health).toBe(72);
  expect(presentation(frame, now + 6001)).toMatchObject({
    status: 'stale',
    health: null,
    rul: null,
    version: 'test-model',
  });
  expect(presentation(frame, now, false).rul).toBeNull();
});
it.each([
  'warming_up',
  'inactive',
  'insufficient_data',
  'model_unavailable',
  'out_of_domain',
] as const)('abstains for %s', (status) => {
  const frame = fixture();
  frame.conteudo.insight.status = status;
  expect(
    presentation(frame, Date.parse(frame.metadata.observed_at)),
  ).toMatchObject({ status, health: null, rul: null });
});
it('breaks trends at model/boot/time boundaries and never fills unavailable points', () => {
  const first = fixture();
  const second = structuredClone(first);
  second.timestamp = new Date(Date.parse(first.timestamp) + 2000).toISOString();
  second.conteudo.insight.model_version = 'other-model';
  const third = structuredClone(second);
  third.timestamp = new Date(Date.parse(second.timestamp) + 8000).toISOString();
  third.conteudo.insight.status = 'model_unavailable';
  const series = trend(
    pointsFromFrames([first, second, third]),
    'rul_calendar_hours',
  );
  expect(series.values).toEqual([38, null, 38, null, null]);
});
