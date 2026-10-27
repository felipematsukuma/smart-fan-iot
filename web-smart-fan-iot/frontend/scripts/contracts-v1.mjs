import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { compileFromFile } from 'json-schema-to-typescript';
import { format, resolveConfig } from 'prettier';

const input = fileURLToPath(
  new URL('../src/lib/contracts-v1.schema.json', import.meta.url),
);
const output = fileURLToPath(
  new URL('../src/lib/contracts-v1.generated.ts', import.meta.url),
);
const generated = await compileFromFile(input, {
  bannerComment:
    '/** Generated from the canonical Python wire schema. Do not edit by hand. */',
});
const content = await format(generated, {
  ...(await resolveConfig(output)),
  filepath: output,
});
if (process.argv.includes('--check')) {
  if ((await readFile(output, 'utf8')) !== content) {
    throw new Error('Generated wire types differ; run npm run contracts:types');
  }
} else {
  await writeFile(output, content, 'utf8');
}
