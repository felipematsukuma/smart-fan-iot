/** Generated from the canonical Python v2 wire schema. Do not edit by hand. */

export type EventV2 =
  | TelemetrySampleV2
  | TelemetryPersistedV2
  | FrameReadyV2
  | InsightPredictedV2
  | CommandRequestedV2
  | CommandAckV2
  | DeviceStateV2
  | DeviceAvailabilityV2
  | TransportReceiptV2
  | AlertV2
  | JobRequestedV2
  | JobProgressV2
  | ModelAvailableV2
  | ModelActivatedV2
  | QuarantinedV2;
export type Id = string;
export type SchemaVersion = '2.0';
export type Timestamp = string;
export type CorrelationId = string | null;
export type Tipo = 'telemetry.sampled';
export type Dispositivo = string;
export type Producer = 'simulator';
export type CausationId = string | null;
export type BootId = string;
export type Sequence = number;
export type Zone = string;
export type EquipmentType = 'ac_split_onoff';
export type ClockScale = 1;
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
export type Id1 = string;
export type SchemaVersion1 = '2.0';
export type Timestamp1 = string;
export type CorrelationId1 = string | null;
export type Tipo1 = 'telemetry.persisted';
export type Dispositivo1 = string;
export type Producer1 = 'writer';
export type CausationId1 = string | null;
export type BootId1 = string;
export type Sequence1 = number;
export type Zone1 = string;
export type EquipmentType1 = 'ac_split_onoff';
export type ClockScale1 = 1;
export type ObservedAt = string;
export type PersistedData = PersistedData1;
export type SourceEventId = string;
export type Id2 = string;
export type SchemaVersion2 = '2.0';
export type Timestamp2 = string;
export type CorrelationId2 = string | null;
export type Tipo2 = 'frame.ready';
export type Dispositivo2 = string;
export type Producer2 = 'inference';
export type CausationId2 = string | null;
export type BootId2 = string;
export type Sequence2 = number;
export type Zone2 = string;
export type EquipmentType2 = 'ac_split_onoff';
export type ClockScale2 = 1;
export type ObservedAt1 = string;
export type SourceEventId1 = string;
export type Insight = ValidInsightV2 | UnavailableInsightV2;
export type Status = 'valid';
export type ModelVersion = string;
export type FeatureVersion = 'hvac-window-v1';
export type HealthScore = number;
export type RulCalendarHours = number;
export type Status1 =
  | 'warming_up'
  | 'insufficient_data'
  | 'inactive'
  | 'stale'
  | 'model_unavailable'
  | 'out_of_domain';
export type ModelVersion1 = string | null;
export type FeatureVersion1 = 'hvac-window-v1';
export type HealthScore1 = null;
export type RulCalendarHours1 = null;
export type Id3 = string;
export type SchemaVersion3 = '2.0';
export type Timestamp3 = string;
export type CorrelationId3 = string | null;
export type Tipo3 = 'insight.predicted';
export type Dispositivo3 = string;
export type Conteudo = ValidSourceInsight | UnavailableSourceInsight;
export type Status2 = 'valid';
export type ModelVersion2 = string;
export type FeatureVersion2 = 'hvac-window-v1';
export type HealthScore2 = number;
export type RulCalendarHours2 = number;
export type SourceEventId2 = string;
export type Status3 =
  | 'warming_up'
  | 'insufficient_data'
  | 'inactive'
  | 'stale'
  | 'model_unavailable'
  | 'out_of_domain';
export type ModelVersion3 = string | null;
export type FeatureVersion3 = 'hvac-window-v1';
export type HealthScore3 = null;
export type RulCalendarHours3 = null;
export type SourceEventId3 = string;
export type Id4 = string;
export type SchemaVersion4 = '2.0';
export type Timestamp4 = string;
export type CorrelationId4 = string | null;
export type Tipo4 = 'command.requested';
export type Dispositivo4 = string;
export type Producer3 = 'api' | 'control';
export type CausationId3 = string | null;
export type Zone3 = string;
export type EquipmentType3 = 'ac_split_onoff';
export type CommandId = string;
export type TargetBootId = string;
export type Revision = number;
export type CompressorOn1 = boolean;
export type CondenserFanOn1 = boolean;
export type Mode = 'manual' | 'auto';
export type ExpiresAt = string;
export type ReasonCode = string;
export type Id5 = string;
export type SchemaVersion5 = '2.0';
export type Timestamp5 = string;
export type CorrelationId5 = string | null;
export type Tipo5 = 'command.applied' | 'command.rejected' | 'command.expired';
export type Dispositivo5 = string;
export type CommandId1 = string;
export type Revision1 = number;
export type ReasonCode1 = string;
export type Id6 = string;
export type SchemaVersion6 = '2.0';
export type Timestamp6 = string;
export type CorrelationId6 = string | null;
export type Tipo6 = 'device.state';
export type Dispositivo6 = string;
export type Mode1 = 'manual' | 'auto';
export type ManualCoolingBlock = boolean;
export type ReasonCode2 = string;
export type Id7 = string;
export type SchemaVersion7 = '2.0';
export type Timestamp7 = string;
export type CorrelationId7 = string | null;
export type Tipo7 = 'device.availability';
export type Dispositivo7 = string;
export type Metadata = SimulatorMetadata | GatewayMetadata;
export type Producer4 = 'gateway';
export type CausationId4 = string | null;
export type BootId3 = string;
export type Sequence3 = number;
export type Zone4 = string;
export type EquipmentType4 = 'ac_split_onoff';
export type ClockScale3 = 1;
export type ObservedAt2 = string;
export type Status4 = 'online' | 'offline';
export type ReasonCode3 = string;
export type Id8 = string;
export type SchemaVersion8 = '2.0';
export type Timestamp8 = string;
export type CorrelationId8 = string | null;
export type Tipo8 = 'transport.received';
export type Dispositivo8 = string;
export type SourceEventId4 = string;
export type Status5 = 'durably_received';
export type Id9 = string;
export type SchemaVersion9 = '2.0';
export type Timestamp9 = string;
export type CorrelationId9 = string | null;
export type Tipo9 = 'alert.raised' | 'alert.cleared';
export type Dispositivo9 = string;
export type Producer5 = 'control';
export type CausationId5 = string | null;
export type BootId4 = string;
export type Sequence4 = number;
export type Zone5 = string;
export type EquipmentType5 = 'ac_split_onoff';
export type ClockScale4 = 1;
export type ObservedAt3 = string;
export type AlertId = string;
export type RuleId = string;
export type Severity = 'info' | 'warning' | 'critical';
export type SourceEventId5 = string;
export type ReasonCode4 = string;
export type Id10 = string;
export type SchemaVersion10 = '2.0';
export type Timestamp10 = string;
export type CorrelationId10 = string | null;
export type Tipo10 = 'job.generate' | 'job.train';
export type Dispositivo10 = null;
export type Producer6 = 'api';
export type CausationId6 = string | null;
export type JobId = string;
export type DatasetId = string;
export type ConfigVersion = number;
export type Id11 = string;
export type SchemaVersion11 = '2.0';
export type Timestamp11 = string;
export type CorrelationId11 = string | null;
export type Tipo11 = 'job.progress';
export type Dispositivo11 = null;
export type Producer7 = 'jobs-worker';
export type CausationId7 = string | null;
export type JobId1 = string;
export type Kind = 'generate' | 'train';
export type Status6 =
  'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type Processed = number;
export type Total = number;
export type ReasonCode5 = string | null;
export type Id12 = string;
export type SchemaVersion12 = '2.0';
export type Timestamp12 = string;
export type CorrelationId12 = string | null;
export type Tipo12 = 'model.available';
export type Dispositivo12 = null;
export type ModelVersion4 = string;
export type FeatureVersion4 = 'hvac-window-v1';
export type DatasetId1 = string;
export type Sha256 = string;
export type Id13 = string;
export type SchemaVersion13 = '2.0';
export type Timestamp13 = string;
export type CorrelationId13 = string | null;
export type Tipo13 = 'model.activated';
export type Dispositivo13 = null;
export type Producer8 = 'inference';
export type CausationId8 = string | null;
export type Id14 = string;
export type SchemaVersion14 = '2.0';
export type Timestamp14 = string;
export type CorrelationId14 = string | null;
export type Tipo14 = 'message.quarantined';
export type Dispositivo14 = string | null;
export type Producer9 =
  | 'simulator'
  | 'gateway'
  | 'writer'
  | 'control'
  | 'inference'
  | 'api'
  | 'jobs-worker';
export type CausationId9 = string | null;
export type Conteudo1 = InlineQuarantine | ReferencedQuarantine;
export type FailureId = string;
export type Owner = string;
export type ReasonCode6 = string;
export type OriginalSha256 = string;
export type OriginalRoute = string;
export type Attempts = number;
export type OriginalBytesB64 = string;
export type OriginalRef = null;
export type FailureId1 = string;
export type Owner1 = string;
export type ReasonCode7 = string;
export type OriginalSha2561 = string;
export type OriginalRoute1 = string;
export type Attempts1 = number;
export type OriginalBytesB641 = null;
export type OriginalRef1 = string;

export interface TelemetrySampleV2 {
  id: Id;
  schema_version: SchemaVersion;
  timestamp: Timestamp;
  correlation_id: CorrelationId;
  tipo: Tipo;
  dispositivo: Dispositivo;
  metadata: SimulatorMetadata;
  conteudo: TelemetryData;
}
export interface SimulatorMetadata {
  producer: Producer;
  causation_id: CausationId;
  boot_id: BootId;
  sequence: Sequence;
  zone: Zone;
  equipment_type: EquipmentType;
  clock_scale: ClockScale;
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
export interface TelemetryPersistedV2 {
  id: Id1;
  schema_version: SchemaVersion1;
  timestamp: Timestamp1;
  correlation_id: CorrelationId1;
  tipo: Tipo1;
  dispositivo: Dispositivo1;
  metadata: WriterMetadata;
  conteudo: PersistedData;
}
export interface WriterMetadata {
  producer: Producer1;
  causation_id: CausationId1;
  boot_id: BootId1;
  sequence: Sequence1;
  zone: Zone1;
  equipment_type: EquipmentType1;
  clock_scale: ClockScale1;
  observed_at: ObservedAt;
}
export interface PersistedData1 {
  readings: Readings;
  actuators: Actuators;
  quality: Quality;
  source_event_id: SourceEventId;
}
export interface FrameReadyV2 {
  id: Id2;
  schema_version: SchemaVersion2;
  timestamp: Timestamp2;
  correlation_id: CorrelationId2;
  tipo: Tipo2;
  dispositivo: Dispositivo2;
  metadata: InferenceMetadata;
  conteudo: FrameData;
}
export interface InferenceMetadata {
  producer: Producer2;
  causation_id: CausationId2;
  boot_id: BootId2;
  sequence: Sequence2;
  zone: Zone2;
  equipment_type: EquipmentType2;
  clock_scale: ClockScale2;
  observed_at: ObservedAt1;
}
export interface FrameData {
  source_event_id: SourceEventId1;
  telemetry: PersistedData;
  insight: Insight;
}
export interface ValidInsightV2 {
  status: Status;
  model_version: ModelVersion;
  feature_version: FeatureVersion;
  health_score: HealthScore;
  rul_calendar_hours: RulCalendarHours;
}
export interface UnavailableInsightV2 {
  status: Status1;
  model_version: ModelVersion1;
  feature_version: FeatureVersion1;
  health_score: HealthScore1;
  rul_calendar_hours: RulCalendarHours1;
}
export interface InsightPredictedV2 {
  id: Id3;
  schema_version: SchemaVersion3;
  timestamp: Timestamp3;
  correlation_id: CorrelationId3;
  tipo: Tipo3;
  dispositivo: Dispositivo3;
  metadata: InferenceMetadata;
  conteudo: Conteudo;
}
export interface ValidSourceInsight {
  status: Status2;
  model_version: ModelVersion2;
  feature_version: FeatureVersion2;
  health_score: HealthScore2;
  rul_calendar_hours: RulCalendarHours2;
  source_event_id: SourceEventId2;
}
export interface UnavailableSourceInsight {
  status: Status3;
  model_version: ModelVersion3;
  feature_version: FeatureVersion3;
  health_score: HealthScore3;
  rul_calendar_hours: RulCalendarHours3;
  source_event_id: SourceEventId3;
}
export interface CommandRequestedV2 {
  id: Id4;
  schema_version: SchemaVersion4;
  timestamp: Timestamp4;
  correlation_id: CorrelationId4;
  tipo: Tipo4;
  dispositivo: Dispositivo4;
  metadata: CommandMetadata;
  conteudo: CommandDataV2;
}
export interface CommandMetadata {
  producer: Producer3;
  causation_id: CausationId3;
  zone: Zone3;
  equipment_type: EquipmentType3;
}
export interface CommandDataV2 {
  command_id: CommandId;
  target_boot_id: TargetBootId;
  revision: Revision;
  desired: DesiredActuators;
  mode: Mode;
  expires_at: ExpiresAt;
  reason_code: ReasonCode;
}
export interface DesiredActuators {
  compressor_on: CompressorOn1;
  condenser_fan_on: CondenserFanOn1;
}
export interface CommandAckV2 {
  id: Id5;
  schema_version: SchemaVersion5;
  timestamp: Timestamp5;
  correlation_id: CorrelationId5;
  tipo: Tipo5;
  dispositivo: Dispositivo5;
  metadata: SimulatorMetadata;
  conteudo: AckDataV2;
}
export interface AckDataV2 {
  command_id: CommandId1;
  revision: Revision1;
  observed: Actuators;
  reason_code: ReasonCode1;
}
export interface DeviceStateV2 {
  id: Id6;
  schema_version: SchemaVersion6;
  timestamp: Timestamp6;
  correlation_id: CorrelationId6;
  tipo: Tipo6;
  dispositivo: Dispositivo6;
  metadata: SimulatorMetadata;
  conteudo: StateDataV2;
}
export interface StateDataV2 {
  actuators: Actuators;
  mode: Mode1;
  manual_cooling_block: ManualCoolingBlock;
  reason_code: ReasonCode2;
}
export interface DeviceAvailabilityV2 {
  id: Id7;
  schema_version: SchemaVersion7;
  timestamp: Timestamp7;
  correlation_id: CorrelationId7;
  tipo: Tipo7;
  dispositivo: Dispositivo7;
  metadata: Metadata;
  conteudo: AvailabilityDataV2;
}
export interface GatewayMetadata {
  producer: Producer4;
  causation_id: CausationId4;
  boot_id: BootId3;
  sequence: Sequence3;
  zone: Zone4;
  equipment_type: EquipmentType4;
  clock_scale: ClockScale3;
  observed_at: ObservedAt2;
}
export interface AvailabilityDataV2 {
  status: Status4;
  reason_code: ReasonCode3;
}
export interface TransportReceiptV2 {
  id: Id8;
  schema_version: SchemaVersion8;
  timestamp: Timestamp8;
  correlation_id: CorrelationId8;
  tipo: Tipo8;
  dispositivo: Dispositivo8;
  metadata: GatewayMetadata;
  conteudo: ReceiptDataV2;
}
export interface ReceiptDataV2 {
  source_event_id: SourceEventId4;
  status: Status5;
}
export interface AlertV2 {
  id: Id9;
  schema_version: SchemaVersion9;
  timestamp: Timestamp9;
  correlation_id: CorrelationId9;
  tipo: Tipo9;
  dispositivo: Dispositivo9;
  metadata: ControlMetadata;
  conteudo: AlertDataV2;
}
export interface ControlMetadata {
  producer: Producer5;
  causation_id: CausationId5;
  boot_id: BootId4;
  sequence: Sequence4;
  zone: Zone5;
  equipment_type: EquipmentType5;
  clock_scale: ClockScale4;
  observed_at: ObservedAt3;
}
export interface AlertDataV2 {
  alert_id: AlertId;
  rule_id: RuleId;
  severity: Severity;
  source_event_id: SourceEventId5;
  reason_code: ReasonCode4;
}
export interface JobRequestedV2 {
  id: Id10;
  schema_version: SchemaVersion10;
  timestamp: Timestamp10;
  correlation_id: CorrelationId10;
  tipo: Tipo10;
  dispositivo: Dispositivo10;
  metadata: ApiMetadata;
  conteudo: JobRequestData;
}
export interface ApiMetadata {
  producer: Producer6;
  causation_id: CausationId6;
}
export interface JobRequestData {
  job_id: JobId;
  dataset_id: DatasetId;
  config_version: ConfigVersion;
}
export interface JobProgressV2 {
  id: Id11;
  schema_version: SchemaVersion11;
  timestamp: Timestamp11;
  correlation_id: CorrelationId11;
  tipo: Tipo11;
  dispositivo: Dispositivo11;
  metadata: WorkerMetadata;
  conteudo: ProgressDataV2;
}
export interface WorkerMetadata {
  producer: Producer7;
  causation_id: CausationId7;
}
export interface ProgressDataV2 {
  job_id: JobId1;
  kind: Kind;
  status: Status6;
  processed: Processed;
  total: Total;
  reason_code?: ReasonCode5;
}
export interface ModelAvailableV2 {
  id: Id12;
  schema_version: SchemaVersion12;
  timestamp: Timestamp12;
  correlation_id: CorrelationId12;
  tipo: Tipo12;
  dispositivo: Dispositivo12;
  metadata: WorkerMetadata;
  conteudo: ModelDataV2;
}
export interface ModelDataV2 {
  model_version: ModelVersion4;
  feature_version: FeatureVersion4;
  dataset_id: DatasetId1;
  sha256: Sha256;
}
export interface ModelActivatedV2 {
  id: Id13;
  schema_version: SchemaVersion13;
  timestamp: Timestamp13;
  correlation_id: CorrelationId13;
  tipo: Tipo13;
  dispositivo: Dispositivo13;
  metadata: ModelMetadata;
  conteudo: ModelDataV2;
}
export interface ModelMetadata {
  producer: Producer8;
  causation_id: CausationId8;
}
export interface QuarantinedV2 {
  id: Id14;
  schema_version: SchemaVersion14;
  timestamp: Timestamp14;
  correlation_id: CorrelationId14;
  tipo: Tipo14;
  dispositivo: Dispositivo14;
  metadata: MetadataV2;
  conteudo: Conteudo1;
}
export interface MetadataV2 {
  producer: Producer9;
  causation_id: CausationId9;
}
export interface InlineQuarantine {
  failure_id: FailureId;
  owner: Owner;
  reason_code: ReasonCode6;
  original_sha256: OriginalSha256;
  original_route: OriginalRoute;
  attempts: Attempts;
  original_bytes_b64: OriginalBytesB64;
  original_ref: OriginalRef;
}
export interface ReferencedQuarantine {
  failure_id: FailureId1;
  owner: Owner1;
  reason_code: ReasonCode7;
  original_sha256: OriginalSha2561;
  original_route: OriginalRoute1;
  attempts: Attempts1;
  original_bytes_b64: OriginalBytesB641;
  original_ref: OriginalRef1;
}
