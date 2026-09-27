from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # PostgreSQL
    POSTGRES_USER: str = "iot_user"
    POSTGRES_PASSWORD: str = "iot_password"
    POSTGRES_DB: str = "smart_fan_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # InfluxDB
    INFLUXDB_URL: str = "http://influxdb:8086"
    INFLUXDB_TOKEN: str = "my-super-secret-auth-token-12345"
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