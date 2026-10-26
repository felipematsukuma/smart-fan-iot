"""Testes de integridade da regra de energia.

A integração trapezoidal só avança quando o intervalo entre amostras está
dentro da tolerância (MAX_ENERGY_SAMPLE_GAP_SECONDS). A regra está isolada em
`app.energy`, e estes testes usam a MESMA função que a API usa.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.energy import EnergyResult, downsample_samples, integrate_energy

UTC = timezone.utc
T0 = datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC)
TOLERANCE = 80.0
# Tolerância sem teto: isola o trapézio da regra de lacuna.
NO_GAP_LIMIT = 1e9


def series(pairs):
    """[(segundos_desde_T0, potencia), ...] -> [(datetime, float)]"""
    return [(T0 + timedelta(seconds=s), float(p)) for s, p in pairs]


# ---------------------------------------------------------------- energia


def test_lista_vazia_nao_quebra():
    r = integrate_energy([], TOLERANCE)
    assert r.energy_wh == 0.0
    assert r.avg_power_w == 0.0
    assert r.total_samples == 0


def test_uma_unica_amostra_nao_gera_energia():
    r = integrate_energy(series([(0, 30.0)]), TOLERANCE)
    assert r.energy_wh == 0.0
    assert r.total_samples == 1


def test_trapezio_de_potencia_constante():
    """30 W durante 1 h == 30 Wh."""
    r = integrate_energy(series([(0, 30), (3600, 30)]), NO_GAP_LIMIT)
    assert r.energy_wh == pytest.approx(30.0, abs=0.01)


def test_trapezio_acumulativo_com_passos_reais():
    """Mesma energia, agora com passos de 4 s como na telemetria real."""
    dados = [(i * 4, 30) for i in range(901)]  # 3600 s
    r = integrate_energy(series(dados), TOLERANCE)
    assert r.energy_wh == pytest.approx(30.0, abs=0.01)
    assert r.discarded_intervals == 0


def test_trapezio_interpola_entre_potencias_diferentes():
    """0 W -> 30 W em 1 h: a média do trapézio é 15 W, logo 15 Wh."""
    r = integrate_energy(series([(0, 0), (3600, 30)]), NO_GAP_LIMIT)
    assert r.energy_wh == pytest.approx(15.0, abs=0.01)


def test_intervalo_dentro_da_tolerancia_e_integrado():
    r = integrate_energy(series([(0, 30), (60, 30)]), TOLERANCE)
    assert r.energy_wh == pytest.approx(0.5, abs=0.01)   # 30 W por 60 s
    assert r.discarded_intervals == 0
    assert r.covered_samples == 1


def test_intervalo_acima_da_tolerancia_e_descartado():
    """30 W por 600 s, mas a lacuna excede a tolerância: não pode inventar."""
    r = integrate_energy(series([(0, 30), (600, 30)]), TOLERANCE)
    assert r.energy_wh == 0.0
    assert r.discarded_intervals == 1
    assert r.discarded_wh == pytest.approx(5.0, abs=0.01)


def test_nunca_conta_mais_que_a_integracao_completa():
    """Propriedade de integridade central: em energia, subestimar é aceitável
    (ninguém perde dinheiro), inventar não é."""
    dados = [
        (0, 29.77), (3, 29.77), (4, 0), (50, 0), (51, 29.77),
        (700, 29.77), (701, 0), (4000, 0), (4001, 29.77),
    ]
    restrito = integrate_energy(series(dados), TOLERANCE)
    completo = integrate_energy(series(dados), NO_GAP_LIMIT)
    assert restrito.energy_wh <= completo.energy_wh + 1e-6
    assert restrito.energy_wh >= 0.0


def test_media_cobre_todas_as_amostras():
    """A média ignora a regra de lacuna: é sobre todas as amostras coletadas."""
    r = integrate_energy(series([(0, 10), (1000, 20), (2000, 30)]), TOLERANCE)
    assert r.avg_power_w == pytest.approx(20.0, abs=0.01)
    assert r.total_samples == 3


def test_relogio_que_retrocede_e_ignorado():
    """Defense em profundidade: a API ordena as amostras antes de integrar, mas
    se alguma vez chegar fora de ordem o intervalo negativo não pode virar
    energia negativa."""
    amostras = [
        (T0, 30.0),
        (T0 - timedelta(seconds=10), 30.0),          # retrocesso
        (T0 + timedelta(seconds=10), 30.0),
    ]
    r = integrate_energy(amostras, TOLERANCE)
    # o par que retrocede é ignorado; o par seguinte (T0-10 -> T0+10) vale 20 s
    assert r.energy_wh == pytest.approx(30.0 * 20 / 3600, abs=0.001)
    assert r.energy_wh > 0
    assert r.discarded_intervals == 0


def test_lacuna_no_meio_nao_contamina_os_lados():
    r = integrate_energy(
        series([(0, 30), (10, 30), (5000, 30), (5010, 30)]), TOLERANCE
    )
    lateral = 30.0 * 20 / 3600   # 10 s antes + 10 s depois da lacuna
    assert r.energy_wh == pytest.approx(lateral, abs=0.01)
    assert r.discarded_intervals == 1


def test_energia_coerente_com_tensao_corrente_e_fator_de_potencia():
    """Coerência física: P = V * I * FP, com V=127 e FP=0,90 no firmware.
    0,26 A em 1 h resulta em ~29,7 Wh."""
    potencia = 0.26 * 127 * 0.90
    r = integrate_energy(series([(0, potencia), (3600, potencia)]), NO_GAP_LIMIT)
    assert r.energy_wh == pytest.approx(29.718, abs=0.02)
    assert r.avg_power_w == pytest.approx(29.72, abs=0.02)


def test_zero_watts_gera_zero_energia():
    r = integrate_energy(series([(0, 0), (3600, 0)]), NO_GAP_LIMIT)
    assert r.energy_wh == 0.0


def test_resultado_e_imutavel():
    r = integrate_energy(series([(0, 30), (10, 30)]), TOLERANCE)
    assert isinstance(r, EnergyResult)
    with pytest.raises(Exception):
        r.energy_wh = 999.0


def test_arredondamento_nao_acumula_erro():
    """Com passo de 4 s e 1 h de dados, o arredondamento a 3 casas não pode
    introduzir desvio perceptível."""
    dados = [(i * 4, 29.77) for i in range(901)]
    r = integrate_energy(series(dados), TOLERANCE)
    exato = 29.77 * 1.0
    assert abs(r.energy_wh - exato) < 0.01


# -------------------------------------------------------------- downsample


def test_downsample_nao_altera_series_curtas():
    dados = series([(i, 30) for i in range(50)])
    assert downsample_samples(dados, 120) == dados


def test_downsample_respeita_o_teto():
    dados = series([(i, 30) for i in range(1000)])
    assert len(downsample_samples(dados, 120)) == 120


def test_downsample_preserva_bordas():
    """O primeiro e o último ponto precisam sobreviver: são as bordas do período."""
    dados = series([(i, i) for i in range(1000)])
    r = downsample_samples(dados, 120)
    assert r[0] == dados[0]
    assert r[-1] == dados[-1]


def test_downsample_preserva_ordem_cronologica():
    dados = series([(i, 30) for i in range(1000)])
    tempos = [t for t, _ in downsample_samples(dados, 120)]
    assert tempos == sorted(tempos)


def test_downsample_rejeita_limite_absurdo():
    dados = series([(i, 30) for i in range(1000)])
    with pytest.raises(ValueError):
        downsample_samples(dados, 1)


def test_historico_para_frontend_sempre_cabe_no_teto():
    """Contrato com o frontend: nunca mais que MAX_HISTORY_POINTS."""
    from app.main import MAX_HISTORY_POINTS
    for n in (0, 1, 2, 119, 120, 121, 241, 5000, 100000):
        dados = series([(i, 30) for i in range(n)])
        r = downsample_samples(dados, MAX_HISTORY_POINTS)
        assert len(r) <= MAX_HISTORY_POINTS


# ------------------------------------------------- amostragem por atividade


def _off_then_on(t0_off_min, off_minutes, samples_per_minute=1):
    """Série (datetime, W) com um trecho desligado cercado por trechos ligados."""
    dados = [(0, 29.77), (1, 29.77)]
    for m in range(off_minutes):
        for k in range(samples_per_minute):
            dados.append((t0_off_min + m + k / samples_per_minute, 0.0))
    dados.append((t0_off_min + off_minutes + 1, 29.77))
    return series(dados)


def test_trecho_desligado_ganha_somente_as_bordas():
    """Um desligamento de 3 h precisa de 2 pontos, não de milhares.

    O gráfico comprime esse trecho; o que importa é saber QUANDO desligou e
    QUANDO religou. Com passo de 4 s, 3 h são 2700 amostras.
    """
    dados = _off_then_on(2, 180, samples_per_minute=15)   # ~2700 amostras a 0 W
    assert len(dados) > 240, "a série precisa exceder o teto para haver downsample"
    r = downsample_samples(dados, 240, gap_limit_seconds=TOLERANCE)
    desligados = [p for _, p in r if p == 0.0]
    assert len(desligados) == 2
    # e o orçamento não foi todo para o desligamento
    assert len([p for _, p in r if p > 0]) >= 2


def test_trecho_com_consumo_mais_longo_ganha_mais_pontos():
    """A resolução extra vai para onde há consumo, não para onde há silêncio."""
    dados = [(i, 29.77) for i in range(300)]
    dados += [(i, 0.0) for i in range(300, 3300)]
    r = downsample_samples(series(dados), 240, gap_limit_seconds=TOLERANCE)
    ligados = [p for _, p in r if p > 0]
    desligados = [p for _, p in r if p == 0]
    assert len(ligados) > len(desligados) * 5


def test_nenhuma_regiao_some_do_grafico():
    """O defeito original: com dado esparso, o ponto isolado some da tela.

    A garantia é que TODO trecho de atividade tenha pelo menos 2 pontos, para
    formar linha. Um ponto só não desenha nada com pointRadius: 0.
    """
    dados = []
    for burst in range(40):                       # 40 rajadas de 5 amostras
        base = burst * 60
        for k in range(5):
            dados.append((base + k * 4, 29.77))
    r = downsample_samples(series(dados), 240, gap_limit_seconds=TOLERANCE)

    inicio = T0
    for burst in range(40):
        comeco = inicio + timedelta(seconds=burst * 60)
        fim = comeco + timedelta(seconds=60)
        dentro = [p for p in r if comeco <= p[0] < fim]
        assert len(dentro) >= 2, f"rajada {burst} ficou com {len(dentro)} ponto(s)"


def test_downsample_preserva_o_pico():
    """O valor máximo da série é o dado mais importante do gráfico."""
    dados = [(i, 0.0) for i in range(50)]
    dados[25] = (25, 91.4)
    dados += [(50 + i, 29.77) for i in range(400)]
    r = downsample_samples(series(dados), 60, gap_limit_seconds=TOLERANCE)
    assert max(p for _, p in r) == pytest.approx(91.4)


def test_downsample_nao_altera_a_integracao():
    """A energia NUNCA sai da série reamostrada.

    É a separação mais importante do módulo: descartar amostras é aceitável
    para desenhar, mas mudaria a conta de luz.

    Aqui a amostragem por atividade preserva a integral exatamente, porque o
    trecho com consumo é uniforme. A propriedade garantida é a que importa: a
    versão reamostrada NUNCA supera a completa. Subestimar é aceitável
    (ninguém perde dinheiro); inventar não é.
    """
    dados = series([(i * 4, 29.77 if 2000 < i < 2600 else 0.0) for i in range(4000)])
    completo = integrate_energy(dados, TOLERANCE)
    reduzido = integrate_energy(
        downsample_samples(dados, 240, gap_limit_seconds=TOLERANCE),
        TOLERANCE,
    )
    assert reduzido.energy_wh <= completo.energy_wh + 1e-9
    # E a produção realmente integra a série completa, não a reamostrada.
    import inspect

    from app import main as main_mod

    fonte = inspect.getsource(main_mod.get_metrics)
    assert "integrate_energy(samples" in fonte
    assert "downsample_samples" in fonte
    # a integração vem ANTES do downsample no corpo da função
    assert fonte.index("integrate_energy(samples") < fonte.index("downsample_samples")


def test_regiao_de_uma_amostra_ganha_ponto():
    """Uma rajada de 1 amostra é ruído, mas não pode desaparecer sem mais."""
    dados = series([(0, 29.77), (1, 29.77), (600, 29.77), (601, 29.77), (602, 29.77)])
    r = downsample_samples(dados, 4, gap_limit_seconds=TOLERANCE)
    assert len(r) == 4
    assert r[0][0] == dados[0][0]
    assert r[-1][0] == dados[-1][0]


def test_tolerancia_cobre_a_pausa_real_do_dispositivo():
    """Trava de regressão da tolerância.

    Medido em produção: a maior pausa do dispositivo ligado é 68,4 s e o menor
    trecho de estado desconhecido é 91,1 s. A tolerância precisa ficar entre
    os dois — abaixo dela a energia real é perdida, acima dela o consumo é
    inventado.
    """
    MAIOR_PAUSA = 68.4
    MENOR_DESCONHECIDO = 91.1
    TOLERANCIA = 80.0
    assert MAIOR_PAUSA < TOLERANCIA < MENOR_DESCONHECIDO

    # Com a tolerância escolhida, a pausa é integrada...
    r = integrate_energy(series([(0, 30), (MAIOR_PAUSA, 30)]), TOLERANCIA)
    assert r.energy_wh > 0 and r.discarded_intervals == 0
    # ...e o trecho desconhecido não é.
    r = integrate_energy(series([(0, 30), (MENOR_DESCONHECIDO, 30)]), TOLERANCIA)
    assert r.energy_wh == 0.0 and r.discarded_intervals == 1


def test_dense_eight_hours_keeps_full_coverage_after_downsampling():
    from app.energy import series_metadata
    start = datetime(2026, 10, 26, tzinfo=timezone.utc)
    samples = [(start + timedelta(seconds=2 * i), 30.0) for i in range(14401)]
    end = start + timedelta(hours=8)
    metadata = series_metadata(samples, start, end, 80)
    assert len(downsample_samples(samples, 240)) == 240
    assert metadata["coverage"] == 1.0
    assert integrate_energy(samples, 80).energy_wh == 240.0
    assert len(metadata["segments"]) == 1


def test_zero_endpoints_do_not_cover_a_missing_hour():
    from app.energy import series_metadata
    start = datetime(2026, 10, 26, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    metadata = series_metadata([(start, 0), (end, 0)], start, end, 80)
    assert metadata["coverage"] == 0
    assert metadata["segments"][0]["kind"] == "no-data"
