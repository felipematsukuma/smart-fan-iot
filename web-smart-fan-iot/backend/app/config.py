from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL
    POSTGRES_USER: str = "iot_user"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "smart_fan_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # InfluxDB
    INFLUXDB_URL: str = "http://influxdb:8086"
    INFLUXDB_TOKEN: str
    INFLUXDB_ORG: str = "iot_org"
    INFLUXDB_BUCKET: str = "telemetry"

    # MQTT
    MQTT_BROKER: str = "mosquitto"
    MQTT_PORT: int = 1883

    # Aplicação
    APP_TIMEZONE: str = "America/Sao_Paulo"

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()