export interface Command {
  id: string;
  revision: number;
  producer: string;
  status: 'pending' | 'confirmed' | 'failed';
  result: string | null;
  reason_code: string;
  execution_unknown: boolean;
  created_at: string;
  ack_event_id?: string | null;
}
export interface Observation {
  fresh: boolean;
  observation: null | {
    sampled_at: string;
    mode: string;
    manual_cooling_block: boolean;
    telemetry: {
      actuators: { compressor_on: boolean; condenser_fan_on: boolean };
    };
  };
}
export interface Rule {
  revision: number;
  timezone: string;
  configuration: {
    enabled: boolean;
    setpoint_c: number;
    hysteresis_c: number;
    minimum_off_seconds: number;
    minimum_on_seconds: number;
    schedule_enabled: boolean;
    start_hour: number;
    end_hour: number;
    weekdays: number[];
  };
}
