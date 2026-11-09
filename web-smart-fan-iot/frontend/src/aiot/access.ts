import type { Role, User } from './auth';

export function mayVisit(
  roles: readonly Role[] | undefined,
  user: User | null,
) {
  return user !== null && (!roles || roles.includes(user.role));
}

export function safeDestination(value: unknown) {
  return typeof value === 'string' &&
    value.startsWith('/') &&
    !value.startsWith('//') &&
    !value.includes('\\')
    ? value
    : '/';
}
