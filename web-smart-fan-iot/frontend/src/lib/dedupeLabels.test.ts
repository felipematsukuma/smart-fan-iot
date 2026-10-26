import { describe, expect, it } from 'vitest';
import { dedupeLabels } from './chartRules';

describe('dedupeLabels', () => {
  it('remove repetições consecutivas', () => {
    expect(dedupeLabels(['a', 'a', 'b', 'b', 'b', 'c'])).toEqual(['a', 'b', 'c']);
  });

  it('preserva a ordem e a primeira ocorrência', () => {
    expect(dedupeLabels(['x', 'y', 'x'])).toEqual(['x', 'y', 'x']);
  });

  it('não descarta rótulos distintos', () => {
    const labels = ['28/09 15:41', '28/09 15:42', '28/09 16:41'];
    expect(dedupeLabels(labels)).toEqual(labels);
  });

  it('listas vazias e de um item', () => {
    expect(dedupeLabels([])).toEqual([]);
    expect(dedupeLabels(['só um'])).toEqual(['só um']);
  });
});
