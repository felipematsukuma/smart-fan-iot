import axios from 'axios';
import type { Device, MetricsSummary } from '../types';

const requestedDevice = new URLSearchParams(window.location.search).get(
  'device',
);
export const DEVICE_ID =
  requestedDevice && /^[A-Za-z0-9_-]{1,64}$/.test(requestedDevice)
    ? requestedDevice
    : import.meta.env.VITE_DEVICE_ID || 'esp32_fan_01';
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  timeout: 10000,
});

export async function getDevice(deviceId = DEVICE_ID): Promise<Device> {
  return (await api.get<Device>(`/device/${encodeURIComponent(deviceId)}`))
    .data;
}

export async function getMetrics(
  start: Date,
  end: Date,
): Promise<MetricsSummary> {
  const { data } = await api.get<MetricsSummary>(
    `/device/${encodeURIComponent(DEVICE_ID)}/metrics`,
    {
      params: { start: start.toISOString(), end: end.toISOString() },
    },
  );
  if (!Array.isArray(data.history) || !Number.isFinite(data.estimated_kwh)) {
    throw new Error('Resposta de métricas inválida');
  }
  return data;
}

export async function listDevices(): Promise<Device[]> {
  return (await api.get<Device[]>('/devices')).data;
}
