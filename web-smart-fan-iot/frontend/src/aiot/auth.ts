import { shallowRef } from 'vue';

export type Role = 'visualizador' | 'operador' | 'administrador';
export interface User {
  id: string;
  username: string;
  role: Role;
  expires_at: string;
}
export const currentUser = shallowRef<User | null>(null);
export const sessionNotice = shallowRef('');
let accessToken: string | null = null;
let expiry: ReturnType<typeof setTimeout> | undefined;
const ended = new Set<() => void>();

export class ApiError extends Error {
  status: number;
  correlationId: string | undefined;
  constructor(status: number, message: string, correlationId?: string) {
    super(message);
    this.status = status;
    this.correlationId = correlationId;
  }
}

export function clearSession(notice = '') {
  accessToken = null;
  currentUser.value = null;
  sessionNotice.value = notice;
  if (expiry !== undefined) clearTimeout(expiry);
  expiry = undefined;
  for (const callback of ended) callback();
}

export function onSessionEnded(callback: () => void) {
  ended.add(callback);
  return () => ended.delete(callback);
}

export async function apiResponse(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  if (!path.startsWith('/') || path.startsWith('//'))
    throw new Error('Rota inválida.');
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      headers,
      credentials: 'omit',
      cache: 'no-store',
    });
  } catch {
    throw new ApiError(
      0,
      'Não foi possível conectar. Verifique a conexão e tente novamente.',
    );
  }
  if (!response.ok) {
    let message = 'Não foi possível concluir a operação.';
    const body: unknown = await response.json().catch(() => null);
    if (
      body &&
      typeof body === 'object' &&
      'title' in body &&
      typeof body.title === 'string'
    ) {
      message = body.title;
    }
    if (response.status === 401 && accessToken)
      clearSession('Sua sessão expirou. Entre novamente.');
    throw new ApiError(
      response.status,
      message,
      response.headers.get('X-Correlation-ID') ?? undefined,
    );
  }
  return response;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await apiResponse(path, options);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function signIn(username: string, password: string) {
  clearSession();
  try {
    const result = await api<{ access_token: string; expires_at: string }>(
      '/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      },
    );
    accessToken = result.access_token;
    const user = await api<User>('/auth/me');
    currentUser.value = user;
    expiry = setTimeout(
      () => clearSession('Sua sessão expirou. Entre novamente.'),
      Math.max(0, Date.parse(result.expires_at) - Date.now()),
    );
  } catch (error) {
    clearSession();
    throw error;
  }
}

export async function signOut() {
  try {
    if (accessToken) await api<void>('/auth/logout', { method: 'POST' });
  } finally {
    clearSession();
  }
}
