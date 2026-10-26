/**
 * Regras de frescor do dispositivo, extraídas de App.vue para serem testáveis.
 *
 * A distinção que importa: "sem mensagem há pouco tempo" é diferente de
 * "sem telemetria de verdade". Com a tolerância errada, o painel desligava o
 * botão de comando enquanto o ventilador estava funcionando.
 */

/**
 * Folga para considerar o ESP32 online.
 *
 * Medindo os intervalos entre amostras DENTRO de sessões ativas (ESP32 ligado,
 * sem pausas longas do Wokwi):
 *     mediana 3,9 s · p90 4,9 s · p95 5,4 s · p99 31,2 s · máximo 68,4 s
 *
 * Com 10 s o painel marcava OFFLINE em 18 lacunas, 412 s acumulados, 12 delas
 * com o ventilador LIGADO. 90 s cobre toda a cauda com ~30% de margem.
 */
export const OFFLINE_FRESHNESS_MS = 90_000;

/** Intervalo de consulta das métricas agregadas. */
export const METRICS_REFRESH_MS = 5_000;

/** Tempo que se espera a confirmação do ESP32 após um comando. */
export const COMMAND_TIMEOUT_MS = 10_000;

/** Heartbeat do status a cada segundo, para o "há X s" ficar fluido. */
export const STATUS_TICK_MS = 1_000;

/**
 * O dispositivo está online?
 *
 * Exige o socket conectado E uma mensagem recente. O socket aberto sozinho não
 * basta: o backend pode estar de pé enquanto o ESP32 está fora.
 */
export function isDeviceOnline(
  socketConnected: boolean,
  lastMessageAt: number | null,
  now: number
): boolean {
  if (!socketConnected) return false;
  if (lastMessageAt === null) return false;
  return now - lastMessageAt <= OFFLINE_FRESHNESS_MS;
}

/** Texto de "último sinal" a partir da idade da última mensagem. */
export function formatLastSeen(lastMessageAt: number | null, now: number): string {
  if (lastMessageAt === null) return 'sem sinal';
  const age = Math.max(0, (now - lastMessageAt) / 1000);
  // O limiar compara a idade real, e não a arredondada: com 2,5 s a tela
  // mostraria "há 3 s" (o arredondamento) enquanto o teste de 3 s ainda valia.
  if (age < 3) return 'agora mesmo';
  const seconds = Math.round(age);
  if (seconds < 60) return `há ${seconds} s`;
  return `há ${Math.round(seconds / 60)} min`;
}

/** Períodos rápidos de análise, em horas. */
export const PERIODS = { '8h': 8, '24h': 24, '7d': 168 } as const;
export type PeriodKey = keyof typeof PERIODS | 'custom';

/** O período é longo o bastante para precisar mostrar o dia nos rótulos? */
export function isMultiDay(key: PeriodKey): boolean {
  if (key === 'custom') return false;
  return PERIODS[key] > 24;
}

/** Rótulo do período, como exibido no cabeçalho e nos cartões. */
export function periodLabel(key: PeriodKey): string {
  if (key === 'custom') return 'Período personalizado';
  return `Últimas ${PERIODS[key]}h`;
}
