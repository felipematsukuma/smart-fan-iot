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
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
    INFLUXDB_TIMEOUT_MS: int = 2000

    APP_TIMEZONE: str = "America/Sao_Paulo"

    @property
    def database_url(self) -> str:
        # O driver é explicitado de propósito. Sem o sufixo, o SQLAlchemy 2.1
        # passou a assumir `psycopg` (v3) em `postgresql://`, enquanto o projeto
        # instala `psycopg2-binary` — o build quebrava com
        # "ModuleNotFoundError: No module named 'psycopg'". Fixar o driver aqui
        # deixa a URL correta em qualquer versão do SQLAlchemy.
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
