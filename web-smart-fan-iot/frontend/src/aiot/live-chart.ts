import type { FrameReadyV2 } from '../lib/contracts-v2.generated';

export const readings = [
  {
    key: 'power_w',
    name: 'Potência',
    unit: 'W',
    group: 'power',
    color: '#0f766e',
    dash: [],
  },
  {
    key: 'indoor_temp_c',
    name: 'Temperatura interna',
    unit: '°C',
    group: 'temperature',
    color: '#0f766e',
    dash: [],
  },
  {
    key: 'outdoor_temp_c',
    name: 'Temperatura externa',
    unit: '°C',
    group: 'temperature',
    color: '#1d4ed8',
    dash: [8, 4],
  },
  {
    key: 'compressor_case_temp_c',
    name: 'Temperatura da carcaça',
    unit: '°C',
    group: 'temperature',
    color: '#9d174d',
    dash: [2, 4],
  },
  {
    key: 'current_a',
    name: 'Corrente',
    unit: 'A',
    group: 'current',
    color: '#6d28d9',
    dash: [],
  },
  {
    key: 'vibration_rms_mm_s',
    name: 'Vibração',
    unit: 'mm/s',
    group: 'vibration',
    color: '#92400e',
    dash: [],
  },
] as const;
export type ReadingKey = (typeof readings)[number]['key'];
// Physical combinations reviewed explicitly: temperatures of the same equipment,
// with distinct measurement locations; other quantities are always isolated.
export const allowedCombinations: readonly (readonly ReadingKey[])[] = [
  ['power_w'],
  ['current_a'],
  ['vibration_rms_mm_s'],
  ['indoor_temp_c'],
  ['outdoor_temp_c'],
  ['compressor_case_temp_c'],
  ['indoor_temp_c', 'outdoor_temp_c'],
  ['indoor_temp_c', 'compressor_case_temp_c'],
  ['outdoor_temp_c', 'compressor_case_temp_c'],
  ['indoor_temp_c', 'outdoor_temp_c', 'compressor_case_temp_c'],
];
export function selectReading(
  selected: ReadingKey[],
  key: ReadingKey,
): ReadingKey[] {
  const current = readings.find((item) => item.key === selected[0]);
  const next = readings.find((item) => item.key === key)!;
  const proposed =
    current?.group !== next.group
      ? [key]
      : selected.includes(key)
        ? selected.filter((item) => item !== key)
        : [...selected, key];
  return allowedCombinations.some(
    (combo) =>
      combo.length === proposed.length &&
      combo.every((item) => proposed.includes(item)),
  )
    ? readings
        .filter((item) => proposed.includes(item.key))
        .map((item) => item.key)
    : selected;
}
export function chartTitle(selected: ReadingKey[]) {
  return selected.length > 1
    ? 'Temperaturas em tempo real'
    : `${readings.find((item) => item.key === selected[0])!.name} em tempo real`;
}
export function chartSamples(frames: FrameReadyV2[], selected: ReadingKey[]) {
  const samples: (FrameReadyV2 | null)[] = [];
  const timestamps: string[] = [];
  frames.forEach((frame, index) => {
    const previous = frames[index - 1];
    if (
      previous &&
      (Date.parse(frame.timestamp) - Date.parse(previous.timestamp) > 6000 ||
        previous.metadata.boot_id !== frame.metadata.boot_id)
    ) {
      samples.push(null);
      timestamps.push(frame.timestamp);
    }
    samples.push(frame);
    timestamps.push(frame.timestamp);
  });
  return {
    labels: timestamps.map((at) => new Date(at).toLocaleTimeString('pt-BR')),
    datasets: readings
      .filter((item) => selected.includes(item.key))
      .map((item) => ({
        label: `${item.name} (${item.unit})`,
        data: samples.map(
          (frame) => frame?.conteudo.telemetry.readings[item.key] ?? null,
        ),
        borderColor: item.color,
        borderDash: [...item.dash],
        borderWidth: 2,
        pointRadius: frames.length === 1 ? 3 : 0,
        pointHitRadius: 16,
        spanGaps: false,
        fill: false,
        tension: 0,
      })),
  };
}
