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
    """Desliga devices no horário local configurado, com precisão de 30 s.

    O comando é idempotente por natureza: o ESP32 também se desliga sozinho no
    horário (main.cpp) e publica `state`, de modo que as duas rotas convergem.
    Aqui o objetivo é garantir o desligamento mesmo se a configuração do
    dispositivo tiver divergido do NVS, e marcar `is_on = False` para não
    repetir o comando a cada 30 s.
    """
    now_str = datetime.now(app_timezone).strftime("%H:%M")
    db = SessionLocal()
    try:
        devices = db.query(Device).filter(
            Device.auto_off_enabled.is_(True),
            Device.auto_off_time == now_str,
            Device.is_on.is_(True),
        ).all()

        # `is_on` reflete a telemetria atual (ver mqtt_service._sync_is_on),
        # então o comando só sai quando o ventilador está realmente ligado.
        to_turn_off = [device.device_id for device in devices]

        for device_id in to_turn_off:
            logger.info(
                "Horário atingido (%s)! Enviando OFF para %s",
                now_str,
                device_id,
            )
            mqtt_manager.publish_command(device_id, {"action": "OFF"})
            # Escrita pelo gerenciador para manter banco e cache coerentes.
            mqtt_manager.set_device_is_on(device_id, False)

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
