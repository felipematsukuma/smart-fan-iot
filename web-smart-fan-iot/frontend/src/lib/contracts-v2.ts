import { eventV2 as structural } from './validators.generated.mjs';
import type { EventV2 } from './contracts-v2.generated';

// UTC timestamps have at most six fractional digits. Date.parse truncates
// microseconds, so use an equivalent fixed-precision key after schema validation.
const utcKey = (value: string) =>
  value.slice(0, 19) +
  '.' +
  value.slice(19, -1).replace('.', '').padEnd(6, '0');

/** JSON Schema validates shape; these cross-field invariants are not expressible in standard JSON Schema. */
export function isEventV2(value: unknown): value is EventV2 {
  if (!structural(value)) return false;
  if (value.tipo === 'command.requested') {
    if (value.id !== value.conteudo.command_id) return false;
    if (utcKey(value.conteudo.expires_at) <= utcKey(value.timestamp))
      return false;
  }
  if (
    value.tipo === 'frame.ready' &&
    value.conteudo.source_event_id !== value.conteudo.telemetry.source_event_id
  )
    return false;
  if (
    value.tipo === 'job.progress' &&
    value.conteudo.processed > value.conteudo.total
  )
    return false;
  return true;
}

/** Enforce byte limits at the wire boundary, not by JS string character count. */
export function parseEventV2(payload: string): EventV2 {
  const size = new TextEncoder().encode(payload).byteLength;
  if (size > 32768) throw new Error('Event exceeds transport limit');
  const value: unknown = JSON.parse(payload);
  if (!isEventV2(value)) throw new Error('Invalid v2 event');
  if (value.tipo !== 'message.quarantined' && size > 16384)
    throw new Error('Event exceeds normal limit');
  return value;
}
