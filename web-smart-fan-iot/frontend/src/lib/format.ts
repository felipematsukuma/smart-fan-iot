/**
 * Formatação de números para exibição.
 *
 * Isolada para ser testável: regras de precisão são fáceis de quebrar num
 * ajuste visual e ninguém percebe até a conta sair errada.
 */

/**
 * Energia em kWh com precisão adaptativa.
 *
 * O valor muda de escala conforme a janela: consumo de casa é ~0,04 kWh e
 * precisão de 3 casas já esconderia tudo. Abaixo de 0,001 kWh usamos mais casas
 * para o número não virar 0,000.
 */
export function formatKwh(value: number): string {
  return value >= 0.001 ? value.toFixed(3) : value.toFixed(6);
}

/**
 * Dinheiro em BRL com precisão adaptativa.
 *
 * Valores pequenos (energia residual de minutos) precisam de mais casas para
 * não aparecerem como R$ 0,00.
 */
export function formatCurrency(value: number): string {
  const minor = Math.abs(value) < 0.1;
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: minor ? 5 : 2,
    maximumFractionDigits: minor ? 5 : 2,
  }).format(value);
}

/** Potência com uma casa decimal. */
export function formatPower(value: number): string {
  return value.toFixed(1);
}

/** Corrente com três casas, como sai do firmware. */
export function formatCurrent(value: number): string {
  return value.toFixed(3);
}

/**
 * Projeção de custo mensal a partir do consumo do período.
 *
 * `estimated_kwh` cobre `durationHours`; projetamos 30 dias a partir disso.
 * Sem isso, comparar janelas de tamanhos diferentes daria números sem sentido.
 */
export function projectMonthlyCost(
  estimatedKwh: number,
  tariff: number,
  durationHours: number
): number {
  if (!(durationHours > 0)) return 0;
  return (estimatedKwh * tariff * 30) / (durationHours / 24);
}

/**
 * Intervalo médio entre amostras, em minutos inteiros.
 *
 * Devolve `null` quando não há dados suficientes, para o chamador omitir o
 * trecho em vez de exibir "a cada 0 min".
 */
export function sampleIntervalMinutes(timesIso: string[]): number | null {
  if (timesIso.length < 2) return null;
  const first = new Date(timesIso[0]).getTime();
  const last = new Date(timesIso[timesIso.length - 1]).getTime();
  const spanMinutes = (last - first) / 60_000;
  if (!(spanMinutes > 0)) return null;
  return Math.max(1, Math.round(spanMinutes / (timesIso.length - 1)));
}

/** Texto de cobertura, já formatado em porcentagem. */
export function formatCoverage(coverage: number): string {
  return `${(coverage * 100).toFixed(0)}%`;
}
