import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { compileFromFile } from 'json-schema-to-typescript';
import { format, resolveConfig } from 'prettier';

for (const name of ['ws-client', 'ws-server']) {
  const input = fileURLToPath(
    new URL(`../src/lib/${name}.schema.json`, import.meta.url),
  );
  const output = fileURLToPath(
    new URL(`../src/lib/${name}.generated.ts`, import.meta.url),
  );
  const generated = await compileFromFile(input, {
    bannerComment:
      '/** Generated from canonical Python WebSocket controls. Do not edit by hand. */',
  });
  const content = await format(generated, {
    ...(await resolveConfig(output)),
    filepath: output,
  });
  if (process.argv.includes('--check')) {
    if (
      (await readFile(output, 'utf8')).replaceAll('\r\n', '\n') !==
      content.replaceAll('\r\n', '\n')
    )
      throw new Error('Generated WebSocket types differ');
  } else await writeFile(output, content, 'utf8');
}
