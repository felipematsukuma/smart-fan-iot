import { it } from 'vitest';
import { buildTimeline } from './chartRules';
const MIN = 60000, ON = 29.77, T0 = Date.parse('2026-09-28T18:00:00Z');
it('dbg', () => {
  const pares: Array<[number, number]> = [];
  for (let m = 0; m < 60; m += 4) pares.push([m, ON]);
  const times = pares.map(([m]) => T0 + m * MIN);
  const values = pares.map(() => ON);
  const t = buildTimeline(times, values, { windowStartMs: T0, windowEndMs: T0 + 60 * MIN });
  console.log('n amostras', times.length, 'deltas', times.slice(1).map((x,i)=> (x-times[i])/MIN).join(','));
  console.log('gaps', JSON.stringify(t.gaps.map(g => ({r: g.reason, de: (g.from-T0)/MIN, ate: (g.to-T0)/MIN}))));
  console.log('segments', t.segments.map(s => `${s.kind}[${(s.from-T0)/MIN}..${(s.to-T0)/MIN}]`).join(' '));
  console.log('points', t.points.length, 'axisMs', t.axisMs/MIN);
});
