import { serverControl as structural } from './validators.generated.mjs';
import type { ServerControl } from './ws-server.generated';
import { isEventV2 } from './contracts-v2';

export function isServerControl(value: unknown): value is ServerControl {
  return (
    structural(value) &&
    (value.type !== 'snapshot' || value.events.every(isEventV2))
  );
}
