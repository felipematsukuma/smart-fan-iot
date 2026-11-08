import type { TelemetryData } from '../types';

type RealtimeMessage = Partial<TelemetryData> & {
  device_id: string;
  event: 'telemetry' | 'state' | 'config';
};

export function isRealtimeMessage(value: unknown): value is RealtimeMessage {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const data = value as Record<string, unknown>;
  if (
    typeof data.device_id !== 'string' ||
    !['telemetry', 'state', 'config'].includes(String(data.event))
  )
    return false;
  if (data.is_on !== undefined && typeof data.is_on !== 'boolean') return false;
  if (data.auto_mode !== undefined && typeof data.auto_mode !== 'boolean')
    return false;
  if (data.event === 'telemetry') {
    if (typeof data.is_on !== 'boolean') return false;
    for (const field of ['voltage_rms', 'current_a', 'power_w', 'timestamp']) {
      if (
        typeof data[field] !== 'number' ||
        !Number.isFinite(data[field]) ||
        data[field] < 0
      )
        return false;
    }
  }
  return true;
}
