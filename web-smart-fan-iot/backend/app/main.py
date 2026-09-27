import asyncio
import math
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db, query_api
from app.models import Device
from app.mqtt_service import mqtt_manager
from app.scheduler import scheduler, start_scheduler
from app.schemas import DeviceCommand, ScheduleUpdate

DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_ENERGY_SAMPLE_GAP_SECONDS = 10
MAX_ANALYSIS_HOURS = 168
MAX_HISTORY_POINTS = 120

Base.metadata.create_all(bind=engine)


def validate_device_id(device_id: str) -> str:
    if not DEVICE_ID_PATTERN.fullmatch(device_id):
        raise HTTPException(status_code=422, detail="device_id inválido")
    return device_id


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(settings.APP_TIMEZONE))
    return value.astimezone(timezone.utc)


def _flux_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _downsample_samples(
    samples: list[tuple[datetime, float]],
    max_points: int = MAX_HISTORY_POINTS,
) -> list[tuple[datetime, float]]:
    if len(samples) <= max_points:
        return samples

    last_index = len(samples) - 1
    return [
        samples[round(index * last_index / (max_points - 1))]
        for index in range(max_points)
    ]


def ensure_default_device() -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.device_id == "esp32_fan_01").first()
        if not device:
            device = Device(
                device_id="esp32_fan_01",
                name="Ventilador Quarto",
                auto_off_time="03:00",
                auto_off_enabled=True,
            )
            db.add(device)
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_default_device()
    mqtt_manager.set_event_loop(asyncio.get_running_loop())
    mqtt_manager.start()
    start_scheduler()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        mqtt_manager.stop()


app = FastAPI(title="Smart Fan IoT API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mqtt_connected": mqtt_manager.is_connected,
    }


@app.get("/api/device/{device_id}")
def get_device(device_id: str, db: Session = Depends(get_db)):
    validate_device_id(device_id)
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@app.post("/api/device/{device_id}/command")
def send_command(
    device_id: str,
    cmd: DeviceCommand,
    db: Session = Depends(get_db),
) -> dict:
    validate_device_id(device_id)
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    command = cmd.model_dump()
    if not mqtt_manager.publish_command(device_id, command):
        raise HTTPException(status_code=503, detail="Broker MQTT indisponível")

    return {
        "status": "published",
        "device_id": device_id,
        "command": command,
    }


@app.put("/api/device/{device_id}/schedule")
def update_schedule(
    device_id: str,
    sched: ScheduleUpdate,
    db: Session = Depends(get_db),
) -> dict:
    validate_device_id(device_id)
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    configuration = {
        "auto_mode": sched.auto_off_enabled,
        "shutdown_time": sched.auto_off_time,
    }
    if not mqtt_manager.publish_configuration(device_id, configuration):
        db.rollback()
        raise HTTPException(status_code=503, detail="Broker MQTT indisponível")

    device.auto_off_time = sched.auto_off_time
    device.auto_off_enabled = sched.auto_off_enabled
    device.kwh_rate = sched.kwh_rate
    db.commit()

    return {
        "status": "updated",
        "device_id": device.device_id,
        "configuration_published": configuration,
    }


def _iter_power_samples(result) -> Iterator[tuple[datetime, float]]:
    for table in result:
        for record in table.records:
            value = record.get_value()
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                continue
            timestamp = record.get_time()
            if timestamp is not None:
                yield timestamp, float(value)


@app.get("/api/device/{device_id}/metrics")
def get_metrics(
    device_id: str,
    range_hours: int = Query(default=8, ge=1, le=MAX_ANALYSIS_HOURS),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> dict:
    validate_device_id(device_id)

    if start is None and end is None:
        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(hours=range_hours)
        range_clause = f"range(start: -{range_hours}h)"
    else:
        if start is None or end is None:
            raise HTTPException(
                status_code=422,
                detail="Informe start e end together para analisar um período",
            )

        period_start = _to_utc(start)
        period_end = _to_utc(end)
        if period_start >= period_end:
            raise HTTPException(
                status_code=422,
                detail="O início do período deve ser anterior ao fim",
            )

        duration_hours = (period_end - period_start).total_seconds() / 3600
        if duration_hours > MAX_ANALYSIS_HOURS:
            raise HTTPException(
                status_code=422,
                detail=f"O período não pode exceder {MAX_ANALYSIS_HOURS} horas",
            )

        range_clause = (
            f'range(start: time(v: "{_flux_datetime(period_start)}"), '
            f'stop: time(v: "{_flux_datetime(period_end)}"))'
        )

    query = f'''
    from(bucket: "{settings.INFLUXDB_BUCKET}")
      |> {range_clause}
      |> filter(fn: (r) => r["_measurement"] == "electrical_measurement")
      |> filter(fn: (r) => r["device_id"] == "{device_id}")
      |> filter(fn: (r) => r["_field"] == "power_w")
    '''

    samples = sorted(_iter_power_samples(query_api.query(
        org=settings.INFLUXDB_ORG,
        query=query,
    )))

    total_samples = len(samples)
    sum_power = sum(power for _, power in samples)
    avg_power_w = (sum_power / total_samples) if total_samples else 0.0

    energy_wh = 0.0
    for (previous_time, previous_power), (current_time, current_power) in zip(
        samples,
        samples[1:],
    ):
        gap_seconds = (current_time - previous_time).total_seconds()
        if 0 < gap_seconds <= MAX_ENERGY_SAMPLE_GAP_SECONDS:
            average_interval_power = (previous_power + current_power) / 2
            energy_wh += average_interval_power * gap_seconds / 3600

    history = [
        {"time": timestamp.isoformat(), "power_w": round(power, 2)}
        for timestamp, power in _downsample_samples(samples)
    ]
    duration_hours = (period_end - period_start).total_seconds() / 3600

    return {
        "device_id": device_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "duration_hours": round(duration_hours, 3),
        "avg_power_w": round(avg_power_w, 2),
        "energy_wh": round(energy_wh, 3),
        "estimated_kwh": round(energy_wh / 1000, 6),
        "history_count": total_samples,
        "history": history,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    mqtt_manager.active_websockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        mqtt_manager.active_websockets.discard(websocket)
