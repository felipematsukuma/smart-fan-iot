import type { EventV1 } from './contracts-v1.generated';
import type { EventV2 } from './contracts-v2.generated';
import type { ServerControl } from './ws-server.generated';
import type { ClientPacket } from './ws-client.generated';
export function eventV1(value: unknown): value is EventV1;
export function eventV2(value: unknown): value is EventV2;
export function serverControl(value: unknown): value is ServerControl;
export function clientPacket(value: unknown): value is ClientPacket;
