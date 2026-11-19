export const shortId = (id: string) =>
  id.length > 16 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
export function jobDate(value: string) {
  const time = Date.parse(value);
  return Number.isFinite(time)
    ? new Date(time).toLocaleString('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'short',
      })
    : 'Data indisponível';
}
export function featureLabel(feature: string): string {
  const extra: Record<string, string> = {
    case_minus_outdoor_mean: 'Diferença carcaça–exterior',
    indoor_cooling_rate_c_per_min: 'Ritmo de resfriamento',
    coverage: 'Cobertura das leituras',
  };
  if (extra[feature]) return extra[feature];
  const sensors: Record<string, string> = {
    current_a: 'Corrente',
    compressor_case_temp_c: 'Temp. da carcaça',
    vibration_rms_mm_s: 'Vibração',
    indoor_temp_c: 'Temp. interna',
    outdoor_temp_c: 'Temp. externa',
  };
  const stats: Record<string, string> = {
    mean: 'média',
    std: 'desvio padrão',
    slope_per_s: 'tendência',
  };
  for (const [sensor, label] of Object.entries(sensors)) {
    const suffix = feature.slice(sensor.length + 1);
    if (feature.startsWith(sensor + '_') && stats[suffix])
      return `${label} · ${stats[suffix]}`;
  }
  return feature;
}
