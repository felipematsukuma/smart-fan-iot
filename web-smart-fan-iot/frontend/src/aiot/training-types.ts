export type TargetName = 'health_score' | 'rul_calendar_hours';
export interface Metrics {
  mae: number | null;
  rmse: number | null;
  r2: number | null;
  count: number;
  reason: string | null;
}
export interface TargetReport {
  selected_algorithm: string;
  validation_candidates: Record<string, Metrics>;
  validation_baseline: Metrics;
  test: Metrics;
  test_baseline: Metrics;
  benchmark: Metrics;
  benchmark_baseline: Metrics;
  benchmark_active: Metrics | null;
  feature_importance: { feature: string; importance: number; std: number }[];
  scatter: { real: number; predicted: number }[];
  censored_excluded: number;
  healthy_false_positive_fraction: number | null;
  train_samples: number;
  validation_samples: number;
  test_samples: number;
}
export interface TrainingReport {
  model_version: string;
  dataset_sha256: string;
  feature_version: string;
  feature_names: string[];
  rul_unit: string;
  targets: Record<TargetName, TargetReport>;
  split: { train: string[]; validation: string[]; test: string[] };
  benchmark_sha256: string;
  benchmark_seed: number;
  eligible: boolean;
  promotion_reasons: string[];
  limitations: string[];
  hyperparameters: Record<string, unknown>;
  feature_rows: number;
  source_rows: number;
}
export interface ModelRecord {
  version: string;
  dataset_id: string;
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  approved: boolean;
  artifact_sha256: string | null;
  report?: TrainingReport | null;
  promotion_reasons?: string[];
}
export interface Selection {
  desired_version: string | null;
  active_version: string | null;
  activation_revision: number;
  active_revision: number;
}
