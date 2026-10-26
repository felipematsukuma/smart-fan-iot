import asyncio
import json
import logging
import os
from typing import Any

import paho.mqtt.client as mqtt
from influxdb_client import Point

from app.config import settings
from app.database import SessionLocal, write_api
from app.models import Device

logger = logging.getLogger("MQTT_SERVICE")


class MQTTManager:
    def __init__(self):
        self.client = mqtt.Client(
            client_id=f"fastapi_backend_{os.getpid()}",
            clean_session=True,
        )
        self.client.reconnect_delay_set(min_delay=1, max_delay=5)
        self.active_websockets: set[Any] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._connected = False
        self._started = False
        # Último `is_on` conhecido por dispositivo, para não gravar no Postgres
        # a cada mensagem de telemetria (que chega várias vezes por segundo).
        self._last_is_on: dict[str, bool] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected and self.client.is_connected()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            self._connected = False
            logger.error("Erro ao conectar no broker MQTT. Código: %s", rc)
            return

        self._connected = True
        logger.info("FastAPI conectado ao broker Mosquitto")
        client.subscribe("devices/+/telemetry", qos=1)
        client.subscribe("devices/+/state", qos=1)
        client.subscribe("devices/+/config", qos=1)
        self._publish_stored_configurations()

    def on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("Conexão MQTT interrompida. Código: %s", rc)

    def on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload MQTT deve ser um objeto JSON")

            topic_parts = msg.topic.split("/")
            topic_device_id = topic_parts[1] if len(topic_parts) >= 3 else None
            payload_device_id = payload.get("device_id")

            if not topic_device_id or (
                payload_device_id and payload_device_id != topic_device_id
            ):
                raise ValueError(f"device_id incoerente no tópico {msg.topic}")

            if msg.topic.endswith("/telemetry"):
                self._handle_telemetry(topic_device_id, payload)
            elif msg.topic.endswith("/state"):
                self._sync_device(topic_device_id, payload)
                self._broadcast(payload, event="state")
            elif msg.topic.endswith("/config"):
                self._sync_device(topic_device_id, payload)
                self._broadcast(payload, event="config")
            else:
                logger.warning("Tópico MQTT não tratado: %s", msg.topic)
        except Exception:
            logger.exception("Erro ao processar mensagem MQTT em %s", msg.topic)

    def _handle_telemetry(self, device_id: str, payload: dict[str, Any]) -> None:
        is_on = bool(payload.get("is_on", False))
        current_a = float(payload.get("current_a", 0.0))
        power_w = float(payload.get("power_w", 0.0))
        voltage_rms = float(payload.get("voltage_rms", 127.0))

        point = (
            Point("electrical_measurement")
            .tag("device_id", device_id)
            .field("is_on", int(is_on))
            .field("current_a", current_a)
            .field("power_w", power_w)
            .field("voltage_rms", voltage_rms)
        )

        try:
            write_api.write(
                bucket=settings.INFLUXDB_BUCKET,
                org=settings.INFLUXDB_ORG,
                record=point,
            )
        except Exception:
            # A visualização em tempo real não deve depender da disponibilidade
            # do InfluxDB. A falha fica registrada e a telemetria segue via WS.
            logger.exception("Falha ao gravar telemetria de %s no InfluxDB", device_id)

        self._broadcast(payload, event="telemetry")
        # O estado real do relé chega em toda telemetria. Sincronizar aqui evita
        # que o Postgres conserve um `is_on` obsoleto: o agendador de desligamento
        # automático decide com base nesse campo, e um valor velho pode desligar
        # (ou deixar ligado) um ventilador que não está no estado registrado.
        self._sync_is_on(device_id, is_on)

    def _sync_is_on(self, device_id: str, is_on: bool) -> None:
        """Persiste `is_on` apenas quando o valor realmente muda."""
        cached = self._last_is_on.get(device_id)
        if cached is not None and cached == is_on:
            return
        self.set_device_is_on(device_id, is_on)

    def set_device_is_on(self, device_id: str, is_on: bool) -> None:
        """Única porta de escrita de `is_on`.

        Atualiza o banco e o cache local juntos. Passar por aqui é obrigatório:
        se um escritor gravasse só o banco, o cache ficaria divergente e a
        sincronização por telemetria passaria a ignorar o valor novo — voltando
        a persistir um estado obsoleto, que é a origem do desligamento incoerente.
        """
        db = SessionLocal()
        try:
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if device is not None and device.is_on != is_on:
                device.is_on = is_on
                db.commit()
            self._last_is_on[device_id] = is_on
        except Exception:
            db.rollback()
            logger.exception("Falha ao sincronizar is_on de %s", device_id)
        finally:
            db.close()

    def _sync_device(self, device_id: str, payload: dict[str, Any]) -> None:
        db = SessionLocal()
        try:
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if not device:
                logger.warning("Estado recebido para dispositivo inexistente: %s", device_id)
                return

            if "is_on" in payload:
                device.is_on = bool(payload["is_on"])
                self._last_is_on[device_id] = device.is_on
            if "auto_mode" in payload:
                device.auto_off_enabled = bool(payload["auto_mode"])
            if "shutdown_time" in payload:
                device.auto_off_time = str(payload["shutdown_time"])

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _publish_stored_configurations(self) -> None:
        db = SessionLocal()
        try:
            devices = db.query(Device).all()
            for device in devices:
                if device.auto_off_time:
                    self.publish_configuration(
                        device.device_id,
                        {
                            "auto_mode": device.auto_off_enabled,
                            "shutdown_time": device.auto_off_time,
                        },
                        wait_for_ack=False,
                    )
        except Exception:
            logger.exception("Falha ao publicar configurações armazenadas")
        finally:
            db.close()

    def _broadcast(self, data: dict[str, Any], event: str) -> None:
        if not self.loop or not self.active_websockets or self.loop.is_closed():
            return

        message = {**data, "event": event}
        asyncio.run_coroutine_threadsafe(self.broadcast_ws(message), self.loop)

    async def broadcast_ws(self, data: dict[str, Any]) -> None:
        dead_sockets = set()
        for websocket in tuple(self.active_websockets):
            try:
                await websocket.send_json(data)
            except Exception:
                dead_sockets.add(websocket)
        self.active_websockets.difference_update(dead_sockets)

    def publish_command(
        self,
        device_id: str,
        command: dict[str, Any],
        retained: bool = False,
    ) -> bool:
        topic = f"devices/{device_id}/command"
        return self._publish(topic, command, retained=retained)

    def publish_configuration(
        self,
        device_id: str,
        configuration: dict[str, Any],
        wait_for_ack: bool = True,
    ) -> bool:
        topic = f"devices/{device_id}/config/set"
        return self._publish(
            topic,
            configuration,
            retained=True,
            wait_for_ack=wait_for_ack,
        )

    def _publish(
        self,
        topic: str,
        payload: dict[str, Any],
        retained: bool,
        wait_for_ack: bool = True,
    ) -> bool:
        if not self.is_connected:
            logger.error("Não foi possível publicar em %s: MQTT desconectado", topic)
            return False

        try:
            info = self.client.publish(
                topic,
                json.dumps(payload),
                qos=1,
                retain=retained,
            )
            if wait_for_ack:
                info.wait_for_publish(timeout=2.0)
                if not info.is_published():
                    logger.error(
                        "Publicação MQTT não confirmada em %s: rc=%s",
                        topic,
                        info.rc,
                    )
                    return False
            elif info.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error("Publicação MQTT rejeitada em %s: rc=%s", topic, info.rc)
                return False
            logger.info("Comando publicado em %s: %s", topic, payload)
            return True
        except Exception:
            logger.exception("Falha ao publicar em %s", topic)
            return False

    def start(self) -> None:
        if self._started:
            return

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self._started = True

        try:
            self.client.connect_async(settings.MQTT_BROKER, settings.MQTT_PORT, 60)
            self.client.loop_start()
        except Exception:
            self._started = False
            logger.exception("Não foi possível iniciar o cliente MQTT")

    def stop(self) -> None:
        if not self._started:
            return
        self.client.disconnect()
        self.client.loop_stop()
        self._connected = False
        self._started = False


mqtt_manager = MQTTManager()
