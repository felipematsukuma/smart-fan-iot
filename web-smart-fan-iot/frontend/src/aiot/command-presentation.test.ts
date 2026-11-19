import { expect, it } from 'vitest';
import { commandPresentation } from './command-presentation';
it('never presents API acceptance or an unreferenced acknowledgement as physical execution', () => {
  expect(
    commandPresentation({ status: 'pending', execution_unknown: false }).label,
  ).toContain('Aceito pela API');
  expect(
    commandPresentation({ status: 'confirmed', execution_unknown: false })
      .label,
  ).toBe('Sem execução confirmada');
  expect(
    commandPresentation({
      status: 'confirmed',
      execution_unknown: false,
      ack_event_id: 'physical-event',
    }).label,
  ).toBe('Executado pelo dispositivo');
});
it('keeps an uncertain physical outcome distinct from rejection and from sending', () => {
  expect(
    commandPresentation({ status: 'failed', execution_unknown: true }).label,
  ).toBe('Execução desconhecida');
  expect(
    commandPresentation({
      status: 'failed',
      execution_unknown: false,
      ack_event_id: 'rejected',
    }).label,
  ).toBe('Sem execução confirmada');
  expect(commandPresentation(undefined, true).label).toBe(
    'Enviando solicitação',
  );
});
