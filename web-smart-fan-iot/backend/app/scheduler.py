import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import SessionLocal
from app.models import Device
from app.mqtt_service import mqtt_manager

logger = logging.getLogger("SCHEDULER")
app_timezone = ZoneInfo(settings.APP_TIMEZONE)
scheduler = AsyncIOScheduler(timezone=app_timezone)


async def check_auto_turn_off() -> None:
    """Request OFF while due and still observed ON; never invent a relay state.

    A broker PUBACK is not an actuator acknowledgement. Retry every 30 seconds
    in the due minute until telemetry/state confirms OFF.
    """
    now_str = datetime.now(app_timezone).strftime("%H:%M")
    db = SessionLocal()
    try:
        devices = (
            db.query(Device)
            .filter(
                Device.auto_off_enabled.is_(True),
                Device.auto_off_time == now_str,
                Device.is_on.is_(True),
            )
            .all()
        )

        # `is_on` reflete a telemetria atual (ver mqtt_service._sync_is_on),
        # então o comando só sai quando o ventilador está realmente ligado.
        to_turn_off = [device.device_id for device in devices]

        for device_id in to_turn_off:
            logger.info(
                "Horário atingido (%s)! Enviando OFF para %s",
                now_str,
                device_id,
            )
            if not mqtt_manager.publish_command(device_id, {"action": "OFF"}):
                logger.warning("OFF pending for %s: broker unavailable", device_id)

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Erro no scheduler")
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        check_auto_turn_off,
        "interval",
        seconds=30,
        id="check_auto_turn_off",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
