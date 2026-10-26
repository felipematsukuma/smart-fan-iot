"""Fixtures compartilhadas.

Estratégia: substituímos APENAS as fronteiras de I/O (Postgres, InfluxDB) e
deixamos `app.mqtt_service` e `app.scheduler` reais. Stubbar o módulo inteiro
seria mais fácil, mas então os testes não exercitariam a lógica de verdade —
o erro mais comum em suítes que "passam" sem testar nada.
"""

import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

published_commands = []
published_configs = []


# ------------------------------------------------------- fakes de I/O (banco)


class FakeColumn:
    """Coluna SQLAlchemy falsa: `is_()`, `==` e `in_()` devolvem predicados
    que o FakeQuery sabe aplicar de verdade."""

    def __init__(self, name):
        self.name = name

    def is_(self, value):
        return lambda row: getattr(row, self.name) is value

    def __eq__(self, value):
        return lambda row: getattr(row, self.name) == value

    def in_(self, values):
        return lambda row: getattr(row, self.name) in values

    def __hash__(self):
        return hash(self.name)


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self.predicates = []

    def filter(self, *preds):
        self.predicates.extend(preds)
        return self

    def _apply(self):
        rows = self.rows
        for p in self.predicates:
            rows = [r for r in rows if p(r)]
        return rows

    def first(self):
        rows = self._apply()
        return rows[0] if rows else None

    def all(self):
        return self._apply()


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        return FakeQuery(self.rows)

    def add(self, obj):
        self.added.append(obj)
        self.rows.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


class FakeDeviceRow:
    def __init__(self, device_id="esp32_fan_01", is_on=False, enabled=True, at="03:30", rate=0.85):
        self.id = 1
        self.device_id = device_id
        self.name = "Ventilador Quarto"
        self.is_on = is_on
        self.kwh_rate = rate
        self.auto_off_time = at
        self.auto_off_enabled = enabled


DB_ROWS = []


def fake_session_local():
    return FakeSession(DB_ROWS)


class FakePoint:
    """Dublê do Point do InfluxDB, com os acessos que o serviço usa."""

    def __init__(self, measurement, tags=None, fields=None):
        self._measurement = measurement
        self._tags = tags or {}
        self._fields = fields or {}

    def get_measurement(self):
        return self._measurement

    def get_field(self, name):
        return self._fields.get(name)

    def get_tag(self, name):
        return self._tags.get(name)


class FakeWriteApi:
    written = []

    @staticmethod
    def write(bucket=None, org=None, record=None, **kw):
        FakeWriteApi.written.append(record)


_fake_db = types.ModuleType("app.database")
_fake_db.SessionLocal = fake_session_local
_fake_db.write_api = FakeWriteApi
_fake_db.query_api = types.SimpleNamespace(query=lambda **kw: [])


class FakeMetaData:
    """`Base.metadata.create_all(...)` roda na importação de app.main; aqui é
    um no-op, porque o schema real é criado pelo Postgres do compose."""

    def __init__(self):
        self.criadas = 0

    def create_all(self, **kwargs):
        self.criadas += 1


class FakeBase:
    metadata = FakeMetaData()


_fake_db.Base = FakeBase
_fake_db.FakeBase = FakeBase
_fake_db.engine = object()
_fake_db.get_db = lambda: iter([FakeSession(DB_ROWS)])
_fake_db.DB_ROWS = DB_ROWS
_fake_db.FakeSession = FakeSession
_fake_db.FakeQuery = FakeQuery
_fake_db.FakeDeviceRow = FakeDeviceRow
_fake_db.FakeColumn = FakeColumn
_fake_db.FakePoint = FakePoint
_fake_db.FakeWriteApi = FakeWriteApi
sys.modules["app.database"] = _fake_db


# ---------------------------------------------------------- app.models real
# O Device é usado como "tabela" pelos dublês; basta ter as colunas do schema.

_fake_models = types.ModuleType("app.models")


class Device:
    device_id = FakeColumn("device_id")
    is_on = FakeColumn("is_on")
    auto_off_enabled = FakeColumn("auto_off_enabled")
    auto_off_time = FakeColumn("auto_off_time")
    kwh_rate = FakeColumn("kwh_rate")
    name = FakeColumn("name")
    id = FakeColumn("id")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


_fake_models.Device = Device
_fake_models.FakeDeviceRow = FakeDeviceRow
sys.modules["app.models"] = _fake_models


# ------------------------------------------- cliente paho falso (transporte)


class FakePahoInfo:
    def __init__(self, rc: int):
        self.rc = rc

    def wait_for_publish(self, timeout=None):
        return True

    def is_published(self):
        return True


class FakePahoClient:
    """Transporte MQTT falso. Mantemos o `MQTTManager` real, então o caminho de
    publicação (tópico, qos, retain, checagem de erro) é de verdade exercitado;
    só a rede é substituída."""

    def __init__(self, rc: int = 0):
        self.rc = rc
        self.published = []
        self.subscriptions = []
        self.is_connected = lambda: True

    def publish(self, topic, payload, qos=0, retain=False):
        import json

        self.published.append(
            {
                "topic": topic,
                "payload": json.loads(payload) if isinstance(payload, str) else payload,
                "qos": qos,
                "retain": retain,
            }
        )
        return FakePahoInfo(self.rc)

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))
        return (0, 0)

    def connect(self, *a, **k):
        return 0

    def connect_async(self, *a, **k):
        return None

    def reconnect_delay_set(self, *a, **k):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def loop_forever(self):
        pass

    def on_connect(self, *a, **k):
        pass

    def on_disconnect(self, *a, **k):
        pass

    def on_message(self, *a, **k):
        pass

    def disconnect(self):
        pass


@pytest.fixture
def broker(manager):
    """Instala um cliente MQTT falso e marca o gerenciador como conectado."""
    client = FakePahoClient()
    manager.client = client
    manager._connected = True
    yield client
    manager.client = None
    manager._connected = False


# ------------------------------------------------------------------ helpers

BRT = timezone(timedelta(hours=-3))


def at_brt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=BRT)


def telemetry_payload(**over):
    base = dict(
        device_id="esp32_fan_01",
        is_on=True,
        auto_mode=True,
        shutdown_time="03:30",
        voltage_rms=127.0,
        current_a=0.26,
        power_w=29.77,
        total_energy_wh=1.5,
        fan_on_time_ms=18061,
        timestamp=23532,
    )
    base.update(over)
    return base


def mqtt_message(topic: str, payload) -> object:
    """Mensagem MQTT falsa com o payload já serializado, como o broker faria."""
    import json

    class _Msg:
        def __init__(self, topic, payload):
            self.topic = topic
            self.payload = json.dumps(payload).encode("utf-8")

    return _Msg(topic, payload)


@pytest.fixture(autouse=True)
def clean_state():
    published_commands.clear()
    published_configs.clear()
    FakeWriteApi.written.clear()
    DB_ROWS.clear()
    from app.mqtt_service import mqtt_manager

    mqtt_manager._last_is_on.clear()
    yield
    published_commands.clear()
    published_configs.clear()
    FakeWriteApi.written.clear()
    DB_ROWS.clear()
    mqtt_manager._last_is_on.clear()


@pytest.fixture
def manager():
    from app.mqtt_service import mqtt_manager

    return mqtt_manager
