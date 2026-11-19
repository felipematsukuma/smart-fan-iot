import type { FrameReadyV2 } from '../lib/contracts-v2.generated';
import { frameFresh } from './live-store';

export function overviewFreshness(
  frame: FrameReadyV2 | undefined,
  bootId: string | null | undefined,
  reference: number,
) {
  if (!frame)
    return {
      kind: 'missing' as const,
      fresh: false,
      age: null,
      reference,
      reason: 'Aguardando a primeira leitura.',
    };
  const sampled = Date.parse(frame.timestamp);
  const observed = Date.parse(frame.metadata.observed_at);
  const age = Math.floor((reference - sampled) / 1000);
  if (!Number.isFinite(age) || sampled > observed || observed > reference)
    return {
      kind: 'unavailable' as const,
      fresh: false,
      age: null,
      reference,
      reason: 'Horário da amostra inconsistente.',
    };
  if (bootId !== frame.metadata.boot_id)
    return {
      kind: 'unavailable' as const,
      fresh: false,
      age,
      reference,
      reason: 'Aguardando leituras da inicialização atual.',
    };
  const fresh = frameFresh(frame, reference);
  return {
    kind: fresh ? ('recent' as const) : ('old' as const),
    fresh,
    age,
    reference,
    reason: '',
  };
}
