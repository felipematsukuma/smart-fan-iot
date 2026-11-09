/** Generated from canonical Python WebSocket controls. Do not edit by hand. */

export type ClientPacket = Authenticate | Subscribe | Ping | Pong;
export type Type = 'authenticate';
export type Ticket = string;
export type Devices = string[] | null;
export type Type1 = 'subscribe';
/**
 * @maxItems 100
 */
export type Devices1 = string[];
export type Type2 = 'ping';
export type Id = string;
export type Type3 = 'pong';
export type Id1 = string;

export interface Authenticate {
  type: Type;
  ticket: Ticket;
  devices?: Devices;
}
export interface Subscribe {
  type: Type1;
  devices: Devices1;
}
export interface Ping {
  type: Type2;
  id: Id;
}
export interface Pong {
  type: Type3;
  id: Id1;
}
