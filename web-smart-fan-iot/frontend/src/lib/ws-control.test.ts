import { describe, expect, it } from 'vitest';
import cases from './ws.fixtures.json';
import { isServerControl } from './ws-control';

describe('canonical server control cases', () => {
  for (const fixture of cases.filter((item) => item.kind === 'server')) {
    it(fixture.name, () =>
      expect(isServerControl(fixture.value)).toBe(fixture.valid),
    );
  }
});
