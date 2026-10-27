/** Generated from the canonical Python wire schema. Do not edit by hand. */

export type EventV1 =
  | TelemetryEvent
  | StateEvent
  | AvailabilityEvent
  | CommandEvent
  | AckEvent
  | RejectedAckEvent
  | ExpiredAckEvent
  | InsightEvent
  | AlertEvent
  | GenerateEvent
  | TrainEvent
  | ProgressEvent
  | ModelEvent;
export type SchemaVersion = '1.0';
export type Id = string;
export type Timestamp = string;
export type Type = 'telemetry.sampled' | 'telemetry.persisted';
export type Stream = 'live';
export type DeviceId = string;
export type Zone = string;
export type EquipmentType = 'ac_split_onoff';
export type Producer =
  | 'simulator'
  | 'gateway'
  | 'writer'
  | 'api'
  | 'control'
  | 'inference'
  | 'jobs-worker';
export type CorrelationId = string | null;
export type CausationId = string | null;
export type BootId = string;
export type Sequence = number;
export type TelemetryData = TelemetryData1;
export type CurrentA = number | null;
export type CompressorCaseTempC = number | null;
export type VibrationRmsMmS = number | null;
export type IndoorTempC = number | null;
export type OutdoorTempC = number | null;
export type PowerW = number | null;
export type CompressorOn = boolean;
export type CondenserFanOn = boolean;
/**
 * @maxItems 5
 */
export type MissingFields =
  | []
  | [
      | 'current_a'
      | 'compressor_case_temp_c'
      | 'vibration_rms_mm_s'
      | 'indoor_temp_c'
      | 'outdoor_temp_c',
    ]
  | [
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
    ]
  | [
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
    ]
  | [
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
    ]
  | [
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
      (
        | 'current_a'
        | 'compressor_case_temp_c'
        | 'vibration_rms_mm_s'
        | 'indoor_temp_c'
        | 'outdoor_temp_c'
      ),
    ];
export type SchemaVersion1 = '1.0';
export type Id1 = string;
export type Timestamp1 = string;
export type Type1 = 'device.state';
export type Stream1 = 'live';
export type DeviceId1 = string;
export type Zone1 = string;
export type EquipmentType1 = 'ac_split_onoff';
export type Mode = 'manual' | 'auto';
export type SchemaVersion2 = '1.0';
export type Id2 = string;
export type Timestamp2 = string;
export type Type2 = 'device.availability';
export type Stream2 = 'live';
export type DeviceId2 = string;
export type Zone2 = string;
export type EquipmentType2 = 'ac_split_onoff';
export type Status = 'online' | 'offline';
export type SchemaVersion3 = '1.0';
export type Id3 = string;
export type Timestamp3 = string;
export type Type3 = 'command.requested';
export type Stream3 = 'live';
export type DeviceId3 = string;
export type Zone3 = string;
export type EquipmentType3 = 'ac_split_onoff';
export type Producer1 =
  | 'simulator'
  | 'gateway'
  | 'writer'
  | 'api'
  | 'control'
  | 'inference'
  | 'jobs-worker';
export type CorrelationId1 = string | null;
export type CausationId1 = string | null;
export type TargetBootId = string;
export type Revision = number;
export type Mode1 = 'manual' | 'auto';
export type ExpiresAt = string;
export type SchemaVersion4 = '1.0';
export type Id4 = string;
export type Timestamp4 = string;
export type Type4 = 'command.applied';
export type Stream4 = 'live';
export type DeviceId4 = string;
export type Zone4 = string;
export type EquipmentType4 = 'ac_split_onoff';
export type CommandId = string;
export type Revision1 = number;
export type Status1 = 'applied';
export type Reason = 'ok';
export type SchemaVersion5 = '1.0';
export type Id5 = string;
export type Timestamp5 = string;
export type Type5 = 'command.rejected';
export type Stream5 = 'live';
export type DeviceId5 = string;
export type Zone5 = string;
export type EquipmentType5 = 'ac_split_onoff';
export type CommandId1 = string;
export type Revision2 = number;
export type Status2 = 'rejected';
export type Reason1 =
  'interlock' | 'short_cycle' | 'obsolete_revision' | 'wrong_boot';
export type SchemaVersion6 = '1.0';
export type Id6 = string;
export type Timestamp6 = string;
export type Type6 = 'command.expired';
export type Stream6 = 'live';
export type DeviceId6 = string;
export type Zone6 = string;
export type EquipmentType6 = 'ac_split_onoff';
export type CommandId2 = string;
export type Revision3 = number;
export type Status3 = 'expired';
export type Reason2 = 'expired';
export type SchemaVersion7 = '1.0';
export type Id7 = string;
export type Timestamp7 = string;
export type Type7 = 'insight.predicted';
export type Stream7 = 'live';
export type DeviceId7 = string;
export type Zone7 = string;
export type EquipmentType7 = 'ac_split_onoff';
export type Data = InsightData | UnavailableInsightData;
export type SourceEventId = string;
export type ModelVersion = string;
export type FeatureVersion = 'hvac-window-v1';
export type Status4 = 'valid';
export type RulOperatingHours = number;
export type HealthScore = number | null;
export type SourceEventId1 = string;
export type ModelVersion1 = string;
export type FeatureVersion1 = 'hvac-window-v1';
export type Status5 =
  'warming_up' | 'insufficient_data' | 'out_of_domain' | 'inactive';
export type RulOperatingHours1 = null;
export type HealthScore1 = number | null;
export type SchemaVersion8 = '1.0';
export type Id8 = string;
export type Timestamp8 = string;
export type Type8 = 'alert.raised' | 'alert.cleared' | 'alert.acknowledged';
export type Stream8 = 'live';
export type DeviceId8 = string;
export type Zone8 = string;
export type EquipmentType8 = 'ac_split_onoff';
export type AlertId = string;
export type RuleId = string;
export type Severity = 'info' | 'warning' | 'critical';
export type ReasonCode = string;
export type SchemaVersion9 = '1.0';
export type Id9 = string;
export type Timestamp9 = string;
export type Type9 = 'dataset.generate.requested';
export type Stream9 = 'system';
export type DeviceId9 = null;
export type Zone9 = null;
export type EquipmentType9 = null;
export type JobId = string;
export type DatasetId = string;
export type Seed = number;
export type Records = number;
export type EquipmentCount = number;
export type ChunkSize = number;
/**
 * @minItems 1
 * @maxItems 3
 */
export type Scenarios =
  | ['healthy' | 'mechanical_wear' | 'heat_transfer_loss']
  | [
      'healthy' | 'mechanical_wear' | 'heat_transfer_loss',
      'healthy' | 'mechanical_wear' | 'heat_transfer_loss',
    ]
  | [
      'healthy' | 'mechanical_wear' | 'heat_transfer_loss',
      'healthy' | 'mechanical_wear' | 'heat_transfer_loss',
      'healthy' | 'mechanical_wear' | 'heat_transfer_loss',
    ];
export type NoiseStd = number;
export type MissingFraction = number;
export type OutlierFraction = number;
export type SchemaVersion10 = '1.0';
export type Id10 = string;
export type Timestamp10 = string;
export type Type10 = 'model.train.requested';
export type Stream10 = 'system';
export type DeviceId10 = null;
export type Zone10 = null;
export type EquipmentType10 = null;
export type JobId1 = string;
export type DatasetId1 = string;
export type Seed1 = number;
export type FeatureVersion2 = 'hvac-window-v1';
/**
 * @minItems 1
 * @maxItems 2
 */
export type Algorithms =
  | ['ridge' | 'hist_gradient_boosting']
  | ['ridge' | 'hist_gradient_boosting', 'ridge' | 'hist_gradient_boosting'];
export type SchemaVersion11 = '1.0';
export type Id11 = string;
export type Timestamp11 = string;
export type Type11 = 'job.progress';
export type Stream11 = 'system';
export type DeviceId11 = null;
export type Zone11 = null;
export type EquipmentType11 = null;
export type JobId2 = string;
export type Kind = 'dataset.generate' | 'model.train';
export type Status6 =
  'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type Processed = number;
export type Total = number;
export type SchemaVersion12 = '1.0';
export type Id12 = string;
export type Timestamp12 = string;
export type Type12 = 'model.activation.requested' | 'model.activated';
export type Stream12 = 'system';
export type DeviceId12 = null;
export type Zone12 = null;
export type EquipmentType12 = null;
export type ModelVersion2 = string;
export type FeatureVersion3 = 'hvac-window-v1';
export type Sha256 = string;

export interface TelemetryEvent {
  schema_version: SchemaVersion;
  id: Id;
  timestamp: Timestamp;
  type: Type;
  stream: Stream;
  device_id: DeviceId;
  zone: Zone;
  equipment_type: EquipmentType;
  metadata: DeviceMetadata;
  data: TelemetryData;
}
export interface DeviceMetadata {
  producer: Producer;
  correlation_id?: CorrelationId;
  causation_id?: CausationId;
  boot_id: BootId;
  sequence: Sequence;
}
export interface TelemetryData1 {
  readings: Readings;
  actuators: Actuators;
  quality: Quality;
}
export interface Readings {
  current_a: CurrentA;
  compressor_case_temp_c: CompressorCaseTempC;
  vibration_rms_mm_s: VibrationRmsMmS;
  indoor_temp_c: IndoorTempC;
  outdoor_temp_c: OutdoorTempC;
  power_w: PowerW;
}
export interface Actuators {
  compressor_on: CompressorOn;
  condenser_fan_on: CondenserFanOn;
}
export interface Quality {
  missing_fields: MissingFields;
}
export interface StateEvent {
  schema_version: SchemaVersion1;
  id: Id1;
  timestamp: Timestamp1;
  type: Type1;
  stream: Stream1;
  device_id: DeviceId1;
  zone: Zone1;
  equipment_type: EquipmentType1;
  metadata: DeviceMetadata;
  data: StateData;
}
export interface StateData {
  actuators: Actuators;
  mode: Mode;
}
export interface AvailabilityEvent {
  schema_version: SchemaVersion2;
  id: Id2;
  timestamp: Timestamp2;
  type: Type2;
  stream: Stream2;
  device_id: DeviceId2;
  zone: Zone2;
  equipment_type: EquipmentType2;
  metadata: DeviceMetadata;
  data: AvailabilityData;
}
export interface AvailabilityData {
  status: Status;
}
export interface CommandEvent {
  schema_version: SchemaVersion3;
  id: Id3;
  timestamp: Timestamp3;
  type: Type3;
  stream: Stream3;
  device_id: DeviceId3;
  zone: Zone3;
  equipment_type: EquipmentType3;
  metadata: Metadata;
  data: CommandData;
}
export interface Metadata {
  producer: Producer1;
  correlation_id?: CorrelationId1;
  causation_id?: CausationId1;
}
export interface CommandData {
  target_boot_id: TargetBootId;
  revision: Revision;
  desired: Actuators;
  mode: Mode1;
  expires_at: ExpiresAt;
}
export interface AckEvent {
  schema_version: SchemaVersion4;
  id: Id4;
  timestamp: Timestamp4;
  type: Type4;
  stream: Stream4;
  device_id: DeviceId4;
  zone: Zone4;
  equipment_type: EquipmentType4;
  metadata: Metadata;
  data: AckData;
}
export interface AckData {
  command_id: CommandId;
  revision: Revision1;
  status: Status1;
  observed: Actuators;
  reason: Reason;
}
export interface RejectedAckEvent {
  schema_version: SchemaVersion5;
  id: Id5;
  timestamp: Timestamp5;
  type: Type5;
  stream: Stream5;
  device_id: DeviceId5;
  zone: Zone5;
  equipment_type: EquipmentType5;
  metadata: Metadata;
  data: RejectedAckData;
}
export interface RejectedAckData {
  command_id: CommandId1;
  revision: Revision2;
  status: Status2;
  observed: Actuators;
  reason: Reason1;
}
export interface ExpiredAckEvent {
  schema_version: SchemaVersion6;
  id: Id6;
  timestamp: Timestamp6;
  type: Type6;
  stream: Stream6;
  device_id: DeviceId6;
  zone: Zone6;
  equipment_type: EquipmentType6;
  metadata: Metadata;
  data: ExpiredAckData;
}
export interface ExpiredAckData {
  command_id: CommandId2;
  revision: Revision3;
  status: Status3;
  observed: Actuators;
  reason: Reason2;
}
export interface InsightEvent {
  schema_version: SchemaVersion7;
  id: Id7;
  timestamp: Timestamp7;
  type: Type7;
  stream: Stream7;
  device_id: DeviceId7;
  zone: Zone7;
  equipment_type: EquipmentType7;
  metadata: Metadata;
  data: Data;
}
export interface InsightData {
  source_event_id: SourceEventId;
  model_version: ModelVersion;
  feature_version: FeatureVersion;
  status: Status4;
  rul_operating_hours: RulOperatingHours;
  health_score: HealthScore;
}
export interface UnavailableInsightData {
  source_event_id: SourceEventId1;
  model_version: ModelVersion1;
  feature_version: FeatureVersion1;
  status: Status5;
  rul_operating_hours: RulOperatingHours1;
  health_score: HealthScore1;
}
export interface AlertEvent {
  schema_version: SchemaVersion8;
  id: Id8;
  timestamp: Timestamp8;
  type: Type8;
  stream: Stream8;
  device_id: DeviceId8;
  zone: Zone8;
  equipment_type: EquipmentType8;
  metadata: Metadata;
  data: AlertData;
}
export interface AlertData {
  alert_id: AlertId;
  rule_id: RuleId;
  severity: Severity;
  reason_code: ReasonCode;
}
export interface GenerateEvent {
  schema_version: SchemaVersion9;
  id: Id9;
  timestamp: Timestamp9;
  type: Type9;
  stream: Stream9;
  device_id: DeviceId9;
  zone: Zone9;
  equipment_type: EquipmentType9;
  metadata: Metadata;
  data: GenerateData;
}
export interface GenerateData {
  job_id: JobId;
  dataset_id: DatasetId;
  seed: Seed;
  records: Records;
  equipment_count: EquipmentCount;
  chunk_size: ChunkSize;
  scenarios: Scenarios;
  noise_std: NoiseStd;
  missing_fraction: MissingFraction;
  outlier_fraction: OutlierFraction;
}
export interface TrainEvent {
  schema_version: SchemaVersion10;
  id: Id10;
  timestamp: Timestamp10;
  type: Type10;
  stream: Stream10;
  device_id: DeviceId10;
  zone: Zone10;
  equipment_type: EquipmentType10;
  metadata: Metadata;
  data: TrainData;
}
export interface TrainData {
  job_id: JobId1;
  dataset_id: DatasetId1;
  seed: Seed1;
  feature_version: FeatureVersion2;
  algorithms: Algorithms;
}
export interface ProgressEvent {
  schema_version: SchemaVersion11;
  id: Id11;
  timestamp: Timestamp11;
  type: Type11;
  stream: Stream11;
  device_id: DeviceId11;
  zone: Zone11;
  equipment_type: EquipmentType11;
  metadata: Metadata;
  data: ProgressData;
}
export interface ProgressData {
  job_id: JobId2;
  kind: Kind;
  status: Status6;
  processed: Processed;
  total: Total;
}
export interface ModelEvent {
  schema_version: SchemaVersion12;
  id: Id12;
  timestamp: Timestamp12;
  type: Type12;
  stream: Stream12;
  device_id: DeviceId12;
  zone: Zone12;
  equipment_type: EquipmentType12;
  metadata: Metadata;
  data: ModelData;
}
export interface ModelData {
  model_version: ModelVersion2;
  feature_version: FeatureVersion3;
  sha256: Sha256;
}
