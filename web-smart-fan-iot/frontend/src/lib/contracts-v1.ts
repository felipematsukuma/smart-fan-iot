import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import schema from './contracts-v1.schema.json';
import type { EventV1 } from './contracts-v1.generated';

const ajv = new Ajv2020({
  allErrors: true,
  coerceTypes: false,
  useDefaults: false,
});
addFormats(ajv);
const validate = ajv.compile<EventV1>(schema);

/** Validate against the schema exported from Python, without coercing input. */
export function isEventV1(value: unknown): value is EventV1 {
  return validate(value);
}
