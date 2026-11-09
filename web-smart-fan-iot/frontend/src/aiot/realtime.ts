import { ref, shallowReactive } from 'vue';
import type { EventV2 } from '../lib/contracts-v2.generated';
import type { Snapshot } from '../lib/ws-server.generated';
import { isServerControl } from '../lib/ws-control';
import { isEventV2 } from '../lib/contracts-v2';
import { api, currentUser, onSessionEnded } from './auth';
import { LiveStore } from './live-store';

export const live = new LiveStore();
export const jobUpdates = shallowReactive(
  new Map<string, Extract<EventV2, { tipo: 'job.progress' }>>(),
);
export const streamStatus = ref<
  'offline' | 'connecting' | 'authenticating' | 'connected' | 'reconnecting'
>('offline');
export const streamNotice = ref('');
let socket: WebSocket | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
let watchdog: ReturnType<typeof setInterval> | undefined;
let generation = 0;
let attempts = 0;
let lastMessage = 0;

export function stopRealtime() {
  generation++;
  clearTimeout(timer);
  clearInterval(watchdog);
  if (socket?.readyState === WebSocket.CONNECTING) {
    const pending = socket;
    pending.onopen = () => pending.close();
  } else socket?.close();
  socket = null;
  streamStatus.value = 'offline';
  live.clear();
  jobUpdates.clear();
}
onSessionEnded(stopRealtime);

export function startRealtime() {
  stopRealtime();
  const epoch = generation;
  attempts = 0;
  streamNotice.value = '';
  const current = () => epoch === generation && currentUser.value !== null;
  async function connect() {
    if (!current()) return;
    streamStatus.value = attempts ? 'reconnecting' : 'connecting';
    try {
      const snapshot = await api<Snapshot>('/snapshot');
      if (!current()) return;
      if (!isServerControl(snapshot) || snapshot.type !== 'snapshot')
        throw new Error('Snapshot inválido.');
      live.replaceDevices(snapshot.devices);
      // REST establishes authorized identities; live values arrive only through WS.
      const ids = snapshot.devices
        .filter((device) => device.enabled)
        .map((device) => device.id);
      const result = await api<{ ticket: string }>('/auth/ws-ticket', {
        method: 'POST',
        body: JSON.stringify({ devices: ids }),
      });
      if (!current()) return;
      const url = new URL('/ws', location.href);
      url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const connection = new WebSocket(url);
      socket = connection;
      lastMessage = Date.now();
      connection.onopen = () => {
        if (!current()) {
          connection.close();
          return;
        }
        streamStatus.value = 'authenticating';
        connection.send(
          JSON.stringify({
            type: 'authenticate',
            ticket: result.ticket,
            devices: ids,
          }),
        );
      };
      connection.onmessage = (message) => {
        if (!current() || typeof message.data !== 'string') return;
        try {
          if (new TextEncoder().encode(message.data).byteLength > 1048576)
            throw new Error('Stream muito grande.');
          const packet: unknown = JSON.parse(message.data);
          if (isEventV2(packet)) {
            if (packet.tipo === 'job.progress') {
              const previous = jobUpdates.get(packet.conteudo.job_id);
              if (
                !previous ||
                Date.parse(previous.timestamp) < Date.parse(packet.timestamp)
              )
                jobUpdates.set(packet.conteudo.job_id, packet);
              if (jobUpdates.size > 100)
                jobUpdates.delete(jobUpdates.keys().next().value!);
            }
            live.apply(packet);
          } else if (isServerControl(packet)) {
            if (packet.type === 'authenticated') {
              streamStatus.value = 'connected';
              attempts = 0;
            } else if (packet.type === 'snapshot') {
              live.replaceDevices(packet.devices);
              packet.events.forEach((event) => live.apply(event));
            } else if (packet.type === 'ping')
              connection.send(JSON.stringify({ type: 'pong', id: packet.id }));
            else if (packet.type === 'notice')
              streamNotice.value =
                'Leituras antigas foram mantidas fora do painel ao vivo.';
          } else throw new Error('Stream inválido.');
          lastMessage = Date.now();
        } catch {
          streamNotice.value = 'Não foi possível validar os dados recebidos.';
          connection.close();
        }
      };
      connection.onerror = () => connection.close();
      connection.onclose = () => {
        if (current()) retry();
      };
      clearInterval(watchdog);
      watchdog = setInterval(() => {
        if (Date.now() - lastMessage > 45000) connection.close();
      }, 1000);
    } catch {
      if (current()) retry();
    }
  }
  function retry() {
    clearTimeout(timer);
    clearInterval(watchdog);
    streamStatus.value = 'reconnecting';
    const delay = Math.min(30000, 1000 * 2 ** Math.min(attempts++, 5));
    timer = setTimeout(
      () => void connect(),
      delay * (0.8 + Math.random() * 0.4),
    );
  }
  void connect();
}
