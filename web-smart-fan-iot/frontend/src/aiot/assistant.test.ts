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

it('validates transport and event envelopes before rendering model output', async () => {
  const controller = new AbortController();
  const events: string[] = [];
  await expect(
    consumeSse(new Response('plain text'), controller.signal, () => undefined),
  ).rejects.toThrow('streaming inválida');
  const response = (value: BodyInit) =>
    new Response(value, { headers: { 'Content-Type': 'text/event-stream' } });
  await consumeSse(
    response(
      ': heartbeat\n\nevent: meta\ndata: {"state":"queued"}\n\nevent: error\ndata: {"code":"unavailable"}\n\n',
    ),
    controller.signal,
    (value) => events.push(value.event),
  );
  expect(events).toEqual(['meta', 'error']);
  await expect(
    consumeSse(
      response('event: unknown\ndata: {}\n\n'),
      controller.signal,
      () => undefined,
    ),
  ).rejects.toThrow('Evento');
  await expect(
    consumeSse(
      response('event: meta\ndata: null\n\n'),
      controller.signal,
      () => undefined,
    ),
  ).rejects.toThrow('Conteúdo');
  await expect(
    consumeSse(
      response(new Uint8Array(131073)),
      controller.signal,
      () => undefined,
    ),
  ).rejects.toThrow('limite');
  controller.abort();
  await consumeSse(response(''), controller.signal, () => {
    throw new Error('Aborted consumer must not receive output');
  });
  expect(
    safeMarkdown('[local](/admin) [mail](mailto:someone@example.com)'),
  ).not.toContain('<a');
});
