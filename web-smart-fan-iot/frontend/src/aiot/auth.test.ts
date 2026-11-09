import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  api,
  ApiError,
  clearSession,
  currentUser,
  signIn,
  signOut,
} from './auth';
import { mayVisit, safeDestination } from './access';

const user = {
  id: 'test-user',
  username: 'viewer',
  role: 'visualizador' as const,
  expires_at: '',
};
function authenticatedResponses(milliseconds = 1800000) {
  const expiration = new Date(Date.now() + milliseconds).toISOString();
  return vi
    .fn()
    .mockResolvedValueOnce(
      Response.json({
        access_token: 'memory-only-test-token',
        expires_at: expiration,
      }),
    )
    .mockResolvedValueOnce(Response.json({ ...user, expires_at: expiration }));
}
beforeEach(() => {
  clearSession();
  vi.useFakeTimers();
});
afterEach(() => {
  clearSession();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('authenticated client boundary', () => {
  it('keeps access in memory and sends Bearer only to the relative API', async () => {
    const fetch = authenticatedResponses();
    vi.stubGlobal('fetch', fetch);
    vi.stubGlobal(
      'localStorage',
      new Proxy(
        {},
        {
          get() {
            throw new Error('Persistent token storage is forbidden');
          },
        },
      ),
    );
    vi.stubGlobal(
      'sessionStorage',
      new Proxy(
        {},
        {
          get() {
            throw new Error('Persistent token storage is forbidden');
          },
        },
      ),
    );
    await signIn('viewer', 'test-only-password');
    expect(currentUser.value?.role).toBe('visualizador');
    const first = fetch.mock.calls[0]![1] as RequestInit;
    const second = fetch.mock.calls[1]![1] as RequestInit;
    expect(new Headers(first.headers).has('Authorization')).toBe(false);
    expect(new Headers(second.headers).get('Authorization')).toBe(
      'Bearer memory-only-test-token',
    );
    expect(second.credentials).toBe('omit');
    await expect(api('https://outside.test')).rejects.toThrow('Rota inválida');
  });
  it('revokes local access on server 401 and on expiration', async () => {
    const fetch = authenticatedResponses(1000);
    vi.stubGlobal('fetch', fetch);
    await signIn('viewer', 'test-only-password');
    await vi.advanceTimersByTimeAsync(1001);
    expect(currentUser.value).toBeNull();
    vi.stubGlobal('fetch', authenticatedResponses());
    await signIn('viewer', 'test-only-password');
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ title: 'Sessão expirada.' }, { status: 401 }),
        ),
    );
    await expect(api('/auth/me')).rejects.toBeInstanceOf(ApiError);
    expect(currentUser.value).toBeNull();
  });
  it('clears local access even when logout cannot reach the server', async () => {
    vi.stubGlobal('fetch', authenticatedResponses());
    await signIn('viewer', 'test-only-password');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    await expect(signOut()).rejects.toBeInstanceOf(ApiError);
    expect(currentUser.value).toBeNull();
  });
});

it('guards administration and refuses external return locations', () => {
  expect(mayVisit(undefined, null)).toBe(false);
  expect(mayVisit(undefined, user)).toBe(true);
  expect(mayVisit(['administrador'], user)).toBe(false);
  expect(safeDestination('https://outside.test')).toBe('/');
  expect(safeDestination('//outside.test')).toBe('/');
  expect(safeDestination('/\\outside.test')).toBe('/');
  expect(safeDestination('/auditoria')).toBe('/auditoria');
});
