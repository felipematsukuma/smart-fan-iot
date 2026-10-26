"""Regras de integracao de energia e de amostragem do historico.

A integracao trapezoidal so avanca quando o intervalo entre amostras esta
dentro da tolerancia (MAX_ENERGY_SAMPLE_GAP_SECONDS). Este modulo isola a
regra para poder ser testada sem depender de InfluxDB.
"""
from dataclasses import dataclass
from datetime import datetime

# Abaixo desta potencia o rele esta aberto: o firmware so zera a potencia
# quando o ventilador esta de fato desligado.
OFF_POWER_THRESHOLD_W = 0.0

# Duracao minima para considerar um trecho a 0 W como "ventilador desligado"
# e nao como uma leitura isolada de ruido.
MIN_OFF_DURATION_SECONDS = 30.0


@dataclass(frozen=True)
class EnergyResult:
    energy_wh: float
    avg_power_w: float
    total_samples: int
    covered_samples: int
    discarded_intervals: int
    discarded_wh: float


def integrate_energy(
    samples: list[tuple[datetime, float]],
    max_gap_seconds: float,
) -> EnergyResult:
    """Integra potência por trapézios entre amostras consecutivas.

    Regras:
      * intervalos <= 0 são ignorados (relógio não retrocede);
      * intervalos acima de `max_gap_seconds` são considerados sem cobertura
        do dispositivo e ficam FORA da conta — nunca inventamos consumo;
      * a média é a média aritmética simples das amostras, cobrindo todo o
        período da consulta (inclusive trechos sem cobertura), que é a média
        de todas as amostras coletadas.
    """
    if not samples:
        return EnergyResult(0.0, 0.0, 0, 0, 0, 0.0)

    total_samples = len(samples)
    sum_power = sum(power for _, power in samples)
    avg_power_w = (sum_power / total_samples) if total_samples else 0.0

    energy_wh = 0.0
    discarded_wh = 0.0
    discarded_intervals = 0
    covered_samples = 0

    for (previous_time, previous_power), (current_time, current_power) in zip(
        samples, samples[1:]
    ):
        gap_seconds = (current_time - previous_time).total_seconds()
        if gap_seconds <= 0:
            continue

        # Potência média do trapézio, integrada ao longo do intervalo.
        interval_wh = (
            (previous_power + current_power) / 2.0
        ) * gap_seconds / 3600.0

        if gap_seconds <= max_gap_seconds:
            energy_wh += interval_wh
            covered_samples += 1
        else:
            discarded_wh += interval_wh
            discarded_intervals += 1

    return EnergyResult(
        energy_wh=round(energy_wh, 3),
        avg_power_w=round(avg_power_w, 2),
        total_samples=total_samples,
        covered_samples=covered_samples,
        discarded_intervals=discarded_intervals,
        discarded_wh=round(discarded_wh, 3),
    )


# --------------------------------------------------------------------------
# Amostragem do historico para o grafico
#
# A selecao por indice (round(i * (N-1) / 119)) e suficiente enquanto a
# telemetria e densa, mas quebra com dados esparsos. Medindo a janela de 7 dias
# deste projeto: 2466 amostras reais viravam 120 pontos distribuidos em 48
# aglomerados, MEDIANA DE 1 PONTO. Ponto isolado nao forma linha — vira um
# espinho vertical de 1 px, e o usuario enxerga um grafico "vazio".
#
# A regra aqui gasta o orcamento onde existe consumo:
#   * trecho a 0 W (rele aberto) ganha no maximo 2 pontos: o instante em que
#     desligou e o em que religou. E tudo que o grafico precisa, porque ele
#     comprime esse trecho para um intervalo fino;
#   * trecho com consumo recebe a maior parte do orcamento, proporcional ao
#     numero de amostras;
#   * lacuna (sem telemetria) nao consome orcamento: o eixo temporal e
#     limitado pela janela inteira, nao pelas amostras.
# --------------------------------------------------------------------------


def _split_regions(
    samples: list[tuple[datetime, float]],
    gap_limit_seconds: float,
    is_off,
) -> list[tuple[bool, list[tuple[datetime, float]]]]:
    """Divide a série em regiões contíguas do mesmo tipo, quebrando em lacunas.

    A quebra na lacuna é deliberada: se o Wokwi pausou no meio de um trecho a
    0 W, o estado durante a pausa é desconhecido e os dois lados não podem ser
    costurados como um desligamento contínuo.
    """
    regions: list[tuple[bool, list[tuple[datetime, float]]]] = []
    current = [samples[0]]
    current_off = is_off(samples[0])

    for previous, current_item in zip(samples, samples[1:]):
        gap_seconds = (current_item[0] - previous[0]).total_seconds()
        item_off = is_off(current_item)
        if gap_seconds > gap_limit_seconds or item_off != current_off:
            regions.append((current_off, current))
            current = [current_item]
            current_off = item_off
        else:
            current.append(current_item)

    regions.append((current_off, current))
    return regions


def _pick_evenly(
    region: list[tuple[datetime, float]],
    quota: int,
) -> list[tuple[datetime, float]]:
    """Seleciona `quota` pontos da região preservando sempre as duas bordas.

    As bordas são as transições de estado: é nelas que se vê o ventilador
    ligando e desligando, que é a informação que o gráfico precisa mostrar.
    """
    total = len(region)
    if quota >= total:
        return list(region)
    if quota <= 0:
        return []
    if quota == 1:
        return [region[0]]

    last_index = total - 1
    indexes = sorted({round(i * last_index / (quota - 1)) for i in range(quota)})
    return [region[i] for i in indexes]


def _spread(
    quotas: list[int],
    capacities: list[int],
    budget: int,
) -> list[int]:
    """Distribui até `budget` pontos extras entre as regiões.

    Cada ponto vai para a região com a maior fatia proporcional da
    capacidade que ainda resta, e nunca ultrapassa essa capacidade. É
    deliberadamente simples: um laço com no máximo `budget` voltas sobre
    `budget` e `len(capacities)`, que são pequenos (centenas), e não há
    acumulado a ajustar, o que elimina a classe de bug em que o arredondamento
    faz o total estourar o limite de pontos.
    """
    remaining = list(capacities)
    while budget > 0:
        eligible = [i for i, room in enumerate(remaining) if room > 0]
        if not eligible:
            break
        total = sum(remaining[i] for i in eligible)
        winner = max(eligible, key=lambda i: remaining[i] / total)
        quotas[winner] += 1
        remaining[winner] -= 1
        budget -= 1
    return quotas


def downsample_samples(
    samples: list[tuple[datetime, float]],
    max_points: int,
    off_threshold_w: float = OFF_POWER_THRESHOLD_W,
    gap_limit_seconds: float = 80.0,
) -> list[tuple[datetime, float]]:
    """Reduz a série para o gráfico, cobrindo TODOS os trechos de atividade.

    Prioridades, em ordem:

      1. Nenhuma região pode sumir. Cada trecho (com consumo ou desligado)
         recebe no mínimo 2 pontos — as duas bordas, que são justamente as
         transições de estado. Um trecho com 1 ponto só não desenha linha
         nenhuma: vira um espinho de 1 px, ou nada, com `pointRadius: 0`.
      2. O que sobra do orçamento vai para os trechos com consumo, na
         proporção do número de amostras. Um trecho desligado nunca ganha
         ponto extra: o gráfico o comprime para um intervalo fino.
      3. Se o mínimo não couber no orçamento, sobrevivem as maiores regiões.

    A INTEGRAÇÃO DE ENERGIA NUNCA USA ESTA FUNÇÃO: ela roda sobre a série
    completa (ver `integrate_energy`), porque descartar amostras mudaria a
    conta. Aqui a perda de detalhe é aceitável porque o objetivo é legibilidade.
    """
    if len(samples) <= max_points:
        return list(samples)
    if max_points < 2:
        raise ValueError("max_points deve ser >= 2 para preservar as bordas")

    def is_off(item: tuple[datetime, float]) -> bool:
        return item[1] <= off_threshold_w

    regions = _split_regions(samples, gap_limit_seconds, is_off)

    # 1. Base: 2 pontos por região, enquanto couber.
    quotas = [min(2, len(region)) for _, region in regions]
    if sum(quotas) > max_points:
        # Não cabe: ficam as maiores regiões, que concentram a informação.
        order = sorted(
            range(len(regions)),
            key=lambda i: (len(regions[i][1]), quotas[i]),
            reverse=True,
        )
        kept = [0] * len(regions)
        left = max_points
        for i in order:
            if left <= 0:
                break
            take = min(quotas[i], left)
            kept[i] = take
            left -= take
        return sorted(
            [point for (_, region), quota in zip(regions, kept)
             for point in _pick_evenly(region, quota)],
            key=lambda item: item[0],
        )

    # 2. Sobra do orçamento: proporcional à capacidade, só para quem consome.
    active_indexes = [i for i, (is_off_region, _) in enumerate(regions) if not is_off_region]
    capacities = [
        len(regions[i][1]) - quotas[i] if i in active_indexes else 0
        for i in range(len(regions))
    ]
    quotas = _spread(quotas, capacities, max_points - sum(quotas))

    selected: list[tuple[datetime, float]] = []
    for (_, region), quota in zip(regions, quotas):
        selected.extend(_pick_evenly(region, quota))
    return sorted(selected, key=lambda item: item[0])


def series_metadata(samples, period_start, period_end, max_gap_seconds):
    """Compute coverage and continuity BEFORE display downsampling.

    Times are server receipt times. Missing edges and gaps are unknown, even
    when both surrounding readings are zero. Coverage never extrapolates.
    """
    segments = []
    covered_seconds = 0.0

    def append(kind, start, end):
        if end <= start:
            return
        if segments and segments[-1]["kind"] == kind and segments[-1]["to"] == start.isoformat():
            segments[-1]["to"] = end.isoformat()
        else:
            segments.append({"kind": kind, "from": start.isoformat(), "to": end.isoformat()})

    if not samples:
        append("no-data", period_start, period_end)
    else:
        append("no-data", period_start, samples[0][0])
        for (start, previous), (end, current) in zip(samples, samples[1:]):
            gap = (end - start).total_seconds()
            if gap <= 0:
                continue
            if gap > max_gap_seconds:
                append("no-data", start, end)
            else:
                covered_seconds += gap
                append("off" if previous == 0 and current == 0 else "active", start, end)
        append("no-data", samples[-1][0], period_end)
    duration = (period_end - period_start).total_seconds()
    powers = [p for _, p in samples]
    return {
        "coverage": min(1.0, covered_seconds / duration) if duration > 0 else 0.0,
        "covered_seconds": round(covered_seconds, 3),
        "max_power_w": max(powers, default=0.0),
        "segments": segments,
    }
