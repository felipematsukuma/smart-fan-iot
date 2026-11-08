import { onMounted, onUnmounted, ref } from 'vue';
import type { TelemetryData } from '../types';
import { isRealtimeMessage } from '../lib/realtime';

export function useWebSocket(url: string, deviceId = 'esp32_fan_01') {
  const telemetry = ref<TelemetryData>({
    device_id: deviceId,
    is_on: false,
    voltage_rms: 127,
    current_a: 0,
    power_w: 0,
    timestamp: 0,
  });

  const isConnected = ref(false);
  const lastMessageAt = ref<number | null>(null);
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let shouldReconnect = true;

  const connect = () => {
    if (!shouldReconnect) return;

    socket = new WebSocket(url);

    socket.onopen = () => {
      isConnected.value = true;
    };

    socket.onmessage = (event) => {
      try {
        const data: unknown = JSON.parse(event.data);
        if (!isRealtimeMessage(data) || data.device_id !== deviceId) return;
        telemetry.value = { ...telemetry.value, ...data };
        // Retained state/config is not evidence that the device is alive now.
        if (data.event === 'telemetry') lastMessageAt.value = Date.now();
      } catch (err) {
        console.error('Erro ao ler WS:', err);
      }
    };

    socket.onclose = () => {
      isConnected.value = false;
      if (shouldReconnect) {
        reconnectTimer = setTimeout(connect, 3000);
      }
    };

    socket.onerror = () => {
      socket?.close();
    };
  };

  onMounted(connect);
  onUnmounted(() => {
    shouldReconnect = false;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
  });

  return { telemetry, isConnected, lastMessageAt };
}
