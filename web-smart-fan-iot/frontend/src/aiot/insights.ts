import type { FrameReadyV2 } from '../lib/contracts-v2.generated';
import { frameFresh } from './live-store';

export const insightLabels: Record<string, string> = {
  valid: 'Previsão disponível',
  warming_up: 'Aquecendo a janela de observação',
  insufficient_data: 'Leituras insuficientes',
  inactive: 'Compressor inativo',
  model_unavailable: 'Modelo indisponível',
  out_of_domain: 'Fora do domínio de treino',
  stale: 'Sem dados recentes',
};
export function presentation(
  frame: FrameReadyV2 | undefined,
  now: number,
  fresh = true,
) {
  const insight = frame?.conteudo.insight;
  const status =
    !frame || !fresh || !frameFresh(frame, now) ? 'stale' : insight!.status;
  const valid = status === 'valid';
  return {
    status,
    label: insightLabels[status] ?? 'Previsão indisponível',
    health: valid ? insight!.health_score : null,
    rul: valid ? insight!.rul_calendar_hours : null,
    version: insight?.model_version ?? null,
  };
}
export interface PredictionPoint {
  sampled_at: string;
  boot_id: string;
  model_version: string | null;
  status: string | null;
  health_score: number | null;
  rul_calendar_hours: number | null;
  source_event_id: string;
}
export function pointsFromFrames(frames: FrameReadyV2[]): PredictionPoint[] {
  return frames.map((frame) => ({
    sampled_at: frame.timestamp,
    boot_id: frame.metadata.boot_id,
    source_event_id: frame.conteudo.source_event_id,
    ...frame.conteudo.insight,
  }));
}
export function trend(
  points: PredictionPoint[],
  target: 'health_score' | 'rul_calendar_hours',
) {
  const labels: string[] = [];
  const values: (number | null)[] = [];
  points.forEach((point, index) => {
    const previous = points[index - 1];
    const label = new Date(point.sampled_at).toLocaleTimeString('pt-BR');
    if (
      previous &&
      (Date.parse(point.sampled_at) - Date.parse(previous.sampled_at) > 6000 ||
        previous.boot_id !== point.boot_id ||
        previous.model_version !== point.model_version)
    ) {
      labels.push(label);
      values.push(null);
    }
    labels.push(label);
    values.push(point.status === 'valid' ? point[target] : null);
  });
  return { labels, values };
}
export const numberText = (value: number | null | undefined) =>
  value == null
    ? '—'
    : value.toLocaleString('pt-BR', { maximumFractionDigits: 1 });

export interface PredictiveConfiguration {
  enabled: boolean;
  health_raise: number;
  health_clear: number;
  rul_raise_hours: number;
  rul_clear_hours: number;
  bad_samples: number;
  good_samples: number;
}
export interface RuleMetadata {
  revision: number;
  configuration: PredictiveConfiguration;
  state: {
    bad_count: number;
    good_count: number;
    active_alert_id: string | null;
    last_sample_at: string;
  } | null;
}
export interface AlertRecord {
  id: string;
  device_id: string;
  severity: string;
  status: string;
  raised_at: string;
  cleared_at: string | null;
  model_version: string | null;
  rule_revision: number;
}
