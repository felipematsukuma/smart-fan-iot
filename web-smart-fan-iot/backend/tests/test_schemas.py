"""Testes dos esquemas de entrada (validação de dados que entram no sistema)."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    AutoShutdownUpdate,
    DeviceCommand,
    ScheduleUpdate,
    TariffUpdate,
    TelemetryPayload,
)

# ------------------------------------------------------------ DeviceCommand


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("ON", "ON"),
        ("OFF", "OFF"),
        ("on", "ON"),
        ("off", "OFF"),  # normaliza caixa
        ("On", "ON"),
    ],
)
def test_comando_normaliza_caixa(entrada, esperado):
    assert DeviceCommand(action=entrada).action == esperado


@pytest.mark.parametrize("invalido", ["", "AUTO", "TOGGLE", "1", "onoff"])
def test_comando_rejeita_acao_desconhecida(invalido):
    with pytest.raises(ValidationError):
        DeviceCommand(action=invalido)


def test_comando_exige_acao():
    with pytest.raises(ValidationError):
        DeviceCommand()


@pytest.mark.parametrize("velocidade", [0, 1, 2, 3, 4])
def test_comando_rejeita_velocidade_nao_implementada(velocidade):
    with pytest.raises(ValidationError):
        DeviceCommand(action="ON", speed=velocidade)


# ------------------------------------------------- validação de horário HH:MM


@pytest.mark.parametrize(
    "hora",
    [
        "00:00",
        "03:30",
        "09:05",
        "23:59",
        "12:00",
    ],
)
def test_aceita_horario_valido(hora):
    assert AutoShutdownUpdate(auto_off_time=hora, auto_off_enabled=True).auto_off_time == hora
    assert ScheduleUpdate(auto_off_time=hora, auto_off_enabled=True).auto_off_time == hora


@pytest.mark.parametrize(
    "hora",
    [
        "24:00",
        "23:60",
        "3:30",
        "0330",
        "03-30",
        "03:3",
        "ab:cd",
        "",
        " 03:30",
        "03:30 ",
        "99:99",
        "12:5a",
    ],
)
def test_rejeita_horario_invalido(hora):
    """A validação é estrita de propósito: um horário ambíguo viraria um
    desligamento no momento errado."""
    with pytest.raises(ValidationError):
        AutoShutdownUpdate(auto_off_time=hora, auto_off_enabled=True)
    with pytest.raises(ValidationError):
        ScheduleUpdate(auto_off_time=hora, auto_off_enabled=True)


# ------------------------------------------------------------------ Tarifa


@pytest.mark.parametrize("tarifa", [0, 0.01, 0.85, 1.0611, 100.0])
def test_tarifa_aceita_valores_nao_negativos(tarifa):
    assert TariffUpdate(kwh_rate=tarifa).kwh_rate == tarifa


@pytest.mark.parametrize("tarifa", [-0.01, -1, -1000])
def test_tarifa_rejeita_negativa(tarifa):
    """Tarifa negativa produziria custo negativo — absurdo."""
    with pytest.raises(ValidationError):
        TariffUpdate(kwh_rate=tarifa)


def test_tarifa_rejeita_texto():
    with pytest.raises(ValidationError):
        TariffUpdate(kwh_rate="abc")


# --------------------------------------------------------- TelemetryPayload


def test_telemetria_valida():
    p = TelemetryPayload(
        device_id="esp32_fan_01",
        is_on=True,
        voltage_rms=127.0,
        current_a=0.26,
        power_w=29.77,
        timestamp=23532.0,
    )
    assert p.device_id == "esp32_fan_01"
    assert p.power_w == pytest.approx(29.77)


def test_telemetria_exige_todos_os_campos():
    with pytest.raises(ValidationError):
        TelemetryPayload(device_id="esp32_fan_01", is_on=True)


def test_telemetria_rejeita_potencia_texto():
    with pytest.raises(ValidationError):
        TelemetryPayload(
            device_id="d",
            is_on=True,
            voltage_rms=127.0,
            current_a=0.26,
            power_w="muito",
            timestamp=1.0,
        )


def test_auto_shutdown_exige_booleano_real():
    """'true' (string) é truthy em Python, mas não é booleano válido.
    O tipo estrito do Pydantic evita gravar 'True' como texto no banco."""
    with pytest.raises(ValidationError):
        AutoShutdownUpdate(auto_off_time="03:30", auto_off_enabled="sim")
