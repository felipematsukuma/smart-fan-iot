import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {
  apiResponse,
  clearSession,
  currentUser,
  onSessionEnded,
  sessionNotice,
  signIn,
  signOut,
} from './auth';

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  vi.useFakeTimers();
  clearSession();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  clearSession();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
async function authenticate() {
  fetchMock
    .mockResolvedValueOnce(
      Response.json({
        access_token: 'unit-only',
        expires_at: new Date(Date.now() + 10000).toISOString(),
      }),
    )
    .mockResolvedValueOnce(
      Response.json({
        id: 'fixture-user',
        username: 'fixture',
        role: 'operador',
      }),
    );
  await signIn('fixture', 'local-placeholder');
}

it.each(['https://example.invalid', '//example.invalid', 'relative'])(
  'rejects nonlocal API path %s before sending credentials',
  async (path) => {
    await expect(apiResponse(path)).rejects.toThrow('Rota inválida');
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

it('keeps a valid session through transport failure, with no cookie fallback', async () => {
  await authenticate();
  fetchMock.mockRejectedValueOnce(new TypeError('offline'));
  await expect(apiResponse('/devices')).rejects.toMatchObject({ status: 0 });
  expect(currentUser.value?.id).toBe('fixture-user');
  const options = fetchMock.mock.calls.at(-1)![1]!;
  expect(options).toMatchObject({ credentials: 'omit', cache: 'no-store' });
  expect(new Headers(options.headers).get('Authorization')).toBe(
    'Bearer unit-only',
  );
});

it.each([
  [503, 'not JSON', 'Não foi possível concluir a operação.'],
  [403, JSON.stringify({ title: 42 }), 'Não foi possível concluir a operação.'],
  [429, JSON.stringify({ title: 'Cota esgotada' }), 'Cota esgotada'],
])(
  'preserves session and safe error details for HTTP %s',
  async (status, body, message) => {
    await authenticate();
    fetchMock.mockResolvedValueOnce(
      new Response(body, {
        status,
        headers: { 'X-Correlation-ID': 'fixture-correlation' },
      }),
    );
    await expect(apiResponse('/devices')).rejects.toMatchObject({
      status,
      message,
      correlationId: 'fixture-correlation',
    });
    expect(currentUser.value?.id).toBe('fixture-user');
  },
);

it('clears an authenticated session on 401 and removes its bearer from the next request', async () => {
  await authenticate();
  const ended = vi.fn();
  const unsubscribe = onSessionEnded(ended);
  try {
    fetchMock.mockResolvedValueOnce(new Response('', { status: 401 }));
    await expect(apiResponse('/devices')).rejects.toMatchObject({
      status: 401,
    });
    expect(currentUser.value).toBeNull();
    expect(sessionNotice.value).toContain('Sua sessão expirou');
    expect(ended).toHaveBeenCalledTimes(1);
    fetchMock.mockResolvedValueOnce(Response.json({}));
    await apiResponse('/snapshot');
    expect(
      new Headers(fetchMock.mock.calls.at(-1)![1]!.headers).has(
        'Authorization',
      ),
    ).toBe(false);
  } finally {
    unsubscribe();
  }
});

it('does not retain credentials if the user lookup fails after login', async () => {
  fetchMock
    .mockResolvedValueOnce(
      Response.json({
        access_token: 'unit-only',
        expires_at: new Date(Date.now() + 10000).toISOString(),
      }),
    )
    .mockResolvedValueOnce(new Response('unavailable', { status: 503 }));
  await expect(signIn('fixture', 'local-placeholder')).rejects.toMatchObject({
    status: 503,
  });
  expect(currentUser.value).toBeNull();
  fetchMock.mockResolvedValueOnce(Response.json({}));
  await apiResponse('/snapshot');
  expect(
    new Headers(fetchMock.mock.calls.at(-1)![1]!.headers).has('Authorization'),
  ).toBe(false);
});

it('expires locally on schedule and releases unsubscribed listeners', async () => {
  await authenticate();
  const ended = vi.fn();
  const unsubscribe = onSessionEnded(ended);
  unsubscribe();
  vi.advanceTimersByTime(10000);
  expect(currentUser.value).toBeNull();
  expect(sessionNotice.value).toContain('Sua sessão expirou');
  expect(ended).not.toHaveBeenCalled();
});

it('clears local credentials even when server-side logout cannot be reached', async () => {
  await authenticate();
  fetchMock.mockRejectedValueOnce(new TypeError('offline'));
  await expect(signOut()).rejects.toMatchObject({ status: 0 });
  expect(currentUser.value).toBeNull();
  fetchMock.mockResolvedValueOnce(Response.json({}));
  await apiResponse('/snapshot');
  expect(
    new Headers(fetchMock.mock.calls.at(-1)![1]!.headers).has('Authorization'),
  ).toBe(false);
});

it('accepts empty logout responses and never revokes again without a session', async () => {
  await authenticate();
  fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
  await expect(signOut()).resolves.toBeUndefined();
  expect(currentUser.value).toBeNull();
  const requests = fetchMock.mock.calls.length;
  await expect(signOut()).resolves.toBeUndefined();
  expect(fetchMock).toHaveBeenCalledTimes(requests);
});
