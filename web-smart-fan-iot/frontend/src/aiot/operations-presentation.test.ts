import { describe, it, expect } from 'vitest';
import {
  messagingStale,
  outcomeLabels,
  actionLabels,
  queueLabels,
} from './operations-presentation';
describe('apresentação operacional', () => {
  it('frescor considera duas consultas e cache sem trocar rótulo por segundo', () => {
    const time = Date.parse('2026-11-15T12:00:00Z');
    expect(messagingStale('2026-11-15T12:00:00Z', 2, time + 12000)).toBe(false);
    expect(messagingStale('2026-11-15T12:00:00Z', 2, time + 12001)).toBe(true);
    expect(messagingStale('invalid', 2, time)).toBe(true);
  });
  it('falha e cancelamento não são classificados como negação', () => {
    expect(outcomeLabels.failure).toBe('Falhou');
    expect(outcomeLabels.cancelled).toBe('Cancelada');
    expect(outcomeLabels.denied).toBe('Negada');
  });
  it('traduções não confundem solicitação, confirmação e execução', () => {
    expect(actionLabels['command.unconfirmed']).toContain('sem confirmação');
    expect(actionLabels['model.promotion_requested']).toContain('solicitadas');
    expect(queueLabels['q.jobs.generate']).toBe('Geração de dados');
  });
});
