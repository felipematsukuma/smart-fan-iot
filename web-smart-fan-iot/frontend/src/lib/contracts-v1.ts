import { eventV1 as validate } from './validators.generated.mjs';
import type { EventV1 } from './contracts-v1.generated';

/** Validate against the schema exported from Python, without coercing input. */
export function isEventV1(value: unknown): value is EventV1 {
  return validate(value);
}
