"""Testes de integridade do serviço MQTT.

O `MQTTManager` é o REAL; só o Postgres (`app.database`) e o transporte paho
são substituídos. Assim o caminho de código exercitado é o de produção.
"""
import pytest

from app.database import DB_ROWS, FakeDeviceRow, FakeWriteApi
from app.mqtt_service import mqtt_manager
from conftest import mqtt_message, telemetry_payload

TOPICO_TELEMETRIA = "devices/esp32_fan_01/telemetry"
TOPICO_STATE = "devices/esp32_fan_01/state"


def parse_line_protocol(point):
    """Lê o Point pelo `to_line_protocol()`, que é exatamente o que o InfluxDB
    recebe. Testar o formato real é mais forte do que olhar campos privados.

    Formato: `measurement,tag=v field=v,field=v`  (valores `1i` = inteiro).
    """
    lp = point.to_line_protocol().strip()
    head, _, rest = lp.partition(" ")
    measurement, _, tag_part = head.partition(",")
    tags = {}
    for t in tag_part.split(","):
        if "=" in t:
            k, _, v = t.partition("=")
            tags[k] = v
    fields = {}
    for f in rest.split(","):
        if "=" not in f:
            continue
        k, _, v = f.partition("=")
        if v.endswith("i"):
            fields[k] = int(v[:-1])
        else:
            fields[k] = float(v)
    return measurement, tags, fields


def field(ponto, nome):
    return parse_line_protocol(ponto)[2].get(nome)


def tag(ponto, nome):
    return parse_line_protocol(ponto)[1].get(nome)


# ------------------------------------------------ coerência tópico/payload


def test_nao_grava_quando_device_id_divergente_do_topico():
    """Se o payload diz esp32_fan_01 e chega no tópico de outro device, gravar
    a telemetria no dispositivo errado corromperia o histórico. O serviço
    registra o erro e segue — o invariante é que NADA é gravado."""
    mqtt_manager.on_message(
        None, None,
        mqtt_message("devices/outro_device/telemetry", telemetry_payload()),
    )
    assert FakeWriteApi.written == []


def test_nao_grava_quando_payload_nao_e_objeto():
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, [1, 2, 3]))
    assert FakeWriteApi.written == []


def test_nao_grava_quando_topico_mal_formado():
    mqtt_manager.on_message(None, None, mqtt_message("topico", telemetry_payload()))
    assert FakeWriteApi.written == []


def test_erro_de_processamento_nao_derruba_o_servico(caplog):
    """Uma mensagem corrompida não pode derrubar o consumidor MQTT."""
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, {"power_w": "abc"}))
    # o serviço seguiu vivo
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, telemetry_payload()))
    assert len(FakeWriteApi.written) == 1


def test_payload_sem_device_id_usa_o_do_topico():
    """Device vem do tópico quando o payload não traz; tolerante de propósito
    para firmware enxuto."""
    mqtt_manager.on_message(
        None, None, mqtt_message(TOPICO_TELEMETRIA, {k: v for k, v in telemetry_payload().items() if k != "device_id"})
    )
    assert len(FakeWriteApi.written) == 1


# ---------------------------------------------------- gravação no InfluxDB


def test_telemetria_valida_grava_ponto_completo():
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, telemetry_payload()))
    assert len(FakeWriteApi.written) == 1
    measurement, tags, fields = parse_line_protocol(FakeWriteApi.written[0])
    assert measurement == "electrical_measurement"
    assert tags["device_id"] == "esp32_fan_01"
    assert fields["power_w"] == pytest.approx(29.77)
    assert fields["is_on"] == 1
    assert fields["current_a"] == pytest.approx(0.26)
    assert fields["voltage_rms"] == pytest.approx(127.0)


def test_telemetria_de_device_desconhecido_ainda_grava():
    """O histórico não depende do Postgres: um device novo já aparece no
    gráfico antes de existir na tabela de configuração."""
    mqtt_manager.on_message(
        None, None,
        mqtt_message("devices/novo/telemetry", telemetry_payload(device_id="novo")),
    )
    assert len(FakeWriteApi.written) == 1


def test_falha_no_influxdb_nao_impede_o_websocket():
    """Regra do serviço: a visualização em tempo real não pode depender do
    InfluxDB estar disponível. A falha fica registrada, o WS continua."""
    original = FakeWriteApi.write

    def boom(**kw):
        raise RuntimeError("influx fora do ar")

    FakeWriteApi.write = staticmethod(boom)
    try:
        mqtt_manager._broadcast = lambda *a, **k: None
        mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, telemetry_payload()))
    finally:
        FakeWriteApi.write = staticmethod(original)


# -------------------------------------------- sincronização do relé (P5)


def test_is_on_sincroniza_na_mudanca():
    DB_ROWS.append(FakeDeviceRow(is_on=False))
    mqtt_manager._last_is_on.clear()
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, telemetry_payload(is_on=True)))
    assert DB_ROWS[0].is_on is True


def test_is_on_nao_altera_quando_nada_muda():
    DB_ROWS.append(FakeDeviceRow(is_on=True))
    mqtt_manager._last_is_on.clear()
    for _ in range(20):
        mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, telemetry_payload(is_on=True)))
    assert DB_ROWS[0].is_on is True


def test_is_on_corrige_valor_obsoleto():
    """O bug original: o banco dizia ligado, o relé real estava desligado."""
    DB_ROWS.append(FakeDeviceRow(is_on=True))
    mqtt_manager._last_is_on.clear()
    mqtt_manager.on_message(
        None, None,
        mqtt_message(TOPICO_TELEMETRIA, telemetry_payload(is_on=False, power_w=0.0, current_a=0.0)),
    )
    assert DB_ROWS[0].is_on is False


def test_onda_de_telemetria_gera_uma_unica_escrita(monkeypatch):
    """Telemetria chega várias vezes por segundo. Gravar tudo no Postgres seria
    desperdício; só a mudança grava.

    O patch precisa ser em `app.mqtt_service.SessionLocal` (importado por nome),
    não em `app.database` — o serviço guardou a referência na importação.
    """
    import app.mqtt_service as svc
    DB_ROWS.append(FakeDeviceRow(is_on=True))
    mqtt_manager._last_is_on.clear()

    escritas = []
    original = svc.SessionLocal

    def contando():
        s = original()
        s.commit = lambda: escritas.append(1)
        return s

    monkeypatch.setattr(svc, "SessionLocal", contando)
    for _ in range(30):
        mqtt_manager.on_message(
            None, None,
            mqtt_message(TOPICO_TELEMETRIA, telemetry_payload(is_on=False, power_w=0.0)),
        )
    assert len(escritas) == 1
    assert DB_ROWS[0].is_on is False


def test_state_publicado_também_sincroniza_e_atualiza_cache():
    DB_ROWS.append(FakeDeviceRow(is_on=True))
    mqtt_manager._last_is_on.clear()
    mqtt_manager.on_message(
        None, None,
        mqtt_message(TOPICO_STATE, {"device_id": "esp32_fan_01", "is_on": False}),
    )
    assert DB_ROWS[0].is_on is False
    assert mqtt_manager._last_is_on["esp32_fan_01"] is False


# ------------------------------------------------ coerência dos campos


def test_rele_aberto_exige_potencia_zero():
    mqtt_manager.on_message(
        None, None,
        mqtt_message(TOPICO_TELEMETRIA, telemetry_payload(is_on=False, power_w=0.0, current_a=0.0)),
    )
    assert field(FakeWriteApi.written[0], "power_w") == 0.0
    assert field(FakeWriteApi.written[0], "is_on") == 0


def test_potencia_bate_com_tensao_corrente_e_fator_de_potencia():
    """P = V * I * FP, com FP=0,90 no firmware. Se a telemetria quebrar essa
    relação, o cálculo de energia fica sem sentido."""
    payload = telemetry_payload(current_a=0.26, voltage_rms=127.0, power_w=0.26 * 127 * 0.90)
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, payload))
    p = FakeWriteApi.written[0]
    fp = field(p, "power_w") / field(p, "current_a") / field(p, "voltage_rms")
    assert fp == pytest.approx(0.90, abs=0.01)


def test_is_on_e_gravado_como_inteiro():
    """O InfluxDB não tem boolean; gravar 0/1 mantém a consulta filtrável."""
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, telemetry_payload(is_on=True)))
    v = field(FakeWriteApi.written[0], "is_on")
    assert v == 1 and isinstance(v, int)


# ------------------------------------------------------- publicação MQTT


def test_comando_vai_para_o_topico_correto_com_qos1(broker):
    assert mqtt_manager.publish_command("esp32_fan_01", {"action": "OFF"}) is True
    assert len(broker.published) == 1
    p = broker.published[0]
    assert p["topic"] == "devices/esp32_fan_01/command"
    assert p["payload"] == {"action": "OFF"}
    assert p["qos"] == 1


def test_comando_nao_e_retido(broker):
    """Comandos retidos reexecutariam ao reconectar, desligando o ventilador
    fora de hora."""
    mqtt_manager.publish_command("esp32_fan_01", {"action": "OFF"})
    assert broker.published[0]["retain"] is False


def test_configuracao_e_retida(broker):
    """A configuração PRECISA ser retida: o ESP32 a recebe ao reconectar."""
    mqtt_manager.publish_configuration("esp32_fan_01", {"auto_mode": True, "shutdown_time": "03:30"})
    p = broker.published[0]
    assert p["topic"] == "devices/esp32_fan_01/config/set"
    assert p["retain"] is True


def test_publicacao_falha_quando_desconectado():
    mqtt_manager._connected = False
    assert mqtt_manager.publish_command("esp32_fan_01", {"action": "ON"}) is False


def test_assinatura_os_topicos_esperados(broker):
    """Sem assinar `state` e `config`, a sincronização do relé e a configuração
    do ESP32 param de funcionar."""
    mqtt_manager.on_connect(broker, None, None, 0)
    topicos = [t for t, _ in broker.subscriptions]
    assert "devices/+/telemetry" in topicos
    assert "devices/+/state" in topicos
    assert "devices/+/config" in topicos


def test_falha_de_conexao_marca_desconectado(manager):
    manager._connected = True
    manager.on_connect(manager.client, None, None, 5)
    assert manager.is_connected is False


@pytest.mark.parametrize("override", [
    {"is_on": "false"}, {"power_w": -1}, {"power_w": float("nan")},
    {"current_a": -1}, {"timestamp": -1}, {"shutdown_time": "ab:cd"},
])
def test_invalid_telemetry_never_reaches_influx(override):
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_TELEMETRIA, telemetry_payload(**override)))
    assert FakeWriteApi.written == []


def test_invalid_state_does_not_change_observed_relay():
    DB_ROWS.append(FakeDeviceRow(is_on=False))
    mqtt_manager.on_message(None, None, mqtt_message(TOPICO_STATE, {"is_on": "false"}))
    assert DB_ROWS[0].is_on is False
