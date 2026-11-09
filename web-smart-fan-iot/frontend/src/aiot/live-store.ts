import { shallowReactive } from 'vue';
import type { EventV2, FrameReadyV2 } from '../lib/contracts-v2.generated';
import type { DeviceDescriptor } from '../lib/ws-server.generated';

export const frameFresh = (event: FrameReadyV2, now: number) => {
  const sampled = Date.parse(event.timestamp);
  const observed = Date.parse(event.metadata.observed_at);
  return (
    sampled <= observed &&
    observed <= now &&
    now - sampled <= 6000 &&
    now - observed <= 6000
  );
};
const key = (value: string) =>
  value.slice(0, 19) +
  '.' +
  value.slice(19, -1).replace('.', '').padEnd(6, '0');

export class LiveStore {
  devices = shallowReactive(new Map<string, DeviceDescriptor>());
  frames = shallowReactive(new Map<string, FrameReadyV2>());
  sensors = shallowReactive(new Map<string, number | null>());
  actuators = shallowReactive(new Map<string, boolean>());
  availability = shallowReactive(
    new Map<string, { status: 'online' | 'offline'; timestamp: string }>(),
  );
  states = shallowReactive(
    new Map<string, Extract<EventV2, { tipo: 'device.state' }>>(),
  );
  history = new Map<string, FrameReadyV2[]>();
  private retired = new Map<string, Set<string>>();

  replaceDevices(devices: DeviceDescriptor[]) {
    const allowed = new Set(devices.map((device) => device.id));
    for (const device of this.devices.values()) {
      if (!allowed.has(device.id)) {
        this.frames.delete(device.id);
        this.history.delete(device.id);
        this.retired.delete(device.id);
        this.availability.delete(device.id);
        this.states.delete(device.id);
        Object.values(device.sensor_ids).forEach((id) =>
          this.sensors.delete(id),
        );
        Object.values(device.actuator_ids).forEach((id) =>
          this.actuators.delete(id),
        );
        this.devices.delete(device.id);
      }
    }
    devices.forEach((device) => this.devices.set(device.id, device));
  }
  apply(event: EventV2, now = Date.now()) {
    if (event.tipo === 'device.availability' || event.tipo === 'device.state') {
      const device = this.devices.get(event.dispositivo);
      const age = now - Date.parse(event.timestamp);
      if (
        !device ||
        age < 0 ||
        (age > 6000 && event.tipo !== 'device.availability')
      )
        return false;
      if (event.tipo === 'device.availability') {
        const previous = this.availability.get(device.id);
        if (previous && key(previous.timestamp) >= key(event.timestamp))
          return false;
        this.availability.set(device.id, {
          status: event.conteudo.status,
          timestamp: event.timestamp,
        });
      } else {
        const previous = this.states.get(device.id);
        if (previous && key(previous.timestamp) >= key(event.timestamp))
          return false;
        this.states.set(device.id, event);
        if (
          event.metadata.boot_id !== device.boot_id &&
          (!device.last_sample_at ||
            key(event.timestamp) >= key(device.last_sample_at))
        ) {
          this.devices.set(device.id, {
            ...device,
            boot_id: event.metadata.boot_id,
          });
        }
      }
      return true;
    }
    if (event.tipo !== 'frame.ready' || !frameFresh(event, now)) return false;
    const device = this.devices.get(event.dispositivo);
    if (!device || !device.enabled) return false;
    if (
      device.boot_id &&
      device.boot_id !== event.metadata.boot_id &&
      device.last_sample_at &&
      key(event.timestamp) < key(device.last_sample_at)
    )
      return false;
    const previous = this.frames.get(event.dispositivo);
    const retired = this.retired.get(event.dispositivo) ?? new Set<string>();
    if (retired.has(event.metadata.boot_id)) return false;
    if (previous) {
      if (
        key(event.timestamp) <= key(previous.timestamp) ||
        event.id === previous.id
      )
        return false;
      if (
        previous.metadata.boot_id === event.metadata.boot_id &&
        event.metadata.sequence <= previous.metadata.sequence
      )
        return false;
      if (previous.metadata.boot_id !== event.metadata.boot_id) {
        retired.add(previous.metadata.boot_id);
        if (retired.size > 32) retired.delete(retired.values().next().value!);
      }
    }
    this.retired.set(event.dispositivo, retired);
    this.frames.set(event.dispositivo, event);
    this.devices.set(device.id, {
      ...device,
      boot_id: event.metadata.boot_id,
      last_sample_at: event.timestamp,
    });
    for (const [channel, id] of Object.entries(device.sensor_ids)) {
      this.sensors.set(
        id,
        event.conteudo.telemetry.readings[
          channel as keyof typeof device.sensor_ids
        ],
      );
    }
    for (const [channel, id] of Object.entries(device.actuator_ids)) {
      this.actuators.set(
        id,
        event.conteudo.telemetry.actuators[
          channel as keyof typeof device.actuator_ids
        ],
      );
    }
    const history = this.history.get(event.dispositivo) ?? [];
    history.push(event);
    if (history.length > 120) history.shift();
    this.history.set(event.dispositivo, history);
    return true;
  }
  clear() {
    this.devices.clear();
    this.frames.clear();
    this.sensors.clear();
    this.actuators.clear();
    this.history.clear();
    this.retired.clear();
    this.availability.clear();
    this.states.clear();
  }
  fresh(deviceId: string, now = Date.now()) {
    const frame = this.frames.get(deviceId);
    return (
      frame !== undefined &&
      this.devices.get(deviceId)?.boot_id === frame.metadata.boot_id &&
      frameFresh(frame, now)
    );
  }
}
