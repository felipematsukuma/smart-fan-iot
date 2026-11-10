import type { FrameReadyV2 } from '../../lib/contracts-v2.generated';
import type { DeviceDescriptor } from '../../lib/ws-server.generated';
import { frameFresh } from '../live-store';

export type SensorField = keyof DeviceDescriptor['sensor_ids'];
export type Ranges = Record<SensorField, { minimum: number; maximum: number }>;
export const sensorLabels: Record<SensorField, string> = {
  current_a: 'Corrente',
  compressor_case_temp_c: 'Temperatura da carcaça',
  vibration_rms_mm_s: 'Vibração',
  indoor_temp_c: 'Temperatura interna',
  outdoor_temp_c: 'Temperatura externa',
};
export const units: Record<SensorField, string> = {
  current_a: 'A',
  compressor_case_temp_c: '°C',
  vibration_rms_mm_s: 'mm/s',
  indoor_temp_c: '°C',
  outdoor_temp_c: '°C',
};
export interface SceneEntity {
  id: string;
  label: string;
  kind: 'sensor' | 'actuator' | 'equipment';
  field?: SensorField | keyof DeviceDescriptor['actuator_ids'];
}
export function entities(device: DeviceDescriptor): SceneEntity[] {
  return [
    { id: device.id, label: 'Compressor monitorado', kind: 'equipment' },
    ...Object.entries(device.sensor_ids).map(([field, id]) => ({
      id,
      label: sensorLabels[field as SensorField],
      kind: 'sensor' as const,
      field: field as SensorField,
    })),
    ...Object.entries(device.actuator_ids).map(([field, id]) => ({
      id,
      label:
        field === 'compressor_on'
          ? 'Acionamento do compressor'
          : 'Ventilador da condensadora',
      kind: 'actuator' as const,
      field: field as keyof DeviceDescriptor['actuator_ids'],
    })),
  ];
}
export function sensorColor(
  value: number | null,
  range?: { minimum: number; maximum: number },
) {
  if (value == null || !range) return '#8b9aab';
  return value < range.minimum || value > range.maximum ? '#d38a29' : '#238574';
}
export function state(
  frame: FrameReadyV2 | undefined,
  device: DeviceDescriptor,
  now: number,
  ranges?: Ranges,
) {
  if (
    !frame ||
    !device.enabled ||
    frame.metadata.boot_id !== device.boot_id ||
    !frameFresh(frame, now)
  )
    return null;
  const data = frame.conteudo.telemetry;
  return {
    compressor: data.actuators.compressor_on,
    fan: data.actuators.condenser_fan_on,
    vibration: data.readings.vibration_rms_mm_s,
    indoor: data.readings.indoor_temp_c,
    outdoor: data.readings.outdoor_temp_c,
    equipmentColor:
      frame.conteudo.insight.status === 'valid'
        ? frame.conteudo.insight.health_score! < 40
          ? '#d45c52'
          : '#238574'
        : '#8b9aab',
    sensorColors: Object.fromEntries<string>(
      Object.entries(device.sensor_ids).map(([field, id]) => [
        id,
        sensorColor(
          data.readings[field as SensorField],
          ranges?.[field as SensorField],
        ),
      ]),
    ),
  };
}
