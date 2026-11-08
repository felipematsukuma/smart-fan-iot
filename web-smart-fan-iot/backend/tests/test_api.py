"""Testes de integridade da API (rotas e regras de negócio).

Roda contra a aplicação FastAPI real com o banco substituído, então as
validações exercitadas são as de produção.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import DB_ROWS, FakeDeviceRow, FakeSession
from app.main import (
    MAX_ANALYSIS_HOURS,
    MAX_ENERGY_SAMPLE_GAP_SECONDS,
    MAX_HISTORY_POINTS,
    app,
)

DEVICE = "esp32_fan_01"


@pytest.fixture
def client(manager):
    """Cliente HTTP com o banco em memória e o transporte MQTT falso.

    `get_db` é resolvido na importação do módulo, então a troca precisa ser
    feita por `dependency_overrides` — monkeypatch na função não surtiria efeito.
    """
    from conftest import FakePahoClient

    from app.database import get_db
    from app.mqtt_service import mqtt_manager

    DB_ROWS.append(FakeDeviceRow(device_id=DEVICE, is_on=True, at="03:30", rate=0.85))

    broker = FakePahoClient()
    mqtt_manager.client = broker
    mqtt_manager._connected = True

    def fake_get_db():
        return FakeSession(DB_ROWS)

    app.dependency_overrides[get_db] = fake_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        mqtt_manager.client = None
        mqtt_manager._connected = False


def _sem_influx(monkeypatch):
    """Faz /metrics devolver vazio, sem tocar no InfluxDB real."""
    from app import main as main_mod

    class _Api:
        def query(self, **kw):
            return []

    monkeypatch.setattr(main_mod, "query_api", _Api())


# ----------------------------------------------------------------- health


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "mqtt_connected" in r.json()


# ----------------------------------------------------------------- device


def test_get_device(client):
    r = client.get(f"/api/device/{DEVICE}")
    assert r.status_code == 200
    assert r.json()["device_id"] == DEVICE


def test_get_device_inexistente(client):
    assert client.get("/api/device/nao_existe").status_code == 404


@pytest.mark.parametrize(
    "device_id",
    [
        "device com espaco",
        "device/../etc",
        "a" * 65,
        "device@host",
    ],
)
def test_device_id_invalido(client, device_id):
    assert client.get(f"/api/device/{device_id}").status_code in (404, 422)


# ---------------------------------------------------------------- comando


def test_comando_publica_no_mqtt(client):
    r = client.post(f"/api/device/{DEVICE}/command", json={"action": "ON"})
    assert r.status_code == 200
    assert r.json()["status"] == "published"


def test_comando_normaliza_caixa(client):
    assert client.post(f"/api/device/{DEVICE}/command", json={"action": "on"}).status_code == 200


def test_comando_invalido_recusado(client):
    assert client.post(f"/api/device/{DEVICE}/command", json={"action": "TURBO"}).status_code == 422


def test_comando_sem_action_recusado(client):
    assert client.post(f"/api/device/{DEVICE}/command", json={}).status_code == 422


def test_comando_de_device_inexistente(client):
    assert client.post("/api/device/outro/command", json={"action": "ON"}).status_code == 404


# ------------------------------------------------- tarifa e desligamento


def test_tarifa_atualizada(client):
    r = client.put(f"/api/device/{DEVICE}/tariff", json={"kwh_rate": 1.25})
    assert r.status_code == 200
    assert r.json()["kwh_rate"] == 1.25


def test_tarifa_negativa_recusada(client):
    assert client.put(f"/api/device/{DEVICE}/tariff", json={"kwh_rate": -1}).status_code == 422


def test_auto_shutdown_atualizado(client):
    r = client.put(
        f"/api/device/{DEVICE}/auto-shutdown",
        json={"auto_off_time": "05:45", "auto_off_enabled": False},
    )
    assert r.status_code == 200
    assert DB_ROWS[0].auto_off_time == "05:45"
    assert DB_ROWS[0].auto_off_enabled is False


def test_auto_shutdown_hora_invalida_recusada(client):
    r = client.put(
        f"/api/device/{DEVICE}/auto-shutdown",
        json={"auto_off_time": "25:00", "auto_off_enabled": True},
    )
    assert r.status_code == 422


def test_tarifa_e_agendamento_sao_independentes(client):
    """Salvar a tarifa não pode mexer no horário, e vice-versa: são configurações
    distintas com endpoints distintos."""
    client.put(
        f"/api/device/{DEVICE}/auto-shutdown",
        json={"auto_off_time": "05:45", "auto_off_enabled": False},
    )
    client.put(f"/api/device/{DEVICE}/tariff", json={"kwh_rate": 2.5})
    assert DB_ROWS[0].auto_off_time == "05:45"
    assert DB_ROWS[0].auto_off_enabled is False
    assert DB_ROWS[0].kwh_rate == 2.5


# ----------------------------------------------------------------- métricas


def test_metricas_sem_parametros(client, monkeypatch):
    _sem_influx(monkeypatch)
    r = client.get(f"/api/device/{DEVICE}/metrics")
    assert r.status_code == 200
    corpo = r.json()
    for chave in (
        "device_id",
        "period_start",
        "period_end",
        "duration_hours",
        "avg_power_w",
        "energy_wh",
        "estimated_kwh",
        "history_count",
        "history",
    ):
        assert chave in corpo, f"faltou {chave}"
    assert corpo["energy_wh"] == 0.0
    assert corpo["history"] == []


@pytest.mark.parametrize(
    "q,esperado",
    [
        ("range_hours=0", 422),
        ("range_hours=169", 422),
        ("range_hours=168", 200),
        ("start=2026-09-28T10:00:00Z", 422),  # só start
        ("end=2026-09-28T10:00:00Z", 422),  # só end
        ("start=2026-09-28T10:00:00Z&end=2026-09-28T09:00:00Z", 422),  # invertido
        ("start=2026-09-28T10:00:00Z&end=2026-09-28T10:00:00Z", 422),  # vazio
        ("start=2026-09-01T00:00:00Z&end=2026-09-28T00:00:00Z", 422),  # > 168h
    ],
)
def test_metricas_validacao_de_periodo(client, monkeypatch, q, esperado):
    _sem_influx(monkeypatch)
    assert client.get(f"/api/device/{DEVICE}/metrics?{q}").status_code == esperado


def test_metricas_aceita_janela_valida(client, monkeypatch):
    _sem_influx(monkeypatch)
    r = client.get(
        f"/api/device/{DEVICE}/metrics?start=2026-09-28T00:00:00Z&end=2026-09-28T12:00:00Z"
    )
    assert r.status_code == 200
    assert r.json()["duration_hours"] == 12.0


def test_metricas_aceita_start_sem_fuso(client, monkeypatch):
    """Sem fuso, o start é interpretado no fuso da aplicação."""
    _sem_influx(monkeypatch)
    r = client.get(
        f"/api/device/{DEVICE}/metrics?start=2026-09-28T00:00:00&end=2026-09-28T12:00:00"
    )
    assert r.status_code == 200


def test_metricas_de_device_inexistente_nao_quebra(client, monkeypatch):
    """Consulta de um device sem cadastro devolve vazio, não 404: é uma
    pergunta sobre série de tempo, não sobre recurso cadastrado."""
    _sem_influx(monkeypatch)
    r = client.get("/api/device/nao_cadastrado/metrics")
    assert r.status_code == 200
    assert r.json()["history_count"] == 0


# ---------------------------------------------------------------- constantes


def test_limites_de_negocio():
    assert MAX_ANALYSIS_HOURS == 168  # 7 dias
    # O teto precisa cobrir 2 pontos por trecho de atividade. Medindo a janela
    # de 7 dias deste projeto: 35 trechos desligados + 58 com consumo = 93, e
    # 93 x 2 = 186. Com 120 era impossível cobrir tudo, e o gráfico virava uma
    # parede de espinhos de 1 px.
    assert MAX_HISTORY_POINTS >= 186
    assert 68.4 < MAX_ENERGY_SAMPLE_GAP_SECONDS < 91.1


def test_lists_registered_devices(client):
    response = client.get("/api/devices")
    assert response.status_code == 200
    assert response.json()[0]["device_id"] == DEVICE


def test_registration_rejects_duplicate_and_invalid_identity(client):
    assert client.post("/api/devices", json={"device_id": DEVICE, "name": "Fan"}).status_code == 409
    assert (
        client.post("/api/devices", json={"device_id": "bad/id", "name": "Fan"}).status_code == 422
    )
    assert (
        client.post("/api/devices", json={"device_id": "second", "name": "Fan"}).status_code == 201
    )


def test_history_failure_is_explicit(client, monkeypatch):
    from app import main

    def unavailable(**kwargs):
        raise OSError("influx unavailable")

    monkeypatch.setattr(main.query_api, "query", unavailable)
    assert client.get(f"/api/device/{DEVICE}/metrics").status_code == 503


def test_untrusted_web_origin_cannot_read_api(client):
    response = client.get("/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in response.headers
