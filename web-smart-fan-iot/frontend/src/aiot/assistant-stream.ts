/** Incremental SSE parser; limits survive UTF-8 and event boundaries split by TCP. */
export interface AssistantEvent {
  event: 'meta' | 'delta' | 'done' | 'error';
  data: Record<string, unknown>;
}
export async function consumeSse(
  response: Response,
  signal: AbortSignal,
  receive: (event: AssistantEvent) => void,
) {
  if (
    !response.headers.get('content-type')?.startsWith('text/event-stream') ||
    !response.body
  )
    throw new Error('Resposta de streaming inválida.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let buffer = '',
    total = 0,
    ended = false;
  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > 131072) throw new Error('Resposta excedeu o limite local.');
      buffer += decoder.decode(value, { stream: true });
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const packet = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (packet.startsWith(':')) continue;
        const lines = packet.split('\n');
        const kind = lines.find((line) => line.startsWith('event: '))?.slice(7);
        const raw = lines
          .filter((line) => line.startsWith('data: '))
          .map((line) => line.slice(6))
          .join('\n');
        if (!['meta', 'delta', 'done', 'error'].includes(kind ?? ''))
          throw new Error('Evento de streaming inválido.');
        const data: unknown = JSON.parse(raw);
        if (!data || typeof data !== 'object' || Array.isArray(data))
          throw new Error('Conteúdo de streaming inválido.');
        if (
          kind === 'delta' &&
          (!('text' in data) || typeof data.text !== 'string')
        )
          throw new Error('Fragmento de resposta inválido.');
        receive({
          event: kind as AssistantEvent['event'],
          data: data as Record<string, unknown>,
        });
        if (kind === 'done' || kind === 'error') {
          ended = true;
          return;
        }
      }
      if (buffer.length > 65536)
        throw new Error('Evento excedeu o limite local.');
    }
    if (!signal.aborted && !ended)
      throw new Error('Resposta interrompida antes da conclusão.');
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
