import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import standalone from 'ajv/dist/standalone/index.js';
import { format, resolveConfig } from 'prettier';

const directory = new URL('../src/lib/', import.meta.url);
const ajv = new Ajv2020({
  allErrors: true,
  inlineRefs: false,
  coerceTypes: false,
  useDefaults: false,
  code: { source: true, esm: true },
});
addFormats(ajv);
const exports = {
  eventV1: 'contracts-v1',
  eventV2: 'contracts-v2',
  serverControl: 'ws-server',
  clientPacket: 'ws-client',
};
for (const key of Object.values(exports))
  ajv.addSchema(
    JSON.parse(
      await readFile(new URL(`${key}.schema.json`, directory), 'utf8'),
    ),
    key,
  );
let code = standalone(ajv, exports);
code = code
  .replaceAll('require("ajv-formats/dist/formats").fullFormats', 'fullFormats')
  .replaceAll('require("ajv/dist/runtime/ucs2length").default', 'ucs2Length');
if (/\brequire\(/.test(code))
  throw new Error('Unmapped standalone runtime import');
const output = fileURLToPath(new URL('validators.generated.mjs', directory));
const content = await format(
  `/* eslint-disable */\n/** Generated validators: build-time compilation, no unsafe-eval. */\nimport { fullFormats } from 'ajv-formats/dist/formats.js';\nimport * as ucs2Runtime from 'ajv/dist/runtime/ucs2length.js';\nconst ucs2Length = typeof ucs2Runtime.default === 'function' ? ucs2Runtime.default : ucs2Runtime.default.default;\n${code}`,
  { ...(await resolveConfig(output)), filepath: output },
);
if (process.argv.includes('--check')) {
  if (
    (await readFile(output, 'utf8')).replaceAll('\r\n', '\n') !==
    content.replaceAll('\r\n', '\n')
  )
    throw new Error('Generated validators differ');
} else await writeFile(output, content, 'utf8');
