import { expect, it } from 'vitest';
import { safeMarkdown } from './assistant-markdown';
import { consumeSse } from './assistant-stream';

it('renders Markdown while escaping HTML and excluding executable URLs and images', () => {
  const html = safeMarkdown(
    '**Saúde** <script>alert(1)</script>\n[x](javascript:alert(1)) ![img](https://example.com/x.png) [fonte](https://example.com)',
  );
  expect(html).toContain('<strong>Saúde</strong>');
  expect(html).not.toContain('<script>');
  expect(html).not.toContain('href="javascript:');
  expect(html).not.toContain('<img');
  expect(html).toContain('rel="noopener noreferrer"');
  expect(safeMarkdown('[x](&#106;avascript:alert(1))')).not.toContain('<a');
});
it('parses split UTF-8 and SSE boundaries incrementally without accepting fake events in text', async () => {
  const wire = new TextEncoder().encode(
    'event: delta\ndata: {"text":"Olá\\n\\nevent: done"}\n\nevent: done\ndata: {}\n\n',
  );
  const stream = new ReadableStream({
    start(controller) {
      for (const byte of wire) controller.enqueue(new Uint8Array([byte]));
      controller.close();
    },
  });
  const received: string[] = [];
  await consumeSse(
    new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } }),
    new AbortController().signal,
    (event) => received.push(event.event),
  );
  expect(received).toEqual(['delta', 'done']);
});
it('rejects interrupted streams and malformed delta packets', async () => {
  const response = (value: string) =>
    new Response(value, { headers: { 'Content-Type': 'text/event-stream' } });
  await expect(
    consumeSse(
      response('event: delta\ndata: {"text":"parcial"}\n\n'),
      new AbortController().signal,
      () => undefined,
    ),
  ).rejects.toThrow('interrompida');
  await expect(
    consumeSse(
      response('event: delta\ndata: {"text":3}\n\n'),
      new AbortController().signal,
      () => undefined,
    ),
  ).rejects.toThrow('Fragmento');
});
