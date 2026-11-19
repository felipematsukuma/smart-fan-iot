import { describe, it, expect } from 'vitest';
import { shortId, featureLabel, jobDate } from './job-presentation';
describe('rótulos de apresentação', () => {
  it('abrevia sem modificar identidade original', () => {
    const id = '12345678-1234-1234-1234-123456789abc';
    expect(shortId(id)).toBe('12345678…9abc');
    expect(shortId('short')).toBe('short');
    expect(id.length).toBe(36);
  });
  it('traduz atributos conhecidos e preserva os desconhecidos', () => {
    expect(featureLabel('current_a_mean')).toBe('Corrente · média');
    expect(featureLabel('vibration_rms_mm_s_slope_per_s')).toBe(
      'Vibração · tendência',
    );
    expect(featureLabel('coverage')).toBe('Cobertura das leituras');
    expect(featureLabel('future_field')).toBe('future_field');
  });
  it('não inventa data', () =>
    expect(jobDate('invalid')).toBe('Data indisponível'));
});
