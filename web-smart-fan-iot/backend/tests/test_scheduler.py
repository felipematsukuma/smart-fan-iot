"""Testes do agendador de desligamento automático.

Objetivo central: garantir que ele NUNCA desligue algo que não esteja ligado.
Era exatamente esse o risco quando `is_on` no Postgres podia ficar obsoleto.
"""
import types
from datetime import datetime, timedelta, timezone

import pytest

from app import scheduler as sched
from app.database import DB_ROWS, FakeDeviceRow
from app.mqtt_service import mqtt_manager

BRT = timezone(timedelta(hours=-3))


def run_at(iso: str):
    """Executa o agendador com o relógio congelado no instante informado."""
    target = datetime.fromisoformat(iso).replace(tzinfo=BRT)
    sched.datetime = types.SimpleNamespace(now=lambda tz=None: target)
    import asyncio
    return asyncio.run(sched.check_auto_turn_off())


@pytest.fixture
def at():
    def _at(iso):
        target = datetime.fromisoformat(iso).replace(tzinfo=BRT)
        sched.datetime = types.SimpleNamespace(now=lambda tz=None: target)
        import asyncio
        return asyncio.run(sched.check_auto_turn_off())
    return _at


def comandos(broker, sufixo="/command"):
    return [p for p in broker.published if p["topic"].endswith(sufixo)]


# ------------------------------------------------- desligamento na hora certa


def test_desliga_ventilador_ligado_no_horario(at, broker):
    DB_ROWS.append(FakeDeviceRow(is_on=True, at="03:30"))
    at("2026-09-29T03:30:10")
    c = comandos(broker)
    assert len(c) == 1
    assert c[0]["payload"] == {"action": "OFF"}
    assert DB_ROWS[0].is_on is True  # observed state awaits device confirmation


def test_nao_desliga_ventilador_ja_desligado(at, broker):
    """Cenário crítico: com o relé aberto não há nada a fazer. Enviar o comando
    seria um desligamento sem nexo com a realidade."""
    DB_ROWS.append(FakeDeviceRow(is_on=False, at="03:30"))
    at("2026-09-29T03:30:10")
    assert comandos(broker) == []
    assert DB_ROWS[0].is_on is False


def test_respeita_desligamento_automatico_desativado(at, broker):
    DB_ROWS.append(FakeDeviceRow(is_on=True, enabled=False, at="03:30"))
    at("2026-09-29T03:30:10")
    assert comandos(broker) == []
    assert DB_ROWS[0].is_on is True


def test_ignora_horario_diferente(at, broker):
    DB_ROWS.append(FakeDeviceRow(is_on=True, at="03:30"))
    at("2026-09-29T14:00:00")
    assert comandos(broker) == []


# ------------------------------------------------------------ idempotência


def test_retries_until_device_confirms_off(at, broker):
    DB_ROWS.append(FakeDeviceRow(is_on=True, at="03:30"))
    at("2026-09-29T03:30:05")
    assert len(comandos(broker)) == 1
    at("2026-09-29T03:30:35")
    assert len(comandos(broker)) == 2
    DB_ROWS[0].is_on = False
    at("2026-09-29T03:30:50")
    assert len(comandos(broker)) == 2


def test_horario_avaliado_no_fuso_do_servidor(at, broker):
    """O agendador casa HH:MM no fuso configurado, não em UTC. Um agendador em
    UTC desligaria 3 h fora do horário pedido pelo usuário."""
    DB_ROWS.append(FakeDeviceRow(is_on=True, at="00:00"))
    at("2026-09-29T00:00:10")            # 00:00 em BRT
    assert len(comandos(broker)) == 1


def test_meia_noite_e_tratada_como_inicio_do_dia(at, broker):
    DB_ROWS.append(FakeDeviceRow(is_on=True, at="00:00"))
    at("2026-09-29T23:59:50")
    assert comandos(broker) == []         # ainda não é 00:00
    at("2026-09-30T00:00:10")
    assert len(comandos(broker)) == 1


# ------------------------------------------- fragilidade da janela de tempo


def test_backend_ignora_minuto_se_passou(at, broker):
    """DOCUMENTA UMA FRAGILIDADE REAL, e não um comportamento desejado.

    O backend casa o minuto exato (`auto_off_time == "HH:MM"`), enquanto o
    firmware tem 2 min de tolerância. Se o backend reiniciar às 03:30:30, ele
    nunca mais título a hora 03:30 e o desligamento fica por conta só do
    firmware. Não é um desligamento INcoerente (o firmware cobre), mas o
    agendador do backend é frágil a reinício na janela.
    """
    DB_ROWS.append(FakeDeviceRow(is_on=True, at="03:30"))
    at("2026-09-29T03:31:05")            # a janela já passou
    assert comandos(broker) == []


# ------------------------------------------------------------- multi-device


def test_so_desliga_o_dispositivo_elegivel(at, broker):
    DB_ROWS.extend([
        FakeDeviceRow("esp32_fan_01", is_on=True, at="03:30"),
        FakeDeviceRow("esp32_fan_02", is_on=True, at="05:00"),
        FakeDeviceRow("esp32_fan_03", is_on=False, at="03:30"),
        FakeDeviceRow("esp32_fan_04", is_on=True, at="03:30", enabled=False),
    ])
    at("2026-09-29T03:30:10")
    alvos = [p["topic"].split("/")[1] for p in comandos(broker)]
    assert alvos == ["esp32_fan_01"]


def test_nenhum_dispositivo_nao_quebra(at, broker):
    at("2026-09-29T03:30:10")
    assert comandos(broker) == []


# ------------------------------------------------- segurança do desligamento


def test_broker_failure_preserves_observed_state(at, manager):
    manager._connected = False
    DB_ROWS.append(FakeDeviceRow(is_on=True, at="03:30"))
    at("2026-09-29T03:30:10")
    assert DB_ROWS[0].is_on is True


def test_agendador_nao_altera_outros_campos(at, broker):
    DB_ROWS.append(FakeDeviceRow(is_on=True, at="03:30", rate=1.25, enabled=True))
    at("2026-09-29T03:30:10")
    assert DB_ROWS[0].kwh_rate == 1.25
    assert DB_ROWS[0].auto_off_time == "03:30"
    assert DB_ROWS[0].auto_off_enabled is True


