export interface Device {
  id: number;
  device_id: string;
  name: string;
  is_on: boolean;
  kwh_rate: number;
  auto_off_time: string;
  auto_off_enabled: boolean;
}

export interface TelemetryData {
  persisted?: boolean;
  device_id: string;
  is_on: boolean;
  voltage_rms: number;
  current_a: number;
  power_w: number;
  timestamp: number;
  event?: 'telemetry' | 'state' | 'config';
  auto_mode?: boolean;
  shutdown_time?: string;
}

export interface MetricPoint {
  time: string;
  power_w: number;
}

export interface SeriesSegment {
  kind: 'active' | 'off' | 'no-data';
  from: string;
  to: string;
}

export interface MetricsSummary {
  coverage?: number;
  covered_seconds?: number;
  max_power_w?: number;
  segments?: SeriesSegment[];
  device_id: string;
  period_start?: string;
  period_end?: string;
  duration_hours?: number;
  avg_power_w: number;
  energy_wh?: number;
  estimated_kwh: number;
  history_count: number;
  history: MetricPoint[];
}
